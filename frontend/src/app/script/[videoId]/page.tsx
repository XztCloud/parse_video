"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { getScript, exportScript, ScriptResponse } from "@/lib/api";
import ScriptTimeline from "@/components/ScriptTimeline";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ScriptDetailPage() {
  const router = useRouter();
  const params = useParams();
  const videoId = Number(params.videoId);
  const [script, setScript] = useState<ScriptResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"timeline" | "raw">("timeline");

  // const getFormattedJSON = (data: any): boolean => {
  //   try {
  //     let parse_data = JSON.parse(data);
  //     console.log('content 解析成功');
  //     return true;
  //   } catch (error) {
  //     const text = script?.content ?? "";
  //     const preview = text.length > 20 ? `${text.slice(0, 20)}...` : text;
  //     console.log('content 非json格式: ', preview);
  //     return false;
  //   }
  // };
  // const isformattedJSON = getFormattedJSON(script?.content);

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
      
      // 1. 将原始的 Blob 转换为字符串文本
      const jsonText = await blob.text();
      
      // 2. 解析为 JSON 对象
      const rawData = JSON.parse(jsonText);
      
      if (activeTab === 'timeline') {
        // 3. 提取出其中的 segments 数组
        const segments = rawData.segments || [];
        
        // 🚀 【可选优化】如果你需要在这个阶段把毫秒(ms)转换为秒(s)，在这里处理：
        const formattedSegments = segments.map((item: any) => ({
          ...item,
          start_time: item.start_time !== undefined ? (item.start_time / 1000).toFixed(2) : item.start_time,
          end_time: item.end_time !== undefined ? (item.end_time / 1000).toFixed(2) : item.end_time,
        }));

        // 4. 将提取/转换后的数组重新序列化，并创建专属的 JSON Blob
        // 使用 JSON.stringify(..., null, 2) 可以让导出的 JSON 文件自动带缩进换行，非常漂亮
        const cleanBlob = new Blob(
          [JSON.stringify(formattedSegments, null, 2)], 
          { type: "application/json" }
        );
        const url = window.URL.createObjectURL(cleanBlob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `script_${videoId}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        console.log('导出原始 Markdown 数据');
        // 如果是原始数据（Markdown），直接使用原始 Blob 就好
        const markdownText  = rawData.script || '';
        const cleanBlob = new Blob([markdownText], { type: 'text/markdown;charset=utf-8' });
        const url = window.URL.createObjectURL(cleanBlob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `script_${videoId}.md`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }


      
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
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-sm border p-6">
              <div className="flex justify-between items-end border-b border-gray-200 w-full mb-6">
                <div className="flex -mb-[1px]">
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
                    onClick={() => setActiveTab('raw')}
                    className={`px-4 py-2.5 font-medium transition-colors ${
                      activeTab === 'raw'
                        ? 'border-b-2 border-blue-500 text-blue-600 font-semibold'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    视频分析脚本
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
                <div className="pb-2 flex-shrink-0"> 
                  <button
                    onClick={handleExport}
                    className="px-3.5 py-1.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    {activeTab === 'timeline' ? '导出 JSON' : '导出 Markdown'}
                  </button>
                </div>
              </div>
              {/* <h2 className="text-lg font-semibold text-gray-900 mb-4">脚本时间轴</h2> */}
              {script ? (
                activeTab === 'timeline' ? (
                  <ScriptTimeline segments={script.segments} />
                ) : (
                  <div className="prose prose-slate max-w-none 
  prose-th:bg-slate-50 prose-th:px-4 prose-th:py-3 prose-th:text-slate-700 prose-th:font-semibold
  prose-td:px-4 prose-td:py-3.5 prose-td:align-top prose-td:text-slate-600 [&_th:nth-child(3)]:min-w-[100px]">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} >
                      {script?.content || "# 正在加载内容..."}
                    </ReactMarkdown>
                  </div>
                )
              ) : (
                <div className="text-gray-500 text-center py-8">未找到脚本</div>
              )}
            </div>
          </div>

          {/* 侧边栏 - 导出和原始数据 */}
          {/* <div className="space-y-6">
           
            <div className="bg-white rounded-xl shadow-sm border p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">导出脚本</h3>
              <button
                onClick={handleExport}
                className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
              >
                导出 JSON
              </button>
            </div>


            {script?.content && activeTab === 'timeline'  && (
              <div className="bg-white rounded-xl shadow-sm border p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">原始数据</h3>
                <pre className="bg-gray-50 p-4 rounded-lg overflow-auto max-h-96 text-xs text-gray-700">
                  {JSON.stringify(script?.segments, null, 2)}
                </pre>
              </div>
            )}
          </div> */}
        </div>
      </div>
    </main>
  );
}
