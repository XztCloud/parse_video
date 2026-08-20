"use client";

import { useRouter } from "next/navigation";
import LogoutButton from "@/components/logout";

type ModuleKey = "parse" | "clone" | "render";

const MODULES: {
  key: ModuleKey;
  name: string;
  desc: string;
  icon: string;
}[] = [
  {
    key: "parse",
    name: "解析视频",
    desc: "上传视频或输入抖音链接，解析出剧本与分镜",
    icon: "📥",
  },
  {
    key: "clone",
    name: "复刻剧本",
    desc: "选择一个主题，生成复刻剧本与分镜",
    icon: "✍️",
  },
  {
    key: "render",
    name: "生成视频",
    desc: "由剧本+分镜渲染 音频 / 图片 / 分镜视频 / 成片",
    icon: "🎬",
  },
];

export default function Home() {
  const router = useRouter();

  const MODULE_ROUTES: Record<ModuleKey, string> = {
    parse: "/",
    clone: "/clone-videos",
    render: "/render-videos",
  };

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-gray-100 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex flex-col space-y-0.5">
            <h1 className="bg-gradient-to-r from-gray-900 to-gray-700 bg-clip-text text-xl font-bold tracking-tight text-transparent sm:text-2xl">
              视频创作工作台
            </h1>
            <p className="hidden text-xs text-gray-400 sm:block">
              模块化创作：解析 → 复刻 → 生成
            </p>
          </div>
          <LogoutButton />
        </div>
      </header>

      {/* 模块卡片 */}
      <div className="max-w-3xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {MODULES.map((m) => (
            <button
              key={m.key}
              onClick={() => router.push(MODULE_ROUTES[m.key])}
              className="group rounded-2xl border border-gray-200 bg-white p-8 text-left shadow-sm transition-all hover:-translate-y-1 hover:border-blue-300 hover:shadow-md"
            >
              <div className="text-4xl mb-4">{m.icon}</div>
              <div className="text-lg font-semibold text-gray-900 group-hover:text-blue-600">
                {m.name}
              </div>
              <div className="mt-2 text-sm text-gray-500 leading-relaxed">
                {m.desc}
              </div>
              <div className="mt-4 text-sm font-medium text-blue-500 opacity-0 transition-opacity group-hover:opacity-100">
                进入 →
              </div>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
