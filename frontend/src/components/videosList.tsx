"use client";

import {
  CloneImage,
  CloneSegmentVideo,
  getVideoUrl,
  getImageUrl,
  getRegenerateStatus,
  regenerate,
  RegenerateResponse,
} from "@/lib/api";
import { setServers } from "dns";
import { useEffect, useState } from "react";

interface ScriptVideoProps {
  videos: CloneSegmentVideo[];
}

export default function VideoList({ videos }: ScriptVideoProps) {
  // 记录当前播放的视频 ID
  const [activeVideoId, setActiveVideoId] = useState<number | null>(null);
  const [openVideoCategory, setOpenVideoCategory] = useState<string | null>(null);

  const [regenStatus, setRegenStatus] = useState<Record<string, string>>({});

  // 保存最新视频参数
  const [videoParams, setVideoParams] = useState<
    Record<string, Partial<CloneSegmentVideo>>
  >({});

  const saveOpenImage = (category: string | null, id: number | null) => {
    setActiveVideoId(id);
    setOpenVideoCategory(category);
  };

  /**
   * 轮询生成状态
   */
  const getRegenVideoStatus = async (category: string, id: number) => {
    const key = category + id;

    const response: RegenerateResponse = await getRegenerateStatus(
      category,
      id,
    );

    setRegenStatus((prev) => ({
      ...prev,
      [key]: response.status,
    }));

    // 更新图片参数
    if (response.status === "SUCCESS") {
      setVideoParams((prev) => ({
        ...prev,
        [key]: {
          width: response.width,
          height: response.height,
          prompt: response.prompt,
          seed: response.seed,
          version: response.version,
        },
      }));

      return;
    }

    // PROCESSING / PENDING继续轮询
    if (response.status === "PROCESSING" || response.status === "PENDING") {
      setTimeout(() => {
        getRegenVideoStatus(category, id);
      }, 3000);

      return;
    }

    // FAILED结束
    if (response.status === "FAILED") {
      return;
    }
  };

  const regenerateVideo = async (
    category: string,
    id: number,
    width: number,
    height: number,
    prompt: string,
    seed: string | null,
  ) => {
    const key = category + id;

    // 点击后立即禁用
    setRegenStatus((prev) => ({
      ...prev,
      [key]: "PROCESSING",
    }));

    await regenerate(category, id, {
      prompt,
      width,
      height,
      seed,
    });

    // 开始轮询
    getRegenVideoStatus(category, id);
  };

  const handlePlay = (e: React.SyntheticEvent<HTMLVideoElement>, category: string, id: number) => {
    setActiveVideoId(id);
    setOpenVideoCategory(category);

    const currentVideoNode = e.currentTarget; // 获取当前播放的 video DOM 节点

    // 获取页面上所有的 video 标签并暂停非当前 ID 的视频
    const allVideos = document.querySelectorAll('video');
    allVideos.forEach((video) => {
      // 找到正在播放但不是当前被点击的视频，将其暂停
      if (video !== currentVideoNode && !video.paused) {
        video.pause();
      }
    });
  };

  console.log(`videos len: ${videos.length}`)

  

  useEffect(() => {
    const statusMap: Record<string, string> = {};

    videos.forEach((video) => {
      const key = video.category + video.id;
      console.log(`set ${key} status ${video.status}`)
      statusMap[key] = video.status;
    });

    setRegenStatus(statusMap);

  }, [videos]);

  if (videos.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无视频</div>;
  }

  return (
    <div className="space-y-4">
      {videos.map((video) => {
        const key = video.category + video.id;

        const status = regenStatus[key];
        console.log(`${key} status: ${status}`)

        const params = videoParams[key] ?? {};
        return (
          <div key={key} className="bg-white rounded-xl shadow border p-5">
            <div className="flex justify-between items-center">
              <div>
                <span className="text-lg font-bold text-gray-800">
                  {video.name}
                </span>

                <span className="ml-4 px-2 py-1 rounded bg-blue-50 text-blue-600 text-sm">
                  {params.width ?? video.width}x{params.height ?? video.height}
                </span>
              </div>

              <div>
                <div className="text-gray-500 text-sm">{video.desc}</div>

                <button
                  disabled={status === "PROCESSING" || status === "PENDING"}
                  className="
                  px-4 rounded-xl 
                  bg-blue-500 
                  text-white 
                  hover:bg-blue-600 
                  transition
                  disabled:bg-gray-400
                  "
                  onClick={() =>
                    regenerateVideo(
                      video.category,
                      video.id,
                      params.width ?? video.width,
                      params.height ?? video.height,
                      params.prompt ?? video.prompt,
                      params.seed ?? video.seed,
                    )
                  }
                >
                  {status === "PROCESSING" || status === "PENDING"
                    ? "生成中..."
                    : "重新生成"}
                </button>
              </div>
            </div>

            <div className="flex justify-between items-center">
              <div className="basis-1/2">
                <p className="text-gray-700 mb-1">
                  {params.prompt ?? video.prompt}
                </p>
              </div>

              <div
                className="
                flex items-center 
                basis-1/2 
                justify-start 
                overflow-hidden 
                cursor-pointer
                "
                style={{
                  width: 500,
                  height: 300,
                }}
                onClick={() => saveOpenImage(video.category, video.id)}
              >
                <video
                  src={`${getVideoUrl(video.category, video.id)}?v=${params.version ?? video.version}`}
                  controls
                  className="
                    max-w-full 
                    max-h-full 
                    object-contain
                  "
                  // 当用户点击原生的播放按钮时触发
                  onPlay={(e) => handlePlay(e, video.category, video.id)}
                />
                {/* <SingleVideoItem
                  key={key}
                  video={item}
                  playingId={activeVideoId}
                  onPlay={handlePlay}
                /> */}
                {/* <img
                  src={`${getVideoUrl(video.category, video.id)}?v=${params.version ?? video.version}`}
                  className="
                  max-w-full 
                  max-h-full 
                  object-contain
                  "
                /> */}
              </div>
            </div>


          </div>
        )
      })
      }
    </div>
  )
}
