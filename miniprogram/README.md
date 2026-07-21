# 自装助手 · 微信小程序

## 1. 用哪个目录打开项目？

**微信开发者工具的项目根目录必须是本文件夹 `miniprogram/`**（里面有 `app.json`、`project.config.json`）。

不要选仓库根目录。

## 2. npm 安装位置

在 **`miniprogram/`** 下执行（不是仓库根目录）：

```bash
cd miniprogram
npm install
```

`package.json` 与 `node_modules` 必须同在 `miniprogram/` 内，才符合[微信 npm 文档](https://developers.weixin.qq.com/miniprogram/dev/devtools/npm.html)对 `miniprogramRoot` 的要求。

`npm install` 会自动执行 `postinstall`，把 TDesign 同步到 `miniprogram_npm/`。仓库里已预置一份，**克隆后通常可直接打开**。

若仍报「未找到组件 `tdesign-miniprogram/...`」，任选其一：

```bash
cd miniprogram
npm run build:npm
```

或在开发者工具：**工具 → 构建 npm**（需先勾选「使用 npm 模块」）。

## 3. 开发者工具设置

1. 打开 **`miniprogram/`** 为项目根目录
2. 详情 → 本地设置 → 勾选 **「使用 npm 模块」**
3. 修改 `app.js` 中 `API_BASE` 为后端地址
4. 本地调试可勾选「不校验合法域名」

## 4. 组件路径说明

页面 `*.json` 中写法（无需改）：

```json
"t-textarea": "tdesign-miniprogram/textarea/textarea"
```

运行时由工具解析到 **`miniprogram/miniprogram_npm/tdesign-miniprogram/textarea/textarea`**。该目录不存在就会报你看到的错误。

## 5. UI 说明

- 对话为默认首页；输入区固定在底部（类通用 AI 对话）
- 图标字体本地化：`assets/fonts/`（`npm run build:npm` 会改写 TDesign CDN）
- 设计约定：[`../skills/miniprogram-design/SKILL.md`](../skills/miniprogram-design/SKILL.md)
- 设计与计划：[`../docs/DESIGN.md`](../docs/DESIGN.md)、[`../docs/DEV_PLAN.md`](../docs/DEV_PLAN.md)
