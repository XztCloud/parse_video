import re

import yt_dlp
import os
from ..config import settings

class DouyinParser:
    @staticmethod
    def download_video(url: str, output_dir: str = None) -> tuple[str, str]:
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