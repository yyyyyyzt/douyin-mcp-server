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
| `tdesign.gtimg.com/.../t.woff ERR_CACHE_MISS` | 小程序无法稳定拉 CDN 字体 | 字体放 `assets/fonts/`，`scripts/build-npm.sh` 改写 `icon.wxss` |
| 对话输入区「看不见」 | `100vh` / 未给 composer `flex-shrink:0` / 被 tabBar 挡住 | `.page-root` 用 `height:100%`；composer 在 flex 流底部；tabBar `placeholder` |
| 设置页乱 | 滥用 `t-cell` note 折行 | 改成分组卡片 + radio 列表 |

## 页面骨架

```
.page-root { display:flex; flex-direction:column; height:100%; min-height:0; }
.scroll-body { flex:1; height:0; }
.composer / 底栏 { flex-shrink:0; }
```

禁止页面根节点使用 `100vh`。

## 改动检查清单

- [ ] 保存/发送不报 `getToken is not a function`
- [ ] 控制台无 `tdesign.gtimg.com` 字体失败
- [ ] AI 助手：空状态欢迎语 + 底部输入框始终可点
- [ ] 收集：粘贴与保存并排，主按钮文案「保存到自己的知识库」
- [ ] 知识库：按阶段标签分组，可筛选
- [ ] 设置：服务状态 + 模型单选，可读可操作
