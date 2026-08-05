"use client";

import {
  cloneFrames,
  cloneImages,
  cloneMergeVideo,
  cloneSegments,
  CloneSegmentsResponse,
  cloneSegmentVideo,
  CloneStatus,
  CloneStatusResponse,
  cloneVoices,
  getCloneStatus,
  getVideoStatus,
  reClonePlot,
  VideoStatusResponse,
} from "@/lib/api";
import { stat } from "fs";
import { useCallback, useEffect, useRef, useState } from "react";

interface CloneProgressProps {
  cloneId: number;
  onStatusChange: (clone_status: CloneStatus) => void;
}

export default function CloneProgress({
  cloneId,
  onStatusChange,
}: CloneProgressProps) {
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CloneStatusResponse | null>(null);
  const [prevStatus, setPrevStatus] = useState<string | null>(null);
  const [autoRun, setAutoRun] = useState<boolean>(false);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setAutoRun(e.target.checked); // e.target.checked 会自动返回 true 或 false
  };

  const continueClone = async (clone_status: string) => {
    try {
      if (clone_status === "PENDING") {
        const data = await reClonePlot(cloneId, autoRun);
        console.log("reClonePlot response is", data);
      }
      else if (clone_status === "PLOT_DONE") {
        const data = await cloneVoices(cloneId, autoRun);
        console.log("cloneVoices response is", data);
      } else if (clone_status === "VOICE_DONE") {
        const data = await cloneSegments(cloneId, autoRun);
        console.log("cloneSegments response is", data);
      } else if (clone_status === "SEGMENTS_DONE") {
        const data = await cloneImages(cloneId, autoRun);
        console.log("cloneSegments response is", data);
      } else if (clone_status === "IMAGE_DONE") {
        const data = await cloneFrames(cloneId, autoRun);
        console.log("cloneFrames response is", data);
      } else if (clone_status === "FRAME_DONE") {
        const data = await cloneSegmentVideo(cloneId, autoRun);
        console.log("cloneSegmentVideo response is", data);
      } else if (clone_status === "SEGMENT_VIDEO_DONE") {
        const data = await cloneMergeVideo(cloneId, autoRun);
        console.log("cloneMergeVideo response is", data);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "失败");
    }
  };

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getCloneStatus(cloneId);
      console.log(`clone status: ${data.clone_progress}, status: ${data.clone_status}, prevStatus: ${prevStatus}`)
      setStatus(data);


      if (prevStatus !== data.clone_status && 
        data.clone_status === CloneStatus.PLOT_DONE) {
        console.log('send status change PLOT_DONE.')
        onStatusChange(CloneStatus.PLOT_DONE); // 剧情脚本完成
      }
      if (prevStatus !== data.clone_status && 
        data.clone_status === CloneStatus.VOICE_DONE) {
        console.log('send status change VOICE_DONE.')
        onStatusChange(CloneStatus.VOICE_DONE); // 剧情脚本完成
      }
      if (prevStatus !== data.clone_status && 
        data.clone_status === CloneStatus.SEGMENTS_DONE) {
        onStatusChange(CloneStatus.SEGMENTS_DONE); // 分镜脚本完成
      }
      if (prevStatus !== data.clone_status && 
        data.clone_status === CloneStatus.IMAGE_DONE) {
        console.log('send status change IMAGE_DONE.')
        onStatusChange(CloneStatus.IMAGE_DONE); // 剧情脚本完成
      }
      if (prevStatus !== data.clone_status && 
        data.clone_status === CloneStatus.FRAME_DONE) {
        console.log('send status change FRAME_DONE.')
        onStatusChange(CloneStatus.FRAME_DONE); // 剧情脚本完成
      }
      if (prevStatus !== data.clone_status && 
        data.clone_status === CloneStatus.SEGMENT_VIDEO_DONE) {
        console.log('send status change SEGMENT_VIDEO_DONE.')
        onStatusChange(CloneStatus.SEGMENT_VIDEO_DONE); // 剧情脚本完成
      }
      if (prevStatus !== data.clone_status) {
        console.log("setPrevStatus", prevStatus)
        setPrevStatus(data.clone_status);
      }
      if (data.clone_status === CloneStatus.DONE) {
        onStatusChange(CloneStatus.DONE); // 视频完成
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      if (data.clone_status === CloneStatus.FAILED) {
        setError(data.error_message || "复刻失败");
        onStatusChange(CloneStatus.FAILED);
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      // console.log(`prevStatus: ${prevStatus}, cone_status: ${data.clone_status}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || "获取状态失败");
    }
  }, [cloneId, onStatusChange, prevStatus]);

  useEffect(() => {
    fetchStatus();
    timerRef.current = setInterval(fetchStatus, 2000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchStatus]);

  const canContinue =
    status &&
    (status.clone_status === "PLOT_DONE" ||
      status.clone_status === "VOICE_DONE" ||
      status.clone_status === "SEGMENTS_DONE" ||
      status.clone_status === "IMAGE_DONE" ||
      status.clone_status === "FRAME_DONE" ||
      status.clone_status === "SEGMENT_VIDEO_DONE");

  const canRetry =
    status &&
    (status.clone_status === "PLOT_DONE" ||
      status.clone_status === "VOICE_DONE" ||
      status.clone_status === "SEGMENTS_DONE" ||
      status.clone_status === "IMAGE_DONE" ||
      status.clone_status === "FRAME_DONE" ||
      status.clone_status === "SEGMENT_VIDEO_DONE" ||
      status.clone_status === "DONE");

  const canSkip =
    status &&
    (status.clone_status === "PLOT_DONE" ||
      status.clone_status === "SEGMENTS_DONE");

  const statusTextMap: Record<string, string> = {
    PENDING: "等待处理",
    PLOT: "复刻剧本中",
    PLOT_DONE: "复刻剧本完成",
    VOICE: "生成音频中",
    VOICE_DONE: "生成音频完成",
    SEGMENTS: "复刻分镜中",
    SEGMENTS_DONE: "复刻分镜完成",
    IMAGE: "生成图片中",
    IMAGE_DONE: "生成图片完成",
    FRAME: "生成参考帧中",
    FRAME_DONE: "生成参考帧完成",
    SEGMENT_VIDEO: "制作视频中",
    SEGMENT_VIDEO_DONE: "制作视频完成",
    MERGE_VIDEO: "融合视频中",
    DONE: "处理完成",
    FAILED: "处理失败",
  };

  const statusText = status
    ? (statusTextMap[status.clone_status] ?? "未知状态")
    : "";

  const statusSkipMap: Record<string, string> = {
    PLOT_DONE: "VOICE_DONE",
    SEGMENTS_DONE: "IMAGE_DONE",
  };

  const skipStatus = status
    ? (statusSkipMap[status.clone_status] ?? "未知状态")
    : "";

  const statusRetryMap: Record<string, string> = {
    PLOT_DONE: "PENDING",
    VOICE_DONE: "PLOT_DONE",
    SEGMENTS_DONE: "VOICE_DONE",
    IMAGE_DONE: "SEGMENTS_DONE",
    FRAME_DONE: "IMAGE_DONE",
    SEGMENT_VIDEO_DONE: "FRAME_DONE",
    DONE: "SEGMENT_VIDEO_DONE"
  }

  const retryStatus = status
    ? (statusRetryMap[status.clone_status] ?? "未知状态")
    : "";

  if (error) {
    return <div className="text-red-500 text-center">{error}</div>;
  }

  if (!status) {
    return <div className="text-gray-500 text-center">加载中...</div>;
  }

  return (
    <div className="w-full mx-auto">
      <div className="rounded-2xl  shadow-sm p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="text-xl font-semibold text-gray-900">
              视频复刻任务
            </h3>

            <p className="text-sm text-gray-500 mt-1">
              当前状态：
              <span className="ml-1 font-medium text-blue-600">
                {statusText}
              </span>
            </p>
          </div>

          <div className="text-2xl font-bold text-blue-600">
            {status.clone_progress}%
          </div>
        </div>

        {/* Progress */}
        <div className="w-full h-3 rounded-full bg-gray-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-500 transition-all duration-500"
            style={{
              width: `${status.clone_progress}%`,
            }}
          />
        </div>

        {/* Bottom */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex gap-2">
            {canContinue && (
              <button
                onClick={() => continueClone(status.clone_status)}
                className="px-4 rounded-xl bg-blue-500 text-white hover:bg-blue-600 transition"
              >
                ▶ 继续
              </button>
            )}

            {canRetry && (
              <button
                className="px-5 py-2 rounded-xl border border-yellow-400 bg-yellow-50 text-yellow-700 hover:bg-yellow-100 transition"
                onClick={() => continueClone(retryStatus)}
              >
                ↻ 重试
              </button>
            )}

            {canSkip && (
              <button
                className="px-5 py-2 rounded-xl border text-gray-700 border-gray-300 hover:bg-gray-100 transition"
                onClick={() => continueClone(skipStatus)}
              >
                ⏭ 跳过
              </button>
            )}
          </div>

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRun}
              onChange={handleCheckboxChange}
              className="w-5 h-5 accent-blue-600"
            />

            <span className="text-sm text-gray-600">自动执行下一步</span>
          </label>
        </div>
      </div>
    </div>
  );
}
