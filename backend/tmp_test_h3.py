"""H3 分镜组提示词测试（script_id=55）。

用法（backend 目录下）：
    source ../.venv/bin/activate && python tmp_test_h3.py

输出：
- 控制台打印每个分镜组的合并信息与生成的 H3 提示词
- 结果同时保存为 JSON：../docs/h3_results_script55.json
"""

import asyncio
import json
import os
import time

from app.services.h3_prompt_optimizer import optimize_script_prompts
from app.tasks.process_loop_manager import process_loop

SCRIPT_ID = 55
# 是否合并连续分镜：True=按时长/图片数合并（每组一段提示词）；
# False=不合并，每个分镜独立一段提示词。默认 False。
MERGE_SEGMENTS = True
OUT_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "h3_results_script55.json"
))

# 已完成的组（边生成边落盘，中途失败不丢结果）
done_groups: list[dict] = []


def save_progress():
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"script_id": SCRIPT_ID, "groups": done_groups}, f,
                  ensure_ascii=False, indent=2)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def main():
    t_start = time.time()
    process_loop.init_process()
    log("process_loop 初始化完成，开始生成提示词（共 3 组）")
    try:
        def on_group(result: dict):
            done_groups.append(result)
            save_progress()
            print(f"\n----- 组 {result['group_index']} 提示词（segment_ids={result['segment_ids']} "
                  f"时长={result['duration']}s）-----", flush=True)
            print(result["prompt"], flush=True)
            print("-----", flush=True)

        results = await optimize_script_prompts(
            SCRIPT_ID, merge_segments=MERGE_SEGMENTS, on_group=on_group
        )

        print(f"\n===== script_id={SCRIPT_ID} 共 {len(results)} 个分镜组 =====")
        for r in results:
            print(f"\n{'=' * 70}")
            print(f"组 {r['group_index']} | segment_ids={r['segment_ids']}")
            print(f"时间 {r['start_time']}s ~ {r['end_time']}s | 时长 {r['duration']}s")
            print(f"image_map: {json.dumps(r['image_map'], ensure_ascii=False)}")
            print("-" * 70)
            print(r["prompt"])
        log(f"结果已保存: {OUT_PATH}，总耗时 {time.time() - t_start:.1f}s")
    finally:
        process_loop.shutdown()


asyncio.run(main())
