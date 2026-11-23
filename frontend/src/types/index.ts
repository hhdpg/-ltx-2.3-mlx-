// 与后端 API 对齐的类型定义

export type TaskStatus =
  | "QUEUED"
  | "STARTING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELING"
  | "CANCELED";

export type TaskType = "T2V" | "I2V" | "EXTEND" | "RETAKE";

// ---- V1.1 连续续写 ----
export interface GenerationProject {
  id: string;
  name: string;
  current_segment_id: string | null;
  segment_count: number;
  append_project_prompt: boolean;
  created_at: string;
  updated_at: string;
  current_video_url: string | null;
  current_duration_seconds: number | null;
}

export interface GenerationProjectDetail extends GenerationProject {
  character_setting: string | null;
  scene_setting: string | null;
  style_setting: string | null;
  continuity_rules: string | null;
  story_summary: string | null;
}

export interface ProjectCreatePayload {
  name: string;
  character_setting?: string | null;
  scene_setting?: string | null;
  style_setting?: string | null;
  continuity_rules?: string | null;
  story_summary?: string | null;
  append_project_prompt?: boolean;
}

export interface GenerationSegment {
  id: string;
  project_id: string;
  task_id: string;
  parent_segment_id: string | null;
  segment_index: number;
  video_url: string;
  prompt: string;
  final_prompt: string | null;
  extend_frames: number | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  frame_rate: number | null;
  task_type: TaskType;
  created_at: string;
  is_current: boolean;
  child_count: number;
  video_ready: boolean;
}

export interface SegmentListResponse {
  project_id: string;
  current_segment_id: string | null;
  items: GenerationSegment[];
  children: Record<string, string[]>;
}

export interface ProjectListResponse {
  items: GenerationProject[];
  total: number;
}

export interface ExtendResponse {
  task_id: string;
  project_id: string;
  source_segment_id: string;
  status: TaskStatus;
  message: string;
  final_prompt: string | null;
  estimated_added_seconds: number | null;
  estimated_added_frames: number | null;
}

export interface ExtendFormPayload {
  source_segment_id: string;
  prompt: string;
  extend_frames: number;
  seed: number | null;
  append_project_prompt: boolean;
  anchor_frame: number | null;
  anchor_strength: number | null;
  anchor_image: File | null;
}


export interface TaskSummary {
  id: string;
  task_type: TaskType;
  prompt: string;
  prompt_excerpt: string;
  width: number;
  height: number;
  frames: number;
  frame_rate: number;
  duration_seconds_est: number | null;
  status: TaskStatus;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  run_seconds: number | null;
  output_ready: boolean;
  has_image: boolean;
}

export interface TaskDetail extends TaskSummary {
  image_path: string | null;
  image_url: string | null;
  model_path: string;
  mode: string;
  seed: number | null;
  output_path: string | null;
  video_url: string | null;
  download_url: string | null;
  log_path: string | null;
  exit_code: number | null;
  pid: number | null;
  command_preview: string | null;
}

export interface TaskListResponse {
  items: TaskSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaskLogsResponse {
  task_id: string;
  lines: string[];
  total_lines: number;
  status: TaskStatus;
}

export interface CreateTaskResponse {
  task_id: string;
  status: TaskStatus;
  message: string;
}

export interface CancelResponse {
  task_id: string;
  status: TaskStatus;
  message: string;
}

export interface DeleteResponse {
  task_id: string;
  deleted_output: boolean;
  message: string;
}

export interface UploadResponse {
  upload_id: string;
  filename: string;
  size: number;
  width: number | null;
  height: number | null;
  content_type: string;
  preview_url: string;
}

export interface CheckItem {
  key: string;
  label: string;
  status: "ok" | "warn" | "error";
  message: string;
  detail: string | null;
}

export interface HealthResponse {
  status: string;
  app: string;
  python: string;
  architecture: string;
  mlx_available: boolean;
  mlx_device: string | null;
  mlx_error: string | null;
  cli_available: boolean;
  cli_error: string | null;
  model_configured: boolean;
  model_path: string | null;
  model_error: string | null;
  ffmpeg_available: boolean;
  ffmpeg_error: string | null;
  queue_running: boolean;
  queue_size: number;
  max_queue_size: number;
  offline_mode: boolean;
  ready: boolean;
  blocking_reasons: string[];
}

export interface SystemInfoResponse {
  app: string;
  app_env: string;
  python_version: string;
  platform: string;
  architecture: string;
  cpu_count: number | null;
  total_memory_gb: number | null;
  available_memory_gb: number | null;
  disk_total_gb: number | null;
  disk_free_gb: number | null;
  model_id: string;
  model_path: string | null;
  output_dir: string;
  upload_dir: string;
  log_dir: string;
  cli_path: string | null;
  cli_version: string | null;
  checks: CheckItem[];
  ready: boolean;
  blocking_reasons: string[];
}

export interface SettingsResponse {
  default_width: number;
  default_height: number;
  default_frames: number;
  default_frame_rate: number;
  low_ram: boolean;
  model_id: string;
  model_path: string | null;
  output_dir: string;
  upload_dir: string;
  allowed_frames: number[];
  allowed_frame_rates: number[];
  allowed_resolutions: number[][];
  allowed_extend_frames: number[];
  default_extend_frames: number;
  max_prompt_length: number;
  max_upload_mb: number;
  max_queue_size: number;
  offline_mode: boolean;
}

export interface SettingsUpdate {
  default_width?: number;
  default_height?: number;
  default_frames?: number;
  default_frame_rate?: number;
  low_ram?: boolean;
  model_path?: string;
}

export interface GenerationForm {
  task_type: TaskType;
  prompt: string;
  width: number;
  height: number;
  frames: number;
  frame_rate: number;
  mode: string;
  seed: number | null;
}
