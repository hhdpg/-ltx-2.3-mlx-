import { http } from "./http";

export interface RetakeSourceInfo {
  kind: "task" | "segment";
  task_id?: string;
  segment_id?: string;
  project_id?: string;
  video_url: string;
  total_latent: number;
  source_frames: number;
  source_duration: number;
  fps: number;
  width: number;
  height: number;
}

export interface RetakeRangeInfo {
  start_latent: number;
  end_latent: number;
  total_latent: number;
  start_frame: number;
  end_frame: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  source_frames: number;
  source_duration: number;
  fps: number;
}

export interface RetakeResponse {
  task_id: string;
  status: string;
  message: string;
  project_id: string | null;
  source_segment_id: string | null;
  final_prompt: string | null;
  range: RetakeRangeInfo | null;
}

/** 单条任务的重拍源信息 */
export async function fetchTaskRetakeSource(taskId: string): Promise<RetakeSourceInfo> {
  const { data } = await http.get<RetakeSourceInfo>(`/retake/source/${taskId}`);
  return data;
}

/** 项目版本的重拍源信息 */
export async function fetchSegmentRetakeSource(
  segmentId: string,
): Promise<RetakeSourceInfo> {
  const { data } = await http.get<RetakeSourceInfo>(
    `/retake/source/segment/${segmentId}`,
  );
  return data;
}

export interface RetakePayload {
  prompt: string;
  startLatent: number;
  endLatent: number;
  keepAudio: boolean;
  seed: number | null;
}

/** 单条任务重拍 */
export async function submitTaskRetake(
  taskId: string,
  payload: RetakePayload,
  appendProjectPrompt = false,
): Promise<RetakeResponse> {
  const form = new FormData();
  form.append("task_id", taskId);
  form.append("prompt", payload.prompt);
  form.append("start_latent", String(payload.startLatent));
  form.append("end_latent", String(payload.endLatent));
  form.append("keep_audio", String(payload.keepAudio));
  form.append("append_project_prompt", String(appendProjectPrompt));
  if (payload.seed !== null && payload.seed !== undefined) {
    form.append("seed", String(payload.seed));
  }
  const { data } = await http.post<RetakeResponse>("/retake", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300_000,
  });
  return data;
}

/** 项目版本重拍（结果会成为新版本） */
export async function submitSegmentRetake(
  projectId: string,
  segmentId: string,
  payload: RetakePayload,
  appendProjectPrompt = true,
): Promise<RetakeResponse> {
  const form = new FormData();
  form.append("prompt", payload.prompt);
  form.append("start_latent", String(payload.startLatent));
  form.append("end_latent", String(payload.endLatent));
  form.append("keep_audio", String(payload.keepAudio));
  form.append("append_project_prompt", String(appendProjectPrompt));
  if (payload.seed !== null && payload.seed !== undefined) {
    form.append("seed", String(payload.seed));
  }
  const { data } = await http.post<RetakeResponse>(
    `/projects/${projectId}/segments/${segmentId}/retake`,
    form,
    { headers: { "Content-Type": "multipart/form-data" }, timeout: 300_000 },
  );
  return data;
}
