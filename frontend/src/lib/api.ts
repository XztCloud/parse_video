import axios from "axios";

const API_PREFIX = "/api/v1";
const api = axios.create({
  baseURL: "",
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

export interface CloneVoice {
  id: number;
  role_name: string;
  voice_type: string;
  text: string;
}

export interface ScriptResponse {
  id: number;
  video_id: number;
  content: any;
  segments: ScriptSegment[];
}

export interface CloneListItem {
  id: number;
  clone_theme: string;
  clone_status: string;
  clone_progress: number;
  error_message?: string;
}

export interface ClonePlotRequest {
  videoId: number;
  cloneTheme: string;
  autoRun: boolean;
  style: string | null;
  product: string | null;
  productDesc: string | null;
}

export interface CloneStatusResponse {
  id: number;
  clone_status: string;
  clone_progress: number;
  error_message?: string;
}

export interface ClonePlotResponse {
  id: number;
  theme: string;
  status: string;
  progress: number;
}

export interface CloneSegmentsResponse {
  id: number;
  status: string;
  progress: number;
}

export interface CloneVideo {
  id: number;
}

export interface ClonseScriptResponse {
  id: number;
  content: string;
  voices: CloneVoice[]
  segments: ScriptSegment[];
  videos: CloneVideo[];
}

export const getDefaultCloneRequest = (videoId: number): ClonePlotRequest => ({
  videoId,
  cloneTheme: 'standard',
  autoRun: false,
  style: null,
  product: null,
  productDesc: null,
});

export enum CloneStatus {
  PENDING = "PENDING",
  PLOT = "PLOT",
  PLOT_DONE = "PLOT_DONE",
  VOICE = "VOICE",
  VOICE_DONE = "VOICE_DONE",
  SEGMENTS = "SEGMENTS",
  SEGMENTS_DONE = "SEGMENTS_DONE",
  IMAGE = "IMAGE",
  IMAGE_DONE = "IMAGE_DONE",
  VIDEO = "VIDEO",
  DONE = "DONE",
  FAILED = "FAILED",
}

export const uploadVideo = async (file: File): Promise<VideoUploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post<VideoUploadResponse>(`${API_PREFIX}/videos/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const parseDouyin = async (url: string): Promise<VideoUploadResponse> => {
  const response = await api.post<VideoUploadResponse>(`${API_PREFIX}/videos/douyin`, { url });
  return response.data;
};

export const getVideoStatus = async (videoId: number): Promise<VideoStatusResponse> => {
  const response = await api.get<VideoStatusResponse>(`${API_PREFIX}/videos/${videoId}/status`);
  return response.data;
};

export const listVideos = async (skip: number = 0, limit: number = 20): Promise<VideoListItem[]> => {
  const response = await api.get<VideoListItem[]>(`${API_PREFIX}/videos/`, { params: { skip, limit } });
  return response.data;
};

export const getScript = async (videoId: number): Promise<ScriptResponse> => {
  const response = await api.get<ScriptResponse>(`${API_PREFIX}/scripts/${videoId}`);
  return response.data;
};

export const listCloneScripts = async (scriptId: number): Promise<CloneListItem[]> => {
  const response = await api.get<CloneListItem[]>(`${API_PREFIX}/clone/${scriptId}/list_clone_scripts`);
  return response.data;
};

export const exportScript = async (videoId: number): Promise<Blob> => {
  const response = await api.get(`${API_PREFIX}/scripts/${videoId}/export`, { responseType: "blob" });
  return response.data;
};

export const clonePlot = async (cloneRequest: ClonePlotRequest): Promise<ClonePlotResponse> => {
  const response = await api.post<ClonePlotResponse>(`${API_PREFIX}/clone/plot`, cloneRequest);
  return response.data;
};

export const getCloneStatus = async (cloneScriptId: number): Promise<CloneStatusResponse> => {
  const response = await api.get<CloneStatusResponse>(`${API_PREFIX}/clone/${cloneScriptId}/status`);
  return response.data;
};

export const getCloneScript = async (cloneScriptId: number): Promise<ClonseScriptResponse> => {
  const response = await api.get<ClonseScriptResponse>(`${API_PREFIX}/clone/${cloneScriptId}`);
  return response.data;
};

export const exportClonePlot = async (videoId: number): Promise<Blob> => {
  const response = await api.get(`${API_PREFIX}/clone/${videoId}/export/plot`, { responseType: "blob" });
  return response.data;
};

export const cloneVoices = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  const response = await api.post<CloneSegmentsResponse>(`${API_PREFIX}/clone/voices`, {cloneScriptId, autoRun});
  return response.data;
}

export const cloneSegments = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  const response = await api.post<CloneSegmentsResponse>(`${API_PREFIX}/clone/segments`, {cloneScriptId, autoRun});
  return response.data;
}

export const cloneImages = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  const response = await api.post<CloneSegmentsResponse>(`${API_PREFIX}/clone/images`, {cloneScriptId, autoRun});
  return response.data;
}

export const exportCloneVoice = async (cloneVoiceId: number): Promise<Blob> => {
  const response = await api.get(`${API_PREFIX}/clone/voice/${cloneVoiceId}`, { responseType: "blob" });
  return response.data;
}