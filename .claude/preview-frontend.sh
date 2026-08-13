#!/bin/bash
# 桌面应用 Browser preview 用来启动前端 dev server 的 wrapper 脚本
# 桌面应用 (Windows) 通过 wsl 调用此脚本，避免复杂的 shell 引号转义
export PATH="/home/xztcloud/.nvm/versions/node/v20.20.2/bin:$PATH"
cd /home/xztcloud/.smarttr/workspace/parse_video/frontend || exit 1
# 端口由 launch.json / preview 通过 PORT 环境变量控制
exec npm run dev
