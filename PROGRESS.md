# 开发进度与任务分解

> 配套阅读：[`docs/DESIGN.md`](docs/DESIGN.md)（总体设计 / 架构 / 接口契约 / 防幻觉策略）。
> 本文件追踪"做到哪了、下一步做什么、验收标准是什么"，是新 agent 接手的入口。

最后更新：完成任务 1~4（最小闭环 + 抖音链接一键入库：异步任务 + 进度查询 + video_id 去重），并纳入云端环境配置。

---

## 总览

| 任务 | 内容 | 状态 |
|---|---|---|
| 1 | SQLite + FTS5 数据层 | ✅ 已完成 |
| 2 | LLM 封装（OpenAI 兼容、可替换、重试）| ✅ 已完成 |
| 3 | 文本录入：文案 → 结构化 → 存库 + API | ✅ 已完成 |
| 4 | 抖音链接一键入库（异步 + 进度 + 去重）| ✅ 已完成 |
| 5 | 卡片编辑 / 删除 API | ⬜ 待开发 |
| 6 | 检索层 + 问答 API | ⬜ 待开发 |
| 7 | 防幻觉（阈值 + 引用 + 警告）| ⬜ 待开发 |
| 8 | 前端三 Tab + PWA + 联调 | ⬜ 待开发 |

> 说明：原始规划把"建 FTS5 索引"列为任务 6、"防幻觉"为任务 7。本进度表中 FTS5 索引
> 已随任务 1 一并落地（`db.search_cards`），故任务 6 聚焦"检索调用 + 问答"，任务 7 聚焦"防幻觉逻辑"。

---

## 已完成详情

### 任务 1 · 数据层 ✅
- 文件：`web/core/db.py`，测试 `tests/test_db.py`
- 能力：`connect / init_db / insert_card / get_card / get_card_by_video_id /
  list_cards / update_card / delete_card / search_cards`
- 要点：FTS5 `trigram` 中文检索；触发器保持索引同步；`video_id UNIQUE` 去重；
  `search_cards` 返回正向 `score`（越大越相关）。

### 任务 2 · LLM 封装 ✅
- 文件：`web/core/llm.py`，测试 `tests/test_llm.py`
- 能力：`LLMClient`（OpenAI 兼容 `chat`，支持 `json_mode`）、`LLMClient.from_env()`、
  `LLMError`；内置超时 + 指数退避重试（网络错误 / 429 / 5xx）。
- 要点：供应商通过 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY` 配置，默认硅基流动，回退 `API_KEY`。

### 任务 3 · 文本录入 ✅
- 文件：`web/core/structure.py`（测试 `tests/test_structure.py`）、`web/app.py`（测试 `tests/test_api_cards.py`）
- 能力：`structure_text(raw_text, llm)` → 一段文案拆为一/多张卡片，JSON 解析失败重试；
  API `POST /api/cards/from-text`、`GET /api/cards`、`GET /api/cards/{id}`。
- 要点：FastAPI 依赖注入 `get_db / get_llm_client`，测试可覆盖。

### 任务 4 · 抖音链接一键入库 ✅
- 文件：`web/app.py`（测试 `tests/test_api_from_link.py`）
- 能力：
  - `POST /api/cards/from-link`：接收抖音分享链接（兼容整段分享文案），后台线程异步执行
    「解析/下载/转写 → 去重 → AI 结构化 → 入库」，立即返回 `task_id`。
  - `GET /api/cards/task/{task_id}`：查询进度，`status` 状态机
    `pending/extracting/structuring/done/duplicate/failed`，附中文 `phase` 与 `progress`。
  - 去重：转写得到 `video_id` 后用 `db.get_card_by_video_id` 判断，已存在则返回 `duplicate`
    并回带已有卡片，不重复插入；并发下 `IntegrityError` 兜底同样转为 `duplicate`。
  - 入库记录 `source_type='douyin_link'`、`source_url`、`video_id`；一段文案拆多卡时，
    受 `video_id UNIQUE` 约束仅第一张携带 `video_id`，其余为 `None`。
- 要点：新增依赖注入 `get_db_path / get_extractor`（`get_db` 改为基于 `get_db_path`），
  测试可 mock `extract_text` 与 LLM、指向临时库，全程不触网。后台任务有顶层异常兜底，
  绝不静默卡死。
- 自测工具：`scripts/check_api_keys.py` 验证 LLM / ASR 平台 Key 连通性（`--only llm|asr`）。

---

## 下一步（待开发任务的验收标准）

### 任务 5 · 卡片编辑 / 删除 ⬜
- `PUT /api/cards/{id}`（只改文本字段：stage/title/raw_text/steps，不重新调 AI；同步更新 structured_json）。
- `DELETE /api/cards/{id}`。
- 复用 `db.update_card / db.delete_card`；FTS 索引由触发器自动同步。
- **验收**：编辑后检索结果随之更新；删除后不再被检索命中（`db` 层测试已验证触发器，补 API 层测试）。

### 任务 6 · 检索 + 问答 ⬜
- 新增 `web/core/retrieve.py`：封装 `db.search_cards`，对 < 3 字的短查询做 LIKE 兜底；输出 Top K。
- `POST /api/chat`：检索 → 拼 prompt（注入命中卡片原文 + 结构化步骤）→ `llm.chat` → 返回 `answer + citations`。
- **验收**：能正确命中相关卡片并在回答中引用标题/步骤。
- **测试**：mock LLM，断言 prompt 含命中卡片、响应含 citations。

### 任务 7 · 防幻觉 ⬜
- 在任务 6 基础上：无命中或最高 `score` 低于经验阈值 → `grounded=false`，
  prompt 切换为"未找到相关标准 + 通用参考（带声明）"。
- 响应增加 `grounded` 字段。
- **验收**：知识库无关问题不会编造个人知识；返回 `grounded=false` 并带声明。
- **测试**：空库 / 无关问题 → grounded=false；相关问题 → grounded=true。

### 任务 8 · 前端 + PWA ⬜
- `web/templates/index.html` 加顶部三 Tab：提取 / 知识库 / 问答。
- 知识库：列表 + 链接/文本录入 + 卡片预览/编辑。
- 问答：聊天流 + 引用折叠 + 无引用黄色警告条。
- PWA：`manifest.json` + 移动端适配。
- **验收**：手机浏览器可粘贴链接入库、可问答看引用。

---

## 给新 agent 的上手指南

1. **先读**：本文件 + `docs/DESIGN.md`，对齐接口契约与防幻觉策略。
2. **环境**：项目用 `uv` 管理（见 `AGENTS.md`）。
   - 正常登录 shell 已自动激活 `.venv`，`python` / `pytest` / `uv` 可直接用。
   - 跑测试：`python -m pytest`（应全绿）。
   - 起服务：`python web/app.py` → http://localhost:8080
3. **开发规范**：
   - **TDD**：先在 `tests/` 写用例，再实现；保持全绿。
   - **依赖注入**：新接口复用 `get_db / get_llm_client`，便于测试覆盖。
   - **不破坏既有接口契约**（小程序前端将依赖它）。
   - LLM 调用统一走 `core/llm.LLMClient`，不要硬编码供应商。
4. **Git**：在 `cursor/` 前缀的特性分支上工作（具体分支名后缀以本 agent 分配的模板为准），
   小步提交、每个逻辑改动一个 commit，完成后推送并开 PR。
5. **完成一个任务后**：更新本文件的状态表与"已完成详情"，再提交。

---

## 关键环境变量（详见 `docs/DESIGN.md` 第 9 节）

| 变量 | 默认 | 用途 |
|---|---|---|
| `API_KEY` | — | 语音识别密钥（也作 LLM Key 回退）|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 硅基流动 / Qwen2.5-7B | LLM 配置（可替换供应商）|
| `KNOWLEDGE_DB` | `data/knowledge.db` | SQLite 路径 |
| `PORT` | `8080` | WebUI 端口 |
