#!/usr/bin/env bash
# 查看日志：./scripts/logs.sh [backend|frontend|app|task <id>]
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"

target="${1:-all}"

case "$target" in
  backend)
    exec tail -F "$LOG_DIR/backend.out"
    ;;
  frontend)
    exec tail -F "$LOG_DIR/frontend.out"
    ;;
  app)
    exec tail -F "$LOG_DIR/app.log"
    ;;
  task)
    task_id="${2:-}"
    if [ -z "$task_id" ]; then
      echo "用法: $0 task <task_id>"
      echo ""
      echo "最近的任务日志文件："
      ls -t "$LOG_DIR/tasks" 2>/dev/null | head -10
      exit 1
    fi
    exec tail -F "$LOG_DIR/tasks/$task_id.log"
    ;;
  all|*)
    echo "可用日志："
    echo "  $0 backend        后端服务输出"
    echo "  $0 frontend       前端 Vite 输出"
    echo "  $0 app            应用日志 (logs/app.log)"
    echo "  $0 task <task_id> 单个任务的推理日志"
    echo ""
    echo "最近任务日志："
    ls -lt "$LOG_DIR/tasks" 2>/dev/null | head -6 || echo "  （暂无）"
    ;;
esac
