'use client';

import { useState, Suspense } from 'react'; // 1. 引入 Suspense
import { useRouter, useSearchParams } from 'next/navigation';
import { login } from '@/lib/api';

// 2. 将原来的登录核心逻辑和 UI 抽离到一个独立的子组件中
function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const router = useRouter();
  
  // 🔥 useSearchParams 放在这个子组件里
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callbackUrl') || '/';

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      await login(formData);

      router.push(callbackUrl);
      router.refresh();
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || '登录失败，请检查账号密码';
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md space-y-8 rounded-xl bg-white p-8 shadow-md border border-gray-100">
      <div>
        <h2 className="mt-6 text-center text-3xl font-bold tracking-tight text-gray-900">欢迎回来</h2>
        <p className="mt-2 text-center text-sm text-gray-600">请登录您的账号以继续</p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-4 border border-red-200">
          <div className="text-sm font-medium text-red-800">{error}</div>
        </div>
      )}

      <form className="mt-8 space-y-6" onSubmit={handleLogin}>
        <div className="space-y-4 rounded-md">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">电子邮箱</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 sm:text-sm"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 sm:text-sm"
              placeholder="••••••••"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="flex w-full justify-center rounded-md bg-blue-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '正在登录...' : '登 录'}
        </button>
      </form>
    </div>
  );
}

// 3. 主页面只负责提供外层布局，并使用 <Suspense> 包裹子组件
export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12 sm:px-6 lg:px-8">
      {/* fallback 是在加载 URL 参数时展示的骨架屏/占位符 */}
      <Suspense fallback={<div className="text-gray-500 text-sm">正在加载登录页面...</div>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}