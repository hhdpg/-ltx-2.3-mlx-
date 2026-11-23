#!/usr/bin/env bash
# 一键启动：后端 (127.0.0.1:8000) + 前端 (127.0.0.1:5173)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# ---------- 前置检查 ----------
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "✗ 后端虚拟环境不存在：$BACKEND_DIR/.venv"
  echo "  请先执行：cd backend && uv venv --python 3.12 .venv && uv pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "✗ 前端依赖未安装：$FRONTEND_DIR/node_modules"
  echo "  请先执行：cd frontend && npm install"
  exit 1
fi

if [ ! -f "$ROOT_DIR/.env" ] && [ -f "$ROOT_DIR/.env.example" ]; then
  echo "! 未找到 .env，已从 .env.example 复制，请按本机路径修改"
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

# ---------- 已运行则先停止 ----------
if [ -f "$RUN_DIR/backend.pid" ] || [ -f "$RUN_DIR/frontend.pid" ]; then
  echo "! 检测到已有进程，先执行停止脚本"
  "$ROOT_DIR/scripts/stop.sh" || true
fi

# ---------- 启动后端 ----------
echo "→ 启动后端 (127.0.0.1:8000)"
(
  cd "$BACKEND_DIR"
  nohup .venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 \
    > "$LOG_DIR/backend.out" 2>&1 &
  echo $! > "$RUN_DIR/backend.pid"
)

# ---------- 启动前端 ----------
echo "→ 启动前端 (127.0.0.1:5173)"
(
  cd "$FRONTEND_DIR"
  nohup npm run dev > "$LOG_DIR/frontend.out" 2>&1 &
  echo $! > "$RUN_DIR/frontend.pid"
)

sleep 3

BACK_PID="$(cat "$RUN_DIR/backend.pid" 2>/dev/null || echo '?')"
FRONT_PID="$(cat "$RUN_DIR/frontend.pid" 2>/dev/null || echo '?')"

echo ""
echo "✓ 已启动"
echo "  后端 PID: $BACK_PID   日志: $LOG_DIR/backend.out"
echo "  前端 PID: $FRONT_PID   日志: $LOG_DIR/frontend.out"
echo ""
echo "  网页:      http://127.0.0.1:5173"
echo "  接口文档:  http://127.0.0.1:8000/docs"
echo "  停止服务:  $ROOT_DIR/scripts/stop.sh"
echo "  查看日志:  $ROOT_DIR/scripts/logs.sh"
