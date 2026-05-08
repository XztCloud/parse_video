import subprocess
import os

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