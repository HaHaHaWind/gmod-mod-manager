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
#    logs 也必须建好并授权:LOG_DIR 默认相对 backend/,而 backend/ 属 root,
#    不授权则文件日志静默降级为"仅终端输出"(app.log 永远不生成)
mkdir -p backend/data backend/logs
chown -R "${SERVICE_USER}":"${SERVICE_USER}" backend/data backend/logs

# 以服务账号身份执行命令:root 下用 sudo -u,避免把数据/库文件写成 root 属主
# (否则服务账号对库文件只读,写入时报 "attempt to write a readonly database")
run_as_service() {
  if [ "$(id -u)" = "0" ] && id "${SERVICE_USER}" &>/dev/null; then
    sudo -u "${SERVICE_USER}" "$@"
  else
    "$@"
  fi
}
# 4.0) 授权路径以 .env 实际生效的配置为准(参数默认值仅作回退)。
#      只按硬编码路径授权的话,用户改了 .env 里的目录后写入会直接 Permission denied。
env_get() {
  local key="$1" default="$2" val
  val="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" backend/.env 2>/dev/null \
        | tail -n1 | tr -d '\r' | sed 's/[[:space:]]*$//')"
  val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
  printf '%s' "${val:-$default}"
}
GMOD_ADDONS="$(env_get GMOD_ADDONS_ROOT "${GMOD_ROOT}/garrysmod/addons")"
GMOD_CFG="$(dirname "$(env_get WORKSHOP_IDS_FILE "${GMOD_ROOT}/garrysmod/cfg/srcds_workshop_ids.txt")")"
GMOD_TRASH="$(env_get TRASH_ROOT "${GMOD_ROOT}/.gmm_trash")"
GMOD_CACHE="$(env_get WORKSHOP_CACHE_ROOT "${GMOD_ROOT}/steam_cache")"
GMOD_SERVER_ROOT="$(env_get GMOD_SERVER_ROOT "${GMOD_ROOT}")"

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
# 4.2) 目录树授权:rwX = 组读写+目录可进入;
#      目录额外加 g+s(setgid):gmm 新建的文件自动继承服务组,
#      配合 4.3 把 srcds 用户入组,即使 umask 收紧也能互相读取
grant_rw() {
  chgrp -R "${SERVICE_USER}" "$1" 2>/dev/null || true
  chmod -R g+rwX "$1" 2>/dev/null || true
  find "$1" -type d -exec chmod g+s {} + 2>/dev/null || true
}

grant_traverse "${GMOD_ADDONS}"
grant_traverse "${GMOD_CFG}"
grant_traverse "${GMOD_TRASH}"
grant_traverse "${GMOD_CACHE}"
for d in "${GMOD_ADDONS}" "${GMOD_CFG}" "${GMOD_TRASH}"; do
  [ -d "${d}" ] || mkdir -p "${d}"
  grant_rw "${d}"
done
# 缓存目录必须"可写":删除 = 把缓存移出 <id>/,恢复 = 移回,
# 两者都需要源父目录可写;只授只读会直接 Errno 13(Permission denied)。
if [ -d "${GMOD_CACHE}" ]; then
  grant_rw "${GMOD_CACHE}"
  # srcds 之后新下载的目录不会继承 chmod,用默认 ACL 兜底,避免新 Mod 再次删除失败
  if command -v setfacl &>/dev/null; then
    setfacl -R  -m "g:${SERVICE_USER}:rwX" "${GMOD_CACHE}" 2>/dev/null || true
    setfacl -R -d -m "g:${SERVICE_USER}:rwX" "${GMOD_CACHE}" 2>/dev/null || true
  else
    echo "!! 未安装 setfacl(acl 包):建议安装以便新目录自动继承写权限"
  fi
fi

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
  # ReadWritePaths 必须跟随 .env 的实际路径,否则改了目录会被 systemd 沙箱拦下。
  # 只列真实存在的目录(列出不存在的路径会让单元启动失败);游戏根目录优先,
  # 已在其下的子目录不再重复列出。
  RWP="${APP_DIR}"
  if [ -d "${GMOD_SERVER_ROOT}" ]; then RWP="${RWP} ${GMOD_SERVER_ROOT}"; fi
  for p in "${GMOD_ADDONS}" "${GMOD_CFG}" "${GMOD_TRASH}" "${GMOD_CACHE}"; do
    [ -d "${p}" ] || continue
    case "${p}" in "${GMOD_SERVER_ROOT}"/*) continue ;; esac
    RWP="${RWP} ${p}"
  done
  sed -e "s#/opt/gmod-mod-manager#${APP_DIR}#g" \
      -e "s#User=gmm#User=${SERVICE_USER}#" \
      -e "s#Group=gmm#Group=${SERVICE_USER}#" \
      -e "s#^ReadWritePaths=.*#ReadWritePaths=${RWP}#" \
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
