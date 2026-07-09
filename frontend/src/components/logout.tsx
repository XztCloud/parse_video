'use client';

import { useRouter } from 'next/navigation';
import { useState, useEffect } from 'react';
import { api, logout } from '@/lib/api';
import { LayoutRouter } from 'next/dist/server/app-render/entry-base';

export default function LogoutButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [username, setUsername] = useState('加载中...');

  // 组件加载时，从本地读取用户名
  useEffect(() => {
    const storedUser = localStorage.getItem('username');
    if (storedUser) {
      // 如果是邮箱，可以只截取 @ 前面的部分作为昵称，更美观
      const displayName = storedUser.includes('@') ? storedUser.split('@')[0] : storedUser;
      setUsername(displayName);
    } else {
      setUsername('未登录');
    }
  }, []);

  const handleLogout = async () => {
    if (!confirm('确定要退出登录吗？')) return;
    setLoading(true);

    try {
      await logout()
      router.push('/login');
      router.refresh();
    } catch (error) {
      console.error('登出失败:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-3 rounded-full border border-gray-100 bg-gray-50/50 p-1.5 pr-3 transition duration-150 hover:bg-gray-50">
      {/* 用户头像徽章（取名字前两个字母大写） */}
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white shadow-sm uppercase">
        {username.slice(0, 2)}
      </div>

      {/* 用户名展示 */}
      <span className="max-w-[120px] truncate text-sm font-medium text-gray-700">
        {username}
      </span>

      {/* 竖线分割 */}
      <div className="h-4 w-px bg-gray-200" />

      {/* 登出小按钮 */}
      <button
        onClick={handleLogout}
        disabled={loading}
        title="退出登录"
        className="text-gray-400 hover:text-red-500 disabled:opacity-50 transition duration-150 focus:outline-none"
      >
        {loading ? (
          <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        ) : (
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
          </svg>
        )}
      </button>
    </div>
  );
}