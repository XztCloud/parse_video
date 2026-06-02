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
    if (p >= 80) return 4;
    if (p >= 60) return 3;
    if (p >= 20) return 2;
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
