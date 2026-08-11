#!/bin/bash

set -e

# 项目根目录（脚本所在目录），防止从任意位置运行时路径错乱
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 加载 nvm（前端需要 node/npm，由 nvm 管理）
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    . "$NVM_DIR/nvm.sh"
else
    echo "⚠️  未找到 nvm ($NVM_DIR/nvm.sh)，前端可能无法启动"
fi

# 检查环境变量文件
if [ ! -f .env ]; then
    echo "请先复制 .env.example 为 .env 并填写配置"
    exit 1
fi

# 启动数据库服务（只需 postgres 和 redis 两个基础设施容器）
echo "启动数据库服务..."
docker compose up -d postgres redis

# 等待数据库动
echo "等待数据库服务启动..."
sleep 5

# 启动后端服务
echo "启动后端服务..."
source .venv/bin/activate
cd backend
setsid nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > ../uvicorn.log 2>&1 < /dev/null &

# 启动celery服务
echo "启动celery服务..."
setsid nohup start-worker > /dev/null 2>&1 < /dev/null &

# 回到根目录（防止路径层级错乱）
cd ..
sleep 2

# 启动前端服务
echo "启动前端服务..."
cd frontend
setsid nohup npm run dev > ../frontend.log 2>&1 < /dev/null &

echo "服务启动完成！"
echo "前端地址: http://localhost:3000"
echo "后端地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo "查看后端日志: tail -f backend/uvicorn.log"
echo "查看 Celery 日志: tail -f backend/LOGS/celery.log"
