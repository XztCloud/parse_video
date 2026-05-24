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
