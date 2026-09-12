export interface ParseHistoryItem {
  id: number;
  title: string;
  duration: string;
  shots: number;
  status: 'done' | 'processing' | 'failed';
  time: string;
  source: string;
  tag: string;
  tagColor: string;
  progress?: number;
}

export interface CopyHistoryItem {
  id: number;
  title: string;
  source: string;
  status: 'done' | 'processing' | 'failed';
  time: string;
  theme: string;
  progress?: number;
  product?: string;
  /** 后端 CloneScript ID，用于轮询状态 */
  cloneScriptId?: number;
  /** 后端 clone_status 原始值 */
  cloneStatus?: string;
  /** 用于展示的标题（区别于后端 id） */
  displayTitle?: string;
  /** 后端 source_type 原始值：CLONE=复刻剧本 / ORIGINAL=原片直转渲染 / NOVEL=小说转剧本 */
  sourceType?: string;
}

export interface GenerateHistoryItem {
  id: number;
  title: string;
  duration: string;
  status: 'done' | 'processing' | 'failed';
  time: string;
  source: string;
  style: string;
  step?: number;
  stepPercent?: number;
  cloneScriptId?: number;
  cloneStatus?: string;
}

export interface ScriptItem {
  id: number;
  title: string;
  shots: number;
  tag: string;
  color: string;
  info?: string;
  /** 视频ID（解析剧本）或克隆剧本ID（复制剧本） */
  sourceId?: number;
  /** 来源类型：parse=解析剧本, copy=复制剧本, novel=小说转剧本 */
  sourceType?: 'parse' | 'copy' | 'novel';
}

/** 标签预设池 — 新解析时从中随机抽取 */
export const tagPresets: { tag: string; tagColor: string }[] = [
  { tag: '美食探店', tagColor: 'from-indigo-400 to-purple-500' },
  { tag: '知识科普', tagColor: 'from-orange-400 to-red-500' },
  { tag: '生活技巧', tagColor: 'from-emerald-400 to-teal-500' },
  { tag: '情感语录', tagColor: 'from-pink-400 to-rose-500' },
  { tag: '旅行攻略', tagColor: 'from-cyan-400 to-blue-500' },
  { tag: '数码测评', tagColor: 'from-blue-400 to-indigo-500' },
  { tag: '健身教学', tagColor: 'from-lime-400 to-green-500' },
  { tag: '宠物日常', tagColor: 'from-amber-400 to-yellow-500' },
  { tag: '穿搭分享', tagColor: 'from-fuchsia-400 to-pink-500' },
  { tag: '职场干货', tagColor: 'from-slate-500 to-gray-700' },
  { tag: '读书分享', tagColor: 'from-teal-400 to-cyan-600' },
  { tag: '影视解说', tagColor: 'from-rose-400 to-red-600' },
  { tag: '音乐翻唱', tagColor: 'from-violet-400 to-purple-600' },
  { tag: '手工DIY', tagColor: 'from-orange-300 to-amber-500' },
  { tag: '汽车评测', tagColor: 'from-gray-500 to-slate-800' },
  { tag: '母婴育儿', tagColor: 'from-sky-400 to-blue-500' },
  { tag: '家居好物', tagColor: 'from-yellow-400 to-orange-500' },
  { tag: '游戏解说', tagColor: 'from-green-400 to-emerald-600' },
  { tag: '理财科普', tagColor: 'from-indigo-400 to-blue-600' },
  { tag: '户外探险', tagColor: 'from-emerald-500 to-teal-700' },
];

/** 随机获取一个标签预设 */
export function getRandomTagPreset(): { tag: string; tagColor: string } {
  return tagPresets[Math.floor(Math.random() * tagPresets.length)];
}

/** 额外的渐变色池，用于动态扩容的新标签（避免与预设标签配色重复） */
const extraGradientColors = [
  'from-indigo-500 to-violet-600',
  'from-cyan-500 to-blue-700',
  'from-emerald-500 to-green-700',
  'from-amber-500 to-orange-700',
  'from-rose-500 to-red-700',
  'from-fuchsia-500 to-purple-700',
  'from-sky-500 to-indigo-700',
  'from-lime-500 to-emerald-700',
  'from-teal-500 to-cyan-700',
  'from-pink-500 to-rose-700',
];

/**
 * 解析类型归属 / 保底扩容。
 * - 传入的 type 命中预设池 → 返回对应标签与配色
 * - 传入的 type 不在池里 → 动态生成一个新类型标签（配色取自 extraGradientColors，按哈希取模保证稳定且不冲突）
 * - 未传入 type（解析不出类型）→ 随机抽一个预设标签兜底
 */
export function resolveTag(type?: string): { tag: string; tagColor: string } {
  if (type && type.trim()) {
    const found = tagPresets.find((p) => p.tag === type);
    if (found) return found;
    // 不在池中，动态扩容：用字符串哈希映射到 extraGradientColors
    let hash = 0;
    for (let i = 0; i < type.length; i++) {
      hash = (hash * 31 + type.charCodeAt(i)) >>> 0;
    }
    const tagColor = extraGradientColors[hash % extraGradientColors.length];
    return { tag: type, tagColor };
  }
  // 保底：随机兜底
  return getRandomTagPreset();
}
