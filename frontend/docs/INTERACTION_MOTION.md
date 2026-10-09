# GMod 模组管理器 · 交互动画层说明

> 续接《[MOTION_AND_TEXTURE.md](./MOTION_AND_TEXTURE.md)》(组件质感移植 + 动效/进度条)。
> 触发原因:用户明确"动画应覆盖**各个交互**与**卡片切换**,而不只是一条进度条"。
> 本轮只动**交互动效层**,布局、接口、业务逻辑零改动;未新增任何依赖。
> 验证:`npm run build`(vue-tsc + vite,2448 modules)通过。
>
> 设计依据:frontend-skill 动效准则——动效服务于**层次与存在感**(presence & hierarchy),全站 2-3 类有明确语义的动画,克制、快速、一致;拒绝纯装饰性动画。

---

## 一、背景与总览

上一轮已交付:路由切换过渡(page)、登录页淡切(fade)、面包屑微动(crumb)、全局路由进度条(RouteProgress)、卡片 hover 阴影与封面回弹。本轮补齐的是**交互瞬间**的动画——用户点开、关闭、筛选、切换主题时的状态迁移反馈:

| # | 交互动画 | 触发场景 | 解决的生硬点 |
| --- | --- | --- | --- |
| 1 | 浮层双向出入场 | 打开/关闭对话框、下拉、菜单、Tooltip、Select | **关闭时瞬间消失**(此前只有入场动画) |
| 2 | 模组卡片网格动画 | 筛选、翻页、搜索 | 卡片整批瞬间替换,无补位过渡 |
| 3 | 统计数字滚动 | 仪表盘轮询刷新 | 数字瞬间跳变 |
| 4 | 页签滑动指示条 | 详情页切换简介/文件/技术详情 | 描边瞬间跳到新页签 |
| 5 | 主题图标切换 | 点击亮/暗切换按钮 | Sun/Moon 生硬替换 |

统一规格:时长 140-320ms,单一曲线族(入场 `cubic-bezier(0.16,1,0.3,1)` 缓出、出场 `ease-in`),全部尊重 `prefers-reduced-motion`。

---

## 二、浮层双向出入场(9 处)

### 2.1 问题

此前所有浮层(reka-ui 系)都只挂了 `animate-ui-in` 静态类——挂载即播入场,**关闭时元素瞬间卸载**,与"打开有动画、关闭无动画"的不对称感是全站最明显的生硬点。

### 2.2 机制

reka-ui(radix 系)的浮层在 `state=closed` 后会**等待 CSS 动画结束再卸载**。因此只需把静态类改为状态驱动双态类,即可获得完整的双向动画:

```text
animate-ui-in                                    (旧:仅入场,关闭瞬间消失)
data-[state=open]:animate-ui-in
data-[state=closed]:animate-ui-out               (新:打开 260ms 入场,关闭 140ms 淡出)
```

### 2.3 应用清单(9 处)

| 文件 | 浮层 | 出场动画 |
| --- | --- | --- |
| `ui/Dialog.vue` | 模态遮罩 | `animate-fade-out`(纯淡出,见 2.4) |
| `ui/Dialog.vue` | 模态内容面板 | `animate-modal-out`(见 2.4,**含 bug 修复**) |
| `ui/Tooltip.vue` | 气泡提示 | `animate-ui-out` |
| `ui/Select.vue` | 下拉面板 | `animate-ui-out` |
| `biz/ModCard.vue` | "更多"操作菜单 | `animate-ui-out` |
| `views/ModsView.vue`(2 处) | 筛选弹层、更多筛选菜单 | `animate-ui-out` |
| `layouts/AppLayout.vue`(2 处) | 折叠态子菜单、账户菜单 | `animate-ui-out` |

### 2.4 模态专用 keyframe(含一个隐患修复)

模态内容面板使用 `left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2` 居中定位。通用的 `ui-in/ui-out` keyframe 会**用自身 transform 覆盖居中位移**,导致面板动画期间跳位。因此为模态新建专用 keyframe,自始至终保持 `-50%,-50%`:

```css
@keyframes modal-in  { from { opacity:0; transform:translate(-50%,-48%) scale(0.97); }
                       to   { opacity:1; transform:translate(-50%,-50%) scale(1); } }
@keyframes modal-out { from { opacity:1; transform:translate(-50%,-50%) scale(1); }
                       to   { opacity:0; transform:translate(-50%,-48.5%) scale(0.98); } }
```

遮罩层是 `fixed inset-0` 的纯色层,任何位移/缩放都会露边,故专用 `fade-out`(纯 opacity)。顺带修复:模态内容面板此前**连入场动画都没有**(仅有遮罩淡入),本轮一并补上 `animate-modal-in`。

Token(`styles.css`):

```css
--animate-modal-in:  modal-in  240ms cubic-bezier(0.16, 1, 0.3, 1);
--animate-modal-out: modal-out 150ms ease-in;
--animate-fade-out:  fade-out 140ms ease-in;
```

---

## 三、模组卡片网格切换动画(ModGrid.vue)

### 3.1 方案

普通 `v-for` 网格改为 Vue `<TransitionGroup>`,利用 FLIP 技术实现三类过渡:

```vue
<TransitionGroup name="card" tag="div"
  class="relative grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-5">
  <ModCard v-for="(m, i) in mods" :key="m.workshop_id"
    :style="{ '--stagger': `${Math.min(i * 30, 270)}ms` }" ... />
</TransitionGroup>
```

### 3.2 三种状态的差异化处理(有意取舍)

| 状态 | CSS 类 | 行为 | 设计意图 |
| --- | --- | --- | --- |
| 进入 | `.card-enter-from` + `.card-enter-active` | 300ms 上滑淡入(下移 10px/0.98 缩放归位),`transition-delay: var(--stagger)` | **stagger 瀑布**:每卡延迟 30ms、上限 270ms,首屏与翻页都有层次感 |
| 移动 | `.card-move` | 320ms FLIP 补位(筛选后留存卡平滑滑动到新位置) | 空间连续性 |
| 离开 | `.card-leave-active { display:none }` | **立即让位** | 有意放弃 leave 动画:翻页时 24 张卡全部移除,若逐张播退场会拖沓混乱;立即消失 + 留存卡 FLIP 补位是 shadcn 系产品的成熟做法 |

### 3.3 行为细节

- `:key` 为 `workshop_id`,轮询刷新数据不变时**不会重播入场**(key 稳定);
- stagger 通过 CSS 变量内联注入,`transition-delay` 只作用于 enter-active,不影响 FLIP 补位;
- 容器加 `relative` 为 FLIP 定位提供包含块。

---

## 四、统计数字滚动(StatCard.vue)

仪表盘四张统计卡的数值(模组总数/待重启/排队任务/回收站条目)每 10s 轮询刷新,此前数字瞬间跳变。本轮实现 rAF 计数过渡:

```ts
watch(() => props.value, (v) => {
  if (typeof v !== 'number' || reduceMotion) { shown.value = v; return }
  const from = typeof shown.value === 'number' ? shown.value : 0
  cancelAnimationFrame(raf)
  if (from === target) { shown.value = target; return }
  // 520ms,ease-out cubic: 1 - (1-t)^3,前快后稳
  const step = (now) => { ...; if (p < 1) raf = requestAnimationFrame(step) }
  raf = requestAnimationFrame(step)
}, { immediate: true })
```

边界处理:
- **非数值**(string 类型,如"3 天")直接显示,不参与动画;
- **值未变化**直接赋值,不启动动画(避免轮询空转);
- **连续变化**先 `cancelAnimationFrame` 上一次动画,从当前显示值继续滚,不回跳;
- **`prefers-reduced-motion`** 首次检测,命中则跳过动画;
- 组件卸载时取消 rAF,防内存泄漏。

---

## 五、详情页页签滑动指示条(ModDetailView.vue)

### 5.1 交互

模组详情页"简介/文件清单/技术详情"三页签,原激活态是静态 `border-b-2` 描边——切换时描边瞬间跳到新页签。改为**底部 2px 强调色圆头条**,随切换平滑滑动(300ms `transition-[left,width]`),与 Material/antd 的 Tabs 指示条一致。

### 5.2 实现

- 函数 ref 把每个页签按钮注册进 `Map<TabKey, HTMLElement>`(`setTabRef`);
- `updateIndicator()` 读取当前按钮的 `offsetLeft/offsetWidth` 写入 `indicator`;
- **三个重算时机**:
  1. `watch(activeTab)` → `nextTick` 后测量(切换页签);
  2. `watch(mod)` → 骨架屏替换为真实内容后重新测量(页签区在骨架期可能不存在);
  3. `ResizeObserver` 观察 tablist 容器——窗口缩放、字体异步加载导致按钮宽度变化时自动校正;
- 首次测量完成前指示条 `opacity: 0`,避免闪现在错误位置;
- `onBeforeUnmount` 断开 observer;
- 页签按钮样式同步简化:移除 `border-b-2` 描边与相关 hover 边框(指示条承担激活指示),保留文字颜色 150ms 过渡。

---

## 六、主题切换图标(AppLayout.vue)

亮/暗切换按钮的 Sun/Moon 图标包 `<Transition name="theme-icon" mode="out-in">`,实现**旋转交叉切换**:

```css
.theme-icon-enter-from { opacity:0; transform:rotate(-90deg) scale(0.6); }
.theme-icon-leave-to   { opacity:0; transform:rotate(90deg)  scale(0.6); }
/* 过渡:180ms opacity + 200ms transform */
```

效果:旧图标右旋缩小淡出 → 新图标左旋放大淡入,`mode="out-in"` 保证同一时刻只有一个图标占位。

---

## 七、styles.css 新增清单

| 类别 | 名称 | 规格 |
| --- | --- | --- |
| token | `--animate-modal-in/out`、`--animate-fade-out` | 2.4 节 |
| keyframes | `modal-in` / `modal-out` / `fade-out` | 保持居中位移的模态专用曲线 |
| 类 | `.card-enter-from` / `.card-enter-active` / `.card-leave-active` / `.card-move` | ModGrid TransitionGroup(第三节) |
| 类 | `.theme-icon-*` | 主题图标旋转交叉(第六节) |

已有的 `ui-in/ui-out`(260/140ms)继续作为通用浮层动画,时长未变。

---

## 八、修改文件清单

| 文件 | 类型 | 内容 |
| --- | --- | --- |
| `src/styles.css` | 改 | modal/fade keyframe 与 token、card 网格过渡类、theme-icon 类 |
| `src/components/ui/Dialog.vue` | 改 | 遮罩淡出、内容面板双向动画(补入场 + 修居中隐患) |
| `src/components/ui/Tooltip.vue` | 改 | 双态出入场 |
| `src/components/ui/Select.vue` | 改 | 双态出入场 |
| `src/components/biz/ModCard.vue` | 改 | 更多菜单双态出入场 |
| `src/components/biz/ModGrid.vue` | 改 | TransitionGroup + stagger + FLIP |
| `src/components/biz/StatCard.vue` | 改 | 数字滚动(rAF + 边界处理) |
| `src/views/ModsView.vue` | 改 | 2 处弹层双态出入场 |
| `src/views/ModDetailView.vue` | 改 | 页签滑动指示条(测量/observer/生命周期) |
| `src/layouts/AppLayout.vue` | 改 | 2 处菜单双态出入场、主题图标过渡 |

**未引入任何新依赖**;路由过渡、进度条、骨架屏、卡片 hover 质感均为上一轮已有,未重复建设。

---

## 九、无障碍与克制原则

- 全部动画处于 `@media (prefers-reduced-motion: reduce)` 全局覆盖之下(0.01ms),系统开启"减少动态效果"时自动失效;数字滚动额外做了显式检测;
- 时长区间 **140-320ms**:浮层出场 140ms、浮层入场 260ms、模态 240ms、卡片 300-320ms、指示条 300ms、数字 520ms(仅首次与轮询时发生);
- 曲线族统一:入场一律缓出曲线 `cubic-bezier(0.16,1,0.3,1)`,出场一律 `ease-in/ease-out`;
- 每个动画都对应明确的**状态迁移语义**(出现/消失/补位/计数/切换),无纯装饰动画。

---

## 十、验证结果与建议人工核对项

- ✅ `npm run build`(vue-tsc 类型检查 + vite 构建)通过;
- ⚠️ 动效属主观体验,建议 `npm run dev` 后重点核对:
  1. 打开任意确认框 → 关闭:面板应缩放淡出(而非瞬间消失),遮罩纯淡出;
  2. 模组库切换筛选/翻页:新卡依次上滑入场,留存卡平滑补位;
  3. 仪表盘首次加载与轮询刷新:统计数字平滑滚动;
  4. 详情页三个页签来回切换:底部指示条平滑滑动,缩放窗口后位置仍准确;
  5. 连续点击主题按钮:图标旋转交叉切换;
  6. 快速开关同一弹层(连点):无残影、无卡死;
  7. 系统开启"减少动态效果"后以上全部近瞬时完成。
