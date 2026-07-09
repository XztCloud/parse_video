import re

import yt_dlp
import os

from app.util import retry_error, logger, timeout
from ..config import settings
from videodl import videodl
from func_timeout import func_set_timeout, FunctionTimedOut

class DouyinParser:

    
        

    @staticmethod
    def download_video_yt(url: str, output_dir: str = None) -> tuple[str, str]:
        if output_dir is None:
            output_dir = settings.UPLOAD_DIR
        
        pattern = r'https?://[^\s]+'
        match = re.search(pattern, url)

        if match:
            url = match.group()
            print(f"匹配到的链接：{url}")
        else:
            print("未找到链接")
            raise ValueError("无效的链接")


        abs_output_dir = os.path.abspath(output_dir)
        os.makedirs(abs_output_dir, exist_ok=True)
        ydl_opts = {"outtmpl": os.path.join(abs_output_dir, "%(id)s.%(ext)s"), "format": "best", "quiet": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "unknown")
            filename = ydl.prepare_filename(info)
            abs_filename = os.path.abspath(filename)
            print(f'abs_filename:{abs_filename}')
            return abs_filename, title
        
    @staticmethod
    def download_video(url: str, output_dir: str = None) -> tuple[str, str]:
        go_on = False
        try:
            return DouyinParser.download_video_yt(url, output_dir)
        except Exception as e:
            logger.warning(f'download yt failed. {e}')
            go_on = True
        if go_on:
            return DouyinParser.download_video_dl(url, output_dir)
        
    @staticmethod
    @retry_error(retries=2)
    @func_set_timeout(30)
    def download_video_dl(url:str, output_dir:str = None) -> tuple[str, str]:
        try:
            video_client = videodl.VideoClient(
                allowed_video_sources=["AcFunVideoClient", "KuaishouVideoClient", "BilibiliVideoClient", "DouyinVideoClient", "YouTubeVideoClient"]
            )
            video_infos = video_client.parsefromurl(url)
            if len(video_infos) == 0:
                raise Exception(f'not find any video info.')
            title = video_infos[0]["title"]
            save_path = video_infos[0]["save_path"]
            logger.info(f'download video title: {title}, save_path:{save_path}')
            video_client.download(video_infos)
            if not os.path.exists(save_path):

                raise Exception(f'file download failed. path not exists.')
        except Exception as e:
            logger.exception('download_video_dl 发生错误')
            logger.error(f'download video failed. {e}')
            raise e
        return  save_path, title