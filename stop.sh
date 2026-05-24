#!/bin/bash

echo "正在停止所有服务..."

# 1. 关闭前端服务
echo "停止前端服务..."
pkill -f "node.*frontend" || true
pkill -f "npm run dev" || true

# 2. 关闭 Uvicorn 后端服务（直接通过 8000 端口和关键词清理）
echo "停止后端 Uvicorn 服务..."
PID_8000=$(lsof -t -i:8000)
if [ ! -z "$PID_8000" ]; then
    kill -9 $PID_8000 2>/dev/null || true
fi
pkill -f "uvicorn.*app.main:app" || true

# 3. 关闭 Celery 异步任务服务
echo "停止 Celery 服务..."
pkill -f "celery -A celery_app" || true

echo "所有服务已成功关闭！"
