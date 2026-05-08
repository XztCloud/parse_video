# 前端页面修复 - 需求规格文档

## 问题描述

前端页面只显示两行文字（"视频脚本解析器"标题和"上传视频，自动解析为结构化脚本"描述），缺少所有核心功能组件（视频上传、进度显示、脚本查看等）。

## 根因分析

### 问题1：page.tsx 是静态占位页面
当前 `frontend/src/app/page.tsx` 只包含硬编码的标题和描述文字，没有集成任何业务组件（VideoUploader、ProgressDisplay、ScriptViewer）。

### 问题2：技术栈不一致
- **设计规格**（specs）要求前端使用 **Vue 3 + Element Plus + Vite**
- **实际实现**使用的是 **Next.js (React) + Tailwind CSS**
- 设计规格中的前端组件（VideoUploader.vue、DouyinInput.vue、ScriptTimeline.vue等）全部是Vue组件，无法在Next.js项目中使用

### 问题3：前端功能严重缺失
当前Next.js前端只有：
- 一个静态首页（page.tsx）- 仅两行文字
- 三个组件文件（VideoUploader.tsx、ProgressDisplay.tsx、ScriptViewer.tsx）- 已编写但未在page.tsx中使用
- API封装（api.ts）- 已编写

缺少的功能：
- 视频上传交互流程
- 抖音链接输入
- 解析进度实时展示
- 脚本时间轴展示
- 脚本导出（TXT/SRT/JSON）
- 历史记录列表
- 路由导航

### 问题4：部署方式变更
- 原设计：所有服务通过docker-compose启动
- 现状：postgres和redis在Docker Desktop中，其他服务在Windows中用命令行启动
- docker-compose.yml中仍包含backend、celery_worker、frontend服务定义，需要清理

## 修复方案

### 方案选择：保留Next.js，补全前端功能

**理由：**
1. 当前项目已有Next.js基础代码（package.json、组件文件、API封装），重写为Vue3工作量大
2. Next.js + React + Tailwind CSS 是成熟的技术栈，完全可以实现设计规格中的所有功能
3. 已有的三个React组件（VideoUploader.tsx、ProgressDisplay.tsx、ScriptViewer.tsx）代码质量良好，可直接复用
4. 只需补全page.tsx主页面逻辑和缺失的组件

### 修复内容

1. **重写 page.tsx** - 实现完整的首页，集成视频上传、抖音链接输入、历史记录
2. **新增 DouyinInput 组件** - 抖音链接输入组件
3. **新增 ScriptTimeline 组件** - 脚本时间轴展示组件
4. **新增路由系统** - 使用Next.js App Router实现页面导航
5. **新增进度页和脚本详情页** - 完整的用户流程
6. **更新 next.config.js** - 配置API代理
7. **清理 docker-compose.yml** - 移除backend/frontend/celery_worker服务定义，仅保留postgres和redis
8. **更新 start.sh** - 改为Windows命令行启动方式

## 数据流

```
用户 → 首页(上传/抖音链接) → 进度页(轮询状态) → 脚本详情页(查看/导出)
```

## API对接

前端API已封装在 `src/lib/api.ts`，后端API路由前缀为 `/videos` 和 `/scripts`（无 `/api` 前缀），需确保前端请求路径匹配。
