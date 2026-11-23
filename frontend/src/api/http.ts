import axios, { AxiosError } from "axios";

export const http = axios.create({
  baseURL: "/api",
  timeout: 120_000,
  validateStatus: (status) => status >= 200 && status < 300,
});

export interface ApiErrorInfo {
  message: string;
  status: number | null;
}

export function extractError(error: unknown): ApiErrorInfo {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: unknown }>;
    const detail = axiosError.response?.data?.detail;
    let message = axiosError.message;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join("；");
    } else if (detail && typeof detail === "object") {
      message = JSON.stringify(detail);
    }
    if (axiosError.code === "ECONNABORTED") {
      message = "请求超时，请稍后重试";
    } else if (!axiosError.response) {
      message = "无法连接本地后端服务，请确认 127.0.0.1:8000 已启动";
    }
    return { message, status: axiosError.response?.status ?? null };
  }
  if (error instanceof Error) {
    return { message: error.message, status: null };
  }
  return { message: "未知错误", status: null };
}
