import json
from ..config import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


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



class ScriptGenerator:
    @staticmethod
    async def generate_script(asr_segments: list[dict], visual_segments: list[dict]) -> list:

        json_example = """
[{
    "start_time": 128000.0,
    "end_time": 132000.0,
    "shot_description": "画面1点描述",
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
    "shot_description": "画面2的描述,
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

输出JSON格式脚本，每个片段包含：start_time, end_time, shot_description, dialogue(包含{{'speaker':'1', 'text': '...'}}组成的list), segment_type(shot/dialogue/mixed)。按时间顺序合并，时间连续不重叠。
输出示例：
{json_example}
"""
        
        model_name="doubao-seed-2.0-pro"
        base_url="https://ark.cn-beijing.volces.com/api/coding/v3"
        api_key="ebd2645e-7e6a-4235-bdf0-7ab08befc4b1"

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
        RETRY_MAX=3
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

        # response = Generation.call(model="qwen-plus", prompt=prompt, result_format="message")
        # if response.status_code == 200:
        #     content = response.output.choices[0].message.content
        #     try:
        #         return json.loads(content)
        #     except json.JSONDecodeError:
        #         return {"raw_script": content, "segments": []}
        # return {"segments": []}