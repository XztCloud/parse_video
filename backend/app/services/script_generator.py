import json
from pathlib import Path

import pandas as pd
from ..config import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

RETRY_MAX=3

def split_by_time_window(
    items: list[dict],
    window_ms: int = 60_000,
    time_key: str = "start_time",
) -> list[list[dict]]:
    """
    将 list[dict] 按照 start_time 所在的时间窗口进行分段。

    时间窗口以 0 为起点，每 window_ms 毫秒为一个窗口：
        [0, 60000), [60000, 120000), [120000, 180000), ...

    每条数据根据其 start_time 落入对应窗口，同一窗口内的数据归入同一个
    list[dict]，最终输出 list[list[dict]]，每个子列表按 start_time 升序排列。

    Args:
        items:     待分段的数据列表，每条 dict 必须包含 time_key 指定的字段。
        window_ms: 时间窗口长度（毫秒），默认 60000（1 分钟）。
        time_key:  用作分段依据的时间字段名，默认 "start_time"。

    Returns:
        分段后的 list[list[dict]]，按窗口起始时间升序排列。

    Examples:
        >>> data = [
        ...     {"start_time": 240,   "text": "A"},
        ...     {"start_time": 1720,  "text": "B"},
        ...     {"start_time": 7000,  "text": "C"},
        ...     {"start_time": 62000, "text": "D"},   # 落入第2个窗口
        ... ]
        >>> split_by_time_window(data)
        [
            [{"start_time": 240, "text": "A"},
             {"start_time": 1720, "text": "B"},
             {"start_time": 7000, "text": "C"}],
            [{"start_time": 62000, "text": "D"}]
        ]
    """
    if not items:
        return []

    # 按 start_time 排序，保证有序
    sorted_items = sorted(items, key=lambda x: x[time_key])

    # 用 dict 收集各窗口的数据，key 为窗口索引
    buckets: dict[int, list[dict]] = {}
    for item in sorted_items:
        t = item[time_key]
        # 兼容秒级浮点数（如 4.0 秒 = 4000 毫秒）
        if isinstance(t, float) and t < 1000:
            t = t * 1000
        window_idx = int(t // window_ms)
        buckets.setdefault(window_idx, []).append(item)

    # 按窗口索引升序输出
    return [buckets[k] for k in sorted(buckets.keys())]


def find_outermost_list(data):
    """
    自动寻找 JSON 结构中最外层的 list。
    如果本身是 list 则直接返回；如果是 dict，则寻找第一个遇到的 list。
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 优先在当前层级寻找 list 类型的 value
        for value in data.values():
            if isinstance(value, list):
                return value
        # 如果当前层没找到，递归向更深层 dict 寻找
        for value in data.values():
            if isinstance(value, dict):
                result = find_outermost_list(value)
                if result is not None:
                    return result
    return None


def json_item_to_markdown(item, level=0):
    """
    递归处理 List 内部的每一个元素，将其转换为带缩进的文本
    """
    md_content = ""
    indent = "  " * level
    
    if isinstance(item, dict):
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                md_content += f"{indent}- **{key}**:\n"
                md_content += json_item_to_markdown(value, level + 1)
            else:
                md_content += f"{indent}- **{key}**: {value}\n"
    elif isinstance(item, list):
        for sub_item in item:
            md_content += json_item_to_markdown(sub_item, level)
    else:
        md_content += f"{indent}- {item}\n"
        
    return md_content


def convert_markdown(ori_data: json) -> str:
    target_list = find_outermost_list(ori_data)
    markdown_text = ""

    if target_list is None:
        print("❌ 错误：在 JSON 中未找到任何 List (数组) 结构！")
        markdown_text = ori_data
    else:
        for index, item in enumerate(target_list):
            print(f'Item {index}: {item}')
            print(f'Type of Item {index}: {type(item)}')
            dialogue = item.get('dialogue', [])
            item['dialogue'] = "<br>".join(f"{item['speaker']}:{item['text']}" for item in dialogue)
            print(f'Processed dialogue for Item {index}: {item["dialogue"]}, type: {type(item["dialogue"])}')

        df = pd.DataFrame(target_list)
        # index=False 表示不把行索引（0, 1, 2...）写进表格
        markdown_table = df.to_markdown(index=False)
        return markdown_table


class ScriptGenerator:
    @staticmethod
    async def generate_script(asr_segments: list[dict], visual_segments: list[dict]) -> list:
        pass

    @staticmethod
    async def llm_generate_script(asr_segments: list[dict], visual_segments: list[dict]) -> list:

        json_example = """
[{
    "start_time": 128000.0,
    "end_time": 132000.0,
    "shot_description": "片段1的描述",
    "dialogue": [
        {"speaker": "2", "text": "哦。"},
        {"speaker": "2", "text": "随便看，我也不知道吃什么。"},
        {"speaker": "3", "text": "又是老问题，中午吃啥？"}
    ],
    "segment_type": "mixed"
},
{
    "start_time": 132000.0,
    "end_time": 136000.0,
    "shot_description": "片段2的描述,
    "dialogue": [
        {"speaker": "2", "text": "别急，我找个人问问。"}
    ],
    "segment_type": "mixed"
}]
"""

        prompt = f"""
你是专业视频脚本分析师。将以下语音识别和镜头分析结果整合为结构化视频脚本。

语音识别结果（带时间戳）：{asr_segments}
镜头分析结果（带时间戳）：{visual_segments}

根据语音识别结果和镜头分析结果，可以根据你的经验适当合并镜头，简化描述，使结果更加简明流畅。

输出JSON格式脚本，每个片段包含：start_time, end_time, shot_description, dialogue(包含{{'speaker':'1', 'text': '...'}}组成的list), segment_type(shot/dialogue/mixed)。按时间顺序合并，时间连续不重叠。
输出示例：
{json_example}
"""
        
        model_name=settings.LLM_NAME
        base_url=settings.LLM_BASE_URL
        api_key=settings.LLM_API_KEY

        llm_kwargs = {
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 20480
        }
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["base_url"] = base_url

        llm = ChatOpenAI(**llm_kwargs)

        messages = [SystemMessage(content=prompt)]
        
        result = []
        last_start_time = max(item['start_time'] for item in visual_segments)
        cnt = 0
        
        while cnt * 60_000 <= last_start_time:
            item_last_start_time = min((cnt+1) * 60_000, last_start_time+1)
            query = f'以start_time为标准，将指定的时间段内（{cnt * 60_000}<=start_time<{item_last_start_time}）的数据，按照指定格式输出json。要json.loads可以解析，不要添加```json```等其他字符'
            retry = 0
            messages.append(HumanMessage(content=query))
            while retry < RETRY_MAX:
                response = llm.invoke(messages)
                content = response.content.strip()
                print(f'content: {content}')
                
                try:
                    result += json.loads(content)
                    break
                except json.JSONDecodeError as e:
                    messages.append(AIMessage(content=content))
                    messages.append(HumanMessage(content=f'json.JSONDecodeError, error is {e}, 重新生成结果让json.load可以解析。'))
                    print(f'json.JSONDecodeError: {e}')
                    retry += 1
                except Exception as e:
                    print(f'Exception: {e}')
                    retry = RETRY_MAX
            if retry == RETRY_MAX:
                print('retry count reached RETRY_MAX! failed.')
                return []

            cnt += 1
        print(f'result: {result}, result type: {type(result)}')

        return result


    @staticmethod
    async def summary_script(script_result: list[dict], output_dir: str | Path) -> list:
        
        folder_path = Path(output_dir)

        # 如果文件夹不存在则创建，parents=True 会自动创建父级目录，exist_ok=True 避免报错
        folder_path.mkdir(parents=True, exist_ok=True)

        result = []

        model_name=settings.LLM_NAME
        base_url=settings.LLM_BASE_URL
        api_key=settings.LLM_API_KEY

        llm_kwargs = {
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 20480
        }
        
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["base_url"] = base_url

        llm = ChatOpenAI(**llm_kwargs)

        prompt=f"""
你是一位专业的短视频导演，精通分析借鉴其他热门短视频脚本。下面是一个待分析的短视频分镜脚本
{script_result}
"""

        messages = [SystemMessage(content=prompt)]

        query = '分析出剧情人物、场景和核心的推广点（如果有的话), 输出markdown格式数据'
        messages.append(HumanMessage(content=query))
        response = llm.invoke(messages)
        content = response.content.strip()
        print(f'content: {content}')
        result.append(content)
        messages.append(content)

        summary_quary = '将script列表中相邻且关联较大的元素进行合并, 并增加plot_tag字段表示合并后段落的主题。按照json格式输出'
        messages.append(summary_quary)

        summary_content = {}
        retry = 0
        while retry < RETRY_MAX:
            response = llm.invoke(messages)
            content = response.content.strip()
            
            print(f'summary_content: {content}')
            
            try:
                summary_content = json.loads(content)
                break
            except json.JSONDecodeError as e:
                messages.append(AIMessage(content=content))
                messages.append(HumanMessage(content=f'json.JSONDecodeError, error is {e}, 重新生成结果让json.load可以解析。'))
                print(f'json.JSONDecodeError: {e}')
                retry += 1
            except Exception as e:
                print(f'Exception: {e}')
                retry = RETRY_MAX
        if retry == RETRY_MAX:
            print('retry count reached RETRY_MAX! failed.')
            summary_content = {}
        print(f'summary_content: {summary_content},  type is {type(summary_content)}')
        markdown_data = convert_markdown(summary_content)
        result.append(markdown_data)

        file_path = folder_path / 'parse_video.md'
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(result[0])
            f.write("\n\n")
            f.write(result[1])
        result.append(str(file_path.absolute()))

        return result



