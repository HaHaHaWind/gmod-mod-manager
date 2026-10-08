# 架构文档(gmod-mod-manager)

本文面向维护者,说明系统的分层结构、关键数据流与设计决策。加载机制调研背景见 [gmod-loading-research.md](gmod-loading-research.md)。

## 1. 总体分层

```
┌────────────────────────────────────────────────────────┐
│  frontend/  Vue 3 + TS + Element Plus(中文 SPA)       │
│     api/(fetch 封装)  stores/(Pinia)  views/(9 页面) │
└──────────────┬─────────────────────────────────────────┘
               │ HTTPS(JSON + Cookie + CSRF 头)
┌──────────────▼─────────────────────────────────────────┐
│  backend/app                                           │
│  ├─ main.py        FastAPI 入口:lifespan/异常/SPA 托管 │
│  ├─ api/           路由层:鉴权依赖、参数校验、序列化   │
│  ├─ schemas/       Pydantic 请求模型                   │
│  ├─ services/      领域服务:扫描/计划/回收站/预览/审计 │
│  ├─ adapters/      管理模式适配器(唯一写盘出口)      │
│  ├─ workers/       进程内任务队列 + 启动恢复           │
│  ├─ models/        SQLAlchemy 实体(naive UTC 约定)   │
│  ├─ security/      Argon2id / 会话签名 / 登录限速      │
│  └─ config.py      全部环境变量,路径均可为空(隔离运行)│
└──────────────┬─────────────────────────────────────────┘
               │ 原子文件操作(受限路径内)
┌──────────────▼─────────────────────────────────────────┐
│  游戏服务器目录(只经适配器触碰)                        │
│  - workshop 缓存 .gma(读)                             │
│  - cfg/srcds_workshop_ids.txt(native_ids 写)          │
│  - garrysmod/addons/(local_managed 写,受管命名)      │
│  - 回收站目录(移动目标,建议在游戏目录外)             │
└────────────────────────────────────────────────────────┘
```

分层规则:

- **API 层不做文件操作**;所有落盘逻辑收敛在 `services/` 与 `adapters/`。
- **适配器是唯一的写盘出口**,三种模式各自决定"写什么、写在哪"。
- **worker 是唯一的重活执行者**,API 只入库并唤醒。

## 2. 五维状态模型

每个 Mod 一行记录,五个字段独立演进,禁止用单一布尔概括:

| 字段 | 写入者 | 说明 |
| --- | --- | --- |
| `inventory_state` | 扫描器 | 磁盘事实:`present / missing / extra / unknown` |
| `desired_state` | 用户计划 | 意图:`enabled / disabled / deleted` |
| `apply_state` | worker | 执行进度:`idle / pending / in_progress / applied / failed` |
| `runtime_state` | 探针 | `loaded / not_loaded / unknown`;探针=srcds 挂载缓存(`cfg/srcds_addons.txt` / `cache/srcds_addon_list_cache.txt`,srcds 自动生成),缺失/不可读/禁用时恒为 unknown |
| `requires_restart` | 适配器 | 变更需重启生效时置 1,应用成功后清 0 的逻辑见计划服务 |

设计动机:GMod 服务器"磁盘上有文件"≠"服务器会加载"≠"管理员想让它加载"。例如 `native_ids` 模式下删掉 ID 文件条目后,gma 仍在缓存里(`inventory=present`),但期望是 `deleted`,重启前 `runtime` 可能仍是 `loaded`(不可知,故 unknown)。把这些维度混成一个状态位必然产生错误结论。

## 3. 管理模式适配器

`adapters/loaders.py` 以多态分发(`get_adapter`),统一接口 + 各自实现:

### ObserveAdapter
一切写方法抛 `403 read_only`(或 `management_mode_observe`);只提供读侧逻辑。默认模式,安装即安全。

### NativeIdsAdapter
- 目标文件:`WORKSHOP_IDS_FILE`(即 `cfg/srcds_workshop_ids.txt`)。
- 解析为 **KeyValues 子集**:支持 `"workshop_ids" { "id" "1" "id" "2" }` 结构,兼容注释(C++ 风格 `//`)与多余空白;无法解析的行**原样保留**,不吞内容。
- 写入前把原始文件移入回收站(可还原);写入走临时文件 + `os.replace` 原子替换 + 目录 fsync。
- 启用 ID = 增加条目;禁用/删除 = 移除条目(gma 留在缓存,不删文件)。
- `SERVER_CONTROL_MODE` 只影响响应文案(manual:提示管理员;systemd:提示可用外部机制),适配器本身**从不**触碰进程。

### LocalManagedAdapter
- 受管命名:文件 `gmm_<ID>_v<N>.gma`、目录 `gmm_<ID>`(正则可识别,扫描时与外来文件区分)。
- `gma_copy`:复制缓存 gma → addons,版本号递增,旧版本进回收站。
- `folder_extract`:解包 gma 到 `gmm_<ID>/`,记录文件清单。
- 禁用/删除 = 把受管条目移入回收站;还原即放回原位。
- 全部经 `services/fsops.py` 的原子操作(临时名 + `os.replace` + fsync),中断后不留半成品。

## 4. 变更计划流水线

```
POST /api/plans          services/plans.create_plan
  │  逐项校验(存在性/受保护ID/动作上限 MAX_ACTION_IDS/只读开关)
  │  生成 diff(当前→期望)+ 阻塞项清单;状态 draft,记 base_revision
  ▼
POST /api/plans/{id}/submit
  │  乐观锁:base_revision 必须仍等于当前 revision,否则 409
  │  状态 queued,入库 apply_plan 任务并唤醒 worker
  ▼
worker: plans.run_apply_plan
  │  状态 applying;逐条目调用适配器
  │  单条失败:记 error,继续后续条目(部分成功语义)
  ▼
收尾:全部成功 → applied;有失败 → failed(可 retry)
     涉及条目 requires_restart=1;写审计
```

防呆设计:

- **TTL**:`PLAN_TTL_MINUTES` 到期后 worker 例行维护把 draft 置 expired,防止陈旧 diff 被误应用。
- **活跃计划互斥**:同一时刻至多一个非终态计划(`/api/plans/active/current`)。
- **失败重试**:`/retry` 只重提 failed 条目,不重跑已成功条目。
- **受保护 ID**:`PROTECTED_IDS` 命中时该项在创建阶段即被标为 blocker,不可提交。

## 5. 任务队列与启动恢复

`workers/runner.py`:

- SQLite 表 `tasks` 持久化;单进程内单 worker 线程顺序消费(设计约束:面板单实例写入,避免分布式锁复杂度)。
- 四类处理器:`scan / metadata_refresh / collection_snapshot / apply_plan`。
- API 入库(QUEUED)后 set 唤醒事件;worker 轮询间隔 1 秒兜底。
- **启动恢复**(lifespan + `cli recover`):上次运行遗留的 RUNNING 任务标记 INTERRUPTED(可见、不自动续跑),关联计划置 RECOVERY_REQUIRED;中断的文件操作由原子写保证"要么完成要么没开始",因此恢复策略是"管理员核对后显式重试",不做自动回滚。
- **例行维护**(每 60 秒):过期计划取消、回收站到期条目清理(`TRASH_RETENTION_DAYS`)。

## 6. 回收站机制

`services/trash.py` + `TRASH_ROOT`:

- 所有破坏性动作(删 ID 条目、移除受管副本、覆盖旧版本)先把原物 move 到回收站,记录原始路径与来源 Workshop ID。
- 还原(`restore`)按记录路径放回;目标已存在时返回冲突,不静默覆盖。
- 永久删除(`purge`)递归删除并留审计;到期自动 purge 由 worker 维护执行。
- 回收站目录**必须在游戏目录之外**(README 已提示),避免被游戏扫描到半成品。

## 7. 安全设计

| 机制 | 实现 |
| --- | --- |
| 密码哈希 | `security/password.py`,Argon2id(argon2-cffi);强度校验≥10 位含字母数字 |
| 会话 | 随机 token,`itsdangerous` 式签名(`SECRET_KEY`,缺省自动生成持久化到 `data/secret.key`,0600);HttpOnly + SameSite=Lax;TTL 默认 72h |
| 登录限速 | `security/ratelimit.py`,滑动窗口 `LOGIN_RATE_LIMIT=5/300`,按用户名+IP 双键 |
| CSRF | 会话签发时生成 token,写请求强制 `X-CSRF-Token` 匹配 |
| 只读开关 | `READ_ONLY=true`(默认)时写接口统一 `409 read_only_mode` |
| 路径穿越 | `services/paths.safe_child`:所有拼路径先 resolve 再断言在配置目录内 |
| SSRF | `services/preview.py`:域名白名单、逐跳重定向都重新校验、DNS 解析结果拒绝私网/环回/链路本地、响应上限 `PREVIEW_MAX_BYTES`、磁盘缓存 |
| 审计 | `services/audit.py`:统一入口记录,详情白名单字段,不含密码/密钥;每请求 `x-request-id` 贯穿日志与审计 |
| 错误结构 | 统一 `{code, message, request_id, details}`,异常处理器兜底,绝不回传堆栈 |

## 8. 数据模型(要点)

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `users` | username, password_hash, is_admin | Argon2id |
| `sessions` | token_hash, user_id, csrf_token, expires_at | 服务端会话 |
| `mods` | workshop_id(PK), 五维状态, load_sources(JSON), metadata_*, deploy_* | 一 ID 一行 |
| `mod_files` | workshop_id(FK), rel_path, size, note | local_managed 解包清单 |
| `change_plans` | kind, status, payload(JSON), diff(JSON), base_revision/revision, expires_at | 乐观锁 |
| `plan_items` | plan_id(FK), workshop_id, action, status, error, result(JSON) | 逐条目执行记录 |
| `tasks` | kind, status, progress/total, result(JSON), plan_id | 队列持久化 |
| `trash_entries` | kind, workshop_id, trash_path, origin_path, status, expires_at | 还原凭据 |
| `audit_logs` | username, action, outcome, target, detail(JSON 脱敏), ip, request_id | 只追加 |

时间约定:**库内一律 naive UTC**(SQLite DateTime 不保 tzinfo,混存 offset 会让排序与比较出错),序列化时统一补 `Z`,前端按 UTC 解析后本地化显示。

## 9. 前端结构

- `api/client.ts`:fetch 封装,自动带 Cookie 与 CSRF 头;`ApiRequestError`(携带 code)与 `UnauthorizedError`(触发跳登录)。
- `stores/auth.ts` / `stores/system.ts`:登录态与系统状态轮询(15 秒)。
- `router`:9 条路由,`beforeEach` 校验登录态,`redirect` 查询参数支持登录后回跳。
- 视图:总览 / Mod 库 / Mod 详情 / 计划列表 / 计划详情 / 任务中心 / 回收站 / 审计日志 / 登录。全部文案中文,状态列用中文标签 + Element Plus tag 颜色语义(success/warning/danger/info)。
- 构建产物由后端托管(`frontend/dist`),SPA 回退到 `index.html`;开发模式走 vite 代理 `/api → 127.0.0.1:8000`。

## 10. 关键设计决策(为什么这样做)

1. **绝不杀进程/自动重启**:需求硬约束 + 运维安全。`requires_restart` + 待重启清单把决定权留给管理员;systemd 控制模式下也只提示,不代操作。
2. **五维状态而非布尔**:见 §2,状态混淆是 Mod 管理事故的主因。
3. **计划必须过 diff 预览 + 乐观锁**:多人/多次编辑草稿时防止"看到的是 A,应用的是 B"。
4. **原子文件操作 + 受管命名**:断电/kill 后不留半成品;`gmm_` 前缀让扫描器能区分"我部署的"与"用户手放的"。
5. **单 worker 顺序队列**:面板是低频管理工具,吞吐不是目标;顺序执行让失败定位与恢复策略简单可靠。
6. **runtime_state 宁 unknown 不猜测**:探针(srcds 自动写出的挂载缓存)可读时才有 `loaded/not_loaded`;探针缺失、被禁用或不可读时如实说不知道,避免误导排障。
7. **路径全部可空**:开发机/新装环境没有游戏目录也能登录、看状态、跑测试(隔离运行),降低部署门槛。
