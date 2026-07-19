# 自装助手 · 微信小程序 UI 优化建议

> 状态：**供评审**（仅文档，未改代码）。
> 依据：当前 `miniprogram/` 脚手架实现、[`FRONTEND_REFACTOR_PLAN.md`](FRONTEND_REFACTOR_PLAN.md) 手机端原则、
> [微信开放文档 · 框架](https://developers.weixin.qq.com/miniprogram/dev/framework/)、
> [TDesign 小程序](https://tdesign.tencent.com/miniprogram/getting-started) /
> [tdesign-miniprogram](https://github.com/Tencent/tdesign-miniprogram)。

---

## 1. 背景与问题现象

当前小程序已具备三 Tab（收集 / 知识库 / 问答）MVP，但真机/开发者工具上可能出现：

| 现象 | 可能原因（对照现实现） |
|---|---|
| 底部菜单「不像固定」、随页面一起滚走 | 若指**原生 tabBar**：官方 tabBar 由客户端固定渲染，理论上不应滚动；更常见是**页面内容区高度算错**（如 `100vh`）导致整页可滚，视觉上像 Tab 没钉住 |
| 若指**问答页输入栏**：`.composer` 未 `position: fixed`，仅在 flex 流内，键盘弹起或内容变长时体验不稳定 | `pages/chat/chat.wxss` |
| 列表最底部被挡住 | Tab 页内容未预留底部空间；或自定义 Tab 未开 `placeholder` |
| 知识库详情抽屉与 Tab 重叠 | `.sheet` 用 `position: fixed; bottom: 0` 未抬高到 Tab 之上 |
| Tab 只有文字、无图标，观感偏「半成品」 | `app.json` 的 `tabBar.list` 未配置 `iconPath` / `selectedIconPath` |
| 设置页存在但无入口 | `pages/settings/settings` 在 `pages` 中但不在 `tabBar`，也未挂到导航 |

**结论**：需要区分两类「底部固定」——

1. **全局 Tab 导航**（收集 / 知识库 / 问答）
2. **页面内底栏**（问答输入区、知识库详情操作条）

二者布局策略不同，不能混用 Web 的 `position: fixed + 100vh` 直觉。

---

## 2. 微信官方文档要点（与本案相关）

### 2.1 原生 tabBar（当前方案）

配置见 [全局配置 · tabBar](https://developers.weixin.qq.com/miniprogram/dev/reference/configuration/app.html#tabBar)：

- `position` 默认 `bottom`，由**客户端**绘制，**不参与页面 WXML 布局**。
- Tab 页的可视区域 = 屏幕高度 − 导航栏 − **tabBar 高度**（已由基础库扣除）。
- `iconPath` / `selectedIconPath` 建议 **81×81px**，单图 ≤ 40KB。
- 因此：**Tab 页内不应再为 tabBar 额外减高度**；但若页面用了 `100vh`，会把 tabBar 区域也算进去，容易造成**整页溢出、可滚动**，看起来像 Tab「不固定」。

### 2.2 自定义 tabBar（品牌化 / TDesign 路线）

见 [自定义 tabBar](https://developers.weixin.qq.com/miniprogram/dev/framework/ability/custom-tabbar.html)：

- `app.json` → `"tabBar": { "custom": true, ... }`
- 根目录增加 `custom-tab-bar/` 组件；官方建议 `position: fixed` 贴底，可用 `cover-view` 保证层级。
- 每个 Tab 页 `onShow` 里通过 `getTabBar()` 更新选中态。
- **必须**为页面内容预留 Tab 占位高度，否则内容会被遮挡（社区常见问题）。

### 2.3 scroll-view 与页面高度

见 [scroll-view 组件](https://developers.weixin.qq.com/miniprogram/dev/component/scroll-view.html)：

- 纵向滚动必须给 `scroll-view` **明确高度**（不能指望 `height: auto` 撑开）。
- 官方与社区推荐在 Tab 页使用 **flex 列布局**：

```css
/* 推荐骨架：Tab 页根容器 */
.page-root {
  display: flex;
  flex-direction: column;
  height: 100%;           /* 不要用 100vh */
  min-height: 0;          /* 允许 flex 子项收缩 */
}
.scroll-body {
  flex: 1;
  height: 0;              /* 或 1px，触发 flex 正确计算 */
}
```

- `100vh` 在 iOS / 鸿蒙 / Skyline 下与「页面实际可用高度」不一致，是**当前 chat 页布局问题的高概率根因**。

### 2.4 安全区（safe-area）

- CSS：`constant(safe-area-inset-bottom)` + `env(safe-area-inset-bottom)` 需成对书写以兼容旧版 iOS。
- 原生 tabBar 会自行处理底部安全区；**页面内 fixed 底栏**（如问答输入框）才需要手动加 safe-area。
- 鸿蒙 / Skyline 下 `env()` 可能无效；TDesign 已在 TabBar 用 `wx.getWindowInfo()` 计算 `--safe-area-inset-bottom` 作为兜底（见 [tdesign#4304](https://github.com/Tencent/tdesign-miniprogram/pull/4304)）。

---

## 3. TDesign 小程序：为何推荐、如何用

### 3.1 与项目目标的匹配

| 需求 | TDesign 能力 |
|---|---|
| 底部 Tab 固定 + 安全区 + 占位 | [`t-tab-bar`](https://tdesign.tencent.com/miniprogram/components/tab-bar)：`fixed`、`safe-area-inset-bottom`、`placeholder` |
| 知识库搜索 / 筛选 | `t-search`、`t-tag` |
| 卡片列表 | `t-cell` / `t-swipe-cell` |
| 详情抽屉 | `t-popup` `placement="bottom"` 或 `t-drawer` |
| 收集页主按钮 / 进度 | `t-button`、`t-progress`、`t-textarea` |
| 问答气泡 / 加载 | `t-loading`、`t-toast` |
| 设计令牌（暖橙主色） | 主题变量 `--td-brand-color` 等，可对齐 Web `#FF6B4A` |

安装（官方推荐 NPM）：

```bash
cd miniprogram   # 或项目根，按实际 package.json 位置
npm i tdesign-miniprogram -S --production
```

开发者工具：详情 → 本地设置 → **使用 npm 模块** → 工具 → 构建 npm。  
参考：[TDesign 快速开始](https://tdesign.tencent.com/miniprogram/getting-started)、[GitHub README](https://github.com/Tencent/tdesign-miniprogram)。

### 3.2 两条 Tab 技术路线对比

| 维度 | A. 继续原生 tabBar | B. 自定义 tabBar + TDesign（推荐） |
|---|---|---|
| 固定贴底 | 客户端保证 | `t-tab-bar` `fixed` + `placeholder` |
| 品牌图标 / 选中态 | 需自备 81px 图标 | 组件内置图标或 slot |
| 与 Web 视觉统一 | 需自己画图标 | 主题色 + 组件样式可调 |
| 页面高度 | 用 `height: 100%`，**禁止 100vh** | 需处理 placeholder 高度；TDesign 已封装 |
| 改造成本 | 低（补图标 + 改布局） | 中（`custom-tab-bar` + 引组件） |
| 长期维护 | 样式分散在各页 wxss | 组件化、与 TDesign 文档同步 |

**建议**：若你已在验收 UI 且希望与 Web 极简风格一致，**优先路线 B**；若只想快速修 Tab「假滚动」，可先做路线 A 的布局修正，再迭代 B。

---

## 4. 推荐页面骨架（统一后各 Tab 复用）

建议在 `miniprogram/` 增加布局约定（可先文档化，实施时抽 `components/page-shell`）：

```
┌─────────────────────────────┐
│  navigationBar（系统）       │
├─────────────────────────────┤
│  .page-root  flex column     │
│  ┌─────────────────────────┐ │
│  │ .scroll-body (flex:1)   │ │  ← scroll-view 或页面滚动区
│  │   主内容                 │ │
│  └─────────────────────────┘ │
│  ┌─────────────────────────┐ │
│  │ .page-footer (可选)      │ │  ← 问答输入栏等，fixed 在 Tab 之上
│  └─────────────────────────┘ │
├─────────────────────────────┤
│  tabBar（原生或 custom）      │  ← 仅全局 Tab，不在页面 WXML 里写死
└─────────────────────────────┘
```

全局样式建议（`app.wxss`）：

```css
page {
  height: 100%;
  background: #fff8f5;
  color: #1f2937;
  font-size: 28rpx;
  box-sizing: border-box;
}

.page-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 32rpx;
  box-sizing: border-box;
}

/* 仅用于页面内 fixed 底栏（在 tabBar 之上），不是 tabBar 本身 */
.page-footer-fixed {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding-bottom: constant(safe-area-inset-bottom);
  padding-bottom: env(safe-area-inset-bottom);
  background: #fff;
  z-index: 100;
}
```

**删除或替换** 当前 `.safe-bottom { padding-bottom: calc(24rpx + env(...)) }` 的笼统用法，改为：

- Tab 页列表区：依赖 `scroll-view` + `flex:1`，**不必**为 tabBar 再加 padding。
- 问答输入栏：单独 `page-footer-fixed`，且 `bottom` 需加上 **tabBar 高度**（自定义 Tab 时由 `t-tab-bar` 的 `placeholder` 处理）。

---

## 5. 分页面优化建议

### 5.1 收集（`pages/collect`）

| 项 | 现状 | 建议 |
|---|---|---|
| 主输入 | 原生 `textarea` | `t-textarea`，`autosize`，最大高度限制 |
| 主按钮 | 自定义 `.btn-primary` | `t-button` `theme="primary"` `block` `size="large"` |
| 进度 | 原生 `progress` | `t-progress` + 人话文案（对齐 Web） |
| 粘贴 | `wx.getClipboardData` | 保留；可加 `t-button` `variant="outline"`「粘贴」 |
| 布局 | 普通流式 | 首屏保证输入框 + 主按钮在可视区内；成功预览用 `t-cell` 折叠 |

### 5.2 知识库（`pages/knowledge`）

| 项 | 现状 | 建议 |
|---|---|---|
| 列表滚动 | **无** `scroll-view`，卡片多时可撑破布局 | 外层 `scroll-view` + `flex:1`；或 `t-pull-down-refresh` |
| 搜索 | 原生 `input` | `t-search` |
| 阶段筛选 | 横向 `scroll-view` + 自绘 chip | `t-tag` / `t-check-tag` 横向滚动 |
| 详情 | 自绘 `.sheet` fixed 到底 | `t-popup` `placement="bottom"`，高度 70vh，`safe-area-inset-bottom` |
| 空状态 | 纯文字 | `t-empty` + 跳转收集页 |

### 5.3 问答（`pages/chat`）——**优先修复**

| 项 | 现状 | 建议 |
|---|---|---|
| 页面高度 | `.page { height: 100vh }` | 改为 `.page-root { height: 100% }` |
| 消息列表 | `scroll-view` 无明确高度 | `flex:1; height:0`，`enhanced` + `show-scrollbar="{{false}}"` |
| 输入区 | 流式 `.composer` | **fixed 底栏**（在 tabBar 之上）；键盘：`adjust-position` / `cursor-spacing` |
| 快捷问题 | 自绘列表 | `t-grid` 或胶囊 `t-tag` |
| 附件 | `button size="mini"` | `t-upload` 或图标按钮 + `chooseMessageFile` |
| 依据标签 | 自绘 `.badge` | `t-tag` `theme="success"` / `theme="warning"` |

参考 Web 文案（[`FRONTEND_REFACTOR_PLAN.md`](FRONTEND_REFACTOR_PLAN.md)）：

- 有依据：绿色「来自你的知识库」
- 无依据：琥珀色「这条回答没有找到你的知识依据，仅供参考」

### 5.4 设置（`pages/settings`）

- 不应占用 Tab；与 Web 一致，从**导航栏右侧「更多」**或首页胶囊进入。
- 使用 `t-cell-group` + `t-cell` 展示 API 地址、服务状态（只读）。
- 从 Tab 页 `navigateTo` 时，该页**无 tabBar**，无需 placeholder。

### 5.5 全局 tabBar / 自定义 Tab

**方案 A（小改）**：保留原生 tabBar，在 `app.json` 补充：

```json
"tabBar": {
  "position": "bottom",
  "color": "#9CA3AF",
  "selectedColor": "#FF6B4A",
  "backgroundColor": "#FFFFFF",
  "borderStyle": "white",
  "list": [
    {
      "pagePath": "pages/collect/collect",
      "text": "收集",
      "iconPath": "assets/tab/collect.png",
      "selectedIconPath": "assets/tab/collect-active.png"
    }
  ]
}
```

**方案 B（推荐）**：`custom: true` + `custom-tab-bar` 使用 TDesign：

```json
"tabBar": {
  "custom": true,
  "list": [ ... 与现网一致 ... ]
}
```

```xml
<!-- custom-tab-bar/index.wxml 示意 -->
<t-tab-bar value="{{active}}" bind:change="onChange" fixed safe-area-inset-bottom placeholder>
  <t-tab-bar-item value="collect" icon="home">收集</t-tab-bar-item>
  <t-tab-bar-item value="knowledge" icon="books">知识库</t-tab-bar-item>
  <t-tab-bar-item value="chat" icon="chat">问答</t-tab-bar-item>
</t-tab-bar>
```

每个 Tab 页 `onShow`：

```js
onShow() {
  if (typeof this.getTabBar === 'function') {
    this.getTabBar((tabBar) => tabBar.setData({ active: 'collect' }));
  }
}
```

> Skyline 渲染模式下 `getTabBar` 为异步回调，需按[官方说明](https://developers.weixin.qq.com/miniprogram/dev/framework/ability/custom-tabbar.html)适配。

---

## 6. 设计规范（对齐 Web + TDesign 令牌）

| 令牌 | 建议值 | 用途 |
|---|---|---|
| 主色 | `#FF6B4A` | 主按钮、Tab 选中、进度条 |
| 页面背景 | `#FFF8F5` | 与 Web PWA 一致 |
| 卡片背景 | `#FFFFFF` | 列表卡片、输入框 |
| 正文 | `#1F2937` | 标题 / 正文 |
| 次要文字 | `#6B7280` | 说明、时间 |
| 成功 / 有依据 | `#059669` | 问答引用 |
| 警告 / 无依据 | `#D97706` | 免责声明 |
| 圆角 | 24rpx（卡片）、999rpx（输入） | 与现 Web 接近 |
| 点击区域 | ≥ 88rpx 高 | 拇指友好（约 44px） |

TDesign 主题覆盖可在 `app.wxss` 或 `theme.json`（若启用 darkmode）中设置 `--td-brand-color: #FF6B4A`。

---

## 7. 建议实施顺序（评审通过后再动代码）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0** | 去掉 Tab 页 `100vh`；问答页 scroll + fixed 输入栏；知识库列表 `scroll-view` | Tab 切换时底栏不「跟着滚」；列表滚到底不被挡 |
| **P1** | 原生 tabBar 补图标 + `borderStyle`；统一 `page-root` 骨架 | 三 Tab 视觉完整；收集/知识库首屏稳定 |
| **P2** | 引入 TDesign；`custom-tab-bar` + `t-tab-bar`；收集/知识库/问答核心组件替换 | 与 Web 风格统一；npm 构建通过 |
| **P3** | `t-popup` 详情抽屉；`t-toast` / `t-loading`；设置页入口 | 详情不挡 Tab；错误提示人话化 |
| **P4** | 真机矩阵：iOS 刘海、Android 手势条、鸿蒙（如有） | 安全区无留白/遮挡 |

---

## 8. 验收清单（你手动测 UI 时可对照）

- [ ] 三个 Tab 页切换时，**底部 Tab 始终贴底固定**，不随内容滚动。
- [ ] 问答页：消息区独立滚动；输入栏贴底；键盘弹起时不挡输入框。
- [ ] 知识库：50+ 条卡片滚动流畅；详情从底部弹出，关闭后 Tab 仍正常。
- [ ] 收集页：主按钮首屏可见；长文粘贴不撑破布局。
- [ ] iPhone 带 Home Indicator 机型：Tab 与页面底栏不贴边、不重叠。
- [ ] 文案无 LLM / ASR / API Key 等技术词（与 Web 一致）。

---

## 9. 参考链接

| 资源 | URL |
|---|---|
| 微信小程序框架 | https://developers.weixin.qq.com/miniprogram/dev/framework/ |
| 全局配置 tabBar | https://developers.weixin.qq.com/miniprogram/dev/reference/configuration/app.html#tabBar |
| 自定义 tabBar | https://developers.weixin.qq.com/miniprogram/dev/framework/ability/custom-tabbar.html |
| scroll-view | https://developers.weixin.qq.com/miniprogram/dev/component/scroll-view.html |
| 窗口信息 / 安全区 | https://developers.weixin.qq.com/miniprogram/dev/api/base/system/wx.getWindowInfo.html |
| TDesign 快速开始 | https://tdesign.tencent.com/miniprogram/getting-started |
| TDesign TabBar 组件 | https://tdesign.tencent.com/miniprogram/components/tab-bar |
| tdesign-miniprogram 仓库 | https://github.com/Tencent/tdesign-miniprogram |

---

## 10. 与现有文档关系

- 产品信息架构与文案：仍以 [`FRONTEND_REFACTOR_PLAN.md`](FRONTEND_REFACTOR_PLAN.md) 为准。
- 后端 API / 鉴权：不变，见 [`WECHAT_MINIPROGRAM_PLAN.md`](WECHAT_MINIPROGRAM_PLAN.md)。
- 本文件仅覆盖 **小程序 UI / 布局 / 组件库** 优化，**不涉及**接口契约变更。
