import asyncio
import enum

import json
from pathlib import Path
import random
import time
from typing import Any, Callable, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from app.config import settings
import httpx
from app.tasks.process_loop_manager import process_loop
from app.util import make_dir, retry_on_httpx_error, runninghub_api_semaphore

from celery.utils.log import get_task_logger

from app.services.comfy.api_comfy import ApiComfy
from app.services.comfy.wrap_comfy import WrapComfy

# runninghub 并发限制统一走 util.runninghub_api_semaphore（limit=1，会员等级并发只有1）

# RunningHub「minimax H3 多人音频驱动」工作流节点常量（nodeInfoList 精确映射见 plan）
# prompt / 音频 / 分辨率 与音频切片槽位固定，参考图支持 8 个槽位（不足填 "None"）
H3_VIDEO_PROMPT_NODE = {"nodeId": "136", "fieldName": "prompt", "description": "prompt"}
H3_VIDEO_AUDIO_NODE = {"nodeId": "171", "fieldName": "audio", "description": "audio"}
H3_VIDEO_AUDIO_START_NODE = {"nodeId": "200", "fieldName": "value", "description": "音频起点"}
H3_VIDEO_AUDIO_DUR_NODE = {"nodeId": "201", "fieldName": "value", "description": "音频时长"}
H3_VIDEO_IMAGE_NODE_IDS = [137, 202, 203, 205, 206, 209, 210, 211]
H3_VIDEO_ASPECT_RATIO_NODE = {
    "nodeId": "115",
    "fieldName": "aspect_ratio",
    "fieldData": '["COMBO", {"default": "1:1 (Square)", "options": ["1:1 (Square)", "2:3 (Portrait Photo)", "3:2 (Photo)", "3:4 (Portrait Standard)", "4:3 (Standard)", "9:16 (Portrait Widescreen)", "16:9 (Widescreen)", "21:9 (Ultrawide)"], "tooltip": "The aspect ratio for the output dimensions.", "multiselect": false}]',
    "description": "aspect_ratio",
}
H3_VIDEO_MEGAPIXELS_NODE = {"nodeId": "115", "fieldName": "megapixels", "description": "megapixels"}



logger = get_task_logger(__name__)

class ImageSize(enum.Enum):
    SIZE_768x1280= "768x1280"
    
    SIZE_512x512 = "512x512"
    SIZE_512x640 = "512x640"
    SIZE_720x1280 = "720x1280"
    SIZE_1280x720 = "1280x720"

    SIZE_1024x1024 = "1024x1024"
    SIZE_960x1280  = "960x1280"
    SIZE_768x1024  = "768x1024"
    SIZE_720x1440  = "720x1440"

    SIZE_1328x1328 = "1328x1328"
    SIZE_1664x928 = "1664x928"
    SIZE_928x1664 = "928x1664"
    SIZE_1472x1140 = "1472x1140"
    SIZE_1140x1472 = "1140x1472"
    SIZE_1584x1056 = "1584x1056"
    SIZE_1056x1584 = "1056x1584"

    @property
    def dimensions(self) -> tuple[int, int]:
        w, h = self.value.split('x')
        return int(w), int(h)
    
    @property
    def width(self) -> int:
        return self.dimensions[0]
    
    @property
    def height(self) -> int:
        return self.dimensions[1]

class VideoSize(enum.Enum):
    SIZE_512x512 = "512x512"
    SIZE_480x848 = "480x848"
    SIZE_848x480 = "848x480"
    
    SIZE_864x480 = "864x480"
    @property
    def dimensions(self) -> tuple[int, int]:
        w, h = self.value.split('x')
        return int(w), int(h)
    
    @property
    def width(self) -> int:
        return self.dimensions[0]
    
    @property
    def height(self) -> int:
        return self.dimensions[1]

class ReferImageInfo(BaseModel):
    type: Literal['role', 'scene', 'frame', 'audio', 'ref']
    path: str
    name_comfy: str | None = Field(default=None)


class GenImageParams(BaseModel):
    prompt: str = Field(
        ...,
        description='生图提示词'
    )
    image_size: ImageSize = Field(
        ...,
        description='图片大小'
    )
    negative_prompt: Optional[str] = Field(default=None, description='指定不希望在生成图片中出现的内容。')
    batch_size:int = Field(default=1, ge=1, le=4, description='批量生图')
    seed:Optional[int] = Field(default=None, le=9999999999, description='随机种子，用于控制生成过程的随机性。使用相同的种子值可以生成相似的图片。')
    seed2:Optional[int] = Field(default=None, le=9999999999, description='随机种子，用于控制生成过程的随机性。使用相同的种子值可以生成相似的图片。在人物四视图中使用')
    num_inference_steps:int = Field(default=20, ge=0, le=100, description='推理步数。步数越多，生成质量通常越高，但耗时也更长。')
    guidance_scale: float = Field(
        default=0.75, le=20.0, 
        description='该值用于控制生成图片与给定提示词的匹配程度。值越高，生成图片越倾向于严格匹配文本提示词；' \
        '值越低，生成图片越具创意和多样性，可能包含更多意外元素。仅适用于 Kwai-Kolors/Kolors。'
    )
    images_path: List[str] = Field(default=[], description='返回的图片路径')
    refer_images: List[ReferImageInfo] = Field(default=[], description='参考图片信息')
    
class RunningHubAPI:
    __isinstance = None
    def __new__(cls, *rags, **kwargs):
        if cls.__isinstance is None:
            cls.__isinstance = super().__new__(cls)
        return cls.__isinstance

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.workflow_url = 'https://www.runninghub.cn/openapi/v2/run/ai-app/'
        self.query_url = 'https://www.runninghub.cn/openapi/v2/query'
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            # 不写死 Content-Type：json= 会自动带 application/json，files= 会自动带 multipart boundary
        }
        self._client: Optional[httpx.AsyncClient] = None
    
    
    async def _get_client(self) -> httpx.AsyncClient:
        """惰性创建并复用 AsyncClient"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client
    
    async def submit_task(
        self,
        node_info_list: List[dict],
        app_id: str = "2091778403019091969",
        instance_type: str = "default",
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交生成任务

        Args:
            node_info_list: 节点参数映射列表
            instance_type: 实例类型 (default: 24G显存, plus: 48G显存)
            webhook_url: Webhook回调地址 (可选)

        Returns:
            包含 taskId 等信息的响应字典
        """
        client = await self._get_client()
        payload = {
            "nodeInfoList": node_info_list,
            "instanceType": instance_type,
            "usePersonalQueue": "false",
        }
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        response = await client.post(self.workflow_url + app_id, json=payload)
        response.raise_for_status()
        return response.json()
    
    async def query_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态"""
        client = await self._get_client()
        response = await client.post(
            self.query_url,
            json={"taskId": task_id},
        )
        response.raise_for_status()
        return response.json()
    
    async def wait_for_completion(
        self,
        task_id: str,
        max_wait_seconds: int = 300,
        poll_interval: float = 5.0,
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        """等待任务完成（非阻塞轮询）

        Args:
            task_id: 任务ID
            max_wait_seconds: 最大等待时间（秒）
            poll_interval: 轮询间隔（秒）
            status_callback: 每次轮询状态变化时的回调 (可选)

        Returns:
            任务完成后的完整结果
        """
        start_time = time.monotonic()

        while time.monotonic() - start_time < max_wait_seconds:
            result = await self.query_task_status(task_id)
            status = result.get("status")

            if status == "SUCCESS":
                return result
            if status == "FAILED":
                error_msg = result.get("errorMessage", "未知错误")
                raise RuntimeError(f"[{task_id}] 任务失败: {error_msg}")
            if status in ("QUEUED", "RUNNING"):
                if status_callback:
                    status_callback(task_id, status)
            else:
                raise RuntimeError(f"[{task_id}] 未知任务状态: {status}")

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"[{task_id}] 任务超时（超过 {max_wait_seconds}秒）")
    
    async def download_result(self, result_url: str, output_path: str) -> str:
        """异步流式下载生成的结果"""
        client = await self._get_client()
        async with client.stream("GET", result_url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
        return output_path

    async def upload_media(self, file_path: str) -> str:
        """上传图片/音频等媒体文件到 RunningHub，返回 nodeInfoList fieldValue 可用的托管文件路径。

        Args:
            file_path: 本地文件路径（png / mp3 等）

        Returns:
            可直接填入 nodeInfoList 的托管文件路径（如 openapi/<hash>.png）。
            复用共享 client（headers 已去掉固定 Content-Type，files= 自动走 multipart）。
        """
        client = await self._get_client()
        upload_url = "https://www.runninghub.cn/openapi/v2/media/upload/binary"
        name = Path(file_path).name
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        files = {"file": (name, file_bytes)}
        response = await client.post(upload_url, files=files)
        response.raise_for_status()
        resp = response.json()
        logger.info(f"[runninghub] upload_media {name} 原始响应: {resp}")

        # 响应结构：{"code":0,"data":{"download_url":..., "fileName":"openapi/<hash>.png", ...}}
        data = resp.get("data") or resp
        if isinstance(data, str):
            return data
        for key in ("fileName", "url", "name", "filename", "file_name"):
            value = data.get(key) if isinstance(data, dict) else None
            if value:
                return str(value)
        raise RuntimeError(f"[runninghub] 上传媒体失败，无法解析上传返回: {resp}")
    
    async def generate(
        self,
        prompt: str,
        width: int = 1280,
        height: int = 720,
        task_type: Literal['four_view', 't2i'] = "four_view",
        output_prefix: str = "assert_pic",
        max_wait_seconds: int = 300,
        poll_interval: float = 5.0,
    ) -> List[Path]:
        """用单个提示词生成并下载图片（完整流程）

        Returns:
            已下载的图片文件路径列表（只统计 png 类型）
        """
        if task_type == 'four_view':
            node_info_list =  [
                {
                    "nodeId": 4,
                    "fieldName": "text",
                    "fieldValue": prompt,
                    "description": "text",
                }
            ]
            app_id = '2091712694423482369'
        elif task_type == 't2i':
            node_info_list =  [
                {
                "nodeId": "4",
                "fieldName": "text",
                "fieldValue": prompt,
                "description": "text"
                },
                {
                "nodeId": "7",
                "fieldName": "width",
                "fieldValue": str(width),
                "description": "width"
                },
                {
                "nodeId": "7",
                "fieldName": "height",
                "fieldValue": str(height),
                "description": "height"
                }
            ]
            app_id = '2091778403019091969'
        else:
            raise ValueError(f"不支持的 task_type: {task_type}")
        
        
        # runninghub 并发统一走模块级 runninghub_api_semaphore（limit=1，会员等级并发只有1）
        async with runninghub_api_semaphore.slot(timeout=30):
            submit_result = await self.submit_task(
                node_info_list=node_info_list,
                app_id=app_id
            )
            task_id = submit_result.get("taskId") or submit_result.get("task_id")
            if not task_id:
                raise RuntimeError(
                    f"API响应中未包含taskId，可用字段: {list(submit_result.keys())}"
                )
            logger.info(f"🚀 任务已提交 [{task_id}] 类型：{task_type} 输入: {prompt}  {width}x{height}")

            result = await self.wait_for_completion(
                task_id,
                max_wait_seconds=max_wait_seconds,
                poll_interval=poll_interval,
                status_callback=lambda tid, st: logger.info(f"   [{tid}] 状态: {st} ..."),
            )
            logger.info(f"✓ [{task_id}] 任务完成")

            results = result.get("results", [])
            if not results:
                raise RuntimeError(f"[{task_id}] 任务成功但没有返回结果")

            downloaded: List[str] = []
            for i, item in enumerate(results):
                result_url = item.get("url")
                output_type = item.get("outputType")
                if not result_url or output_type != "png":
                    continue
                output_path = await self.download_result(
                    result_url, f"{output_prefix}_{i}.png"
                )
                downloaded.append(output_path)
                logger.info(f"   ✓ [{task_id}] 已下载: {output_path}")

            return [Path(p) for p in downloaded]

class GenVideoParams(BaseModel):
    prompt: str = Field(
        ...,
        description='生视频提示词'
    )
    video_size: VideoSize = Field(
        ...,
        description='视频大小'
    )
    duration: float = Field(
        ...,
        ge=1, le=15,
        description='分镜时长'
    )
    rate: int = Field(
        default= 24,
        ge=15, le=30,
        description='帧率'
    )
    
    seed:Optional[int] = Field(default=None, le=9999999999, description='随机种子，用于控制生成过程的随机性。使用相同的种子值可以生成相似的图片。')
    video_path: List[str] = Field(default=[], description='返回的视频路径')
    refer_images: List[ReferImageInfo] = Field(default=[], description='参考图片/音频信息')
    

def _h3_aspect_megapixels(video_size: VideoSize) -> tuple[str, str]:
    """把 VideoSize 映射为 runninghub H3 工作流的 aspect_ratio + megapixels。"""
    w, h = video_size.width, video_size.height
    if w > h:
        ratio = "16:9 (Widescreen)"
    elif w < h:
        ratio = "9:16 (Portrait Widescreen)"
    else:
        ratio = "1:1 (Square)"
    mega = str(max(0.4, round(w * h / 1e6, 1)))
    return ratio, mega


def generate_refer_imag_nodes(wf: WrapComfy, last_latent_positive: str, last_latent_negative: str, index: int, name_comfy: str):
    
    # 复制加载图像节点
    ori_loadimage_node = '加载图像'
    new_loadimage_node = ori_loadimage_node + str(index)
    wf.copy_node(ori_title=ori_loadimage_node, new_title=new_loadimage_node)
    
    # 复制缩放节点
    ori_scale_node = '缩放图像（长边）'
    new_scale_node = ori_scale_node + str(index)
    wf.copy_node(ori_title=ori_scale_node, new_title=new_scale_node)
    
    # 复制VAE编码节点
    ori_vae_encode_node = 'VAE编码'
    new_vae_encode_node = ori_vae_encode_node + str(index)
    wf.copy_node(ori_title=ori_vae_encode_node, new_title=new_vae_encode_node)
    
    ori_latent_positive_node = '参考Latent-正面'
    ori_latent_negative_node = '参考Latent-负面'
    
    # last_latent_positive = ori_latent_positive_node
    # last_latent_negative = ori_latent_negative_node
    
    # 正面条件
    new_latent_positive_node = ori_latent_positive_node + str(index)
    wf.copy_node(ori_title=ori_latent_positive_node, new_title=new_latent_positive_node)
    
    # 负面条件
    new_latent_negative_node = ori_latent_negative_node + str(index)
    wf.copy_node(ori_title=ori_latent_negative_node, new_title=new_latent_negative_node)
    
    # 连线 加载图像 - 缩放
    load_img_id = wf.get_node_id(new_loadimage_node)
    wf.set_node_param(new_scale_node, 'images', [load_img_id, 0]) 
    
    # 连线 缩放/加载vae - vae编码
    scale_id = wf.get_node_id(new_scale_node)
    wf.set_node_param(new_vae_encode_node, 'pixels', [scale_id, 0]) 
    vae_id = wf.get_node_id('加载VAE')
    wf.set_node_param(new_vae_encode_node, 'vae', [vae_id, 0]) 
    
    # 连线 上一个latent-正面/vae编码 - 正面条件
    last_latent_positive_id = wf.get_node_id(last_latent_positive)
    wf.set_node_param(new_latent_positive_node, 'conditioning', [last_latent_positive_id, 0]) 
    last_latent_positive = new_latent_positive_node # 给下一个latent或K采样器连
    vae_enc_id = wf.get_node_id(new_vae_encode_node)
    wf.set_node_param(new_latent_positive_node, 'latent', [vae_enc_id, 0]) 
    
    # 连线 上一个latent-负面/vae编码 - 负面条件
    last_latent_negative_id = wf.get_node_id(last_latent_negative)
    wf.set_node_param(new_latent_negative_node, 'conditioning', [last_latent_negative_id, 0])
    last_latent_negative = new_latent_negative_node
    vae_enc_id = wf.get_node_id(new_vae_encode_node)
    wf.set_node_param(new_latent_negative_node, 'latent', [vae_enc_id, 0]) 
    
    # 连线 上一个latent-正面 - K采样器
    last_latent_positive_id = wf.get_node_id(last_latent_positive)
    wf.set_node_param('K采样器', 'positive', [last_latent_positive_id, 0])
    
    # 连线 上一个latent-负面面 - K采样器
    last_latent_negative_id = wf.get_node_id(last_latent_negative)
    wf.set_node_param('K采样器', 'negative', [last_latent_negative_id, 0])
    
    # 赋值图片
    wf.set_node_param(new_loadimage_node, 'image', name_comfy) 
    
    return last_latent_positive, last_latent_negative

class GenImage:

    def __init__(self):
        self.model_name = settings.IMAGE_MODEL_NAME
        self.api_key = settings.IMAGE_MODEL_API_KEY
        self.base_url = settings.IMAGE_MODEL_BASE_URL

    @retry_on_httpx_error
    async def _request_generate(self, gen_image_params: GenImageParams):
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        params = gen_image_params.model_dump(mode='json', exclude_none=True)
        payload = {
            "model": self.model_name,
            **params
        }
        result=None
        logger.info(f'request full url:{self.base_url}, payload is {payload}')
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request("POST", self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                logger.info(f'gen image result:{result}, type is {type(result)}')
        except httpx.HTTPStatusError as exc:
            # 捕获 HTTP 错误（如 400, 401, 500 等）
            logger.error(f"HTTP 错误，状态码: {exc.response.status_code}")
            logger.error(f"错误返回内容: {exc.response.text}")
            raise

        except httpx.RequestError as exc:
            # 捕获网络连接错误（如断网、超时、DNS 解析失败等，此时连状态码都没有）
            logger.error(f"_request_generate 网络连接失败: {exc.request.url} 无法访问")
            raise
        return result
    
    @retry_on_httpx_error
    async def _download_image(self, url: str, save_dir: str|Path, file_name: str) -> Path:
        """
        异步下载图片到指定文件夹
        :param url: 图片的下载链接
        :param save_dir: 存储的目标文件夹路径
        :param file_name: 保存的文件名（例如 'output.png'）
        """
        # 1. 确保目标文件夹存在（如果不存在则自动创建）
        dest_dir = Path(save_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_path = dest_dir / file_name

        # 2. 发起异步流式请求
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", url) as response:
                    # 检查 HTTP 状态码是否成功（非 2xx 会直接抛出异常）
                    response.raise_for_status()
                    
                    # 3. 异步写入文件（推荐分块读取，防止大图片撑爆内存）
                    # 注：标准 open() 是同步的，对于普通的图片下载，其同步 I/O 阻塞影响极小。
                    with open(file_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
        except httpx.HTTPStatusError as exc:
            # 捕获 HTTP 错误（如 400, 401, 500 等）
            logger.error(f"HTTP 错误，状态码: {exc.response.status_code}")
            logger.error(f"错误返回内容: {exc.response.text}")
            raise

        except httpx.RequestError as exc:
            # 捕获网络连接错误（如断网、超时、DNS 解析失败等，此时连状态码都没有）
            print(f"_download_image 网络连接失败: {exc.request.url} 无法访问")
            raise
                        
        print(f"✅ 图片下载成功: {file_path}")
        return file_path

    async def gen_image(self,  gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list[Path]:
        if not gen_image_params.seed:
            gen_image_params.seed = random.randint(1000000000, 9999999999)
        image_info = await self._request_generate(gen_image_params=gen_image_params)
        images_path = []
        for i, image_info in enumerate(image_info['images']):
            file_name=prefix + '_' + str(i) + '_' + str(round(time.time() * 1000)) + '.png'
            image_url = image_info['url']
            print(f'url: {image_url}, save_dir: {save_dir}, file_name: {file_name}')
            img_path = await self._download_image(url=image_url, save_dir=save_dir, file_name=file_name)
            images_path.append(img_path)
        return images_path

    @staticmethod
    async def gen_image_local_sd15(img_type: Literal['role', 'scene', 'segment'], gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list[Path]:
        if not gen_image_params.seed:
            gen_image_params.seed= random.randint(100000000000000, 999999999999999)
        positive_prompt = gen_image_params.prompt
        negative_prompt = gen_image_params.negative_prompt
        api = ApiComfy()
        if img_type == 'role':
            wf = WrapComfy("app/services/comfy/resource/workflow/generate_portrait.json")

        logger.info(f'gen_image_local img_type:{img_type}, seed:{gen_image_params.seed}')

        wf.set_node_param("空Latent图像", "height", gen_image_params.image_size.height)
        wf.set_node_param("空Latent图像", "width", gen_image_params.image_size.width)

        wf.set_node_param("CLIP Text Encode (Positive Prompt)", "text", positive_prompt)
        if negative_prompt:
            wf.set_node_param("CLIP Text Encode (Negative Prompt)", "text", negative_prompt)

        wf.set_node_param("加载图像", "image", "male_portrait.png")

        wf.set_node_param("K采样器", "seed", gen_image_params.seed)

        results = await api.queue_and_wait_images(wf, output_node_title="保存图像")
        cnt = 0
        img_path = []
        for name_in_comfy, image_data in results.items():
            logger.info(f'name_in_comfy is {name_in_comfy}')
            file_name = f'{prefix}_{cnt}_{str(round(time.time() * 1000))}.png'
            dest_dir = Path(save_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / file_name

            with open(out_path, "wb+") as f:
                f.write(image_data)
            img_path.append(out_path)
            cnt += 1
        return img_path

    @staticmethod
    async def t2i_local_flux2_klien(gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list[Path]:
        """使用flux本地流水线生成图片

        Args:
            gen_image_params (GenImageParams): 提示词、size等可变参数
            save_dir (str | Path): 保存路径
            prefix (str): 保存文件前缀，场景名

        Returns:
            str: 图片路径
        """
        if not gen_image_params.seed:
            gen_image_params.seed= random.randint(100000000000000, 999999999999999)
        positive_prompt = gen_image_params.prompt
        
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/worker_textToImage.json")
        
        wf.set_node_param("空Latent图像", "height", gen_image_params.image_size.height)
        wf.set_node_param("空Latent图像", "width", gen_image_params.image_size.width)
        wf.set_node_param("Input Text", "text", positive_prompt)
        wf.set_node_param("K采样器", "seed", gen_image_params.seed)
        logger.info('begine wait images')
        results = await api.queue_and_wait_images(wf, output_node_title="Save Image")
        # logger.info(f'end wait images, results is {results}')
        cnt = 0
        img_path = []
        for name_in_comfy, image_data in results.items():
            logger.info(f'name_in_comfy is {name_in_comfy}')
            file_name = f'{prefix}_{cnt}.png'
            dest_dir = Path(save_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / file_name

            with open(out_path, "wb+") as f:
                f.write(image_data)
            img_path.append([name_in_comfy, out_path])
            cnt += 1
        return img_path
        
    @staticmethod
    async def i2i_local_flux2_klien(gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list:
        """多图参考生成视频帧图片

        Args:
            gen_image_params (GenImageParams): 提示词、size、参考图等
            save_dir (str | Path): 保存路径
            prefix (str): 名称前缀

        Raises:
            Exception: _description_

        Returns:
            list: _description_
        """
        if len(gen_image_params.refer_images) == 0:
            raise Exception('not find any refer image')
        
        if not gen_image_params.seed:
            gen_image_params.seed= random.randint(100000000000000, 999999999999999)
        logger.info(f'random seed: {gen_image_params.seed}')
        positive_prompt = gen_image_params.prompt
        
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/worker_multiImageFusion.json")
        
        last_latent_positive = '参考Latent-正面'
        last_latent_negative = '参考Latent-负面'
        for i, refer_img in enumerate(gen_image_params.refer_images):
            if i == 0:
                wf.set_node_param('加载图像', 'image', refer_img.name_comfy) 
            else:
                # 开始赋值节点组
                last_latent_positive, last_latent_negative = generate_refer_imag_nodes(
                    wf=wf, last_latent_positive=last_latent_positive, last_latent_negative=last_latent_negative, 
                    index=i, name_comfy=refer_img.name_comfy)
        
        wf.set_node_param("空Latent图像（Flux2）", "height", gen_image_params.image_size.height)
        wf.set_node_param("空Latent图像（Flux2）", "width", gen_image_params.image_size.width)
        wf.set_node_param('Input Text', 'text', positive_prompt) 
        wf.set_node_param("K采样器", "seed", gen_image_params.seed)
            
        # 保存文件，用于测试
        # wf.save_to_file("app/services/comfy/resource/workflow/worker_multiImageFusion2.json")
        
        results = await api.queue_and_wait_images(wf, output_node_title="保存图像")
        cnt = 0
        img_path = []
        for name_in_comfy, image_data in results.items():
            logger.info(f'name_in_comfy is {name_in_comfy}')
            file_name = f'{prefix}_{cnt}.png'
            dest_dir = Path(save_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / file_name

            with open(out_path, "wb+") as f:
                f.write(image_data)
            img_path.append([name_in_comfy, out_path])
            cnt += 1
        return img_path

    @staticmethod
    async def ai2v_local_ltx23(gen_video_params: GenVideoParams, save_dir:str|Path) -> str:
        """音频和图片生成视频

        Args:
            gen_video_params (GenVideoParams): 参考帧等
            save_dir (str | Path): 保存路径

        Raises:
            Exception: 没有参考帧

        Returns:
            str: 视频路径
        """
        if len(gen_video_params.refer_images) == 0:
            raise Exception('not find any refer asset')
        if not gen_video_params.seed:
            gen_video_params.seed= random.randint(100000000000000, 999999999999999)
        logger.info(f'random seed: {gen_video_params.seed}')
        max_frames = int(gen_video_params.duration*gen_video_params.rate+1)
        timeline_data_dict = {
            "segments": [
                {
                    "prompt": gen_video_params.prompt,
                    "length": max_frames,
                    "color": "#d9534f"
                }
            ]
        }
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/worker_ltx23_ai2v.json")
        width = gen_video_params.video_size.width
        height = gen_video_params.video_size.height
        if width > height:
            width = 848
            height = 480
        elif width < height:
            width = 480
            height = 848
        else:
            width = 512
            height = 512
        wf.set_node_param('输入宽', 'width', width)
        wf.set_node_param('输入高', 'height', height)
        # TODO: 目前只适配首帧
        for asset in gen_video_params.refer_images:
            if asset.type == 'frame':
                wf.set_node_param('Multi Image Loader', 'image_paths', asset.name_comfy)
            if asset.type == 'audio':
                wf.set_node_param('加载音频', 'audio', asset.name_comfy)
        wf.set_node_param('时长', 'value', gen_video_params.duration)
        wf.set_node_param('帧率', 'value', gen_video_params.rate)
        wf.set_node_param('分段控制', 'max_frames', max_frames)
        wf.set_node_param('分段控制', 'local_prompts', gen_video_params.prompt)
        wf.set_node_param('分段控制', 'timeline_data', json.dumps(timeline_data_dict))
        wf.set_node_param('分段控制', 'segment_lengths', str(max_frames))
        wf.save_to_file('app/services/comfy/resource/workflow/worker_ltx23_ai2v_2.json')
        # raise 
        gen_video_params.video_path = await api.download_and_save_videos(wf=wf, output_node_title='保存视频', save_dir=save_dir)
        return gen_video_params.video_path[0]

    @staticmethod
    async def test_get_video():
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/test_get_video.json")
        save_dir = settings.UPLOAD_DIR + '/clone_' + str(46) + '/segment_test'
        make_dir(save_dir, re_create=False)
        path = await api.download_and_save_videos(wf=wf, output_node_title='保存视频', save_dir=save_dir)
        print(f'path is {path}')
        
    @staticmethod
    async def t2i_local_krea2(gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list[Path]:
        """使用本地krea2模型文本生图片

        Args:
            gen_image_params (GenImageParams): 参考提示词、size
            save_dir (str | Path): 保存路径
            prefix (str): 文件前缀

        Raises:
            Exception: _description_

        Returns:
            list[Path]: 图片路径
        """
        if not gen_image_params.seed:
            gen_image_params.seed= random.randint(100000000000000, 999999999999999)
        positive_prompt = gen_image_params.prompt
        
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/worker_krea2_t2i.json")
        
        wf.set_node_param("空Latent图像", "height", gen_image_params.image_size.height)
        wf.set_node_param("空Latent图像", "width", gen_image_params.image_size.width)
        wf.set_node_param("CLIP文本编码", "text", positive_prompt)
        wf.set_node_param("K采样器", "seed", gen_image_params.seed)
        logger.info('begine wait images')
        results = await api.queue_and_wait_images(wf, output_node_title="保存图像")
        # logger.info(f'end wait images, results is {results}')
        cnt = 0
        img_path = []
        for name_in_comfy, image_data in results.items():
            logger.info(f'name_in_comfy is {name_in_comfy}')
            file_name = f'{prefix}_{cnt}.png'
            dest_dir = Path(save_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / file_name

            with open(out_path, "wb+") as f:
                f.write(image_data)
            img_path.append([name_in_comfy, out_path])
            cnt += 1
        return img_path
    
    @staticmethod
    async def t2i_role_local_krea2(gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list[Path]:
        """根据人物形象图生成完整四视图

        Args:
            gen_image_params (GenImageParams): 人物形象图以及宽高等参数
            save_dir (str | Path): 保存路径
            prefix (str): 文件前缀

        Raises:
            Exception: _description_

        Returns:
            list[Path]: 输出图片保存路径
        """
        if not gen_image_params.seed:
            gen_image_params.seed= random.randint(100000000000000, 999999999999999)
        if not gen_image_params.seed2:
            gen_image_params.seed2= random.randint(100000000000000, 999999999999999)
        positive_prompt = gen_image_params.prompt
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/worker_krea2_四视图.json")
        wf.set_node_param("CLIP文本编码 (阶段1)", "text", positive_prompt)
        wf.set_node_param("K采样器 (阶段1)", "seed", gen_image_params.seed)
        wf.set_node_param("K采样器 (阶段2)", "seed", gen_image_params.seed2)
        logger.info('begine wait images')
        results = await api.queue_and_wait_images(wf, output_node_title="保存四视图图像")
        # logger.info(f'end wait images, results is {results}')
        cnt = 0
        img_path = []
        for name_in_comfy, image_data in results.items():
            logger.info(f'name_in_comfy is {name_in_comfy}')
            file_name = f'{prefix}_{cnt}.png'
            dest_dir = Path(save_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / file_name

            with open(out_path, "wb+") as f:
                f.write(image_data)
            img_path.append([name_in_comfy, out_path])
            cnt += 1
        return img_path
    
    @staticmethod
    async def i2v_local_minimax_h3(gen_video_params: GenVideoParams, save_dir:str|Path) -> str:
        """使用ref关联图通过本地minimax_h3模型生成视频

        Args:
            gen_video_params (GenVideoParams): 视频参数
            save_dir (str | Path): 保存文件夹路径

        Raises:
            Exception: _description_

        Returns:
            str: 视频路径
        """
        if not gen_video_params.seed:
            gen_video_params.seed= random.randint(100000000000000, 999999999999999)
        logger.info(f'random seed: {gen_video_params.seed}')
        api = ApiComfy()
        wf = WrapComfy("app/services/comfy/resource/workflow/worker_minimax_h3_8lora_refi2v.json")
        base_link_ref = 'ref_images.ref_image_'
        for index, ref_img in enumerate(gen_video_params.refer_images):
            if index == 0:
                # 设置加载图片节点
                wf.set_node_param('加载图像', 'image', ref_img.name_comfy)
                continue
            # 复制加载图像节点，将其他参考图片加入加载到其中
            ori_loadimage_node = '加载图像'
            new_loadimage_node = ori_loadimage_node + str(index)
            wf.copy_node(ori_title=ori_loadimage_node, new_title=new_loadimage_node)
            wf.set_node_param(new_loadimage_node, 'image', ref_img.name_comfy)
            
            id = wf.get_node_id(new_loadimage_node)
            wf.set_node_param('MiniMax H3 Reference to Video', base_link_ref+str(index), [id, 0])
        
        wf.set_node_param('Float (Duration)', 'value', gen_video_params.duration)
        wf.set_node_param('提示词，如果要ai扩写，请加一句帮我写提示词', 'value', gen_video_params.prompt)
        wf.set_node_param("随机噪波", "noise_seed", gen_video_params.seed)
        wf.set_node_param('MiniMax H3 Reference to Video', 'width', gen_video_params.video_size.width)
        wf.set_node_param('MiniMax H3 Reference to Video', 'height', gen_video_params.video_size.height)

        wf.save_to_file('app/services/comfy/resource/workflow/worker_minimax_h3_8lora_refi2v_runtime.json')
        gen_video_params.video_path = await api.download_and_save_videos(wf=wf, output_node_title='保存视频', save_dir=save_dir)
        return gen_video_params.video_path[0]
    
    @staticmethod
    async def i2v_runninghub_h3(
        gen_video_params: GenVideoParams,
        save_dir: str | Path,
        audio_start: float,
        audio_duration: float,
    ) -> str:
        """使用 runninghub「minimax H3 多人音频驱动」工作流，参考图 + 完整音频生成分镜视频。

        Args:
            gen_video_params: 提示词 / 尺寸 / 参考图(type='ref') / 完整音频(type='audio')
            save_dir: 下载保存目录
            audio_start: 完整音频内切片起点（秒），跨镜长句按累计已消耗位置传入
            audio_duration: 本组使用的音频片段时长（秒）

        Returns:
            本地 mp4 路径（原始下载，含口型参考音轨；旁白合入由上层负责）
        """
        if not gen_video_params.seed:
            gen_video_params.seed = random.randint(100000000000000, 999999999999999)
        make_dir(save_dir, re_create=False)

        runninghub_api = RunningHubAPI(api_key=settings.RUNNINGHUB_API_KEY, timeout=30)

        # 1. 并行上传参考图 / 完整音频（复用同一 client，多路复用连接）
        ref_assets = [a for a in gen_video_params.refer_images if a.type == 'ref']
        audio_assets = [a for a in gen_video_params.refer_images if a.type == 'audio']
        if not audio_assets:
            raise ValueError('i2v_runninghub_h3 缺少音频参考（audio 资产），无法生成音驱视频')
        audio_name = await runninghub_api.upload_media(audio_assets[0].path)
        ref_image_names = await asyncio.gather(*(runninghub_api.upload_media(a.path) for a in ref_assets))

        ratio, mega = _h3_aspect_megapixels(gen_video_params.video_size)

        node_info_list: list[dict] = [
            {**H3_VIDEO_AUDIO_NODE, "fieldValue": audio_name},
            {**H3_VIDEO_PROMPT_NODE, "fieldValue": gen_video_params.prompt},
            {**H3_VIDEO_ASPECT_RATIO_NODE, "fieldValue": ratio},
            {**H3_VIDEO_MEGAPIXELS_NODE, "fieldValue": mega},
            *[
                {"nodeId": str(node_id), "fieldName": "image",
                 "fieldValue": ref_image_names[idx] if idx < len(ref_image_names) else "None",
                 "description": f"image{idx + 1}"}
                for idx, node_id in enumerate(H3_VIDEO_IMAGE_NODE_IDS)
            ],
            {**H3_VIDEO_AUDIO_START_NODE, "fieldValue": str(audio_start)},
            {**H3_VIDEO_AUDIO_DUR_NODE, "fieldValue": str(audio_duration)},
        ]
        logger.info(f"[runninghub] h3 视频入参: {json.dumps(node_info_list, ensure_ascii=False)}")

        # 2. 提交 + 轮询（runninghub 队列并发 1）；下载在槽位外，不占用队列伪并发
        async with runninghub_api_semaphore.slot(timeout=60):
            submit_result = await runninghub_api.submit_task(
                node_info_list=node_info_list,
                app_id=settings.RUNNINGHUB_H3_VIDEO_APP_ID,
                instance_type=settings.RUNNINGHUB_H3_VIDEO_INSTANCE_TYPE,
            )
            task_id = submit_result.get("taskId") or submit_result.get("task_id")
            if not task_id:
                raise RuntimeError(f"[runninghub] 响应未包含 taskId: {submit_result}")
            logger.info(f"🚀 [runninghub] h3 视频任务已提交 [{task_id}] "
                        f"音频起点={audio_start}s 音频时长={audio_duration}s")

            result = await runninghub_api.wait_for_completion(
                task_id,
                max_wait_seconds=settings.RUNNINGHUB_VIDEO_MAX_WAIT_SECONDS,
                poll_interval=10.0,
                status_callback=lambda tid, st: logger.info(f"   [{tid}] 状态: {st} ..."),
            )
            logger.info(f"✓ [runninghub] [{task_id}] 任务完成")

            results = result.get("results", [])
            video_url = next(
                (item.get("url") for item in results
                 if item.get("outputType") == "mp4" and item.get("url")),
                None,
            )
            if not video_url:
                raise RuntimeError(f"[runninghub] [{task_id}] 任务成功但没有 mp4 结果: {results}")

        output_path = str(Path(save_dir) / f"runninghub_raw_{task_id}.mp4")
        await runninghub_api.download_result(video_url, output_path)
        logger.info(f"✓ [runninghub] 分镜视频已下载: {output_path}")
        return output_path

    @staticmethod
    async def t2i_runninghub_krea2(gen_image_params: GenImageParams, save_dir:str|Path, prefix:str='', task_type:Literal['four_view', 't2i'] = "four_view",) -> str:
        """调用runninghub AI应用生成图片

        Args:
            gen_image_params (GenImageParams): 生成图篇参数
            save_dir (str | Path): 保存文件夹路径
            prefix (str): 文件前缀

        Raises:
            Exception: _description_

        Returns:
            str: 返回生成图片路径
        """
        make_dir(save_dir, re_create=False)
        final_prefix = str(Path(save_dir) / prefix)
        runninghub_api = RunningHubAPI(api_key=settings.RUNNINGHUB_API_KEY)
        path_list = await runninghub_api.generate(
            prompt=gen_image_params.prompt, 
            width=gen_image_params.image_size.width, 
            height=gen_image_params.image_size.height, 
            output_prefix=final_prefix,
            task_type=task_type,
            max_wait_seconds=300)
        if len(path_list) == 2 and task_type == 'four_view':
            # 返回四视图图片路径
            return path_list[1:]
        return path_list
            
        
if __name__ == '__main__':
    process_loop.init_process()
    parama = GenImageParams(prompt='花园里的小男孩，11岁，玩泥巴，脏兮兮', image_size=ImageSize.SIZE_720x1280)
    result = process_loop.run(GenImage.t2i_runninghub_krea2(gen_image_params=parama, save_dir='./', prefix='test_role_img', task_type='four_view'))
    print(result)
    time.sleep(2)
    parama = GenImageParams(prompt='一个干净整洁的房间，有一个电脑桌，桌子上有rog台式电脑', image_size=ImageSize.SIZE_720x1280)
    result = process_loop.run(GenImage.t2i_runninghub_krea2(gen_image_params=parama, save_dir='./', prefix='test_scene_img', task_type='t2i'))
    print(result)