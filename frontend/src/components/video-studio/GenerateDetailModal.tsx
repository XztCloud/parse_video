"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getCloneScript, getCloneStatus, clonePhase, exportCloneVoice, getImageUrl, getVideoUrl } from "@/lib/api";

interface GenerateDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  cloneScriptId: number | null;
  cloneStatus?: string;
  /** 是否为人工控制模式 */
  isManual?: boolean;
  /** 刷新父组件数据 */
  onRefresh?: () => Promise<void>;
}

const STATUS_LABELS: Record<string, string> = {
  VOICE: '配音生成中', VOICE_DONE: '配音完成',
  IMAGE: '生图中', IMAGE_DONE: '生图完成',
  FRAME: '参考帧生成中', FRAME_DONE: '参考帧完成',
  SEGMENT_VIDEO: '分镜视频生成中', SEGMENT_VIDEO_DONE: '分镜视频完成',
  MERGE_VIDEO: '合并成片中', DONE: '已完成', FAILED: '失败',
};

const STATUS_TABS: { key: string; label: string; icon: string; nextStep?: number; doneStatus: string }[] = [
  { key: 'voice', label: '配音', icon: '🎙', nextStep: 4, doneStatus: 'VOICE_DONE' },
  { key: 'images', label: '角色/场景图', icon: '🖼', nextStep: 5, doneStatus: 'IMAGE_DONE' },
  { key: 'frames', label: '参考帧', icon: '🎬', nextStep: 6, doneStatus: 'FRAME_DONE' },
  { key: 'segment_videos', label: '分镜视频', icon: '📹', nextStep: 7, doneStatus: 'SEGMENT_VIDEO_DONE' },
  { key: 'video', label: '成片', icon: '🎞', doneStatus: 'DONE' },
];

function getStatusStep(status: string): number {
  const map: Record<string, number> = {
    VOICE: 3, VOICE_DONE: 3,
    IMAGE: 4, IMAGE_DONE: 4,
    FRAME: 5, FRAME_DONE: 5,
    SEGMENT_VIDEO: 6, SEGMENT_VIDEO_DONE: 6,
    MERGE_VIDEO: 7, DONE: 7,
  };
  return map[status] || 0;
}

export default function GenerateDetailModal({ isOpen, onClose, cloneScriptId, cloneStatus, isManual = false, onRefresh }: GenerateDetailModalProps) {
  const [detail, setDetail] = useState<any>(null);
  const [currentStatus, setCurrentStatus] = useState(cloneStatus || '');
  const [activeTab, setActiveTab] = useState('voice');
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Audio playback
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioCache = useRef<Map<number, string>>(new Map());
  const currentUrlRef = useRef<string | null>(null);
  const animationRef = useRef<number | null>(null);
  const [playingId, setPlayingId] = useState<number | null>(null);
  const [loadingAudioId, setLoadingAudioId] = useState<number | null>(null);
  const [pause, setPause] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);

  const getAudio = () => {
    if (audioRef.current) return audioRef.current;
    const audio = new Audio();
    audio.preload = "auto";
    audio.ontimeupdate = () => setCurrentTime(audio.currentTime);
    audio.onloadedmetadata = () => setAudioDuration(audio.duration);
    audio.onended = () => stopAudio();
    audio.onerror = () => stopAudio();
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
    if (animationRef.current) cancelAnimationFrame(animationRef.current);
    setPlayingId(null);
    setCurrentTime(0);
    setAudioDuration(audio.duration || 0);
  };

  const fetchAndPlayAudio = async (id: number) => {
    const audio = getAudio();
    if (playingId === id) {
      if (!pause) { audio.pause(); setPause(true); }
      else { audio.play(); setPause(false); }
      return;
    }
    setPause(false);
    stopAudio();
    try {
      setLoadingAudioId(id);
      let url: string;
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
      console.error('播放音频失败', e);
      stopAudio();
    } finally {
      setLoadingAudioId(null);
    }
  };

  const formatAudioTime = (t: number) => {
    if (!t || Number.isNaN(t)) return '00:00';
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  // 关闭时清理音频
  useEffect(() => {
    if (!isOpen) {
      stopAudio();
      audioCache.current.forEach(url => URL.revokeObjectURL(url));
      audioCache.current.clear();
    }
  }, [isOpen]);

  // 打开新详情时重置状态
  useEffect(() => {
    if (isOpen && cloneScriptId) {
      setCurrentStatus(cloneStatus || '');
      setDetail(null);
      setActiveTab('voice');
      stopAudio();
    }
  }, [isOpen, cloneScriptId, cloneStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  // 拉取详情
  const fetchDetail = useCallback(async () => {
    if (!cloneScriptId) return;
    try {
      const data = await getCloneScript(cloneScriptId);
      setDetail(data);
      if (data.clone_status) setCurrentStatus(data.clone_status);
      const step = getStatusStep(data.clone_status || currentStatus);
      if (step >= 5) setActiveTab('frames');
      else if (step >= 4) setActiveTab('images');
      else if (step >= 3) setActiveTab('voice');
    } catch (e) {
      console.error('拉取生成详情失败', e);
    }
  }, [cloneScriptId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 轮询状态 - 任务进行中 3 秒轮询
  useEffect(() => {
    if (!isOpen || !cloneScriptId) return;
    fetchDetail();
    const pollInterval = (!currentStatus.endsWith('_DONE') && currentStatus !== 'DONE' && currentStatus !== 'FAILED') ? 3000 : 10000;
    pollRef.current = setInterval(async () => {
      try {
        const st = await getCloneStatus(cloneScriptId);
        setCurrentStatus(st.clone_status);
        const data = await getCloneScript(cloneScriptId);
        setDetail(data);
      } catch {}
    }, pollInterval);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [isOpen, cloneScriptId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 继续下一步
  const handleContinue = useCallback(async () => {
    if (!cloneScriptId) return;
    const matchedTab = STATUS_TABS.find(t => t.doneStatus === currentStatus);
    if (!matchedTab?.nextStep) return;
    setActionLoading(true);
    try {
      await clonePhase(cloneScriptId, matchedTab.nextStep, false);
    } catch (e) {
      console.error('推进步骤失败', e);
    } finally {
      setActionLoading(false);
      if (onRefresh) await onRefresh();
    }
  }, [cloneScriptId, currentStatus, onRefresh]);

  if (!isOpen || !cloneScriptId) return null;

  const step = getStatusStep(currentStatus);
  const isDone = currentStatus === 'DONE';
  const isFailed = currentStatus === 'FAILED';
  const currentTab = STATUS_TABS.find(t => t.key === activeTab);
  // 判断当前状态是否某个步骤已完成且有下一步
  const matchedTab = STATUS_TABS.find(t => t.doneStatus === currentStatus);
  const canContinue = isManual && !isDone && !isFailed && !!matchedTab?.nextStep;

  const voices = detail?.voices || [];
  const images = detail?.images || [];
  const frames = detail?.frames || [];
  const segmentVideos = detail?.segment_videos || [];
  const video = detail?.video;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden modal-in">
        {/* Header */}
        <div className="p-6 border-b border-slate-200 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-pink-500 to-rose-500 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-800">生成资产详情</h3>
              <p className="text-sm text-slate-500">
                {STATUS_LABELS[currentStatus] || currentStatus}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
            <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress bar - 仅在进行中步骤显示 */}
        {!isDone && !isFailed && !currentStatus.endsWith('_DONE') && (
          <div className="px-6 pt-4">
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-pink-500 to-rose-500 rounded-full progress-animated transition-all duration-500"
                style={{ width: `${detail?.clone_progress || 0}%` }} />
            </div>
            {/* Step indicators */}
            <div className="flex items-center justify-between mt-3 text-xs">
              {STATUS_TABS.map((t, i) => {
                const tabStep = getStatusStep(t.doneStatus);
                const isReached = step > tabStep || currentStatus === t.doneStatus;
                return (
                  <span key={t.key} className={`flex items-center gap-1 ${isReached ? 'text-pink-600 font-medium' : 'text-slate-400'}`}>
                    {isReached ? '✅' : step >= tabStep - 1 ? '🔄' : '⏳'} {t.label}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="px-6 pt-4 border-b border-slate-200 flex gap-4 overflow-x-auto">
          {STATUS_TABS.map(t => {
            const count = t.key === 'voice' ? voices.length : t.key === 'images' ? images.length : t.key === 'frames' ? frames.length : t.key === 'segment_videos' ? segmentVideos.length : video ? 1 : 0;
            return (
              <button key={t.key} onClick={() => setActiveTab(t.key)}
                className={`pb-3 border-b-2 font-medium text-sm whitespace-nowrap flex items-center gap-1.5 ${
                  activeTab === t.key ? 'border-pink-500 text-pink-600' : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}>
                {t.icon} {t.label}
                {count > 0 && <span className="px-1.5 py-0.5 bg-slate-100 text-slate-500 text-xs rounded-full">{count}</span>}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="overflow-y-auto max-h-[calc(85vh-280px)] p-6">
          {activeTab === 'voice' && (
            <div className="space-y-3">
              {voices.length === 0 ? (
                <p className="text-center text-slate-400 py-8">暂无配音数据</p>
              ) : voices.map((v: any) => {
                const isCurrent = playingId === v.id;
                return (
                  <div key={v.id} className="p-4 bg-slate-50 rounded-xl border border-slate-200/60">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-800 text-sm">{v.role_name}</span>
                        <span className="text-xs text-slate-400">{v.duration?.toFixed(1)}s</span>
                      </div>
                      <span className="text-xs text-slate-400">{v.voice_type}</span>
                    </div>
                    <p className="text-xs text-slate-500 mb-3">{v.text}</p>
                    {/* 播放器 */}
                    <div className="flex items-center gap-3">
                      <button onClick={() => fetchAndPlayAudio(v.id)} disabled={loadingAudioId === v.id}
                        className="w-8 h-8 rounded-full bg-pink-500 hover:bg-pink-600 text-white flex items-center justify-center transition disabled:bg-slate-300 flex-shrink-0">
                        {loadingAudioId === v.id ? (
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : isCurrent && !pause ? (
                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
                        ) : (
                          <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                        )}
                      </button>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                          <span className="tabular-nums w-10">{isCurrent ? formatAudioTime(currentTime) : '00:00'}</span>
                          <input type="range" min={0} max={isCurrent ? audioDuration : v.duration} step={0.01}
                            value={isCurrent ? currentTime : 0}
                            onChange={(e) => { if (audioRef.current) { audioRef.current.currentTime = Number(e.target.value); setCurrentTime(Number(e.target.value)); } }}
                            disabled={!isCurrent}
                            className="flex-1 accent-pink-500 cursor-pointer" />
                          <span className="tabular-nums w-10 text-right">{isCurrent ? formatAudioTime(audioDuration) : formatAudioTime(v.duration)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {(activeTab === 'images' || activeTab === 'frames') && (() => {
            const items = activeTab === 'images' ? images : frames;
            return items.length === 0 ? (
              <p className="text-center text-slate-400 py-8">暂无数据</p>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                {items.map((img: any) => (
                  <div key={img.id} className="bg-white rounded-xl border border-slate-200/60 overflow-hidden shadow-sm">
                    <div className="bg-slate-100 flex items-center justify-center overflow-hidden">
                      <img src={getImageUrl(img.category, img.id)} alt={img.name} className="w-full object-contain" loading="lazy" />
                    </div>
                    <div className="p-3">
                      <p className="text-sm font-semibold text-slate-800 truncate">{img.name}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{img.desc || img.prompt?.slice(0, 40)}</p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${img.status === 'SUCCESS' ? 'bg-green-50 text-green-600' : img.status === 'PROCESSING' ? 'bg-yellow-50 text-yellow-600' : 'bg-slate-100 text-slate-500'}`}>
                          {img.status === 'SUCCESS' ? '已完成' : img.status === 'PROCESSING' ? '生成中' : img.status}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}

          {activeTab === 'segment_videos' && (
            <div className="space-y-3">
              {segmentVideos.length === 0 ? (
                <p className="text-center text-slate-400 py-8">暂无分镜视频</p>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {segmentVideos.map((sv: any) => (
                    <div key={sv.id} className="bg-white rounded-xl border border-slate-200/60 overflow-hidden shadow-sm">
                      <div className="aspect-video bg-slate-900 flex items-center justify-center">
                        {sv.status === 'SUCCESS' ? (
                          <video src={getVideoUrl('segment_video', sv.id)} controls className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-slate-500 text-sm">{sv.status === 'PROCESSING' ? '生成中...' : '待生成'}</span>
                        )}
                      </div>
                      <div className="p-3">
                        <p className="text-sm font-semibold text-slate-800">{sv.name}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'video' && (
            <div>
              {!video ? (
                <p className="text-center text-slate-400 py-8">暂无成片</p>
              ) : (
                <div className="max-w-md mx-auto">
                  <div className="aspect-video bg-slate-900 rounded-xl overflow-hidden flex items-center justify-center">
                    <video src={getVideoUrl('merged', video.id)} controls className="w-full h-full" />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50/50 flex justify-between items-center">
          <button onClick={onClose} className="px-5 py-2.5 text-slate-600 hover:bg-slate-200 rounded-xl transition-colors text-sm font-medium">
            关闭
          </button>
          {canContinue && (
            <button onClick={handleContinue} disabled={actionLoading}
              className="px-6 py-2.5 bg-gradient-to-r from-pink-500 to-rose-500 text-white rounded-xl text-sm font-medium shadow-md hover:shadow-lg transition-all disabled:opacity-50">
              {actionLoading ? '推进中...' : '继续'}
            </button>
          )}
          {isFailed && (
            <span className="text-sm text-red-500 font-medium">❌ 生成失败</span>
          )}
        </div>
      </div>
    </div>
  );
}
