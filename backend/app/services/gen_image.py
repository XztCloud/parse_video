import asyncio
from datetime import datetime
import enum

import json
from pathlib import Path
import random
import time
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
import requests
from sqlalchemy import literal
from app.config import settings
import httpx

from app.util import make_dir, retry_on_httpx_error

from celery.utils.log import get_task_logger

from app.services.comfy.api_comfy import ApiComfy
from app.services.comfy.wrap_comfy import WrapComfy


logger = get_task_logger(__name__)

class ImageSize(enum.Enum):
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
    type: Literal['role', 'scene', 'frame', 'audio']
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
    num_inference_steps:int = Field(default=20, ge=0, le=100, description='推理步数。步数越多，生成质量通常越高，但耗时也更长。')
    guidance_scale: float = Field(
        default=0.75, le=20.0, 
        description='该值用于控制生成图片与给定提示词的匹配程度。值越高，生成图片越倾向于严格匹配文本提示词；' \
        '值越低，生成图片越具创意和多样性，可能包含更多意外元素。仅适用于 Kwai-Kolors/Kolors。'
    )
    images_path: List[str] = Field(default=[], description='返回的图片路径')
    refer_images: List[ReferImageInfo] = Field(default=[], description='参考图片信息')

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
        logger.info(f'end wait images, results is {results}')
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
        print('hello world.')
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
    async def ai2v_local_flux2_klien(gen_video_params: GenVideoParams, save_dir:str|Path) -> str:
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
        
if __name__ == '__main__':
    
    # parama = GenImageParams(prompt='女孩在唱歌', image_size=ImageSize.SIZE_720x1280)
    # asyncio.run(GenImage.i2i_local_flux2_klien(gen_image_params=parama, save_dir='./', prefix='test_img'))
    
    url = settings.COMFY_URL + '/upload/image'
    image_path = '/home/xztcloud/.smarttr/workspace/parse_video/backend/uploads/clone_45/熬夜上班族_0.png'
    image_path = '/home/xztcloud/.smarttr/workspace/parse_video/backend/uploads/clone_46/segment_f47ac10b-58cc-4372-a567-0e02b2c3d479_0.png'
    image_path = '/home/xztcloud/.smarttr/workspace/parse_video/backend/uploads/clone_46/segment_f47ac10b-58cc-4372-a567-0e02b2c3d479_0.png'
    with open(image_path, "rb") as f:
        # files 字典的 key 必须是 'image'
        files = {"image": f}
        # 如果需要，可以通过 overwrite 覆盖同名文件
        data = {"overwrite": "true"}
        response = requests.post(url, files=files, data=data)

    if response.status_code == 200:
        result = response.json()
        print(f'result name: {result["name"]}')  # 返回服务器上的文件名（例如: "example.png"）
    else:
        raise Exception(f"图片上传失败: {response.text}")