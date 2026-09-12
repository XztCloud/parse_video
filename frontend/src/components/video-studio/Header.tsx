"use client";

interface HeaderProps {
  activeTab: string;
}

const titles: Record<string, { title: string; desc: string }> = {
  parse: { title: '解析视频', desc: '上传视频或粘贴链接，AI 自动提取剧本与分镜' },
  novel: { title: '小说转剧本', desc: '粘贴小说内容，AI 一键转换为分镜剧本' },
  copy: { title: '复制剧本', desc: '基于已有剧本，AI 创意改写生成新版本' },
  generate: { title: '生成视频', desc: '选择剧本，四步流水线生成专业视频' },
};

export default function Header({ activeTab }: HeaderProps) {
  const { title, desc } = titles[activeTab] || titles.parse;

  return (
    <header className="glass border-b border-white/50 sticky top-0 z-30">
      <div className="px-8 py-4 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">{title}</h2>
          <p className="text-sm text-slate-500 mt-0.5">{desc}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <input
              type="text"
              placeholder="搜索任务..."
              className="w-64 pl-10 pr-4 py-2.5 bg-white/60 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm transition-all"
            />
            <svg className="w-5 h-5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <button className="relative p-2.5 text-slate-600 hover:bg-white/60 rounded-xl transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full ring-2 ring-white" />
          </button>
        </div>
      </div>
    </header>
  );
}
