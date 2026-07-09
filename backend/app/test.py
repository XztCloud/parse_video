import os
import re
import requests
import yt_dlp

from videodl import videodl

def get_clean_kuaishou_url(url):
    """
    追踪快手链接的重定向，并清洗掉多余的分享参数，防止 yt-dlp 报错
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        # 1. 追踪重定向拿到长链接
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        final_url = response.url
        
        # 2. 如果链接里包含 short-video，用正则提取核心部分，丢弃后面所有的 ? 参数
        # 比如把 https://www.kuaishou.com/short-video/3xzuaass7k24hyk?cc=... 
        # 清洗为 https://www.kuaishou.com/short-video/3xzuaass7k24hyk
        if 'short-video' in final_url:
            match = re.search(r'(https://www\.kuaishou\.com/short-video/[A-Za-z0-9_-]+)', final_url)
            if match:
                clean_url = match.group(1)
                print(f"🔗 链接清洗成功: {clean_url}")
                return clean_url
                
        return final_url
    except Exception as e:
        print(f"⚠️ 追踪重定向失败: {e}")
        return url

# --- 你原本的方法内部修改 ---
def download_video(url):
    

    print('1')
    video_client = videodl.VideoClient(allowed_video_sources=["KuaishouVideoClient"])
    print('2')
    video_infos = video_client.parsefromurl(url)
    if len(video_infos) == 0:
        raise Exception(f'not find any video info.')


    print(f'download video title: {video_infos[0]["title"]}, save_path:{video_infos[0]["save_path"]}')
    video_client.download(video_infos)
    if not os.path.exists(video_infos[0]["save_path"]):
        
        raise Exception(f'file download failed. path not exists.')

# 测试调用
if __name__ == "__main__":
    url='https://www.kuaishou.com/short-video/3xkt69hruiq7bqw?cc=share_copylink&followRefer=151&shareMethod=TOKEN&docId=9&kpn=KUAISHOU&subBiz=BROWSE_SLIDE_PHOTO&photoId=3xkt69hruiq7bqw&shareId=19025509990666&shareToken=X-ajHUyf4xe58WBx&shareResourceType=PHOTO_OTHER&userId=3xra2cj8m8hr3gm&shareType=1&et=1_i%252F2009817759366674449_bs6502%2524s&shareMode=APP&efid=3xv8n8pky4wrj4i&originShareId=19025509990666&appType=21&shareObjectId=5248382615599762434&shareUrlOpened=0&timestamp=1783403117610&utm_source=app_share&utm_medium=app_share&utm_campaign=app_share&location=app_share'
    download_video(url)