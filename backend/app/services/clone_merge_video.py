import asyncio
import inspect
import os
import subprocess
import tempfile

from celery.utils.log import get_task_logger
import ffmpeg
from sqlalchemy import delete, select

from app.config import settings
from app.models.script import CloneScript, CloneScriptSegment, CloneSegmentVideo, CloneVideo, CloneStatus
from app.tasks.process_loop_manager import process_loop
from app.util import make_dir, get_video_duration_ffprobe

logger = get_task_logger(__name__)


def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")


def _ffprobe_resolution(video_path: str) -> tuple[int, int]:
    """用 ffprobe 读取视频宽高，失败时返回 (0, 0)。"""
    try:
        probe = ffmpeg.probe(video_path)
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                return int(stream.get("width", 0)), int(stream.get("height", 0))
    except Exception:
        logger.exception(f"ffprobe 读取分辨率失败: {video_path}")
    return 0, 0


def merge_videos_with_ffmpeg(video_paths: list[str], output_path: str) -> None:
    """将多个 MP4 按顺序合并为一个视频。

    分镜视频可能编码参数不一致，这里统一重编码：
    - 以第一个分镜的宽高为基准，其余分镜 scale 对齐
    - 音频统一 aac/48000
    使用 concat demuxer + concat list 文件，避免超长命令行。
    """
    if not video_paths:
        raise ValueError("合并视频列表为空")

    base_width, base_height = _ffprobe_resolution(video_paths[0])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        concat_list_path = f.name
        for idx, path in enumerate(video_paths):
            abs_path = os.path.abspath(path)
            if not os.path.isfile(abs_path):
                raise FileNotFoundError(f"分镜视频不存在: {abs_path}")
            f.write(f"file '{abs_path}'\n")
        f.flush()

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-vf", f"scale={base_width}:{base_height}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000",
            "-movflags", "+faststart",
            output_path,
        ]
        logger.info(f"执行 ffmpeg 合并: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-3000:]
            raise RuntimeError(f"ffmpeg 合并失败:\n{stderr_tail}")
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


async def merge_segment_videos(clone_script_id: int) -> None:
    """合并复刻视频的全部分镜 MP4 为成片，写入 CloneVideo 表并推进状态到 DONE。"""
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    clone_script = None
    try:
        res = await db.execute(select(CloneScript).where(CloneScript.id == clone_script_id))
        clone_script = res.scalar_one_or_none()
        if not clone_script:
            raise ValueError(f'not find clone_script: {clone_script_id}')

        # 关联分镜，按 start_time 升序取分镜视频
        res = await db.execute(
            select(CloneSegmentVideo, CloneScriptSegment.start_time)
            .join(CloneScriptSegment, CloneSegmentVideo.clone_script_sgement_id == CloneScriptSegment.id)
            .where(CloneScriptSegment.script_id == clone_script_id)
            .order_by(CloneScriptSegment.start_time)
        )
        rows = res.all()
        segment_videos = [video for video, _ in rows]
        if not segment_videos:
            raise ValueError(f'clone_script {clone_script_id} 没有分镜视频可合并')

        video_paths = [v.path for v in segment_videos]
        base_width, base_height = segment_videos[0].width, segment_videos[0].height

        save_dir = settings.UPLOAD_DIR + '/clone_' + str(clone_script_id)
        make_dir(save_dir, re_create=False)
        output_path = os.path.join(save_dir, 'merged.mp4')
        abs_output_path = os.path.abspath(output_path)

        merge_videos_with_ffmpeg(video_paths, abs_output_path)

        duration = get_video_duration_ffprobe(abs_output_path)

        # 支持重跑：表有 video_id 唯一约束，先删旧记录
        await db.execute(delete(CloneVideo).where(CloneVideo.video_id == clone_script_id))

        merged_video = CloneVideo(
            video_id=clone_script_id,
            file_path=output_path,
            duration=duration,
            width=base_width,
            height=base_height,
            rate=24,
            version=0,
        )
        db.add(merged_video)

        clone_script.clone_progress = 100
        clone_script.clone_status = CloneStatus.DONE
        await db.commit()
        logger.info(f'合并视频完成: {output_path}, duration={duration}, status={clone_script.clone_status.value}')
    except Exception as e:
        logger.exception('merge_segment_videos 发生错误')
        await db.rollback()
        if clone_script:
            clone_script.clone_error_message = '合并分镜视频时发生错误'
            clone_script.clone_status = CloneStatus.FAILED
            await db.commit()
        raise
    finally:
        await db.close()


if __name__ == '__main__':
    process_loop.init_process()
    process_loop.run(merge_segment_videos(54))
    process_loop.shutdown()
