"use client";

import { useState } from "react";
import { parseDouyin } from "@/lib/api";

interface DouyinInputProps {
  onParseSuccess: (videoId: number) => void;
}

export default function DouyinInput({ onParseSuccess }: DouyinInputProps) {
  const [url, setUrl] = useState("");
  const [isParsing, setIsParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleParse = async () => {
    const raw = url.trim();
    if (!raw) {
      setError("请输入抖音分享链接");
      return;
    }
    // 抖音分享文案通常是"描述文字 + URL"，自动提取其中的 http(s) 链接
    const urlMatch = raw.match(/https?:\/\/[^\s，,。]+/);
    const parsedUrl = urlMatch ? urlMatch[0] : raw;
    setIsParsing(true);
    setError(null);
    try {
      const result = await parseDouyin(parsedUrl);
      onParseSuccess(result.id);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      let message = "解析失败，请重试";
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        // FastAPI 422 校验错误的 detail 是数组
        message = detail.map((d: any) => d.msg).filter(Boolean).join("；");
      }
      setError(message);
    } finally {
      setIsParsing(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="flex gap-2">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="请输入抖音分享链接"
          className="flex-1 px-4 py-2 border border-gray-300 text-gray-800 rounded-lg focus:outline-none focus:border-blue-500"
          onKeyDown={(e) => e.key === "Enter" && handleParse()}
        />
        <button
          onClick={handleParse}
          disabled={isParsing}
          className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50"
        >
          {isParsing ? "解析中..." : "解析"}
        </button>
      </div>
      {error && <div className="mt-2 text-red-500 text-sm text-center">{error}</div>}
    </div>
  );
}
