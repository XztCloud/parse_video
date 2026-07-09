"use client";

import { CloneVoice, exportCloneVoice } from "@/lib/api";
import React, { useState, useRef } from "react";
import {
  PlayIcon,
  PauseIcon,
  SpeakerWaveIcon,
} from "@heroicons/react/24/solid";

interface ScriptVoiceProps {
  voices: CloneVoice[];
}

export default function VoiceList({ voices }: ScriptVoiceProps) {
  if (voices.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无音频数据</div>;
  }

  const audioRef = useRef<HTMLAudioElement | null>(null);

  // 已缓存的音频
  const audioCache = useRef<Map<number, string>>(new Map());

  // 当前播放的ObjectURL
  const currentUrlRef = useRef<string | null>(null);

  // requestAnimationFrame
  const animationRef = useRef<number | null>(null);

  // 当前播放ID
  const [playingId, setPlayingId] = useState<number | null>(null);

  // 当前正在加载
  const [loadingId, setLoadingId] = useState<number | null>(null);

  const [pause, setPause] = useState<boolean>(false);

  // 当前播放时间
  const [currentTime, setCurrentTime] = useState(0);

  // 总时长
  const [duration, setDuration] = useState(0);

  const getAudio = () => {
    if (audioRef.current) return audioRef.current;

    const audio = new Audio();

    audio.preload = "auto";

    audio.ontimeupdate = () => {
      setCurrentTime(audio.currentTime);
    };

    audio.onloadedmetadata = () => {
      setDuration(audio.duration);
    };

    audio.onended = () => {
      stopAudio();
    };

    audio.onerror = () => {
      stopAudio();
    };

    audioRef.current = audio;

    return audio;
  };

  const updateProgress = () => {
    const audio = audioRef.current;

    if (!audio) return;

    setCurrentTime(audio.currentTime);

    animationRef.current = requestAnimationFrame(updateProgress);
  };

  const stopAudio = () => {
    const audio = audioRef.current;

    if (!audio) return;

    audio.pause();

    audio.currentTime = 0;

    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }

    setPlayingId(null);

    setCurrentTime(0);

    setDuration(audio.duration || 0);
  };


  const fetchAndPlayAudio = async (id: number) => {
    const audio = getAudio();

    // 当前播放 -> 暂停
    if (playingId === id) {
      if (!audio) return;
      if (!pause) {
        audio.pause();

        // if (animationRef.current) {
        //   cancelAnimationFrame(animationRef.current);
        // }

        // setPlayingId(null);
        setPause(true);
      } else {
        audio.play()
        // if (animationRef.current) {
        //   cancelAnimationFrame(animationRef.current);
        // }
        setPause(false);
      }
      
      return;
    }
    setPause(false);
    // 先停止其它
    stopAudio();

    try {
      setLoadingId(id);

      let url: string;

      // 已缓存
      if (audioCache.current.has(id)) {
        url = audioCache.current.get(id)!;
      } else {
        const blob = await exportCloneVoice(id);

        url = URL.createObjectURL(blob);

        audioCache.current.set(id, url);
      }

      currentUrlRef.current = url;

      audio.src = url;

      await audio.play();

      setPlayingId(id);

      updateProgress();
    } catch (e) {
      console.error(e);

      stopAudio();
    } finally {
      setLoadingId(null);
    }
  };

  const handleSeek = (value: number) => {
    const audio = audioRef.current;

    if (!audio) return;

    audio.currentTime = value;

    setCurrentTime(value);
  };

  const formatTime = (time: number) => {
    if (!time || Number.isNaN(time)) return "00:00";

    const minute = Math.floor(time / 60);

    const second = Math.floor(time % 60);

    return `${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`;
  };

  return (
    <div className="space-y-4">
      {voices.map((voice) => {
        const isCurrent = playingId === voice.id;

        return (
          <div
            key={voice.id}
            className="relative pl-8 pb-6 border-l-2 border-blue-200 last:border-l-0 last:pb-0"
          >
            <div className="absolute left-[-9px] top-0 w-4 h-4 rounded-full bg-blue-500 border-2 border-white" />

            <div className="bg-white rounded-xl shadow border p-5">
              {/* 标题 */}
              <div className="flex justify-between items-center">
                <div>
                  <span className="text-lg font-bold text-gray-800">
                    {voice.role_name}
                  </span>

                  <span className="ml-4 px-2 py-1 rounded bg-blue-50 text-blue-600 text-sm">
                    {voice.voice_type}
                  </span>
                </div>

                <div className="text-gray-500 text-sm">{voice.duration}s</div>
              </div>

              {/* 文本 */}

              <div className="mt-4 text-gray-700 leading-7">{voice.text}</div>

              {/* 播放器 */}

              <div className="mt-5 flex items-center gap-4">
                {/* 播放按钮 */}

                <button
                  onClick={() => fetchAndPlayAudio(voice.id)}
                  disabled={loadingId === voice.id}
                  className="w-8 h-8 rounded-full bg-blue-500 hover:bg-blue-600 text-white flex items-center justify-center transition disabled:bg-gray-300"
                >
                  {loadingId === voice.id ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : isCurrent && !pause ? (
                    <PauseIcon className="w-4 h-4" />
                  ) : (
                    <PlayIcon className="w-4 h-4" />
                  )}
                </button>

                {/* 时间轴 */}

                <div className="flex-1">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>{isCurrent ? formatTime(currentTime) : "00:00"}</span>
                    <input
                    type="range"
                      min={0}
                      max={isCurrent ? duration : voice.duration}
                      step={0.01}
                      value={isCurrent ? currentTime : 0}
                      onChange={(e) => handleSeek(Number(e.target.value))}
                      disabled={!isCurrent}
                      className="
                                  mx-4
                                  w-full
                                  accent-blue-500
                                  cursor-pointer
                              "
                    />
                    <span>
                      {isCurrent
                        ? formatTime(duration)
                        : formatTime(voice.duration)}
                    </span>
                  </div>

                 
                </div>

                {/* 喇叭 */}

                {/* <SpeakerWaveIcon className="w-6 h-6 text-gray-400" /> */}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
