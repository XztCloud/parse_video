import asyncio
import inspect
import os
import tempfile

from celery.utils.log import get_task_logger
import ffmpeg
from sqlalchemy import delete, select

from app.config import settings
from app.models.script import CloneScript, CloneScriptSegment, CloneSegmentVideo, CloneVideo, CloneVoice, GenerateFlowStatus
from app.tasks.process_loop_manager import process_loop
from app.util import MERGE_VIDEO_BEGIN_PROGRESS, MERGE_VIDEO_COMPLETE_PROGRESS, get_md5, get_video_duration_ffprobe, make_dir, run_ffmpeg

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
        run_ffmpeg(cmd, "ffmpeg 合并失败")
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


def _line_visible(dialogue_item: dict, segment: dict) -> bool:
    """与 clone_segment_video 的旁白判定保持一致：角色不在场（invisible）或命中
    旁白词组视为画外音。跨句修复只处理口型台词（旁白本来就在参考轨里连续）。"""
    from app.services.clone_segment_video import _is_narration_line
    return not _is_narration_line(dialogue_item, segment)


def _audio_file_duration(path: str) -> float | None:
    """读取音频文件真实时长（本地存在才读）。"""
    if path and os.path.isfile(path):
        try:
            d = get_video_duration_ffprobe(path)
            if d and d > 0:
                return float(d)
        except Exception:
            logger.exception(f'ffprobe 读取音频时长失败: {path}')
    return None


def find_multi_shot_sentences(
    segments: list[dict],
    voice_durations: dict,
) -> list[dict]:
    """找出「一句话贯穿多个分镜」的口型句子，供合并后用整句原始音频铺回。

    Args:
        segments: 全部按 start_time 升序的分镜 dict（含 dialogue / role_view_info）
        voice_durations: (role_name, voice_type, text_md5) -> 估值时长（兜底用）

    Returns:
        [{path, duration, merged_start, cover_len}] —— path=原始完整句音频；duration=文件真实时长
        （读不到则用估值）；merged_start=句子首次口型行所在分镜表绝对起点；
        cover_len=句子在成片中应铺满的时长（跨镜区间终点 - 起点），源句短于它时拉伸补足。
    """
    info: dict[str, dict] = {}   # audio_path -> {seg_ids, start, cover_end, est_dur}
    for seg in segments:
        for item in seg.get('dialogue') or []:
            path = item.get('audio_path')
            if not path or not _line_visible(item, seg):
                continue
            md5 = get_md5(item.get('lines') or '')
            est = voice_durations.get((item.get('role_name'), item.get('audio_style'), md5))
            if est is None or est <= 0:
                continue
            rec = info.setdefault(path, {
                "seg_ids": set(), "start": None, "cover_end": 0.0, "est_dur": est,
            })
            rec["seg_ids"].add(seg.get("id"))
            rec["cover_end"] = max(rec["cover_end"], seg.get("end_time") or 0.0)
            if rec["start"] is None:
                rec["start"] = (seg.get('start_time') or 0.0) + (item.get('start_offset') or 0.0)
            rec["est_dur"] = max(rec["est_dur"], est)

    results = []
    for path, rec in info.items():
        if len(rec["seg_ids"]) < 2:
            continue  # 仅在单个分镜内出现：H3 一次生成完整，无跨镜接缝，无需替换
        duration = _audio_file_duration(path) or rec["est_dur"]
        results.append({
            "path": path,
            "duration": round(duration, 3),
            "merged_start": round(rec["start"], 3),
            "cover_len": round(max(0.0, rec["cover_end"] - rec["start"]), 3),
        })
    return results


def _atempo_chain(ratio: float) -> list[str]:
    """把变速比拆成多个 atempo（单个 atempo 限 0.5~2.0），返回 filter 片段列表。"""
    factors: list[float] = []
    r = ratio
    # 防除零/无限
    r = min(max(r, 0.01), 100.0)
    while r > 2.0:
        factors.append(2.0)
        r /= 2.0
    while r < 0.5:
        factors.append(0.5)
        r /= 0.5
    factors.append(r)
    return [f"atempo={f:.6f}" for f in factors]


def repair_cross_group_audio(
    merged_path: str,
    sentences: list[dict],
    output_path: str,
) -> str:
    """把跨镜句的完整源音频**替换**到合并成片对应时间区间，消除句内/跨镜不连贯。

    实现：先把每个句子的覆盖区间 [start, start+target] 内的**原音轨静音**，
    再把源完整句音频铺回。源句时长短于其跨镜覆盖时长时，用 atempo 拉伸铺满
    （保调变速，避免句尾留白停顿）。amix normalize=0 保音量不衰减。
    注意是「替换」而非叠加——否则原轨里的 H3 重建句尾会与源句叠成双份。

    Args:
        merged_path: 合并后的成片 mp4
        sentences: [{path, duration, merged_start, cover_len}] —— merged_start 已是**实际成片时间**
        output_path: 修复后输出路径

    Returns:
        output_path
    """
    if not sentences:
        import shutil
        shutil.copyfile(merged_path, output_path)
        return output_path

    merged_dur = get_video_duration_ffprobe(merged_path) or 0.0
    cmd = ["ffmpeg", "-y", "-i", merged_path]
    for sent in sentences:
        cmd += ["-i", sent["path"]]

    # 每句目标铺放时长：跨镜覆盖区间，但不越过成片结尾
    targets = []
    for sent in sentences:
        target = min(sent.get("cover_len") or sent["duration"], max(0.0, merged_dur - sent["merged_start"]))
        targets.append(max(target, 0.1))

    # 1) 原音轨：在每句覆盖区间 [start, start+tgt] 内静音（volume=0 + enable 时间窗口）。
    # tgt=该句跨镜覆盖终点（含其句尾镜整段，H3 重建的衔接垫残余已在内），不额外延展，
    # 避免误删紧随其后的下一句。
    enable_conds = "+".join(
        f"between(t,{sent['merged_start']:.3f},{sent['merged_start'] + tgt:.3f})"
        for sent, tgt in zip(sentences, targets)
    )
    filter_parts = [
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"volume=0:enable='{enable_conds}'[amute]"
    ]
    # 2) 各源句：必要时 atempo 拉伸到目标时长 → adelay 到其起点
    # 注意 ffmpeg atempo>1 是加速、<1 才是放慢，因此 tempo = 源时长/目标时长。
    for i, (sent, tgt) in enumerate(zip(sentences, targets), start=1):
        tempo = sent["duration"] / tgt if tgt > 0 else 1.0
        stretch = ",".join(_atempo_chain(tempo)) if abs(tempo - 1.0) > 0.01 else ""
        pos_ms = int(max(0.0, sent["merged_start"]) * 1000)
        chain = f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo"
        if stretch:
            chain += f",{stretch}"
            logger.info(f"  句 {os.path.basename(sent['path'])} 拉伸 {sent['duration']:.2f}s→{tgt:.2f}s (tempo={tempo:.3f}) @{sent['merged_start']:.2f}s")
        chain += f",adelay=delays={pos_ms}:all=1[na{i}]"
        filter_parts.append(chain)
    mix_inputs = "".join(f"[na{i}]" for i in range(1, len(sentences) + 1))
    filter_parts.append(
        f"[amute]{mix_inputs}amix=inputs={len(sentences) + 1}:duration=first:dropout_transition=0:normalize=0[aout]"
    )
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    logger.info(f"执行跨句音频修复 ffmpeg: {' '.join(cmd)}")
    run_ffmpeg(cmd, "跨句音频修复失败")
    return output_path


def seg_table_start(segments: list[dict], member_ids: set[int]) -> float:
    """一组分镜在分镜表时间轴上的起点（组首成员的 start_time）。"""
    for seg in segments:
        if seg["id"] in member_ids:
            return seg.get("start_time") or 0.0
    return 0.0


def seg_table_range(segments: list[dict], member_ids: set[int]) -> tuple[float, float]:
    """一组分镜在分镜表时间轴上的 [起点, 终点)。"""
    start = None
    end = 0.0
    for seg in segments:
        if seg["id"] in member_ids:
            start = seg.get("start_time") or 0.0 if start is None else start
            end = max(end, seg.get("end_time") or 0.0)
    return (start if start is not None else 0.0, end)


async def repair_cross_group_sentences(clone_script_id: int, merged_path: str, db) -> None:
    """合并成片后的跨句音频修复编排：还原分组 → 找跨组句 → 实测各组实际起始 → 铺回原始句。

    任一步无数据或无跨组句时静默跳过（原成片保持不变）。
    """
    # 1. 分镜（含台词，audio_path 由共享助手补齐）+ 配音时长
    from app.services.clone_segment_video import _load_segment_audio_assets, _is_narration_line
    all_segments, voice_durations = await _load_segment_audio_assets(clone_script_id, db)
    if not all_segments or not voice_durations:
        logger.info('[跨句修复] 无分镜或无配音，跳过')
        return
    # 2. 还原分组：CloneSegmentVideo 锚在每组首分镜；组员 = 锚之间连续的分镜
    anchors = (await db.execute(
        select(CloneSegmentVideo.clone_script_sgement_id)
        .join(CloneScriptSegment, CloneSegmentVideo.clone_script_sgement_id == CloneScriptSegment.id)
        .where(CloneScriptSegment.script_id == clone_script_id)
    )).scalars().all()
    anchor_set = set(anchors)
    group_member_ids: list[set[int]] = []
    current: set[int] = set()
    for seg in all_segments:
        # CloneSegmentVideo 锚在每组首分镜（segment_ids[0]）：
        # 遇到新锚 → 上一组收口，开启新组
        if current and seg["id"] in anchor_set:
            group_member_ids.append(current)
            current = set()
        current.add(seg["id"])
    if current:
        # 最后一个锚之后开启的组（含其自身锚及后续分镜）
        group_member_ids.append(current)

    # 3. 找「一句话贯穿多个分镜」的句子（分镜表时间轴）
    sentences = find_multi_shot_sentences(all_segments, voice_durations)
    if not sentences:
        logger.info('[跨句修复] 无跨镜句，跳过')
        return

    # 4. 实测各组在成片里的实际起始（concat 后逐组实测时长累计），把表时间轴平移到实际时间轴
    actual_starts: list[float] = []
    offset = 0.0
    for members in group_member_ids:
        actual_starts.append(offset)
        # 组视频时长 = 该组锚（首分镜）的 CloneSegmentVideo 实测时长
        anchor_id = sorted(members & anchor_set)[0] if (members & anchor_set) else None
        vrow = None
        if anchor_id is not None:
            vrow = (await db.execute(
                select(CloneSegmentVideo).where(CloneSegmentVideo.clone_script_sgement_id == anchor_id)
            )).scalar_one_or_none()
        if vrow and vrow.path and os.path.isfile(vrow.path):
            offset += get_video_duration_ffprobe(vrow.path)

    # 表时间轴 → 实际时间轴：句子起点落在哪组，就按该组的（实际起点 - 表起点）平移
    shifted = []
    for sent in sentences:
        gi = next((gi for gi, members in enumerate(group_member_ids)
                   if seg_table_range(all_segments, members)[0] <= sent["merged_start"]
                   < seg_table_range(all_segments, members)[1]), None)
        if gi is None:
            shifted.append(sent)
            continue
        table_start = seg_table_start(all_segments, group_member_ids[gi])
        shifted.append({**sent, "merged_start": sent["merged_start"] + (actual_starts[gi] - table_start)})

    logger.info(f'[跨句修复] 跨组句 {len(shifted)} 个: ' + '; '.join(
        f"{os.path.basename(s['path'])}@{s['merged_start']:.2f}s(+{s['duration']:.2f}s)" for s in shifted))

    # 5. 修复（写旁路文件再原子替换，失败保留原成片）
    tmp_path = merged_path + '.repair.mp4'
    repair_cross_group_audio(merged_path, shifted, tmp_path)
    os.replace(tmp_path, merged_path)
    logger.info(f'[跨句修复] 完成: {merged_path}')


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
        
        clone_script.generate_flow_progress = MERGE_VIDEO_BEGIN_PROGRESS
        clone_script.generate_flow_status = GenerateFlowStatus.MERGE_VIDEO
        await db.commit()

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

        # 跨句音频修复：一句话贯穿多个分镜组时，把原始完整句音频铺回成片，
        # 消除 H3 分组重建音轨的组间接缝不连贯。
        try:
            await repair_cross_group_sentences(clone_script_id, abs_output_path, db)
        except Exception:
            logger.exception('跨句音频修复失败（不影响合并产物，保留原成片）')

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

        clone_script.generate_flow_progress = MERGE_VIDEO_COMPLETE_PROGRESS
        clone_script.generate_flow_status = GenerateFlowStatus.MERGE_VIDEO_DONE
        await db.commit()
        logger.info(f'合并视频完成: {output_path}, duration={duration}, status={clone_script.clone_status.value}')
    except Exception as e:
        logger.exception('merge_segment_videos 发生错误')
        await db.rollback()
        if clone_script:
            clone_script.clone_error_message = '合并分镜视频时发生错误'
            clone_script.generate_flow_status = GenerateFlowStatus.FAILED
            await db.commit()
        raise
    finally:
        await db.close()


if __name__ == '__main__':
    process_loop.init_process()
    process_loop.run(merge_segment_videos(54))
    process_loop.shutdown()
