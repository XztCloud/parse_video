"use client";

import { CloneImage, getImageUrl } from "@/lib/api";
import { useState } from "react";



interface ScriptImageProps {
  images: CloneImage[];
}

export default function ImageList({ images }: ScriptImageProps) {

  const [isOpen, setIsOpen] = useState<boolean>(false);

  if (images.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无音图片</div>;
  }

  return (
    <div className="space-y-4">
      {images.map((image) => {
          return (
            <div
            key={image.id}
            className="bg-white rounded-xl shadow border p-5">
              <div className="flex justify-between items-center">
                <div>
                  <span className="text-lg font-bold text-gray-800">
                    {image.role_name}
                  </span>

                  <span className="ml-4 px-2 py-1 rounded bg-blue-50 text-blue-600 text-sm">
                    {image.width}x{image.height}
                  </span>
                </div>
                <div className="text-gray-500 text-sm">{image.desc}s</div>
              </div>

              {/* 缩略图容器 */}
              <div className="flex justify-between items-center">
                <div className="basis-1/2 items-center">
                 
                    <p className="text-gray-700 mb-1">
                      {image.prompt}
                    </p>
                  
                </div>
                <div 
                  className="flex items-center basis-1/2  justify-start overflow-hidden cursor-pointer "
                  style={{ width: 500, height: 300 }} // 容器固定为 max_len 的正方形
                  onClick={() => setIsOpen(true)}
                >
                  <img
                    src={getImageUrl(image.id)}
                    alt={`图片`}
                    // max-w-full 和 max-h-full 确保图片不超出容器
                    // object-contain 保持宽高比
                    className="max-w-full max-h-full object-contain transition-transform duration-200 hover:scale-105"
                  />
                </div>
              </div>

              {/* 点击弹出的原图模态框 (Modal) */}
              {isOpen && (
                <div 
                  className="fixed inset-0 z-50 overflow-auto bg-black/80 cursor-zoom-out p-4 md:p-0 flex justify-center items-start"
                  onClick={() => setIsOpen(false)}
                >
                  <div className="relative max-w-[90vw] max-h-[90vh]">
                    <img
                      src={getImageUrl(image.id)}
                      alt={` 原图`}
                      className="w-full h-full object-scale-down rounded-sm"
                    />
                    {/* 右上角关闭按钮
                    <button 
                      className="absolute -top-10 right-0 text-white text-sm bg-black/40 px-3 py-1 rounded-full hover:bg-black/60 transition-colors"
                      onClick={() => setIsOpen(false)}
                    >
                      关闭
                    </button> */}
                  </div>
                </div>
              )}
              {/* <img src={getImageUrl(image.id)} /> */}

            </div>
          )
      })
      }
    </div>
  )
}
