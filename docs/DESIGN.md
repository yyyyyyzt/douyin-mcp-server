# 自装助手 · 总体设计文档

> 本文件是项目的**单一事实来源（Single Source of Truth）**：产品定位、信息架构、
> 架构与数据模型、接口契约、资源节约与限额策略、防幻觉策略。
> 开发前先读本文件，再读 [`DEV_PLAN.md`](DEV_PLAN.md)（任务分解与验收标准）与
> [`../PROGRESS.md`](../PROGRESS.md)（当前进度）。
>
> 文中明确区分「✅ 现状（已实现）」与「🎯 目标（待实施，对应 DEV_PLAN 任务）」。

---

## 1. 产品定位

- **一句话**：刷到认可的装修知识 → 存进自己的知识库 → 和 AI 对话时，AI 严格基于这些知识回答。
- **目标用户**：正在装修、主要用手机、完全不懂 AI 概念的普通用户。
- **主形态**：**微信原生小程序**（`miniprogram/`）。Web（`web/templates/index.html`）仅作
  开发调试与自托管兼容入口，不再新增功能。
- **核心理念**：
  1. **AI 对话是产品的中心**：进入小程序即是对话页（Tab 文案「AI 助手」）；收集与管理知识都是为对话服务的。
  2. **收藏即拥有**：粘贴抖音分享链接即可自动转写、整理、入库，无需手动誊抄。
  3. **知识默认私有**：`is_public` 默认 0；公开后如何分享 → 下一步规划。
  4. **防幻觉**：回答必须声明是否基于用户知识库，绝不编造。
  5. **Web 冻结**：仅不方便使用小程序时调试，不再新增功能。

## 2. 信息架构（🎯 目标，对应 DEV_PLAN 任务 M2）

小程序底部 3 个 Tab，**对话居中且为默认落地页**：

```
┌─────────────────────────────────────┐
│              页面内容                │
├───────────┬───────────┬─────────────┤
│   收集     │  AI 对话   │   知识库    │
│  (左)      │ (中,默认)  │   (右)      │
└───────────┴───────────┴─────────────┘
```

| Tab | 位置 | 职责 | 主动作 |
|---|---|---|---|
| 收集 | 左 | 把刷到的装修经验存起来 | 粘贴链接/文字 → 保存到知识库 |
| **AI 助手** | **中（默认落地页）** | 基于知识库对话问答 | 提问、上传报价单、查看依据 |
| 知识库 | 右 | 管理已保存的知识 | 搜索、筛选、查看、编辑、删除 |

- **未登录用户**：打开小程序先尝试 `wx.login` 静默登录；失败或登录态失效时，
  对话页显示登录引导卡片（「微信一键登录」按钮），点击后完成登录再进入正常流程。
  收集/知识库 Tab 同样受登录门槛保护。
- 设置入口保留在页面右上角（非 Tab），只读展示服务状态与模型选择。
- ✅ 现状：Tab 顺序为 收集|知识库|问答，默认落地收集页，登录失败仅 toast 提示——**需要改**。

### 对话可扩展架构（✅ 已有骨架，保留）

后期「报价单审查 / 装修进度 / 记账 / 预算」等能力统一在对话 Tab 以消息类型扩展
（`miniprogram/utils/chat-scenarios.js` + `components/chat-message` 按 `kind` 分支渲染），
不新开 Tab。当前已接通 `knowledge_qa`（知识问答）与 `quote_review`（报价单审查）。

### 小程序 UI 约定（✅ 已实施，沿用）

- 组件库 [TDesign 小程序](https://tdesign.tencent.com/miniprogram/getting-started) +
  `custom-tab-bar`（`t-tab-bar` fixed/placeholder/safe-area）。
- 页面骨架：`.page-root { display:flex; flex-direction:column; height:100% }`（禁用 `100vh`），
  滚动区 `flex:1; height:0`。
- 设计令牌：主色 `#FF6B4A`、背景 `#FFF8F5`、成功 `#059669`、警告 `#D97706`；
  点击区域 ≥ 88rpx。
- 文案禁止出现 LLM / ASR / Prompt / API Key 等技术词；可信度用「来自你的知识库 /
  没找到你的知识依据」表达。
- 本地构建见 [`../miniprogram/README.md`](../miniprogram/README.md)。

## 3. 技术栈与架构

| 层 | 选择 | 说明 |
|---|---|---|
| 后端 | Python + FastAPI（`web/app.py`） | JSON API，前后端解耦 |
| 数据库 | SQLite + FTS5(trigram) | 零配置单文件；无并发要求，单机即可 |
| 前端（主） | 微信原生小程序 + TDesign | `miniprogram/` |
| 前端（辅） | 单文件 HTML + Tailwind CDN + Alpine.js | `web/templates/index.html`，仅调试用 |
| 鉴权 | 微信 `code2session` + HMAC Bearer token | Web 用 `ALLOW_LOCAL_AUTH=1` 本地登录兼容 |
| LLM / ASR | OpenAI 兼容接口（默认硅基流动） | 供应商可替换；密钥只在服务端 `.env` |
| 视频处理 | `douyin-video/scripts/douyin_downloader.py` + ffmpeg | 解析/下载/转写 |

```
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ 微信原生小程序（主形态）        │  │ WebUI（调试/自托管兼容）        │
│ 收集 | AI对话(默认) | 知识库    │  │ 收集 | 知识库 | 问答           │
└──────────────┬───────────────┘  └──────────────┬───────────────┘
               │ Bearer Token JSON API            │
┌──────────────▼──────────────────────────────────▼──────────────┐
│  FastAPI（web/app.py）                                           │
│   /api/auth/*    微信登录 / 本地登录                              │
│   /api/video/*   抖音解析/转写（视频+转写缓存）                     │
│   /api/cards/*   知识 CRUD（markdown，按 user_id）                │
│   /api/chat      基于知识库的对话（每日限额）                       │
└───┬──────────────┬──────────────┬──────────────┬───────────────┘
┌───▼────┐  ┌──────▼─────┐  ┌─────▼──────┐  ┌────▼─────────────┐
│core/db │  │core/llm    │  │core/auth   │  │douyin_downloader │
│SQLite  │  │OpenAI兼容  │  │wechat+HMAC │  │解析/下载/转写+缓存│
└────────┘  └────────────┘  └────────────┘  └──────────────────┘
```

### 目录结构

```
├── web/
│   ├── app.py                  # FastAPI 应用（鉴权 + 视频提取 + 知识库 + 对话）
│   ├── core/                   # db / llm / auth / wechat / structure / retrieve / qa / documents / prompts / settings
│   ├── templates/index.html    # Web 调试前端
│   └── static/                 # PWA manifest / 图标
├── miniprogram/                # 微信原生小程序（主形态）
├── douyin-video/scripts/douyin_downloader.py   # 抖音解析/下载/转写（含视频缓存）
├── scripts/check_api_keys.py   # LLM/ASR Key 连通性自测
├── tests/                      # pytest（TDD，全部离线）
├── data/                       # SQLite / 缓存（gitignore）
├── docs/DESIGN.md              # 本文件
├── docs/DEV_PLAN.md            # 开发计划（任务分解 + 验收标准）
└── PROGRESS.md                 # 进度追踪
```

## 4. 数据模型（🎯 目标，对应 DEV_PLAN 任务 M1）

原则：**尽量精简**。知识正文统一为 **Markdown**，不再维护 `structured_json`/steps
结构化字段；无并发要求，SQLite 单文件即可。项目尚未投入运行，**直接改 schema，
不写兼容迁移代码**（现有 `db.py` 中 legacy 迁移逻辑一并删除）。

```sql
-- 用户：微信 openid + 等级（限额用）
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    openid TEXT NOT NULL UNIQUE,      -- Web 调试用户为 'local-web'
    unionid TEXT,
    level INTEGER NOT NULL DEFAULT 0, -- 用户等级：0 普通；后期不同等级不同每日限额
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

-- 知识：markdown 正文 + 少量元数据
CREATE TABLE knowledge_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    content_md TEXT NOT NULL,         -- Markdown 正文（唯一正文字段）
    stage TEXT,                       -- 装修阶段标签：水电/防水/泥木/油漆/验收/其他
    source_type TEXT DEFAULT 'manual',-- 'manual' | 'douyin_link'
    source_url TEXT,
    video_id TEXT,
    is_public INTEGER NOT NULL DEFAULT 0,  -- 默认私有；公开分享 UX 下一步规划
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, video_id)         -- 同一用户不重复入库同一视频
);

-- FTS5 全文检索（title + content_md，trigram 中文子串）
CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    title, content_md,
    content='knowledge_cards', content_rowid='id',
    tokenize='trigram'
);
-- + AFTER INSERT/UPDATE/DELETE 触发器保持同步

-- 链接提取每日用量（只限提取，不限对话）：一天一行
CREATE TABLE llm_usage (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,                -- 'YYYY-MM-DD'
    extract_calls INTEGER NOT NULL DEFAULT 0,  -- 链接提取（转写+整理）次数
    PRIMARY KEY (user_id, day)
);

-- 转写共享缓存：同一视频跨用户复用 ASR 结果，节约资源
CREATE TABLE transcripts (
    video_id TEXT NOT NULL,
    asr_model TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, asr_model)
);
```

- ✅ 现状：`users`（无 `level`）、`knowledge_cards`（`raw_text` + `structured_json`）
  已按 `user_id` 隔离；`llm_usage`、`transcripts` 不存在 → 🎯 M1/M2 直接改 schema。
- **检索范围（本期）**：仅自己的知识。`is_public` 字段预留，跨用户共享检索延期。

### 资源节约策略

| 资源 | 策略 | 状态 |
|---|---|---|
| 视频下载 | 按 `video_id` 落盘缓存（`VIDEO_CACHE_DIR`，全局共享），命中则跳过下载 | ✅ 已实现 |
| 语音转写 | `transcripts` 表按 `(video_id, asr_model)` 缓存，跨用户复用，命中则跳过 ASR | 🎯 M2 |
| 链接提取限额 | `llm_usage.extract_calls` + 按 `users.level` 查限额；**对话不限额** | 🎯 M2 |
| 重复收藏 | 同一用户同一 `video_id` 不重复入库 | ✅ 已实现 |

限额默认值（可通过 `DAILY_EXTRACT_LIMIT` 覆盖，不做计费）：

```python
DAILY_EXTRACT_LIMITS = {   # level -> 每日链接提取次数
    0: 10,   # 普通用户
    1: 50,   # 后期高级用户
}
```

## 5. API 契约

所有接口返回 JSON；业务接口需 `Authorization: Bearer <token>`，按 `user_id` 作用域。

### 鉴权（✅ 已实现）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/wechat/login` | 小程序 `wx.login` code → `code2session` → 签发 token |
| POST | `/api/auth/local` | Web 调试登录（仅 `ALLOW_LOCAL_AUTH=1`）|

### 业务（✅ 已实现；🎯 M1 中卡片形状改为 markdown）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` / `/api/config` | 健康检查 / 模型目录（可匿名）|
| POST | `/api/video/info` | 抖音链接 → 视频信息/无水印下载链接 |
| POST | `/api/video/extract` (+`/task/{id}`) | 链接 → 转写文案（异步 + 进度；命中缓存则秒回）|
| GET | `/api/video/download` | 代理下载无水印视频 |
| POST | `/api/cards/structure` / `/api/cards/save` | 文案 → AI 整理（markdown）/ 入库 |
| POST | `/api/cards/from-text` | 粘贴文字 → AI 整理 → 入库 |
| POST | `/api/cards/from-link` (+`/task/{id}`) | 链接 → 转写 → 整理 → 入库（异步）|
| GET/PUT/DELETE | `/api/cards*` | 列表（`?stage=`）/ 详情 / 编辑 / 删除 |
| POST | `/api/documents/parse` | 上传报价单/合同解析 |
| POST | `/api/chat` | 对话：检索 → prompt → LLM → `answer + grounded + citations` |
| GET/PUT/POST | `/api/admin/prompts*` | 提示词调试（需 `X-Admin-Token`）|

🎯 M1 契约变更：卡片对象由 `{raw_text, structured_json, steps}` 简化为
`{id, title, content_md, stage, source_url, video_id, is_public, created_at}`。
🎯 M2：链接提取超限返回 `429 {"error": "今日链接提取次数已用完，明天再来吧"}`；对话不限额。

## 6. 防幻觉策略（✅ 已实现，保持）

1. **Prompt 约束**：只能依据检索到的知识片段回答；无相关片段时必须先声明
   「根据你当前的知识库，未找到相关标准」，再给通用建议。
2. **检索 + 阈值**：`web/core/retrieve.py` 整句短语 FTS → 3-gram 重叠召回 → LIKE 兜底；
   `grounded` = 有召回且最高分 ≥ `CHAT_MIN_SCORE`。
3. **前端表达**：有依据 → 绿色「来自你的知识库」+ 可折叠引用；无依据 → 琥珀色
   「这条回答没有找到你的知识依据，仅供参考」。

## 7. 配置项（环境变量，`.env`）

| 变量 | 默认 | 用途 |
|---|---|---|
| `API_KEY` | — | ASR 密钥（也作 LLM Key 回退）|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 硅基流动 / Qwen3-8B | LLM 配置 |
| `ASR_MODEL` | SenseVoiceSmall | 语音识别模型 |
| `KNOWLEDGE_DB` | `data/knowledge.db` | SQLite 路径 |
| `VIDEO_CACHE_DIR` | `data/video_cache` | 视频缓存目录 |
| `CHAT_MIN_SCORE` | `0.0` | grounded 判定阈值 |
| `WECHAT_APPID` / `WECHAT_SECRET` | — | 小程序登录 |
| `SESSION_SECRET` | — | HMAC 会话签名 |
| `ALLOW_LOCAL_AUTH` | `0` | `1` 时允许 Web 本地登录 |
| `ADMIN_TOKEN` / `PROMPTS_FILE` | — | 提示词调试 |
| `DAILY_EXTRACT_LIMIT` | `10` | 🎯 M2：level 0 每日链接提取限额（对话不限）|
| `PORT` | `8080` | 服务端口 |

## 8. 不做的事情（红线）

- 不做复杂商业化 / 计费；限额只做简单每日计数。
- 不做向量数据库；FTS5 足够，保留扩展空间。
- 不做多实例部署 / Redis 队列；单机 SQLite + 内存任务队列。
- 不引入 uni-app / Taro；小程序用微信原生 + TDesign。
- 不把任何密钥放进小程序客户端。
- Web 前端只维持可用，不再新增功能。
