"use client";

import CloneProgress from "@/components/CloneProgress";
import ScriptTimeline from "@/components/ScriptTimeline";
import VoiceList from "@/components/VoicesList";
import { CloneStatus, CloneStatusResponse, ClonseScriptResponse, exportClonePlot, getCloneScript, getCloneStatus } from "@/lib/api";
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
  const [cloneScript, setCloneScript] = useState<ClonseScriptResponse|null>(null);
  const [activeTab, setActiveTab] = useState<"raw"|"voices"|"timeline"|"images"|"videos">("raw");

  const onStatusChange = useCallback(async (cloneStatus: CloneStatus) => {
    try {
      console.log("current clone status", cloneStatus);
      const data = await getCloneScript(cloneId);
      setCloneScript(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "获取数据失败");
    }
  }, []);


  const handleExportPlot = async ()=> {
    try {
      const blob = await exportClonePlot(cloneId);
      
      if (blob.type === 'application/json') { // 或者根据你的后端报错特征判断
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

  const handleExportSegments = async ()=> {

  };

  useEffect(() => {
    const fetchScript = async () => {
      try {
        const data = await getCloneScript(cloneId);
        setCloneScript(data);
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
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <button
            onClick={() => router.back()}
            className="text-blue-500 hover:text-blue-600 text-sm"
          >
            ← 返回
          </button>
          <h1 className="text-2xl font-bold text-gray-900 mt-2"> 复刻详情</h1>
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
                    onClick={() => setActiveTab('raw')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'raw'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    视频脚本
                  </button>

                  <button
                    onClick={() => setActiveTab('voices')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'voices'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    音频
                  </button>

                  <button
                    onClick={() => setActiveTab('timeline')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'timeline'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    分镜脚本
                  </button>
                  
                  <button
                    onClick={() => setActiveTab('images')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'images'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    图片
                  </button>

                  <button
                    onClick={() => setActiveTab('videos')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'videos'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
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
                {['raw', 'timeline'].includes(activeTab) && (
                  <div className="pb-2 flex-shrink-0"> 
                    <button
                      onClick={activeTab === 'raw' ? handleExportPlot : (activeTab === 'timeline' ? handleExportSegments: undefined)}
                      className="px-3.5 py-1.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                    >
                      导出脚本
                    </button>
                  </div>
                  )
                }
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
                      <div className="text-gray-500 text-center py-8">暂无脚本片段</div>
                    )

                    }
                  </div>
                ) : activeTab === 'voices' ? (
                  <div
                    className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]"
                  >
                    {cloneScript?.voices ? (
                      <VoiceList voices={cloneScript.voices}></VoiceList>
                    ) : (
                      <div className="text-gray-500 text-center py-8">暂无音频</div>
                    )

                    }
                  </div>
                ) : (
                  <div className="text-gray-500 text-center py-8">暂无脚本片段</div>
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
