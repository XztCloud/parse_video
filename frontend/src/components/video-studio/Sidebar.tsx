"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { logout } from "@/lib/api";

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export default function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  const router = useRouter();
  const [username, setUsername] = useState('小鸣同学');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const storedUser = localStorage.getItem('username');
    if (storedUser) {
      const displayName = storedUser.includes('@') ? storedUser.split('@')[0] : storedUser;
      setUsername(displayName);
    }
  }, []);

  const handleLogout = async () => {
    if (!confirm('确定要退出登录吗？')) return;
    setLoading(true);
    try {
      await logout();
      router.push('/login');
      router.refresh();
    } catch (error) {
      console.error('登出失败:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="w-72 glass border-r border-white/50 flex flex-col sticky top-0 h-screen">
      {/* Logo */}
      <div className="p-6 border-b border-slate-200/60">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 rounded-2xl flex items-center justify-center shadow-lg glow-indigo">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold gradient-text">Video Studio</h1>
            <p className="text-xs text-slate-500">AI 视频创作工作台</p>
          </div>
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex-1 p-4 space-y-2">
        <div className="mb-4 px-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">创作流程</p>
        </div>

        {/* 模块1：解析视频 */}
        <button
          onClick={() => onTabChange('parse')}
          className={`nav-item w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl transition-all duration-300 text-left ${
            activeTab === 'parse'
              ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg glow-indigo'
              : 'text-slate-600 hover:bg-white/60'
          }`}
        >
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${
            activeTab === 'parse' ? 'bg-white/20' : 'bg-slate-100'
          }`}>
            <svg className={`w-5 h-5 ${activeTab === 'parse' ? 'text-white' : 'text-slate-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div className="flex-1">
            <div className="font-medium">解析视频</div>
            <div className={`text-xs ${activeTab === 'parse' ? 'text-white/70' : 'text-slate-400'}`}>提取剧本与分镜</div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            activeTab === 'parse' ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-500'
          }`}>1</span>
        </button>

        {/* 模块2：复制剧本 */}
        <button
          onClick={() => onTabChange('copy')}
          className={`nav-item w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl transition-all duration-300 text-left ${
            activeTab === 'copy'
              ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg glow-indigo'
              : 'text-slate-600 hover:bg-white/60'
          }`}
        >
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${
            activeTab === 'copy' ? 'bg-white/20' : 'bg-slate-100'
          }`}>
            <svg className={`w-5 h-5 ${activeTab === 'copy' ? 'text-white' : 'text-slate-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div className="flex-1">
            <div className="font-medium">复制剧本</div>
            <div className={`text-xs ${activeTab === 'copy' ? 'text-white/70' : 'text-slate-400'}`}>AI 创意改写</div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            activeTab === 'copy' ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-500'
          }`}>2</span>
        </button>

        {/* 模块3：生成视频 */}
        <button
          onClick={() => onTabChange('generate')}
          className={`nav-item w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl transition-all duration-300 text-left ${
            activeTab === 'generate'
              ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg glow-indigo'
              : 'text-slate-600 hover:bg-white/60'
          }`}
        >
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${
            activeTab === 'generate' ? 'bg-white/20' : 'bg-slate-100'
          }`}>
            <svg className={`w-5 h-5 ${activeTab === 'generate' ? 'text-white' : 'text-slate-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="flex-1">
            <div className="font-medium">生成视频</div>
            <div className={`text-xs ${activeTab === 'generate' ? 'text-white/70' : 'text-slate-400'}`}>一键成片输出</div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            activeTab === 'generate' ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-500'
          }`}>3</span>
        </button>

        <div className="mt-8 mb-4 px-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">其他</p>
        </div>

        <button className="w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-slate-600 hover:bg-white/60 transition-all text-left">
          <div className="w-9 h-9 bg-slate-100 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <span className="font-medium">设置</span>
        </button>
      </nav>

      {/* 用户信息 */}
      <div className="p-4 border-t border-slate-200/60">
        <div className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/60 transition-colors">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-white font-bold shadow-md">
            {username.slice(0, 1).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-slate-800 truncate">{username}</div>
            <div className="text-xs text-slate-500">专业版</div>
          </div>
          {/* 退出按钮 */}
          <button
            onClick={handleLogout}
            disabled={loading}
            title="退出登录"
            className="p-2.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors disabled:opacity-50"
          >
            {loading ? (
              <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </aside>
  );
}
