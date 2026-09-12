"use client";

import { useCallback, useEffect, useState } from "react";
import { listUsers, setUserActive, deleteUser, getMe, type UserInfo } from "@/lib/api";

function formatDate(value?: string | null): string {
  if (!value) return '—';
  try {
    const d = new Date(value);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return value;
  }
}

export default function AdminUsersTab() {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');
  // 当前登录账号 id：自身不能删除
  const [meId, setMeId] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setUsers(await listUsers());
    } catch (e: any) {
      setError(e?.response?.data?.detail || '加载账号列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  useEffect(() => {
    (async () => {
      try {
        setMeId((await getMe()).id);
      } catch {
        // 静默失败：拿不到自身 id 时不影响列表展示
      }
    })();
  }, []);

  const handleDelete = useCallback(async (user: UserInfo) => {
    if (!window.confirm(`确认删除账号 ${user.email} 及其全部资产？此操作不可恢复。`)) return;
    setBusyId(user.id);
    setError('');
    try {
      await deleteUser(user.id);
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
    } catch (e: any) {
      setError(e?.response?.data?.detail || '删除失败，请稍后重试');
    } finally {
      setBusyId(null);
    }
  }, []);

  const handleToggle = useCallback(async (user: UserInfo) => {
    setBusyId(user.id);
    setError('');
    try {
      const updated = await setUserActive(user.id, !user.is_active);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (e: any) {
      setError(e?.response?.data?.detail || '操作失败，请稍后重试');
    } finally {
      setBusyId(null);
    }
  }, []);

  return (
    <div className="bg-white/70 backdrop-blur-xl rounded-3xl shadow-xl border border-white/60 overflow-hidden">
      <div className="p-6 border-b border-slate-200/60 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-800">账号管理</h3>
            <p className="text-sm text-slate-500">激活后该账号才能生成配音/图片/视频</p>
          </div>
        </div>
        <button
          onClick={fetchUsers}
          disabled={loading}
          className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 bg-white rounded-xl hover:bg-slate-100 transition-colors disabled:opacity-50"
        >
          刷新
        </button>
      </div>

      {error && (
        <div className="mx-6 mt-4 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center text-slate-400 text-sm">加载中…</div>
      ) : users.length === 0 ? (
        <div className="p-12 text-center text-slate-400 text-sm">暂无账号</div>
      ) : (
        <div className="divide-y divide-slate-100">
          {users.map((u) => (
            <div key={u.id} className="p-5 flex items-center gap-4 hover:bg-slate-50/60 transition-colors">
              <div className="w-12 h-12 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-xl flex items-center justify-center flex-shrink-0 text-indigo-600 font-bold">
                {(u.full_name || u.email).slice(0, 1).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-slate-800 truncate">{u.full_name || u.email.split('@')[0]}</h4>
                  {u.is_superuser && (
                    <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-purple-100 text-purple-700">管理员</span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-0.5 truncate">
                  {u.email} · 注册于 {formatDate(u.created_at)}
                </p>
              </div>
              <span className={`px-3 py-1 text-xs font-medium rounded-full flex-shrink-0 ${
                u.is_active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
              }`}>
                {u.is_active ? '已激活' : '未激活'}
              </span>
              <button
                onClick={() => handleToggle(u)}
                disabled={busyId === u.id}
                className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors disabled:opacity-50 flex-shrink-0 ${
                  u.is_active
                    ? 'text-slate-600 border border-slate-300 bg-white hover:bg-slate-100'
                    : 'text-white bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600'
                }`}
              >
                {busyId === u.id ? '处理中...' : u.is_active ? '停用' : '激活'}
              </button>
              {u.id !== meId && !u.is_superuser && (
                <button
                  onClick={() => handleDelete(u)}
                  disabled={busyId === u.id}
                  className="px-4 py-2 text-sm rounded-lg font-medium transition-colors flex-shrink-0 text-red-600 border border-red-200 bg-white hover:bg-red-50 disabled:opacity-50"
                >
                  删除
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
