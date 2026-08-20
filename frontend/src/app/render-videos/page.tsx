"use client";

import { VideoPicker } from "@/components/VideoPicker";
import { renderFromScript } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function RenderVideosPage() {
  const router = useRouter();

  return (
    <VideoPicker
      title="生成视频"
      subtitle="选择一个已解析视频，按原片直转渲染出音频 / 图片 / 分镜视频 / 成片"
      action={(video) => ({
        text: "开始生成",
        onClick: async () => {
          try {
            const res = await renderFromScript(video.id);
            router.push(`/cloneDetail/${res.id}`);
          } catch (err: any) {
            alert(err.response?.data?.detail || "生成失败");
          }
        },
      })}
    />
  );
}
