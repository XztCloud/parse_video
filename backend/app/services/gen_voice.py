

import asyncio
import base64
from datetime import datetime 
import json
import os
from pathlib import Path
import shutil
import traceback
from typing import List, Literal, Optional
import uuid

from pydantic import BaseModel, Field
import requests
import volcenginesdkcore
import volcenginesdkspeechsaasprod
from volcenginesdkcore.rest import ApiException
from langchain.messages import AIMessage, HumanMessage
from mutagen.mp3 import MP3

from app.util import async_retry_error, retry_error

from app.config import settings
from app.services.llm import SelectVoiceID

import re

from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)

MAX_CONCURRENT = 3
url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"

def parse_event(stream):
    event = {
        "event": "",
        "data": ""
    }

    for raw_line in stream:
        line = raw_line.decode("utf-8").strip()
        # 空行 = 一个完整事件结束
        if line == "":
            if event["data"]:
                # 去掉最后一个换行
                event["data"] = event["data"].rstrip("\n")
                yield event
            event = {
                "id": None,
                "event": "message",
                "data": "",
                "retry": None
            }
            continue

        # 注释行（以:开头）
        if line.startswith(":"):
            continue

        if ":" in line:
            field, value = line.split(":", 1)
            value = value.lstrip()

            if field == "data":
                event["data"] += value + "\n"
            elif field == "event":
                event["event"] = value

    # 处理流结束但没有空行的情况
    if event["data"]:
        event["data"] = event["data"].rstrip("\n")
        yield event

def get_exact_duration(file_path):
    # 直接解析 MP3 文件
    audio = MP3(file_path)
    
    # 获取精准时长（秒）
    duration = audio.info.length
    
    # 顺便一提，你可以用这个库直接验证你的已知参数是否准确：
    # logger.info(f"实际采样率: {audio.info.sample_rate} Hz")
    # logger.info(f"实际比特率: {audio.info.bitrate / 1000} kbps")
    
    return duration

@retry_error
def tts_http_sse_stream(url, headers, params, audio_save_path):
    session = requests.Session()
    try:
        # logger.info('请求的url:', url)
        # logger.info('请求的headers:', headers)
        # logger.info('请求的params:\n', params)
        response = session.post(url, headers=headers, json=params, stream=True)
        # logger.info(response)
        # 打印response headers
        # logger.info(f"code: {response.status_code} header: {response.headers}")
        logid = response.headers.get('X-Tt-Logid')
        # logger.info(f"X-Tt-Logid: {logid}")

        # 用于存储音频数据
        audio_data = bytearray()
        total_audio_size = 0
        for event_data in parse_event(response.iter_lines()):
            if not event_data:
                continue
            # logger.info('get event', event_data['event'])
            data = json.loads(event_data['data'])

            if data.get("code", 0) == 0 and "data" in data and data["data"]:
                chunk_audio = base64.b64decode(data["data"])
                audio_size = len(chunk_audio)
                total_audio_size += audio_size
                audio_data.extend(chunk_audio)
                continue
            if data.get("code", 0) == 0 and "sentence" in data and data["sentence"]:
                # logger.info("sentence_data:", data)
                continue
            if data.get("code", 0) == 20000000:
                if 'usage' in data:
                    logger.info("usage:", data['usage'])
                break
            if data.get("code", 0) > 0:
                logger.info(f"error response:{data}")
                break
        
        duration = 0
        # 保存音频文件
        if audio_data:
            if os.path.exists(audio_save_path):
                backup_path = f"{audio_save_path}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(audio_save_path, backup_path)
                logger.info(f"📦 原文件已备份到: {backup_path}")

            with open(audio_save_path, "wb") as f:
                f.write(audio_data)
            logger.info(f"文件保存在{audio_save_path},文件大小: {len(audio_data) / 1024:.2f} KB")
            # 确保生成的音频有正确的访问权限
            os.chmod(audio_save_path, 0o644)
            duration = get_exact_duration(audio_save_path)
        return duration
    
    except Exception as e:
        logger.info(f"请求失败: {e}")
        logger.exception('tts_http_sse_stream')
        raise e
    finally:
        response.close()
        session.close()


class Lines(BaseModel):
    role_name: str = Field(..., description="说话角色名，与音色dict对应")
    audio_style: str = Field(..., description="音频情绪，例如：愤怒、严厉、高分贝；唯唯诺诺、无奈、叹气 等")
    text: str = Field(..., description="人物台词")
    audio_path: Optional[Path] = Field(default=None, description='生成音频路径')
    duration: float = Field(default=0.0, description='音频时长')
    speed: int = Field(default=20, ge=-50, le=100, description='语速控制，-50表示0.5倍速， 100表示2倍速')  # 基础语速设置20，不然很多音色太慢，不连贯
    target_duration: Optional[float] = Field(default=None, description='计算得到的每句话目标时长')
    spk_id: Optional[str] = Field(default=None, description="音色id")

class GenVoiceParam(BaseModel):
    role_name: str
    voice_desc: str | None
    age: int
    gender: Literal['male', 'female'] = Field(description="角色的性别。")
    lines_list: List[str]
    # voice_type: Optional[str] = Field(default=None, description='音色ID')
    

class GenVoice:

    def __init__(self):
        self.config = volcenginesdkcore.Configuration()
        self.config.ak = settings.BYTEDANCE_AK
        self.config.sk = settings.BYTEDANCE_SK
        self.config.region = "cn-beijing"
        volcenginesdkcore.Configuration.set_default(self.config)
        self.total=0
        self.voice_list = [] # 获取所有音色
        self.used_voices = ['zh_male_cixingjieshuonan_uranus_bigtts']   # 过滤特殊音色和已经使用的音色，尽量不要重复
        self.filter_voice_info = {} # role_name: voice_type  根据角色信息获得的音色类型


    async def get_voice_list(self, limit:int=50):
        api_instance = volcenginesdkspeechsaasprod.SPEECHSAASPRODApi()
        
        async def smart_selct(page:int, limit:int=50):
            list_speakers_request = volcenginesdkspeechsaasprod.ListSpeakersRequest(
                limit=limit,
                page=page,
                resource_ids=["seed-tts-2.0"],
            )
            try:
                result = await asyncio.to_thread(api_instance.list_speakers, list_speakers_request)
                if result and hasattr(result, 'speakers') and result.speakers:
                    for speaker in result.speakers:
                        self.voice_list.append(speaker.to_dict())
                if result and hasattr(result, 'total') and result.total:
                    self.total = result.total
                    
            except ApiException as e:
                logger.info("Exception when calling api: %s\n" % e)
        
        await smart_selct(page=1)
        logger.info(f'total: {self.total}')

        remain_total = 0 if self.total - limit <= 0 else self.total - limit
        run_cnt = remain_total // limit
        add_num = 1 if remain_total % limit != 0 else 0
        run_cnt += add_num
        logger.info(f'run_cnt: {run_cnt}')

        tasks = [
            smart_selct(page=i+2, limit=limit) 
            for i in range(run_cnt)
        ]

        await asyncio.gather(*tasks)

    async def has_english(self, lines_list: list[str]) -> bool:
        has_english = False
        for lines in lines_list:
            has_english = bool(re.search(r'[a-zA-Z]', lines))
            if has_english:
                break
        return has_english





    async def filter_voices(self, role_voice: GenVoiceParam):
        llm_error_meg = ''
        filter_voices = {}

        has_english = await self.has_english(lines_list=role_voice.lines_list)

        def check_voice_info(voice_type, filter_decs):
            if voice_type is None:
                return True
            if filter_decs is None:
                return True
            if voice_type in self.used_voices:
                return True
            return False
        
        def check_categories(speaker):
            categories = speaker.get('categories', None)
            categories_detail = []
            if isinstance(categories, list):
                continue_flag = True
                for item in categories:
                    categories_detail = item.get('categories', [])
                    if '旁白' in role_voice.role_name:
                        if "通用场景" in categories_detail or "视频配音" in categories_detail:
                            continue_flag = False
                            break
                    else:
                        if "角色扮演" in categories_detail:
                            continue_flag = False
                            break
                if continue_flag:
                    return True
            return False
        
        def check_language(speaker):
            languages = speaker.get('languages', [])
            lang_type_list = []
            for item in languages:
                lang_type = item.get('language', None) 
                if lang_type:
                    lang_type_list.append(lang_type)
            if has_english:
                if 'zh-cn' not in lang_type_list:
                    return True
            if 'zh-cn' not in lang_type_list and 'zh' not in lang_type_list:
                return True
            return False
        
        def check_age(speaker):
            filter_age = '青年'
            if 0 <= role_voice.age < 14:
                filter_age = '儿童'
            if 14 <= role_voice.age < 40:
                filter_age = '青年'
            if 40 <= role_voice.age < 59:
                filter_age = '中年'
            if 59 <= role_voice.age:
                filter_age = '老年'
            if speaker.get('age', '') != filter_age:
                return True
            return False

        def check_gender(speaker):
            filter_gender = '男' if role_voice.gender=='male' else '女'
            if speaker.get('gender', '') != filter_gender:
                return True
            return False


        for speaker in self.voice_list:
            voice_type = speaker.get('voice_type', None)
            filter_decs = speaker.get('description', None)

            if check_voice_info(voice_type, filter_decs):
                continue
            if check_categories(speaker):
                continue
            if check_language(speaker):
                continue
            if check_age(speaker) or check_gender(speaker):
                continue
            filter_voices[voice_type] = filter_decs
        
        if not filter_voices:
            logger.info(f'warning, not find any voices.')
            for speaker in self.voice_list:
                voice_type = speaker.get('voice_type', None)
                filter_decs = speaker.get('description', None)
                if check_voice_info(voice_type, filter_decs) or check_gender(speaker):
                    continue
                filter_voices[voice_type] = filter_decs
                
        if not filter_voices:
            raise Exception('not found any voices.')

        @async_retry_error
        async def llm_select_voice():
            from app.services.llm import voice_model, VOICE_SELECT_PROMPT
            nonlocal llm_error_meg
            try:
                query = VOICE_SELECT_PROMPT.format(
                    target_desc=role_voice.model_dump_json(),
                    voice_dict=filter_voices,
                    error_msg=llm_error_meg
                )
                logger.info(f'select voice query is {query}')
                response = await voice_model.ainvoke(
                    [HumanMessage(query)],
                    config={
                        "configurable": {
                            "temperature": 1.0
                        }
                    }
                )

                if not isinstance(response, SelectVoiceID):
                    raise Exception('返回格式不正确')
                logger.info(f'selected voice type is {response.model_dump()}')

                selected_voice_type = response.selected_voice_type

                if selected_voice_type not in filter_voices.keys():
                    raise Exception('选择的voice_type 不在候选音色列表中，请重新选择。')

                self.used_voices.append(selected_voice_type)
                self.filter_voice_info[role_voice.role_name] = selected_voice_type
            except Exception as e:
                llm_error_meg = f"LLM调用失败: {str(e)}\n详细堆栈:\n{traceback.format_exc()}"
                raise

        await llm_select_voice()


    async def show(self):
        logger.info(f'self total is {self.total}, self voice_list len:{len(self.voice_list)}')
        logger.info(f'last voice: {self.voice_list[-1]}, type is {type(self.voice_list[-1])}')

        # import volcenginesdkspeechsaasprod.models.speaker_for_list_speakers_output.SpeakerForListSpeakersOutput
        with open('voices.json', 'w', encoding='utf-8') as f:
            json.dump(self.voice_list, f, indent=4, ensure_ascii=False)


    async def _gen_request(self, speaker:str, lines: Lines):
        connect_id = str(uuid.uuid4())
        logger.info(f'gen voice resource id: {connect_id}')
        headers = {
            "X-Api-Key": settings.BYTEDANCE_API_KEY,
            "X-Api-Resource-Id": 'seed-tts-2.0',
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        }

        additions = {
            "context_texts":[lines.audio_style],
            "disable_markdown_filter": True
        }
        additions_str = json.dumps(additions)
        logger.info(f'additions_str is {additions_str}')

        payload = {
            "user": {
                "uid": connect_id
            },
            "req_params": {
                "text": lines.text,
                "model": "seed-tts-2.0-expressive",
                "speaker": speaker,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": lines.speed
                },
                "additions": additions_str
            }
        }
        return headers, payload


    async def select_voice_type(self, lines: Lines):
        speaker = self.filter_voice_info.get(lines.role_name, None)

    
    async def dwonload_voice(self, lines_voices: List[Lines], save_dir:str|Path):
        sem = asyncio.Semaphore(MAX_CONCURRENT) # 进程级别，控制celery进程数，防止QPS超  进程*sem <= tts QPS
       
        async def download_worker(lines: Lines, index: int):
            async with sem:
                try:
                    speaker = self.filter_voice_info.get(lines.role_name, None)
                    if speaker is None:
                        raise Exception(f'not find speaker by role {lines.role_name}')
                    file_name = lines.role_name + '_' + str(index) + '.mp3'
                    audio_save_path = Path(save_dir) / file_name
                    headers, payload = await self._gen_request(speaker, lines)
                   
                    duration = await asyncio.to_thread(tts_http_sse_stream, url=url, headers=headers, params=payload, audio_save_path=audio_save_path)
                    lines.audio_path = audio_save_path
                    lines.duration = duration
                    lines.spk_id = speaker
                except Exception as e:
                    logger.exception('dwonload_voice 发生异常')
                    logger.info(f'occur error. {e}')
                    raise e
        
        async with asyncio.TaskGroup() as tg:
            for i, lines in enumerate(lines_voices):
                tg.create_task(download_worker(lines=lines, index=i))
                


if __name__ == '__main__':
    gen_voice = GenVoice()
    asyncio.run(gen_voice.get_voice_list())
    asyncio.run(gen_voice.show())
    
