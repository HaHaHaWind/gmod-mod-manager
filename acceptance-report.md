# 验收报告(gmod-mod-manager)

- 项目:GMod 服务端 Workshop Mod 管理面板
- 验收日期:2026-10-08
- 验收环境:Windows 11 开发机(Python 3.10.11 / Node 22);目标部署环境 Linux + systemd + nginx(脚本与单元文件已交付,见"已知限制")

---

## 1. 结论

**通过。** 全部 81 个后端自动化测试通过;前端类型检查与生产构建通过;数据库迁移链(upgrade → downgrade → upgrade)验证通过;CLI 工具验证通过;需求文档要求的全套交付物齐备。

## 2. 交付物清单

| 交付物 | 位置 | 状态 |
| --- | --- | --- |
| 后端源码(FastAPI + SQLAlchemy 2 + Alembic) | `backend/` | ✅ |
| 前端源码(Vue 3 + TS + Element Plus,中文) | `frontend/` | ✅ |
| 前端生产构建产物(后端自动托管) | `frontend/dist/` | ✅ |
| 数据库迁移 | `backend/migrations/versions/9d2393a22114_initial_schema.py` | ✅ |
| 自动化测试 | `backend/tests/`(7 个模块,81 用例) | ✅ 81/81 通过 |
| 环境变量样例(全中文注释) | `.env.example` | ✅ |
| systemd 服务单元 | `deploy/gmod-mod-manager.service` | ✅ |
| nginx 反向代理配置 | `deploy/nginx.conf` | ✅ |
| 一键安装脚本 | `deploy/install.sh` | ✅ |
| 中文 README | `README.md` | ✅ |
| 架构文档 | `docs/architecture.md` | ✅ |
| GMod 加载机制调研 | `docs/gmod-loading-research.md` | ✅ |
| 第三方组件声明 | `THIRD_PARTY_NOTICES.md` | ✅ |
| 验收报告(本文件) | `acceptance-report.md` | ✅ |

## 3. 自动化测试结果

执行命令与输出:

```
$ cd backend && python -m pytest
........................................................................ [ 88%]
.........                                                                [100%]
81 passed, 1 warning in 4.25s
```

(唯一 warning 来自 starlette TestClient 的上游弃用提示,与业务代码无关。)

### 用例分布

| 测试模块 | 覆盖范围 |
| --- | --- |
| `tests/test_auth.py` | 登录/登出/会话、Argon2id、CSRF 校验、登录限速、只读开关、权限(admin/普通用户) |
| `tests/test_gma_scan.py` | GMA 二进制解析(标题/作者/标签/文件清单)、缓存扫描、`srcds_workshop_ids.txt` KeyValues 子集解析与写回、inventory_state 判定 |
| `tests/test_adapters.py` | 三种管理模式适配器:observe 拒写、native_ids 原子写回+注释保留、local_managed gma_copy/folder_extract、受管命名、路径穿越拒绝 |
| `tests/test_plans.py` | 计划创建(校验/受保护 ID/动作上限)、diff 预览、乐观锁冲突、submit/apply/cancel/retry、TTL 过期、失败项重试、requires_restart 置位 |
| `tests/test_recovery.py` | 中断任务标记 INTERRUPTED、计划进入 RECOVERY_REQUIRED、恢复计划生成、原子操作无半成品 |
| `tests/test_trash.py` | 移入回收站、还原(含目标冲突)、彻底删除、到期清理 |
| `tests/test_preview.py` | SSRF 防护:域名白名单、私网/环回地址拒绝、重定向逐跳校验、响应大小上限、磁盘缓存 |

## 4. 构建与运行验证

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 后端测试 | `python -m pytest` | ✅ 81 passed |
| 迁移升级 | `alembic upgrade head` | ✅ `9d2393a22114` initial schema |
| 迁移回滚 | `alembic downgrade base` | ✅ |
| 迁移再升级 | `alembic upgrade head` | ✅(与首次结果一致) |
| CLI 初始化 | `python -m app.cli init-db` | ✅ 幂等,路径正确 |
| CLI 用户列表 | `python -m app.cli list-admins` | ✅ |
| 前端类型检查 + 构建 | `npm run build`(vue-tsc -b && vite build) | ✅ 0 错误 |
| 构建产物 | `frontend/dist/index.html` + `assets/*` | ✅ 10 个视图按路由分包 |

说明:验证过程中发现并修复了一个缺陷——`migrations/env.py` 直连数据库前未确保 `DATA_DIR` 存在(父目录缺失时 SQLite 报 `unable to open database file`);已修复为迁移前调用 `ensure_data_dir()`(与 `app.db.get_engine()` 行为一致),修复后迁移链验证通过。

## 5. 需求覆盖矩阵

对照需求文档的关键条款:

| 需求 | 实现 | 验证 |
| --- | --- | --- |
| 路径全部可配置,未配置可隔离运行 | `config.py` 五个游戏路径默认空串,派生属性 `Path \| None` | ✅ 空配置下 81 测试通过;界面显示"路径未配置" |
| 三种管理模式 observe/native_ids/local_managed | `adapters/loaders.py` 多态分发,启动校验非法值 | ✅ test_adapters |
| local_managed 双策略 gma_copy/folder_extract | 受管命名 `gmm_<ID>_v<N>.gma` / `gmm_<ID>/` | ✅ test_adapters |
| 五维状态模型(禁单一布尔) | `constants.py` 枚举 + `mods` 表五字段独立 | ✅ 全链路(API/UI);UI 中文标签 |
| 无探针时 runtime_state 恒 unknown | 探针未接入,写入端只产 unknown | ✅ 设计约束 + 代码审查 |
| 绝不杀进程/自动重启 | 代码库无进程终止调用;`SERVER_CONTROL_MODE` 仅影响提示 | ✅ 代码审查(全库无 kill/restart 系统调用) |
| 变更计划:草稿→diff→提交→应用,失败可重试 | `services/plans.py` + worker;TTL/乐观锁/阻塞项 | ✅ test_plans |
| 回收站 + 到期清理 | `services/trash.py` + worker 例行维护 | ✅ test_trash |
| 启动恢复(中断任务可见、显式重试) | `workers/runner.py` startup_recovery + `cli recover` | ✅ test_recovery |
| Argon2id + HttpOnly Cookie + CSRF | `security/password.py` / `sessions.py` | ✅ test_auth |
| 登录限速 5/300 | `security/ratelimit.py` 滑动窗口 | ✅ test_auth |
| 防路径穿越 | `services/paths.safe_child` resolve 后断言 | ✅ test_adapters |
| 防预览 SSRF(白名单/公网校验/限大小) | `services/preview.py` | ✅ test_preview |
| 审计脱敏 + request_id | `services/audit.py` 白名单字段;中间件注入 x-request-id | ✅ test_auth + 代码审查 |
| 只读总开关默认开启 | `READ_ONLY=true` 默认;写接口 409 | ✅ test_auth |
| 24 个 REST 端点 + OpenAPI | `api/routers/*` + `/api/openapi.json` | ✅ 端点清点(docs/UI 对齐) |
| 中文 Web 界面 | Vue 3 + Element Plus 全中文;9 个视图 | ✅ 构建通过 + 文案审查 |
| systemd + nginx 交付 | `deploy/` 两个文件 + install.sh | ✅ 已交付(见已知限制第 1 条) |
| 文档(README/.env.example/THIRD_PARTY/验收) | 见交付物清单 | ✅ |

## 6. 已知限制

1. **Linux 部署脚本未在本机执行**:`install.sh`、systemd 单元与 nginx 配置按目标环境(Debian 系 + `/opt/gmod-mod-manager`)编写;开发机为 Windows,建议首次上机时按 README"手动部署"步骤核对一遍路径。
2. **runtime_state 恒为 unknown**:未接入运行时探针(日志解析/RCON 属后续增强),这是设计取舍而非缺陷——宁可 unknown 不出错误结论。
3. **单实例部署**:任务队列为进程内单 worker 顺序消费,不支持多副本水平扩展(面板属低频管理工具,符合预期)。
4. **Steam Web API 可选**:未配置 `STEAM_WEB_API_KEY` 时仅使用 GMA 内嵌元数据;受限/隐藏创意工坊条目会显示为 metadata_failed,可通过界面查看原因。
5. **测试基座**:81 个用例覆盖服务层与 API 层(经 TestClient);未包含浏览器端 E2E(前端以类型检查 + 构建验证)。

## 7. 上线核对单(建议)

- [ ] `cp .env.example .env` 并核对 5 个游戏路径与 `TRASH_ROOT`(在游戏目录外)
- [ ] `python -m app.cli create-admin <管理员名>` 创建初始管理员
- [ ] 保持 `MANAGEMENT_MODE=observe`、`READ_ONLY=true`,执行一次扫描核对 Mod 清单
- [ ] 核对无误后切 `READ_ONLY=false`,按需切 `native_ids` / `local_managed`
- [ ] 配置 systemd 开机自启:`systemctl enable --now gmod-mod-manager`
- [ ] 在 nginx 层叠加 TLS(建议 certbot)与访问控制
