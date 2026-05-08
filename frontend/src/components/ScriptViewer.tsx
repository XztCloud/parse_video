"use client";

import { useEffect, useState } from "react";
import { getScript, exportScript, ScriptResponse } from "@/lib/api";

interface ScriptViewerProps {
  videoId: number;
}

export default function ScriptViewer({ videoId }: ScriptViewerProps) {
  const [script, setScript] = useState<ScriptResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchScript = async () => {
      try {
        const data = await getScript(videoId);
        setScript(data);
      } catch (err: any) {
        setError(err.response?.data?.detail || "获取脚本失败");
      } finally {
        setLoading(false);
      }
    };
    fetchScript();
  }, [videoId]);

  const handleExport = async () => {
    try {
      const blob = await exportScript(videoId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `script_${videoId}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setError(err.response?.data?.detail || "导出失败");
    }
  };

  if (loading) {
    return <div className="text-gray-500 text-center">加载脚本中...</div>;
  }

  if (error) {
    return <div className="text-red-500 text-center">{error}</div>;
  }

  if (!script) {
    return <div className="text-gray-500 text-center">未找到脚本</div>;
  }

  return (
    <div className="w-full max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">视频脚本</h2>
        <button
          onClick={handleExport}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
        >
          导出脚本
        </button>
      </div>
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-2">脚本内容</h3>
          <pre className="bg-gray-100 p-4 rounded overflow-auto max-h-96">
            {JSON.stringify(script.content, null, 2)}
          </pre>
        </div>
        <div>
          <h3 className="text-lg font-semibold mb-2">脚本片段</h3>
          <div className="space-y-4">
            {script.segments.map((segment) => (
              <div key={segment.id} className="border rounded-lg p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="text-sm text-gray-500">
                    {segment.start_time.toFixed(2)}s - {segment.end_time.toFixed(2)}s
                  </div>
                  <span className="px-2 py-1 bg-gray-200 rounded text-xs">
                    {segment.segment_type}
                  </span>
                </div>
                {segment.shot_description && (
                  <div className="mb-2">
                    <div className="text-sm font-medium text-gray-700">镜头描述:</div>
                    <div className="text-gray-600">{segment.shot_description}</div>
                  </div>
                )}
                {segment.dialogue && (
                  <div>
                    <div className="text-sm font-medium text-gray-700">对话:</div>
                    <div className="text-gray-600">{segment.dialogue}</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}