
import asyncio
import json
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
        self, wf: WrapComfy, output_node_title: str, loop:asyncio.BaseEventLoop = asyncio.get_event_loop()
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
