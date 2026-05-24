import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  timeout: 30000,
});

export interface VideoUploadResponse {
  id: number;
  filename: string;
  status: string;
  progress: number;
}

export interface VideoStatusResponse {
  id: number;
  filename: string;
  status: string;
  progress: number;
  error_message?: string;
}

export interface VideoListItem {
  id: number;
  filename: string;
  status: string;
  progress: number;
  error_message?: string;
}

export interface DialogueItem {
  speaker: string;
  text: string;
}

export interface ScriptSegment {
  id: number;
  start_time: number;
  end_time: number;
  shot_description: string;
  dialogue: DialogueItem[];
  segment_type: string;
}

export interface ScriptResponse {
  id: number;
  video_id: number;
  content: any;
  segments: ScriptSegment[];
}

export const uploadVideo = async (file: File): Promise<VideoUploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post<VideoUploadResponse>("/videos/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const parseDouyin = async (url: string): Promise<VideoUploadResponse> => {
  const response = await api.post<VideoUploadResponse>("/videos/douyin", { url });
  return response.data;
};

export const getVideoStatus = async (videoId: number): Promise<VideoStatusResponse> => {
  const response = await api.get<VideoStatusResponse>(`/videos/${videoId}/status`);
  return response.data;
};

export const listVideos = async (skip: number = 0, limit: number = 20): Promise<VideoListItem[]> => {
  const response = await api.get<VideoListItem[]>("/videos/", { params: { skip, limit } });
  return response.data;
};

export const getScript = async (videoId: number): Promise<ScriptResponse> => {
  const response = await api.get<ScriptResponse>(`/scripts/${videoId}`);
  return response.data;
};

export const exportScript = async (videoId: number): Promise<Blob> => {
  const response = await api.get(`/scripts/${videoId}/export`, { responseType: "blob" });
  return response.data;
};