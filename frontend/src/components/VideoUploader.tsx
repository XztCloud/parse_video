"use client";

import { useState, useRef } from "react";
import { uploadVideo } from "@/lib/api";

interface VideoUploaderProps {
  onUploadSuccess: (videoId: number) => void;
}

export default function VideoUploader({ onUploadSuccess }: VideoUploaderProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();

    setIsDragging(false);

    const file = e.dataTransfer.files?.[0];

    if (file) {
      handleUpload(file);
    }
  };

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      const result = await uploadVideo(file);
      onUploadSuccess(result.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || "上传失败，请重试");
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleUpload(file);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
          ${
            isDragging
              ? "border-blue-500 bg-blue-50"
              : "border-gray-300 hover:border-blue-500"
          }
        `}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".mp4,.mov,.avi,.mkv"
          className="hidden"
        />
        {isUploading ? (
          <div className="text-blue-500">上传中...</div>
        ) : (
          <div>
            <div className="text-gray-500 mb-2">点击或拖拽视频文件到此处</div>
            <div className="text-sm text-gray-400">
              支持 MP4, MOV, AVI, MKV 格式
            </div>
          </div>
        )}
      </div>
      {error && <div className="mt-4 text-red-500 text-center">{error}</div>}
    </div>
  );
}
