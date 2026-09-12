"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createNovel,
  uploadNovel,
  generateNovel,
  getNovelStatus,
  getNovelScripts,
  getCloneScript,
  listNovels,
  type NovelStatusResponse,
  type NovelScriptItem,
} from "@/lib/api";
import { exportClonePlotMarkdown, exportStoryboardJson } from "@/lib/exportUtils";
import DetailModal from "./DetailModal";

/* ==================== Types ==================== */
interface NovelHistoryItem {
  id: number;
  title: string;
  shots: number;
  style: string;
  time: string;
  status: "done" | "processing" | "failed";
  progress?: number;
}

interface NovelChapterItem {
  id: number;
  chapter_title: string | null;
  chapter_index: number | null;
  scene_index: number | null;
  clone_status: string;
  clone_progress: number;
}

interface NovelShot {
  num: number;
  desc: string;
  dialogue: string;
  duration: string;
  shotType: string;
}

interface NovelScriptData {
  title: string;
  script: string;
  shots: NovelShot[];
}

/* ==================== Helpers ==================== */
function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return isToday ? `今天 ${hh}:${mm}` : `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
  } catch {
    return iso;
  }
}

const STYLE_MAP: Record<string, string> = {
  shortvideo: "短视频爆款",
  movie: "影视解说",
  drama: "剧情短片",
  children: "儿童故事",
  mystery: "悬疑推理",
};

const GRADIENT_LIST = [
  "from-indigo-500 to-purple-600",
  "from-pink-400 to-rose-500",
  "from-slate-600 to-slate-800",
  "from-amber-400 to-orange-500",
  "from-emerald-400 to-teal-500",
  "from-cyan-400 to-blue-500",
];

/* ==================== Component ==================== */
export default function NovelScriptTab({ onGenerateVideo }: { onGenerateVideo?: (scriptId: number) => void }) {
  const [content, setContent] = useState("");
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");
  const [fileName, setFileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [style, setStyle] = useState("shortvideo");
  const [shotCount, setShotCount] = useState("auto");
  const [perspective, setPerspective] = useState("original");
  const [isConverting, setIsConverting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState("");
  const [result, setResult] = useState<NovelScriptData | null>(null);
  const [activeResultTab, setActiveResultTab] = useState<"script" | "shots">("script");
  const [history, setHistory] = useState<NovelHistoryItem[]>([]);
  const [currentNovelId, setCurrentNovelId] = useState<number | null>(null);
  const [selectedNovelId, setSelectedNovelId] = useState<number | null>(null);
  const [selectedNovelTitle, setSelectedNovelTitle] = useState("");
  const [novelChapters, setNovelChapters] = useState<NovelChapterItem[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(false);

  // Detail modal state（复用复制剧本的 DetailModal）
  const [modalOpen, setModalOpen] = useState(false);
  const [modalTitle, setModalTitle] = useState("");
  const [modalSubtitle, setModalSubtitle] = useState("");
  const [modalSegments, setModalSegments] = useState<any[]>([]);
  const [modalCategory, setModalCategory] = useState<string | null>(null);
  const [modalDuration, setModalDuration] = useState<number | null>(null);
  const [modalVideoId, setModalVideoId] = useState<number | null>(null);
  const [modalCreatedAt, setModalCreatedAt] = useState<string | null>(null);
  const [modalParsePointer, setModalParsePointer] = useState<any>(null);
  const [modalScriptContent, setModalScriptContent] = useState<any>(null);
  const [modalParseScript, setModalParseScript] = useState<any>(null);
  // 是否允许「用此剧本生成视频」（仅已完成剧本）
  const [modalCanGenerate, setModalCanGenerate] = useState(false);
  // 是否允许导出（剧本内容 md / 分镜脚本 json）
  const [modalCanExport, setModalCanExport] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const charCount = content.length;

  /* ---- 加载历史记录 ---- */
  const fetchHistory = useCallback(async () => {
    try {
      const novels = await listNovels(0, 50);
      const items: NovelHistoryItem[] = novels.map((n: any) => ({
        id: n.id,
        title: n.title,
        shots: 0,
        style: "—",
        time: formatTime(n.created_at),
        status: n.status === "DONE" ? "done" : n.status === "FAILED" ? "failed" : "processing",
        progress: n.progress,
      }));
      setHistory(items);
    } catch {
      // 静默失败
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  /* ---- 点击历史记录，查看章节列表 ---- */
  const handleViewChapters = useCallback(async (novelId: number, title: string) => {
    setSelectedNovelId(novelId);
    setSelectedNovelTitle(title);
    setNovelChapters([]);
    setChaptersLoading(true);
    try {
      const scripts = await getNovelScripts(novelId);
      setNovelChapters(scripts as NovelChapterItem[]);
    } catch {
      setNovelChapters([]);
    } finally {
      setChaptersLoading(false);
    }
  }, []);

  const handleBackToList = useCallback(() => {
    setSelectedNovelId(null);
    setSelectedNovelTitle("");
    setNovelChapters([]);
  }, []);

  /* ---- 点击章节，查看剧本详情（复用 DetailModal） ---- */
  const handleViewChapterDetail = useCallback(async (ch: NovelChapterItem) => {
    const scriptTitle = ch.chapter_title || `场景 ${(ch.chapter_index ?? 0) + 1}`;
    setModalTitle(scriptTitle);
    setModalSubtitle(ch.clone_status === "PLOT_DONE" || ch.clone_status === "SEGMENTS_DONE" ? "小说剧本详情" : "处理中...");
    setModalSegments([]);
    setModalCategory(null);
    setModalDuration(null);
    setModalVideoId(ch.id);
    setModalCanGenerate(ch.clone_status === "SEGMENTS_DONE");
    setModalCanExport(ch.clone_status === "SEGMENTS_DONE");
    setModalCreatedAt(null);
    setModalParsePointer(null);
    setModalScriptContent(null);
    setModalParseScript(null);
    setModalOpen(true);

    try {
      const detail = await getCloneScript(ch.id);
      setModalSegments(detail.segments || []);
      setModalParsePointer(detail.clone_parse_pointer || null);
      setModalParseScript(detail.clone_parse_script?.plot_script || null);
      setModalScriptContent(detail.content || null);
      setModalCreatedAt(detail.created_at || null);
    } catch {
      // 静默失败，保持空数据
    }
  }, []);

  /* ---- 导出：剧本内容 markdown / 分镜脚本 json ---- */
  const handleExport = useCallback(async (kind: 'script' | 'storyboard') => {
    const id = modalVideoId;
    if (!id) return;
    try {
      if (kind === 'script') {
        await exportClonePlotMarkdown(id, `clone_${id}.md`);
      } else {
        exportStoryboardJson(modalSegments, `storyboard_${id}.json`);
      }
    } catch (e) {
      console.error('导出失败', e);
      alert('导出失败，请稍后重试');
    }
  }, [modalVideoId, modalSegments]);

  /* ---- 轮询状态 ---- */
  const pollStatus = useCallback((novelId: number) => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    pollingRef.current = setInterval(async () => {
      try {
        const status: NovelStatusResponse = await getNovelStatus(novelId);
        setProgress(status.progress);

        if (status.status === "DONE") {
          clearInterval(pollingRef.current!);
          pollingRef.current = null;
          setProgressText("转换完成！");
          setProgress(100);

          // 获取生成的剧本列表
          const scripts = await getNovelScripts(novelId);
          if (scripts.length > 0) {
            // 用第一个剧本的 clone_parse_script 构建结果
            // 目前后端返回的是列表，暂用标题和元数据展示
            setResult({
              title: status.title,
              script: `共生成 ${scripts.length} 个剧本片段\n\n` +
                scripts.map((s: NovelScriptItem, i: number) =>
                  `【第${i + 1}段】${s.chapter_title || ""} - 场景${(s.scene_index ?? 0) + 1}\n状态: ${s.clone_status}`
                ).join("\n\n"),
              shots: [],
            });
          }

          setIsConverting(false);
          fetchHistory();
        } else if (status.status === "FAILED") {
          clearInterval(pollingRef.current!);
          pollingRef.current = null;
          setProgressText(status.error_message || "转换失败");
          setIsConverting(false);
          fetchHistory();
        } else {
          setProgressText(`处理中... (${status.script_count} 个片段)`);
        }
      } catch {
        // 轮询出错，继续尝试
      }
    }, 2000);
  }, [fetchHistory]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  /* ---- 开始转换 ---- */
  const handleConvert = useCallback(async () => {
    if (!content.trim() && !selectedFile) {
      alert("请输入小说内容或上传文件");
      return;
    }

    const title = content.trim().slice(0, 30) || (selectedFile?.name ?? "未命名小说");

    setIsConverting(true);
    setProgress(0);
    setProgressText("正在创建小说记录...");
    setResult(null);

    try {
      let novelRes;
      if (selectedFile && inputMode === "upload") {
        novelRes = await uploadNovel(selectedFile, title);
      } else {
        novelRes = await createNovel(title, content);
      }

      setCurrentNovelId(novelRes.id);
      setProgress(5);
      setProgressText("已创建记录，开始生成剧本...");

      await generateNovel({
        novelId: novelRes.id,
        theme: STYLE_MAP[style] || style,
        autoRun: false,
        requirements: {
          shotCount,
          perspective,
        },
      });

      setProgress(10);
      setProgressText("生成任务已提交，等待处理...");
      pollStatus(novelRes.id);
    } catch (err: any) {
      setIsConverting(false);
      const msg = err?.response?.data?.detail || err?.message || "转换失败";
      setProgressText(`错误: ${msg}`);
      alert(`转换失败: ${msg}`);
    }
  }, [content, selectedFile, inputMode, style, shotCount, perspective, pollStatus]);

  /* ---- File upload ---- */
  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = [".txt", ".md", ".markdown"];
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!allowed.includes(ext)) {
      alert("仅支持 .txt / .md / .markdown 格式文件");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("文件大小不能超过 5MB");
      return;
    }
    setSelectedFile(file);
    setFileName(file.name);

    // 读取文件内容以显示字数
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setContent(text);
    };
    reader.readAsText(file, "utf-8");
    e.target.value = "";
  }, []);

  /* ---- Copy script ---- */
  const handleCopy = useCallback(() => {
    if (!result) return;
    navigator.clipboard.writeText(result.script).then(() => alert("已复制到剪贴板"));
  }, [result]);

  /* ---- Download script ---- */
  const handleDownload = useCallback(() => {
    if (!result) return;
    const blob = new Blob([result.script], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.title}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  return (
    <>
      {/* ==================== 转换设置区 ==================== */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 card-hover">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-xl flex items-center justify-center shadow-md">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-800">小说转剧本</h3>
            <p className="text-sm text-slate-500">粘贴小说内容，AI 自动转换为分镜剧本</p>
          </div>
        </div>

        {/* 小说内容输入 */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-3">小说内容</label>

          {/* 输入方式切换按钮 */}
          <div className="flex gap-2 mb-4 p-1 bg-slate-100 rounded-xl w-fit">
            <button
              onClick={() => setInputMode("paste")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                inputMode === "paste"
                  ? "bg-white text-indigo-600 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              粘贴文本
            </button>
            <button
              onClick={() => setInputMode("upload")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                inputMode === "upload"
                  ? "bg-white text-indigo-600 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              上传文件
            </button>
          </div>

          {/* 粘贴文本模式 */}
          {inputMode === "paste" && (
            <div>
              <textarea
                ref={textareaRef}
                rows={8}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="请粘贴小说原文或故事内容..."
                className="w-full px-4 py-3.5 bg-slate-50/80 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent focus:bg-white transition-all text-sm resize-none leading-relaxed"
                style={{ height: 180 }}
              />
              <div className="flex justify-between mt-2 text-xs text-slate-400">
                <span>建议粘贴 500-3000 字的小说内容</span>
                <span>{charCount} / 5000 字</span>
              </div>
            </div>
          )}

          {/* 上传文件模式 */}
          {inputMode === "upload" && (
            <div>
              <label className="flex flex-col items-center justify-center p-10 border-2 border-dashed border-slate-200 rounded-2xl hover:border-indigo-400 hover:bg-indigo-50/30 transition-all cursor-pointer group">
                <input
                  type="file"
                  className="hidden"
                  accept=".txt,.md,.markdown"
                  onChange={handleFileUpload}
                />
                {fileName ? (
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-14 h-14 bg-indigo-100 rounded-2xl flex items-center justify-center">
                      <svg className="w-7 h-7 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-slate-700">{fileName}</p>
                      <p className="text-xs text-slate-400 mt-1">{charCount} 字</p>
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <button
                        onClick={(ev) => { ev.preventDefault(); ev.stopPropagation(); setFileName(""); setSelectedFile(null); setContent(""); }}
                        className="px-4 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg transition-colors font-medium"
                      >
                        清除文件
                      </button>
                      <span className="text-xs text-slate-300">或</span>
                      <span className="text-xs text-indigo-500 font-medium">点击更换文件</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-14 h-14 bg-slate-100 group-hover:bg-indigo-100 rounded-2xl flex items-center justify-center transition-colors">
                      <svg className="w-7 h-7 text-slate-400 group-hover:text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-slate-600">点击上传或拖拽文件到此处</p>
                      <p className="text-xs text-slate-400 mt-1">支持 .txt / .md / .markdown 格式，最大 5MB</p>
                    </div>
                    <div className="px-4 py-2 bg-slate-100 group-hover:bg-indigo-100 group-hover:text-indigo-600 rounded-xl text-xs font-medium text-slate-500 transition-colors">
                      选择文件
                    </div>
                  </div>
                )}
              </label>
            </div>
          )}
        </div>

        {/* 设置区 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">剧本风格</label>
            <select
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent focus:bg-white transition-all text-sm appearance-none cursor-pointer"
            >
              <option value="shortvideo">短视频爆款</option>
              <option value="movie">影视解说</option>
              <option value="drama">剧情短片</option>
              <option value="children">儿童故事</option>
              <option value="mystery">悬疑推理</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">分镜数量</label>
            <select
              value={shotCount}
              onChange={(e) => setShotCount(e.target.value)}
              className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent focus:bg-white transition-all text-sm appearance-none cursor-pointer"
            >
              <option value="auto">自动</option>
              <option value="6">6个</option>
              <option value="8">8个</option>
              <option value="10">10个</option>
              <option value="12">12个</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">叙事视角</label>
            <select
              value={perspective}
              onChange={(e) => setPerspective(e.target.value)}
              className="w-full px-4 py-3 bg-slate-50/80 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent focus:bg-white transition-all text-sm appearance-none cursor-pointer"
            >
              <option value="original">原文视角</option>
              <option value="third">第三人称</option>
              <option value="first">第一人称</option>
              <option value="narrator">旁白解说</option>
            </select>
          </div>
        </div>

        {/* 底部操作 */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-400">⏱ 预计转换时间约 30 秒</span>
          <button
            onClick={handleConvert}
            disabled={isConverting}
            className="px-8 py-3.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white rounded-xl font-medium shadow-lg glow-indigo hover:shadow-xl transition-all hover:-translate-y-0.5 whitespace-nowrap disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isConverting ? "转换中..." : "开始转换"}
          </button>
        </div>
      </div>

      {/* ==================== 转换进度区 ==================== */}
      {isConverting && (
        <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 p-8 mb-8 fade-in">
          <div className="flex items-start gap-4">
            <div className="relative">
              <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-2xl flex items-center justify-center shadow-lg pulse-ring">
                <svg className="w-6 h-6 text-white animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-bold text-slate-800">正在转换小说...</h4>
                <span className="text-sm font-bold gradient-text">{progress}%</span>
              </div>
              <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden mb-3">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-full progress-animated transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-sm text-slate-500">{progressText}</p>
            </div>
          </div>
        </div>
      )}

      {/* ==================== 转换结果区 ==================== */}
      {result && (
        <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden mb-8 slide-up-in">
          <div className="p-6 border-b border-slate-200/60 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-xl flex items-center justify-center shadow-md">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-800">转换结果</h3>
                <p className="text-sm text-slate-500">AI 已将小说转换为分镜剧本</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopy}
                className="px-4 py-2 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors font-medium flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                复制
              </button>
              <button
                onClick={handleDownload}
                className="px-4 py-2 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors font-medium flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                下载
              </button>
            </div>
          </div>

          {/* Tab 切换 */}
          <div className="px-6 border-b border-slate-200/60">
            <div className="flex gap-6">
              <button
                onClick={() => setActiveResultTab("script")}
                className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeResultTab === "script"
                    ? "border-indigo-500 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                剧本内容
              </button>
              <button
                onClick={() => setActiveResultTab("shots")}
                className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeResultTab === "shots"
                    ? "border-indigo-500 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                分镜脚本
              </button>
            </div>
          </div>

          {/* 剧本内容 */}
          {activeResultTab === "script" && (
            <div className="p-6">
              <div className="bg-slate-50/80 border border-slate-200 rounded-2xl p-6">
                <pre className="whitespace-pre-wrap text-sm text-slate-700 leading-relaxed font-sans">
                  {result.script}
                </pre>
              </div>
            </div>
          )}

          {/* 分镜脚本 */}
          {activeResultTab === "shots" && (
            <div className="p-6 space-y-4">
              {result.shots.map((shot) => (
                <div key={shot.num} className="flex gap-4 p-4 bg-slate-50/80 rounded-2xl border border-slate-200/60">
                  <div className="w-14 h-10 bg-gradient-to-br from-indigo-400 to-purple-500 rounded-lg flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                    {String(shot.num).padStart(2, "0")}
                  </div>
                  <div className="flex-1">
                    <h5 className="font-semibold text-slate-800 mb-1">{shot.shotType}</h5>
                    <p className="text-sm text-slate-600 mb-2">{shot.desc}</p>
                    <p className="text-xs text-slate-500 italic mb-2">{shot.dialogue}</p>
                    <div className="flex flex-wrap gap-2">
                      <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">{shot.shotType}</span>
                      <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">{shot.duration}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ==================== 章节列表区（点击历史记录后显示） ==================== */}
      {selectedNovelId && (
        <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden mb-8 slide-up-in">
          <div className="p-6 border-b border-slate-200/60 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={handleBackToList} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
                <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-xl flex items-center justify-center shadow-md">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-800">{selectedNovelTitle}</h3>
                <p className="text-sm text-slate-500">
                  {chaptersLoading ? "加载中..." : `共 ${novelChapters.length} 个场景`}
                </p>
              </div>
            </div>
          </div>

          <div className="p-6">
            {chaptersLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                <span className="ml-3 text-slate-500 text-sm">正在加载章节...</span>
              </div>
            ) : novelChapters.length === 0 ? (
              <div className="text-center py-12 text-slate-400 text-sm">暂无章节数据</div>
            ) : (
              <div className="space-y-3">
                {novelChapters.map((ch, i) => {
                  const gradient = GRADIENT_LIST[i % GRADIENT_LIST.length];
                  const statusLabel = ch.clone_status === "SEGMENTS_DONE"
                    ? { text: "已完成", color: "text-emerald-600 bg-emerald-50" }
                    : ch.clone_status === "FAILED"
                    ? { text: "失败", color: "text-red-600 bg-red-50" }
                    : { text: "处理中", color: "text-amber-600 bg-amber-50" };
                  return (
                    <div
                      key={ch.id}
                      className="flex items-center gap-4 p-4 bg-slate-50/80 rounded-2xl border border-slate-200/60 hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => handleViewChapterDetail(ch)}
                    >
                      <div className={`w-12 h-12 bg-gradient-to-br ${gradient} rounded-xl flex items-center justify-center text-white font-bold text-sm flex-shrink-0`}>
                        {ch.scene_index !== null ? `S${ch.scene_index + 1}` : `C${(ch.chapter_index ?? i) + 1}`}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm truncate">
                          {ch.chapter_title || `场景 ${i + 1}`}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {ch.chapter_index !== null && `第${ch.chapter_index + 1}章`}
                          {ch.scene_index !== null && ` · 场景${ch.scene_index + 1}`}
                        </div>
                      </div>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${statusLabel.color}`}>
                        {statusLabel.text}
                      </span>
                      {(ch.clone_status === "PLOT_DONE" || ch.clone_status === "SEGMENTS_DONE") && (
                        <div className="w-8 h-8 bg-emerald-50 rounded-lg flex items-center justify-center flex-shrink-0">
                          <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ==================== 历史记录区 ==================== */}
      <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden">
        <div className="p-6 border-b border-slate-200/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-800">历史转换记录</h3>
              <p className="text-sm text-slate-500">查看所有小说转剧本任务</p>
            </div>
          </div>
          <button className="text-sm text-indigo-600 hover:text-indigo-700 font-medium">查看全部 →</button>
        </div>

        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          {history.map((item, i) => (
            <div key={item.id} className="p-4 bg-slate-50/80 rounded-2xl border border-slate-200/60 hover:shadow-md transition-shadow cursor-pointer" onClick={() => handleViewChapters(item.id, item.title)}>
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-14 h-14 bg-gradient-to-br ${GRADIENT_LIST[i % GRADIENT_LIST.length]} rounded-xl flex items-center justify-center text-white font-bold text-lg flex-shrink-0`}>
                  {item.title.slice(0, 2)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 truncate">{item.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {item.shots}个分镜 · {item.style} · {item.time}
                  </div>
                </div>
              </div>
              {item.status === "processing" && (
                <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full progress-animated transition-all"
                    style={{ width: `${item.progress || 0}%` }}
                  />
                </div>
              )}
              {item.status === "done" && (
                <div className="flex items-center gap-1 text-xs text-emerald-600">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                  </svg>
                  转换完成
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 详情模态框（复用复制剧本的 DetailModal） */}
      <DetailModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        type="novel"
        title={modalTitle}
        subtitle={modalSubtitle}
        segments={modalSegments}
        category={modalCategory}
        duration={modalDuration}
        videoId={modalVideoId}
        createdAt={modalCreatedAt}
        parsePointer={modalParsePointer}
        scriptContent={modalScriptContent}
        parseScript={modalParseScript}
        canGenerate={modalCanGenerate}
        canExport={modalCanExport}
        onExport={handleExport}
        onGenerate={() => {
          const scriptId = modalVideoId;
          setModalOpen(false);
          if (scriptId) onGenerateVideo?.(scriptId);
        }}
      />
    </>
  );
}
