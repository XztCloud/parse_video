
import asyncio
import json
import os
import aiohttp
from urllib.parse import urlencode, urljoin
import uuid

import requests
import websockets

from app.config import settings
from celery.utils.log import get_task_logger
from requests.auth import HTTPBasicAuth

from app.services.comfy.wrap_comfy import WrapComfy

logger = get_task_logger(__name__)

class ApiComfy:
    def __init__(self):
        self.url = settings.comfy_ws_url
        self.auth = None
        if settings.COMFY_USER:
            self.auth = aiohttp.BasicAuth(login=settings.COMFY_USER, password=settings.COMFY_PASSWORD)
    
    async def queue_prompt(self, prompt: dict, client_id: str | None = None)->dict:
        p = {"prompt": prompt}
        if client_id:
            p["client_id"] = client_id
        
        logger.info(f"Posting prompt to {self.url}/prompt")

        async with aiohttp.ClientSession() as session:
            target_url = urljoin(self.url, "/prompt")
            
            # 直接传入 json=p，aiohttp 会自动处理编码和 content-type
            async with session.post(target_url, json=p, auth=self.auth) as resp:
                logger.info(f"{resp.status}: {resp.reason}")
                
                if resp.status == 200:
                    # 注意：resp.json() 在 aiohttp 中是一个异步等待对象
                    return await resp.json()
                else:
                    # 异步获取错误的文本响应内容（如果有的话）
                    err_text = await resp.text()
                    raise Exception(
                        f"Request failed with status code {resp.status}: {resp.reason}. Details: {err_text}"
                    )
    
    async def queue_prompt_and_wait(self, prompt: dict) -> str:
        client_id = str(uuid.uuid4())
        resp = await self.queue_prompt(prompt, client_id)
        logger.debug(resp)
        prompt_id = resp["prompt_id"]
        logger.info(f"Connecting to {self.url.format(client_id).split('@')[-1]}")
        async with websockets.connect(uri=self.url.format(client_id)) as websocket:
            while True:
                # out = ws.recv()
                out = await websocket.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message["type"] == "crystools.monitor":
                        continue
                    logger.debug(message)
                    if message["type"] == "execution_error":
                        data = message["data"]
                        if data["prompt_id"] == prompt_id:
                            raise Exception("Execution error occurred.")
                    if message["type"] == "status":
                        data = message["data"]
                        if data["status"]["exec_info"]["queue_remaining"] == 0:
                            return prompt_id
                    if message["type"] == "executing":
                        data = message["data"]
                        if data["node"] is None and data["prompt_id"] == prompt_id:
                            return prompt_id
    
    async def queue_and_wait_images(
        self, wf: WrapComfy, output_node_title: str
    ) -> dict:
        """
        Queues a prompt with a ComfyWorkflowWrapper object and waits for the images to be generated.

        Args:
            prompt (ComfyWorkflowWrapper): The ComfyWorkflowWrapper object representing the prompt.
            output_node_title (str): The title of the output node.

        Returns:
            dict: A dictionary mapping image filenames to their content.

        Raises:
            Exception: If the request fails with a non-200 status code.
        """
        prompt = wf.workflow
        prompt_id = await self.queue_prompt_and_wait(prompt)
        history = await self.get_history(prompt_id)
        image_node_id = wf.get_node_id(output_node_title)
        images = history[prompt_id]["outputs"][image_node_id]["images"]
        return {
            image["filename"]: await self.get_image(
                image["filename"], image["subfolder"], image["type"]
            )
            for image in images
        }
    

    async def get_history(self, prompt_id: str) -> dict:
        """
        Retrieves the execution history for a prompt.

        Args:
            prompt_id (str): The ID of the prompt.

        Returns:
            dict: The response JSON object.

        Raises:
            Exception: If the request fails with a non-200 status code.
        """
        logger.info(f"Posting prompt to {self.url}/prompt")

        async with aiohttp.ClientSession() as session:
            url = urljoin(self.url, f"/history/{prompt_id}")
            logger.info(f"Getting history from {url}")
            async with session.get(url, auth=self.auth) as resp:
                logger.info(f"{resp.status}: {resp.reason}")
                
                if resp.status == 200:
                    # 注意：resp.json() 在 aiohttp 中是一个异步等待对象
                    return await resp.json()
                else:
                    # 异步获取错误的文本响应内容（如果有的话）
                    err_text = await resp.text()
                    raise Exception(
                        f"Request failed with status code {resp.status}: {resp.reason}. Details: {err_text}"
                    )


    async def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """
        Retrieves an image from the Comfy API server.

        Args:
            filename (str): The filename of the image.
            subfolder (str): The subfolder of the image.
            folder_type (str): The type of the folder.

        Returns:
            bytes: The content of the image.

        Raises:
            Exception: If the request fails with a non-200 status code.
        """
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url = urljoin(self.url, f"/view?{urlencode(params)}")
        logger.info(f"Getting image from {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=self.auth) as resp:
                logger.debug(f"{resp.status}: {resp.reason}")
                if resp.status == 200:
                    return await resp.read()
                else:
                    raise Exception(
                        f"Request failed with status code {resp.status}: {resp.reason}"
                    )

    async def queue_and_wait_videos(
        self, wf: WrapComfy, output_node_title: str
    ) -> dict[str, bytes]:
        """
        提交工作流并等待视频（或 Animated GIF）生成完成，随后下载视频文件。

        Args:
            wf (WrapComfy): 工作流包装对象。
            output_node_title (str): 目标视频保存节点的标题（例如: "保存视频"）。

        Returns:
            dict[str, bytes]: 文件名映射到文件二进制内容的字典。
        """
        prompt = wf.workflow
        prompt_id = await self.queue_prompt_and_wait(prompt)
        history = await self.get_history(prompt_id)
        video_node_id = wf.get_node_id(output_node_title)
        
        node_output = history[prompt_id]["outputs"].get(video_node_id, {})
       
        print("========== ComfyUI 返回的节点原始数据 ==========")
        print(node_output)
        print("==============================================")

        # 视频保存节点的输出字段可能为 'gifs' 或 'videos'
        video_list = (
            node_output.get("images") 
            or node_output.get("gifs") 
            or node_output.get("videos") 
            or []
        )

        if not video_list:
            raise ValueError(f"节点 '{output_node_title}' (ID: {video_node_id}) 未返回任何视频数据。")

        # 注意：获取视频与获取图片的 API 端点是一致的（均通过 /view 端点）
        return {
            item["filename"]: await self.get_image(
                item["filename"], item["subfolder"], item["type"]
            )
            for item in video_list
        }


    async def download_and_save_videos(self, wf: WrapComfy, output_node_title: str, save_dir: str = "./downloads"):
        """
        提交任务并把生成的视频直接保存到本地文件夹
        """
        # 1. 获取视频的二进制数据字典 {filename: bytes}
        videos_dict = await self.queue_and_wait_videos(wf, output_node_title)
        
        # 2. 确保保存目录存在
        os.makedirs(save_dir, exist_ok=True)
        
        saved_paths = []
        # 3. 写入文件
        for filename, video_bytes in videos_dict.items():
            file_path = os.path.join(save_dir, filename)
            with open(file_path, "wb") as f:
                f.write(video_bytes)
            print(f"视频已保存至: {file_path}")
            saved_paths.append(file_path)
            
        return saved_paths