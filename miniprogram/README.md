# 自装助手 · 微信小程序

## 依赖安装

```bash
cd miniprogram
npm install
```

在微信开发者工具中：

1. 打开本目录为小程序项目根目录
2. 详情 → 本地设置 → 勾选「使用 npm 模块」
3. 工具 → **构建 npm**
4. 修改 `app.js` 中 `API_BASE` 为后端 HTTPS 地址
5. 本地调试可勾选「不校验合法域名」

## UI 说明

- 使用 [TDesign 小程序](https://tdesign.tencent.com/miniprogram/getting-started) + 自定义 `custom-tab-bar`
- 对话场景模型见 `utils/chat-scenarios.js`
- UI 优化与扩展规划见 [`../docs/MINIPROGRAM_UI_OPTIMIZATION.md`](../docs/MINIPROGRAM_UI_OPTIMIZATION.md)
