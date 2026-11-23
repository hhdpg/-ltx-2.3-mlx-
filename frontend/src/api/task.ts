import { http } from "./http";
import type {
  CancelResponse,
  DeleteResponse,
  TaskDetail,
  TaskListResponse,
  TaskLogsResponse,
  TaskStatus,
} from "@/types";

export interface TaskQuery {
  status?: TaskStatus | "";
  task_type?: "T2V" | "I2V" | "";
  limit?: number;
  offset?: number;
}

export async function fetchTasks(query: TaskQuery = {}): Promise<TaskListResponse> {
  const params: Record<string, string | number> = {
    limit: query.limit ?? 20,
    offset: query.offset ?? 0,
  };
  if (query.status) params.status = query.status;
  if (query.task_type) params.task_type = query.task_type;
  const { data } = await http.get<TaskListResponse>("/tasks", { params });
  return data;
}

export async function fetchTask(taskId: string): Promise<TaskDetail> {
  const { data } = await http.get<TaskDetail>(`/tasks/${taskId}`);
  return data;
}

export async function cancelTask(taskId: string): Promise<CancelResponse> {
  const { data } = await http.post<CancelResponse>(`/tasks/${taskId}/cancel`);
  return data;
}

export async function deleteTask(
  taskId: string,
  deleteOutput = true,
): Promise<DeleteResponse> {
  const { data } = await http.delete<DeleteResponse>(`/tasks/${taskId}`, {
    params: { delete_output: deleteOutput },
  });
  return data;
}

export async function fetchTaskLogs(
  taskId: string,
  lines = 200,
): Promise<TaskLogsResponse> {
  const { data } = await http.get<TaskLogsResponse>(`/tasks/${taskId}/logs`, {
    params: { lines },
  });
  return data;
}

export function videoUrl(taskId: string): string {
  return `/api/files/${taskId}/video`;
}

export function downloadUrl(taskId: string): string {
  return `/api/files/${taskId}/download`;
}
