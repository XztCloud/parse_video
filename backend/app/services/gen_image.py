from datetime import datetime
import enum

from pathlib import Path
import random
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
import requests
from app.config import settings
import httpx

from app.util import retry_on_httpx_error

from celery.utils.log import get_task_logger

from app.services.comfy.api_comfy import ApiComfy
from app.services.comfy.wrap_comfy import WrapComfy


logger = get_task_logger(__name__)

class ImageSize(enum.Enum):
    SIZE_512x512 = "512x512"
    SIZE_512x640 = "512x640"

    SIZE_1024x1024 = "1024x1024"
    SIZE_960x1280  = "960x1280"
    SIZE_768x1024  = "768x1024"
    SIZE_720x1440  = "720x1440"
    SIZE_720x1280  = "720x1280"

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
        gen_image_params.seed= random.randint(1000000000, 9999999999)
        image_info = await self._request_generate(gen_image_params=gen_image_params)
        images_path = []
        for i, image_info in enumerate(image_info['images']):
            file_name=prefix + '_' + str(i) + '.png'
            image_url = image_info['url']
            print(f'url: {image_url}, save_dir: {save_dir}, file_name: {file_name}')
            img_path = await self._download_image(url=image_url, save_dir=save_dir, file_name=file_name)
            images_path.append(img_path)
        return images_path


    async def gen_image_local(self, img_type: Literal['male', 'female', 'scene'], gen_image_params: GenImageParams, save_dir:str|Path, prefix:str) -> list[Path]:
        gen_image_params.seed= random.randint(100000000000000, 999999999999999)
        positive_prompt = gen_image_params.prompt
        negative_prompt = gen_image_params.negative_prompt
        api = ApiComfy()
        if img_type in ['male', 'female']:
            wf = WrapComfy("app/services/comfy/resource/workflow/generate_portrait.json")

        logger.info(f'gen_image_local img_type:{img_type}, seed:{gen_image_params.seed}')

        wf.set_node_param("空Latent图像", "height", gen_image_params.image_size.height)
        wf.set_node_param("空Latent图像", "width", gen_image_params.image_size.width)

        wf.set_node_param("CLIP Text Encode (Positive Prompt)", "text", positive_prompt)
        if negative_prompt:
            wf.set_node_param("CLIP Text Encode (Negative Prompt)", "text", negative_prompt)

        if img_type == 'male':
            wf.set_node_param("加载图像", "image", "male_portrait.png")
        elif img_type == 'female':
            wf.set_node_param("加载图像", "image", "female_portrait.png")

        wf.set_node_param("K采样器", "seed", gen_image_params.seed)

        results = await api.queue_and_wait_images(wf, output_node_title="保存图像")
        cnt = 0
        img_path = []
        for _, image_data in results.items():
            file_name = f'{prefix}_{cnt}.png'
            dest_dir = Path(save_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / file_name

            with open(out_path, "wb+") as f:
                f.write(image_data)
            img_path.append(out_path)
            cnt += 1
        return img_path



