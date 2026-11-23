import { http } from "./http";
import type { CreateTaskResponse, UploadResponse } from "@/types";

export interface SubmitPayload {
  task_type: "T2V" | "I2V";
  prompt: string;
  width: number;
  height: number;
  frames: number;
  frame_rate: number;
  mode: string;
  seed: number | null;
  image: File | null;
  projectId?: string | null;
}

export async function submitGeneration(
  payload: SubmitPayload,
  onProgress?: (percent: number) => void,
): Promise<CreateTaskResponse> {
  const form = new FormData();
  form.append("task_type", payload.task_type);
  form.append("prompt", payload.prompt);
  form.append("width", String(payload.width));
  form.append("height", String(payload.height));
  form.append("frames", String(payload.frames));
  form.append("frame_rate", String(payload.frame_rate));
  form.append("mode", payload.mode);
  if (payload.seed !== null && payload.seed !== undefined) {
    form.append("seed", String(payload.seed));
  }
  if (payload.image) {
    form.append("image", payload.image, payload.image.name);
  }
  if (payload.projectId) {
    form.append("project_id", payload.projectId);
  }

  const { data } = await http.post<CreateTaskResponse>("/generations", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
  return data;
}

export async function uploadImage(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("image", file, file.name);
  const { data } = await http.post<UploadResponse>("/files/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
