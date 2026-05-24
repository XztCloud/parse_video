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
    if (!url.trim()) {
      setError("请输入抖音分享链接");
      return;
    }
    setIsParsing(true);
    setError(null);
    try {
      const result = await parseDouyin(url.trim());
      onParseSuccess(result.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || "解析失败，请重试");
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
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
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
