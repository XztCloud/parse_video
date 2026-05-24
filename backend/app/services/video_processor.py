from pathlib import Path
import shutil
import subprocess
import os
from typing import List, NamedTuple, Union
from scenedetect import AdaptiveDetector, ContentDetector, FrameTimecode, TimecodeLike, open_video, SceneManager, save_images, split_video_ffmpeg
from scenedetect import split_video_ffmpeg

def has_mp4_files(folder_path: str|Path):
    # 使用 rglob 可以连同【子文件夹】一起查找；如果只想找【当前目录】，把 rglob 改为 glob
    has_mp4 = any(Path(folder_path).rglob("*.mp4"))
    return has_mp4


def get_sorted_mp4_files(folder_path: Union[str, Path]) -> List[Path]:
    clean_path = Path(folder_path)
    
    # 1. 找出所有 mp4
    # 2. 按最后修改时间（st_mtime）从新到旧排序
    # 3. 返回排好序的 Path 对象列表
    return sorted(
        clean_path.rglob("*.mp4"), 
        key=lambda p: p.stat().st_mtime, 
        reverse=True
    )


def make_dir(dir_path: str|Path):
    target_dir = Path(dir_path)
    
    if target_dir.exists():
        # 如果存在，使用 rmtree 递归删除该文件夹及其内部的所有子文件和子文件夹
        shutil.rmtree(target_dir)
        
    # 重新创建这个文件夹
    # parents=True: 如果上级目录不存在，会自动连同上级目录一起创建
    # exist_ok=True: 防御性参数，防止高并发下创建瞬间冲突报错
    target_dir.mkdir(parents=True, exist_ok=True)


# 定义一个你专属的“镜头信息”数据结构
class SceneInfo(NamedTuple):
    start: FrameTimecode
    end: FrameTimecode
    video_path: str  # 新增的路径字段
    image_path_list: list[str]

# 2. 声明你的新列表类型
extended_scene_list: list[SceneInfo] = []


class VideoProcessor:
    @staticmethod
    def extract_audio(video_path: str, output_path: str = None) -> str:
        if output_path is None:
            base = os.path.splitext(video_path)[0]
            output_path = f"{base}.wav"
        print(f'video_path:{video_path}, output_path:{output_path}')
        cmd = ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    @staticmethod
    def extract_frames(video_path: str, output_dir: str, fps: float = 1.0) -> list[str]:
        os.makedirs(output_dir, exist_ok=True)
        pattern = os.path.join(output_dir, "frame_%04d.jpg")
        cmd = ["ffmpeg", "-i", video_path, "-vf", f"fps={fps}", "-q:v", "2", "-y", pattern]
        subprocess.run(cmd, check=True, capture_output=True)
        frames = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".jpg")])
        return frames

    @staticmethod
    def get_duration(video_path: str) -> float:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    
    @staticmethod
    def split_video_into_scenes(video_path: str, output_dir: str|Path, adaptive_threshold: float=3.5, 
                                min_scene_len: TimecodeLike=25, window_width: int=5) -> list:
        # Open our video, create a scene manager, and add a detector.
        make_dir(output_dir)

        result = []
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(
            AdaptiveDetector(adaptive_threshold=adaptive_threshold, min_scene_len=min_scene_len, window_width=window_width))
        scene_manager.detect_scenes(video, show_progress=True)
        scene_list = scene_manager.get_scene_list()
        print(f'scene_list: {scene_list}')
        ret = split_video_ffmpeg(video_path, scene_list, show_progress=True, output_dir=output_dir)
        if ret != 0:
            print(f'split_video_ffmpeg failed. ret: {ret}')
            return result
        video_list = get_sorted_mp4_files(output_dir)
        print(f'split video list is {video_list}, len is {len(video_list)}')
        if len(video_list) != len(scene_list):
            print(f'error, split video len != scene len')
            return result
        
        base_dir = Path(output_dir)
        new_width = min(video.frame_size[0], 720)
        for i, scene in enumerate(scene_list):
            start_time, end_time = scene
            duration_seconds = end_time.get_seconds() - start_time.get_seconds()
            dynamic_num = min(max(2, int(duration_seconds / 2)), 5)
            out_dir = str(base_dir / f'scene_{i}/')
            
            saved_images_dict = save_images(
                scene_list=[scene],
                video=video,
                num_images=dynamic_num,
                image_extension="jpg",
                width=new_width,
                output_dir= str(base_dir / f'scene_{i}/')
            )

            all_image_paths: list[str] = [
                out_dir + '/' + img_path 
                for paths in saved_images_dict.values() 
                for img_path in paths
            ]

            scene_data = SceneInfo(start_time, end_time, video_list[i], all_image_paths)
            result.append(scene_data)
        
        return result 
    
    @staticmethod
    def extract_frames_with_scene(scene_list: list[SceneInfo], output_dir: str | Path):
        make_dir(output_dir)
