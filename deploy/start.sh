#!/usr/bin/env bash
# GMod Workshop Mod 管理面板 - 启动/停止脚本(适用于无 systemd 或手动部署场景)
# 用法:
#   bash deploy/start.sh start     # 后台启动(默认 127.0.0.1:8000)
#   bash deploy/start.sh stop      # 停止
#   bash deploy/start.sh restart   # 重启
#   bash deploy/start.sh status    # 查看状态
# 环境变量覆盖:
#   HOST=0.0.0.0 PORT=8000 bash deploy/start.sh start
# 注意:已通过 install.sh 安装 systemd 服务时,请直接用 systemctl 管理,无需本脚本。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
PID_FILE="${APP_DIR}/backend/data/uvicorn.pid"
LOG_FILE="${APP_DIR}/backend/data/uvicorn.log"

_running() {
  [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

do_start() {
  if ! [ -x "${APP_DIR}/backend/.venv/bin/python" ]; then
    echo "!! 未找到虚拟环境 backend/.venv,请先执行:sudo bash deploy/install.sh"
    exit 1
  fi
  if _running; then
    echo "==> 已在运行(PID $(cat "${PID_FILE}")),如需重启请用 restart"
    exit 0
  fi
  mkdir -p "${APP_DIR}/backend/data"
  cd "${APP_DIR}/backend"
  echo "==> 数据库迁移…"
  .venv/bin/alembic upgrade head
  if [ ! -f "${APP_DIR}/frontend/dist/index.html" ]; then
    echo "!! frontend/dist 不存在,Web 界面不可用(API 正常)"
    echo "   构建方法:cd frontend && npm ci && npm run build"
  fi
  echo "==> 启动 uvicorn(${HOST}:${PORT})…"
  nohup .venv/bin/uvicorn app.main:app --host "${HOST}" --port "${PORT}" >> "${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"
  sleep 1
  if _running; then
    echo "==> 已启动:http://${HOST}:${PORT}(日志:${LOG_FILE})"
  else
    echo "!! 启动失败,请查看日志:${LOG_FILE}"
    rm -f "${PID_FILE}"
    exit 1
  fi
}

do_stop() {
  if ! _running; then
    echo "==> 未在运行"
    rm -f "${PID_FILE}"
    return 0
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  echo "==> 停止面板服务(PID ${pid})…"
  kill "${pid}"          # 优雅退出(SIGTERM);仅停止面板进程,不涉及游戏服务器进程
  rm -f "${PID_FILE}"
  echo "==> 已停止"
}

do_status() {
  if _running; then
    echo "运行中(PID $(cat "${PID_FILE}")):http://${HOST}:${PORT}"
  else
    echo "未运行"
    exit 1
  fi
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop || true; do_start ;;
  status)  do_status ;;
  *) echo "用法:bash deploy/start.sh {start|stop|restart|status}"; exit 1 ;;
esac
