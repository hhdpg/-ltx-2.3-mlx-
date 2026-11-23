import { http } from "./http";
import type {
  HealthResponse,
  SettingsResponse,
  SettingsUpdate,
  SystemInfoResponse,
  TaskLogsResponse,
} from "@/types";

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>("/health", { timeout: 120_000 });
  return data;
}

export async function fetchSystemInfo(): Promise<SystemInfoResponse> {
  const { data } = await http.get<SystemInfoResponse>("/system/info", {
    timeout: 120_000,
  });
  return data;
}

export async function fetchSettings(): Promise<SettingsResponse> {
  const { data } = await http.get<SettingsResponse>("/settings");
  return data;
}

export async function updateSettings(
  payload: SettingsUpdate,
): Promise<SettingsResponse> {
  const { data } = await http.put<SettingsResponse>("/settings", payload);
  return data;
}

export async function fetchSystemLogs(lines = 1000): Promise<TaskLogsResponse> {
  const { data } = await http.get<TaskLogsResponse>("/system/logs", {
    params: { lines },
  });
  return data;
}
