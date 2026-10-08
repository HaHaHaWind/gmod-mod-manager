# 第三方开源组件声明(THIRD_PARTY NOTICES)

本项目(gmod-mod-manager)使用了以下开源组件,感谢原作者与社区。各组件版权归其各自所有者所有,本项目按其许可证要求在此声明。

## 后端 Python 依赖

来源:`backend/requirements.in`

| 组件 | 版本范围 | 许可证 | 用途 | 主页 |
| --- | --- | --- | --- | --- |
| FastAPI | >=0.115,<1 | MIT | Web 框架 | https://github.com/fastapi/fastapi |
| Uvicorn | >=0.30,<1 | BSD-3-Clause | ASGI 服务器 | https://github.com/encode/uvicorn |
| Pydantic | >=2.7,<3 | MIT | 数据校验 | https://github.com/pydantic/pydantic |
| pydantic-settings | >=2.2,<3 | MIT | 环境变量配置 | https://github.com/pydantic/pydantic-settings |
| SQLAlchemy | >=2.0,<3 | MIT | ORM / 数据库 | https://github.com/sqlalchemy/sqlalchemy |
| Alembic | >=1.13,<2 | MIT | 数据库迁移 | https://github.com/sqlalchemy/alembic |
| argon2-cffi | >=23.1,<26 | MIT | Argon2id 密码哈希 | https://github.com/hynek/argon2-cffi |
| HTTPX | >=0.27,<1 | BSD-3-Clause | HTTP 客户端(Steam 元数据/预览代理) | https://github.com/encode/httpx |
| filelock | >=3.13,<4 | Unlicense(公共领域) | 跨平台文件锁 | https://github.com/tox-dev/py-filelock |

## 前端 Node 依赖

来源:`frontend/package.json`(直接依赖;构建产物同时包含其传递依赖,如 dayjs、lodash、@vue/*、@babel/* 等,均为 MIT 或等效宽松许可证)

### 运行时依赖

| 组件 | 版本范围 | 许可证 | 用途 | 主页 |
| --- | --- | --- | --- | --- |
| Vue | ^3.4 | MIT | 前端框架 | https://github.com/vuejs/core |
| Vue Router | ^4.4 | MIT | 路由 | https://github.com/vuejs/router |
| Pinia | ^2.1 | MIT | 状态管理 | https://github.com/vuejs/pinia |
| Element Plus | ^2.7 | MIT | UI 组件库 | https://github.com/element-plus/element-plus |
| @element-plus/icons-vue | ^2.3 | MIT | 图标 | https://github.com/element-plus/element-plus-icons |

### 开发依赖

| 组件 | 版本范围 | 许可证 | 用途 | 主页 |
| --- | --- | --- | --- | --- |
| TypeScript | ~5.4 | Apache-2.0 | 类型系统 | https://github.com/microsoft/TypeScript |
| Vite | ^5.3 | MIT | 构建工具 | https://github.com/vitejs/vite |
| @vitejs/plugin-vue | ^5.1 | MIT | Vue 官方 Vite 插件 | https://github.com/vitejs/vite-plugin-vue |
| vue-tsc | ^2.0 | MIT | Vue 类型检查 | https://github.com/vuejs/language-tools |
| @types/node | ^26 | MIT | Node 类型声明 | https://github.com/DefinitelyTyped/DefinitelyTyped |

## 运行环境说明

- **Python**:PSF 许可证(https://docs.python.org/3/license.html)
- **Node.js / npm**:MIT 及 Apache-2.0 组合(https://github.com/nodejs/node)
- **SQLite**:Public Domain(https://www.sqlite.org/copyright.html)
- **nginx**:BSD-2-Clause(https://nginx.org/LICENSE)

## 许可证全文

上述 MIT / BSD / Apache-2.0 许可证全文可在各组件源码仓库或发行包内的 `LICENSE` / `LICENSE.txt` 文件中查阅(本项目 `frontend/node_modules/<组件>/LICENSE*` 目录下保留了对应文件)。

## 项目自身代码

本项目自身代码(backend/、frontend/src/、deploy/、docs/)由用户委托编写,不附带额外开源许可证约束;如需对外发布,请自行选择许可证并保留本声明。
