#!/usr/bin/env bash
# 停止后端与前端
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_one() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  if [ ! -f "$pid_file" ]; then
    echo "· $name 未在运行（无 pid 文件）"
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$pid_file"
    return
  fi

  if kill -0 "$pid" 2>/dev/null; then
    echo "→ 停止 $name (PID $pid)"
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.3
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "  强制结束 $name"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  else
    echo "· $name (PID $pid) 已不存在"
  fi
  rm -f "$pid_file"
}

# 兜底：清理残留的 uvicorn / vite 进程（仅限本项目端口）
stop_one frontend
stop_one backend

for port in 8000 5173; do
  pids="$(lsof -ti tcp:$port 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "→ 清理端口 $port 上的残留进程: $pids"
    echo "$pids" | xargs -r kill -TERM 2>/dev/null || true
    sleep 1
    pids="$(lsof -ti tcp:$port 2>/dev/null || true)"
    [ -n "$pids" ] && echo "$pids" | xargs -r kill -KILL 2>/dev/null || true
  fi
done

echo "✓ 已停止"
