# AI 装修监理助手 · 总体设计文档

> 本文件是项目的"单一事实来源（Single Source of Truth）"，描述目标、架构、数据模型、
> 接口契约、防幻觉策略与关键技术决策。任何后续开发（包括新启动的 agent）都应先读本文件，
> 再读 [`../PROGRESS.md`](../PROGRESS.md) 了解当前进度与下一步。

---

## 1. 项目起点（第一性原理）

- **用户**：仅作者本人，无多用户、无登录、无权限。
- **目标**：把在短视频平台上认可的装修知识，沉淀为结构化卡片；与装修公司沟通时，
  基于这些卡片回答问题，**严格防止模型幻觉**。
- **范围**：只做最核心的「存知识」和「问知识」两条链路。分享、协作、版本化、反馈闭环暂不做。
- **形态**：先做一个可自托管的 Web 应用（移动优先 + PWA）；**长远目标是推广为微信小程序**，
  因此后端必须是干净、前后端解耦的 JSON API。

### 与原始仓库的关系

本项目构建在 `douyin-mcp-server`（短视频无水印下载 + 语音转文案）之上。原仓库的
抖音解析/下载/转写能力，正好补上了"知识录入"最难的一环：**用户无需手动誊抄文案，
粘贴一个分享链接即可自动得到文案**。这是本产品"真正易用"的关键。

---

## 2. 技术栈

| 层 | 选择 | 原因 |
|---|------|------|
| 后端 | Python + FastAPI | 复用现有 WebUI 工程，AI 生态成熟 |
| 数据库 | SQLite + FTS5(trigram) | 零配置、单文件；trigram 分词器支持中文子串检索 |
| 前端 | 原生 HTML + Tailwind(CDN) + Alpine.js | 零构建，单页即可；后续可平移到小程序 |
| LLM | OpenAI 兼容接口（默认硅基流动） | **供应商可替换**，结构化与问答统一一套客户端 |
| 语音识别 | 硅基流动 SenseVoice / 阿里云百炼 | 复用原仓库能力 |
| 向量检索 | 暂不做 | 初期知识量少，关键词 + FTS5 足够；保留后续扩展空间 |
| 部署 | 本地 / 单机 Docker | 自用，无需公网 |

---

## 3. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  前端（web/templates/index.html，Tailwind + Alpine）           │
│  Tab1 提取  |  Tab2 知识库  |  Tab3 问答        （后续 PWA 化） │
└───────────────┬─────────────────────────────────────────────┘
                │ fetch JSON
┌───────────────▼─────────────────────────────────────────────┐
│  FastAPI（web/app.py）                                         │
│   /api/video/*      抖音解析/转写/下载（已有）                  │
│   /api/cards/*      知识卡片录入/列表/详情（部分完成）          │
│   /api/chat         基于知识库的问答（待开发）                  │
│   依赖注入：get_db / get_llm_client（便于测试覆盖）            │
└───┬───────────────┬───────────────┬──────────────┬───────────┘
    │               │               │              │
┌───▼────┐   ┌──────▼─────┐   ┌─────▼──────┐  ┌────▼─────────────┐
│core/db │   │core/llm    │   │core/       │  │douyin_downloader │
│SQLite  │   │OpenAI兼容  │   │structure   │  │解析/下载/转写     │
│+FTS5   │   │可替换供应商│   │文案->卡片  │  │（原仓库脚本）     │
└────────┘   └────────────┘   └────────────┘  └──────────────────┘
    │
┌───▼──────────────────────────────────┐
│ data/knowledge.db （已 gitignore）     │
└───────────────────────────────────────┘
```

### 目录结构

```
douyin-mcp-server/
├── web/
│   ├── app.py                  # FastAPI 应用（抖音提取 + 知识库 + 问答）
│   ├── core/                   # 装修助手核心
│   │   ├── db.py               # SQLite + FTS5 存储与检索
│   │   ├── llm.py              # OpenAI 兼容、可替换供应商的 LLM 客户端
│   │   └── structure.py        # 文案 -> 结构化知识卡片
│   └── templates/index.html    # 单页前端（待加知识库/问答 Tab）
├── douyin-video/scripts/douyin_downloader.py   # 解析/下载/转写（复用）
├── douyin_mcp_server/          # MCP server（原仓库）
├── tests/                      # pytest 测试（TDD）
├── data/                       # SQLite 文件（gitignore）
├── docs/DESIGN.md              # 本文件
├── PROGRESS.md                 # 进度与任务分解
└── AGENTS.md                   # 云端 agent 环境说明
```

---

## 4. 数据模型

主表 `knowledge_cards` + 外部内容 FTS5 虚拟表 `knowledge_fts`（trigram 分词），
通过触发器保持同步。

```sql
CREATE TABLE knowledge_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT,                 -- 阶段：水电/泥木/油漆/防水/拆改/验收...
    title TEXT,
    raw_text TEXT NOT NULL,     -- 原始文案（转写或粘贴）
    structured_json TEXT,       -- AI 结构化结果（stage/title/steps）
    source_type TEXT DEFAULT 'manual',  -- 'manual' | 'douyin_link'
    source_url TEXT,            -- 抖音分享链接（来源追溯）
    video_id TEXT UNIQUE,       -- 抖音视频 ID，用于去重
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    title, raw_text,
    content='knowledge_cards', content_rowid='id',
    tokenize='trigram'
);
-- + AFTER INSERT/UPDATE/DELETE 触发器保持 FTS 同步
```

### 结构化卡片 JSON schema

```json
{
  "stage": "水电改造",
  "title": "冷热水管走顶规范",
  "steps": [
    {"order": 1, "action": "弹线定位", "detail": "用激光水平仪", "standard": "误差≤2mm", "warning": "避开承重墙和电线管"}
  ]
}
```

> 原文（或对应片段）存于 `raw_text` 列；`structured_json` 只存结构化部分，不重复存原文。

---

## 5. API 契约

> 所有接口返回 JSON；前后端解耦，便于后续接入微信小程序。

### 已实现

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 + ASR Key 配置状态 |
| POST | `/api/video/info` | 抖音链接 → 视频信息/下载链接（无需 Key）|
| POST | `/api/video/extract` | 抖音链接 → 转写文案（需 ASR Key）|
| GET | `/api/video/download` | 代理下载无水印视频 |
| POST | `/api/cards/from-text` | 粘贴文案 → AI 结构化 → 入库（支持多卡）|
| POST | `/api/cards/from-link` | 抖音链接 → 转写 → 结构化 → 入库（异步，返回 `task_id`）|
| GET | `/api/cards/task/{task_id}` | 查询链接录入任务进度/结果 |
| GET | `/api/cards?stage=` | 卡片列表（可按阶段筛选）|
| GET | `/api/cards/{id}` | 卡片详情（含解析后的 steps）|
| PUT | `/api/cards/{id}` | 编辑卡片（只改文本，不重新调 AI，同步 structured_json）|
| DELETE | `/api/cards/{id}` | 删除卡片 |
| POST | `/api/chat` | 问答：检索 → 拼 prompt → LLM → 带引用回答（含 `grounded`）|

`/api/cards/from-text` 响应示例：

```json
{
  "success": true,
  "cards": [
    {"id": 1, "stage": "水电改造", "title": "冷热水管走顶规范",
     "raw_text": "...", "structured_json": "...", "steps": [...],
     "created_at": "...", "video_id": null}
  ]
}
```

### 待实现（契约预定义，便于后续 agent 对齐）

| 方法 | 路径 | 说明 | 任务 |
|---|---|---|---|
| —（前端）| `web/templates/index.html` | 三 Tab（提取/知识库/问答）+ PWA | 8 |

`/api/chat` 响应结构（已实现）：

```json
{
  "success": true,
  "answer": "……",
  "grounded": true,
  "citations": [
    {"id": 1, "title": "冷热水管走顶规范", "excerpt": "...", "score": 3.2}
  ]
}
```

---

## 6. 防幻觉策略（核心，必须实现）

1. **Prompt 约束**（任务 6/7）：
   > 你是一名私人装修监理助手，只能根据以下提供的知识片段回答问题。如果片段中没有任何相关信息，
   > 你必须先说"根据你当前的知识库，未找到相关标准"，然后可以补充一段以"以下是通用知识，仅供参考："
   > 开头的建议。绝对不要编造知识库中没有的内容。

2. **检索阈值**：FTS5 先判断是否有命中；有命中再用 `bm25()` 排序取 Top K（K=5）。
   - 注意：SQLite `bm25()` **越小越相关**。`db.search_cards` 已将其转为 `score = -bm25`
     的正向分值（**越大越相关**），上层据此设经验阈值（无命中或最高分低于阈值 → 判定"无依据"）。
   - trigram 分词器要求查询长度 ≥ 3 字符；过短查询需在 `retrieve` 层做兜底（如 LIKE）。
   - **实现补充（`web/core/retrieve.py`）**：整句短语 FTS 对「自然语言整句提问」几乎不命中，
     故在其之上增加 **3-gram 重叠召回**——把问题切成 3 字片段分别检索、按命中片段数排序，
     实现关键词级别的重合召回；再以整句 LIKE 兜底。`grounded` 判定 = 有召回且最高分 ≥
     `CHAT_MIN_SCORE`（默认 0.0，可调高以要求更强相关）。

3. **前端展示**：无引用（`grounded=false`）时，回答顶部用黄色警告条提示
   "以下回答未基于你的个人知识库"。

---

## 7. UI/UX 原则（"真正好用"）

- **移动优先 + PWA**：作者在手机上刷视频，录入动作也应在手机上一气呵成
  （复制分享链接 → 粘贴 → 自动入库）。加 `manifest.json` 即可"添加到主屏幕"。
- **一键化录入**：链接版录入只需一个输入框 + 一个按钮，实时显示进度，
  完成后弹出卡片预览供确认/微调（阶段、标题）。
- **问答带引用**：回答下方折叠展示引用卡片，可点击查看原文。
- 顶部三 Tab：提取 / 知识库 / 问答。沿用现有 Tailwind + Alpine，零构建。

---

## 8. 关键技术决策与取舍

| 决策 | 选择 | 理由 / 取舍 |
|---|---|---|
| 中文全文检索 | FTS5 `tokenize='trigram'` | 默认分词器不切中文；trigram 零依赖支持子串检索（需 SQLite ≥ 3.34）。更高精度可后续上 jieba |
| bm25 方向 | 转为正向 `score` | SQLite bm25 越小越相关，统一为越大越相关便于设阈值 |
| LLM 供应商 | OpenAI 兼容 + env 配置 | 默认硅基流动（与 ASR 同平台，一个 Key 搞定），随时可换 OpenAI/DeepSeek/本地模型 |
| 录入耗时 | 链接版需异步 | 下载+转写+结构化可能 20~60s，必须异步 + 进度，避免前端卡死 |
| 去重 | `video_id UNIQUE` | 同一视频不重复入库 |
| 依赖注入 | `get_db`/`get_llm_client` | 测试可覆盖，无需真实网络/Key |
| 测试策略 | TDD | 先写测试再实现，核心逻辑全覆盖 |

---

## 9. 配置项（环境变量）

| 变量 | 默认 | 用途 |
|---|---|---|
| `API_KEY` | — | 语音识别（ASR）密钥，也作为 LLM_API_KEY 的回退 |
| `LLM_API_KEY` | 回退 `API_KEY` | LLM 密钥 |
| `LLM_BASE_URL` | `https://api.siliconflow.cn/v1` | LLM 接口地址（可换供应商）|
| `LLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | LLM 模型名 |
| `LLM_TIMEOUT` | `60` | LLM 请求超时（秒）|
| `LLM_MAX_RETRIES` | `3` | LLM 重试次数（指数退避）|
| `KNOWLEDGE_DB` | `data/knowledge.db` | SQLite 文件路径 |
| `CHAT_MIN_SCORE` | `0.0` | 问答 `grounded` 判定阈值（最高召回分低于此 → 判为无依据）|
| `PORT` | `8080` | WebUI 端口 |

---

## 10. 不做的事情（红线）

- 不引入用户系统、登录、OAuth。
- 不做社交分享、副本分支、版本管理。
- 不做向量数据库、图数据库（保留后续扩展）。
- 不做链接自动抓取以外的反爬对抗（人工粘贴链接优先）。
- 不做商业化/社区功能。

> 例外：长远会做微信小程序前端用于推广，但**后端契约保持不变**。
