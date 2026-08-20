import axios from "axios";

const API_PREFIX = "/api/v1";
export const api = axios.create({
  baseURL: "",
  timeout: 30000,
  // ⚡ 关键核心：允许跨域请求携带和接收 Cookie 凭证
  withCredentials: true,
});

// 自动注入 Authorization Header (支持你后端的 OAuth2PasswordBearer)
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
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
  duration?: number | null;
  category?: string | null;
}

export interface VideoListItem {
  id: number;
  filename: string;
  status: string;
  progress: number;
  error_message?: string;
  duration?: number | null;
  category?: string | null;
  type_summary?: string | null;
  created_at?: string | null;
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
  shot_features?: string[];
  segment_type: string;
}

export interface CloneVoice {
  id: number;
  role_name: string;
  duration: number;
  voice_type: string;
  spk_id: string;
  text: string;
}

export interface CloneImage {
  id: number;
  name: string;
  width: number;
  height: number;
  desc: string | null;
  prompt: string;
  seed: string | null;
  category: string;
  status: string;
  version: number;
}

export interface ScriptResponse {
  id: number;
  video_id: number;
  content: any;
  parse_pointer?: {
    role_library?: { role_name: string; gender: string; age: number; voice_style_guide?: string; effect: string }[];
    scene_library?: { scene_name: string; environment_description: string; color_grading: string }[];
    global_style?: { global_style_suffix: string };
    core_shell_point?: { user_pain_point: string; product_usp: string[]; hook_trigger: string; keywords_to_include: string[] } | null;
  };
  parse_script?: any;
  segments: ScriptSegment[];
}

export interface CloneListItem {
  id: number;
  clone_theme: string;
  clone_status: string;
  clone_progress: number;
  error_message?: string;
}

export interface CloneAllItem {
  id: number;
  script_id: number;
  video_id: number;
  video_title: string;
  video_category: string | null;
  clone_theme: string;
  clone_status: string;
  clone_progress: number;
  error_message?: string;
  source_type: string;
  created_at: string | null;
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

export interface RenderFromScriptResponse {
  id: number;
  theme: string;
  source_type: string;
  status: string;
  progress: number;
}

export interface CloneSegmentsResponse {
  id: number;
  status: string;
  progress: number;
}


export interface CloneSegmentVideo {
  id: number;
  name: string;
  width: number;
  height: number;
  desc: string | null;
  prompt: string;
  seed: string | null;
  category: string;
  status: string;
  version: number;
}

export interface CloneVido {
  "id": number;
  "category": string;
  "duration": number;
}

export interface ClonseScriptResponse {
  id: number;
  source_type: string;
  content: string;
  clone_parse_pointer?: any;
  clone_parse_script?: any;
  created_at?: string;
  voices: CloneVoice[];
  segments: ScriptSegment[];
  images: CloneImage[];
  frames: CloneImage[];
  segment_videos: CloneSegmentVideo[];
  video: CloneVido|null;
}

export interface Toekn {
  access_token: string;
  token_type: string;
}

export interface RegenerateRequest {
  prompt: string;
  width: number|null;
  height: number|null;
  seed: string|null;
}

export interface RegenerateResponse {
  status: string;
  id: number;
  width: number;
  height: number;
  prompt: string;
  seed: string;
  version: number;
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
  FRAME = "FRAME",
  FRAME_DONE = "FRAME_DONE",
  SEGMENT_VIDEO = "SEGMENT_VIDEO",
  SEGMENT_VIDEO_DONE = "SEGMENT_VIDEO_DONE",
  MERGE_VIDEO = "MERGE_VIDEO",
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

export const listAllCloneScripts = async (offset: number = 0, limit: number = 50): Promise<CloneAllItem[]> => {
  const response = await api.get<CloneAllItem[]>(`${API_PREFIX}/clone/list_all`, { params: { offset, limit } });
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

export const reClonePlot = async (cloneScriptId: number, autoRun: boolean=false): Promise<ClonePlotResponse> => {
  const response = await api.post<ClonePlotResponse>(`${API_PREFIX}/clone/re_plot`, {cloneScriptId, autoRun});
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

/**
 * 推进复刻到指定阶段。
 * 后端已合并原 /clone/voices、/segments、/images、/frames、/segment_videos、/video 六个接口为 /clone/phase。
 * step: 2=分镜 3=配音 4=生图 5=参考帧 6=分镜视频 7=合并成片
 */
export const clonePhase = async (cloneScriptId: number, step: number, autoRun: boolean = false): Promise<CloneSegmentsResponse> => {
  const response = await api.post<CloneSegmentsResponse>(`${API_PREFIX}/clone/phase`, {cloneScriptId, autoRun, step});
  return response.data;
}

export const cloneSegments = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  return clonePhase(cloneScriptId, 2, autoRun);
}

export const cloneVoices = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  return clonePhase(cloneScriptId, 3, autoRun);
}

export const cloneImages = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  return clonePhase(cloneScriptId, 4, autoRun);
}

export const cloneFrames = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  return clonePhase(cloneScriptId, 5, autoRun);
}

export const cloneSegmentVideo = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  return clonePhase(cloneScriptId, 6, autoRun);
}

export const cloneMergeVideo = async (cloneScriptId: number, autoRun: boolean=false): Promise <CloneSegmentsResponse> => {
  return clonePhase(cloneScriptId, 7, autoRun);
}

/** 输出视频模块：以原片解析出的剧本+分镜为输入，一键创建 ORIGINAL 渲染工作台并自动跑全流程 */
export const renderFromScript = async (videoId: number): Promise<RenderFromScriptResponse> => {
  const response = await api.post<RenderFromScriptResponse>(`${API_PREFIX}/render/from-script`, { videoId });
  return response.data;
};

export const exportCloneVoice = async (cloneVoiceId: number): Promise<Blob> => {
  const response = await api.get(`${API_PREFIX}/clone/voice/${cloneVoiceId}`, { responseType: "blob" });
  return response.data;
}

export function getImageUrl(category:string, id: number): string {
  const base = api.defaults.baseURL ?? "";
  return `${base}${API_PREFIX}/clone/image/${category}/${id}`;
}

export function getVideoUrl(category:string, id: number): string {
  const base = api.defaults.baseURL ?? "";
  return `${base}${API_PREFIX}/clone/video/${category}/${id}`;
}

export const login = async (params: URLSearchParams): Promise<void> => {
  const response = await api.post(`${API_PREFIX}/login/access-token`, params);
  localStorage.setItem('token', response.data.access_token);
  localStorage.setItem('username', params.get('username') || '未知');
}

export const logout = async (): Promise<void> => {
  await api.post(`${API_PREFIX}/login/logout`);
  localStorage.removeItem('token');
  localStorage.removeItem('username')
}

export const regenerate = async (category: string, id: number, payload:RegenerateRequest): Promise<void> => {
  await api.patch(`${API_PREFIX}/clone/${category}/${id}/regenerate`, payload);
}

export const getRegenerateStatus = async (category: string, id: number) : Promise<RegenerateResponse> => {
  const response = await api.get(`${API_PREFIX}/clone/${category}/${id}/regenerate`)
  return response.data
}

