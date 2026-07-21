---
name: miniprogram-design
description: >-
  自装助手微信小程序 UI/交互设计与排障约定。当修改 miniprogram/ 页面布局、对话界面、
  Tab、登录、TDesign 组件、字体图标，或用户反馈小程序界面报错/不好用时使用。
---

# 自装助手 · 小程序设计 Skill

## 产品界面原则

1. **AI 助手是中心**：默认落地对话页；输入区必须始终可见（类 ChatGPT：消息区 + 底部固定输入框）。
2. **少组件、少远程资源**：能用原生 `button`/`input`/`textarea` 就不用 TDesign；图标字体必须本地化。
3. **人话文案**：不出现 LLM/ASR/API Key；按钮写结果（「保存到自己的知识库」）。
4. **一屏一主动作**：收集页只有「粘贴 + 保存」；设置页分组卡片，不要挤成表格。

## 已知坑（必避）

| 问题 | 原因 | 解法 |
|---|---|---|
| `authUtil.getToken is not a function` / `module 'utils/token.js' is not defined` | 循环依赖，或新建 utils 文件未被工具打包 | **不要**拆独立 `token.js`；token 读写内联在 `auth.js` / `request.js`；登录用 `wx.request` 直调 |
| `Failed to load local font … t.ttf-do-not-use-local-path` / CDN 字体失败 | 微信拒绝本地 ttf/woff 路径，CDN 也不稳 | `assets/fonts/t.woff` + `scripts/build-npm.sh` 把 `@font-face` **改写为 base64 data URI**；自定义 tabBar **不用** TDesign 图标 |
| 对话输入区被底部菜单挡住 | 自定义 tabBar 是 `position:fixed` 悬浮层，不占文档流 | `.page-root` 设 `padding-bottom: calc(112rpx + env(safe-area-inset-bottom))`；composer 不再单独加 safe-area |
| 设置页乱 | 滥用 `t-cell` note 折行 | 改成分组卡片 + radio 列表 |

## 页面骨架

```
.page-root {
  display:flex; flex-direction:column; height:100%; min-height:0;
  padding-bottom: calc(112rpx + env(safe-area-inset-bottom)); /* tab 页必留 */
}
.scroll-body { flex:1; height:0; }
.composer / 底栏 { flex-shrink:0; }
```

禁止页面根节点使用 `100vh`。自定义 tabBar 高度与 `custom-tab-bar/index.wxss` 保持一致。

## 改动检查清单

- [ ] 保存/发送不报 `getToken is not a function`
- [ ] 控制台无本地字体 500、无 `tdesign.gtimg.com` 字体失败
- [ ] AI 助手：空状态欢迎语 + 底部输入框始终可点（不被 tab 遮挡）
- [ ] 收集：粘贴与保存并排，主按钮文案「保存到自己的知识库」
- [ ] 知识库：按阶段标签分组，可筛选
- [ ] 设置：服务状态 + 模型单选，可读可操作
