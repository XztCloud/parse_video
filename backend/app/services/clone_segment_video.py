
import asyncio
import inspect
import os
from pydantic import BaseModel, Field
from pydub import AudioSegment
import requests
from sqlalchemy import delete, select
from app.tasks.process_loop_manager import process_loop

from celery.utils.log import get_task_logger
from app.config import settings
from app.models.script import CloneScript, CloneScriptSegment, CloneSegmentImg, CloneSegmentVideo, CloneStatus, GenerateStatus
from app.util import make_dir
from app.services.gen_image import GenImage, GenVideoParams, ReferImageInfo, VideoSize

logger = get_task_logger(__name__)

BEGIN_PROGRESS = 61
COMPLETE_PROGRESS = 95



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
    

async def generate_segments_video(clone_script_id: int, go_head: bool=False):
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    try:
        res = await db.execute(select(CloneScript).where(CloneScript.id == clone_script_id))
        clone_script = res.scalar_one_or_none()
        if not clone_script:
            raise ValueError('not find clone_script.')
        clone_script.clone_progress = BEGIN_PROGRESS
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
            print(f'refer_frames: {refer_frames}')
            # 4. 生成视频
            rate = 24
            duration = segment.end_time - segment.start_time
            params = GenVideoParams(prompt=merge_prompt, video_size=video_size, duration=duration, rate=rate, refer_images=refer_frames)
            video_path = await GenImage.ai2v_local_flux2_klien(gen_video_params=params, save_dir=save_dir)
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
            clone_script.clone_progress = BEGIN_PROGRESS + int((COMPLETE_PROGRESS - BEGIN_PROGRESS) * (i + 1) / len(segments))
            await db.commit()
            await db.refresh(clone_segment_video)

        clone_script.clone_progress = COMPLETE_PROGRESS
        clone_script.clone_status = CloneStatus.SEGMENT_VIDEO_DONE
        await db.commit()
    except ValueError:
        logger.exception('not find data')
        raise
    except Exception as e:
        logger.exception('generate_segment_video 发生错误')
        await db.rollback()  # ✅ 先回滚，重置数据库 Session 状态
        if clone_script:
            clone_script.clone_error_message = '生成分镜视频时发生错误'
            clone_script.clone_status = CloneStatus.FAILED
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