"use client";

import {
  CloneImage,
  getImageUrl,
  getRegenerateStatus,
  regenerate,
  RegenerateResponse,
} from "@/lib/api";
import { useEffect, useState } from "react";

interface ScriptImageProps {
  images: CloneImage[];
}

export default function ImageList({ images }: ScriptImageProps) {
  const [openImageId, setOpenImageId] = useState<number | null>(null);
  const [openImageSrc, setOpenImageSrc] = useState<string | null>(null);

  // key = category + id
  const [regenStatus, setRegenStatus] = useState<Record<string, string>>({});

  // 保存最新图片参数
  const [imageParams, setImageParams] = useState<
    Record<string, Partial<CloneImage>>
  >({});

  // 当前处于编辑态（展示 textarea + 取消/同步）的图片 key
  const [editingKey, setEditingKey] = useState<string | null>(null);
  // 编辑中的提示词草稿
  const [editingPrompt, setEditingPrompt] = useState<string>("");

  const saveOpenImage = (src: string | null, id: number | null) => {
    setOpenImageId(id);
    setOpenImageSrc(src);
  };

  /**
   * 轮询生成状态
   */
  const getRegenImageStatus = async (category: string, id: number) => {
    const key = category + id;

    const response: RegenerateResponse = await getRegenerateStatus(
      category,
      id,
    );

    setRegenStatus((prev) => ({
      ...prev,
      [key]: response.status,
    }));

    // 更新图片参数
    if (response.status === "SUCCESS") {
      setImageParams((prev) => ({
        ...prev,
        [key]: {
          width: response.width,
          height: response.height,
          prompt: response.prompt,
          seed: response.seed,
          version: response.version,
        },
      }));

      // 同步成功后退出编辑态
      setEditingKey((prev) => (prev === key ? null : prev));

      return;
    }

    // PROCESSING / PENDING继续轮询
    if (response.status === "PROCESSING" || response.status === "PENDING") {
      setTimeout(() => {
        getRegenImageStatus(category, id);
      }, 3000);

      return;
    }

    // FAILED结束
    if (response.status === "FAILED") {
      // 失败也退出编辑态，让用户能看到状态
      setEditingKey((prev) => (prev === key ? null : prev));
      return;
    }
  };

  const regenerateImage = async (
    category: string,
    id: number,
    width: number,
    height: number,
    prompt: string,
    seed: string | null,
  ) => {
    const key = category + id;

    // 点击后立即禁用
    setRegenStatus((prev) => ({
      ...prev,
      [key]: "PROCESSING",
    }));

    await regenerate(category, id, {
      prompt,
      width,
      height,
      seed,
    });

    // 开始轮询
    getRegenImageStatus(category, id);
  };

  /**
   * 点击"编辑"：进入编辑态，回填当前提示词
   */
  const startEdit = (key: string, currentPrompt: string) => {
    setEditingKey(key);
    setEditingPrompt(currentPrompt);
  };

  /**
   * 点击"取消"：退出编辑态，不修改
   */
  const cancelEdit = () => {
    setEditingKey(null);
    setEditingPrompt("");
  };

  /**
   * 点击"同步"：提交修改后的提示词并重新生成
   */
  const syncEdit = async (
    category: string,
    id: number,
    image: CloneImage,
  ) => {
    const key = category + id;
    if (!editingPrompt.trim()) {
      return;
    }
    // 退出编辑态，进入生成中
    setEditingKey(null);
    setEditingPrompt("");
    await regenerateImage(
      category,
      id,
      imageParams[key]?.width ?? image.width,
      imageParams[key]?.height ?? image.height,
      editingPrompt.trim(),
      imageParams[key]?.seed ?? image.seed,
    );
  };

  useEffect(() => {
    if (!images || images.length === 0) return;
    const statusMap: Record<string, string> = {};

    images.forEach((image) => {
      const key = image.category + image.id;
      statusMap[key] = image.status;
    });
    setRegenStatus(statusMap);

  }, [images]);

  if (!images || images.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无图片</div>;
  }

  return (
    <div className="space-y-4">
      {images.map((image) => {
        const key = image.category + image.id;

        const status = regenStatus[key];

        const params = imageParams[key] ?? {};
        const currentPrompt = params.prompt ?? image.prompt;

        const isEditing = editingKey === key;
        const isProcessing = status === "PROCESSING" || status === "PENDING";

        return (
          <div key={key} className="bg-white rounded-xl shadow border p-5">
            <div className="flex justify-between items-center">
              <div>
                <span className="text-lg font-bold text-gray-800">
                  {image.name}
                </span>

                <span className="ml-4 px-2 py-1 rounded bg-blue-50 text-blue-600 text-sm">
                  {params.width ?? image.width}x{params.height ?? image.height}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <div className="text-gray-500 text-sm mr-2">{image.desc}</div>

                {!isEditing && (
                  <button
                    disabled={isProcessing}
                    className="
                    px-4 py-1.5 rounded-xl
                    bg-blue-500
                    text-white
                    hover:bg-blue-600
                    transition
                    disabled:bg-gray-400
                    "
                    onClick={() => startEdit(key, currentPrompt)}
                  >
                    编辑
                  </button>
                )}

                {!isEditing && (
                  <button
                    disabled={isProcessing}
                    className="
                    px-4 py-1.5 rounded-xl
                    bg-green-500
                    text-white
                    hover:bg-green-600
                    transition
                    disabled:bg-gray-400
                    "
                    onClick={() =>
                      regenerateImage(
                        image.category,
                        image.id,
                        params.width ?? image.width,
                        params.height ?? image.height,
                        currentPrompt,
                        params.seed ?? image.seed,
                      )
                    }
                  >
                    {isProcessing ? "生成中..." : "重新生成"}
                  </button>
                )}

                {isEditing && (
                  <>
                    <button
                      className="
                      px-4 py-1.5 rounded-xl
                      bg-gray-400
                      text-white
                      hover:bg-gray-500
                      transition
                      "
                      onClick={cancelEdit}
                    >
                      取消
                    </button>
                    <button
                      className="
                      px-4 py-1.5 rounded-xl
                      bg-blue-500
                      text-white
                      hover:bg-blue-600
                      transition
                      "
                      onClick={() =>
                        syncEdit(image.category, image.id, image)
                      }
                    >
                      同步
                    </button>
                  </>
                )}
              </div>
            </div>

            <div className="flex justify-between items-center">
              <div className="basis-1/2">
                {isEditing ? (
                  <textarea
                    value={editingPrompt}
                    onChange={(e) => setEditingPrompt(e.target.value)}
                    rows={8}
                    className="
                    w-full
                    px-3
                    py-2
                    border
                    border-gray-300
                    rounded-lg
                    focus:outline-none
                    focus:border-blue-500
                    text-gray-800
                    text-sm
                    "
                  />
                ) : (
                  <p className="text-gray-700 mb-1">{currentPrompt}</p>
                )}
              </div>

              <div
                className="
                flex items-center
                basis-1/2
                justify-start
                overflow-hidden
                cursor-pointer
                "
                style={{
                  width: 500,
                  height: 300,
                }}
                onClick={() => saveOpenImage(image.category, image.id)}
              >
                <img
                  src={`${getImageUrl(image.category, image.id)}?v=${params.version ?? image.version}`}
                  className="
                  max-w-full
                  max-h-full
                  object-contain
                  "
                />
              </div>
            </div>
            {openImageId === image.id && openImageSrc === image.category && (
              <div
                className="fixed inset-0 z-50 overflow-auto bg-black/80 cursor-zoom-out p-4 md:p-0 flex justify-center items-start"
                onClick={() => saveOpenImage(null, null)}
              >
                <div className="relative max-w-[90vw] max-h-[90vh]">
                  <img
                    src={`${getImageUrl(image.category, image.id)}?v=${params.version ?? image.version}`}
                    alt={` 原图`}
                    className="w-full h-full object-scale-down rounded-sm"
                  />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
