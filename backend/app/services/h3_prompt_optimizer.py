"""H3 Ref2VA 提示词优化模块。

从 clone_script_segments 读取分镜数据，关联角色/场景参考图片，
**按分镜时长合并连续分镜**（组内总时长 < 15 秒）作为一次输入，
相同资产（同一张角色图/场景图、相同的角色状态）只输入一次，
按 H3 Full-Reference Mode 六段式规则生成提示词，返回每个分镜组的
提示词及图片对应关系。

用法：
    from app.services.h3_prompt_optimizer import optimize_script_prompts
    results = await optimize_script_prompts(script_id=55)
"""

import asyncio
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text

from app.services.llm import model

# 注意：不能在此处模块级导入 app.tasks.process_loop_manager！
# app.tasks 包 __init__ 会触发 parse_video -> clone -> clone_segment_video 链路，
# 而 clone_segment_video 又 import 本模块，形成循环导入。process_loop 改为函数内懒加载。

# 分镜合并阈值（秒）：连续分镜组总时长小于该值才合并
GROUP_MAX_DURATION = 15.0

# 每组参考图片数量上限：加入下一分镜后参考图会超过该值时，立即收组交给 LLM，
# 不再继续合并（视频模型参考图过多效果差）。
GROUP_MAX_IMAGES = 5

# LLM 调用兜底：单次超时（秒）与最大重试次数。
# 实测火山引擎 Ark 接口对大 prompt 的生成偶发挂起（连接建立后服务端长时间不返回），
# 且生成耗时波动大（1~5 分钟不等），超时后重试即可恢复。
LLM_CALL_TIMEOUT = 300.0
LLM_MAX_RETRIES = 3

# H3 Ref2VA 六段式输出规则（参考 skill/h3-prompt-writing 的 ref-en.txt / base-en.txt）
H3_SYSTEM_PROMPT = """
你是一位精通 MiniMax H3 视频生成提示词的工程师。请按 H3 Full-Reference Mode（Ref2VA）的
六段式格式，为一个分镜组（多个连续镜头组成的一段视频）生成一段 H3 提示词。

输入 JSON 说明：
- duration_budget: 该分镜组的目标总时长（秒），提示词中的时间轴必须与其吻合；外部音轨会按此
  时长驱动口型。
- shots: 按时间顺序排列的镜头列表。每镜包含：
    start_time / end_time（组内相对时间，第一镜从 0 开始）、scene_name（场景名）、
    shot_type（景别）、shot_description（镜头描述）、dialogue（台词）、
    role_view_info（该镜中可见角色及其位置/动作/表情）。
  dialogue 每项含 role_name / lines / audio_style / lines_flag / start_offset / end_offset：
    - lines_flag: head/body/tail/all。一句话跨越多个分镜时中间分镜必用 body；
      lines 中始终给出完整句文本（head=起始段、body=中间段、tail=收尾段、all=独立句）。
    - start_offset/end_offset: 台词在当前分镜时间线上的相对起止（秒）。
- refer_image: 参考图片清单。同一资产（同一张角色图/场景图）在整个分镜组中只出现一次。

输出必须严格按以下六个 section 的顺序组织，section 名保持英文，正文用中文描述
（对话 <d> 内的台词保留原语言）：

1. subject_definitions:
   用 <Picture N> 和 <Subject N> 定义参考内容。<Subject N> 表示可复用的人物/场景，
   <Picture N> 是参考图片。例如：
   "<Subject 1> 是 <Picture 1> 中的人物，保持其面部特征与服饰。"
   对需要在画面中露出并说话的角色，在 subject_definitions 中为其语音定义一个 <Audio N>
   音色引用并绑定到说话人，写法："<Subject 2> (S2) 的语音音色与语气参考，来自 <Audio 2>。"
   画外说话人没有对应可见角色图时，不分配 <Picture N>，但仍可给出 <Audio N> 音色引用。
2. summary:
   用一句英文概括视频内容与参考关系，带 [reference generation] 前缀；存在语音驱动时前缀写
   [reference generation + audio reference]。
3. retention_analysis:
   逐条说明每个 <Subject N>/<Picture N>/<Audio N> 的保留方式（fully_preserved /
   partially_preserved / attribute_transfer / weak_reference；音频通常为 reference——
   仅参考音色语气，不复制原信号）。
4. detailed_description:
   按时间顺序逐镜描述整组分镜：构图、主体、环境、动作、镜头运动、声音、
   以及参考内容出现的位置。第一镜标 [Shot 1]（组内 00:00 开始），后续镜头用
   [Shot N] At MM:SS.mmm 标注组内相对切点。对话用 <d>[Chinese] ...</d> 标记，
   说话人按出现顺序分配稳定编号 (S1)、(S2) 并在全片复用。
5. overall_soundscape:
   概括整体环境音与物理音效；只写环境/动作产生的非语言声，不重复对白。
6. non_diegetic_music:
   描述仅观众可闻的背景音乐；无则写 N/A。

音频与台词规则：
- 每条台词都要写明说话人动作/表情 + 口型与音轨同步，例如 "His mouth moves in natural sync
  with the line"。音频由外部音轨驱动，提示词必须让口型与台词窗口对齐。
- 跨镜长台词（lines_flag 为 head/body/tail）：说明完整句延续当前镜，在切入切出的两贴近
  写上 <scenetrans> 并注明音频无缝跨镜延续（例如 continues seamlessly across the cut），
  不作句子的重述或重启；全片复用同一说话人编号 (Sx)。
- 画外音：说话人未出现在 shots 的 role_view_info 中、或 visibility 非 visible 的台词，
  用 "says in an off-screen voiceover: <d>...</d> while his/her lips remain completely closed"。
- 每镜内台词窗口必须与输入 start_offset/end_offset 一致；切点时间（[Shot N] At MM:SS.mmm）
  与 duration_budget 吻合。

其他规则：
- 每个 <Picture N> / <Audio N> 必须在 subject_definitions 中定义，且全程标签一致；同一资产在
  分镜组内多次出现时保持同一编号，不要新增定义。
- 只描述输入 JSON 中提供的角色与场景，不编造不在场的人物。
- 必须完整覆盖输入中的所有镜头与台词，一个分镜都不能遗漏；镜头顺序与
  相对时间按输入 JSON 为准。
"""


def _seg_duration(seg: dict) -> float:
    """单个分镜时长（秒），缺失时间戳时返回 0。"""
    return max(0.0, (seg.get("end_time") or 0.0) - (seg.get("start_time") or 0.0))


def _segment_picture_ids(
    seg: dict,
    scene_images: dict[str, dict],
    role_images: dict[str, dict],
    use_scene_image: bool,
) -> set[tuple[str, int]]:
    """单个分镜会引用的参考图片 (category, id) 集合。

    与 _build_group_input 的分配规则保持一致：
    - 场景图：仅当 use_scene_image=True 且 scene_name 在场景图中
    - 角色图：仅可见角色（visibility == "visible"）且 role_name 在角色图中
    """
    ids: set[tuple[str, int]] = set()
    if use_scene_image:
        scene_name = seg.get("scene_name")
        if scene_name and scene_name in scene_images:
            ids.add(("scene", scene_images[scene_name]["id"]))
    for v in (seg.get("role_view_info") or []):
        if not isinstance(v, dict) or v.get("visibility") != "visible":
            continue
        role_name = v.get("role_name")
        if role_name and role_name in role_images:
            ids.add(("role", role_images[role_name]["id"]))
    return ids


def _group_segments(
    segments: list[dict], max_duration: float = GROUP_MAX_DURATION
) -> list[list[dict]]:
    """按分镜时长合并连续分镜：组内总时长 < max_duration。

    顺序遍历（调用方保证按 start_time 升序）。累积当前组时长，若加入下一分镜后
    总时长 >= max_duration，则关闭当前组并新开一组。单个分镜时长超过阈值时
    独立成组。
    """
    groups: list[list[dict]] = []
    current: list[dict] = []
    current_dur = 0.0
    for seg in segments:
        d = _seg_duration(seg)
        if current and current_dur + d >= max_duration:
            groups.append(current)
            current = []
            current_dur = 0.0
        current.append(seg)
        current_dur += d
    if current:
        groups.append(current)
    return groups


def _group_segments_with_images(
    segments: list[dict],
    scene_images: dict[str, dict],
    role_images: dict[str, dict],
    use_scene_image: bool = False,
    max_duration: float = GROUP_MAX_DURATION,
    max_images: int = GROUP_MAX_IMAGES,
) -> list[list[dict]]:
    """按分镜时长 + 参考图片数量上限合并连续分镜。

    组内总时长 < max_duration，且组内参考图片数 <= max_images（视频模型参考图
    过多效果差）。当加入下一分镜会使总时长 >= max_duration **或** 图片数
    > max_images 时，立即关闭当前组并交给 LLM，不再合并。
    单个分镜自身超过任一上限时独立成组（无法再拆分）。
    """
    pic_ids = [
        _segment_picture_ids(s, scene_images, role_images, use_scene_image)
        for s in segments
    ]
    groups: list[list[dict]] = []
    current: list[dict] = []
    current_dur = 0.0
    current_pics: set[tuple[str, int]] = set()
    for seg, pids in zip(segments, pic_ids):
        d = _seg_duration(seg)
        if current and (
            current_dur + d >= max_duration or len(current_pics | pids) > max_images
        ):
            groups.append(current)
            current, current_dur, current_pics = [], 0.0, set()
        current.append(seg)
        current_dur += d
        current_pics |= pids
    if current:
        groups.append(current)
    return groups


def _build_group_input(
    group: list[dict],
    scene_images: dict[str, dict],
    role_images: dict[str, dict],
    use_scene_image: bool = False,
) -> tuple[dict, list[dict]]:
    """组装一个分镜组（多个连续分镜）的待优化 JSON，并返回图片映射。

    合并规则：
    - shots 按时间顺序展开，start_time/end_time 换算为组内相对时间（第一镜从 0 开始）。
    - 参考图片按 (category, id) 去重：同一张场景图/角色图在组内多处出现时，
      只分配一次 <Picture N> 并只在 refer_image 中列一次。
    - use_scene_image=False（默认）时不将场景图作为参考输入：不分配 <Picture N>、
      不出现在 refer_image 与 image_map；场景名仍保留在 shots 中供 LLM 文字理解。
    - role_view_info 按 (role_name, position, action, emotion) 全组去重：
      与前面镜头完全相同的角色状态不重复输入。
    - dialogue 为脚本内容，全部保留（不可丢失台词）。

    返回 (input_json, image_map)：
    - input_json 含 duration_budget / shots / refer_image
    - image_map 为 [{"Picture N": "image_path"}]，直接给出该参考图片的文件路径
    """
    group_start = group[0].get("start_time") or 0.0

    # 参考图片编号映射：label -> {"category","id","name"}
    picture_index: dict[str, dict] = {}
    next_num = 1

    def _assign_picture(obj: dict) -> str:
        nonlocal next_num
        # 同一张图（同 category + id）复用同一编号，不重复定义
        for label, info in picture_index.items():
            if info["id"] == obj["id"] and info["category"] == obj["category"]:
                return label
        label = f"Picture {next_num}"
        next_num += 1
        picture_index[label] = obj
        return label

    # 全组角色状态去重集合
    seen_role_states: set[tuple] = set()

    shots: list[dict] = []
    for seg in group:
        abs_start = seg.get("start_time") or 0.0
        abs_end = seg.get("end_time") or abs_start
        rel_start = round(abs_start - group_start, 3)
        rel_end = round(abs_end - group_start, 3)

        # 该镜可见角色（过滤 visibility == "visible"）
        visible_roles = [
            v for v in (seg.get("role_view_info") or [])
            if isinstance(v, dict) and v.get("visibility") == "visible"
        ]

        # 角色状态精简 + 组内去重（完全相同的不重复输入）
        role_view: list[dict] = []
        for v in visible_roles:
            if not v.get("role_name"):
                continue
            key = (v.get("role_name"), v.get("position"), v.get("action"), v.get("emotion"))
            if key in seen_role_states:
                continue
            seen_role_states.add(key)
            role_view.append({
                "role_name": v.get("role_name"),
                "position": v.get("position"),
                "action": v.get("action"),
                "emotion": v.get("emotion"),
            })

        # dialogue 精简：role_name / lines / audio_style + 台词窗口（脚本内容，全部保留）。
        # lines_flag（head/body/tail/all）与 start/end_offset 供 LLM 对齐跨镜长台词与音频切片。
        dialogue = [
            {
                "role_name": d.get("role_name"),
                "lines": d.get("lines"),
                "audio_style": d.get("audio_style"),
                "lines_flag": d.get("lines_flag"),
                "start_offset": d.get("start_offset"),
                "end_offset": d.get("end_offset"),
            }
            for d in (seg.get("dialogue") or [])
            if isinstance(d, dict) and d.get("role_name")
        ]

        shots.append({
            "start_time": rel_start,
            "end_time": rel_end,
            "scene_name": seg.get("scene_name") or "",
            "shot_type": seg.get("shot_type") or "",
            "shot_description": seg.get("shot_description") or "",
            "dialogue": dialogue,
            "role_view_info": role_view,
        })

    # 参考图片：按 (category, id) 去重，同一资产只列一次
    refer_lines: list[str] = []
    for shot in shots:
        scene_name = shot.get("scene_name")
        if use_scene_image and scene_name and scene_name in scene_images:
            si = scene_images[scene_name]
            if not any(
                info["category"] == "scene" and info["id"] == si["id"]
                for info in picture_index.values()
            ):
                label = _assign_picture({
                    "category": "scene", "id": si["id"], "name": scene_name,
                    "path": si.get("path", ""),
                })
                refer_lines.append(f"场景参考 <{label}>（{scene_name}）")
        for v in shot.get("role_view_info") or []:
            role_name = v.get("role_name")
            if role_name and role_name in role_images:
                ri = role_images[role_name]
                if not any(
                    info["category"] == "role" and info["id"] == ri["id"]
                    for info in picture_index.values()
                ):
                    label = _assign_picture({
                        "category": "role", "id": ri["id"], "name": role_name,
                        "path": ri.get("path", ""),
                    })
                    refer_lines.append(f"角色参考 <{label}>（{role_name}）")

    # 无任何可见角色参考的分镜组（纯场景/产品展示/空镜等）：
    # 回落引用该组场景的场景图作为唯一参考，否则后续视频生成会因没有参考图报错。
    if not refer_lines:
        added_scenes: set[str] = set()
        for shot in shots:
            scene_name = shot.get("scene_name")
            if not scene_name or scene_name in added_scenes or scene_name not in scene_images:
                continue
            si = scene_images[scene_name]
            label = _assign_picture({
                "category": "scene", "id": si["id"], "name": scene_name,
                "path": si.get("path", ""),
            })
            refer_lines.append(f"场景参考 <{label}>（{scene_name}）")
            added_scenes.add(scene_name)
            if len(refer_lines) >= 5:
                break

    duration_budget = round(sum(_seg_duration(s) for s in group), 3)

    input_json: dict = {
        "duration_budget": duration_budget,
        "shots": shots,
    }
    if refer_lines:
        input_json["refer_image"] = "；".join(refer_lines)

    image_map = [
        {label: info.get("path", "")}
        for label, info in picture_index.items()
    ]
    return input_json, image_map


async def _generate_h3_prompt(input_json: dict) -> str:
    """调用 LLM 生成 H3 六段式提示词（带超时与重试兜底）。"""
    payload = json.dumps(input_json, ensure_ascii=False, indent=2)
    messages = [
        SystemMessage(H3_SYSTEM_PROMPT),
        HumanMessage(
            "请根据以下分镜组 JSON，生成 H3 Ref2VA 六段式提示词：\n"
            f"```json\n{payload}\n```"
        ),
    ]
    last_err: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            resp = await asyncio.wait_for(
                model.ainvoke(
                    messages,
                    config={"configurable": {"temperature": 0.4}},
                ),
                timeout=LLM_CALL_TIMEOUT,
            )
            return resp.content if isinstance(resp.content, str) else str(resp.content)
        except asyncio.TimeoutError as e:
            last_err = e
            print(f"[h3] LLM 调用超时（{LLM_CALL_TIMEOUT:.0f}s），"
                  f"第 {attempt}/{LLM_MAX_RETRIES} 次重试...", flush=True)
        except Exception as e:  # noqa: BLE001 - 网络/接口异常统一重试
            last_err = e
            print(f"[h3] LLM 调用异常: {type(e).__name__}: {e}，"
                  f"第 {attempt}/{LLM_MAX_RETRIES} 次重试...", flush=True)
    raise RuntimeError(f"H3 提示词生成失败（重试 {LLM_MAX_RETRIES} 次）：{last_err}")


def _select_groups(
    segments: list[dict],
    scene_images: dict[str, dict],
    role_images: dict[str, dict],
    use_scene_image: bool,
    merge_segments: bool,
) -> list[list[dict]]:
    """按 merge_segments 选择分组策略。

    - True: 按时长(<15s) + 参考图片数(<=5) 合并连续分镜
    - False: 不合并，每个分镜单独成组（返回 [[seg], [seg], ...]）
    """
    if merge_segments:
        return _group_segments_with_images(
            segments, scene_images, role_images, use_scene_image=use_scene_image
        )
    return [[s] for s in segments]


async def optimize_script_prompts(
    script_id: int,
    use_scene_image: bool = False,
    merge_segments: bool = False,
    on_group: Any | None = None,
    max_groups: int | None = None,
) -> list[dict]:
    print(f'use_scene_image： {use_scene_image}，merge_segments: {merge_segments}')
    """为指定复刻脚本的每个分镜组生成 H3 提示词。

    流程：读取分镜（按 start_time 升序）→ 分组（合并与否见 merge_segments）→
    每个分镜组组装输入（相同资产去重）→ LLM 生成一段 H3 六段式提示词。

    merge_segments: 是否合并连续分镜。True 时按 时长(<15s) + 参考图片数(<=5)
    合并连续分镜（视频模型参考图过多效果差，且本地显存带不动太多参考图）；
    False（默认）时不合并，每个分镜单独生成一段提示词。

    use_scene_image: 是否将场景图作为参考输入。False（默认）时场景图不参与
    <Picture N> 参考分配（refer_image / image_map 不含场景），场景名仍以文字
    形式保留在 shots 中；True 时才把场景图作为参考。

    on_group: 可选回调，每组生成完成后立即调用（参数为该组 result dict），
    可用于边生成边落盘，避免中途失败丢失已完成结果。

    max_groups: 最多只生成前几个分镜组的提示词（调 LLM 前切组，用于分批/按需生成），
    None 表示全部。

    返回 list，每个元素对应一个分镜组：
    {
        "group_index": int,                 # 第几个分镜组（从 1 开始）
        "segment_ids": [int, ...],          # 组内分镜 id（按时间顺序）
        "start_time": float,                # 组起始时间（视频时间轴，秒）
        "end_time": float,                  # 组结束时间（视频时间轴，秒）
        "duration": float,                  # 组总时长（秒，< 15）
        "prompt": str,                      # H3 六段式提示词
        "image_map": [{"Picture N": "image_path"}]
    }
    """
    # 懒加载：避免模块级导入触发 app.tasks 包循环导入
    from app.tasks.process_loop_manager import process_loop

    db = process_loop.AsyncSessionLocal()
    try:
        # 1. 查询分镜（按时间排序）
        seg_res = await db.execute(
            text(
                "SELECT id, start_time, end_time, scene_name, shot_type, shot_description, "
                "dialogue, role_view_info "
                "FROM clone_script_segments WHERE script_id = :sid ORDER BY start_time"
            ).bindparams(sid=script_id)
        )
        segments = [dict(row._mapping) for row in seg_res.fetchall()]

        # 2. 查询场景图（script_id + scene_name，含 path）
        scene_res = await db.execute(
            text(
                "SELECT id, scene_name, path FROM clone_scene_images "
                "WHERE script_id = :sid AND status = 'SUCCESS'"
            ).bindparams(sid=script_id)
        )
        scene_images = {row.scene_name: {"id": row.id, "scene_name": row.scene_name, "path": row.path}
                        for row in scene_res.fetchall()}

        # 3. 查询角色图（script_id + role_name，含 path）
        role_res = await db.execute(
            text(
                "SELECT id, role_name, path FROM clone_role_images "
                "WHERE script_id = :sid AND status = 'SUCCESS'"
            ).bindparams(sid=script_id)
        )
        role_images = {row.role_name: {"id": row.id, "role_name": row.role_name, "path": row.path}
                       for row in role_res.fetchall()}
    finally:
        await db.close()

    if not segments:
        return []

    groups = _select_groups(
        segments, scene_images, role_images,
        use_scene_image=use_scene_image, merge_segments=merge_segments,
    )
    # 只处理前 N 组分镜（在调 LLM 之前切，避免为后续分镜浪费 token）
    if max_groups is not None and max_groups > 0:
        groups = groups[:max_groups]
    mode = "合并" if merge_segments else "不合并（每分镜独立）"
    print(f"[h3] script_id={script_id} 分镜 {len(segments)} 个 → {mode} → {len(groups)} 组 "
          f"(时长<{GROUP_MAX_DURATION}s 且 参考图<={GROUP_MAX_IMAGES}张)", flush=True)

    results: list[dict] = []
    for idx, group in enumerate(groups, start=1):
        group_start = group[0].get("start_time") or 0.0
        group_end = group[-1].get("end_time") or group_start
        input_json, image_map = _build_group_input(
            group, scene_images, role_images, use_scene_image=use_scene_image
        )
        print(f"[h3] 组 {idx}: segment_ids={[s['id'] for s in group]} "
              f"时长={round(group_end - group_start, 3)}s 参考图={len(image_map)}张 开始调 LLM...", flush=True)
        prompt = await _generate_h3_prompt(input_json)
        print(f"[h3] 组 {idx}: LLM 完成，提示词 {len(prompt)} 字符", flush=True)
        result = {
            "group_index": idx,
            "segment_ids": [s["id"] for s in group],
            "start_time": group_start,
            "end_time": group_end,
            "duration": round(group_end - group_start, 3),
            "prompt": prompt,
            "image_map": image_map,
        }
        results.append(result)
        if on_group is not None:
            on_group(result)
    return results


if __name__ == "__main__":
    import asyncio
    from app.tasks.process_loop_manager import process_loop

    async def _main():
        process_loop.init_process()
        try:
            results = await optimize_script_prompts(55)
            for r in results:
                print(f"\n{'='*60}\ngroup_index: {r['group_index']}")
                print(f"segment_ids: {r['segment_ids']}")
                print(f"time: {r['start_time']} ~ {r['end_time']} (duration={r['duration']}s)")
                print(f"image_map: {json.dumps(r['image_map'], ensure_ascii=False)}")
                print(f"prompt:\n{r['prompt'][:800]}")
        finally:
            process_loop.shutdown()

    asyncio.run(_main())
