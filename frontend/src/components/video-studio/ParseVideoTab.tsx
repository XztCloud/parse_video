"use client";

import { useState, useRef, useCallback } from "react";
import { ParseHistoryItem, getRandomTagPreset, tagPresets } from "./data";
import { uploadVideo, parseDouyin, getVideoStatus } from "@/lib/api";

interface ParseVideoTabProps {
  history: ParseHistoryItem[];
  onHistoryChange: (history: ParseHistoryItem[]) => void;
  onViewDetail: (item: ParseHistoryItem) => void;
  onRefresh?: () => void;
}

/** 从 Axios 错误中安全提取错误消息字符串 */
function extractErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: any) => d.msg || String(d)).join('; ');
  }
  return String(detail);
}

export default function ParseVideoTab({ history, onHistoryChange, onViewDetail, onRefresh }: ParseVideoTabProps) {
  const [showProgress, setShowProgress] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressText, setProgressText] = useState('');
  const [progressTitle, setProgressTitle] = useState('正在解析视频...');
  const [videoUrl, setVideoUrl] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  /** 轮询视频解析状态 */
  const pollVideoStatus = useCallback((videoId: number, fileName: string) => {
    const stages = [
      { text: '正在上传视频文件...', pct: 10 },
      { text: '提取音频进行语音识别...', pct: 35 },
      { text: '分析画面内容与场景...', pct: 55 },
      { text: 'AI 生成分镜脚本...', pct: 80 },
      { text: '整理最终输出...', pct: 95 },
    ];
    let stage = 0;

    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await getVideoStatus(videoId);

        if (data.status === 'done') {
          if (pollRef.current) clearInterval(pollRef.current);
          setProgressPercent(100);
          setProgressTitle('解析完成！');
          setProgressText('已成功提取剧本和分镜脚本，可在历史记录中查看详情');

          // 从后端返回的 category 随机兜底
          const tag = data.category || getRandomTagPreset().tag;
          const tagColor = tagPresets.find(t => t.tag === tag)?.tagColor || 'from-cyan-400 to-blue-500';
          const dur = data.duration ?? 0;
          const m = Math.floor(dur / 60);
          const s = Math.floor(dur % 60);

          onHistoryChange([{
            id: data.id,
            title: data.filename || fileName,
            duration: `${m}:${String(s).padStart(2, '0')}`,
            shots: 0,
            status: 'done',
            time: '刚刚',
            source: fileName.includes('抖音') ? '抖音链接' : '上传视频',
            tag,
            tagColor,
          }, ...history]);

          onRefresh?.();
          setTimeout(() => {
            setShowProgress(false);
            setProgressPercent(0);
          }, 2000);
          return;
        }

        if (data.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          setProgressTitle('解析失败');
          setProgressText(data.error_message || '解析过程出错，请重试');

          // 更新历史记录状态为 failed
          const errorMsg = data.error_message || '解析失败';
          onHistoryChange(prev => prev.map(h =>
            h.id === videoId ? { ...h, status: 'failed', time: `失败: ${errorMsg}` } : h
          ));

          onRefresh?.();
          setTimeout(() => {
            setShowProgress(false);
            setProgressPercent(0);
          }, 3000);
          return;
        }

        // 仍在处理中：根据 progress 值更新进度条
        const backendPct = data.progress || 0;
        // 同时更新阶段文字
        while (stage < stages.length && backendPct >= stages[stage].pct) {
          stage++;
        }
        if (stage < stages.length) {
          setProgressPercent(backendPct);
          setProgressText(stages[stage].text);
        } else {
          setProgressPercent(Math.min(backendPct, 99));
          setProgressText('最后处理中...');
        }
      } catch {
        // 轮询失败时静默，继续等待
      }
    }, 3000);
  }, [history, onHistoryChange, onRefresh]);

  /** 上传文件解析 */
  const handleUpload = useCallback(async (file: File) => {
    setShowProgress(true);
    setProgressTitle('正在解析视频...');
    setProgressPercent(0);
    setProgressText('正在上传视频文件...');

    try {
      const res = await uploadVideo(file);
      pollVideoStatus(res.id, file.name);
    } catch (err: any) {
      const msg = extractErrorMessage(err, '上传失败');
      setProgressTitle('上传失败');
      setProgressText(msg);
      setTimeout(() => {
        setShowProgress(false);
        setProgressPercent(0);
      }, 3000);
    }
  }, [pollVideoStatus]);

  /** 抖音链接解析 */
  const handleParseDouyin = useCallback(async () => {
    if (!videoUrl.trim()) {
      alert('请输入视频链接');
      return;
    }

    // 从分享文案中提取 URL（用户可能粘贴整段抖音分享文字）
    const urlMatch = videoUrl.match(/https?:\/\/[^\s]+/);
    const extractedUrl = urlMatch ? urlMatch[0] : videoUrl.trim();

    setShowProgress(true);
    setProgressTitle('正在解析视频...');
    setProgressPercent(0);
    setProgressText('正在解析抖音链接...');

    try {
      const res = await parseDouyin(extractedUrl);
      pollVideoStatus(res.id, '抖音分享视频');
    } catch (err: any) {
      const msg = extractErrorMessage(err, '解析失败');
      setProgressTitle('解析失败');
      setProgressText(msg);
      setTimeout(() => {
        setShowProgress(false);
        setProgressPercent(0);
      }, 3000);
    }
  }, [videoUrl, pollVideoStatus]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith('video/')) {
      handleUpload(files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleUpload(e.target.files[0]);
    }
  };

  const handleStartParseFromUrl = () => {
    handleParseDouyin();
  };

  return (
    <div>
      {/* 上传区域 */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 card-hover">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-xl flex items-center justify-center shadow-md">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-800">上传视频解析</h3>
            <p className="text-sm text-slate-500">支持拖拽上传或粘贴抖音分享链接</p>
          </div>
        </div>

        {/* 拖拽上传区 */}
        <div
          className={`relative border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-300 cursor-pointer mb-6 ${
            isDragOver
              ? 'border-indigo-500 bg-indigo-50/30 scale-[1.01]'
              : 'border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/30'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept="video/*"
            onChange={handleFileSelect}
          />
          <div className="flex flex-col items-center">
            <div className="w-16 h-16 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <p className="text-slate-700 font-medium mb-1">拖拽视频文件到此处</p>
            <p className="text-sm text-slate-400 mb-4">或点击选择文件 · 支持 MP4, MOV, AVI, WebM · 最大 500MB</p>
            <button className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-xl text-sm font-medium shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5">
              选择视频文件
            </button>
          </div>
        </div>

        {/* 分隔线 */}
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1 h-px bg-slate-200" />
          <span className="text-sm text-slate-400">或粘贴链接</span>
          <div className="flex-1 h-px bg-slate-200" />
        </div>

        {/* URL输入 */}
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <div className="absolute left-4 top-1/2 -translate-y-1/2 w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
            </div>
            <input
              type="text"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              placeholder="粘贴抖音分享链接或整段分享文案，自动提取URL"
              className="w-full pl-14 pr-4 py-3.5 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent focus:bg-white transition-all text-sm"
            />
          </div>
          <button
            onClick={handleStartParseFromUrl}
            className="px-8 py-3.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white rounded-xl font-medium shadow-lg glow-indigo hover:shadow-xl transition-all hover:-translate-y-0.5 whitespace-nowrap"
          >
            开始解析
          </button>
        </div>
      </div>

      {/* 解析进度提示 */}
      {showProgress && (
        <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 fade-in">
          <div className="flex items-start gap-4">
            <div className="relative">
              <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-2xl flex items-center justify-center shadow-lg text-indigo-500 pulse-ring">
                <svg className="w-6 h-6 text-white animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-bold text-slate-800">{progressTitle}</h4>
                <span className="text-sm font-bold gradient-text">{progressPercent}%</span>
              </div>
              <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden mb-3">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-full progress-animated transition-all duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="text-sm text-slate-500">{progressText}</p>
            </div>
          </div>
        </div>
      )}

      {/* 历史记录 */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden">
        <div className="p-6 border-b border-slate-200/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-slate-700 to-slate-900 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-800">解析历史</h3>
              <p className="text-sm text-slate-500">查看已解析的视频任务</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">全部</button>
            <button className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">解析中</button>
            <button className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">已完成</button>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          {history.map((item) => (
            <div key={item.id} className="p-5 hover:bg-slate-50/60 transition-colors">
              <div className="flex items-center gap-4">
                <div className={`w-16 h-12 bg-gradient-to-br ${item.tagColor} rounded-xl flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-sm`}>
                  {item.tag}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-slate-800 truncate">{item.title}</h4>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span>⏱ {item.duration}</span>
                    <span>🎬 {item.shots}个分镜</span>
                    <span>📅 {item.time}</span>
                    <span>📎 {item.source}</span>
                  </div>
                  {item.status === 'processing' && item.progress !== undefined && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-indigo-600 font-medium">解析中 {item.progress}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full progress-animated" style={{ width: `${item.progress}%` }} />
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {item.status === 'done' ? (
                    <>
                      <span className="px-3 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full">已完成</span>
                      <button
                        onClick={() => onViewDetail(item)}
                        className="px-4 py-2 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors font-medium"
                      >
                        查看详情
                      </button>
                    </>
                  ) : item.status === 'failed' ? (
                    <span className="px-3 py-1 text-xs font-medium bg-red-100 text-red-700 rounded-full">解析失败</span>
                  ) : (
                    <span className="px-3 py-1 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-full flex items-center gap-1">
                      <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse" />
                      解析中
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="p-4 text-center border-t border-slate-100">
          <button className="text-sm text-indigo-600 hover:text-indigo-700 font-medium">查看全部记录 →</button>
        </div>
      </div>
    </div>
  );
}
