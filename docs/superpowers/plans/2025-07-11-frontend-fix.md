# 前端页面修复 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复前端页面只显示两行文字的问题，补全所有核心功能组件和页面路由，使前端完整可用。

**Architecture:** 保留现有Next.js + React + Tailwind CSS技术栈，补全page.tsx主页面逻辑，新增缺失组件（DouyinInput、ScriptTimeline），使用Next.js App Router实现路由导航，配置API代理对接后端。

**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS, Axios, lucide-react

---

## 文件结构

```
frontend/src/
├── app/
│   ├── globals.css          (修改: 优化样式)
│   ├── layout.tsx           (保留: 无需修改)
│   ├── page.tsx             (重写: 首页-上传/抖音/历史记录)
│   ├── progress/
│   │   └── [id]/
│   │       └── page.tsx     (新增: 解析进度页)
│   └── script/
│       └── [videoId]/
│           └── page.tsx     (新增: 脚本详情页)
├── components/
│   ├── VideoUploader.tsx    (保留: 已有)
│   ├── DouyinInput.tsx      (新增: 抖音链接输入)
│   ├── ProgressDisplay.tsx  (保留: 已有)
│   ├── ScriptTimeline.tsx   (新增: 脚本时间轴)
│   └── ScriptViewer.tsx     (保留: 已有)
├── lib/
│   └── api.ts               (修改: 修复API路径和新增接口)
next.config.js               (修改: 添加API代理)
```

---

### Task 1: 修复API封装和Next.js配置

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/next.config.js`

- [ ] **Step 1: 修复api.ts - 添加缺失的API接口**

当前api.ts缺少视频列表接口和抖音解析接口，且API路径需要与后端路由匹配（后端路由前缀为`/videos`和`/scripts`，无`/api`前缀）。

```typescript
import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  timeout: 30000,
});

export interface VideoUploadResponse {
  id: number;
  filename: string;
  status: string;
  progress: number;
}

export interface VideoStatusResponse {
  id: number;
  filename: string;
  status: string;
  progress: number;
  error_message?: string;
}

export interface VideoListItem {
  id: number;
  filename: string;
  status: string;
  progress: number;
  error_message?: string;
}

export interface ScriptSegment {
  id: number;
  start_time: number;
  end_time: number;
  shot_description: string;
  dialogue: string;
  segment_type: string;
}

export interface ScriptResponse {
  id: number;
  video_id: number;
  content: any;
  segments: ScriptSegment[];
}

export const uploadVideo = async (file: File): Promise<VideoUploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post<VideoUploadResponse>("/videos/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const parseDouyin = async (url: string): Promise<VideoUploadResponse> => {
  const response = await api.post<VideoUploadResponse>("/videos/douyin", { url });
  return response.data;
};

export const getVideoStatus = async (videoId: number): Promise<VideoStatusResponse> => {
  const response = await api.get<VideoStatusResponse>(`/videos/${videoId}/status`);
  return response.data;
};

export const listVideos = async (skip: number = 0, limit: number = 20): Promise<VideoListItem[]> => {
  const response = await api.get<VideoListItem[]>("/videos/", { params: { skip, limit } });
  return response.data;
};

export const getScript = async (videoId: number): Promise<ScriptResponse> => {
  const response = await api.get<ScriptResponse>(`/scripts/${videoId}`);
  return response.data;
};

export const exportScript = async (videoId: number): Promise<Blob> => {
  const response = await api.get(`/scripts/${videoId}/export`, { responseType: "blob" });
  return response.data;
};
```

- [ ] **Step 2: 修改next.config.js - 添加API代理**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
```

- [ ] **Step 3: 验证配置**

Run: `cd parse_video/frontend && cat next.config.js`
Expected: 文件包含rewrites配置

---

### Task 2: 新增DouyinInput组件

**Files:**
- Create: `frontend/src/components/DouyinInput.tsx`

- [ ] **Step 1: 创建抖音链接输入组件**

```tsx
"use client";

import { useState } from "react";
import { parseDouyin } from "@/lib/api";

interface DouyinInputProps {
  onParseSuccess: (videoId: number) => void;
}

export default function DouyinInput({ onParseSuccess }: DouyinInputProps) {
  const [url, setUrl] = useState("");
  const [isParsing, setIsParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleParse = async () => {
    if (!url.trim()) {
      setError("请输入抖音分享链接");
      return;
    }
    setIsParsing(true);
    setError(null);
    try {
      const result = await parseDouyin(url.trim());
      onParseSuccess(result.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || "解析失败，请重试");
    } finally {
      setIsParsing(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="flex gap-2">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="请输入抖音分享链接"
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
          onKeyDown={(e) => e.key === "Enter" && handleParse()}
        />
        <button
          onClick={handleParse}
          disabled={isParsing}
          className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50"
        >
          {isParsing ? "解析中..." : "解析"}
        </button>
      </div>
      {error && <div className="mt-2 text-red-500 text-sm text-center">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 2: 验证组件文件创建**

Run: `cd parse_video/frontend && cat src/components/DouyinInput.tsx | head -5`
Expected: 文件存在且包含"use client"

---

### Task 3: 新增ScriptTimeline组件

**Files:**
- Create: `frontend/src/components/ScriptTimeline.tsx`

- [ ] **Step 1: 创建脚本时间轴组件**

```tsx
"use client";

import { ScriptSegment } from "@/lib/api";

interface ScriptTimelineProps {
  segments: ScriptSegment[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export default function ScriptTimeline({ segments }: ScriptTimelineProps) {
  if (segments.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无脚本片段</div>;
  }

  return (
    <div className="space-y-4">
      {segments.map((seg) => (
        <div key={seg.id} className="relative pl-8 pb-6 border-l-2 border-blue-200 last:border-l-0 last:pb-0">
          <div className="absolute left-[-9px] top-0 w-4 h-4 rounded-full bg-blue-500 border-2 border-white" />
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-500 font-mono">
                {formatTime(seg.start_time)} - {formatTime(seg.end_time)}
              </span>
              <span className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-600">
                {seg.segment_type === "shot"
                  ? "镜头"
                  : seg.segment_type === "dialogue"
                  ? "台词"
                  : "混合"}
              </span>
            </div>
            {seg.shot_description && (
              <p className="text-gray-700 mb-1">
                <span className="font-medium text-gray-900">镜头：</span>
                {seg.shot_description}
              </p>
            )}
            {seg.dialogue && (
              <p className="text-gray-700">
                <span className="font-medium text-gray-900">台词：</span>
                {seg.dialogue}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 验证组件文件创建**

Run: `cd parse_video/frontend && cat src/components/ScriptTimeline.tsx | head -5`
Expected: 文件存在且包含"use client"

---

### Task 4: 重写首页 page.tsx

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: 重写首页 - 集成视频上传、抖音输入、历史记录**

```tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import VideoUploader from "@/components/VideoUploader";
import DouyinInput from "@/components/DouyinInput";
import { listVideos, VideoListItem } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"upload" | "douyin">("upload");
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchVideos = async () => {
    setLoading(true);
    try {
      const data = await listVideos();
      setVideos(data);
    } catch {
      // 静默处理，历史记录加载失败不影响主功能
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVideos();
  }, []);

  const handleUploadSuccess = (videoId: number) => {
    router.push(`/progress/${videoId}`);
  };

  const handleParseSuccess = (videoId: number) => {
    router.push(`/progress/${videoId}`);
  };

  const statusLabel = (s: string) => {
    const map: Record<string, string> = {
      pending: "等待中",
      processing: "解析中",
      done: "已完成",
      failed: "失败",
    };
    return map[s] || s;
  };

  const statusColor = (s: string) => {
    const map: Record<string, string> = {
      pending: "bg-gray-100 text-gray-600",
      processing: "bg-yellow-100 text-yellow-700",
      done: "bg-green-100 text-green-700",
      failed: "bg-red-100 text-red-700",
    };
    return map[s] || "bg-gray-100 text-gray-600";
  };

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900">视频脚本解析器</h1>
          <p className="text-sm text-gray-500 mt-1">上传视频或输入抖音链接，自动解析为结构化脚本</p>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Tab切换 */}
        <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
          <button
            onClick={() => setActiveTab("upload")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === "upload"
                ? "bg-white text-blue-600 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            本地上传
          </button>
          <button
            onClick={() => setActiveTab("douyin")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === "douyin"
                ? "bg-white text-blue-600 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            抖音链接
          </button>
        </div>

        {/* 内容区 */}
        <div className="bg-white rounded-xl shadow-sm border p-8 mb-8">
          {activeTab === "upload" ? (
            <VideoUploader onUploadSuccess={handleUploadSuccess} />
          ) : (
            <DouyinInput onParseSuccess={handleParseSuccess} />
          )}
        </div>

        {/* 历史记录 */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900">历史记录</h2>
            <button
              onClick={fetchVideos}
              className="text-sm text-blue-500 hover:text-blue-600"
            >
              刷新
            </button>
          </div>

          {loading ? (
            <div className="text-center py-8 text-gray-500">加载中...</div>
          ) : videos.length === 0 ? (
            <div className="text-center py-8 text-gray-400">暂无记录</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-gray-500">
                    <th className="pb-3 font-medium">视频名称</th>
                    <th className="pb-3 font-medium w-24">状态</th>
                    <th className="pb-3 font-medium w-24">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((video) => (
                    <tr key={video.id} className="border-b last:border-b-0">
                      <td className="py-3 text-sm text-gray-900">{video.filename}</td>
                      <td className="py-3">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${statusColor(video.status)}`}>
                          {statusLabel(video.status)}
                        </span>
                      </td>
                      <td className="py-3">
                        <button
                          onClick={() => {
                            if (video.status === "done") {
                              router.push(`/script/${video.id}`);
                            } else {
                              router.push(`/progress/${video.id}`);
                            }
                          }}
                          className="text-sm text-blue-500 hover:text-blue-600"
                        >
                          {video.status === "done" ? "查看脚本" : "查看进度"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: 验证首页文件**

Run: `cd parse_video/frontend && cat src/app/page.tsx | head -3`
Expected: 文件以"use client"开头

---

### Task 5: 新增解析进度页

**Files:**
- Create: `frontend/src/app/progress/[id]/page.tsx`

- [ ] **Step 1: 创建解析进度页**

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { getVideoStatus, VideoStatusResponse } from "@/lib/api";

export default function ProgressPage() {
  const router = useRouter();
  const params = useParams();
  const videoId = Number(params.id);
  const [status, setStatus] = useState<VideoStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getVideoStatus(videoId);
      setStatus(data);
      if (data.status === "done") {
        // 延迟跳转，让用户看到100%
        setTimeout(() => router.push(`/script/${videoId}`), 1500);
        return;
      }
      if (data.status === "failed") {
        setError(data.error_message || "处理失败");
        return;
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "获取状态失败");
    }
  }, [videoId, router]);

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, 2000);
    return () => clearInterval(timer);
  }, [fetchStatus]);

  const getStepActive = () => {
    if (!status) return 0;
    const p = status.progress;
    if (p >= 100) return 5;
    if (p > 80) return 4;
    if (p > 60) return 3;
    if (p > 20) return 2;
    if (p > 0) return 1;
    return 0;
  };

  const steps = [
    { label: "上传完成", desc: "视频已上传到服务器" },
    { label: "提取音频", desc: "FFmpeg提取音频轨道" },
    { label: "语音识别", desc: "ASR识别台词内容" },
    { label: "镜头分析", desc: "视觉模型分析画面" },
    { label: "生成脚本", desc: "整合结构化脚本" },
  ];

  if (error) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-sm border p-8 max-w-md text-center">
          <div className="text-red-500 text-lg font-medium mb-2">解析失败</div>
          <div className="text-gray-600 mb-6">{error}</div>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            返回首页
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <button onClick={() => router.push("/")} className="text-blue-500 hover:text-blue-600 text-sm">
            ← 返回首页
          </button>
          <h1 className="text-2xl font-bold text-gray-900 mt-2">解析进度</h1>
        </div>
      </header>

      <div className="max-w-2xl mx-auto px-6 py-8">
        <div className="bg-white rounded-xl shadow-sm border p-8">
          {/* 视频信息 */}
          {status && (
            <div className="mb-6 text-sm text-gray-500">
              视频: {status.filename}
            </div>
          )}

          {/* 进度条 */}
          <div className="mb-8">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-600">总体进度</span>
              <span className="text-blue-600 font-medium">{status?.progress || 0}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-blue-500 h-3 rounded-full transition-all duration-500"
                style={{ width: `${status?.progress || 0}%` }}
              />
            </div>
          </div>

          {/* 步骤列表 */}
          <div className="space-y-4">
            {steps.map((step, index) => {
              const active = getStepActive();
              const isCompleted = index < active;
              const isCurrent = index === active;
              return (
                <div key={index} className="flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium shrink-0 ${
                    isCompleted ? "bg-green-500 text-white" :
                    isCurrent ? "bg-blue-500 text-white" :
                    "bg-gray-200 text-gray-500"
                  }`}>
                    {isCompleted ? "✓" : index + 1}
                  </div>
                  <div>
                    <div className={`font-medium ${isCurrent ? "text-blue-600" : isCompleted ? "text-green-600" : "text-gray-400"}`}>
                      {step.label}
                    </div>
                    <div className="text-sm text-gray-500">{step.desc}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 完成提示 */}
          {status?.status === "done" && (
            <div className="mt-6 text-center text-green-600 font-medium">
              ✓ 解析完成，正在跳转到脚本详情...
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: 验证进度页文件**

Run: `cd parse_video/frontend && ls src/app/progress/\\[id\\]/page.tsx`
Expected: 文件存在

---

### Task 6: 新增脚本详情页

**Files:**
- Create: `frontend/src/app/script/[videoId]/page.tsx`

- [ ] **Step 1: 创建脚本详情页**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { getScript, exportScript, ScriptResponse } from "@/lib/api";
import ScriptTimeline from "@/components/ScriptTimeline";

export default function ScriptDetailPage() {
  const router = useRouter();
  const params = useParams();
  const videoId = Number(params.videoId);
  const [script, setScript] = useState<ScriptResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchScript = async () => {
      try {
        const data = await getScript(videoId);
        setScript(data);
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取脚本失败");
      } finally {
        setLoading(false);
      }
    };
    fetchScript();
  }, [videoId]);

  const handleExport = async () => {
    try {
      const blob = await exportScript(videoId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `script_${videoId}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setError(err.response?.data?.detail || "导出失败");
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">加载脚本中...</div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-sm border p-8 max-w-md text-center">
          <div className="text-red-500 text-lg font-medium mb-2">加载失败</div>
          <div className="text-gray-600 mb-6">{error}</div>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            返回首页
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <button onClick={() => router.push("/")} className="text-blue-500 hover:text-blue-600 text-sm">
            ← 返回首页
          </button>
          <h1 className="text-2xl font-bold text-gray-900 mt-2">脚本详情</h1>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 脚本时间轴 - 主内容区 */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl shadow-sm border p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">脚本时间轴</h2>
              {script ? (
                <ScriptTimeline segments={script.segments} />
              ) : (
                <div className="text-gray-500 text-center py-8">未找到脚本</div>
              )}
            </div>
          </div>

          {/* 侧边栏 - 导出和原始数据 */}
          <div className="space-y-6">
            {/* 导出 */}
            <div className="bg-white rounded-xl shadow-sm border p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">导出脚本</h3>
              <button
                onClick={handleExport}
                className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
              >
                导出 JSON
              </button>
            </div>

            {/* 原始脚本数据 */}
            {script?.content && (
              <div className="bg-white rounded-xl shadow-sm border p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">原始数据</h3>
                <pre className="bg-gray-50 p-4 rounded-lg overflow-auto max-h-96 text-xs text-gray-700">
                  {JSON.stringify(script.content, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: 验证脚本详情页文件**

Run: `cd parse_video/frontend && ls src/app/script/\\[videoId\\]/page.tsx`
Expected: 文件存在

---

### Task 7: 优化globals.css样式

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: 优化全局样式**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --foreground-rgb: 0, 0, 0;
  --background-rgb: 249, 250, 251;
}

body {
  color: rgb(var(--foreground-rgb));
  background: rgb(var(--background-rgb));
}

/* 自定义滚动条 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}
```

- [ ] **Step 2: 验证样式文件**

Run: `cd parse_video/frontend && cat src/app/globals.css | head -5`
Expected: 文件包含@tailwind指令

---

### Task 8: 清理docker-compose.yml和更新启动脚本

**Files:**
- Modify: `docker-compose.yml`
- Modify: `start.sh` (或创建Windows版本)

- [ ] **Step 1: 清理docker-compose.yml - 仅保留postgres和redis**

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: parse_video
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

- [ ] **Step 2: 创建Windows启动脚本 start.bat**

```bat
@echo off
echo 正在启动 parse_video 项目...
echo.

echo [1/4] 启动 Docker 容器 (PostgreSQL + Redis)...
docker-compose up -d
if %errorlevel% neq 0 (
    echo Docker 启动失败，请确保 Docker Desktop 正在运行
    pause
    exit /b 1
)

echo [2/4] 等待数据库就绪...
timeout /t 3 /nobreak >nul

echo [3/4] 启动后端服务...
start "FastAPI Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo [4/4] 启动 Celery Worker...
start "Celery Worker" cmd /k "cd /d %~dp0backend && celery -A celery_app.celery_app worker --loglevel=info --pool=solo"

echo [5/4] 启动前端服务...
start "Next.js Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo 所有服务已启动！
echo 前端地址: http://localhost:3000
echo 后端地址: http://localhost:8000
echo API文档:  http://localhost:8000/docs
echo ========================================
echo.
echo 按任意键退出此窗口（服务将继续运行）...
pause >nul
```

- [ ] **Step 3: 验证文件**

Run: `cd parse_video && cat docker-compose.yml | head -10`
Expected: 仅包含postgres和redis服务

---

### Task 9: 验证前端构建

**Files:**
- None (验证步骤)

- [ ] **Step 1: 安装前端依赖**

Run: `cd parse_video/frontend && npm install`
Expected: 依赖安装成功

- [ ] **Step 2: 验证TypeScript编译**

Run: `cd parse_video/frontend && npx tsc --noEmit`
Expected: 无编译错误

- [ ] **Step 3: 验证Next.js构建**

Run: `cd parse_video/frontend && npm run build`
Expected: 构建成功，无错误

- [ ] **Step 4: 验证开发服务器启动**

Run: `cd parse_video/frontend && npm run dev`
Expected: 开发服务器在 http://localhost:3000 启动，页面显示完整的首页（包含上传区域、抖音链接输入、历史记录）
