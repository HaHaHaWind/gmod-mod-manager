# GMod 模组管理器 · 视觉质感与动效增强说明

> 续接《[DASHBOARD_REDESIGN.md](./DASHBOARD_REDESIGN.md)》(第二轮仪表盘化与暗色主题)。
> 本轮包含两个子阶段,均只动**视觉与动效层**,页面布局、交互逻辑、接口零改动:
> 1. **组件质感移植**——对齐 MCSManager(ant-design-vue)的卡片阴影、圆角、按钮/输入框材质;
> 2. **动效与加载反馈**——路由切换过渡、全局加载进度条、面包屑微动效。
> 验证:每轮 `npm run build`(vue-tsc + vite)通过。

---

## 一、背景与目标

用户先后提出两个诉求:

| 诉求 | 期望效果 | 对标 |
| --- | --- | --- |
| "想要类似 MCSManager 的组件质感" | 卡片有真实的阴影层次与 hover 反馈,不是扁平贴边 | MCSManager 的 `.global-card-container-shadow` 体系 |
| "加上动画、切换页面/加载的等待动画,现在的切换过于生硬" | 页面切换有进出过渡、路由等待有进度反馈 | 现代控制台通用的 out-in 页面过渡 + NProgress 式进度条 |

**关键实现策略**:逐条对照 MCSManager 源码(`frontend/src/assets/base.scss` 等)提取参数,移植到本项目自有的 Tailwind 4 token 体系,**不引入 ant-design-vue、不引入 nprogress**,全部自建。

---

## 二、组件质感改造(第一阶段)

### 2.1 卡片阴影体系(核心)

MCSM 卡片质感的本质是"**静止态贴地短阴影 + hover 阴影抬升**",边框在亮色下完全透明、暗色下极淡。已作为全局 token 落地(`styles.css`):

| Token | 亮色 | 暗色 | 用途 |
| --- | --- | --- | --- |
| `--c-shadow-card` | `0 1px 2px 1px rgb(0 0 0/0.12)` | 同式 `0.35` 透明度 | 卡片静止态贴地阴影 |
| `--c-shadow-card-hover` | `0 4px 8px 0 rgb(0 0 0/0.12)` + 贴地基线 | 同式 `0.5`/`0.35` | hover 抬升扩散阴影 |
| `--c-card-border` | `transparent` | `rgb(196 196 196/0.25)` | 卡片边框(亮色无框、暗色淡框) |

过渡规格(MCSM 同款):`transition-[box-shadow] duration-[400ms] ease-in-out`——**卡片本体不位移,只有阴影动**,时长 0.4s。

应用组件:

- `Panel.vue` —— 所有面板卡片(替换原"边框变色 + 上浮位移"方案)
- `StatCard.vue` —— 仪表盘统计卡(图标底座同步收敛为 7px 圆角)
- `ModCard.vue` —— 模组卡片(**去掉 hover -translate-y-1 位移**,保留选中态 accent 描边 + ring)

### 2.2 圆角全局收敛

通过覆盖 Tailwind 4 的 radius token 一次性生效,未逐文件修改:

| Token | 原默认 | 现值 | 对齐对象 |
| --- | --- | --- | --- |
| `--radius-md` | 6px | 6px | 控件 |
| `--radius-lg` | 8px | 7px | 输入框/下拉 |
| `--radius-xl` | 12px | **8px** | 卡片、按钮(antd 6-8px 级) |
| `--radius-2xl` | 16px | **10px** | 模态、欢迎横幅 |

效果:全站所有 `rounded-xl` 等工具类自动收敛到 MCSM 的小圆角观感。

### 2.3 按钮(`Button.vue`)

| 项 | 改造 |
| --- | --- |
| 过渡时长 | 150ms → **300ms**(`transition-all`) |
| 按下反馈 | `active:scale-[0.96]`(更明显的下压) |
| primary hover | 新增蓝色光晕 `hover:shadow-[0_4px_14px_rgb(59_110_245/0.4)]` |
| 圆角 | 随 radius token 自动 8px |

### 2.4 输入框(`Input.vue`)

- focus 样式改为 **antd 式光环**:边框变强调色 + `ring-[3px] ring-accent/15`(低透明度大光环,替代原 2px 35% 重描边)
- 过渡 `transition-[border-color,box-shadow] duration-300`,光环出现柔和

### 2.5 模态遮罩(`Dialog.vue`)

对齐 MCSM 遮罩规格:`backdrop-blur-[4px] backdrop-saturate-[1.1]`(原仅 blur 3px)。

### 2.6 模组封面动效(`ModCard.vue`)

hover 时封面图使用 MCSM 的**回弹过冲曲线**:

```text
transition-[transform,filter] duration-[400ms] ease-spring
group-hover:rotate-1 group-hover:scale-[1.06] group-hover:brightness-110
```

其中 `--c-spring: cubic-bezier(0.175, 0.885, 0.32, 1.275)`(extract 自 MCSM `.package-image`),放大同时轻微旋转与提亮,松开后回弹。

---

## 三、动效与加载反馈(第二阶段)

### 3.1 路由切换过渡(核心)

`AppLayout.vue` 的 RouterView 由单向入场动画改为**完整 out-in 过渡**:

```vue
<RouterView v-slot="{ Component }">
  <Transition name="page" mode="out-in">
    <component :is="Component" :key="route.fullPath" />
  </Transition>
</RouterView>
```

CSS 定义(`styles.css`):

| 阶段 | 时长 | 曲线 | 变换 |
| --- | --- | --- | --- |
| 出场(page-leave) | 160ms | `ease-in` | `opacity→0` + 上移 6px |
| 入场(page-enter) | 280ms | `cubic-bezier(0.16,1,0.3,1)` | `opacity 0→1` + 下 10px/0.996 缩放归位 |

设计意图:**出场快、入场慢**,总切换约 440ms——先给"离开"一个干脆的确认,再让新页面从容落位,消除"瞬间替换"的生硬感。

### 3.2 登录页 ↔ 主布局切换(`App.vue`)

顶层 RouterView 加 `Transition name="fade" mode="out-in"`(220ms 交叉淡切),key 设计为 `route.name === 'login' ? 'login' : 'app'`——只在登录页与主布局之间切换时触发,**布局内部导航不会重复触发外层过渡**(由 3.1 的 page 过渡接管)。

### 3.3 面包屑微动效(`AppLayout.vue`)

面包屑 `<nav>` 包 `Transition name="crumb" mode="out-in"` 并 keyed by `route.name`:路由变化时标题淡出(120ms)再上滑淡入(200ms),消除顶栏文字瞬间跳变。

### 3.4 全局路由加载进度条(`RouteProgress.vue`,新建)

NProgress 风格顶部进度条,**零依赖自建**。挂载于 `App.vue`,常驻不卸载。

**时序设计**(覆盖两类等待:懒加载页面 chunk 下载、路由守卫中的会话探测请求):

```text
start() ── rAF ─→ 30% ── 320ms ─→ 55% ── 900ms ─→ 75% ── 1800ms ─→ 88%
                                                              afterEach/onError
                                                                  ↓
                                                            100%(240ms 冲顶) ── 360ms ─→ 淡出
```

- 推进条宽度的过渡:常规阶段 `620ms cubic-bezier(0.16,1,0.3,1)`(前快后慢的爬升感),完成阶段 `240ms ease-out`(干脆冲顶)
- 淡出:容器 opacity 280ms,延迟 100ms,避免进度条"闪现即消失"
- 样式:顶部 3px 强调色圆头条 + 蓝色光晕阴影;`pointer-events-none` 不拦截交互;`z-[100]` 置于所有浮层之上
- 接入点:`router.beforeEach → start()`、`router.afterEach → done()`、`router.onError → done()`(导航失败也正确收尾)
- 防抖设计:`running` 标志防重入;每次导航重置爬升计时器;组件卸载清理全部计时器

无障碍:`role="progressbar"`,`aria-hidden` 随可见状态切换。

### 3.5 数据骨架屏(已有,未改动)

模组卡片骨架(`ModGrid.vue`)、详情页/表格骨架(各视图 `Skeleton` 组件)此前已就位,本轮未重复建设;进度条只负责"路由级"等待,骨架负责"数据级"等待,两层互补。

---

## 四、动效 token 与 CSS 类清单

### 4.1 全局动画 token(`styles.css`)

| Token | 值 | 说明 |
| --- | --- | --- |
| `--animate-ui-in` | 260ms `cubic-bezier(0.645,0.045,0.355,1)` | 浮层入场(antd 标准曲线) |
| `--animate-ui-out` | 140ms `ease-in` | 浮层出场 |
| `--animate-rise` | 320ms 同上曲线 | 卡片级入场(面板内元素) |
| `--ease-spring` | `cubic-bezier(0.175,0.885,0.32,1.275)` | 回弹过冲(封面 hover) |

### 4.2 过渡 CSS 类

| 类名 | 触发处 | 规格 |
| --- | --- | --- |
| `.page-*` | AppLayout RouterView | 3.1 所述 |
| `.fade-*` | App.vue 顶层 | 220ms 交叉淡切 |
| `.crumb-*` | 面包屑 nav | 200/120ms 上滑淡切 |

### 4.3 无障碍

`styles.css` 既有全局规则 `@media (prefers-reduced-motion: reduce)` 将所有 transition/animation 压缩到 0.01ms,上述全部动效自动对该偏好失效,无需逐个处理。

---

## 五、修改文件清单

| 文件 | 类型 | 内容 |
| --- | --- | --- |
| `src/styles.css` | 改 | 阴影/边框/回弹曲线 token、radius 覆盖、动画时长、page/fade/crumb 过渡类 |
| `src/components/ui/RouteProgress.vue` | **新增** | 全局路由进度条 |
| `src/components/ui/Panel.vue` | 改 | 贴地阴影 + hover 抬升 + 卡片边框 token |
| `src/components/biz/StatCard.vue` | 改 | 同上 + 图标底座圆角 |
| `src/components/biz/ModCard.vue` | 改 | 去位移改阴影、封面回弹动效 |
| `src/components/ui/Button.vue` | 改 | 300ms 过渡、下压反馈、primary 光晕 |
| `src/components/ui/Input.vue` | 改 | antd 式 focus 光环 |
| `src/components/ui/Dialog.vue` | 改 | 遮罩 saturate + blur 4px |
| `src/layouts/AppLayout.vue` | 改 | RouterView page 过渡、面包屑 crumb 过渡 |
| `src/App.vue` | 改 | 顶层 fade 过渡、挂载 RouteProgress |

**未引入任何新依赖。**

---

## 六、验证结果与建议人工核对项

- ✅ 两阶段 `npm run build`(vue-tsc 类型检查 + vite 构建)均通过;期间修复 1 处模板闭合标签缺失(面包屑 `</Transition>`)。
- ⚠️ 动效属主观体验,建议 `npm run dev` 后重点核对:
  1. 连续切换侧栏页面,感受 out-in 节奏(出场快、入场缓);
  2. 首次进入模组详情(懒加载 chunk 触发进度条);
  3. 刷新直开详情页(会话探测期间进度条持续爬升,不再白屏);
  4. 模组卡片 hover:阴影抬升 + 封面回弹缩放,卡片本身不跳动;
  5. 暗色模式:卡片淡边框、hover 阴影是否清晰可辨;
  6. 登录 → 登出 → 再登录的 fade 过渡;
  7. 系统开启"减少动态效果"后所有动效是否近瞬时完成。
