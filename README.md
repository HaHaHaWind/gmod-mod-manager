# GMod Workshop Mod 管理面板(gmod-mod-manager)

面向 Linux Garry's Mod 专用服务器的 Workshop Mod 管理面板。提供 Mod 库盘点、变更计划(预览 → 提交 → 应用)、回收站、后台任务、审计日志等能力,**全程不杀进程、不自动重启服务器**;需要重启的动作只置位 `requires_restart`,由管理员决定何时重启。

> 默认部署目标:`/home/l4d2/Steam/steamapps/common/GarrysModDS`(所有路径均可在环境变量中覆盖,未配置时面板可隔离运行,仅展示"路径未配置"提示)。

---

## 目录

- [功能特性](#功能特性)
- [核心概念](#核心概念)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [CLI 管理命令](#cli-管理命令)
- [API 概览](#api-概览)
- [安全模型](#安全模型)
- [目录结构](#目录结构)
- [开发与测试](#开发与测试)
- [常见问题](#常见问题)

---

## 功能特性

- **Mod 库**:扫描 Workshop 缓存(`.gma`)与 `garrysmod/addons` 目录,识别 GMA 元数据(标题/作者/标签/文件清单/大小),可选通过 Steam Web API 补全远程元数据(带 TTL 缓存)。
- **三种管理模式**(适配器模式,详见 [架构文档](docs/architecture.md)):
  - `observe`:只读观察,不写任何游戏文件;
  - `native_ids`:管理 `cfg/srcds_workshop_ids.txt`(KeyValues 子集解析,保留注释与格式);
  - `local_managed`:面板自行部署本地副本(`gma_copy` 复制 GMA 或 `folder_extract` 解包文件夹)。
- **变更计划**:先创建草稿(diff 预览、冲突与阻塞项检查)→ 提交排队 → 后台 worker 逐步执行 → 失败项可重试;计划有过期时间(TTL)与乐观锁 revision。
- **五维状态模型**:每条 Mod 记录维护 `inventory_state / desired_state / apply_state / runtime_state / requires_restart` 五个独立维度;`runtime_state` 由 srcds 挂载缓存(`cfg/srcds_addons.txt`)探针推断,探针缺失时恒为 `unknown`,绝不臆测。
- **回收站**:删除动作先移入受管回收站目录,支持一键还原与到期自动清理(保留天数可配)。
- **后台任务**:扫描 / 元数据刷新 / 集合快照 / 应用计划均走进程内队列,启动时自动恢复被中断的任务并生成恢复计划。
- **审计日志**:记录全部敏感动作(操作人/动作/结果/目标/脱敏详情/IP/request_id)。
- **预览图代理**:`/api/preview` 校验白名单域名 + 公网 IP,防 SSRF,支持磁盘缓存。
- **本地封面图**:扫描/元数据刷新后自动抓取创意工坊封面落盘(`data/previews`),列表与详情优先显示本地图,未落盘时自动回退在线代理(`AUTO_FETCH_PREVIEWS` 可关)。
- **中文界面**:Vue 3 + Element Plus,全部文案为中文。

## 核心概念

### 三种管理模式

| 模式 | 面板写什么 | 适用场景 | 恢复方式 |
| --- | --- | --- | --- |
| `observe` | 什么都不写(默认) | 上线前摸底、只读审计 | 不适用 |
| `native_ids` | `cfg/srcds_workshop_ids.txt` | 服务器用 Workshop ID 方式加载 | 回收站保留原始文件副本 |
| `local_managed` | `garrysmod/addons` 下的本地副本 | 需要固定内容、离线可复现 | 删除部署副本 + 回收站 |

`local_managed` 的部署策略:

- `gma_copy`:直接复制 `.gma` 到 addons 目录(加载快,文件大);
- `folder_extract`:解包为文件夹(便于打补丁,占用更高)。

### 五维状态

| 维度 | 取值 | 含义 |
| --- | --- | --- |
| `inventory_state` | `present / missing / extra / unknown` | 磁盘实际有什么 |
| `desired_state` | `enabled / disabled / deleted` | 管理员希望是什么 |
| `apply_state` | `idle / pending / in_progress / applied / failed` | 部署动作进行到哪一步 |
| `runtime_state` | `loaded / not_loaded / unknown` | 服务器运行时加载状态(由 srcds 挂载缓存探针推断,探针缺失时恒为 unknown) |
| `requires_restart` | `0 / 1` | 是否需要重启才能生效 |

### 变更计划生命周期

```
draft ──提交──▶ queued ──worker 领取──▶ applying ──▶ applied
  │                │                    │
  │                └──取消──▶ cancelled │
  └──过期/TTL──▶ expired               └──部分失败──▶ failed(可 retry)
```

## 快速开始

### 一键启动(Windows 本机体验 / 无 systemd 的 Linux)

**Windows**:双击项目根目录的 `start.bat`(或 PowerShell 运行 `.\start.ps1 [-Port 8000]`),脚本自动完成:创建虚拟环境并安装依赖 → 生成 `.env` → 数据库迁移 → 缺失时自动 npm 构建前端 → 询问创建管理员 → 启动服务。完成后浏览器访问 `http://127.0.0.1:8000`。

**Linux**(未使用 systemd 安装方式时):

```bash
bash deploy/start.sh start     # 后台启动(默认 127.0.0.1:8000,可用 HOST=/PORT= 环境变量覆盖)
bash deploy/start.sh stop      # 停止(仅停止面板进程,不涉及游戏服务器)
bash deploy/start.sh restart   # 重启
bash deploy/start.sh status    # 查看状态
```

### 方式一:一键安装(Linux,推荐)

```bash
# 1. 上传项目到服务器,例如 /opt/gmod-mod-manager
sudo bash deploy/install.sh
```

脚本完成:创建 `gmm` 运行用户 → Python venv 与依赖 → 生成 `.env` → 数据库迁移 → 前端产物(仓库自带 `dist` 时直接使用,缺失时自动 npm 构建)→ 创建管理员 → 部署 systemd 服务与 nginx 站点。安装后访问 `http://<服务器IP>:8080`。

### 方式二:手动部署

```bash
# 后端(Python 3.10+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.in
cp ../.env.example .env      # 按需修改
python -m app.cli init-db
python -m app.cli create-admin admin
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端(可选;若已有 dist 产物可跳过)
cd ../frontend
npm ci && npm run build      # 产物输出到 frontend/dist,后端自动托管
```

生产环境建议再用 `deploy/gmod-mod-manager.service` + `deploy/nginx.conf` 托管。

### 最小配置示例(.env)

```ini
GMOD_SERVER_ROOT=/home/l4d2/Steam/steamapps/common/GarrysModDS
WORKSHOP_CACHE_ROOT=/home/l4d2/Steam/steamapps/workshop/content/4000
GMOD_ADDONS_ROOT=/home/l4d2/Steam/steamapps/common/GarrysModDS/garrysmod/addons
WORKSHOP_IDS_FILE=/home/l4d2/Steam/steamapps/common/GarrysModDS/garrysmod/cfg/srcds_workshop_ids.txt
TRASH_ROOT=/home/l4d2/Steam/gmm_trash
MANAGEMENT_MODE=observe      # 确认无误后再切换 native_ids / local_managed
READ_ONLY=true               # 只读总开关,观察期保持 true
```

## 配置说明

完整变量与中文注释见 [.env.example](.env.example)。要点:

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `GMOD_SERVER_ROOT` | 空 | 游戏服务器根目录 |
| `WORKSHOP_CACHE_ROOT` | 空 | Workshop 缓存(`content/4000`) |
| `GMOD_ADDONS_ROOT` | 空 | addons 目录(`local_managed` 部署目标) |
| `WORKSHOP_IDS_FILE` | 空 | `srcds_workshop_ids.txt` 路径(`native_ids` 模式) |
| `TRASH_ROOT` | 空 | 回收站目录(必须在游戏目录之外) |
| `MANAGEMENT_MODE` | `observe` | `observe / native_ids / local_managed` |
| `SERVER_CONTROL_MODE` | `manual` | `manual / systemd`;面板**从不**杀进程或自动重启 |
| `LOCAL_MANAGED_STRATEGY` | `gma_copy` | `gma_copy / folder_extract` |
| `READ_ONLY` | `true` | 全局只读开关(默认开启) |
| `PROTECTED_IDS` | 空 | 逗号分隔的受保护 Workshop ID,禁止删除 |
| `MAX_ACTION_IDS` | `200` | 单计划动作上限 |
| `PLAN_TTL_MINUTES` | `120` | 草稿过期时间 |
| `LOGIN_RATE_LIMIT` | `5/300` | 登录限速:300 秒内最多 5 次 |
| `SESSION_TTL_HOURS` | `72` | 会话有效期 |
| `STEAM_API_BASE` | Steam 官方 | 元数据 API,可反代 |
| `STEAM_PROXY` | 空(直连) | 访问 Steam API 与封面 CDN 的 HTTP 代理(国内服务器建议配置) |
| `STEAM_WEB_API_KEY` | 空 | 可选,用于作者昵称增强查询 |
| `AUTO_FETCH_PREVIEWS` | `true` | 扫描/元数据刷新后自动抓取封面到本地(`data/previews`) |
| `TRASH_RETENTION_DAYS` | `30` | 回收站自动永久删除天数 |
| `PUBLIC_ORIGIN` | `http://localhost:8080` | 对外访问地址(CORS 白名单用) |

## CLI 管理命令

在 `backend` 目录下执行:

```bash
python -m app.cli init-db                        # 初始化数据库(幂等)
python -m app.cli create-admin admin             # 创建管理员(密码强度≥10位含字母数字)
python -m app.cli create-admin admin -p 'S3cret!'# 非交互指定密码(仅脚本场景)
python -m app.cli list-admins                    # 列出用户
python -m app.cli reset-password admin           # 重置密码
python -m app.cli recover                        # 手动执行一次启动恢复(中断任务→恢复计划)
```

## API 概览

全部接口前缀 `/api`,JSON 通信;除 `auth/login` 外均需会话 Cookie(`session`)与 `X-CSRF-Token` 头。OpenAPI 描述:`/api/openapi.json`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录(限速) |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/mods` | Mod 列表(筛选/分页) |
| GET | `/api/mods/{wid}` | Mod 详情(含文件清单) |
| GET | `/api/mods/{wid}/preview` | 本地预览图(未落盘自动回退在线代理) |
| POST | `/api/mods/scan` | 发起扫描任务 |
| POST | `/api/mods/metadata/refresh` | 批量刷新元数据 |
| GET | `/api/plans` | 计划列表 |
| POST | `/api/plans` | 创建计划草稿 |
| GET | `/api/plans/active/current` | 当前活跃计划 |
| GET | `/api/plans/{id}` | 计划详情(diff/阻塞项/条目) |
| POST | `/api/plans/{id}/submit` | 提交排队 |
| POST | `/api/plans/{id}/apply` | 执行(仅 manual 审批流;排队时无需) |
| POST | `/api/plans/{id}/cancel` | 取消 |
| POST | `/api/plans/{id}/retry` | 重试失败项 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务详情 |
| GET | `/api/trash` | 回收站列表 |
| POST | `/api/trash/{id}/restore` | 还原 |
| POST | `/api/trash/{id}/purge` | 彻底删除 |
| POST | `/api/collections/snapshot` | 采集当前集合快照 |
| GET | `/api/system/status` | 系统状态(健康/路径配置) |
| GET | `/api/system/audit` | 审计日志(仅管理员) |
| GET | `/api/preview` | 预览图代理(防 SSRF) |

## 安全模型

- **认证**:Argon2id 密码哈希;HttpOnly + SameSite=Lax 会话 Cookie;登录限速(`5/300`)。
- **CSRF**:所有写请求要求 `X-CSRF-Token` 头,与会话绑定。
- **只读开关**:`READ_ONLY=true` 时一切写接口返回 `409 read_only_mode`。
- **路径安全**:所有文件操作限制在配置目录内(防穿越);回收站目录建议置于游戏目录之外。
- **SSRF 防护**:预览代理仅允许 Steam/SteamUserImages 白名单域名,逐跳重定向校验,解析后拒绝私网/环回地址,限响应大小(`PREVIEW_MAX_BYTES`)。
- **审计脱敏**:审计详情不记录密码/密钥;每条日志附 `request_id` 便于追踪。
- **进程安全**:`SERVER_CONTROL_MODE` 仅影响提示方式;代码中不存在 kill/重启服务器的调用。

## 目录结构

```
gmod-mod-manager/
├── backend/
│   ├── app/
│   │   ├── adapters/        # 三种管理模式适配器(loaders.py)
│   │   ├── api/             # 路由(routers/)与序列化(views.py)
│   │   ├── models/          # SQLAlchemy 实体
│   │   ├── schemas/         # Pydantic 请求模型
│   │   ├── security/        # Argon2id / 会话 / 限速
│   │   ├── services/        # GMA 解析/扫描/计划/回收站/预览/审计…
│   │   ├── workers/         # 进程内任务队列 + 启动恢复
│   │   ├── cli.py           # 管理命令
│   │   ├── config.py        # 全部环境变量(路径可配置)
│   │   ├── constants.py     # 五维状态枚举 + 中文映射
│   │   └── main.py          # FastAPI 入口(SPA 托管)
│   ├── migrations/          # Alembic
│   ├── tests/               # pytest(115 个用例)
│   └── requirements.in
├── frontend/                # Vue 3 + TS + Element Plus(中文)
│   └── src/{api,components,router,stores,utils,views}
├── deploy/
│   ├── gmod-mod-manager.service
│   ├── nginx.conf
│   └── install.sh
├── docs/
│   ├── architecture.md
│   └── gmod-loading-research.md
├── .env.example
├── THIRD_PARTY_NOTICES.md
└── acceptance-report.md
```

## 开发与测试

```bash
# 后端测试(115 个用例,Windows/Linux 均通过)
cd backend && python -m pytest

# 前端类型检查 + 构建
cd frontend && npm ci && npm run build

# 本地开发(vite 代理 /api → 127.0.0.1:8000)
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev        # http://localhost:5173
```

## 常见问题

**Q:面板会自动重启我的服务器吗?**
不会。代码中没有任何停止/重启进程的逻辑;需要重启的变更只会把 Mod 的 `requires_restart` 置为 1,并在界面上给出待重启清单,由管理员自行操作。

**Q:首次进入全是"路径未配置"?**
正常。所有游戏路径默认为空,填写 `.env` 后重启服务即可;未配置时面板仍可登录并查看系统状态。

**Q:(runtime_state)为什么一直显示"未知"?**
探针(`cfg/srcds_addons.txt`,srcds 自动生成的挂载缓存)不存在或不可读时,系统不会臆测加载状态——宁可 unknown 不出错报。srcds 至少启动过一次后探针出现,重新扫描即可看到 `loaded / not_loaded`。

**Q:删除错了怎么恢复?**
进入"回收站"页,找到条目点击"还原"。超过保留天数(`TRASH_RETENTION_DAYS`,默认 30 天)会被自动清理。

**Q:如何从只读切换到可写?**
设置 `READ_ONLY=false` 并重启服务;建议先在 `observe` 模式核对扫描结果,再切 `native_ids` 或 `local_managed`。

**Q:计划应用了一半进程挂了怎么办?**
重启服务时启动恢复会自动把中断任务标记并生成恢复计划;也可手动执行 `python -m app.cli recover`。计划详情页对失败项提供"重试失败项"按钮。

更多设计细节见 [docs/architecture.md](docs/architecture.md) 与 [docs/gmod-loading-research.md](docs/gmod-loading-research.md)。
