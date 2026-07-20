# 自装助手 · 开发计划（v2 改版）

> 状态：**待用户确认**。确认后其他 agent 按本文件逐任务实施。
> 前置阅读：[`DESIGN.md`](DESIGN.md)（目标信息架构 / 数据模型 / API 契约）。
> 进度打勾与验收记录写入 [`../PROGRESS.md`](../PROGRESS.md)。

## 背景

任务 1~14（知识库 MVP、微信登录、用户隔离、小程序三 Tab、TDesign UI）已完成并合入 main。
本轮改版三个主题：

1. **对话为中心**：小程序默认落地 AI 对话页，Tab 布局改为 收集(左) | AI 对话(中) | 知识库(右)；
   未登录用户提供微信登录引导。
2. **存储精简**：知识正文统一 Markdown，删除 structured_json/steps；新增每日 LLM 限额与
   转写共享缓存；数据库直接改 schema，不写兼容迁移（项目未投入运行）。
3. **共享知识**：知识默认公开共享（`is_public=1`），问答检索覆盖「自己的 + 共享的」知识。

遗留清理（本 PR 已完成）：删除 `douyin_mcp_server/` MCP server、skill 打包文件，
`pyproject.toml` 更名为 `zizhuang-assistant` 并移除 `mcp` 依赖；删除过时计划文档。

---

## 任务总览

| 任务 | 主题 | 依赖 |
|---|---|---|
| M1 | 后端：知识 Markdown 化 + schema 精简 | — |
| M2 | 后端：每日 LLM 限额 + 转写共享缓存 | M1 |
| M3 | 小程序：Tab 重排（对话居中为首页）+ 登录引导 | — |
| M4 | 小程序：知识库管理页 Markdown 渲染 + 收集页适配 | M1, M3 |
| M5 | 共享知识检索与引用标注 | M1 |
| M6 | 收尾：Web 调试端适配 + 真机验收 + 部署清单 | M1~M5 |

M1/M2（后端）与 M3（小程序壳）可并行；M4/M5 依赖前置任务合入。
每个任务独立分支 + PR，TDD：先写/改 `tests/` 再实现，保持 `python -m pytest` 全绿。

---

## M1 · 知识 Markdown 化 + schema 精简

**改动文件**：`web/core/db.py`、`web/core/structure.py`、`web/core/qa.py`、
`web/core/retrieve.py`、`web/app.py`、`tests/`

- `knowledge_cards` 改为 DESIGN.md 第 4 节的目标 schema：`content_md` 为唯一正文字段，
  新增 `is_public`（默认 1）；删除 `raw_text`/`structured_json` 及相关 steps 归一化逻辑。
- 删除 `db.py` 中 `_migrate_legacy_schema` / `_LEGACY_FTS_TRIGGERS` 等兼容迁移代码；
  FTS5 索引列改为 `title, content_md`。
- `structure.py`：AI 整理的输出从 JSON steps 改为 **Markdown**（标题 + 正文，
  正文含要点/步骤/注意事项的 markdown 列表）；prompt 相应更新（`web/core/prompts.py`）。
- API 卡片对象统一为 `{id, title, content_md, stage, source_type, source_url, video_id,
  is_public, created_at, updated_at}`；`PUT /api/cards/{id}` 可改
  `title/content_md/stage/is_public`。
- `qa.py`：引用注入 prompt 时直接用 `content_md`。

**验收**：
- 全部测试绿；`from-text` / `from-link` / `save` 产出 markdown 卡片；
- 老字段（`raw_text`、`structured_json`、`steps`）在代码与 API 响应中不再出现；
- 检索/问答/编辑/删除链路可用（测试覆盖）。

## M2 · 每日 LLM 限额 + 转写共享缓存

**改动文件**：`web/core/db.py`（`llm_usage`、`transcripts` 表）、`web/app.py`、
`web/core/settings.py`、`.env.example`、`tests/`

- `users` 增加 `level INTEGER DEFAULT 0`；代码内 `DAILY_LIMITS = {level: {chat, extract}}`，
  level 0 默认 chat=20 / extract=10，可用 `DAILY_CHAT_LIMIT` / `DAILY_EXTRACT_LIMIT` 覆盖。
- `/api/chat` 与 `/api/video/extract*`、`/api/cards/from-link|from-text` 调 LLM/ASR 前检查并
  计数（`llm_usage` UPSERT）；超限返回 `429` + 人话提示「今日次数已用完，明天再来吧」。
- 转写共享缓存：`extract` 流程解析出 `video_id` 后先查 `transcripts(video_id, asr_model)`，
  命中则跳过下载+ASR（也不计入 extract 限额）；未命中转写成功后写入。
  替代现在「转写不缓存」的行为（`douyin_downloader` 内文件级 transcript 缓存逻辑移除，
  统一走数据库缓存）。
- 小程序/Web 对 429 展示友好提示。

**验收**：
- 测试覆盖：超限 429、跨天重置、不同 level 限额不同、转写缓存命中跳过 ASR 且跨用户生效；
- 视频缓存（`VIDEO_CACHE_DIR`）行为保持不变。

## M3 · 小程序 Tab 重排 + 登录引导

**改动文件**：`miniprogram/app.json`、`custom-tab-bar/`、`utils/auth.js`、`utils/tab.js`、
`pages/chat/*`、`pages/collect/*`、`pages/knowledge/*`

- `app.json`：`pages` 首项与 tabBar 顺序改为 `collect | chat | knowledge`，
  **入口页 = `pages/chat/chat`**（pages 数组第一项为 chat）；custom-tab-bar 顺序与默认
  选中同步为对话居中。
- Tab 文案：收集 / AI 助手（或「对话」，实施时按 UI 效果定）/ 知识库。
- 登录门槛：`app.js` 启动静默 `ensureLogin()`；失败或 401 时页面显示**登录引导卡片**
  （品牌 + 一句话价值说明 +「微信一键登录」按钮），登录成功后刷新页面数据；
  三个 Tab 页共用该逻辑（可抽 `components/login-guard` 或页面 mixin）。
- `utils/request.js`：401 时清 token → 触发登录引导（不再无限静默重试）。

**验收**：
- 开发者工具中：启动直接落在对话页，Tab 顺序为 收集|对话|知识库，对话居中高亮；
- 模拟 401/未登录：三个页面均出现登录引导卡片，点按钮后恢复正常；
- 键盘弹起、safe-area 等既有布局不回归。

## M4 · 知识库管理页 Markdown 渲染 + 收集页适配

**改动文件**：`miniprogram/pages/knowledge/*`、`pages/collect/*`、`components/`

- 卡片详情用 markdown 渲染（优先小程序 `rich-text` + 轻量 md→节点转换，
  避免引入重依赖；效果不足再评估 towxml）。
- 编辑：`t-textarea` 直接编辑 markdown 原文；保存走 `PUT /api/cards/{id}`。
- 详情增加「公开共享」开关（`is_public`）。
- 收集页保存成功预览改为 markdown 摘要（标题 + 前几行）。

**验收**：开发者工具中列表/详情/编辑/删除/共享开关全链路可用；含列表、粗体、
分级标题的 markdown 正常显示。

## M5 · 共享知识检索与引用标注

**改动文件**：`web/core/retrieve.py`、`web/core/qa.py`、`web/app.py`、
`miniprogram/pages/chat/*`、`components/chat-message/*`、`tests/`

- 检索范围：`user_id = 我` OR (`is_public = 1` AND `user_id != 我`)；自己的知识排序加权优先。
- 引用对象增加 `source: "mine" | "shared"`；对话气泡引用区分「我的知识 / 共享知识」标签。
- 知识库管理页仍只列自己的知识（共享池不提供独立浏览页，保持简单；后续可加）。

**验收**：测试覆盖「A 的公开知识可被 B 检索、私有知识不可见、引用带 source 标注」；
对话页两种引用标签可见。

## M6 · 收尾：Web 调试端适配 + 验收 + 部署清单

- `web/templates/index.html` 适配 markdown 卡片与 429 提示（最小改动，保持可用即可）。
- 小程序真机矩阵验收（iOS / Android：Tab 固定、键盘、safe-area、登录流程）。
- 部署清单核对：公网 HTTPS + 备案域名、微信公众平台 request/uploadFile 合法域名、
  `.env` 完整配置（`WECHAT_APPID/SECRET`、`SESSION_SECRET`、`ALLOW_LOCAL_AUTH=0`）。
- 更新 `PROGRESS.md` / `README.md` 收尾。

---

## 待确认事项（用户拍板后开工）

1. **共享默认值**：知识默认公开（`is_public=1`，推荐，符合「共享知识为主」）还是默认私有？
2. **限额默认值**：level 0 每日对话 20 次、链接提取 10 次，是否合适？
3. **中间 Tab 文案**：「AI 助手」还是「对话」？
4. **Web 端**：确认「保留但冻结（仅调试用）」的定位？
5. **旧数据**：确认无需保留任何现网数据，M1 直接改 schema、删除迁移代码？

## 实施规范（给后续 agent）

- 每任务一个 `cursor/` 前缀分支 + PR；小步提交。
- TDD：先写 `tests/` 再实现；`python -m pytest` 必须全绿。
- 依赖注入沿用 `get_db / get_llm_client / get_current_user`，测试不触网。
- 小程序改动必须在微信开发者工具（或按 `miniprogram/README.md` 构建）手动验证并留截图/录屏。
- 用户可见文案不出现 LLM / ASR / Prompt / API Key 等技术词。
- 完成任务后更新 `PROGRESS.md` 状态表。
