#!/bin/bash

# 检查环境变量文件
if [ ! -f .env ]; then
    echo "请先复制 .env.example 为 .env 并填写配置"
    exit 1
fi

# 启动后端服务
echo "启动数据库服务..."
docker-compose up -d

# 等待数据库动
echo "等待数据库服务启动..."
sleep 5

# 启动后端服务
# echo "启动后端服务..."
# osascript -e 'tell app "Terminal" to do script "cd '$(pwd)'/backend && source ../.venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"'

source .venv/bin/activate
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > ../uvicorn.log 2>&1 &

# 启动celery服务
echo "启动celery服务..."
celery -A celery_app.celery_app worker --loglevel=info > ../celery.log 2>&1 &

# 回到根目录（防止路径层级错乱）
cd ..

# 启动前端服务
echo "启动前端服务..."
cd frontend
npm run dev > ../frontend.log 2>&1 &

echo "服务启动完成！"
echo "前端地址: http://localhost:3000"
echo "后端地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo "查看后端日志: tail -f backend/uvicorn.log"
echo "查看 Celery 日志: tail -f celery.log"
