"""临时验证脚本：clone_script_id=55，用 minimax_h3 只生成前 3 个分镜视频。

用法：
    cd backend && source ../.venv/bin/activate && python tmp_test_minimax_video.py
输出重定向到日志文件便于后台监控。
"""
import sys
import time

# 先按 celery worker 的加载顺序导入 app.tasks.parse_video，
# 避免直接 import clone_segment_video 时触发 app.tasks/__init__ 循环导入。
import app.tasks.parse_video  # noqa: F401

from app.services.clone_segment_video import generate_segments_video_minimax_h3
from app.tasks.process_loop_manager import process_loop

SCRIPT_ID = 55
MAX_GROUPS = 3


def main():
    t0 = time.time()
    process_loop.init_process()
    print(f"[{time.strftime('%H:%M:%S')}] init done, generating first {MAX_GROUPS} segment videos "
          f"(script_id={SCRIPT_ID})...", flush=True)
    try:
        process_loop.run(generate_segments_video_minimax_h3(SCRIPT_ID, max_groups=MAX_GROUPS))
        print(f"[{time.strftime('%H:%M:%S')}] DONE, total {time.time() - t0:.1f}s", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] FAILED: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
    finally:
        try:
            process_loop.shutdown()
        except Exception as e:  # 清理异常不影响结果
            print(f"[{time.strftime('%H:%M:%S')}] shutdown warn: {e}", flush=True)


if __name__ == "__main__":
    main()