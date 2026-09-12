# 小说转剧本 API 测试指南

## 🚀 启动应用

```bash
# 1. 进入后端目录
cd /home/xztcloud/.smarttr/workspace/parse_video/backend

# 2. 安装依赖（如果还没有）
pip install -r requirements.txt

# 3. 启动 FastAPI 应用
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. 启动 Celery Worker（另一个终端）
celery -A app.celery_app worker --loglevel=info
```

## 📋 API 端点列表

### 1. 上传小说

**端点**: `POST /api/v1/novel/upload`

**请求**:
```bash
curl -X POST "http://localhost:8000/api/v1/novel/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/香灭.md" \
  -F "title=香灭"
```

**响应示例**:
```json
{
  "id": 1,
  "title": "香灭",
  "chapter_count": 8,
  "status": "PENDING",
  "created_at": "2026-08-20T12:00:00"
}
```

### 2. 生成剧本

**端点**: `POST /api/v1/novel/generate`

**请求**:
```bash
curl -X POST "http://localhost:8000/api/v1/novel/generate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "novelId": 1,
    "theme": "恐怖悬疑",
    "autoRun": false,
    "requirements": {
      "style": "暗黑风格",
      "target_audience": "年轻人"
    }
  }'
```

**响应示例**:
```json
{
  "novelId": 1,
  "status": "PROCESSING",
  "clone_script_ids": []
}
```

### 3. 查看处理状态

**端点**: `GET /api/v1/novel/{novel_id}/status`

**请求**:
```bash
curl -X GET "http://localhost:8000/api/v1/novel/1/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例**:
```json
{
  "id": 1,
  "title": "香灭",
  "status": "PROCESSING",
  "progress": 50,
  "error_message": null,
  "chapter_count": 8,
  "script_count": 4,
  "created_at": "2026-08-20T12:00:00"
}
```

### 4. 查看生成的剧本

**端点**: `GET /api/v1/novel/{novel_id}/scripts`

**请求**:
```bash
curl -X GET "http://localhost:8000/api/v1/novel/1/scripts" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例**:
```json
[
  {
    "id": 1,
    "clone_theme": "恐怖悬疑",
    "clone_status": "PLOT_DONE",
    "clone_progress": 100,
    "source_type": "NOVEL",
    "chapter_index": 1,
    "chapter_title": "第1章 新电梯",
    "scene_index": 0
  },
  {
    "id": 2,
    "clone_theme": "恐怖悬疑",
    "clone_status": "PLOT_DONE",
    "clone_progress": 100,
    "source_type": "NOVEL",
    "chapter_index": 1,
    "chapter_title": "第1章 新电梯",
    "scene_index": 1
  }
]
```

### 5. 列出所有小说

**端点**: `GET /api/v1/novel/list_all`

**请求**:
```bash
curl -X GET "http://localhost:8000/api/v1/novel/list_all" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例**:
```json
[
  {
    "id": 1,
    "title": "香灭",
    "chapter_count": 8,
    "status": "DONE",
    "progress": 100,
    "created_at": "2026-08-20T12:00:00"
  }
]
```

## 🔐 认证

所有 API 端点都需要 JWT token 认证。请先通过登录接口获取 token：

```bash
# 登录获取 token
curl -X POST "http://localhost:8000/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_email@example.com&password=your_password"
```

## 📊 完整测试流程

### 流程 1: 上传并生成剧本

```bash
# Step 1: 上传小说
curl -X POST "http://localhost:8000/api/v1/novel/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@香灭.md" \
  -F "title=香灭"

# Step 2: 生成剧本（使用返回的 novelId）
curl -X POST "http://localhost:8000/api/v1/novel/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"novelId": 1, "theme": "恐怖悬疑"}'

# Step 3: 轮询查看状态
while true; do
  STATUS=$(curl -s "http://localhost:8000/api/v1/novel/1/status" \
    -H "Authorization: Bearer $TOKEN")
  echo "$STATUS"
  
  # 检查是否完成
  if echo "$STATUS" | grep -q '"status":"DONE"'; then
    break
  fi
  
  sleep 5
done

# Step 4: 查看生成的剧本
curl -X GET "http://localhost:8000/api/v1/novel/1/scripts" \
  -H "Authorization: Bearer $TOKEN"
```

### 流程 2: 批量测试

```bash
# 创建测试脚本
cat > test_novel_api.sh << 'EOF'
#!/bin/bash

# 配置
BASE_URL="http://localhost:8000"
TOKEN="YOUR_TOKEN_HERE"

echo "=== 测试小说转剧本 API ==="

# 1. 上传小说
echo "1. 上传小说..."
UPLOAD_RESULT=$(curl -s -X POST "$BASE_URL/api/v1/novel/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@香灭.md" \
  -F "title=香灭测试")

NOVEL_ID=$(echo $UPLOAD_RESULT | jq -r '.id')
echo "   小说ID: $NOVEL_ID"

# 2. 生成剧本
echo "2. 生成剧本..."
GENERATE_RESULT=$(curl -s -X POST "$BASE_URL/api/v1/novel/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"novelId\": $NOVEL_ID, \"theme\": \"恐怖悬疑\"}")

echo "   生成结果: $GENERATE_RESULT"

# 3. 等待完成
echo "3. 等待处理完成..."
while true; do
  STATUS=$(curl -s "$BASE_URL/api/v1/novel/$NOVEL_ID/status" \
    -H "Authorization: Bearer $TOKEN")
  
  CURRENT_STATUS=$(echo $STATUS | jq -r '.status')
  PROGRESS=$(echo $STATUS | jq -r '.progress')
  SCRIPT_COUNT=$(echo $STATUS | jq -r '.script_count')
  
  echo "   状态: $CURRENT_STATUS | 进度: $PROGRESS% | 剧本数: $SCRIPT_COUNT"
  
  if [ "$CURRENT_STATUS" = "DONE" ] || [ "$CURRENT_STATUS" = "FAILED" ]; then
    break
  fi
  
  sleep 3
done

# 4. 查看结果
echo "4. 查看生成的剧本..."
SCRIPTS=$(curl -s "$BASE_URL/api/v1/novel/$NOVEL_ID/scripts" \
  -H "Authorization: Bearer $TOKEN")

echo "$SCRIPTS" | jq '.[] | {id, chapter_title, scene_index, clone_status}'

echo "=== 测试完成 ==="
EOF

chmod +x test_novel_api.sh
echo "测试脚本已创建: test_novel_api.sh"
```

## 🌐 Swagger UI 测试

启动应用后，直接访问 Swagger UI 进行交互式测试：

1. 打开浏览器访问: `http://localhost:8000/docs`
2. 点击右上角的 "Authorize" 按钮
3. 输入 token: `Bearer YOUR_TOKEN`
4. 展开 `/novel` 端点
5. 点击 "Try it out" 进行测试

## 📝 注意事项

1. **异步处理**: 生成剧本是异步任务，需要轮询状态接口查看进度
2. **文件大小**: 上传的文件不能超过 `MAX_UPLOAD_SIZE`（默认 500MB）
3. **支持格式**: 仅支持 `.txt`, `.md`, `.markdown` 格式
4. **Token 过期**: Token 有过期时间（默认 60 分钟），过期后需要重新登录
5. **并发限制**: API 有速率限制，避免频繁调用

## 🔧 常见问题

### Q: 上传失败怎么办？
A: 检查文件格式是否正确（.txt/.md），文件是否为 UTF-8 编码

### Q: 生成剧本很慢？
A: 这是正常的，因为需要调用 LLM 分析小说内容。根据小说长度，可能需要几分钟到几十分钟

### Q: 如何查看详细错误信息？
A: 检查 `error_message` 字段，或查看服务器日志

### Q: 能否同时生成多个剧本？
A: 可以，每个生成请求都是独立的 Celery 任务

## 📚 相关文档

- [小说转剧本测试报告](./novel_to_script_test_results.md)
- [实现计划](../.claude/plans/clone-scripts-clone-script-segments-2-m-giggly-book.md)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
