"use client";

import { useEffect, useState, useCallback } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import ParseVideoTab from "./ParseVideoTab";
import NovelScriptTab from "./NovelScriptTab";
import CopyScriptTab from "./CopyScriptTab";
import GenerateVideoTab from "./GenerateVideoTab";
import DetailModal from "./DetailModal";
import { listVideos, getScript, getCloneScript, listAllCloneScripts, listNovels, getNovelScripts, ScriptSegment, VideoListItem, CloneAllItem } from "@/lib/api";
import {
  ParseHistoryItem,
  CopyHistoryItem,
  GenerateHistoryItem,
  ScriptItem,
  tagPresets,
} from "./data";

const DEFAULT_TAG_COLOR = "from-cyan-400 to-blue-500";

function tagColorFor(name: string | null | undefined): string {
  if (!name) return DEFAULT_TAG_COLOR;
  return tagPresets.find((t) => t.tag === name)?.tagColor || DEFAULT_TAG_COLOR;
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds && seconds !== 0) return "计算中";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 将后端 VideoListItem 映射成 ParseHistoryItem */
function mapVideoToParseItem(v: VideoListItem): ParseHistoryItem {
  const isDone = v.status === "done";
  const isFailed = v.status === "failed";
  return {
    id: v.id,
    title: v.filename || "未命名视频",
    duration: formatDuration(v.duration),
    shots: 0,
    status: isDone ? "done" : isFailed ? "failed" : "processing",
    time: isDone ? (v.category || "已解析") : isFailed ? "解析失败" : "解析中",
    source: "上传视频",
    tag: (isDone && v.category) || (isDone ? "未分类" : isFailed ? "解析失败" : "解析中"),
    tagColor: isDone ? tagColorFor(v.category) : DEFAULT_TAG_COLOR,
    progress: (isDone || isFailed) ? undefined : v.progress,
  };
}

export default function VideoStudio() {
  const [activeTab, setActiveTab] = useState("parse");
  const [parseHistoryData, setParseHistoryData] = useState<ParseHistoryItem[]>([]);
  const [copyHistoryData, setCopyHistoryData] = useState<CopyHistoryItem[]>([]);
  const [generateHistoryData, setGenerateHistoryData] = useState<GenerateHistoryItem[]>([]);
  // 后端视频元数据缓存（id -> video），供详情弹窗使用
  const [videosMeta, setVideosMeta] = useState<Record<number, VideoListItem>>({});

  // Detail modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<"parse" | "copy" | "novel">("parse");
  const [modalTitle, setModalTitle] = useState("");
  const [modalSubtitle, setModalSubtitle] = useState("");
  const [modalSegments, setModalSegments] = useState<ScriptSegment[]>([]);
  const [modalCategory, setModalCategory] = useState<string | null>(null);
  const [modalTypeSummary, setModalTypeSummary] = useState<string | null>(null);
  const [modalDuration, setModalDuration] = useState<number | null>(null);
  const [modalVideoId, setModalVideoId] = useState<number | null>(null);
  const [modalCreatedAt, setModalCreatedAt] = useState<string | null>(null);
  const [modalParsePointer, setModalParsePointer] = useState<any>(null);
  const [modalScriptContent, setModalScriptContent] = useState<any>(null);
  const [modalParseScript, setModalParseScript] = useState<any>(null);

  // 生成视频页面的剧本数据
  const [genParsedScripts, setGenParsedScripts] = useState<ScriptItem[]>([]);
  const [genClonedScripts, setGenClonedScripts] = useState<ScriptItem[]>([]);
  const [genNovelScripts, setGenNovelScripts] = useState<ScriptItem[]>([]);

  // 拉取真实视频列表
  const fetchVideos = useCallback(async () => {
    try {
      const videos = await listVideos();
      const meta: Record<number, VideoListItem> = {};
      videos.forEach((v) => { meta[v.id] = v; });
      setVideosMeta(meta);
      setParseHistoryData(videos.map(mapVideoToParseItem));

      // 构建解析剧本列表（DONE 状态的视频）
      const doneVideos = videos.filter(v => v.status === 'done');
      const parsed: ScriptItem[] = doneVideos.map(v => {
        const tag = v.category || '未分类';
        const dur = v.duration ?? 0;
        const m = Math.floor(dur / 60);
        const s = Math.floor(dur % 60);
        return {
          id: v.id,
          title: v.filename,
          shots: 0,
          tag,
          color: tagColorFor(tag),
          info: `时长 ${m}:${String(s).padStart(2, '0')}`,
          sourceId: v.id,
          sourceType: 'parse' as const,
        };
      });
      setGenParsedScripts(parsed);
    } catch {
      // API 失败时保持空列表
    }
  }, []);

  // 拉取复刻剧本列表 + 生成历史
  const fetchCloneAndGenHistory = useCallback(async () => {
    try {
      const allItems = await listAllCloneScripts(0, 50);

      // 构建复制剧本列表（仅 source_type 为 CLONE，且 SEGMENTS_DONE）
      const cloned: ScriptItem[] = allItems
        .filter(item => item.source_type === 'CLONE' && item.clone_status === 'SEGMENTS_DONE')
        .map(item => {
          const tag = item.clone_theme || '未分类';
          return {
            id: item.id,
            title: `${item.video_title.slice(0, 12)} - ${tag}`,
            shots: 0,
            tag,
            color: tagColorFor(item.video_category),
            sourceId: item.id,
            sourceType: 'copy' as const,
          };
        });
      setGenClonedScripts(cloned);

      // 构建生成历史（step3+ 状态的克隆脚本，基于 generate_flow_status）
      const genStatuses = ['VOICE', 'VOICE_DONE', 'IMAGE', 'IMAGE_DONE', 'FRAME', 'FRAME_DONE', 'SEGMENT_VIDEO', 'SEGMENT_VIDEO_DONE', 'MERGE_VIDEO', 'MERGE_VIDEO_DONE', 'FAILED'];
      const genHistory: GenerateHistoryItem[] = allItems
        .filter(item => genStatuses.includes(item.generate_flow_status))
        .map(item => {
          const isDone = item.generate_flow_status === 'MERGE_VIDEO_DONE' || item.generate_flow_status.endsWith('_DONE');
          const isFailed = item.generate_flow_status === 'FAILED';
          const stepMap: Record<string, number> = {
            VOICE: 1, VOICE_DONE: 1,
            IMAGE: 2, IMAGE_DONE: 2,
            FRAME: 3, FRAME_DONE: 3,
            SEGMENT_VIDEO: 4, SEGMENT_VIDEO_DONE: 4,
            MERGE_VIDEO: 5, MERGE_VIDEO_DONE: 5,
          };
          let displayTime = '—';
          if (item.created_at) {
            try {
              const d = new Date(item.created_at);
              const now = new Date();
              const isToday = d.toDateString() === now.toDateString();
              const hh = String(d.getHours()).padStart(2, '0');
              const mm = String(d.getMinutes()).padStart(2, '0');
              displayTime = isToday ? `今天 ${hh}:${mm}` : `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
            } catch { displayTime = item.created_at; }
          }
          return {
            id: item.id,
            title: `${item.video_title.slice(0, 12)} - ${item.clone_theme}`,
            duration: '—',
            status: isDone ? 'done' : isFailed ? 'failed' : 'processing',
            time: displayTime,
            source: item.source_type === 'ORIGINAL' ? '原片直转' : '剧本复制',
            style: item.clone_theme,
            step: stepMap[item.generate_flow_status] || 0,
            stepPercent: item.generate_flow_progress,
            cloneScriptId: item.id,
            cloneStatus: item.generate_flow_status,
          };
        });
      setGenerateHistoryData(genHistory);
    } catch {
      // 静默失败
    }
  }, []);

  // 拉取小说转剧本的剧本列表
  const fetchNovelScripts = useCallback(async () => {
    try {
      const novels = await listNovels(0, 50);
      const allNovelScripts: ScriptItem[] = [];
      for (const novel of novels) {
        try {
          const scripts = await getNovelScripts(novel.id);
          for (const script of scripts) {
            if (script.source_type !== 'NOVEL') continue;
            allNovelScripts.push({
              id: script.id,
              title: `${novel.title.slice(0, 6)}-${script.chapter_index ?? 0}-${script.chapter_title || `场景 ${(script.scene_index ?? 0) + 1}`}`,
              shots: 0,
              tag: novel.title.slice(0, 6),
              color: 'from-indigo-400 to-blue-500',
              info: `小说转剧本`,
              sourceId: script.id,
              sourceType: 'novel' as const,
            });
          }
        } catch {
          // 单个小说获取失败不影响其他
        }
      }
      setGenNovelScripts(allNovelScripts);
    } catch {
      // 静默失败
    }
  }, []);

  // 首次加载
  useEffect(() => {
    fetchVideos();
    fetchCloneAndGenHistory();
    fetchNovelScripts();
  }, [fetchVideos, fetchCloneAndGenHistory, fetchNovelScripts]);

  const handleViewParseDetail = async (item: ParseHistoryItem) => {
    const meta = videosMeta[item.id];
    setModalType("parse");
    setModalTitle(item.title);
    setModalSubtitle(meta?.type_summary || "视频解析结果预览");
    setModalCategory(meta?.category ?? null);
    setModalTypeSummary(meta?.type_summary ?? null);
    setModalDuration(meta?.duration ?? null);
    setModalVideoId(meta?.id ?? null);
    setModalCreatedAt(meta?.created_at ?? null);

    // 拉取真实分镜
    setModalSegments([]);
    setModalParsePointer(null);
    setModalScriptContent(null);
    setModalParseScript(null);
    if (item.status === "done") {
      try {
        const script = await getScript(item.id);
        setModalSegments(script.segments || []);
        setModalParsePointer(script.parse_pointer || null);
        setModalScriptContent(script.content || null);
        setModalParseScript(script.parse_script || null);
      } catch {
        setModalSegments([]);
        setModalParsePointer(null);
        setModalScriptContent(null);
        setModalParseScript(null);
      }
    }
    setModalOpen(true);
  };

  const handleViewCopyDetail = async (item: any) => {
    setModalType("copy");
    setModalTitle(item.displayTitle || item.title || "复制剧本详情");
    setModalSubtitle(item.theme ? `主题: ${item.theme}` : "AI 创意改写结果");
    setModalSegments([]);
    setModalParsePointer(null);
    setModalScriptContent(null);
    setModalParseScript(null);
    setModalOpen(true);

    // 如果有 cloneScriptId，拉取真实的克隆剧本数据
    if (item.cloneScriptId) {
      try {
        const cloneDetail = await getCloneScript(item.cloneScriptId);
        setModalSegments(cloneDetail.segments || []);
        setModalScriptContent(cloneDetail.content || null);
        setModalParsePointer(cloneDetail.clone_parse_pointer || null);
        setModalParseScript(cloneDetail.clone_parse_script?.plot_script || null);
        setModalCreatedAt(cloneDetail.created_at || null);
        setModalVideoId(cloneDetail.id || null);
      } catch {
        setModalSegments([]);
        setModalParsePointer(null);
        setModalScriptContent(null);
        setModalParseScript(null);
      }
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/30 to-purple-50/40">
      {/* 背景装饰 */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute -top-40 -right-40 w-[500px] h-[500px] bg-indigo-300/20 rounded-full blur-3xl" />
        <div className="absolute top-1/3 -left-20 w-[400px] h-[400px] bg-purple-300/20 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 right-1/4 w-[450px] h-[450px] bg-pink-300/15 rounded-full blur-3xl" />
      </div>

      <div className="flex min-h-screen">
        {/* 侧边栏 */}
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

        {/* 主内容区 */}
        <main className="flex-1 overflow-x-hidden">
          <Header activeTab={activeTab} />

          <div className="p-8">
            {activeTab === "parse" && (
              <ParseVideoTab
                history={parseHistoryData}
                onHistoryChange={setParseHistoryData}
                onViewDetail={handleViewParseDetail}
                onRefresh={fetchVideos}
              />
            )}
            {activeTab === "novel" && (
              <NovelScriptTab />
            )}
            {activeTab === "copy" && (
              <CopyScriptTab
                history={copyHistoryData}
                onHistoryChange={setCopyHistoryData}
                onViewDetail={handleViewCopyDetail}
                sourceVideos={Object.values(videosMeta)
                  .filter(v => v.status === 'done')
                  .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))}
              />
            )}
            {activeTab === "generate" && (
              <GenerateVideoTab
                history={generateHistoryData}
                onRefresh={async () => { await fetchCloneAndGenHistory(); await fetchNovelScripts(); }}
                parsedScripts={genParsedScripts}
                clonedScripts={genClonedScripts}
                novelScripts={genNovelScripts}
              />
            )}
          </div>
        </main>
      </div>

      {/* 详情模态框 */}
      <DetailModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        type={modalType}
        title={modalTitle}
        subtitle={modalSubtitle}
        segments={modalSegments}
        category={modalCategory}
        typeSummary={modalTypeSummary}
        duration={modalDuration}
        videoId={modalVideoId}
        createdAt={modalCreatedAt}
        parsePointer={modalParsePointer}
        scriptContent={modalScriptContent}
        parseScript={modalParseScript}
      />
    </div>
  );
}
