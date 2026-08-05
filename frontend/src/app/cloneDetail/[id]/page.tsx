"use client";

import CloneProgress from "@/components/CloneProgress";
import ImageList from "@/components/ImagesList";
import LogoutButton from "@/components/logout";
import ScriptTimeline from "@/components/ScriptTimeline";
import VideoList from "@/components/videosList";
import VoiceList from "@/components/VoicesList";
import {
  CloneStatus,
  CloneStatusResponse,
  ClonseScriptResponse,
  exportClonePlot,
  getCloneScript,
  getCloneStatus,
} from "@/lib/api";
import { useRouter, useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ClonePage() {
  const router = useRouter();
  const params = useParams();
  const [loading, setLoading] = useState(true);
  const cloneId = Number(params.id);
  const [error, setError] = useState<string | null>(null);
  const [cloneScript, setCloneScript] = useState<ClonseScriptResponse | null>(
    null,
  );
  const [activeTab, setActiveTab] = useState<
    "raw" | "voices" | "timeline" | "images" | "frames" | "segment_videos" | "video"
  >("raw");

  const onStatusChange = useCallback(async (cloneStatus: CloneStatus) => {
    try {
      console.log("current clone status", cloneStatus);
      const data = await getCloneScript(cloneId);
      setCloneScript(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "获取数据失败");
    }
  }, []);

  const handleExportPlot = async () => {
    try {
      const blob = await exportClonePlot(cloneId);

      if (blob.type === "application/json") {
        // 或者根据你的后端报错特征判断
        const errorText = await blob.text();
        const errorJson = JSON.parse(errorText);
        setError(errorJson.detail || "导出失败");
        return;
      }

      // const mdBlob = new Blob([blob], { type: 'text/markdown;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `clone_${cloneId}.md`;
      document.body.appendChild(a);
      a.click();

      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error: any) {
      // 如果后端返回了错误信息，且被包装成了 Blob
      if (error.response?.data instanceof Blob) {
        const blobData = error.response.data;

        // 使用 FileReader 将二进制的错误信息读出来
        const reader = new FileReader();
        reader.onload = function () {
          const errorText = reader.result as string;
          const errorJson = JSON.parse(errorText);

          // 这里的 errorJson.detail 就是上一问你拼接的 "导出复刻脚本信息失败: 400..."
          setError(errorJson.detail || "下载失败");
        };
        reader.readAsText(blobData);
      } else {
        setError("网络请求失败");
      }
    }
  };

  const handleExportSegments = async () => {};

  useEffect(() => {
    const fetchScript = async () => {
      try {
        const data = await getCloneScript(cloneId);
        
        setCloneScript(data);
        console.log(JSON.stringify(data, null, 2));
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取脚本失败");
      } finally {
        setLoading(false);
      }
    };
    fetchScript();
  }, [cloneId]);

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
          <div className="text-red-500 text-lg font-medium mb-2">复刻失败</div>
          <div className="text-gray-600 mb-6">{error}</div>
          <button
            onClick={() => router.back()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            返回
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 w-full border-b border-gray-100 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          {/* 左侧区域：返回按钮 + 标题 */}
          <div className="flex items-center gap-3">
            {/* 返回上一页按钮 */}
            <button
              onClick={() => router.back()}
              title="返回上一页按钮"
              className="group flex h-9 w-9 items-center justify-center rounded-full border border-gray-100 bg-white text-gray-500 shadow-sm transition-all duration-150 hover:bg-gray-50 hover:text-gray-700 hover:shadow-md active:scale-95"
            >
              {/* 精致的向左箭头 */}
              <svg
                className="h-4 w-4 transition-transform duration-150 group-hover:-translate-x-0.5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="2.5"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15.75 19.5L8.25 12l7.5-7.5"
                />
              </svg>
            </button>

            {/* 标题与副标题 */}
            <div className="flex flex-col space-y-0.5">
              <h1 className="bg-gradient-to-r from-gray-900 to-gray-700 bg-clip-text text-xl font-bold tracking-tight text-transparent sm:text-2xl">
                复刻详情
              </h1>
              <p className="hidden text-xs text-gray-400 sm:block">
                复刻原视频脚本，得到新的剧情大纲、声音、分镜、图片和视频
              </p>
            </div>
          </div>

          {/* 右侧：动作按钮区 */}
          <div className="flex items-center gap-4">
            <LogoutButton />
          </div>
        </div>
      </header>
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-sm border p-6">
              {
                <CloneProgress
                  cloneId={cloneId}
                  onStatusChange={onStatusChange}
                />
              }
            </div>
          </div>
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-sm border p-6">
              <div className="flex justify-between items-end border-b border-gray-200 w-full mb-6">
                <div className="flex -mb-[1px]">
                  <button
                    onClick={() => setActiveTab("raw")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "raw"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    视频脚本
                  </button>

                  <button
                    onClick={() => setActiveTab("voices")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "voices"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    音频
                  </button>

                  <button
                    onClick={() => setActiveTab("timeline")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "timeline"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    分镜脚本
                  </button>

                  <button
                    onClick={() => setActiveTab("images")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "images"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    图片
                  </button>

                  <button
                    onClick={() => setActiveTab("frames")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "frames"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    分镜帧
                  </button>

                  <button
                    onClick={() => setActiveTab("segment_videos")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "segment_videos"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    分镜视频
                  </button>

                  <button
                    onClick={() => setActiveTab("video")}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === "video"
                        ? "border-b-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    视频
                  </button>

                  {/* <button
                    onClick={() => setActiveTab('clone')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'clone'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    一键复刻
                  </button> */}
                </div>
                {/* 右侧：独立的导出按钮（增加 mb-2 或 py-1.5 稍微提上去一点，避免压到下划线） */}
                {["raw", "timeline"].includes(activeTab) && (
                  <div className="pb-2 flex-shrink-0">
                    <button
                      onClick={
                        activeTab === "raw"
                          ? handleExportPlot
                          : activeTab === "timeline"
                            ? handleExportSegments
                            : undefined
                      }
                      className="px-3.5 py-1.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                    >
                      导出脚本
                    </button>
                  </div>
                )}
              </div>
              {cloneScript ? (
                activeTab === "timeline" ? (
                  <ScriptTimeline segments={cloneScript.segments} />
                ) : activeTab === "raw" ? (
                  <div
                    className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]"
                  >
                    {cloneScript?.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {cloneScript.content}
                      </ReactMarkdown>
                    ) : (
                      <div className="text-gray-500 text-center py-8">
                        暂无脚本片段
                      </div>
                    )}
                  </div>
                ) : activeTab === "voices" ? (
                  <div
                    className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]"
                  >
                    {cloneScript?.voices ? (
                      <VoiceList voices={cloneScript.voices}></VoiceList>
                    ) : (
                      <div className="text-gray-500 text-center py-8">
                        暂无音频
                      </div>
                    )}
                  </div>
                ) : activeTab === "images" ? (
                  <div
                    className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]"
                  >
                    {cloneScript?.images ? (
                      <ImageList images={cloneScript.images}></ImageList>
                    ) : (
                      <div className="text-gray-500 text-center py-8">
                        暂无音频
                      </div>
                    )}
                  </div>
                ) : activeTab === "frames" ? (
                  <div
                    className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]"
                  >
                    {cloneScript?.frames ? (
                      <ImageList images={cloneScript.frames}></ImageList>
                    ) : (
                      <div className="text-gray-500 text-center py-8">
                        暂无音频
                      </div>
                    )}
                  </div>
                ) : activeTab === "segment_videos" ? (
                  <div
                    className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]"
                  >
                  
                    {cloneScript?.frames ? (
                      <VideoList videos={cloneScript.segment_videos}></VideoList>
                    ) : (
                      <div className="text-gray-500 text-center py-8">
                        暂无音频
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-gray-500 text-center py-8">
                    暂无脚本片段
                  </div>
                )
              ) : (
                <div className="text-gray-500 text-center py-8">未找到脚本</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
