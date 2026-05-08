#!/bin/bash

# 检查环境变量文件
if [ ! -f .env ]; then
    echo "请先复制 .env.example 为 .env 并填写配置"
    exit 1
fi

# 启动后端服务
echo "启动后端服务..."
docker-compose up -d

# 等待后端启动
echo "等待后端服务启动..."
sleep 5

# 启动前端服务
echo "启动前端服务..."
cd frontend
npm run dev &

echo "服务启动完成！"
echo "前端地址: http://localhost:3000"
echo "后端地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
