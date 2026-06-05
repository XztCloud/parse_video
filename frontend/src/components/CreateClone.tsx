import { cloneVideo } from "@/lib/api";
import { title } from "process";
import { useState } from "react";

interface CreateCloneProps {
    videoId: number;
    onComplete: (theme: string) => void;
}

export default function CreateClone({videoId, onComplete }: CreateCloneProps) {
    const [theme, setTheme] = useState("");
    const [isParsing, setIsParsing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    
    const postCloneMsg = async () => {
        if (!theme.trim()) {
            setError("请输入复刻主题");
            return;
        }
        setIsParsing(true);
        setError(null)
        try {
            console.log(`videoId: ${videoId}, theme: ${theme.trim()}`)
            const result = await cloneVideo(videoId, theme.trim());
            console.log("result is ", result)
            onComplete(theme.trim());
        } catch (err: any) {
            setError(err.response?.data?.detail || "解析失败，请重试");
        } finally {
            setIsParsing(false);
        }
    };

    return (
        <div className="w-full max-w-md mx-auto">
            <div className="flex flex-col">
                <div className='flex flex-row items-center gap-4 mb-6'>
                    <div className="basis-1/4 text-lg text-gray-700 font-medium">视频主题:</div>
                    <div className="basis-3/4 text-gray-500">
                        <input
                            type="text"
                            value={theme}
                            onChange={(e) => setTheme(e.target.value)}
                            placeholder="请输入视频主题"
                            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                        />
                    </div>
                </div>
                <div className="text-center">
                    <button
                        onClick={() => postCloneMsg()}
                        disabled={isParsing}
                        className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
                    >
                         {isParsing ? "复刻中..." : "复刻"}
                    </button>
                </div>
            </div>
            {error && <div className="mt-2 text-red-500 text-sm text-center">{error}</div>}
        </div>
    );
}