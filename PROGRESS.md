# 开发进度与任务分解

> 配套阅读：[`docs/DESIGN.md`](docs/DESIGN.md)（总体设计 / 架构 / 接口契约 / 防幻觉策略）。
> 本文件追踪"做到哪了、下一步做什么、验收标准是什么"，是新 agent 接手的入口。

最后更新：完成任务 1~7（最小闭环 + 抖音链接一键入库 + 卡片编辑/删除 + 检索问答 + 防幻觉），并纳入云端环境配置。

---

## 总览

| 任务 | 内容 | 状态 |
|---|---|---|
| 1 | SQLite + FTS5 数据层 | ✅ 已完成 |
| 2 | LLM 封装（OpenAI 兼容、可替换、重试）| ✅ 已完成 |
| 3 | 文本录入：文案 → 结构化 → 存库 + API | ✅ 已完成 |
| 4 | 抖音链接一键入库（异步 + 进度 + 去重）| ✅ 已完成 |
| 5 | 卡片编辑 / 删除 API | ✅ 已完成 |
| 6 | 检索层 + 问答 API | ✅ 已完成 |
| 7 | 防幻觉（阈值 + 引用 + 警告）| ✅ 已完成（后端）|
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

### 任务 5 · 卡片编辑 / 删除 ✅
- 文件：`web/app.py`（测试 `tests/test_api_cards_edit.py`）
- 能力：
  - `PUT /api/cards/{id}`：局部更新文本字段 `stage/title/raw_text/steps`（均可选），
    **不重新调 AI**；同步重写 `structured_json`（保持 stage/title/steps 一致）；
    未提供的字段保持不变；保留 `video_id` 等来源字段。
  - `DELETE /api/cards/{id}`：删除卡片，不存在返回 404。
- 要点：复用 `db.update_card / db.delete_card`，FTS 索引由 AFTER UPDATE/DELETE 触发器
  自动同步（测试用 `db.search_cards` 断言编辑后新标题命中、旧标题/已删卡片不再命中）；
  空 body 或空 `raw_text` 返回 400；`steps` 经 `structure._normalize_step` 归一化。

### 任务 6 · 检索 + 问答 ✅
- 文件：`web/core/retrieve.py`、`web/core/qa.py`（测试 `tests/test_retrieve.py`、`tests/test_qa.py`、
  `tests/test_api_chat.py`）
- 检索 `retrieve.retrieve(conn, query, top_k=5)`：
  1) 整句短语 FTS（短关键词精确路径）→ 2) **3-gram 重叠召回**（把问题切 3 字片段分别检索，
     按命中片段数排序，解决「整句自然语言提问无法短语命中」的问题）→ 3) 整句 LIKE 兜底；
     < 3 字超短查询直接 LIKE。
- 问答 `qa.build_messages(question, cards, grounded)` + `qa.to_citation(card)`：把命中卡片的
  标题/阶段/步骤/原文注入 prompt，约束模型「只能依据片段作答」；引用对象含 id/title/stage/excerpt/score。
- API `POST /api/chat`：检索 → 拼 prompt → `llm.chat` → 返回 `answer + grounded + citations`。

### 任务 7 · 防幻觉 ✅（后端）
- `retrieve.is_grounded(results, min_score)`：无召回或最高分 < 阈值 `CHAT_MIN_SCORE`（默认 0.0）
  → `grounded=false`，prompt 切换为 `SYSTEM_UNGROUNDED`（先声明「根据你当前的知识库，未找到相关标准」，
  再给「以下是通用知识，仅供参考：」的免责建议），且不返回任何引用。
- 真实 LLM 验证：相关问题 `grounded=true` 并引用知识库标准；无关问题 `grounded=false` 且带声明，
  不编造个人知识。前端黄色警告条留待任务 8 依据 `grounded` 字段渲染。

---

## 下一步（待开发任务的验收标准）

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
| `CHAT_MIN_SCORE` | `0.0` | 问答 grounded 判定阈值（最高分低于此判为无依据）|
| `PORT` | `8080` | WebUI 端口 |
