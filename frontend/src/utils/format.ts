import { computed } from "vue";
import type { TaskStatus } from "@/types";

export interface StatusMeta {
  label: string;
  type: "info" | "warning" | "primary" | "success" | "danger";
  color: string;
  active: boolean;
}

const MAP: Record<TaskStatus, StatusMeta> = {
  QUEUED: { label: "排队中", type: "info", color: "#8b96a5", active: true },
  STARTING: { label: "启动中", type: "warning", color: "#d29922", active: true },
  RUNNING: { label: "生成中", type: "primary", color: "#4c8dff", active: true },
  SUCCEEDED: { label: "已完成", type: "success", color: "#3fb950", active: false },
  FAILED: { label: "失败", type: "danger", color: "#f85149", active: false },
  CANCELING: { label: "正在取消", type: "warning", color: "#d29922", active: true },
  CANCELED: { label: "已取消", type: "info", color: "#6b7785", active: false },
};

export function statusMeta(status: TaskStatus): StatusMeta {
  return MAP[status] ?? { label: status, type: "info", color: "#8b96a5", active: false };
}

export function useStatusMeta(status: () => TaskStatus) {
  return computed(() => statusMeta(status()));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "—";
  }
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function formatElapsed(startedAt: string | null | undefined): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return "—";
  return formatDuration((Date.now() - start) / 1000);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}
