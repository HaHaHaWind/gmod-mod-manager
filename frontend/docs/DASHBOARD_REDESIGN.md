# GMod 模组管理器 · 第二轮改版说明：仪表盘化与暗色主题

> 续接《[FRONTEND_REDESIGN.md](../../FRONTEND_REDESIGN.md)》(第一轮产品化改版)。
> 触发原因:用户希望获得 [MCSManager](https://github.com/MCSManager/MCSManager) 式的**完整仪表盘观感**。
> 范围:仅修改 `frontend/`;后端零改动;未新增任何依赖。
> 验证:`npm run build`(vue-tsc + vite)通过。
>
> **续篇**:本轮之后追加"组件质感移植 + 动效/进度条"视觉增强,详见 [MOTION_AND_TEXTURE.md](./MOTION_AND_TEXTURE.md)。

---

## 一、背景与决策

第一轮改版依据需求文档把面板做成了"资源管理器式模组工具",并明确了两条原则:**默认进入模组库**、"不要做成服务器监控大屏"。用户在对比 MCSManager 后提出想要"类似的完整仪表盘观感",经确认本轮推翻上述两条原则,保留其余工程约束。

### 用户确认的三个决策

| 决策点 | 结论 | 说明 |
| --- | --- | --- |
| 实现路线 | **自建仿 MCSM 观感** | 保持 reka-ui + Tailwind 4 技术栈,重做视觉与布局;不引入 ant-design-vue,避免全组件重写 |
| 默认首页 | **仪表盘优先** | 新建 `/dashboard` 作为产品首页,根路径与登录后默认落此;模组库退为一级入口之一 |
| 主题模式 | **亮暗双主题** | token 双套变量,顶栏一键切换、记忆偏好、首次跟随系统 |

### 数据真实性约束(延续第一轮)

MCSManager 仪表盘的核心是 CPU/内存实时监控图表,但本后端**不提供**这类数据源。本轮仪表盘全部使用真实接口数据(`/system/status` counts、`/api/mods` 计数、`/api/plans/active/current`、`/api/tasks`),不编造监控指标、不加虚假图表。

---

## 二、架构层面修改

### 2.1 结论

- **路由**:默认首页从模组库改为仪表盘;`/dashboard` 由"兼容重定向"变为真实页面;原服务状态页独立为 `SystemStatusView.vue`(`DashboardView.vue` 删除)。
- **新增模块**:`views/DashboardHome.vue`(仪表盘首页)、`composables/useTheme.ts`(主题状态)。
- **技术栈**:不变,无新依赖。

### 2.2 路由对照(`src/router/index.ts`)

| 路径 | 第一轮 | 本轮 |
| --- | --- | --- |
| `/` | 重定向到 `mods` | **重定向到 `dashboard`** |
| `/dashboard` | 重定向到 `/system`(兼容跳转) | **仪表盘首页(新页面)** |
| `/system` | 服务状态(组件 `DashboardView.vue`) | 服务状态(组件改名 `SystemStatusView.vue`,内容不变) |
| `/:pathMatch(.*)*` | 回落到 `mods` | 回落到 `dashboard` |

其余路由(mods / plans / tasks / trash / audit)与守卫逻辑不变。

---

## 三、亮暗双主题实现(`styles.css` + `useTheme.ts`)

### 3.1 token 双套化

- 颜色 token 从 `@theme` 静态值改为 **`@theme inline` 引用 CSS 变量**,变量在 `:root`(亮色)与 `html.dark`(暗色)中各定义一套;切换 `html.dark` class 即全局换肤,**所有页面组件零改动**。
- 新增 `@custom-variant dark (&:where(.dark, .dark *))`,使 `dark:` 前缀基于 class 生效(备用)。
- 分层阴影、背景光晕、骨架屏微光同步变量化:`--c-shadow-card/-pop`、`--glow-1/-2`、`--shimmer`(暗色下阴影更重、微光更弱)。

### 3.2 暗色取值(蓝灰基调)

| Token | 亮色 | 暗色 |
| --- | --- | --- |
| canvas / surface / surface-muted / surface-sunken | `#F6F7F9` / `#FFF` / `#F1F3F6` / `#E9ECF1` | `#0E1116` / `#151A21` / `#1C222B` / `#232B36` |
| line / line-strong | `#E5E8EE` / `#D2D8E2` | `#262E3A` / `#364152` |
| ink / ink-2 / ink-3 / ink-4 | `#20242C` / `#454E5C` / `#626B78` / `#99A2B0` | `#E9EDF3` / `#C6CDD8` / `#8D97A6` / `#5C6674` |
| accent(soft / line) | `#3B6EF5`(`#EDF2FE` / `#CAD9FC`) | `#5B8AF7`(`#1A2740` / `#2C3F63`) |
| ok / warn / danger(各带 soft) | `#15803D` / `#B45309` / `#DC2626` | `#34D399` / `#FBBF24` / `#F87171` |

### 3.3 切换机制(`composables/useTheme.ts`)

- 模块级单例;`theme` ref + `setTheme()` + `toggleTheme()`。
- 偏好存 `localStorage['gmod_mm_theme']`;首次无偏好时跟随 `prefers-color-scheme`。
- `apply()` 同步切换 `html.dark` class 与 `color-scheme`(滚动条、原生控件随动)。

### 3.4 防首屏闪烁(`index.html`)

- `<head>` 内联脚本:加载前读取偏好并预置 `html.dark`,避免暗色用户看到亮色闪变。
- 页面标题同步改为"**GMod 模组管理器**"(原"GMod Workshop Mod 管理面板")。

---

## 四、布局改造(`layouts/AppLayout.vue` 重写)

### 4.1 可折叠侧栏

- 宽度 **224px ↔ 68px** 图标模式;状态存 `localStorage['gmod_mm_sidebar']`;仅影响 lg+ 布局,移动端抽屉始终全宽。
- 折叠态:导航项只显示图标(`title` 悬停提示);"操作记录"组变为**弹出子菜单**(DropdownMenu,含变更记录/后台任务),有活跃计划时图标右上角显示琥珀小圆点。
- 底部:展开时显示"服务概要"卡(数据库/后台进程,点击进服务状态页)+ 收起按钮;折叠时仅显示展开按钮。

### 4.2 顶栏

- 原"页面标题"改为**面包屑**:`仪表盘 / 父级上下文 / 当前页`(模组详情父级为"模组库",变更详情父级为"变更记录",末级加粗)。
- 右侧保留:只读/管理模式/待重启/活跃计划徽标;新增**主题切换按钮**(Sun/Moon 随状态);账户菜单(头像+退出)不变。

### 4.3 导航结构

主入口变为:**仪表盘**(LayoutDashboard,第一位)、模组库、回收站;折叠分组"操作记录"(变更记录/后台任务);次级"系统"(服务状态、审计日志[adminOnly])。

---

## 五、仪表盘首页(`views/DashboardHome.vue`,新建)

页面结构(自上而下):

1. **欢迎横幅**:accent 渐变大卡 + 白色装饰圆;时段问候(早上好/中午好/下午好/晚上好/夜深了)+ 用户名;摘要句(模组总数、待重启数);右侧"快速扫描 / 全量扫描(校验文件)"快捷按钮(只读时禁用,创建后跳转后台任务)。
2. **概览统计**:4 张 StatCard——模组总数(总数)、待重启模组(warning)、排队任务(neutral)、回收站条目(danger),均来自 `system.status.counts`。
3. **模组状态分布**(占 2/3 宽):并行发起 3 个 `apiModList({ inventory_state: x, page_size: 1 })` 请求仅取 `total`(present/missing/invalid),渲染**堆叠比例条** + 图例(含"回收站中 N 个"独立计数);加载中显示骨架;无数据时 EmptyState 引导执行首次扫描。
4. **服务健康**(1/3 宽):数据库/后台进程状态点、只读开启提示、缺路径警告;链接到 `/system`。
5. **最近后台任务**(2/3 宽):最近 6 条,任务类型中文名 + 时间 + 状态徽标;running 且有总数显示进度条、总数未知显示不确定进度;链接到 `/tasks`。
6. **进行中的变更**(1/3 宽):活跃计划的 planTitle + 徽标 + 变更项数 + "继续处理";无计划时 EmptyState 引导去模组库。

数据策略:`onMounted` 首刷(system.refresh + 活跃计划 + 任务列表 + 状态分布,非关键数据静默失败),`usePolling` 10s 自动刷新。

---

## 六、服务状态页(`views/SystemStatusView.vue`)

原 `DashboardView.vue` 内容原样迁移(标题区、运行状况、待重启与缺路径警告条、配置与统计、维护操作、进行中的变更计划),仅组件文件名与路由指向变化,逻辑未改动。

---

## 七、暗色硬编码修复清单

`bg-ink` 在暗色下会翻转为近白色,凡是"以深色为底 + 白字"的用途全部改为**固定深色**(亮暗观感一致):

| 文件 | 位置 | 原值 | 新值 |
| --- | --- | --- | --- |
| `layouts/AppLayout.vue` | 移动端抽屉遮罩 | `bg-ink/35` | `bg-black/45` |
| `components/ui/Dialog.vue` | 模态遮罩 | `bg-ink/30` | `bg-black/45` |
| `components/ui/Tooltip.vue` | 提示气泡 | `bg-ink` | `bg-[#1B232E]` |
| `views/LoginView.vue` | 左侧品牌面板 | `bg-ink` | `bg-[#20242C]` |
| `components/biz/ModCard.vue` | 封面分类角标 | `bg-ink/55` | `bg-black/55` |
| `components/biz/ModCard.vue` | 多选按钮未选中态 | `bg-ink/35` | `bg-black/45` |

其余 `text-white` 均位于 accent/ok/danger 色底或白装饰上,与主题无关,已排查确认。

---

## 八、本地偏好键汇总

| 键 | 内容 | 写入位置 |
| --- | --- | --- |
| `gmod_mm_theme` | `light` / `dark` | 顶栏主题切换 |
| `gmod_mm_sidebar` | 侧栏折叠状态(`1`=折叠) | 侧栏折叠按钮 |
| `gmod_mm_scroll` | 模组库滚动位置(第一轮) | 详情页返回时恢复 |

密码、会话、CSRF token 均不落本地持久化(约束不变)。

---

## 九、保留与未改动项

- 模组库、模组详情、变更记录/详情、后台任务、回收站、审计日志、登录页的**布局与交互全部不动**,自动继承新主题。
- 会话/CSRF/路由守卫/只读/权限/保护条目等工程边界不变;接口层不变;后端不变。
- 不新增 MCSM 式的实时监控图表、终端、设计模式卡片自定义等后端不支持或本轮未确认的能力。

## 十、验证结果

- ✅ `npm run build`(vue-tsc + vite)通过;期间修复 1 处遗漏(`pageTitle` 计算属性缺失导致的 TS2304)。
- ✅ 暗色硬编码全量排查(`bg-ink` / `text-white` / `bg-white` / 纯色 rgb),确认无反转问题残留。
- ⚠️ **浏览器交互验证未执行**(环境无浏览器),建议 `npm run dev` 后人工核对:
  1. 暗色模式下各页面观感(尤其登录页、Tooltip、模态遮罩、封面角标);
  2. 主题切换 + 刷新后记忆是否生效,首次访问是否跟随系统;
  3. 侧栏折叠/展开、折叠态"操作记录"弹出菜单;
  4. 仪表盘各卡片数据与空态(无模组 / 无活跃计划 / 无任务);
  5. 手机宽度下抽屉与底部导航。

## 十一、启动方式

```bash
cd frontend
npm install   # 如未安装依赖
npm run dev   # 开发预览
npm run build # 生产构建(输出 dist/)
```
