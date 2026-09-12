
import asyncio
import inspect
import os
import time
from pathlib import Path
from typing import NamedTuple
from pydub import AudioSegment
import requests
from sqlalchemy import delete, select
from app.tasks.process_loop_manager import process_loop

from celery.utils.log import get_task_logger
from app.config import settings
from app.models.script import CloneScript, CloneScriptSegment, CloneSegmentImg, CloneSegmentVideo, CloneVoice, GenerateFlowStatus, GenerateStatus
from app.util import SEGMENT_VIDEO_BEGIN_PROGRESS, SEGMENT_VIDEO_COMPLETE_PROGRESS, get_md5, make_dir, run_ffmpeg
from app.services.clone_service import SEGMENT_CONTINUATION_PAD
from app.services.gen_image import GenImage, GenVideoParams, ReferImageInfo, VideoSize
from app.services.h3_prompt_optimizer import optimize_script_prompts

logger = get_task_logger(__name__)

# 旁白/画外音角色名关键词（命中视为旁白，不写入口型参考音频）
NARRATION_ROLE_KEYWORDS = ("旁白", "解说", "配音", "画外音", "narrator", "voiceover", "narration")


class RefAudio(NamedTuple):
    """口型参考音频切片：完整句音频 + 在该完整句内的 [起点, 时长]（秒）。"""
    path: str
    start: float
    duration: float


class AudioOverlay(NamedTuple):
    """需在生成后合入的旁白切片：完整句音频内的[起点,时长] + 本组内位置（秒）。"""
    path: str
    start: float
    duration: float
    clip_local: float


def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")
    
def merge_segment_prompt(segment: CloneScriptSegment):
    prompt = f"""镜头：{segment.shot_type}
{segment.shot_description}
""" 
    visible_role_list = []
    for role in segment.role_view_info:
        if role['visibility'] != 'invisible':
            visible_role_list.append(role['role_name'])
    
    for item in segment.dialogue:
        if item['role_name'] in visible_role_list:
            prompt += f'{item['role_name']}：{item['lines']} \n'
    
    logger.info(f'merge_segment_prompt is {prompt}')
    return prompt
        
def process_and_concat_audios(input_paths: list[str|float], output_path: str) -> str:
    """
    1. 获取第一个 MP3 的采样率和通道数并打印
    2. 生成指定时长的静音数据存入变量 silence
    3. 按顺序拼接静音及输入的 MP3 文件
    4. 输出最终拼接好的音频文件路径
    """
    if not input_paths:
        raise ValueError("输入文件路径列表不能为空！")

    print(f'input_paths: {input_paths}')
    first_file_path = None
    for item in input_paths:
        if isinstance(item, str):
            first_file_path = item
            break
    # 读取第一个 MP3 文件以获取音频参数
    if first_file_path:
        first_audio = AudioSegment.from_file(first_file_path)
        
        sample_rate = first_audio.frame_rate  # 采样率 (Hz)
        channels = first_audio.channels       # 通道数 (1=mono, 2=stereo)
        duration_sec = first_audio.duration_seconds # 时长 (秒)
    else:
        sample_rate = 24000
        channels = 1
        duration_sec = 0.0

    print(f"=== 首个音频文件参数 ({first_file_path}) ===")
    print(f"时长: {duration_sec:.2f} 秒")
    print(f"采样率: {sample_rate} Hz")
    print(f"通道数: {channels}")
    print("=" * 40)
    
    combined = None
    for item in input_paths:
        if isinstance(item, float):
            # 根据首个音频的采样率和通道数，生成 1.5 秒（或指定时长）的静音数据存入 silence 变量
            silence_ms = int(item * 1000)
            silence = AudioSegment.silent(duration=silence_ms, frame_rate=sample_rate)
            # 确保静音数据的通道数与目标一致
            silence = silence.set_channels(channels)
            if not combined:
                combined = silence
            else:
                combined += silence
        else:
            audio = AudioSegment.from_file(item)
            # 统一采样率和通道数，避免拼接时参数不一致导致的音频失真
            audio = audio.set_frame_rate(sample_rate).set_channels(channels)
            if not combined:
                combined = audio
            else:
                combined += audio
    
    if not combined:
        raise ValueError('not generate any audio')
    combined.export(output_path, format="mp3")
    print(f"拼接完成！输出文件路径: {output_path}")
    
    return output_path

def merge_audio(segment: CloneScriptSegment, output_path: str):
    if len(segment.dialogue) == 0:
        process_and_concat_audios(input_paths=[segment.end_time - segment.start_time], output_path=output_path)
        return
    visible_role_list = []
    for role in segment.role_view_info:
        if role['visibility'] != 'invisible':
            visible_role_list.append(role['role_name'])

    audio_list = []
    for item in segment.dialogue:
        if item['role_name'] in visible_role_list:
            audio_list.append(item['audio_path'])
        else:
            audio_list.append(item['end_offset'] - item['start_offset'])
    process_and_concat_audios(input_paths=audio_list, output_path=output_path)


def _is_narration_line(dialogue_item: dict, segment: dict) -> bool:
    """判断一句台词是否为旁白/画外音（不驱动画面人物口型的参考音频）。

    规则：角色名命中旁白词组；或该镜中该角色 visibility == "invisible"；
    角色未在 role_view_info 列明时默认视为旁白，避免乱驱动口型。
    """
    role_name = dialogue_item.get('role_name')
    if role_name and any(k in role_name for k in NARRATION_ROLE_KEYWORDS):
        return True
    for rv in (segment.get('role_view_info') or []):
        if rv.get('role_name') == role_name:
            return rv.get('visibility') == 'invisible'
    return True


def _audio_duration_of(
    dialogue_item: dict,
    voice_durations: dict,
    real_dur_cache: dict,
) -> float | None:
    """整句真实时长：优先 CloneVoice 配音表，回落探测音频文件（结果按 path 缓存）。"""
    search_md5 = get_md5(dialogue_item.get('lines') or '')
    dur = voice_durations.get(
        (dialogue_item.get('role_name'), dialogue_item.get('audio_style'), search_md5)
    )
    if dur is not None and dur > 0:
        return float(dur)
    path = dialogue_item.get('audio_path')
    if path:
        if path not in real_dur_cache:
            if os.path.isfile(path):
                try:
                    real_dur_cache[path] = AudioSegment.from_file(path).duration_seconds
                except Exception:
                    real_dur_cache[path] = 0.0
            else:
                return None
        if real_dur_cache[path] > 0:
            return real_dur_cache[path]
    return None


class _LipSlice(NamedTuple):
    """组内一句口型台词的可闻切片：完整句音频内的起点+时长、本组内位置。"""
    path: str
    start_in_full: float
    duration: float
    clip_local: float


def _export_fallback_ref(save_dir: str, tag: str, track: AudioSegment) -> RefAudio:
    """导出兜底参考音频（整组铺好的轨道），起点 0/全长。"""
    ref_path = str(Path(save_dir) / f"{tag}_{round(time.time() * 1000)}.mp3")
    track.export(ref_path, format="mp3")
    return RefAudio(ref_path, 0.0, round(len(track) / 1000.0, 3))


def _build_narration_only_ref(overlays: list[AudioOverlay], clip_dur: float) -> AudioSegment:
    """纯旁白组参考音轨：旁白按其镜内位置直接铺入（画外音不驱动口型，
    提示词已要求 off-screen lips closed），生成后不再重复混入。"""
    track = AudioSegment.silent(duration=int(clip_dur * 1000), frame_rate=44100).set_channels(1)
    src_cache: dict[str, AudioSegment] = {}
    for ov in overlays:
        src = src_cache.get(ov.path)
        if src is None:
            src = AudioSegment.from_file(ov.path)
            src_cache[ov.path] = src
        start_ms = int(ov.start * 1000)
        end_ms = int(min(ov.start + ov.duration, len(src) / 1000.0) * 1000)
        if end_ms <= start_ms:
            continue
        track = track.overlay(src[start_ms:end_ms], position=max(0, int(ov.clip_local * 1000)))
    return track


def _build_empty_ref(clip_dur: float) -> AudioSegment:
    """无台词组的兜底音轨：-60dB 极轻噪底（非全零，人耳不可闻）。
    纯数字静音会使 H3 音频 VAE 崩溃（IndexError，已实测），噪底保住时间轴画面。"""
    return AudioSegment.silent(duration=int(clip_dur * 1000), frame_rate=44100) \
        .set_channels(1).apply_gain(-60)


def build_segment_group_audio_package(
    all_segments: list[dict],
    group_segment_ids: list[int],
    voice_durations: dict,
    save_dir: str,
) -> tuple[RefAudio | None, list[AudioOverlay]]:
    """构造一个分镜组的「口型参考音频 + 待合入旁白」。

    跨镜长台词（lines_flag head/body/tail）用同一完整音频、不同切片：
    - audio_start = 该完整句在本组分镜前的累计消耗（与 sync_segment_timeline 同源）
    - audio_duration = 本组分镜内铺入的时长（head/all 吃满剩余，body/tail 只给衔接垫）
    用户示例：10s 句跨 6s/4s 镜 → group1(0,6) group2(6,4)，均用同一 10s 完整音频。

    Returns:
        ref: RefAudio(完整音频路径, audio_start, audio_duration)，直接喂给 runninghub H3 音驱工作流。
             无口型台词时兜底：纯旁白组旁白直接作参考音轨；纯空镜组 -60dB 噪底（纯静音会撞坏 H3 VAE）。
        overlays: [AudioOverlay(旁白完整音频路径, 完整音频内切片起点, 切片时长, 本组内位置)] 生成后合入；
             兜底路径（旁白直接作参考音轨）时为空。
    """
    group_ids = set(group_segment_ids)
    group_segments = [s for s in all_segments if s['id'] in group_ids]
    if not group_segments:
        return None, []
    group_start = group_segments[0].get('start_time') or 0.0
    group_end = group_segments[-1].get('end_time') or group_start
    clip_dur = max(0.0, group_end - group_start)

    real_dur_cache: dict[str, float] = {}

    # 顺序扫描到本组最后一个分镜为止。切片分配镜像 sync_segment_timeline 的校准规则，
    # 保证参考音轨与镜头时长逐镜同源：
    # - head/all 镜：从 start_offset 起铺整句剩余（真实时长，含句尾自然衰减前的全部语音）
    # - body/tail 镜：铺句尾之后的接续内容（衔接垫，不推进整句的语音消耗）
    # consumed 按「文件内已消耗位置」累计；真实文件时长为上限。
    lip_slices: list[_LipSlice] = []
    overlays: list[AudioOverlay] = []              # 旁白切片
    consumed: dict[str, float] = {}
    walk_end = all_segments.index(group_segments[-1]) + 1
    for seg in all_segments[:walk_end]:
        seg_local = (seg.get('start_time') or 0.0) - group_start
        for item in seg.get('dialogue') or []:
            path = item.get('audio_path')
            if not path:
                continue
            real_total = _audio_duration_of(item, voice_durations, real_dur_cache)
            if real_total is None or real_total <= 0:
                continue  # 查不到真实配音 → 该行不计入
            start_in_full = consumed.get(path, 0.0)
            if item.get('lines_flag') in ('body', 'tail'):
                # 延续镜：铺句子当前位置起的 SEGMENT_CONTINUATION_PAD 接续，
                # 与校准规则一致（垫时长不消耗整句语音，不推进 consumed）。
                portion = SEGMENT_CONTINUATION_PAD
                if seg.get('id') not in group_ids:
                    continue  # 非本组分镜：不收集切片
                clip_local = seg_local + (item.get('start_offset') or 0.0)
                if _is_narration_line(item, seg):
                    overlays.append(AudioOverlay(path, start_in_full, portion, clip_local))
                else:
                    lip_slices.append(_LipSlice(path, start_in_full, portion, clip_local))
                continue
            # head/all 镜：从 start_offset 起铺整句剩余（真实时长）
            remaining = max(0.0, real_total - start_in_full)
            if remaining <= 0:
                continue  # 句已播完：后续镜为空窗
            portion = remaining
            consumed[path] = start_in_full + portion
            if seg.get('id') not in group_ids:
                continue  # 非本组分镜：只累计已消耗，不收集切片
            clip_local = seg_local + (item.get('start_offset') or 0.0)
            if _is_narration_line(item, seg):
                overlays.append(AudioOverlay(path, start_in_full, portion, clip_local))
            else:
                lip_slices.append(_LipSlice(path, start_in_full, portion, clip_local))

    if not lip_slices:
        # 无口型台词：仍需生成画面保住时间轴。
        # 纯旁白组 → 旁白直接作参考音轨（画外音不驱动口型，无需生成后合入，overlays 清空防重复）；
        # 纯空镜组 → -60dB 噪底兜底（纯静音会使 H3 音频 VAE 崩溃）。
        if overlays:
            narration_ref = _export_fallback_ref(
                save_dir, "ref_narration", _build_narration_only_ref(overlays, clip_dur)
            )
            return narration_ref, []
        return _export_fallback_ref(save_dir, "ref_silence", _build_empty_ref(clip_dur)), []

    unique_paths = {s.path for s in lip_slices}
    if len(unique_paths) == 1:
        # Case A：组内仅一句完整口型台词 → 用该完整音频 + 切片区间，不预切分。
        # 时长按台词窗口取，仅受真实音频上限钳制（镜长短于窗口时仍传窗口切片，
        # H3 的音频起点/时长语义与提示词的台词窗口一一对应）。
        path = next(iter(unique_paths))
        audio_start = round(min(s.start_in_full for s in lip_slices), 3)
        audio_dur = round(sum(s.duration for s in lip_slices), 3)
        total = real_dur_cache.get(path)
        if total is not None and audio_start < total:
            # 仅钳制句内切片；衔接垫切片（起点=句尾）不受整句时长钳制
            head_slices = [s for s in lip_slices if s.start_in_full < total]
            if len(head_slices) < len(lip_slices):
                # 含衔接垫切片：只钳制句内部分
                in_full = sum(s.duration for s in head_slices)
                audio_dur = min(in_full, max(0.0, total - audio_start)) + \
                    (audio_dur - in_full)
        return RefAudio(path, audio_start, max(audio_dur, 0.1)), overlays

    # Case B：组内多句口型台词 → 拼合为镜内完整音频（各句按时间窗在镜内位置铺放）
    track = AudioSegment.silent(duration=int(clip_dur * 1000), frame_rate=44100).set_channels(1)
    src_cache: dict[str, AudioSegment] = {}
    for sl in lip_slices:
        src = src_cache.get(sl.path)
        if src is None:
            src = AudioSegment.from_file(sl.path)
            src_cache[sl.path] = src
        total = real_dur_cache.get(sl.path) or (len(src) / 1000.0)
        start_ms = int(min(sl.start_in_full, total) * 1000)
        end_ms = int(min(sl.start_in_full + sl.duration, total) * 1000)
        if end_ms <= start_ms:
            continue
        track = track.overlay(src[start_ms:end_ms], position=max(0, int(sl.clip_local * 1000)))
    ref_path = str(Path(save_dir) / f"ref_combined_{round(time.time() * 1000)}.mp3")
    track.export(ref_path, format="mp3")
    return RefAudio(ref_path, 0.0, round(clip_dur, 3)), overlays


def overlay_narration_audio(
    clip_path: str,
    overlays: list[AudioOverlay],
    output_path: str,
) -> str:
    """把旁白音频按镜内位置合入已生成的分镜视频（口型参考音轨中旁白为静音区间）。

    Args:
        clip_path: 生成的原始分镜 mp4（含口型参考音轨）
        overlays: [AudioOverlay(旁白完整音频路径, 完整音频内切片起点, 切片时长, 本组内位置)]
        output_path: 合入后的输出文件路径

    Returns:
        output_path
    """
    if not overlays:
        os.replace(clip_path, output_path)
        return output_path

    cmd = ["ffmpeg", "-y", "-i", clip_path]
    for ov in overlays:
        cmd += ["-ss", f"{ov.start:.3f}", "-t", f"{ov.duration:.3f}", "-i", ov.path]

    filter_parts = []
    for i, ov in enumerate(overlays, start=1):
        pos_ms = int(ov.clip_local * 1000)
        filter_parts.append(
            f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"adelay=delays={pos_ms}:all=1[na{i}]"
        )
    mix_inputs = "".join(f"[na{i}]" for i in range(1, len(overlays) + 1))
    filter_parts.append(
        f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        f"[a0]{mix_inputs}amix=inputs={len(overlays) + 1}:duration=first:dropout_transition=0[aout]"
    )
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    logger.info(f"执行旁白合入 ffmpeg: {' '.join(cmd)}")
    run_ffmpeg(cmd, "旁白合入失败")
    return output_path
    
async def upload_asset(asset_list: list[ReferImageInfo]):
    logger.info(f'asset_list is {asset_list}')
    url = settings.COMFY_URL + '/upload/image'
    for image_path in asset_list:
        with open(image_path.path, "rb") as f:
            # files 字典的 key 必须是 'image'
            files = {"image": f}
            # 如果需要，可以通过 overwrite 覆盖同名文件
            data = {"overwrite": "true"}
            response = requests.post(url, files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            image_path.name_comfy = result["name"]  # 返回服务器上的文件名（例如: "example.png"）
            logger.info(f'send comfy name is {image_path.name_comfy}')
        else:
            raise Exception(f"上传失败: {response.text}")


async def _load_segment_audio_assets(clone_script_id: int, db):
    """预载分镜（含台词/出场信息）与配音真实时长，供 runninghub 音频切片使用。

    老数据/require_voice=False 时分镜 dialogue 里可能没有 audio_path，
    这里按 (role_name, text_md5) 从 CloneVoice 补齐 —— 同一完整句跨镜共用同一完整音频。
    """
    seg_res = await db.execute(
        select(CloneScriptSegment)
        .where(CloneScriptSegment.script_id == clone_script_id)
        .order_by(CloneScriptSegment.start_time)
    )
    segments = seg_res.scalars().all()

    voice_res = await db.execute(
        select(CloneVoice).where(CloneVoice.script_id == clone_script_id)
    )
    voices = voice_res.scalars().all()
    voice_durations = {
        (v.role_name, v.voice_type, v.text_md5): v.duration
        for v in voices
    }
    # 台词音频路径：优先精确匹配 (role, md5, voice_type=audio_style)，回落 (role, md5)
    voice_path_exact = {(v.role_name, v.text_md5, v.voice_type): v.path for v in voices}
    voice_path_any: dict[tuple[str, str], str] = {}
    for v in voices:
        voice_path_any.setdefault((v.role_name, v.text_md5), v.path)

    all_segments = []
    for seg in segments:
        dialogue = []
        for d in (seg.dialogue or []):
            item = dict(d)
            if not item.get('audio_path'):
                md5 = get_md5(item.get('lines') or '')
                path = (
                    voice_path_exact.get((item.get('role_name'), md5, item.get('audio_style')))
                    or voice_path_any.get((item.get('role_name'), md5))
                )
                if path:
                    item['audio_path'] = path
            dialogue.append(item)
        all_segments.append({
            "id": seg.id,
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "dialogue": dialogue,
            "role_view_info": seg.role_view_info or [],
        })
    return all_segments, voice_durations


async def generate_segments_video_minimax_h3(clone_script_id: int, go_head: bool=False, max_groups: int | None = None):
    """使用minimax_h3 关联角色信息生成视频

    USE_COMFY_VIDEO=True 走本地 Comfy（i2v_local_minimax_h3）；
    False 走 RunningHub「minimax H3 多人音频驱动」工作流（merge_segments=True，
    参考图 + 完整音频 + 音频起点/时长，生成后旁白合入）。

    Args:
        clone_script_id (int): 复刻脚本id
        go_head (bool, optional): 是否跳过已生成分镜视频. Defaults to False.
        max_groups (int | None, optional): 只生成前几个分镜组（分批生成用），None 全部.
    """
    db = process_loop.AsyncSessionLocal()
    clone_script = None
    try:
        res = await db.execute(select(CloneScript).where(CloneScript.id == clone_script_id))
        clone_script = res.scalar_one_or_none()
        if not clone_script:
            raise ValueError(f'not find clone_script: {clone_script_id}')
        clone_script.generate_flow_progress = SEGMENT_VIDEO_BEGIN_PROGRESS
        await db.commit()

        # 1. 生成符合minimax_h3的提示词（runninghub 打开 merge_segments 合并连续分镜）
        merge_segments = not settings.USE_COMFY_VIDEO
        if not settings.USE_COMFY_VIDEO:
            # 仅 runninghub 分支预载分镜 + 配音时长（音频切片用；comfy 分支不浪费 DB 查询）
            all_segments, voice_durations = await _load_segment_audio_assets(clone_script_id, db)
        else:
            all_segments, voice_durations = [], {}
        segment_param_list = await optimize_script_prompts(
            clone_script_id, merge_segments=merge_segments, max_groups=max_groups
        )
        total = len(segment_param_list)
        if total == 0:
            raise ValueError(f'clone_script {clone_script_id} 没有可生成视频的分镜')

        for i, segment_param in enumerate(segment_param_list):
            segment_ids = segment_param['segment_ids']
            if not segment_ids:
                continue
            # go_head: 已有成功记录则跳过
            if go_head:
                res = await db.execute(
                    select(CloneSegmentVideo)
                    .where(CloneSegmentVideo.clone_script_sgement_id == segment_ids[0])
                )
                existed = res.scalar_one_or_none()
                if existed and existed.status == GenerateStatus.SUCCESS:
                    logger.info(f'go_head skip it. {existed.desc}')
                    continue
            # 重跑：先删旧记录，避免重复
            await db.execute(
                delete(CloneSegmentVideo)
                .where(CloneSegmentVideo.clone_script_sgement_id == segment_ids[0])
            )
            logger.info(f'begin generate {i+1}/{total} video (segment_ids={segment_ids})...')

            # 2. 参考图片
            ref_pictures = []
            for image in segment_param['image_map']:
                for path in image.values():
                    ref_pictures.append(ReferImageInfo(type='ref', path=path))
            if not ref_pictures:
                raise ValueError(f'segment_ids={segment_ids} 没有参考图片')

            save_dir = settings.UPLOAD_DIR + '/clone_' + str(clone_script_id) + '/segment_' + str(i)
            make_dir(save_dir, re_create=False)

            if settings.USE_COMFY_VIDEO:
                # —— 本地 Comfy 分支 ——
                await upload_asset(ref_pictures)
                logger.info(f'refer image is {ref_pictures}')
                gen_video_params = GenVideoParams(
                    prompt=segment_param['prompt'],
                    video_size=VideoSize.SIZE_864x480,
                    duration=segment_param['duration'],
                    rate=24,
                    refer_images=ref_pictures,
                )
                video_path = await GenImage.i2v_local_minimax_h3(gen_video_params, save_dir)
            else:
                # —— RunningHub H3 音驱分支 ——
                ref, overlays = build_segment_group_audio_package(
                    all_segments, segment_ids, voice_durations, save_dir
                )
                gen_video_params = GenVideoParams(
                    prompt=segment_param['prompt'],
                    video_size=VideoSize.SIZE_864x480,
                    duration=segment_param['duration'],
                    rate=24,
                    refer_images=ref_pictures + [ReferImageInfo(type='audio', path=ref.path)],
                )
                logger.info(f'[runninghub] segment_ids={segment_ids} 音频包 '
                            f'{ref.path} [起点={ref.start}s 时长={ref.duration}s] 旁白段={len(overlays)}')
                raw_path = await GenImage.i2v_runninghub_h3(
                    gen_video_params, save_dir, audio_start=ref.start, audio_duration=ref.duration
                )
                final_path = str(Path(save_dir) / 'segment_video.mp4')
                video_path = overlay_narration_audio(raw_path, overlays, final_path)
                # 清理原始下载（旁白已合入 segment_video.mp4）
                if raw_path != video_path and os.path.isfile(raw_path):
                    os.remove(raw_path)
                logger.info(f'segment {segment_ids} runninghub video saved: {video_path}')

            # 4. 保存数据（一组对应组内第一个分镜，video_merge 按 start_time 排序合并）
            db.add(CloneSegmentVideo(
                clone_script_sgement_id=segment_ids[0],
                width=gen_video_params.video_size.width,
                height=gen_video_params.video_size.height,
                path=video_path,
                prompt=segment_param['prompt'],
                status=GenerateStatus.SUCCESS,
                seed=gen_video_params.seed,
                desc=f'分镜{i+1}',
                version=0,
            ))
            clone_script.generate_flow_progress = SEGMENT_VIDEO_BEGIN_PROGRESS + (SEGMENT_VIDEO_COMPLETE_PROGRESS - SEGMENT_VIDEO_BEGIN_PROGRESS) * (i + 1) // total
            await db.commit()
            logger.info(f'segment {segment_ids} video saved: {video_path}')

        clone_script.generate_flow_progress = SEGMENT_VIDEO_COMPLETE_PROGRESS
        clone_script.generate_flow_status = GenerateFlowStatus.SEGMENT_VIDEO_DONE
        await db.commit()
    except Exception as e:
        logger.exception('generate_segments_video_minimax_h3 发生错误')
        await db.rollback()
        if clone_script:
            clone_script.clone_error_message = '生成分镜视频时发生错误'
            clone_script.generate_flow_status = GenerateFlowStatus.FAILED
            await db.commit()
        raise
    finally:
        await db.close()


async def generate_segments_video(clone_script_id: int, go_head: bool=False):
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    try:
        res = await db.execute(select(CloneScript).where(CloneScript.id == clone_script_id))
        clone_script = res.scalar_one_or_none()
        if not clone_script:
            raise ValueError('not find clone_script.')
        clone_script.generate_flow_progress = SEGMENT_VIDEO_BEGIN_PROGRESS
        await db.commit()
        
        res = await db.execute(select(CloneScriptSegment).where(CloneScriptSegment.script_id == clone_script_id).order_by(CloneScriptSegment.start_time))
        segments = res.scalars().all()
        video_size = None
        for i, segment in enumerate(segments):
            if i > 0:
                continue
            if go_head:
                res = await db.execute(select(CloneSegmentVideo).where(CloneSegmentVideo.clone_script_sgement_id == segment.id))
                clone_segment_video = res.scalar_one_or_none()
                if clone_segment_video and clone_segment_video.status==GenerateStatus.SUCCESS:
                    logger.info(f'go_head skip it. {clone_segment_video.desc}')
                    continue
            else:
                await db.execute(select(CloneSegmentVideo).where(CloneSegmentVideo.clone_script_sgement_id == segment.id))
                await db.commit()
            save_dir = settings.UPLOAD_DIR + '/clone_' + str(clone_script_id) + '/segment_' + str(i)
            make_dir(save_dir, re_create=False)
            res = await db.execute(select(CloneSegmentImg).where(CloneSegmentImg.clone_script_sgement_id == segment.id))
            clone_segment_images = res.scalars().all()
            if not video_size:
                video_size = VideoSize.SIZE_512x512
                if len(clone_segment_images) > 0:
                    if clone_segment_images[0].width > clone_segment_images[0].height:
                        video_size = VideoSize.SIZE_848x480
                    if clone_segment_images[0].width < clone_segment_images[0].height:
                        video_size = VideoSize.SIZE_480x848
            refer_frames = [ReferImageInfo(type='frame', path=images.path)  for images in clone_segment_images]
            
            # 1. 拼接提示词
            merge_prompt = merge_segment_prompt(segment)
            print(merge_prompt)
            # 2. 拼接音频
            output_path = save_dir + f"/merge_audio.mp3"
            merge_audio(segment, output_path)
            if not os.path.exists(output_path):
                raise Exception('merge_audio output_path not exists')
            if not os.path.isfile(output_path):
                raise Exception('merge_audio output_path not file')
            refer_frames.append(ReferImageInfo(type='audio', path=output_path))
            # 3. 上传资产
            await upload_asset(refer_frames)
            logger.info(f'refer_frames: {refer_frames}')
            # 4. 生成视频
            rate = 24
            duration = segment.end_time - segment.start_time
            params = GenVideoParams(prompt=merge_prompt, video_size=video_size, duration=duration, rate=rate, refer_images=refer_frames)
            video_path = await GenImage.ai2v_local_ltx23(gen_video_params=params, save_dir=save_dir)
            # 5. 保存数据
            clone_segment_video = CloneSegmentVideo(
                clone_script_sgement_id=segment.id,
                width=video_size.width,
                height=video_size.height,
                path=video_path,
                prompt=merge_prompt,
                status=GenerateStatus.SUCCESS,
                seed=params.seed,
                desc=f'分镜{i+1}',
                version=0
            )
            db.add(clone_segment_video)
            clone_script.generate_flow_progress = SEGMENT_VIDEO_BEGIN_PROGRESS + (SEGMENT_VIDEO_COMPLETE_PROGRESS - SEGMENT_VIDEO_BEGIN_PROGRESS) * (i + 1) // len(segments)
            await db.commit()
            await db.refresh(clone_segment_video)

        clone_script.generate_flow_progress = SEGMENT_VIDEO_COMPLETE_PROGRESS
        clone_script.generate_flow_status = GenerateFlowStatus.SEGMENT_VIDEO_DONE
        await db.commit()
    except ValueError:
        logger.exception('not find data')
        raise
    except Exception as e:
        logger.exception('generate_segment_video 发生错误')
        await db.rollback()  # ✅ 先回滚，重置数据库 Session 状态
        if clone_script:
            clone_script.clone_error_message = '生成分镜视频时发生错误'
            clone_script.generate_flow_status = GenerateFlowStatus.FAILED
            await db.commit()
        raise
    finally:
        await db.close()

async def get_video():
    await GenImage.test_get_video()


if __name__ == '__main__':
    process_loop.init_process()
    process_loop.run(get_video())
    process_loop.shutdown()
    
    # asyncio.run(generate_segments_video(46))