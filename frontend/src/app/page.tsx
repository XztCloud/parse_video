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
      done: "解析完成",
      failed: "失败",
      cloning: "复刻中",
      clone: "复刻完成",
    };
    return map[s] || s;
  };

  const cloneStatusLabel = (s: string) => {
    const map: Record<string, string> = {
      pending: "等待中",
      cloning: "复刻中",
      done: "解析完成",
      CLONE_FAILED: "复刻失败",
      clone_done: "复刻完成",
    };
    return map[s] || s;
  };

  const statusColor = (s: string) => {
    const map: Record<string, string> = {
      pending: "bg-gray-100 text-gray-600",
      processing: "bg-yellow-100 text-yellow-700",
      done: "bg-green-100 text-green-700",
      failed: "bg-red-100 text-red-700",
      cloning: "bg-yellow-100 text-yellow-700",
      clone: "bg-green-100 text-green-700",
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
                    <th className="pb-3 font-medium w-48">状态</th>
                    <th className="pb-3 font-medium w-48">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((video) => (
                    <tr key={video.id} className="border-b last:border-b-0">
                      <td className="py-3 text-sm text-gray-900">{video.filename}</td>
                      <td className="py-3">
                        <div className="inline-flex items-center gap-2">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${statusColor(video.status)}`}>
                            {statusLabel(video.status)}
                          </span>
                          {video.status === 'done' && video.clone_status != 'pending' &&(
                            <span className={`px-2 py-1 rounded text-xs font-medium ${statusColor(video.status)}`}>
                              {cloneStatusLabel(video.clone_status)}
                            </span>
                          )}
                        </div>
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
                        
                        {video.status === "done" && (
                          <button
                            onClick={() => {
                              if (video.status === "done") {
                                router.push(`/script/${video.id}`);
                              } else {
                                router.push(`/progress/${video.id}`);
                              }
                            }}
                              className="px-3 text-sm text-blue-500 hover:text-blue-600"
                          >
                            {video.clone_status === "clone_done" ? "查看复刻" : video.clone_status === "pending" ? "开始复刻" : "查看进度"}
                          </button>
                        )}
                        <button
                          onClick={() => {
                            router.push(`/cloneProgress/${video.id}`);
                          }}
                          className="px-3 text-sm text-blue-500 hover:text-blue-600"
                        >
                          {/* <button style={{ display: 'flex', alignItems: 'center', gap: '8px' }}> */}
                            {/* 调整大小和阴影 */}
                            {/* <span style={{ fontSize: '18px', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.1))' }}> */}
                              🗑️
                            {/* </span> */}
                          {/* </button> */}
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
