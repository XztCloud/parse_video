#!/bin/bash

echo "正在停止所有服务..."

# 1. 通过端口杀进程（最可靠）
echo "按端口清理..."
for port in 8000 3000; do
  pids=$(lsof -t -i:$port 2>/dev/null)
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
    echo "  端口 $port: 已杀掉进程 $pids"
  fi
done

# 2. 关闭前端（next-server / node / npm）
echo "停止前端服务..."
pkill -9 -f "next-server" 2>/dev/null || true
pkill -9 -f "next dev" 2>/dev/null || true
pkill -9 -f "npm run dev" 2>/dev/null || true

# 3. 关闭后端（start-api / uvicorn）
echo "停止后端服务..."
pkill -9 -f "start-api" 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true

# 4. 关闭 Celery（start-worker / celery）
echo "停止 Celery 服务..."
pkill -9 -f "start-worker" 2>/dev/null || true
pkill -9 -f "celery" 2>/dev/null || true

# 5. 清理 setsid 产生的孤儿进程（通过项目路径匹配）
echo "清理残留进程..."
pkill -9 -f "parse_video/.venv/bin" 2>/dev/null || true

echo "所有服务已成功关闭！"
