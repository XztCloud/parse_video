import { exportCloneScriptPlot, exportScript } from "./api";

/** 触发浏览器下载 */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** 导出复刻剧本（复制/小说）的剧本内容 markdown：复用 /clone/{id}/export/plot */
export async function exportClonePlotMarkdown(cloneScriptId: number, filename: string) {
  downloadBlob(await exportCloneScriptPlot(cloneScriptId), filename);
}

/** 导出解析剧本的剧本内容 markdown：后端 /scripts/{id}/export 返回的 script 字段即 markdown 文本 */
export async function exportParsedScriptMarkdown(videoId: number, filename: string) {
  const blob = await exportScript(videoId);
  let markdown: string;
  try {
    const data = JSON.parse(await blob.text());
    markdown = typeof data?.script === "string" ? data.script : JSON.stringify(data, null, 2);
  } catch {
    markdown = await blob.text();
  }
  downloadBlob(new Blob([markdown], { type: "text/markdown;charset=utf-8" }), filename);
}

/** 导出分镜脚本 JSON：直接用弹窗已加载的数据生成，无需新增后端接口 */
export function exportStoryboardJson(segments: unknown[], filename: string) {
  const payload = { count: segments.length, segments };
  downloadBlob(
    new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" }),
    filename,
  );
}
