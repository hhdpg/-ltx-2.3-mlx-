import { http } from "./http";
import type {
  ExtendFormPayload,
  ExtendResponse,
  GenerationProjectDetail,
  GenerationSegment,
  ProjectCreatePayload,
  ProjectListResponse,
  SegmentListResponse,
} from "@/types";

export async function fetchProjects(): Promise<ProjectListResponse> {
  const { data } = await http.get<ProjectListResponse>("/projects");
  return data;
}

export async function fetchProject(projectId: string): Promise<GenerationProjectDetail> {
  const { data } = await http.get<GenerationProjectDetail>(`/projects/${projectId}`);
  return data;
}

export async function createProject(
  payload: ProjectCreatePayload,
): Promise<GenerationProjectDetail> {
  const { data } = await http.post<GenerationProjectDetail>("/projects", payload);
  return data;
}

export async function updateProject(
  projectId: string,
  payload: Partial<ProjectCreatePayload>,
): Promise<GenerationProjectDetail> {
  const { data } = await http.put<GenerationProjectDetail>(
    `/projects/${projectId}`,
    payload,
  );
  return data;
}

export async function deleteProject(
  projectId: string,
  deleteVideos = false,
): Promise<{ message: string; deleted_segments: number; deleted_files: number }> {
  const { data } = await http.delete(`/projects/${projectId}`, {
    params: { delete_videos: deleteVideos },
  });
  return data;
}

export async function fetchSegments(projectId: string): Promise<SegmentListResponse> {
  const { data } = await http.get<SegmentListResponse>(
    `/projects/${projectId}/segments`,
  );
  return data;
}

export async function attachSegment(
  projectId: string,
  taskId: string,
): Promise<GenerationSegment> {
  const { data } = await http.post<GenerationSegment>(
    `/projects/${projectId}/segments`,
    { task_id: taskId },
  );
  return data;
}

export async function setCurrentSegment(
  projectId: string,
  segmentId: string,
): Promise<GenerationSegment> {
  const { data } = await http.put<GenerationSegment>(
    `/projects/${projectId}/current-segment`,
    { segment_id: segmentId },
  );
  return data;
}

export async function deleteSegment(
  segmentId: string,
  deleteVideo = false,
): Promise<{ message: string }> {
  const { data } = await http.delete(`/segments/${segmentId}`, {
    params: { delete_video: deleteVideo },
  });
  return data;
}

export async function previewPrompt(
  projectId: string,
  prompt: string,
  appendProjectPrompt: boolean,
): Promise<string> {
  const { data } = await http.post<{ final_prompt: string }>(
    `/projects/${projectId}/prompt-preview`,
    { prompt, append_project_prompt: appendProjectPrompt },
  );
  return data.final_prompt;
}

export async function submitExtend(
  projectId: string,
  payload: ExtendFormPayload,
): Promise<ExtendResponse> {
  const form = new FormData();
  form.append("source_segment_id", payload.source_segment_id);
  form.append("prompt", payload.prompt);
  form.append("extend_frames", String(payload.extend_frames));
  form.append("append_project_prompt", String(payload.append_project_prompt));
  if (payload.seed !== null && payload.seed !== undefined) {
    form.append("seed", String(payload.seed));
  }
  if (payload.anchor_frame !== null && payload.anchor_frame !== undefined) {
    form.append("anchor_frame", String(payload.anchor_frame));
  }
  if (payload.anchor_strength !== null && payload.anchor_strength !== undefined) {
    form.append("anchor_strength", String(payload.anchor_strength));
  }
  if (payload.anchor_image) {
    form.append("anchor_image", payload.anchor_image, payload.anchor_image.name);
  }

  const { data } = await http.post<ExtendResponse>(
    `/projects/${projectId}/extend`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 300_000,
    },
  );
  return data;
}

export function segmentVideoUrl(segmentId: string): string {
  return `/api/segments/${segmentId}/video`;
}
