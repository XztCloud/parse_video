"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { clonePlot, getCloneStatus, listAllCloneScripts } from "@/lib/api";
import { CopyHistoryItem } from "./data";

interface CopyScriptTabProps {
  history: CopyHistoryItem[];
  /** 支持直接传新数组，或传 React 风格的更新函数 */
  onHistoryChange: (
    next: CopyHistoryItem[] | ((prev: CopyHistoryItem[]) => CopyHistoryItem[])
  ) => void;
  onViewDetail: (item: CopyHistoryItem) => void;
  sourceVideos?: { id: number; filename: string; duration?: number | null; category?: string | null }[];
}

const tagColors: Record<string, string> = {
  '美食探店': 'from-indigo-400 to-purple-500',
  '知识科普': 'from-orange-400 to-red-500',
  '生活技巧': 'from-emerald-400 to-teal-500',
  '情感语录': 'from-pink-400 to-rose-500',
  '旅行攻略': 'from-cyan-400 to-blue-500',
  '数码测评': 'from-blue-400 to-indigo-500',
  '健身教学': 'from-lime-400 to-green-500',
  '宠物日常': 'from-amber-400 to-yellow-500',
  '穿搭分享': 'from-fuchsia-400 to-pink-500',
  '职场干货': 'from-slate-500 to-gray-700',
  '读书分享': 'from-teal-400 to-cyan-600',
  '影视解说': 'from-rose-400 to-red-600',
  '音乐翻唱': 'from-violet-400 to-purple-600',
  '手工DIY': 'from-orange-300 to-amber-500',
  '汽车评测': 'from-gray-500 to-slate-800',
  '母婴育儿': 'from-sky-400 to-blue-500',
  '家居好物': 'from-yellow-400 to-orange-500',
  '游戏解说': 'from-green-400 to-emerald-600',
  '理财科普': 'from-indigo-400 to-blue-600',
  '户外探险': 'from-emerald-500 to-teal-700',
  '未分类': 'from-cyan-400 to-blue-500',
};

/** 根据后端 clone_status 映射前端展示文案 */
function statusDisplay(cloneStatus?: string): { label: string; status: CopyHistoryItem['status'] } {
  switch (cloneStatus) {
    case 'PLOT':        return { label: '剧本创作中', status: 'processing' };
    case 'PLOT_DONE':   return { label: '剧本完成，准备分镜', status: 'processing' };
    case 'SEGMENTS':    return { label: '分镜创作中', status: 'processing' };
    case 'SEGMENTS_DONE': return { label: '已完成', status: 'done' };
    case 'FAILED':      return { label: '失败', status: 'failed' };
    default:            return { label: '处理中', status: 'processing' };
  }
}

/** 根据后端 clone_status 估算前端进度百分比 */
function statusProgress(cloneStatus?: string, backendProgress?: number): number {
  if (backendProgress !== undefined && backendProgress > 0) return backendProgress;
  switch (cloneStatus) {
    case 'PLOT':          return 5;
    case 'PLOT_DONE':     return 20;
    case 'SEGMENTS':      return 35;
    case 'SEGMENTS_DONE': return 100;
    case 'FAILED':        return 0;
    default:              return 0;
  }
}

export default function CopyScriptTab({ history, onHistoryChange, onViewDetail, sourceVideos }: CopyScriptTabProps) {
  const [copyTheme, setCopyTheme] = useState('');
  const [productSwap, setProductSwap] = useState('');
  const [selectedSource, setSelectedSource] = useState('1');
  const [isCreating, setIsCreating] = useState(false);
  const [activeCloneId, setActiveCloneId] = useState<number | null>(null);
  const [activeProgress, setActiveProgress] = useState(0);
  const [activeStatusText, setActiveStatusText] = useState('');
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const sourceScripts = (sourceVideos && sourceVideos.length > 0)
    ? sourceVideos.map(v => {
        const tag = v.category || '未分类';
        const dur = v.duration ?? 0;
        const m = Math.floor(dur / 60);
        const s = Math.floor(dur % 60);
        return {
          id: String(v.id),
          tag,
          title: v.filename,
          info: `时长 ${m}:${String(s).padStart(2, '0')}`,
          color: tagColors[tag] || 'from-cyan-400 to-blue-500',
        };
      })
    : [
        
      ];

  const themePresets = [
    { emoji: '😂', label: '搞笑幽默' },
    { emoji: '📚', label: '专业干货' },
    { emoji: '💝', label: '情感治愈' },
    { emoji: '🎭', label: '反转剧情' },
  ];

  const productPresets = [
    { emoji: '🤖', label: '千问' },
    { emoji: '🫘', label: '豆包' },
    { emoji: '💬', label: 'ChatGPT' },
    { emoji: '🌙', label: 'Kimi' },
    { emoji: '✨', label: '文心一言' },
    { emoji: '🧠', label: '通义万相' },
  ];

  const scrollRef = useRef<HTMLDivElement>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const itemsPerPage = 4;
  const totalPages = Math.ceil(sourceScripts.length / itemsPerPage);

  const scrollTo = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return;
    const childWidth = scrollRef.current.children[0]?.getBoundingClientRect().width || 0;
    const gap = 16;
    const offset = direction === 'left' ? -(childWidth + gap) : (childWidth + gap);
    scrollRef.current.scrollBy({ left: offset, behavior: 'smooth' });
    setCurrentPage(prev => direction === 'left' ? Math.max(0, prev - 1) : Math.min(totalPages - 1, prev + 1));
  };

  // 拉取真实复制历史
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const allItems = await listAllCloneScripts(0, 50);
        if (cancelled) return;
        const mapped: CopyHistoryItem[] = allItems.map(item => {
          const isDone = item.clone_status === 'SEGMENTS_DONE';
          const isFailed = item.clone_status === 'FAILED';
          // 格式化时间
          let displayTime = '';
          if (item.created_at) {
            try {
              const d = new Date(item.created_at);
              const now = new Date();
              const isToday = d.toDateString() === now.toDateString();
              const hh = String(d.getHours()).padStart(2, '0');
              const mm = String(d.getMinutes()).padStart(2, '0');
              displayTime = isToday ? `今天 ${hh}:${mm}` : `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
            } catch {
              displayTime = item.created_at;
            }
          }
          return {
            id: item.id,
            displayTitle: `${item.video_title.slice(0, 12)} - ${item.clone_theme}`,
            title: item.clone_theme,
            source: item.video_title,
            status: isDone ? 'done' : isFailed ? 'failed' : 'processing' as const,
            time: displayTime,
            theme: item.clone_theme,
            progress: item.clone_progress,
            cloneScriptId: item.id,
            cloneStatus: item.clone_status,
            sourceType: item.source_type,
          };
        });
        onHistoryChange(prev => {
          // 合并：保留当前正在创建的（没有 cloneScriptId 的），用后端数据替换有 cloneScriptId 的
          const inFlight = prev.filter(h => !h.cloneScriptId);
          return [...inFlight, ...mapped];
        });
      } catch (e) {
        console.warn('拉取复制历史失败', e);
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** 轮询 clone 状态直到进入目标阶段 */
  const pollUntil = useCallback((cloneScriptId: number, targetStatuses: string[]): Promise<string> => {
    return new Promise((resolve, reject) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const st = await getCloneStatus(cloneScriptId);
          const cs = st.clone_status;
          const pct = st.clone_progress || 0;

          setActiveProgress(pct);
          setActiveStatusText(statusDisplay(cs).label);

          // 同步更新历史记录
          onHistoryChange(prev => prev.map(h =>
            h.cloneScriptId === cloneScriptId
              ? { ...h, progress: pct, cloneStatus: cs, ...statusDisplay(cs) }
              : h
          ));

          if (cs === 'FAILED') {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            reject(new Error(st.error_message || '任务执行失败'));
            return;
          }
          if (targetStatuses.includes(cs)) {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            resolve(cs);
            return;
          }
        } catch (e) {
          // 网络错误暂不中断，继续轮询
          console.warn('轮询状态失败，稍后重试', e);
        }
      }, 3000);
    });
  }, [onHistoryChange]);

  /** 清理轮询 */
  const cleanupPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  /** 停止当前活动任务 */
  const handleStop = useCallback(() => {
    cleanupPoll();
    setIsCreating(false);
    setActiveCloneId(null);
  }, [cleanupPoll]);

  /** 开始复制剧本 */
  const startCopy = useCallback(async () => {
    if (!copyTheme.trim()) {
      alert('请输入复制主题或选择预设风格');
      return;
    }
    if (isCreating) {
      alert('当前有任务进行中，请等待完成');
      return;
    }

    const sourceVideoId = parseInt(selectedSource, 10);
    if (isNaN(sourceVideoId)) {
      alert('请选择源剧本');
      return;
    }

    const sourceName = sourceScripts.find(s => s.id === selectedSource)?.title || '未知';
    const productLabel = productSwap.trim() || undefined;
    const displayTitle = `${sourceName.slice(0, 12)} - ${copyTheme}${productLabel ? ` · ${productLabel}` : ''}`;

    setIsCreating(true);
    setActiveProgress(5);
    setActiveStatusText('剧本创作中');

    // 创建历史记录
    const newItem: CopyHistoryItem = {
      id: Date.now(),
      title: displayTitle,
      source: sourceName,
      status: 'processing',
      time: '刚刚',
      theme: copyTheme,
      product: productLabel,
      progress: 5,
      cloneStatus: 'PLOT',
      sourceType: 'CLONE',
    };
    onHistoryChange([newItem, ...history]);

    try {
      // 1. 调用 clonePlot 接口
      const plotRes = await clonePlot({
        videoId: sourceVideoId,
        cloneTheme: copyTheme,
        autoRun: false,
        style: null,
        product: productLabel || null,
        productDesc: null,
      });

      const cloneScriptId = plotRes.id;
      setActiveCloneId(cloneScriptId);

      // 更新历史记录（加入 cloneScriptId）
      onHistoryChange(prev => prev.map(h =>
        h.id === newItem.id ? { ...h, cloneScriptId } : h
      ));

      // 2. 后端在 clone_plot 的同一个任务里自动完成「剧本创作 + 分镜创作」，
      //    这里只需一次轮询到分镜完成（SEGMENTS_DONE），避免前端二次触发丢请求
      await pollUntil(cloneScriptId, ['SEGMENTS_DONE']);

      // 5. 全部完成
      setActiveProgress(100);
      setActiveStatusText('已完成');
      onHistoryChange(prev => prev.map(h =>
        h.cloneScriptId === cloneScriptId
          ? { ...h, status: 'done', cloneStatus: 'SEGMENTS_DONE', progress: 100, time: '刚刚' }
          : h
      ));

    } catch (e: any) {
      console.error('复制剧本失败', e);
      setActiveStatusText('失败');
      const errorMsg = e?.message || '未知错误';
      onHistoryChange(prev => prev.map(h =>
        h.id === newItem.id
          ? { ...h, status: 'failed', cloneStatus: 'FAILED', progress: 0, time: `失败: ${errorMsg}` }
          : h
      ));
    } finally {
      setIsCreating(false);
      setActiveCloneId(null);
      // 延迟清除进度面板
      setTimeout(() => {
        setActiveProgress(0);
        setActiveStatusText('');
      }, 3000);
    }
  }, [copyTheme, productSwap, selectedSource, isCreating, history, onHistoryChange, sourceScripts, pollUntil, cleanupPoll]);

  const getPaginationDots = (): number[] => {
    if (totalPages <= 3) {
      return Array.from({ length: totalPages }, (_, i) => i);
    } else if (currentPage <= 1) {
      return [0, 1, 2];
    } else if (currentPage >= totalPages - 2) {
      return [totalPages - 3, totalPages - 2, totalPages - 1];
    } else {
      return [currentPage - 1, currentPage, currentPage + 1];
    }
  };

  return (
    <div>
      {/* 复制操作区 */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 card-hover">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-md">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-800">AI 剧本复制</h3>
            <p className="text-sm text-slate-500">基于已解析视频，一键生成创意改写版本</p>
          </div>
        </div>

        {/* 选择源视频 - 轮播 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-3">选择源剧本</label>
          <div className="relative group">
            <button
              onClick={() => scrollTo('left')}
              disabled={currentPage === 0}
              className={`absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 z-10 w-9 h-9 rounded-full bg-white/90 border border-slate-200 shadow-md flex items-center justify-center transition-all ${
                currentPage === 0 ? 'opacity-0 pointer-events-none' : 'hover:bg-slate-50 hover:shadow-lg'
              }`}
            >
              <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <button
              onClick={() => scrollTo('right')}
              disabled={currentPage >= totalPages - 1}
              className={`absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 z-10 w-9 h-9 rounded-full bg-white/90 border border-slate-200 shadow-md flex items-center justify-center transition-all ${
                currentPage >= totalPages - 1 ? 'opacity-0 pointer-events-none' : 'hover:bg-slate-50 hover:shadow-lg'
              }`}
            >
              <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
            </button>

            <div ref={scrollRef} className="flex gap-4 overflow-x-auto scroll-smooth snap-x snap-mandatory pb-2 hide-scrollbar" style={{ scrollbarWidth: 'none' }}>
              {sourceScripts.map((script) => (
                <label key={script.id} className="cursor-pointer snap-start flex-shrink-0 w-[calc(25%-12px)]">
                  <input type="radio" name="copySource" value={script.id} className="hidden peer"
                    checked={selectedSource === script.id} onChange={() => setSelectedSource(script.id)} />
                  <div className={`p-4 border-2 rounded-2xl transition-all ${
                    selectedSource === script.id ? 'border-purple-500 bg-purple-50/50' : 'border-slate-200 hover:border-purple-300'
                  }`}>
                    <div className="flex items-start gap-3">
                      <div className={`w-12 h-14 bg-gradient-to-br ${script.color} rounded-xl flex items-center justify-center text-white font-bold text-[15px] leading-tight text-center flex-shrink-0 px-1 whitespace-pre-line`}>
                        {script.tag.length > 2 ? script.tag.slice(0, 2) + '\n' + script.tag.slice(2) : script.tag}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm leading-snug line-clamp-2">{script.title}</div>
                        <div className="text-xs text-slate-400 mt-1.5">{script.info}</div>
                      </div>
                    </div>
                  </div>
                </label>
              ))}
            </div>

            {/* 分页指示器 */}
            <div className="flex items-center justify-center gap-1.5 mt-3">
              {getPaginationDots().map((dot) => (
                <button key={dot} onClick={() => {
                  setCurrentPage(dot);
                  if (scrollRef.current) {
                    const cw = scrollRef.current.children[0]?.getBoundingClientRect().width || 0;
                    scrollRef.current.scrollTo({ left: dot * (cw + 16), behavior: 'smooth' });
                  }
                }} className={`h-1.5 rounded-full transition-all duration-300 ${
                  dot === currentPage ? 'w-5 bg-purple-500' : 'w-1.5 bg-slate-300 hover:bg-slate-400'
                }`} />
              ))}
              <span className="text-xs text-slate-400 ml-2 tabular-nums">{currentPage + 1}/{totalPages}</span>
            </div>
          </div>
        </div>

        {/* 复制主题输入 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-3">复制主题 / 风格</label>
          <input type="text" value={copyTheme} onChange={(e) => setCopyTheme(e.target.value)}
            placeholder="例如：换成职场风格、改成搞笑版、用二次元语气..."
            className="w-full px-4 py-3.5 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent focus:bg-white transition-all text-sm" />
          <div className="flex flex-wrap gap-2 mt-3">
            {themePresets.map((p) => (
              <button key={p.label} onClick={() => setCopyTheme(p.label)}
                className="px-3 py-1.5 bg-slate-100 hover:bg-purple-100 hover:text-purple-700 text-slate-600 rounded-lg text-xs transition-colors">
                {p.emoji} {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* 推广产品替换 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-3">
            推广产品替换
            <span className="ml-2 text-xs text-slate-400 font-normal">（可选，替换原视频中的推广产品）</span>
          </label>
          <div className="relative">
            <div className="absolute left-4 top-1/2 -translate-y-1/2 w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </div>
            <input type="text" value={productSwap} onChange={(e) => setProductSwap(e.target.value)}
              placeholder="例如：把千问换成豆包、推广换成Kimi..."
              className="w-full pl-14 pr-4 py-3.5 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent focus:bg-white transition-all text-sm" />
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            {productPresets.map((p) => (
              <button key={p.label} onClick={() => setProductSwap(p.label)}
                className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                  productSwap === p.label ? 'bg-purple-100 text-purple-700 font-medium' : 'bg-slate-100 hover:bg-purple-100 hover:text-purple-700 text-slate-600'
                }`}>
                {p.emoji} {p.label}
              </button>
            ))}
            {productSwap && (
              <button onClick={() => setProductSwap('')}
                className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-500 rounded-lg text-xs transition-colors">✕ 清除</button>
            )}
          </div>
        </div>

        <button onClick={startCopy} disabled={isCreating}
          className={`w-full py-4 rounded-2xl font-bold shadow-lg transition-all text-lg ${
            isCreating
              ? 'bg-gradient-to-r from-slate-400 to-slate-500 text-white cursor-not-allowed'
              : 'bg-gradient-to-r from-purple-500 via-pink-500 to-rose-500 text-white glow-purple hover:shadow-xl hover:-translate-y-0.5'
          }`}>
          {isCreating ? '⏳ 任务进行中...' : '✨ 开始复制剧本'}
        </button>
      </div>

      {/* 实时进度展示 */}
      {isCreating && (
        <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 fade-in">
          <div className="flex items-start gap-4">
            <div className="relative">
              <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl flex items-center justify-center shadow-lg text-purple-500 pulse-ring">
                <svg className="w-6 h-6 text-white animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-bold text-slate-800">{activeStatusText || '处理中...'}</h4>
                <span className="text-sm font-bold gradient-text">{activeProgress}%</span>
              </div>
              <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden mb-3">
                <div className="h-full bg-gradient-to-r from-purple-500 via-pink-500 to-rose-500 rounded-full progress-animated transition-all duration-500"
                  style={{ width: `${activeProgress}%` }} />
              </div>
              {/* 阶段指示 */}
              <div className="flex items-center gap-6 text-xs text-slate-500">
                <span className={activeProgress >= 5 ? 'text-purple-600 font-medium' : ''}>
                  {activeProgress >= 20 ? '✅' : '🔄'} 剧本创作
                </span>
                <span className={activeProgress >= 31 ? 'text-purple-600 font-medium' : ''}>
                  {activeProgress >= 100 ? '✅' : activeProgress >= 31 ? '🔄' : '⏳'} 分镜创作
                </span>
              </div>
            </div>
          </div>
          <button onClick={handleStop}
            className="mt-4 w-full py-2.5 border border-slate-200 text-slate-500 hover:text-red-500 hover:border-red-200 rounded-xl text-sm transition-colors">
            停止任务
          </button>
        </div>
      )}

      {/* 历史记录 */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden">
        <div className="p-6 border-b border-slate-200/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-purple-600 to-pink-600 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-800">复制历史</h3>
              <p className="text-sm text-slate-500">所有 AI 剧本复制任务记录</p>
            </div>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          {history.filter(item => item.sourceType === 'CLONE').map((item) => {
            const ds = statusDisplay(item.cloneStatus);
            const displayStatus = item.status || ds.status;
            return (
              <div key={item.id} className="p-5 hover:bg-slate-50/60 transition-colors">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-pink-100 rounded-xl flex items-center justify-center flex-shrink-0">
                    <svg className="w-6 h-6 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h4 className="font-semibold text-slate-800 truncate">{item.displayTitle || item.title}</h4>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                      <span>🎯 {item.theme}</span>
                      {item.product && <span>🏷️ 推广{item.product}</span>}
                      <span>📅 {item.time}</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1 truncate">来源：{item.source}</p>
                    {displayStatus === 'processing' && (
                      <div className="mt-2">
                        <span className="text-xs text-purple-600 font-medium">
                          {ds.label} {(item.progress ?? 0)}%
                        </span>
                        <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1">
                          <div className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full progress-animated"
                            style={{ width: `${item.progress ?? 0}%` }} />
                        </div>
                      </div>
                    )}
                    {displayStatus === 'failed' && (
                      <div className="mt-1">
                        <span className="text-xs text-red-500 font-medium">❌ {item.time.includes('失败') ? item.time : '任务失败'}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {displayStatus === 'done' ? (
                      <>
                        <span className="px-3 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full">已完成</span>
                        {item.cloneScriptId && (
                          <button onClick={() => onViewDetail(item)}
                            className="px-4 py-2 text-sm text-purple-600 hover:bg-purple-50 rounded-lg transition-colors font-medium">查看详情</button>
                        )}
                      </>
                    ) : displayStatus === 'failed' ? (
                      <span className="px-3 py-1 text-xs font-medium bg-red-100 text-red-700 rounded-full">失败</span>
                    ) : (
                      <span className="px-3 py-1 text-xs font-medium bg-purple-100 text-purple-700 rounded-full flex items-center gap-1">
                        <span className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-pulse" /> {ds.label}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {history.filter(item => item.sourceType === 'CLONE').length === 0 && (
          <div className="p-12 text-center text-slate-400 text-sm">
            暂无复制记录，选择源剧本开始创作吧
          </div>
        )}
      </div>
    </div>
  );
}
