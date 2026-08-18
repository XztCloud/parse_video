# H3 提示词优化：分镜组合并生成（Ref2VA）

> 模块：`backend/app/services/h3_prompt_optimizer.py`
> 测试：`backend/tests/tests/services/test_h3_prompt_optimizer.py`（纯逻辑单测）
> 手动测试：`backend/tmp_test_h3.py`（真实 LLM，script_id=55）
> 生成日期：2026-08-14

---

## 一、背景

原实现（单分镜模式）为**每个分镜**单独生成一段 H3 提示词：

- 分镜只有 2~4 秒，单镜提示词信息量小，视频生成时切得太碎
- 同一角色/场景资产在多个分镜中重复输入，浪费 token 且标签不一致

新流程改为**按分镜时长合并分镜**：连续若干个分镜总时长小于 15 秒就合并成一组，
一组只生成**一段** H3 六段式提示词；相同资产（同一张角色图/场景图、相同的角色状态）
去重后只输入一次。

## 二、分组算法

两个约束同时生效，任一触发即收组交给 LLM：

1. **时长约束**：`_group_segments(segments, max_duration=15.0)` —— 连续分镜组内
   总时长 < 15 秒；加入下一分镜后总时长 ≥ 15 秒则关闭当前组
2. **参考图数量约束**：`_group_segments_with_images(..., max_images=5)` —— 组内
   参考图片数 ≤ 5 张（视频模型参考图过多效果差）；加入下一分镜后参考图会超过
   5 张则**立即收组，即使时长远不足 15 秒也不再合并**

- 参考图计数与 `_build_group_input` 的分配规则一致：场景图（仅 `use_scene_image=True` 时）
  + 可见角色图，按 `(category, id)` 去重（同一资产跨分镜只算 1 张）
- 单个分镜自身超过任一上限时独立成组（无法再拆分）
- 阈值常量：`GROUP_MAX_DURATION = 15.0`、`GROUP_MAX_IMAGES = 5`（均可调）

### script_id=55 实测分组（14 个分镜，总时长 39.3s）

**默认（use_scene_image=False）—— 3 组：**

| 组 | 分镜 id | 时间区间 | 时长 | 参考图 |
|---|---|---|---|---|
| 1 | 144,145,146,147,148 | 0.0 ~ 12.4s | 12.4s | 5 张（5 角色） |
| 2 | 149,150,151,152 | 12.4 ~ 25.8s | 13.4s | 2 张（秦王+谋将） |
| 3 | 153,154,155,156,157 | 25.8 ~ 39.3s | 13.5s | 4 张 |

**use_scene_image=True —— 拆成 5 组（场景图计入后触发图片上限）：**

| 组 | 分镜 id | 时长 | 参考图 |
|---|---|---|---|
| 1 | 144 | 2.0s | 3 张（远山场景 + 国风男女） |
| 2 | 145,146,147,148,149 | 14.0s | 4 张 |
| 3 | 150,151,152,153 | 12.3s | 3 张 |
| 4 | 154,155,156 | 8.0s | 3 张 |
| 5 | 157 | 3.0s | 3 张 |

> 带场景图时组 1/组 5 只剩 1 个分镜：因为下一分镜会引入新场景/角色图，参考图
> 数将超过 5 张，按规则立即收组。

## 三、合并输入 JSON 结构（每组一次）

```json
{
  "duration_budget": 12.4,
  "shots": [
    {
      "start_time": 0.0,
      "end_time": 2.0,
      "scene_name": "开篇展示场景：云雾奇峰远山",
      "shot_type": "远景",
      "shot_description": "云雾缭绕的奇峰远山……",
      "dialogue": [{"role_name": "旁白", "lines": "……", "audio_style": "沉稳"}],
      "role_view_info": [{"role_name": "秦王", "position": "居中", "action": "端坐", "emotion": "威严"}]
    },
    { "...第二个镜头..." }
  ],
  "refer_image": "场景参考 <Picture 1>（核心主场景：中式古典秦殿）；角色参考 <Picture 2>（秦王）"
}
```

要点：

- `duration_budget`：该组目标总时长，提示词时间轴必须与其吻合
- `shots[].start_time / end_time`：**组内相对时间**（第一镜从 0 开始），LLM 直接据此标注 `[Shot N] At MM:SS.mmm`
- `refer_image`：参考图片清单，每个资产只列一次

## 四、资产去重规则（相同资产不重复输入）

1. **参考图片按 `(category, id)` 去重**：同一张场景图/角色图在组内多个分镜出现时，
   只分配一次 `<Picture N>`（编号复用），`refer_image` 只列一次，`image_map` 无重复
2. **场景图开关 `use_scene_image`**（默认 `False`）：为 False 时不将场景图作为参考
   输入（`refer_image` / `image_map` 不含场景，场景名仍以文字保留在 shots 中）；
   为 True 时才把场景图作为 `<Picture N>` 参考
3. **角色状态按 `(role_name, position, action, emotion)` 全组去重**：与前面镜头完全相同的
   角色状态不重复输入（角色连续性由 LLM 推断）；状态变化时仍会重新出现
4. **台词（dialogue）全部保留**：这是脚本内容，不属"资产"，不可丢句
5. **画外音**（`visibility != "visible"`）：进入 dialogue 但不出现在 role_view_info，
   不分配 `<Picture N>`

返回的 `image_map`（供后续 ComfyUI 上传参考图使用，**值直接是该图片的文件路径**）：

```json
[{"Picture 1": "/path/to/backend/uploads/clone_55/核心主场景：中式古典秦殿_0.png"},
 {"Picture 2": "/path/to/backend/uploads/clone_55/古风秦王_0.png"}]
```

## 五、LLM 输出要求（H3 六段式，Ref2VA）

系统提示词 `H3_SYSTEM_PROMPT`（已更新为多镜版本），要求：

1. `subject_definitions` — 用 `<Picture N>` / `<Subject N>` 定义参考内容，同一资产编号全程一致
2. `summary` — 英文一句，带 `[reference generation]` 前缀
3. `retention_analysis` — 每个标签的保留方式（fully_preserved / partially_preserved / attribute_transfer / weak_reference）
4. `detailed_description` — 按时间顺序逐镜描述整组：第一镜 `[Shot 1]`（00:00 开始），
   后续 `[Shot N] At MM:SS.mmm`（组内相对切点）；说话人稳定编号 `(S1)(S2)`；对话 `<d>[Chinese] ...</d>`
5. `overall_soundscape` — 整体环境音
6. `non_diegetic_music` — 背景音乐，无则 N/A

规则：必须完整覆盖输入中所有镜头与台词、不编造不在场人物、标签一致不新增定义。

## 六、接口

```python
from app.services.h3_prompt_optimizer import optimize_script_prompts
results = await optimize_script_prompts(script_id=55)
# 参数：
#   script_id       复刻脚本 id
#   merge_segments  是否合并连续分镜，默认 False（不合并，每个分镜独立一段提示词，
#                   参考图最少，适合本地显存小的机器跑 ComfyUI）；
#                   True 时按 时长(<15s) + 参考图片数(<=5) 合并
#   use_scene_image 是否将场景图作为参考输入，默认 False（不传场景图作 <Picture N> 参考；
#                   场景名仍以文字保留在 shots 中）；True 时才把场景图加入参考
#   on_group        可选回调，每组生成完立即调用，用于边生成边落盘
#
# 合并规则（仅 merge_segments=True 时生效，模块常量可调）：
#   GROUP_MAX_DURATION = 15.0   组内总时长 < 15s
#   GROUP_MAX_IMAGES   = 5      组内参考图片数 <= 5，超出立即收组不再合并
```

### merge_segments 两种模式实测对比（script_id=55，默认不带场景图）

| 模式 | 组数 | 每组参考图 | 适用场景 |
|---|---|---|---|
| `False`（默认） | 14（每分镜一组） | 1~3 张 | 本地显卡带不动多参考图，逐镜生成 |
| `True` | 3 组 | 2~5 张 | 显卡够用，每段视频更长更连贯 |

每个元素：

```python
{
    "group_index": 1,
    "segment_ids": [144, 145, 146, 147, 148],
    "start_time": 0.0,
    "end_time": 12.4,
    "duration": 12.4,
    "prompt": "subject_definitions: ...",
    "image_map": [{"Picture 1": "/path/to/backend/uploads/clone_55/古风秦王_0.png"}]
}
```

## 七、测试

- **纯逻辑单测**（不调 LLM/DB）：`backend/tests/tests/services/test_h3_prompt_optimizer.py`，18 个用例
  - 分组：script55 时长序列 → 3 组；单镜超 15s 独立成组；空输入；单分镜
  - 合并输入：图片去重、相对时间、角色状态去重、台词全保留、画外音过滤
- **真实 LLM 测试**：`backend/tmp_test_h3.py`（script_id=55），结果见下节及
  `docs/h3_results_script55.json`

> ⚠️ 注意：`backend/tests/conftest.py` 的会话级 `db` 夹具（autouse）会在结束时清空
> Video/User/VoiceInfoCollect 表。跑会连真实库的测试前请保持它处于注释状态。

## 八、script_id=55 实测结果

完整提示词文本见 **`docs/h3_results_script55.json`**（边生成边落盘）。

### 已生成 2/3 组（2026-08-14 实测）

**组 1**（segment_ids=144-148，0~12.4s，开篇远山 + 秦殿开场）——2665 字符：

```text
subject_definitions:
<Subject 1> 是 <Picture 1> 中的场景，即云雾缭绕的奇峰远山，保持其青灰色调与山峦形态。
<Subject 2> 是 <Picture 2> 中的人物，即25岁国风男青年，保持其面部特征与服饰。
...（共 7 个 Subject：开篇场景/男女主持/秦殿/使臣/秦王/质问王侯）

summary:
[reference generation] This video depicts a humorous ancient Chinese court scene where a Qin
emperor desperately wants a cup of instant noodles...

retention_analysis:
<Subject 1>（<Picture 1> 开篇场景）：fully_preserved ...
...

detailed_description:
[Shot 1] 00:00 - 00:02.000  中景推镜。...（男女主持持方便面，背景为云雾奇峰远山）
[Shot 2] At 00:02.000 - 00:05.900  ...（S1）使臣：<d>[Chinese] 珍宝若被强夺，不如当场摔碎。</d>
[Shot 3] At 00:05.900 - 00:08.400  ...（S2）秦王：<d>[Chinese] 不要摔，我要统一方便面！</d>
[Shot 4] At 00:08.400 - 00:10.400  ...（S3）王侯：<d>[Chinese] 那之前说好的15个城池。</d>
[Shot 5] At 00:10.400 - 00:12.400  ...（S2）秦王：<d>[Chinese] 给给给，现在就给。</d>

overall_soundscape:
山景风声鸟鸣 → 秦殿朝堂低语声、脚步声、衣料摩擦声、方便面盒挤压声。

non_diegetic_music:
N/A
```

**组 2**（segment_ids=149-152，12.4~25.8s，秦殿吃面剧情）——1824 字符：

```text
subject_definitions:
<Subject 1> 核心主场景秦殿 / <Subject 2> 古风秦王 / <Subject 3> 黑衣劲装谋将

summary:
[reference generation] A Chinese ancient palace scene from Picture 1, featuring the emperor
from Picture 2 and the strategist from Picture 3 enjoying instant noodles...

detailed_description:
[Shot 1]（00:00）秦王（S1）特写吃面：<d>[Chinese] 一口统一，整块更好吃。</d>
[Shot 2] At 00:03.600 谋将（S2）俯身盯地图
[Shot 3] At 00:06.600 谋将（S2）吃面：<d>[Chinese] 别争了，整块更好吃。</d>
[Shot 4] At 00:10.900 谋将（S2）回味：<d>[Chinese] 整块真肉果然好吃。</d>

non_diegetic_music:
低沉的古琴与编钟垫乐，秦王吃面轻快、谋将看图紧张、回味舒缓。
```

### 组 3 未生成（外部 API 挂起）

**组 3**（segment_ids=153-157，25.8~39.3s，收尾场景 + 开篇远山收束）：多次调用火山引擎 Ark
（`deepseek-v4-flash` / coding/v3）均**连接后服务端 300s 不返回**而超时（重试 3 次亦然）。
分组与输入构造本身正常（见下），属外部 API 间歇性挂起，非本模块逻辑问题。

组 3 的合并输入摘要（供重跑参考）：

```json
{
  "duration_budget": 13.5,
  "shots": [5 个镜头：收尾场景：云雾奇峰山顶 ×4 + 开篇展示场景：云雾奇峰远山 ×1],
  "refer_image": "场景参考 <Picture 1>（收尾场景：云雾奇峰山顶）；场景参考 <Picture 2>（开篇展示场景：云雾奇峰远山）"
}
```

> 重跑组 3：`cd backend && source ../.venv/bin/activate && python tmp_test_h3.py`
> （脚本会重新生成全部 3 组；若只想补组 3，可临时把 `optimize_script_prompts` 的
> `groups` 切片为 `groups[2:]`。）

### 已知环境问题：Ark API 间歇性挂起

实测规律（2026-08-14）：对 `ark.cn-beijing.volces.com/api/coding/v3` 的调用，
短请求 2.8s 返回，H3 大 prompt 生成 55s~2min 返回，但**偶发连接建立后服务端长时间
（>5min）不响应**，重试同样命中。用户反馈火山 coding plan 对**并发不友好**：
务必保持请求**严格串行**（当前实现即一次一个、await 完成后才发下一个）。
模块内已加 `LLM_CALL_TIMEOUT=300s + 3 次重试` 兜底。
