"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { clonePlot, clonePhase, getCloneStatus, getCloneCapabilities } from "@/lib/api";
import { GenerateHistoryItem, ScriptItem } from "./data";
import GenerateDetailModal from "./GenerateDetailModal";

interface GenerateVideoTabProps {
  history: GenerateHistoryItem[];
  onRefresh?: () => Promise<void>;
  clonedScripts?: ScriptItem[];
  novelScripts?: ScriptItem[];
  /** 从详情弹窗跳转时预选的剧本（复制/小说来源），需用户再点“开始生成视频” */
  preselect?: { sourceType: 'copy' | 'novel'; scriptId: number } | null;
  /** 当前账号是否已激活：未激活点「开始生成视频」时弹框提示（后端亦有兜底拦截） */
  isActive?: boolean;
}

export default function GenerateVideoTab({ history, onRefresh, clonedScripts, novelScripts, preselect, isActive = true }: GenerateVideoTabProps) {
  const [showProgress, setShowProgress] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailCloneId, setDetailCloneId] = useState<number | null>(null);
  const [detailCloneStatus, setDetailCloneStatus] = useState('');
  const [genSource, setGenSource] = useState<'copy' | 'novel'>('copy');
  const [selectedScript, setSelectedScript] = useState<number>(1);
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [style, setStyle] = useState('真实摄影');
  const [method, setMethod] = useState<'cloud' | 'local'>('cloud');
  const [flowControl, setFlowControl] = useState('人工控制');
  // docker 部署无本地 comfy，仅允许云端；默认保守禁用，能力接口返回后再放开
  const [allowLocalComfy, setAllowLocalComfy] = useState(false);

  // 拉取生成能力：docker 部署下仅允许「云端 API 生成」
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const caps = await getCloneCapabilities();
        if (cancelled) return;
        setAllowLocalComfy(caps.allow_local_comfy);
        if (!caps.allow_local_comfy) setMethod('cloud');
      } catch {
        // 拉取失败保守处理：只允许云端
        if (!cancelled) setAllowLocalComfy(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // 取消标志：点击关闭/取消时置 true，用于中断 startGenerate 流程
  const cancelledRef = useRef(false);
  // 标记弹窗来源：'generate'=startGenerate 打开，'history'=历史记录打开
  const modalSourceRef = useRef<'generate' | 'history'>('generate');

  // Generation state
  const [totalPercent, setTotalPercent] = useState(0);
  const [currentStepText, setCurrentStepText] = useState('');
  const manualContinueResolveRef = useRef<(() => void) | null>(null);
  const manualCancelRef = useRef<(() => void) | null>(null);

  const scripts: ScriptItem[] = genSource === 'copy'
    ? (clonedScripts && clonedScripts.length > 0 ? clonedScripts : [])
    : (novelScripts && novelScripts.length > 0 ? novelScripts : []);

  // 来源/列表变化后，若当前选中项不在列表内，自动选中第一个，避免默认 id 落空。
  // 声明在预选 effect 之前，保证跳转预选（后执行）能覆盖这里的兜底选中。
  useEffect(() => {
    if (scripts.length > 0 && !scripts.some(s => s.id === selectedScript)) {
      setSelectedScript(scripts[0].id);
    }
  }, [scripts, selectedScript]);

  // 从详情弹窗跳转时预选剧本：仅应用一次，之后用户可自由切换
  const appliedPreselectRef = useRef<typeof preselect>(null);
  useEffect(() => {
    if (preselect && preselect !== appliedPreselectRef.current) {
      appliedPreselectRef.current = preselect;
      setGenSource(preselect.sourceType);
      setSelectedScript(preselect.scriptId);
    }
  }, [preselect]);

  // Carousel state
  const scrollRef = useRef<HTMLDivElement>(null);
  const [genCurrentPage, setGenCurrentPage] = useState(0);
  const genItemsPerPage = 4;
  const genTotalPages = Math.max(1, Math.ceil(scripts.length / genItemsPerPage));
  const genGetPaginationDots = (): number[] => {
    if (genTotalPages <= 3) return Array.from({ length: genTotalPages }, (_, i) => i);
    if (genCurrentPage <= 1) return [0, 1, 2];
    if (genCurrentPage >= genTotalPages - 2) return [genTotalPages - 3, genTotalPages - 2, genTotalPages - 1];
    return [genCurrentPage - 1, genCurrentPage, genCurrentPage + 1];
  };

  // 根据 clone_progress 推断重试步骤
  const getRetryStep = (progress: number): number => {
    if (progress < 1) return 0;       // 未开始
    if (progress <= 10) return 3;     // VOICE:       1 ~ 10
    if (progress <= 30) return 4;     // IMAGE:      11 ~ 30
    if (progress <= 50) return 5;     // FRAME:      31 ~ 50
    if (progress <= 90) return 6;     // SEGMENT_VIDEO: 51 ~ 90
    return 7;                         // MERGE_VIDEO: 91 ~ 100
  };
  const RETRY_LABELS: Record<number, string> = { 3: '配音', 4: '生图', 5: '参考帧', 6: '分镜视频', 7: '合并成片' };
  const [retryLoading, setRetryLoading] = useState<number | null>(null);

  const handleRetry = useCallback(async (cloneScriptId: number, progress: number) => {
    const step = getRetryStep(progress);
    if (!step) return;
    setRetryLoading(cloneScriptId);
    try {
      await clonePhase(cloneScriptId, step, false);
      if (onRefresh) await onRefresh();
    } catch (e: any) {
      console.error('重试失败', e);
      alert(e?.response?.data?.detail || '重试失败，请稍后重试');
    } finally {
      setRetryLoading(null);
    }
  }, [onRefresh]);

  /** 人工控制：打开 Modal 展示结果，暂停等待用户点击「继续」或关闭取消 */
  const waitManual = useCallback((cloneScriptId: number, status: string) => {
    return new Promise<void>((resolve, reject) => {
      manualContinueResolveRef.current = () => {
        manualContinueResolveRef.current = null;
        manualCancelRef.current = null;
        resolve();
      };
      manualCancelRef.current = () => {
        manualContinueResolveRef.current = null;
        manualCancelRef.current = null;
        cancelledRef.current = true;
        setDetailModalOpen(false);
        resolve();
      };
      setDetailCloneId(cloneScriptId);
      setDetailCloneStatus(status);
      modalSourceRef.current = 'generate';
      setDetailModalOpen(true);
    });
  }, []);

  const handleManualContinue = useCallback(() => {
    if (manualContinueResolveRef.current) {
      const resolve = manualContinueResolveRef.current;
      manualContinueResolveRef.current = null;
      manualCancelRef.current = null;
      setDetailModalOpen(false);
      resolve();
    }
  }, []);

  /** 轮询 clone 状态直到进入目标阶段 */
  const pollCloneStatus = useCallback((cloneScriptId: number, targetStatuses: string[]): Promise<string> => {
    return new Promise((resolve, reject) => {
      const pollInterval = setInterval(async () => {
        try {
          const st = await getCloneStatus(cloneScriptId);
          // 检查 clone_status 和 generate_flow_status
          const currentStatus = st.generate_flow_status || st.clone_status;
          if (currentStatus === 'FAILED' || st.clone_status === 'FAILED') {
            clearInterval(pollInterval);
            reject(new Error(st.error_message || '任务执行失败'));
            return;
          }
          if (targetStatuses.includes(currentStatus) || targetStatuses.includes(st.clone_status)) {
            clearInterval(pollInterval);
            resolve(currentStatus);
            return;
          }
        } catch {}
      }, 5000);
    });
  }, []);

  const startGenerate = useCallback(async () => {
    const selected = scripts.find(s => s.id === selectedScript);
    if (!selected) { alert('请先选择一个剧本'); return; }

    // 未激活账号：弹框明确提示（需用户点确认），不发起请求；后端另有 403 兜底
    if (!isActive) {
      alert('账号未激活：请联系管理员激活账号后，才能生成配音 / 图片 / 视频。');
      return;
    }

    const autoRun = flowControl === '自动';
    cancelledRef.current = false;
    setShowProgress(true);
    setTotalPercent(0);
    setCurrentStepText('正在准备...');

    try {
      let cloneScriptId: number;

      if ((selected.sourceType === 'copy' || selected.sourceType === 'novel') && selected.sourceId) {
        cloneScriptId = selected.sourceId;
        setCurrentStepText('已就绪，开始配音...');
      } else {
        setCurrentStepText('正在创建复刻剧本...');
        const plotRes = await clonePlot({
          videoId: selected.sourceId || selected.id,
          cloneTheme: selected.tag || '标准生成',
          autoRun: false, style, product: null, productDesc: null,
          aspectRatio, generationMethod: method,
        });
        cloneScriptId = plotRes.id;

        // clone_plot 会在同一后端任务里自动完成「剧本 + 分镜」，直接等 SEGMENTS_DONE 即可
        setCurrentStepText('剧本与分镜创作中...');
        await pollCloneStatus(cloneScriptId, ['SEGMENTS_DONE']);
      }

      if (cancelledRef.current) return;

      setCurrentStepText('配音生成中...');
      await clonePhase(cloneScriptId, 3, autoRun);

      if (autoRun) {
        setCurrentStepText('自动生成中...');
        await pollCloneStatus(cloneScriptId, ['MERGE_VIDEO_DONE']);
        setTotalPercent(100);
        setCurrentStepText('视频生成完成！');
      } else {
        await pollCloneStatus(cloneScriptId, ['VOICE_DONE']);
        setCurrentStepText('配音完成');
        await waitManual(cloneScriptId, 'VOICE_DONE');

        if (cancelledRef.current) return;

        setCurrentStepText('生图中...');
        await clonePhase(cloneScriptId, 4, false);
        await pollCloneStatus(cloneScriptId, ['IMAGE_DONE']);
        setCurrentStepText('生图完成');
        await waitManual(cloneScriptId, 'IMAGE_DONE');

        if (cancelledRef.current) return;

        setCurrentStepText('参考帧生成中...');
        await clonePhase(cloneScriptId, 5, false);
        await pollCloneStatus(cloneScriptId, ['FRAME_DONE']);
        setCurrentStepText('参考帧完成');
        await waitManual(cloneScriptId, 'FRAME_DONE');

        if (cancelledRef.current) return;

        setCurrentStepText('分镜视频生成中...');
        await clonePhase(cloneScriptId, 6, false);
        await pollCloneStatus(cloneScriptId, ['SEGMENT_VIDEO_DONE']);
        setCurrentStepText('分镜视频完成');
        await waitManual(cloneScriptId, 'SEGMENT_VIDEO_DONE');

        if (cancelledRef.current) return;

        setCurrentStepText('合并成片中...');
        await clonePhase(cloneScriptId, 7, false);
        await pollCloneStatus(cloneScriptId, ['MERGE_VIDEO_DONE']);
        setTotalPercent(100);
        setCurrentStepText('视频生成完成！');
      }
    } catch (e: any) {
      console.error('生成视频失败:', e);
      // 后端 409 会带上明确原因（如“任务正在进行中”），优先展示
      const detail = e?.response?.data?.detail || e?.message || '未知错误';
      setCurrentStepText(`生成失败: ${detail}`);
      setTotalPercent(0);
    } finally {
      if (onRefresh) await onRefresh();
      setTimeout(() => setShowProgress(false), 2000);
    }
  }, [scripts, selectedScript, flowControl, aspectRatio, style, method, isActive, onRefresh, pollCloneStatus]);

  return (
    <div>
      {/* 生成操作区 */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 card-hover">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-gradient-to-br from-pink-500 to-rose-500 rounded-xl flex items-center justify-center shadow-md">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-800">AI 视频生成</h3>
            <p className="text-sm text-slate-500">选择剧本，一键生成专业视频</p>
          </div>
        </div>

        {/* 剧本来源切换 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-3">选择剧本来源</label>
          <div className="flex gap-2 mb-4">
            <button onClick={() => { setGenSource('copy'); setGenCurrentPage(0); }}
              className={`px-5 py-2.5 rounded-xl text-sm font-medium transition-all ${genSource === 'copy' ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-md' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              复制的剧本
            </button>
            <button onClick={() => { setGenSource('novel'); setGenCurrentPage(0); }}
              className={`px-5 py-2.5 rounded-xl text-sm font-medium transition-all ${genSource === 'novel' ? 'bg-gradient-to-r from-indigo-500 to-blue-500 text-white shadow-md' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              来自小说的剧本
            </button>
          </div>

          {/* 剧本列表 - 轮播 */}
          <div className="relative group">
            <button onClick={() => { if (!scrollRef.current || genCurrentPage === 0) return; const cw = scrollRef.current.children[0]?.getBoundingClientRect().width || 0; scrollRef.current.scrollTo({ left: (genCurrentPage - 1) * (cw + 16), behavior: 'smooth' }); setGenCurrentPage(p => Math.max(0, p - 1)); }}
              disabled={genCurrentPage === 0}
              className={`absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 z-10 w-9 h-9 rounded-full bg-white/90 border border-slate-200 shadow-md flex items-center justify-center transition-all ${genCurrentPage === 0 ? 'opacity-0 pointer-events-none' : 'hover:bg-slate-50 hover:shadow-lg'}`}>
              <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <button onClick={() => { if (!scrollRef.current || genCurrentPage >= genTotalPages - 1) return; const cw = scrollRef.current.children[0]?.getBoundingClientRect().width || 0; scrollRef.current.scrollTo({ left: (genCurrentPage + 1) * (cw + 16), behavior: 'smooth' }); setGenCurrentPage(p => Math.min(genTotalPages - 1, p + 1)); }}
              disabled={genCurrentPage >= genTotalPages - 1}
              className={`absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 z-10 w-9 h-9 rounded-full bg-white/90 border border-slate-200 shadow-md flex items-center justify-center transition-all ${genCurrentPage >= genTotalPages - 1 ? 'opacity-0 pointer-events-none' : 'hover:bg-slate-50 hover:shadow-lg'}`}>
              <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
            </button>
            <div ref={scrollRef} className="flex gap-4 overflow-x-auto scroll-smooth snap-x snap-mandatory pb-2 hide-scrollbar" style={{ scrollbarWidth: 'none' }}>
              {scripts.map((s) => (
                <label key={s.id} className="cursor-pointer snap-start flex-shrink-0 w-[calc(25%-12px)]">
                  <input type="radio" name="genScript" value={s.id} className="hidden peer" checked={selectedScript === s.id} onChange={() => setSelectedScript(s.id)} />
                  <div className={`p-4 border-2 rounded-2xl transition-all ${selectedScript === s.id ? 'border-pink-500 bg-pink-50/50' : 'border-slate-200 hover:border-pink-300'}`}>
                    <div className="flex items-start gap-3">
                      <div className={`w-12 h-14 bg-gradient-to-br ${s.color} rounded-xl flex items-center justify-center text-white font-bold text-[15px] leading-tight text-center flex-shrink-0 px-1 whitespace-pre-line`}>
                        {s.tag.length > 2 ? s.tag.slice(0, 2) + '\n' + s.tag.slice(2) : s.tag}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm leading-snug line-clamp-2">{s.title}</div>
                        <div className="text-xs text-slate-400 mt-1.5">{s.info || `${s.shots}个分镜`}</div>
                      </div>
                    </div>
                  </div>
                </label>
              ))}
            </div>
            <div className="flex items-center justify-center gap-1.5 mt-3">
              {genGetPaginationDots().map((dot) => (
                <button key={dot} onClick={() => { setGenCurrentPage(dot); if (scrollRef.current) { const cw = scrollRef.current.children[0]?.getBoundingClientRect().width || 0; scrollRef.current.scrollTo({ left: dot * (cw + 16), behavior: 'smooth' }); } }} className={`h-1.5 rounded-full transition-all duration-300 ${dot === genCurrentPage ? 'w-5 bg-pink-500' : 'w-1.5 bg-slate-300 hover:bg-slate-400'}`} />
              ))}
              <span className="text-xs text-slate-400 ml-2 tabular-nums">{genCurrentPage + 1}/{genTotalPages}</span>
            </div>
          </div>
        </div>

        {/* 生成设置 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">视频比例</label>
            <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent focus:bg-white transition-all text-sm">
              <option value="16:9">16:9（横屏）</option><option value="9:16">9:16（竖屏）</option><option value="1:1">1:1（方形）</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">画面风格</label>
            <select value={style} onChange={(e) => setStyle(e.target.value)} className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent focus:bg-white transition-all text-sm">
              <option value="真实摄影">真实摄影</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">生成方式</label>
            <select value={method} onChange={(e) => setMethod(e.target.value as 'cloud' | 'local')} className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent focus:bg-white transition-all text-sm">
              <option value="cloud">云端 API 生成</option><option value="local" disabled={!allowLocalComfy}>本地 comfy 生成</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">流程控制</label>
            <select value={flowControl} onChange={(e) => setFlowControl(e.target.value)} className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent focus:bg-white transition-all text-sm">
              <option value="人工控制">人工控制</option><option value="自动" disabled>自动</option>
            </select>
          </div>
        </div>

        {/* 生成进度 */}
        {showProgress && (
          <div className="mb-6 p-4 bg-slate-50 rounded-2xl border border-slate-200/60 fade-in">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-slate-600">{currentStepText || '处理中...'}</span>
              <span className="text-sm font-bold text-pink-600">{totalPercent}%</span>
            </div>
            <div className="h-2.5 bg-slate-200 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-pink-500 to-rose-500 rounded-full progress-animated transition-all duration-500" style={{ width: `${totalPercent}%` }} />
            </div>
          </div>
        )}

        {/* 开始按钮 */}
        <button onClick={startGenerate} disabled={showProgress || scripts.length === 0}
          className={`w-full py-4 rounded-2xl font-bold shadow-lg transition-all text-lg ${showProgress || scripts.length === 0 ? 'bg-gradient-to-r from-slate-400 to-slate-500 text-white cursor-not-allowed' : 'bg-gradient-to-r from-pink-500 via-rose-500 to-orange-500 text-white glow-pink hover:shadow-xl hover:-translate-y-0.5'}`}>
          {showProgress ? '⏳ 生成中...' : '🎬 开始生成视频'}
        </button>
      </div>

      {/* 生成历史 */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden">
        <div className="p-6 border-b border-slate-200/60 flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-red-500 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-800">生成历史</h3>
            <p className="text-sm text-slate-500">所有视频生成任务记录</p>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          {history.map((item) => (
            <div key={item.id} className="p-5 hover:bg-slate-50/60 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-16 h-12 bg-gradient-to-br from-rose-400 to-orange-400 rounded-xl flex items-center justify-center text-white flex-shrink-0 shadow-sm">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-slate-800 truncate">{item.title}</h4>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span>⏱ {item.duration}</span>
                    <span>🎨 {item.style}</span>
                    <span>📅 {item.time}</span>
                    <span>📎 {item.source}</span>
                  </div>
                  {item.status === 'processing' && item.step !== undefined && item.stepPercent !== undefined && (
                    <div className="mt-2">
                      <span className="text-xs text-pink-600 font-medium">生成中 · {item.stepPercent}%</span>
                      <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1">
                        <div className="h-full bg-gradient-to-r from-pink-500 to-rose-500 rounded-full progress-animated" style={{ width: `${item.stepPercent}%` }} />
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {item.status === 'done' ? (() => {
                    const DONE_LABELS: Record<string, string> = {
                      VOICE_DONE: '音频完成', IMAGE_DONE: '生图完成',
                      FRAME_DONE: '帧合成完成', SEGMENT_VIDEO_DONE: '分镜视频完成',
                      MERGE_VIDEO_DONE: '已完成', DONE: '已完成',
                    };
                    const label = (item.cloneStatus && DONE_LABELS[item.cloneStatus]) || '已完成';
                    return (
                      <>
                        <span className="px-3 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full">{label}</span>
                        <button onClick={() => { modalSourceRef.current = 'history'; setDetailCloneId(item.cloneScriptId || null); setDetailCloneStatus(item.cloneStatus || ''); setDetailModalOpen(true); }}
                          className="px-4 py-2 text-sm text-pink-600 hover:bg-pink-50 rounded-lg transition-colors font-medium">查看详情</button>
                      </>
                    );
                  })() : item.status === 'failed' ? (
                    <>
                      <span className="px-3 py-1 text-xs font-medium bg-red-100 text-red-700 rounded-full">失败</span>
                      {item.cloneScriptId && item.stepPercent !== undefined && getRetryStep(item.stepPercent) > 0 && (
                        <button onClick={() => handleRetry(item.cloneScriptId!, item.stepPercent!)}
                          disabled={retryLoading === item.cloneScriptId}
                          className="px-4 py-2 text-sm text-white bg-gradient-to-r from-pink-500 to-rose-500 hover:from-pink-600 hover:to-rose-600 rounded-lg transition-colors font-medium disabled:opacity-50">
                          {retryLoading === item.cloneScriptId ? '重试中...' : `重试${RETRY_LABELS[getRetryStep(item.stepPercent!)] || ''}`}
                        </button>
                      )}
                      <button onClick={() => { modalSourceRef.current = 'history'; setDetailCloneId(item.cloneScriptId || null); setDetailCloneStatus(item.cloneStatus || ''); setDetailModalOpen(true); }}
                        className="px-4 py-2 text-sm text-pink-600 hover:bg-pink-50 rounded-lg transition-colors font-medium">查看详情</button>
                    </>
                  ) : (
                    <>
                      <span className="px-3 py-1 text-xs font-medium bg-pink-100 text-pink-700 rounded-full flex items-center gap-1">
                        <span className="w-1.5 h-1.5 bg-pink-500 rounded-full animate-pulse" /> 生成中
                      </span>
                      <button onClick={() => { modalSourceRef.current = 'history'; setDetailCloneId(item.cloneScriptId || null); setDetailCloneStatus(item.cloneStatus || ''); setDetailModalOpen(true); }}
                        className="px-4 py-2 text-sm text-pink-600 hover:bg-pink-50 rounded-lg transition-colors font-medium">查看详情</button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 生成资产详情弹窗 */}
      <GenerateDetailModal isOpen={detailModalOpen} onClose={() => {
        if (modalSourceRef.current === 'generate') {
          cancelledRef.current = true;
          if (manualCancelRef.current) {
            manualCancelRef.current();
          }
          setShowProgress(false);
          setCurrentStepText('已取消');
        }
        setDetailModalOpen(false);
        if (onRefresh) onRefresh();
      }}
        cloneScriptId={detailCloneId} cloneStatus={detailCloneStatus}
        isManual={flowControl === '人工控制'} onRefresh={onRefresh}
        onManualContinue={handleManualContinue} isHistory={modalSourceRef.current === 'history'} />
    </div>
  );
}
