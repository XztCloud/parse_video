"use client";

import { listVideos, VideoListItem } from "@/lib/api";
import LogoutButton from "@/components/logout";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

interface VideoPickerProps {
  title: string;
  subtitle: string;
  /** label + handler 的每个 done 视频动作 */
  action: (video: VideoListItem) => { text: string; onClick: () => void };
}

/** 通用"已解析视频选择列表"：仅列出解析完成(status=done)的视频，提供单个动作 */
export function VideoPicker({ title, subtitle, action }: VideoPickerProps) {
  const router = useRouter();
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listVideos();
      setVideos(data.filter((v) => v.status === "done"));
    } catch {
      // 静默
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 w-full border-b border-gray-100 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/home")}
              className="group flex h-9 w-9 items-center justify-center rounded-full border border-gray-100 bg-white text-gray-500 shadow-sm transition-all hover:bg-gray-50 hover:text-gray-700"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
              </svg>
            </button>
            <div className="flex flex-col space-y-0.5">
              <h1 className="text-xl font-bold tracking-tight text-gray-900 sm:text-2xl">{title}</h1>
              <p className="hidden text-xs text-gray-400 sm:block">{subtitle}</p>
            </div>
          </div>
          <LogoutButton />
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900">已解析视频</h2>
            <button onClick={fetchVideos} className="text-sm text-blue-500 hover:text-blue-600">
              刷新
            </button>
          </div>

          {loading ? (
            <div className="text-center py-8 text-gray-500">加载中...</div>
          ) : videos.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              暂无已解析视频，请先在"解析视频"模块上传
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-gray-500">
                    <th className="pb-3 font-medium">视频名称</th>
                    <th className="pb-3 font-medium w-40 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((video) => {
                    const a = action(video);
                    return (
                      <tr key={video.id} className="border-b last:border-b-0">
                        <td className="py-3 text-sm text-gray-900">{video.filename}</td>
                        <td className="py-3 text-right">
                          <button
                            onClick={a.onClick}
                            className="text-sm text-blue-500 hover:text-blue-600"
                          >
                            {a.text}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
