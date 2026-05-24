"use client";

import { useEffect, useState } from "react";
import { getVideoStatus, VideoStatusResponse } from "@/lib/api";

interface ProgressDisplayProps {
  videoId: number;
  onComplete: () => void;
}

export default function ProgressDisplay({ videoId, onComplete }: ProgressDisplayProps) {
  const [status, setStatus] = useState<VideoStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const pollStatus = async () => {
      try {
        const data = await getVideoStatus(videoId);
        setStatus(data);
        if (data.status === "done") {
          onComplete();
          return;
        }
        if (data.status === "failed") {
          setError(data.error_message || "处理失败");
          return;
        }
        setTimeout(pollStatus, 2000);
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取状态失败");
      }
    };
    pollStatus();
  }, [videoId, onComplete]);

  if (error) {
    return <div className="text-red-500 text-center">{error}</div>;
  }

  if (!status) {
    return <div className="text-gray-500 text-center">加载中...</div>;
  }

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="mb-4">
        <div className="text-sm text-gray-500 mb-1">处理进度</div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
            style={{ width: `${status.progress}%` }}
          ></div>
        </div>
        <div className="text-right text-sm text-gray-500 mt-1">{status.progress}%</div>
      </div>
      <div className="text-center">
        <div className="text-sm text-gray-500">
          状态:{" "}
          {status.status === "pending" && "等待处理"}
          {status.status === "processing" && "处理中"}
          {status.status === "done" && "处理完成"}
          {status.status === "failed" && "处理失败"}
        </div>
      </div>
    </div>
  );
}