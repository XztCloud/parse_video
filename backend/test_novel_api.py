#!/usr/bin/env python3
"""
小说转剧本 API 测试脚本

使用方法：
1. 启动 FastAPI 应用：python -m uvicorn app.main:app --reload
2. 运行此脚本：python test_novel_api.py
"""

import requests
import json
import time
from pathlib import Path

# 配置
BASE_URL = "http://localhost:8000"
TOKEN = ""  # 需要先登录获取 token

# 测试文件路径
NOVEL_FILE = "/home/xztcloud/.smarttr/workspace/parse_video/香灭.md"


def get_token(email: str, password: str) -> str:
    """登录获取 token"""
    url = f"{BASE_URL}/api/v1/login/access-token"
    data = {
        "username": email,
        "password": password
    }
    response = requests.post(url, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print(f"登录失败: {response.status_code} - {response.text}")
        return None


def upload_novel(file_path: str, title: str) -> dict:
    """上传小说"""
    url = f"{BASE_URL}/api/v1/novel/upload"
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with open(file_path, 'rb') as f:
        files = {'file': (Path(file_path).name, f, 'text/markdown')}
        data = {'title': title}
        response = requests.post(url, headers=headers, files=files, data=data)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"上传失败: {response.status_code} - {response.text}")
        return None


def generate_scripts(novel_id: int, theme: str) -> dict:
    """生成剧本"""
    url = f"{BASE_URL}/api/v1/novel/generate"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "novelId": novel_id,
        "theme": theme,
        "autoRun": False
    }
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"生成失败: {response.status_code} - {response.text}")
        return None


def get_status(novel_id: int) -> dict:
    """获取处理状态"""
    url = f"{BASE_URL}/api/v1/novel/{novel_id}/status"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"获取状态失败: {response.status_code} - {response.text}")
        return None


def get_scripts(novel_id: int) -> list:
    """获取生成的剧本"""
    url = f"{BASE_URL}/api/v1/novel/{novel_id}/scripts"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"获取剧本失败: {response.status_code} - {response.text}")
        return []


def list_all_novels() -> list:
    """列出所有小说"""
    url = f"{BASE_URL}/api/v1/novel/list_all"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"获取列表失败: {response.status_code} - {response.text}")
        return []


def get_db_segments_for_novel(novel_id: int) -> list:
    """直接从数据库查该小说生成的CloneScript分镜（CloneScriptSegment）

    Args:
        novel_id: 小说ID

    Returns:
        CloneScriptSegment记录列表
    """
    import asyncio
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.script import CloneScript, CloneScriptSegment

    async def _query():
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(CloneScriptSegment)
                .join(CloneScript, CloneScriptSegment.script_id == CloneScript.id)
                .where(CloneScript.novel_id == novel_id)
                .order_by(CloneScriptSegment.id)
            )
            return rows.scalars().all()

    return asyncio.run(_query())


def test_segments(novel_id: int):
    """测试分镜落库情况（直接查DB）"""
    print("\n=== 测试分镜（CloneScriptSegment）落库 ===")

    segments = get_db_segments_for_novel(novel_id)
    if not segments:
        print("❌ 未找到该小说的分镜记录")
        return []

    total = len(segments)
    with_dialogue = sum(1 for s in segments if s.dialogue)
    print(f"✅ 生成分镜总数: {total}")
    print(f"   序号: 时间       台词数  情绪/主题")
    for i, seg in enumerate(segments[:10]):
        print(
            f"   {i+1}. {seg.start_time:.1f}-{seg.end_time:.1f}s   "
            f"{len(seg.dialogue) if seg.dialogue else 0}   "
            f"{seg.segment_type or '-'}"
        )
    if total > 10:
        print(f"   ... 还有 {total - 10} 个分镜")
    print(f"   - 含台词分镜数: {with_dialogue}/{total}")
    print(f"   - is_novel标记: {sum(1 for s in segments if s.is_novel)}/{total}")
    return segments


def wait_for_completion(novel_id: int, timeout: int = 300) -> dict:
    """等待处理完成"""
    start_time = time.time()

    while True:
        status = get_status(novel_id)
        if not status:
            return None

        current_status = status.get("status")
        progress = status.get("progress", 0)
        script_count = status.get("script_count", 0)

        print(f"  状态: {current_status} | 进度: {progress}% | 剧本数: {script_count}")

        if current_status in ["DONE", "FAILED"]:
            return status

        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"  超时（{timeout}秒）")
            return status

        time.sleep(3)


def test_upload():
    """测试上传功能"""
    print("\n=== 测试上传小说 ===")

    if not Path(NOVEL_FILE).exists():
        print(f"❌ 测试文件不存在: {NOVEL_FILE}")
        return None

    result = upload_novel(NOVEL_FILE, "香灭测试")
    if result:
        print(f"✅ 上传成功")
        print(f"   小说ID: {result['id']}")
        print(f"   标题: {result['title']}")
        print(f"   状态: {result['status']}")
        return result['id']
    else:
        print("❌ 上传失败")
        return None


def test_generate(novel_id: int):
    """测试生成功能"""
    print("\n=== 测试生成剧本 ===")

    result = generate_scripts(novel_id, "恐怖悬疑")
    if result:
        print(f"✅ 生成任务已启动")
        print(f"   小说ID: {result['novelId']}")
        print(f"   状态: {result['status']}")
        return True
    else:
        print("❌ 生成失败")
        return False


def test_status(novel_id: int):
    """测试状态查询"""
    print("\n=== 测试状态查询 ===")

    status = get_status(novel_id)
    if status:
        print(f"✅ 状态查询成功")
        print(f"   小说ID: {status['id']}")
        print(f"   标题: {status['title']}")
        print(f"   状态: {status['status']}")
        print(f"   进度: {status['progress']}%")
        print(f"   章节数: {status.get('chapter_count', 'N/A')}")
        print(f"   剧本数: {status.get('script_count', 0)}")
        if status.get('error_message'):
            print(f"   错误: {status['error_message']}")
        return status
    else:
        print("❌ 状态查询失败")
        return None


def test_scripts(novel_id: int):
    """测试剧本查询"""
    print("\n=== 测试剧本查询 ===")

    scripts = get_scripts(novel_id)
    if scripts:
        print(f"✅ 查询成功，共 {len(scripts)} 个剧本")
        for i, script in enumerate(scripts[:5]):  # 只显示前5个
            print(f"   {i+1}. ID: {script['id']}")
            print(f"      章节: {script.get('chapter_title', 'N/A')}")
            print(f"      场景: {script.get('scene_index', 'N/A')}")
            print(f"      状态: {script['clone_status']}")
        if len(scripts) > 5:
            print(f"   ... 还有 {len(scripts) - 5} 个剧本")
        return scripts
    else:
        print("❌ 查询失败")
        return []


def test_list_all():
    """测试列表查询"""
    print("\n=== 测试列表查询 ===")

    novels = list_all_novels()
    if novels:
        print(f"✅ 查询成功，共 {len(novels)} 个小说")
        for novel in novels:
            print(f"   - ID: {novel['id']} | 标题: {novel['title']} | 状态: {novel['status']}")
        return novels
    else:
        print("❌ 查询失败")
        return []


def run_full_test():
    """运行完整测试"""
    print("=" * 60)
    print("小说转剧本 API 完整测试")
    print("=" * 60)

    # 检查 token
    if not TOKEN:
        print("\n❌ 错误：请先设置 TOKEN")
        print("   1. 启动应用：python -m uvicorn app.main:app --reload")
        print("   2. 登录获取 token")
        print("   3. 设置 TOKEN 变量")
        return

    # 1. 测试上传
    novel_id = test_upload()
    if not novel_id:
        print("\n❌ 上传失败，测试终止")
        return

    # 2. 测试生成
    if not test_generate(novel_id):
        print("\n❌ 生成失败，测试终止")
        return

    # 3. 等待完成
    print("\n=== 等待处理完成 ===")
    final_status = wait_for_completion(novel_id, timeout=120)
    if final_status and final_status['status'] == 'DONE':
        print(f"\n✅ 处理完成！")
    else:
        print(f"\n⚠️  处理未完成或失败")

    # 4. 测试状态查询
    test_status(novel_id)

    # 5. 测试剧本查询
    test_scripts(novel_id)

    # 5.5. 测试分镜落库（直接查DB）
    test_segments(novel_id)

    # 6. 测试列表查询
    test_list_all()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    # 方式1：手动设置 token
    # TOKEN = "your_token_here"

    # 方式2：自动登录获取 token
    # TOKEN = get_token("your_email@example.com", "your_password")

    # 方式3：从环境变量获取
    import os
    TOKEN = os.getenv("NOVEL_API_TOKEN", "")

    if not TOKEN:
        print("请设置 TOKEN：")
        print("  export NOVEL_API_TOKEN=your_token")
        print("  或修改脚本中的 TOKEN 变量")
        print()
        print("测试脚本已创建，但需要 token 才能运行")
        print("请参考 docs/novel_api_test_guide.md 获取更多信息")
    else:
        run_full_test()
