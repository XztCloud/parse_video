"use client";

import { useState } from "react";
import { ScriptSegment } from "@/lib/api";

interface DetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  type: 'parse' | 'copy' | 'novel';
  title?: string;
  subtitle?: string;
  segments?: ScriptSegment[];
  category?: string | null;
  typeSummary?: string | null;
  duration?: number | null;
  videoId?: number | null;
  createdAt?: string | null;
  parsePointer?: {
    role_library?: { role_name: string; gender: string; age: number; voice_style_guide?: string; effect: string }[];
    scene_library?: { scene_name: string; environment_description: string; color_grading: string }[];
    global_style?: { global_style_suffix: string };
    core_shell_point?: { user_pain_point: string; product_usp: string[]; hook_trigger: string; keywords_to_include: string[] } | null;
  } | null;
  scriptContent?: any;
  parseScript?: any;
}

const storyboardData = [
  { num: '01', title: '胡同外景', desc: '镜头从胡同口缓缓推进，灰瓦青砖，阳光洒落', tags: ['全景', '推进镜头', '3秒'], color: 'from-indigo-400 to-purple-500' },
  { num: '02', title: '推门而入', desc: '手推木门特写，门吱呀一声打开，店内暖光涌出', tags: ['特写', '慢动作', '2秒'], color: 'from-purple-400 to-pink-500' },
  { num: '03', title: '炸酱特写', desc: '锅中炸酱翻滚冒泡，浓郁酱香，配福叔旁白', tags: ['微距', '特写', '4秒'], color: 'from-pink-400 to-rose-500' },
  { num: '04', title: '成品展示', desc: '一碗面端上来，各色菜码整齐，筷子拌匀的特写', tags: ['俯拍', '3秒'], color: 'from-rose-400 to-orange-500' },
  { num: '05', title: '品尝反应', desc: '吃一口面，露出满足的表情，点头称赞', tags: ['中景', '2秒'], color: 'from-orange-400 to-amber-500' },
  { num: '06', title: '结尾收尾', desc: '福叔在门口挥手，镜头拉远淡出，配文字总结', tags: ['拉远', '淡出', '3秒'], color: 'from-amber-400 to-yellow-500' },
];

const tagColors = [
  'from-indigo-400 to-purple-500',
  'from-purple-400 to-pink-500',
  'from-pink-400 to-rose-500',
  'from-rose-400 to-orange-500',
  'from-orange-400 to-amber-500',
  'from-amber-400 to-yellow-500',
  'from-emerald-400 to-teal-500',
  'from-cyan-400 to-blue-500',
  'from-sky-400 to-indigo-500',
  'from-fuchsia-400 to-purple-600',
];

/** 从 shot_description 截取短标题（去掉分组前缀，取第一行前20字） */
function extractTitle(desc: string): string {
  if (!desc) return '';
  const cleaned = desc.replace(/【.*?】\s*/g, '').trim();
  const firstLine = cleaned.split('\n')[0] || cleaned;
  return firstLine.length > 20 ? firstLine.slice(0, 20) + '...' : firstLine;
}

/** 从 shot_description 截取完整描述（去掉分组前缀和标题行） */
function extractDesc(desc: string): string {
  if (!desc) return '';
  const cleaned = desc.replace(/【.*?】\s*/g, '').trim();
  const lines = cleaned.split('\n');
  return lines.length > 1 ? lines.slice(1).join('\n') : cleaned;
}

function formatTime(ms: number): string {
  // 兼容秒和毫秒：如果值 < 1000 认为是秒，否则是毫秒
  const totalSeconds = ms < 1000 ? ms : ms / 1000;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds && seconds !== 0) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const h = Math.floor(m / 60);
  if (h > 0) {
    return `${h}分${m % 60}秒`;
  }
  return `${m}分${s}秒`;
}

export default function DetailModal({
  isOpen,
  onClose,
  type,
  title,
  subtitle,
  segments,
  category,
  typeSummary,
  duration,
  videoId,
  createdAt,
  parsePointer,
  scriptContent,
  parseScript,
}: DetailModalProps) {
  const [activeTab, setActiveTab] = useState<'script' | 'storyboard' | 'info'>('script');

  if (!isOpen) return null;

  const modalTitle = title || (type === 'parse' ? '解析详情' : type === 'copy' ? '复制剧本详情' : '小说剧本详情');
  const modalSubtitle = subtitle || (type === 'parse' ? '视频解析结果预览' : type === 'copy' ? 'AI 创意改写结果' : '小说转剧本结果');
  const iconColor = type === 'parse' ? 'from-indigo-500 to-purple-500' : type === 'copy' ? 'from-purple-500 to-pink-500' : 'from-indigo-500 to-blue-500';
  const hasRealData = Array.isArray(segments) && segments.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden modal-in">
        {/* 模态框头部 */}
        <div className="p-6 border-b border-slate-200 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 bg-gradient-to-br ${iconColor} rounded-xl flex items-center justify-center`}>
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-800">{modalTitle}</h3>
              <p className="text-sm text-slate-500">{modalSubtitle}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
            <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 模态框内容 */}
        <div className="overflow-y-auto max-h-[calc(85vh-80px)]">
          {/* Tab 切换 */}
          <div className="px-6 pt-6 border-b border-slate-200 flex gap-6">
            <button
              onClick={() => setActiveTab('script')}
              className={`pb-3 border-b-2 font-medium text-sm ${
                activeTab === 'script'
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              📝 剧本内容
            </button>
            <button
              onClick={() => setActiveTab('storyboard')}
              className={`pb-3 border-b-2 font-medium text-sm ${
                activeTab === 'storyboard'
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              🎬 分镜脚本
            </button>
            <button
              onClick={() => setActiveTab('info')}
              className={`pb-3 border-b-2 font-medium text-sm ${
                activeTab === 'info'
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              ℹ️ 任务信息
            </button>
          </div>

          <div className="p-6 pb-16">
            {/* 剧本内容 Tab */}
            {activeTab === 'script' && (
              <div className="space-y-6">
                {/* 核心主题 */}
                <div className="p-4 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-2xl border border-indigo-100">
                  <h4 className="font-bold text-slate-800 mb-2">📌 核心主题</h4>
                  <p className="text-slate-700">{typeSummary || (category ? `${category} - 视频内容分析` : '美食探店 - 北京胡同里的百年老店')}</p>
                </div>

                {hasRealData && parsePointer ? (
                  <>
                    {/* 角色信息 */}
                    {parsePointer.role_library && parsePointer.role_library.length > 0 && (
                      <div>
                        <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                          <span className="w-1 h-5 bg-gradient-to-b from-indigo-500 to-purple-500 rounded-full" />
                          角色信息
                        </h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {parsePointer.role_library.map((role, i) => (
                            <div key={i} className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="font-semibold text-slate-800">{role.role_name}</span>
                                <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">{role.gender === 'male' ? '男' : '女'}</span>
                                <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">约{role.age}岁</span>
                              </div>
                              <p className="text-sm text-slate-600 mb-1">{role.effect}</p>
                              {role.voice_style_guide && (
                                <p className="text-xs text-slate-400">🎙 {role.voice_style_guide}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 场景信息 */}
                    {parsePointer.scene_library && parsePointer.scene_library.length > 0 && (
                      <div>
                        <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                          <span className="w-1 h-5 bg-gradient-to-b from-purple-500 to-pink-500 rounded-full" />
                          场景信息
                        </h4>
                        <div className="space-y-3">
                          {parsePointer.scene_library.map((scene, i) => (
                            <div key={i} className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                              <h5 className="font-semibold text-slate-800 mb-1">{scene.scene_name}</h5>
                              <p className="text-sm text-slate-600 mb-1">{scene.environment_description}</p>
                              {scene.color_grading && (
                                <p className="text-xs text-slate-400">🎨 {scene.color_grading}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 全局风格 */}
                    {parsePointer.global_style && (
                      <div>
                        <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                          <span className="w-1 h-5 bg-gradient-to-b from-pink-500 to-rose-500 rounded-full" />
                          全局风格
                        </h4>
                        <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                          <p className="text-sm text-slate-600">{parsePointer.global_style.global_style_suffix}</p>
                        </div>
                      </div>
                    )}

                    {/* 推广点 */}
                    {parsePointer.core_shell_point && (
                      <div>
                        <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                          <span className="w-1 h-5 bg-gradient-to-b from-rose-500 to-orange-500 rounded-full" />
                          推广信息
                        </h4>
                        <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60 space-y-2">
                          {parsePointer.core_shell_point.user_pain_point && (
                            <div>
                              <span className="text-xs font-medium text-slate-500">用户痛点</span>
                              <p className="text-sm text-slate-600">{parsePointer.core_shell_point.user_pain_point}</p>
                            </div>
                          )}
                          {parsePointer.core_shell_point.product_usp.length > 0 && (
                            <div>
                              <span className="text-xs font-medium text-slate-500">产品卖点</span>
                              <ul className="text-sm text-slate-600 list-disc list-inside">
                                {parsePointer.core_shell_point.product_usp.map((usp, i) => (
                                  <li key={i}>{usp}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {parsePointer.core_shell_point.hook_trigger && (
                            <div>
                              <span className="text-xs font-medium text-slate-500">钩子设计</span>
                              <p className="text-sm text-slate-600">{parsePointer.core_shell_point.hook_trigger}</p>
                            </div>
                          )}
                          {parsePointer.core_shell_point.keywords_to_include.length > 0 && (
                            <div>
                              <span className="text-xs font-medium text-slate-500">关键词</span>
                              <div className="flex flex-wrap gap-2 mt-1">
                                {parsePointer.core_shell_point.keywords_to_include.map((kw, i) => (
                                  <span key={i} className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-xs rounded">{kw}</span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 完整剧本（parse_script 剧情段落） */}
                    {Array.isArray(parseScript) && parseScript.length > 0 && (
                      <div>
                        <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                          <span className="w-1 h-5 bg-gradient-to-b from-indigo-500 to-purple-500 rounded-full" />
                          完整剧本
                        </h4>
                        <div className="space-y-4">
                          {parseScript.map((seg: any, i: number) => {
                            const theme = seg.paragraph_theme || seg.plot_tag || '';
                            const desc = seg.screen_description || seg.shot_description || '';
                            const lines = Array.isArray(seg.actor_lines)
                              ? seg.actor_lines.map((a: any) => ({ speaker: a.role_name || '?', text: a.lines || '', audio: a.audio_style || '' }))
                              : Array.isArray(seg.dialogue)
                                ? (typeof seg.dialogue === 'string'
                                    ? seg.dialogue.split(/\d+:/g).filter(Boolean).map((t: string) => ({ speaker: '', text: t.trim(), audio: '' }))
                                    : seg.dialogue.map((d: any) => ({ speaker: d.speaker || '?', text: d.text || '', audio: '' }))
                                  )
                                : [];
                            return (
                              <div key={i} className="p-4 bg-slate-50/80 rounded-xl border border-slate-200/60">
                                <div className="flex items-center gap-2 mb-2">
                                  <span className="px-2 py-0.5 bg-indigo-100 text-indigo-600 text-xs rounded-full font-medium">
                                    段落 {i + 1}
                                  </span>
                                  {theme && (
                                    <span className="text-sm font-semibold text-slate-800">{theme}</span>
                                  )}
                                </div>
                                {desc && (
                                  <p className="text-sm text-slate-600 mb-3 leading-relaxed">{desc}</p>
                                )}
                                {lines.length > 0 && (
                                  <div className="border-t border-slate-200/70 pt-2 space-y-1">
                                    {lines.map((l: any, li: number) => (
                                      <p key={li} className="text-xs text-slate-500">
                                        <span className="font-medium text-slate-600">{l.speaker ? `角色${l.speaker}：` : ''}</span>
                                        {l.text}
                                        {l.audio && <span className="ml-2 text-slate-400">（{l.audio}）</span>}
                                      </p>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center text-slate-400 py-8">暂无解析数据</div>
                )}
              </div>
            )}

            {/* 分镜脚本 Tab */}
            {activeTab === 'storyboard' && (
              <div className="space-y-4">
                {(!hasRealData || segments!.length === 0) ? (
                  <div className="text-center text-slate-400 py-8">暂无解析数据</div>
                ) : segments!.map((seg, idx) => {
                  const title = hasRealData
                    ? `${formatTime(seg.start_time)} - ${formatTime(seg.end_time)}`
                    : storyboardData[idx]?.title || '';
                  const desc = hasRealData
                    ? extractDesc(seg.shot_description || '')
                    : storyboardData[idx]?.desc || '';
                  const tags = hasRealData
                    ? (Array.isArray(seg.shot_features) ? seg.shot_features : [])
                    : (storyboardData[idx]?.tags || []);
                  const dialogues = hasRealData && Array.isArray(seg.dialogue) ? seg.dialogue : [];
                  const color = hasRealData
                    ? tagColors[idx % tagColors.length]
                    : storyboardData[idx]?.color || 'from-slate-400 to-slate-600';
                  const num = hasRealData
                    ? String(idx + 1).padStart(2, '0')
                    : storyboardData[idx]?.num || String(idx + 1).padStart(2, '0');
                  const durationSec = seg.end_time - seg.start_time;
                  // 值 < 1000 认为是秒，否则是毫秒
                  const durationText = hasRealData
                    ? `${(durationSec < 1000 ? durationSec : durationSec / 1000).toFixed(1)}s`
                    : null;

                  return (
                    <div key={hasRealData ? (seg.id || idx) : `mock-${idx}`} className="flex gap-4 p-4 bg-slate-50/80 rounded-2xl border border-slate-200/60">
                      <div className={`w-14 h-10 bg-gradient-to-br ${color} rounded-lg flex items-center justify-center text-white font-bold text-sm flex-shrink-0`}>
                        {num}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <h5 className="font-semibold text-slate-800">{title}</h5>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {durationText && (
                              <span className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">{durationText}</span>
                            )}
                            {tags.map((tag: string, fi: number) => (
                              <span key={`r-${idx}-${fi}`} className="px-2 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">{tag}</span>
                            ))}
                          </div>
                        </div>
                        {desc && <p className="text-sm text-slate-600 mb-2">{desc}</p>}
                        {/* 分镜对话（仅真实数据时显示） */}
                        {hasRealData && dialogues.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-slate-200/70 space-y-1">
                            {dialogues.map((d: { speaker: string; text: string }, di: number) => (
                              <p key={di} className="text-xs text-slate-500">
                                <span className="font-medium text-slate-600">角色({d.speaker}): </span>
                                {d.text}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* 任务信息 Tab */}
            {activeTab === 'info' && (() => {
              const dateStr = createdAt ? createdAt.split('T')[0].replace(/-/g, '') : '00000000';
              const idForTask = videoId || 0;
              const taskId = type === 'copy'
                ? `#CLONE-${dateStr}-${idForTask}`
                : (hasRealData && videoId && createdAt
                  ? `#PARSE-${dateStr}-${videoId}`
                  : '#PARSE-20240815-001');
              const createdTime = createdAt
                ? createdAt.replace('T', ' ').slice(0, 16)
                : '—';
              // 视频时长：copy 类型从分镜总时长计算
              const totalDuration = hasRealData
                ? segments!.reduce((sum, s) => sum + (s.end_time - s.start_time), 0)
                : null;
              return (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-500 mb-1">任务ID</p>
                    <p className="font-mono text-sm text-slate-800">{taskId}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-500 mb-1">创建时间</p>
                    <p className="text-sm text-slate-800">{createdTime}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-500 mb-1">视频时长</p>
                    <p className="text-sm text-slate-800">
                      {totalDuration !== null
                        ? formatDuration(totalDuration)
                        : (duration ? formatDuration(duration) : '—')}
                    </p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-500 mb-1">分镜数量</p>
                    <p className="text-sm text-slate-800">{hasRealData ? `${segments!.length}个` : '—'}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-500 mb-1">视频类型</p>
                    <p className="text-sm text-slate-800">{category || (type === 'copy' ? '复刻剧本' : '—')}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-500 mb-1">来源</p>
                    <p className="text-sm text-slate-800">{type === 'copy' ? '剧本复制' : '抖音链接'}</p>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>

        {/* 模态框底部 */}
        <div className="p-4 border-t border-slate-200 bg-slate-50/50 flex justify-end gap-3">
          <button onClick={onClose} className="px-5 py-2.5 text-slate-600 hover:bg-slate-200 rounded-xl transition-colors text-sm font-medium">
            关闭
          </button>
          <button className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-xl text-sm font-medium shadow-md hover:shadow-lg transition-all">
            用此剧本生成视频 →
          </button>
        </div>
      </div>
    </div>
  );
}
