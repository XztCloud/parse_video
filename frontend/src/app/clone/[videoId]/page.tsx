"use client";

import CreateClone from "@/components/CreateClone";
import ScriptTimeline from "@/components/ScriptTimeline";
import { getScript, getVideoStatus, ScriptResponse, VideoStatusResponse } from "@/lib/api";
import { useRouter, useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { finished } from "stream";


export default function ClonePage() {
    const router = useRouter();
    const params = useParams();

    const videoId = Number(params.videoId);
    const [status, setStatus] = useState<VideoStatusResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [isGenerating, setIsGenerating] = useState(false)

    const fetchStatus = useCallback(async () => {
        try {
            console.log('进入复刻页面，开始获取视频状态 ', videoId);
            const data = await getVideoStatus(videoId);
            console.log('视频状态数据：', data);
            setStatus(data);
            if (data.status !== "done") {
                setError("视频解析未完成，无法进行复刻");
                return;
            }
            if (data.clone_status === "done") {
                // // 延迟跳转，让用户看到100%
                // setTimeout(() => router.push(`/script/${videoId}`), 1500);
                // return;
                console.log('复刻已完成');
                return;
            }
            else if (data.clone_status === "pending") {
                console.log('复刻未开始，需要填写信息');
                return;
            }
            else if (data.clone_status === "clone_failed") {
                setError(data.error_message || "处理失败");
                return;
            }
            else if (data.clone_status === "cloning") {
                console.log('复刻进行中，当前进度：', data.clone_progress);
                setTimeout(() => router.push(`/cloneProgress/${videoId}`), 1500);
                return;
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || "获取状态失败");
        }
    }, [videoId, router]);

    const onComplete = useCallback(async (theme: string) => {
        try {
            console.log('创建克隆完成，开始获取视频ID ', videoId);
            console.log('视频主题', theme);
            router.push(`/cloneProgress/${videoId}`);
        } catch (err: any) {
            setError(err.response?.data?.detail || "获取状态失败");
        }
    }, [videoId, router]);

    useEffect(() => {
        const fetchScript = async () => {
            console.log('进入复刻页面，开始获取视频状态');
            try {
                const data = await getVideoStatus(videoId);
                console.log('视频状态数据：', data);
                setStatus(data);
            } catch (err: any) {
                setError(err.response?.data?.detail || "获取状态失败");
            } finally {
                setLoading(false);
            }
        };
        fetchScript();
    }, [videoId]);


    if (error) {
        return (
        <main className="min-h-screen bg-gray-50 flex items-center justify-center">
            <div className="bg-white rounded-xl shadow-sm border p-8 max-w-md text-center">
            <div className="text-red-500 text-lg font-medium mb-2">复刻失败</div>
            <div className="text-gray-600 mb-6">{error}</div>
            <button
                onClick={() => router.push("/")}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
            >
                返回首页
            </button>
            </div>
        </main>
        );
    }

    if (loading) {
        return (
        <main className="min-h-screen bg-gray-50 flex items-center justify-center">
            <div className="text-gray-500">加载脚本中...</div>
        </main>
        );
    }

    return (
        <main className="min-h-screen bg-gray-50">
            <header className="bg-white shadow-sm">
                <div className="max-w-5xl mx-auto px-6 py-4">
                <button onClick={() => router.push("/")} className="text-blue-500 hover:text-blue-600 text-sm">
                    ← 返回首页
                </button>
                <h1 className="text-2xl font-bold text-gray-900 mt-2"> {status?.clone_status === 'clone_done' ? '脚本详情' : '创建副本'} </h1>
                </div>
            </header>
            <div className="max-w-5xl mx-auto px-6 py-8">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div className="lg:col-span-3">
                        <div className="bg-white rounded-xl shadow-sm border p-6">
                            {   
                                status?.clone_status === 'pending' || status?.clone_status === 'clone_failed' ? (
                                    <CreateClone videoId={videoId} onComplete={onComplete} />
                                ) : (
                                    <div className="w-full max-w-md mx-auto">
                                        <div className="flex flex-col">
                                            <div className="text-center font-medium text-slate-700">
                                                <span>我是进度条组件</span>
                                            </div>
                                        </div>
                                    </div>
                                )
                            }
                        </div>
                    </div>
                    <div className="lg:col-span-3">
                        <div className="bg-white rounded-xl shadow-sm border p-6">
                            <table className="w-full">
                                <thead>
                                    <tr className="border-b text-left text-sm text-gray-500">
                                        <th className="pb-3 font-medium">主题</th>
                                        <th className="pb-3 font-medium w-48">状态</th>
                                        <th className="pb-3 font-medium w-48">操作</th>
                                    </tr>
                                </thead>
                                <tbody>

                                </tbody>
                                
                            </table>
                        </div>
                    </div>
                </div>

            </div>
        </main>
    );
}