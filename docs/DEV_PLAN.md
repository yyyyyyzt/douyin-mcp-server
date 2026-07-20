# 自装助手 · 开发计划（v2 改版）

> 状态：**已确认，实施中**。其他 agent 按本文件逐任务实施。
> 前置阅读：[`DESIGN.md`](DESIGN.md)。进度写入 [`../PROGRESS.md`](../PROGRESS.md)。

## 已确认决策（2026-07-20）

1. **知识默认私有**（`is_public=0`）。公开后如何分享 → **下一步规划，本期不做共享检索**。
2. **不限制对话**；只限制链接提取（转写 + AI 整理）。
3. 中间 Tab 文案：**AI 助手**。
4. Web 端：**冻结**，仅不方便用小程序时调试。
5. **无历史数据**：直接改 schema，删除全部迁移/兼容代码。

## 背景

v1（任务 1~14）已合入 main。本轮：

1. **对话为中心**：默认落地 AI 助手页；Tab = 收集(左) | AI 助手(中) | 知识库(右)；未登录引导微信登录。
2. **存储精简**：知识正文统一 Markdown；每日只限链接提取；转写跨用户共享缓存。
3. **共享知识**：仅预留 `is_public` 字段（默认 0），分享 UX / 跨用户检索 **延期**。

M0（清理遗留 MCP / 过时文档）已完成。

---

## 任务总览

| 任务 | 主题 | 状态 |
|---|---|---|
| M0 | 清理遗留 + 文档改版 | ✅ |
| M1 | 后端：知识 Markdown 化 + schema 精简 | ⬜ 实施中 |
| M2 | 后端：只限链接提取 + 转写共享缓存 | ⬜ |
| M3 | 小程序：Tab 重排（AI 助手居中首页）+ 登录引导 | ⬜ |
| M4 | 小程序：知识库 Markdown 渲染 + 收集页适配 | ⬜ |
| M5 | 共享知识检索与分享 | ⏸ 延期（下一步规划）|
| M6 | Web 调试端最小适配 + 验收清单 | ⬜ |

M1/M2（后端）与 M3（小程序壳）可并行；M4 依赖 M1+M3。
每任务独立小步提交，TDD，`python -m pytest` 全绿。

---

## M1 · 知识 Markdown 化 + schema 精简

**改动**：`web/core/db.py`、`structure.py`、`qa.py`、`retrieve.py`、`prompts.py`、`web/app.py`、`tests/`、`prompts.example.json`

- `knowledge_cards`：`content_md` 唯一正文；`is_public INTEGER DEFAULT 0`；删除 `raw_text`/`structured_json`。
- 删除全部 legacy 迁移代码；FTS 索引 `title, content_md`。
- `structure.py`：AI 输出改为 Markdown（JSON 仅含 `title/stage/content_md`）；合并多卡为一条 markdown。
- API 卡片对象：`{id, title, content_md, stage, source_type, source_url, video_id, is_public, created_at, updated_at}`。
- `PUT` 可改 `title/content_md/stage/is_public`；`save` / preview 的 `content` 字段映射为 `content_md`（请求可用 `content` 别名以降低前端改动）。
- `qa` / `retrieve` 改用 `content_md`。

**验收**：测试全绿；代码与 API 不再出现 `raw_text`/`structured_json`/`steps`（步骤 UI 进度除外）。

## M2 · 只限链接提取 + 转写共享缓存

**改动**：`web/core/db.py`、`web/app.py`、`settings.py`、`.env.example`、`tests/`、必要时 `douyin_downloader.py`

- `users.level INTEGER DEFAULT 0`；`llm_usage(user_id, day, extract_calls)`；**不统计、不限制对话**。
- 限额：level 0 默认 extract=10，可用 `DAILY_EXTRACT_LIMIT` 覆盖；`DAILY_LIMITS` 代码常量。
- 计入 extract 的接口：`/api/video/extract*`、`/api/cards/from-link`（真正触发 ASR/LLM 时）；命中转写缓存不计入。
- `/api/chat`、`/api/cards/from-text`、`/api/cards/structure`：**不限额**（文字整理成本低；对话不限）。
- `transcripts(video_id, asr_model, text)` 跨用户复用；命中跳过下载+ASR。
- 超限返回 `429` + 「今日链接提取次数已用完，明天再来吧」。

**验收**：超限 429、跨天重置、缓存命中跳过 ASR 且不计入限额、视频文件缓存行为不变。

## M3 · 小程序 Tab 重排 + 登录引导

**改动**：`miniprogram/app.json`、`custom-tab-bar/`、`utils/auth.js`、`utils/tab.js`、`pages/*`

- `pages` 首项与默认落地 = `pages/chat/chat`；tabBar 顺序：收集 | AI 助手 | 知识库。
- 登录引导卡片（三 Tab 共用）；401 清 token → 显示引导。

**验收**：启动落在 AI 助手；未登录可见引导；布局不回归。

## M4 · 知识库 Markdown 渲染 + 收集页适配

**改动**：`miniprogram/pages/knowledge/*`、`pages/collect/*`

- 详情用轻量 md→nodes + `rich-text`；编辑 textarea 改 markdown；字段改 `content_md`。
- 收集页成功预览用 markdown 摘要。
- `is_public` 开关可先隐藏（分享延期）；字段入库默认 0。

**验收**：列表/详情/编辑/删除链路；常见 markdown 可显示。

## M5 · 共享知识（延期）

预留 `is_public` 字段即可。跨用户检索、分享入口、引用标注 → 下一步单独规划。

## M6 · Web 调试端适配 + 收尾

- `web/templates/index.html`：字段改 `content_md`，提取超限友好提示；不做新功能。
- 更新 `PROGRESS.md` / `README.md`。
- 部署清单核对（HTTPS、合法域名、`.env`）。

---

## 实施规范

- TDD；依赖注入；密钥不进小程序；用户文案无 LLM/ASR 等词。
- 完成任务更新 `PROGRESS.md`。
