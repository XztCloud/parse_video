"use client";

import { CloneVoice, exportCloneVoice } from "@/lib/api";
import React, { useState, useRef } from "react";

interface ScriptVoiceProps {
  voices: CloneVoice[];
}

export default function VoiceList({ voices }: ScriptVoiceProps) {
  if (voices.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无音频数据</div>;
  }

  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExportPlot = async (cloneVoiceId: number)=> {
    try {
      const blob = await exportCloneVoice(cloneVoiceId);
      
      if (blob.type === 'application/json') { // 或者根据你的后端报错特征判断
        const errorText = await blob.text();
        const errorJson = JSON.parse(errorText);
        setError(errorJson.detail || "导出失败");
        return;
      }

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

  

  const fetchAndPlayAudio = async (cloneVoiceId: number) => {
    // 1. 如果已经加载过音频，直接控制播放/暂停
    console.log("当前播放的语音ID:", cloneVoiceId);
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
      } else {
        audioRef.current.play();
      }
      setIsPlaying(!isPlaying);
      return;
    }

    // 2. 第一次点击，从后端获取二进制流
    setLoading(true);
    try {
      const response = await exportCloneVoice(cloneVoiceId)
      
      // const blob = await exportCloneVoice(cloneVoiceId);
      
      if (response.type === 'application/json') { // 或者根据你的后端报错特征判断
        const errorText = await response.text();
        const errorJson = JSON.parse(errorText);
        setError(errorJson.detail || "导出失败");
        return;
      }


      // 将响应转化为 Blob (Binary Large Object)
      // const audioBlob = await response.blob();

      // 生成一个临时的本地 URL
      const audioUrl = URL.createObjectURL(response);
      objectUrlRef.current = audioUrl; // 留作后续销毁用

      // 创建音频对象并播放
      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onended = () => {
        setIsPlaying(false);
      };

      await audio.play();
      setIsPlaying(true);
    } catch (error) {
      console.error("音频加载或播放失败:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {voices.map((voice) => (
        <div
          key={voice.id}
          className="relative pl-8 pb-6 border-l-2 border-blue-200 last:border-l-0 last:pb-0"
        >
          <div className="absolute left-[-9px] top-0 w-4 h-4 rounded-full bg-blue-500 border-2 border-white" />
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <span className="text-lg text-gray-800 font-bold">
              {voice.role_name}
            </span>
            <span className="px-2 py-1 bg-gray-100 rounded text-base text-gray-600">
              {voice.voice_type}
            </span>
            <div className="px-2 border">
              <h3>安全音频播放器 (Blob 模式)</h3>
              <button onClick={() => fetchAndPlayAudio(voice.id)} disabled={loading}>
                {loading ? "加载中..." : isPlaying ? "暂停" : "获取并播放"}
              </button>
            </div>
          </div>

        </div>
      ))}
    </div>
  );
}

// export const SecureAudioPlayer: React.FC<SecureAudioPlayerProps> = ({
//   audioId,
// }) => {


  

//   // 组件销毁时，释放内存中的 Object URL
//   React.useEffect(() => {
//     return () => {
//       if (objectUrlRef.current) {
//         URL.revokeObjectURL(objectUrlRef.current);
//       }
//     };
//   }, []);

//   return (
//     <div
//       style={{ padding: "20px", border: "1px solid #ccc", borderRadius: "8px" }}
//     >
//       <h3>安全音频播放器 (Blob 模式)</h3>
//       <button onClick={fetchAndPlayAudio} disabled={loading}>
//         {loading ? "加载中..." : isPlaying ? "暂停" : "获取并播放"}
//       </button>
//     </div>
//   );
// };
