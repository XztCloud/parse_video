"use client";

import { ScriptSegment } from "@/lib/api";

interface ScriptTimelineProps {
  segments: ScriptSegment[];
}

function formatTime(ms: number): string {
  
  const minutes  = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  const milliseconds = ms % 1000;
  return `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}:${milliseconds
    .toString()
    .padStart(3, "0")}`;
}

export default function ScriptTimeline({ segments }: ScriptTimelineProps) {
  if (segments.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无脚本片段</div>;
  }

  return (
    <div className="space-y-4">
      {segments.map((seg) => (
        <div key={seg.id} className="relative pl-8 pb-6 border-l-2 border-blue-200 last:border-l-0 last:pb-0">
          <div className="absolute left-[-9px] top-0 w-4 h-4 rounded-full bg-blue-500 border-2 border-white" />
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-500 font-mono">
                {formatTime(seg.start_time)} - {formatTime(seg.end_time)}
              </span>
              <span className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-600">
                {seg.segment_type === "shot"
                  ? "镜头"
                  : seg.segment_type === "dialogue"
                  ? "台词"
                  : "混合"}
              </span>
            </div>
            {seg.shot_description && (
              <p className="text-gray-700 mb-1">
                <span className="font-medium text-gray-900">镜头：</span>
                {seg.shot_description}
              </p>
            )}
            {seg.dialogue.map((item, index) => (
              <p key={index} className="text-gray-700 mb-1">
                <span className="font-medium text-gray-900">角色{item.speaker}: </span>
                {item.text}
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
