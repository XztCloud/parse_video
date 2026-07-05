"use client";

import CreateClone from "@/components/CreateClone";
import ScriptTimeline from "@/components/ScriptTimeline";
import {
  getScript,
  getVideoStatus,
  ScriptResponse,
  VideoStatusResponse,
  listCloneScripts,
  CloneListItem,
} from "@/lib/api";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { finished } from "stream";

export default function ClonePage() {
  const router = useRouter();
  const params = useParams();

  const videoId = Number(params.videoId);
  const title = useSearchParams().get("title");
  const [script, setScript] = useState<ScriptResponse | null>(null);
  const [status, setStatus] = useState<VideoStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [cloneScripts, setCloneScripts] = useState<CloneListItem[]>([]);

  const onComplete = useCallback(
    async (theme: string, cloneScriptId: number) => {
      try {
        console.log("创建克隆完成，开始获取复刻ID ", cloneScriptId);
        console.log("视频主题", theme);
        router.push(`/cloneDetail/${cloneScriptId}`);
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取状态失败");
      }
    },
    [videoId, router],
  );

  const onStatusChange = useCallback(
    async (status: string) => {
      try {
        console.log("复刻状态", status);
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取状态失败");
      }
    },
    [videoId],
  );

  const cloneStatusColor = (s: string) => {
    const map: Record<string, string> = {
      PENDING: "bg-gray-100 text-gray-600",
      PLOT: "bg-yellow-100 text-yellow-500",
      PLOT_DONE: "bg-green-100 text-green-500",
      SEGMENTS: "bg-yellow-100 text-yellow-600",
      SEGMENTS_DONE: "bg-green-100 text-green-600",
      VIDEO: "bg-yellow-100 text-yellow-700",
      DONE: "bg-green-100 text-green-700",
      FAILED: "bg-red-100 text-red-700",
    };
    return map[s] || "bg-gray-100 text-gray-600";
  };

  const cloneStatusText = (s: string) => {
    const map: Record<string, string> = {
      PENDING: "开始复刻",
      PLOT: "生成剧本大纲",
      PLOT_DONE: "剧本完成",
      SEGMENTS: "生成分镜脚本",
      SEGMENTS_DONE: "分镜完成",
      VIDEO: "生成视频",
      DONE: "复刻完成",
      FAILED: "复刻失败",
    };
    return map[s] || "开始复刻";
  };

  useEffect(() => {
    const fetchScript = async () => {
      try {
        const data = await getScript(videoId);
        setScript(data);
        if (data && data.id) {
          const dataScript = await listCloneScripts(data.id);
          setCloneScripts(dataScript);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取脚本失败");
      } finally {
        setLoading(false);
      }
    };
    fetchScript();
  }, [videoId]);

  if (error) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-sm border p-8 max-w-md text-center">
          <div className="text-red-500 text-lg font-medium mb-2">复刻失败</div>
          <div className="text-gray-600 mb-6">{error}</div>
          <button
            onClick={() => router.back()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            返回首页
          </button>
        </div>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">加载脚本中...</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <button
            onClick={() => router.back()}
            className="text-blue-500 hover:text-blue-600 text-sm"
          >
            ← 返回首页
          </button>
          <h1 className="text-2xl font-bold text-gray-900 mt-2">
            {" "}
            复刻 {title}{" "}
          </h1>
        </div>
      </header>
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-sm border p-6">
              {<CreateClone videoId={videoId} onComplete={onComplete} />}
            </div>
          </div>
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-sm border p-6">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-gray-500">
                    <th className="pb-3 font-medium">主题</th>
                    <th className="pb-3 px-2 font-medium w-36">状态</th>
                    <th className="pb-3 font-medium w-36">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {cloneScripts.map((script) => (
                    <tr key={script.id} className="border-b last:border-b-0">
                      <td className="py-3 text-sm text-gray-900">
                        {script.clone_theme}
                      </td>
                      <td className="py-3">
                        <div className="inline-flex items-center gap-2">
                          <span
                            className={`px-2 py-1 rounded text-xs font-medium ${cloneStatusColor(script.clone_status)}`}
                          >
                            {cloneStatusText(script.clone_status)}
                          </span>
                        </div>
                      </td>
                      <td className="py-3">
                        <button
                          onClick={() => {
                            router.push(`/cloneDetail/${script.id}`);
                          }}
                          className="text-sm text-blue-500 hover:text-blue-600"
                        >
                          查看详情
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
