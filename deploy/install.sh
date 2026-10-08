#!/usr/bin/env bash
# GMod Workshop Mod 管理面板 - 一键安装脚本(Linux)
# 用法:
#   sudo bash deploy/install.sh            # 安装到 /opt/gmod-mod-manager
#   APP_DIR=/srv/gmm sudo -E bash deploy/install.sh
# 前置条件:python3 (>=3.10) / python3-venv / (可选) nginx / systemd
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/gmod-mod-manager}"
SERVICE_USER="${SERVICE_USER:-gmm}"
GMOD_ROOT="${GMOD_ROOT:-/home/l4d2/Steam/steamapps/common/GarrysModDS}"

echo "==> 目标目录:${APP_DIR}"

# 0) 仓库就位(若从压缩包解压到当前目录,则复制过去)
if [ "$(pwd)" != "${APP_DIR}" ]; then
  mkdir -p "${APP_DIR}"
  cp -r backend frontend docs deploy .env.example README.md "${APP_DIR}/" 2>/dev/null || true
fi
cd "${APP_DIR}"

# 1) 服务账号(无登录 shell,仅运行面板)
if ! id "${SERVICE_USER}" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

# 2) Python 虚拟环境 + 依赖
# 2.1) 版本检查(需 >= 3.10)
if ! python3 -c 'import sys; assert sys.version_info >= (3, 10)' &>/dev/null; then
  echo "!! 需要 Python >= 3.10,当前:$(python3 -V 2>&1 || echo '未找到 python3')"; exit 1
fi
# 2.2) Debian/Ubuntu 缺少 python3-venv(ensurepip)时 venv 创建必然失败,自动安装
if ! python3 -c "import ensurepip" &>/dev/null; then
  echo "==> 缺少 python3-venv(ensurepip),尝试自动安装…"
  if command -v apt-get &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq python3-venv
  elif command -v dnf &>/dev/null; then
    dnf install -y python3
  elif command -v yum &>/dev/null; then
    yum install -y python3
  else
    echo "!! 未识别的包管理器,请手动安装 python3-venv 后重跑本脚本"; exit 1
  fi
fi
# 2.3) 清理上次失败遗留的不完整虚拟环境(pip 不可用即视为损坏)
if [ -d backend/.venv ] && ! backend/.venv/bin/pip --version &>/dev/null; then
  echo "==> 检测到不完整的虚拟环境 backend/.venv,清理后重建"
  rm -rf backend/.venv
fi
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.in

# 3) 配置文件(已存在则不覆盖)
if [ ! -f backend/.env ]; then
  cp .env.example backend/.env
  echo "==> 已生成 backend/.env,请按需修改(游戏路径已预填:${GMOD_ROOT})"
fi

# 4) 数据目录与权限(面板需读写游戏服务器的 addons/cfg/回收站)
mkdir -p backend/data
chown -R "${SERVICE_USER}":"${SERVICE_USER}" backend/data

# 以服务账号身份执行命令:root 下用 sudo -u,避免把数据/库文件写成 root 属主
# (否则服务账号对库文件只读,写入时报 "attempt to write a readonly database")
run_as_service() {
  if [ "$(id -u)" = "0" ] && id "${SERVICE_USER}" &>/dev/null; then
    sudo -u "${SERVICE_USER}" "$@"
  else
    "$@"
  fi
}
GMOD_ADDONS="${GMOD_ROOT}/garrysmod/addons"
GMOD_CFG="${GMOD_ROOT}/garrysmod/cfg"

# 4.1) 祖先目录穿越权限:服务账号需要对路径每一级目录都有 x 权限,
#      家目录(如 /home/l4d2)常见 700/750,会导致 stat 下层路径直接 Permission denied
grant_traverse() {
  local seg prefix=""
  while IFS= read -r seg; do
    [ -z "${seg}" ] && continue
    prefix="${prefix}/${seg}"
    if [ -d "${prefix}" ]; then
      chmod a+x "${prefix}" 2>/dev/null || true
    fi
  done <<< "$(printf '%s' "${1%/}" | tr '/' '\n')"
}
# 4.2) 目录树授权:rwX = 组读写+目录可进入; rX = 组只读+目录可进入;
#      目录额外加 g+s(setgid):gmm 新建的文件自动继承服务组,
#      配合 4.3 把 srcds 用户入组,即使 umask 收紧也能互相读取
grant_rw() {
  chgrp -R "${SERVICE_USER}" "$1" 2>/dev/null || true
  chmod -R g+rwX "$1" 2>/dev/null || true
  find "$1" -type d -exec chmod g+s {} + 2>/dev/null || true
}
grant_ro() {
  chgrp -R "${SERVICE_USER}" "$1" 2>/dev/null || true
  chmod -R g+rX  "$1" 2>/dev/null || true
  find "$1" -type d -exec chmod g+s {} + 2>/dev/null || true
}

grant_traverse "${GMOD_ADDONS}"
grant_traverse "${GMOD_ROOT}/steam_cache"
for d in "${GMOD_ADDONS}" "${GMOD_CFG}" "${GMOD_ROOT}/.gmm_trash"; do
  [ -d "${d}" ] || mkdir -p "${d}"
  grant_rw "${d}"
done
if [ -d "${GMOD_ROOT}/steam_cache" ]; then grant_ro "${GMOD_ROOT}/steam_cache"; fi

# 4.3) 把 srcds 运行用户加入服务组:gmm 写入 addons/ids 的文件属主为 gmm 组,
#      srcds 用户入组后总能读到;可用 SRCDS_USER=xxx 覆盖默认值
SRCDS_USER="${SRCDS_USER:-l4d2}"
if id "${SRCDS_USER}" &>/dev/null; then
  usermod -aG "${SERVICE_USER}" "${SRCDS_USER}" 2>/dev/null || true
  echo "==> 已将 srcds 用户 ${SRCDS_USER} 加入 ${SERVICE_USER} 组(已有登录会话需重新登录生效)"
fi

# 5) 数据库迁移(以服务账号执行,避免库文件被写成 root 属主导致后续 readonly)
cd backend
run_as_service .venv/bin/alembic upgrade head
chown -R "${SERVICE_USER}":"${SERVICE_USER}" data 2>/dev/null || true

# 6) 前端产物:仓库自带 dist 时直接使用;否则需 Node.js 现场构建(git clone 部署时必经此步)
if [ ! -f frontend/dist/index.html ]; then
  if ! command -v npm &>/dev/null; then
    echo "!! 未发现 frontend/dist 且未检测到 npm,无法获得前端界面"
    echo "   请安装 Node.js >= 18 后重跑本脚本,或手动执行:cd frontend && npm ci && npm run build"
    exit 1
  fi
  echo "==> 未发现前端产物,使用 npm 自动构建(首次较慢)…"
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi

# 7) 管理员账号(交互式;当前目录为 backend,以服务账号执行)
echo "==> 创建管理员账号(交互式输入密码)"
run_as_service .venv/bin/python -m app.cli create-admin admin || \
  echo "!! 管理员创建失败或已存在,可稍后手动执行:cd backend && sudo -u ${SERVICE_USER} .venv/bin/python -m app.cli create-admin <用户名>"
cd ..

# 8) systemd + nginx
if [ -d /etc/systemd/system ]; then
  sed "s#/opt/gmod-mod-manager#${APP_DIR}#g; s#User=gmm#User=${SERVICE_USER}#; s#Group=gmm#Group=${SERVICE_USER}#" \
    deploy/gmod-mod-manager.service > /etc/systemd/system/gmod-mod-manager.service
  systemctl daemon-reload
  systemctl enable --now gmod-mod-manager
  echo "==> 服务已启动:systemctl status gmod-mod-manager"
fi
# 8.2) nginx 反代:未安装时自动安装(apt/dnf/yum),装好后写入配置
NGINX_CONF_DIR=/etc/nginx/conf.d
if [ ! -d "${NGINX_CONF_DIR}" ] || ! command -v nginx &>/dev/null; then
  echo "==> 未检测到 nginx,尝试自动安装…"
  if command -v apt-get &>/dev/null; then
    apt-get update -qq || true
    apt-get install -y -qq nginx || true
  elif command -v dnf &>/dev/null; then
    dnf install -y nginx || true
  elif command -v yum &>/dev/null; then
    yum install -y nginx || true
  else
    echo "!! 未识别的包管理器,无法自动安装 nginx"
  fi
fi
if [ -d "${NGINX_CONF_DIR}" ] && command -v nginx &>/dev/null; then
  cp deploy/nginx.conf "${NGINX_CONF_DIR}/gmod-mod-manager.conf"
  nginx -t && systemctl enable --now nginx && systemctl reload nginx
  echo "==> nginx 已配置:http://<服务器IP>:8080(记得在防火墙/云安全组放行 8080)"
else
  echo "!! nginx 不可用,已跳过反代配置;可参考 deploy/nginx.conf 手动配置,"
  echo "   或临时用 SSH 隧道访问:ssh -L 8080:127.0.0.1:8000 <user>@<服务器IP>"
fi

cat <<'EOF'

============================================================
安装完成。后续步骤:
  1. 编辑 backend/.env:确认 GMOD_* 路径、MANAGEMENT_MODE、READ_ONLY
  2. 首次使用建议 READ_ONLY=true + MANAGEMENT_MODE=observe,观察扫描结果
  3. 确认无误后改为实际管理模式并 systemctl restart gmod-mod-manager
  4. 浏览器访问 http://<服务器IP>:8080,用刚才创建的 admin 登录
============================================================
EOF
