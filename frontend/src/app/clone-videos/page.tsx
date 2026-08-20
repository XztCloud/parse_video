"use client";

import { VideoPicker } from "@/components/VideoPicker";
import { useRouter } from "next/navigation";

export default function CloneVideosPage() {
  const router = useRouter();

  return (
    <VideoPicker
      title="复刻剧本"
      subtitle="选择一个已解析视频，为其生成复刻剧本与分镜"
      action={(video) => {
        const params = new URLSearchParams();
        params.set("title", video.filename);
        return {
          text: "去复刻",
          onClick: () => router.push(`/clone/${video.id}?${params.toString()}`),
        };
      }}
    />
  );
}
