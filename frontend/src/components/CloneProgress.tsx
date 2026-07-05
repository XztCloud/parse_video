"use client";

import {
  cloneImages,
  cloneSegments,
  CloneSegmentsResponse,
  CloneStatus,
  CloneStatusResponse,
  cloneVoices,
  getCloneStatus,
  getVideoStatus,
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
  const [prevStatus, setPrevStatus] = useState<string|null>(null);
  const [autoRun, setAutoRun] = useState<boolean>(false)

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setAutoRun(e.target.checked); // e.target.checked 会自动返回 true 或 false
  };

  const continueClone = async(clone_status: string) => {
    try {
      if (clone_status === "PLOT_DONE") {
        const data = await cloneVoices(cloneId, autoRun)
        console.log('cloneVoices response is', data)
      }
      else if (clone_status === "VOICE_DONE") {
        const data = await cloneSegments(cloneId, autoRun)
        console.log('cloneSegments response is', data)
      }
      else if (clone_status === "SEGMENTS_DONE") {
        const data = await cloneImages(cloneId, autoRun)
        console.log('cloneSegments response is', data)
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
    timerRef.current =setInterval(fetchStatus, 2000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    }
  }, [fetchStatus]);

  if (error) {
    return <div className="text-red-500 text-center">{error}</div>;
  }

  if (!status) {
    return <div className="text-gray-500 text-center">加载中...</div>;
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="mb-4">
        <div className="text-sm text-gray-500 mb-1">处理进度</div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
            style={{ width: `${status.clone_progress}%` }}
            // style={{ width: "0%" }}
          ></div>
        </div>
        <div className="text-right text-sm text-gray-500 mt-1">
          {status.clone_progress}%
        </div>
      </div>
      <div className="flex w-full items-center border gap-4  p-4">
        <div className="text-right w-3/5  text-gray-500">
          状态: {status.clone_status === "PENDING" && "等待处理"}
          {status.clone_status === "PLOT" && "复刻剧本中"}
          {status.clone_status === "PLOT_DONE" && "复刻剧本完成"}
          {status.clone_status === "VOICE" && "生成音频中"}
          {status.clone_status === "VOICE_DONE" && "生成音频完成"}
          {status.clone_status === "SEGMENTS" && "复刻分镜中"}
          {status.clone_status === "SEGMENTS_DONE" && "复刻分镜完成"}
          {status.clone_status === "IMAGE" && "生成图片中"}
          {status.clone_status === "IMAGE_DONE" && "生成图片完成"}
          {status.clone_status === "VIDEO" && "制作视频中"}
          {status.clone_status === "DONE" && "处理完成"}
          {status.clone_status === "FAILED" && "处理失败"}
        </div>
        <div className="w-2/5 p-4 text-left flex items-center">
        {
          (status.clone_status === "PLOT_DONE" || status.clone_status === "VOICE_DONE" ||
            status.clone_status === "SEGMENTS_DONE" || status.clone_status === "IMAGE_DONE") && (
            <div  className="w-full flex items-center gap-1">
              <button className="w-1/3 px-2.5 py-1  rounded-lg bg-blue-500 hover:bg-blue-600 transition-colors"
              onClick={() => continueClone(status.clone_status)}>
                继续
              </button>
              {
                status.clone_status === "PLOT_DONE" && (
                  <button className="w-1/3 px-2.5 py-1  rounded-lg bg-blue-500 hover:bg-blue-600 transition-colors"
                  onClick={() => continueClone("VOICE_DONE")}>
                    跳过
                  </button>
                )
              }
              {
                status.clone_status === "SEGMENTS_DONE" && (
                  <button className="w-1/3 px-2.5 py-1  rounded-lg bg-blue-500 hover:bg-blue-600 transition-colors"
                  onClick={() => continueClone("IMAGE_DONE")}>
                    跳过
                  </button>
                )
              }
              <label className="w-1/3  inline-flex items-center justify-center mx-2 px-2 py-2">
        
                {/* 3. 原生方框复选框 */}
                <input
                  type="checkbox"
                  checked={autoRun}
                  onChange={handleCheckboxChange}
                  // Tailwind 样式：rounded-md 是方角（带一点点圆润），text-blue-600 是选中后的对勾颜色
                  className="w-5 h-5 m-0 self-center rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                />

                {/* 4. 文本说明 */}
                <span className="px-1 text-s font-medium text-gray-500 whitespace-nowrap">
                  自动执行
                </span>
              </label>
            </div>
          )
        }
        </div>
        
      </div>
    </div>
  );
}
