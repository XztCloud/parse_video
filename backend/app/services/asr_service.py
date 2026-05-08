import base64
import json
from http import HTTPStatus
import time
import uuid

import requests
from ..config import settings


# 辅助函数：将本地文件转换为Base64
def file_to_base64(file_path):
    with open(file_path, 'rb') as file:
        file_data = file.read()  # 读取文件内容
        base64_data = base64.b64encode(file_data).decode('utf-8')  # Base64 编码
    return base64_data


def submit_task(file_path, appid, token):

    #submit_url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    submit_url = "https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/submit"

    task_id = str(uuid.uuid4())

    headers = {
        "X-Api-App-Key": appid,
        "X-Api-Access-Key": token,
        "X-Api-Resource-Id": "volc.bigasr.auc",
        "X-Api-Request-Id": task_id,
        "X-Api-Sequence": "-1"
    }
    try:
        base64_data = file_to_base64(file_path)  # 转换文件为 Base64
    except Exception as e:
        print(f'error, load file to base64. path:{file_path}')
        return None

    request = {
        "user": {
            "uid": "fake_uid"
        },
        "audio": {
            "data": base64_data,
            "format": "wav",
            # "codec": "map3",
            "rate": 16000,
            # "bits": 16,
            "channel": 1
        },
        "request": {
            "model_name": "bigmodel",
            # "model_name": "bigmodel", 
            "enable_channel_split": True, 
            "enable_ddc": True, 
            "enable_speaker_info": True, 
            "enable_punc": True, 
            "enable_itn": True,
            # "enable_itn": True,
            # "enable_punc": True,
            # "enable_ddc": True,
            # "show_utterances": True,
            # "enable_channel_split": True,
            # "vad_segment": True,
            # "enable_speaker_info": True,
            "corpus": {
                # "boosting_table_name": "test",
                "correct_table_name": "",
                "context": ""
            }
        }
    }
    print(f'Submit task id: {task_id}')
    response = requests.post(submit_url, data=json.dumps(request), headers=headers)
    if 'X-Api-Status-Code' in response.headers and response.headers["X-Api-Status-Code"] == "20000000":
        print(f'Submit task response header X-Api-Status-Code: {response.headers["X-Api-Status-Code"]}')
        print(f'Submit task response header X-Api-Message: {response.headers["X-Api-Message"]}')
        x_tt_logid = response.headers.get("X-Tt-Logid", "")
        print(f'Submit task response header X-Tt-Logid: {response.headers["X-Tt-Logid"]}\n')
        return (task_id, x_tt_logid)
    else:
        print(f'Submit task failed and the response headers are: {response.headers}')
        return None
    return task_id


def query_task(task_id, x_tt_logid, appid, token):
    query_url = "https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/query"

    headers = {
        "X-Api-App-Key": appid,
        "X-Api-Access-Key": token,
        "X-Api-Resource-Id": "volc.bigasr.auc",
        "X-Api-Request-Id": task_id,
        "X-Tt-Logid": x_tt_logid  # 固定传递 x-tt-logid
    }

    response = requests.post(query_url, json.dumps({}), headers=headers)

    if 'X-Api-Status-Code' in response.headers:
        print(f'Query task response header X-Api-Status-Code: {response.headers["X-Api-Status-Code"]}')
        print(f'Query task response header X-Api-Message: {response.headers["X-Api-Message"]}')
        print(f'Query task response header X-Tt-Logid: {response.headers["X-Tt-Logid"]}\n')
    else:
        print(f'Query task failed and the response headers are: {response.headers}')
        exit(1)
    return response


# def main():
#     task_id, x_tt_logid = submit_task()
#     while True:
#         query_response = query_task(task_id, x_tt_logid)
#         code = query_response.headers.get('X-Api-Status-Code', "")
#         if code == '20000000':  # task finished
#             print(query_response.json())
#             print("SUCCESS!")
#             exit(0)
#         elif code != '20000001' and code != '20000002':  # task failed
#             print("FAILED!")
#             exit(1)
#         time.sleep(1)
        

def parse_utterances(data):
    result_list = []
    
    # 获取 utterances 列表
    utterances = data.get("result", {}).get("utterances", [])
    all_text = data.get("result", {}).get("text", "")

    for item in utterances:
        # 构造字典
        entry = {
            "speaker": item.get("additions", {}).get("speaker"),
            "start_time": item.get("start_time"),
            "end_time": item.get("end_time"),
            "text": item.get("text")
        }
        result_list.append(entry)
        
    return result_list, all_text


class ASRService:
    @staticmethod
    def transcribe(audio_path: str) -> list[dict] | None:
        # api_key = 'fa794b4b-d446-4e61-82d7-1752eaaf875f'

        appid = "6588537554"
        token = "J-fY9rSthVMfrdS7cCLShmKLv_RwwLk2"
        print(f'appid: {appid}, token: {token}')

        ret = submit_task(audio_path, appid, token)
        if ret is None:
            print('submit_task failed.') 
            return None
        task_id, x_tt_logid  = ret
        while True:
            query_response = query_task(task_id, x_tt_logid, appid, token)
            code = query_response.headers.get('X-Api-Status-Code', "")
            if code == '20000000':  # task finished
                print(query_response.json())
                result, all_text = parse_utterances(query_response.json())
                print(f'result: {result}')
                print(f'all_text: {all_text}')
                print("SUCCESS!")
                return (result, all_text)
            elif code != '20000001' and code != '20000002':  # task failed
                print("FAILED!")
                return None
            time.sleep(1)
