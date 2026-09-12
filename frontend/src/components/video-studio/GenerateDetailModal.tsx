"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getCloneScript, clonePhase, exportCloneVoice, regenerate, getRegenerateStatus, getImageUrl, getVideoUrl } from "@/lib/api";

interface GenerateDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  cloneScriptId: number | null;
  cloneStatus?: string;
  /** 是否为人工控制模式 */
  isManual?: boolean;
  /** 刷新父组件数据 */
  onRefresh?: () => Promise<void>;
  /** 外部接管「继续下一步」：提供时 Modal 的继续按钮调用此回调，而非自动 clonePhase */
  onManualContinue?: () => void;
  /** 是否从历史记录打开：为 true 时「继续」直接调用 clonePhase 推进，而非恢复生成流程 */
  isHistory?: boolean;
}

const STATUS_LABELS: Record<string, string> = {
  VOICE: '配音生成中', VOICE_DONE: '配音完成',
  IMAGE: '生图中', IMAGE_DONE: '生图完成',
  FRAME: '参考帧生成中', FRAME_DONE: '参考帧完成',
  SEGMENT_VIDEO: '分镜视频生成中', SEGMENT_VIDEO_DONE: '分镜视频完成',
  MERGE_VIDEO: '合并成片中', MERGE_VIDEO_DONE: '已完成', FAILED: '失败',
};

const STATUS_TABS: { key: string; label: string; icon: string; nextStep?: number; doneStatus: string }[] = [
  { key: 'voice', label: '配音', icon: '🎙', nextStep: 4, doneStatus: 'VOICE_DONE' },
  { key: 'images', label: '角色/场景图', icon: '🖼', nextStep: 5, doneStatus: 'IMAGE_DONE' },
  { key: 'frames', label: '参考帧', icon: '🎬', nextStep: 6, doneStatus: 'FRAME_DONE' },
  { key: 'segment_videos', label: '分镜视频', icon: '📹', nextStep: 7, doneStatus: 'SEGMENT_VIDEO_DONE' },
  { key: 'video', label: '成片', icon: '🎞', doneStatus: 'MERGE_VIDEO_DONE' },
];

// 页面 Tab：剧本/分镜为只读展示，其余为生成资产
const ALL_TABS = [
  { key: 'script', label: '剧本内容', icon: '📝' },
  { key: 'storyboard', label: '分镜脚本', icon: '🎬' },
  { key: 'voice', label: '配音', icon: '🎙' },
  { key: 'images', label: '角色/场景图', icon: '🖼' },
  { key: 'frames', label: '参考帧', icon: '🎬' },
  { key: 'segment_videos', label: '分镜视频', icon: '📹' },
  { key: 'video', label: '成片', icon: '🎞' },
];

function getStatusStep(status: string): number {
  const map: Record<string, number> = {
    VOICE: 3, VOICE_DONE: 3,
    IMAGE: 4, IMAGE_DONE: 4,
    FRAME: 5, FRAME_DONE: 5,
    SEGMENT_VIDEO: 6, SEGMENT_VIDEO_DONE: 6,
    MERGE_VIDEO: 7, MERGE_VIDEO_DONE: 7,
  };
  return map[status] || 0;
}

// generate_flow_status 处于这些「已完成」状态时，显示重试按钮
const RETRYABLE_STATUS = ['VOICE_DONE', 'IMAGE_DONE', 'FRAME_DONE', 'SEGMENT_VIDEO_DONE', 'MERGE_VIDEO_DONE'];
const RETRY_LABELS: Record<string, string> = {
  VOICE_DONE: '配音', IMAGE_DONE: '生图', FRAME_DONE: '参考帧',
  SEGMENT_VIDEO_DONE: '分镜视频', MERGE_VIDEO_DONE: '合并成片',
};

export default function GenerateDetailModal({ isOpen, onClose, cloneScriptId, cloneStatus, isManual = false, onRefresh, onManualContinue, isHistory = false }: GenerateDetailModalProps) {
  const [detail, setDetail] = useState<any>(null);
  const [currentStatus, setCurrentStatus] = useState(cloneStatus || '');
  const [activeTab, setActiveTab] = useState('voice');
  const [actionLoading, setActionLoading] = useState(false);
  const [retryLoading, setRetryLoading] = useState(false);
  const [regeneratingId, setRegeneratingId] = useState<number | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Audio playback
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioCache = useRef<Map<number, string>>(new Map());
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

  const stopAudio = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
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
      audio.src = url;
      await audio.play();
      setPlayingId(id);
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
      // 优先使用 generate_flow_status（渲染阶段），回退到 clone_status
      const flowStatus = data.generate_flow_status || data.clone_status;
      if (flowStatus) setCurrentStatus(flowStatus);
      const step = getStatusStep(flowStatus || currentStatus);
      if (step >= 5) setActiveTab('frames');
      else if (step >= 4) setActiveTab('images');
      else if (step >= 3) setActiveTab('voice');
    } catch (e) {
      console.error('拉取生成详情失败', e);
    }
  }, [cloneScriptId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 轮询状态 - 任务进行中 3 秒轮询（先立即拉一次，避免等首 tick）
  useEffect(() => {
    if (!isOpen || !cloneScriptId) return;
    fetchDetail();
    const finished = currentStatus === 'MERGE_VIDEO_DONE' || currentStatus === 'FAILED' || currentStatus.endsWith('_DONE');
    const pollInterval = finished ? 10000 : 3000;
    pollRef.current = setInterval(async () => {
      try {
        const data = await getCloneScript(cloneScriptId);
        setDetail(data);
        setCurrentStatus(data.generate_flow_status || data.clone_status || '');
      } catch {}
    }, pollInterval);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [isOpen, cloneScriptId, currentStatus, fetchDetail]); // eslint-disable-line react-hooks/exhaustive-deps

  // 继续下一步
  const handleContinue = useCallback(async () => {
    // 从历史记录打开：不依赖父组件的 waitManual，直接推进到下一阶段
    if (isHistory) {
      if (!cloneScriptId) return;
      const matchedTab = STATUS_TABS.find(t => t.doneStatus === currentStatus);
      if (!matchedTab?.nextStep) return;
      setActionLoading(true);
      try {
        await clonePhase(cloneScriptId, matchedTab.nextStep, false);
      } catch (e: any) {
        console.error('推进步骤失败', e);
        alert(e?.response?.data?.detail || '推进步骤失败，请稍后重试');
      } finally {
        setActionLoading(false);
        if (onRefresh) await onRefresh();
      }
      return;
    }
    // 生成流程中：交由父组件恢复 waitManual 暂停的流程
    if (onManualContinue) {
      onManualContinue();
    }
  }, [isHistory, cloneScriptId, currentStatus, onRefresh, onManualContinue]);

  // 重试当前阶段：按 generate_flow_status 重新触发对应 step 的生成
  const handleRetry = useCallback(async () => {
    if (!cloneScriptId) return;
    const retryStep = getStatusStep(currentStatus);
    if (!retryStep) return;
    setRetryLoading(true);
    try {
      await clonePhase(cloneScriptId, retryStep, false);
    } catch (e: any) {
      console.error('重试失败', e);
      alert(e?.response?.data?.detail || '重试失败，请稍后重试');
    } finally {
      setRetryLoading(false);
      if (onRefresh) await onRefresh();
    }
  }, [cloneScriptId, currentStatus, onRefresh]);

  // 重新生成单张图片：PATCH 触发后轮询直到 SUCCESS
  const handleRegenerateImage = useCallback(async (img: any) => {
    if (!img) return;
    setRegeneratingId(img.id);
    try {
      // width/height/seed 传 null，后端会回填原图参数并取新随机种子
      await regenerate(img.category, img.id, { prompt: img.prompt, width: null, height: null, seed: null });
      const deadline = Date.now() + 120000;
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 2000));
        const st = await getRegenerateStatus(img.category, img.id);
        if (st.status === 'SUCCESS') break;
        if (st.status === 'FAILED') { console.error('图片重新生成失败', st); break; }
      }
      await fetchDetail();
    } catch (e: any) {
      console.error('重新生成图片失败', e);
      alert(e?.response?.data?.detail || '重新生成图片失败，请稍后重试');
    } finally {
      setRegeneratingId(null);
    }
  }, [fetchDetail]);

  // 状态判断
  const isFailed = currentStatus === 'FAILED';
  const step = getStatusStep(currentStatus);
  const isDone = currentStatus === 'MERGE_VIDEO_DONE';
  const matchedTab = STATUS_TABS.find(t => t.doneStatus === currentStatus);
  const canContinue = isManual && !isDone && !isFailed && !!matchedTab?.nextStep;
  const canRetry = RETRYABLE_STATUS.includes(currentStatus) && !isFailed;

  if (!isOpen || !cloneScriptId) return null;

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
                style={{ width: `${detail?.generate_flow_progress || detail?.clone_progress || 0}%` }} />
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
          {ALL_TABS.map(t => {
            const count = t.key === 'voice' ? voices.length
              : t.key === 'images' ? images.length
              : t.key === 'frames' ? frames.length
              : t.key === 'segment_videos' ? segmentVideos.length
              : t.key === 'video' ? (video ? 1 : 0)
              : t.key === 'storyboard' ? (detail?.segments?.length || 0)
              : 0;
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
          {/* 剧本内容 - 只读 */}
          {activeTab === 'script' && (() => {
            const pointer = detail?.clone_parse_pointer;
            const plotScript = detail?.clone_parse_script?.plot_script || [];
            const roleLibrary = pointer?.role_library || [];
            const sceneLibrary = pointer?.scene_library || [];
            const globalStyle = pointer?.global_style;
            const core = pointer?.core_shell_point;
            return (
              <div className="space-y-6">
                {roleLibrary.length > 0 && (
                  <div>
                    <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                      <span className="w-1 h-5 bg-gradient-to-b from-indigo-500 to-purple-500 rounded-full" /> 角色信息
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {roleLibrary.map((r: any, i: number) => (
                        <div key={i} className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="font-semibold text-slate-800">{r.role_name}</span>
                            <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">{r.gender === 'male' ? '男' : '女'}</span>
                            <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">约{r.age}岁</span>
                          </div>
                          {r.effect && <p className="text-sm text-slate-600 mb-1">{r.effect}</p>}
                          {r.voice_style_guide && <p className="text-xs text-slate-400">🎙 {r.voice_style_guide}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {sceneLibrary.length > 0 && (
                  <div>
                    <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                      <span className="w-1 h-5 bg-gradient-to-b from-purple-500 to-pink-500 rounded-full" /> 场景信息
                    </h4>
                    <div className="space-y-3">
                      {sceneLibrary.map((s: any, i: number) => (
                        <div key={i} className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                          <h5 className="font-semibold text-slate-800 mb-1">{s.scene_name}</h5>
                          <p className="text-sm text-slate-600 mb-1">{s.environment_description}</p>
                          {s.color_grading && <p className="text-xs text-slate-400">🎨 {s.color_grading}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {globalStyle?.global_style_suffix && (
                  <div>
                    <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                      <span className="w-1 h-5 bg-gradient-to-b from-pink-500 to-rose-500 rounded-full" /> 全局风格
                    </h4>
                    <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                      <p className="text-sm text-slate-600">{globalStyle.global_style_suffix}</p>
                    </div>
                  </div>
                )}
                {core && (
                  <div>
                    <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                      <span className="w-1 h-5 bg-gradient-to-b from-rose-500 to-orange-500 rounded-full" /> 推广信息
                    </h4>
                    <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60 space-y-2">
                      {core.user_pain_point && (
                        <div><span className="text-xs font-medium text-slate-500">用户痛点</span><p className="text-sm text-slate-600">{core.user_pain_point}</p></div>
                      )}
                      {Array.isArray(core.product_usp) && core.product_usp.length > 0 && (
                        <div>
                          <span className="text-xs font-medium text-slate-500">产品卖点</span>
                          <ul className="text-sm text-slate-600 list-disc list-inside">{core.product_usp.map((u: string, i: number) => <li key={i}>{u}</li>)}</ul>
                        </div>
                      )}
                      {core.hook_trigger && (
                        <div><span className="text-xs font-medium text-slate-500">钩子设计</span><p className="text-sm text-slate-600">{core.hook_trigger}</p></div>
                      )}
                      {Array.isArray(core.keywords_to_include) && core.keywords_to_include.length > 0 && (
                        <div>
                          <span className="text-xs font-medium text-slate-500">关键词</span>
                          <div className="flex flex-wrap gap-2 mt-1">{core.keywords_to_include.map((k: string, i: number) => <span key={i} className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-xs rounded">{k}</span>)}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {plotScript.length > 0 && (
                  <div>
                    <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                      <span className="w-1 h-5 bg-gradient-to-b from-indigo-500 to-purple-500 rounded-full" /> 剧情大纲
                    </h4>
                    <div className="space-y-4">
                      {plotScript.map((seg: any, i: number) => (
                        <div key={i} className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="px-2 py-0.5 bg-indigo-100 text-indigo-600 text-xs rounded-full font-medium">段落 {i + 1}</span>
                            {seg.paragraph_theme && <span className="text-sm font-semibold text-slate-800">{seg.paragraph_theme}</span>}
                          </div>
                          {seg.screen_description && <p className="text-sm text-slate-600 mb-3 leading-relaxed">{seg.screen_description}</p>}
                          {Array.isArray(seg.actor_lines) && seg.actor_lines.length > 0 && (
                            <div className="border-t border-slate-200/70 pt-2 space-y-1">
                              {seg.actor_lines.map((a: any, li: number) => (
                                <p key={li} className="text-xs text-slate-500">
                                  <span className="font-medium text-slate-600">{a.role_name || '?'}：</span>
                                  {a.lines}
                                  {a.audio_style && <span className="ml-2 text-slate-400">（{a.audio_style}）</span>}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {!pointer && plotScript.length === 0 && <p className="text-center text-slate-400 py-8">暂无剧本内容</p>}
              </div>
            );
          })()}

          {/* 分镜脚本 - 只读 */}
          {activeTab === 'storyboard' && (() => {
            const segs = detail?.segments || [];
            if (segs.length === 0) return <p className="text-center text-slate-400 py-8">暂无分镜数据</p>;
            return (
              <div className="space-y-4">
                {segs.map((seg: any, idx: number) => {
                  const start = formatAudioTime(seg.start_time);
                  const end = formatAudioTime(seg.end_time);
                  const dial = Array.isArray(seg.dialogue) ? seg.dialogue : [];
                  return (
                    <div key={seg.id || idx} className="p-4 bg-slate-50/80 rounded-2xl border border-slate-200/60">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="px-2 py-0.5 bg-pink-100 text-pink-600 text-xs rounded-full font-medium">分镜 {idx + 1}</span>
                        <span className="text-xs text-slate-400">{start} - {end}</span>
                        {seg.segment_type && <span className="text-xs text-slate-400">· {seg.segment_type}</span>}
                      </div>
                      {seg.shot_description && <p className="text-sm text-slate-600 leading-relaxed">{seg.shot_description}</p>}
                      {dial.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-200/70 space-y-1">
                          {dial.map((d: any, di: number) => (
                            <p key={di} className="text-xs text-slate-500">
                              <span className="font-medium text-slate-600">{d.speaker || d.role_name || '角色'}：</span>
                              {d.text || d.lines || ''}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}

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
            // 角色/场景图：IMAGE_DONE 时提供单张图片重试
            const showImgRetry = activeTab === 'images' && currentStatus === 'IMAGE_DONE';
            return items.length === 0 ? (
              <p className="text-center text-slate-400 py-8">暂无数据</p>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                {items.map((img: any) => {
                  const isRegenerating = showImgRetry && regeneratingId === img.id;
                  return (
                    <div key={img.id} className="bg-white rounded-xl border border-slate-200/60 overflow-hidden shadow-sm">
                      <div className="bg-slate-100 flex items-center justify-center overflow-hidden relative">
                        <img src={`${getImageUrl(img.category, img.id)}?v=${img.version}`} alt={img.name} className="w-full object-contain" loading="lazy" />
                        {showImgRetry && img.status !== 'PROCESSING' && (
                          <button
                            onClick={() => handleRegenerateImage(img)}
                            disabled={regeneratingId !== null}
                            title="重新生成此图片"
                            className="absolute bottom-2 right-2 w-8 h-8 rounded-full bg-white/90 hover:bg-white shadow-md flex items-center justify-center text-slate-600 transition-colors disabled:opacity-50">
                            {isRegenerating ? (
                              <span className="w-4 h-4 border-2 border-pink-500 border-t-transparent rounded-full animate-spin inline-block" />
                            ) : (
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                              </svg>
                            )}
                          </button>
                        )}
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
                  );
                })}
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
          <div className="flex items-center gap-3">
            {canRetry && (
              <button onClick={handleRetry} disabled={retryLoading || actionLoading}
                className="px-6 py-2.5 text-slate-600 border border-slate-300 bg-white hover:bg-slate-100 rounded-xl text-sm font-medium transition-colors disabled:opacity-50">
                {retryLoading ? '重试中...' : `重试${RETRY_LABELS[currentStatus] || ''}`}
              </button>
            )}
            {canContinue && (
              <button onClick={handleContinue} disabled={actionLoading || retryLoading}
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
    </div>
  );
}
