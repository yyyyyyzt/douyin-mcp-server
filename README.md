# AI 装修监理助手

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

把短视频里认可的装修知识，沉淀为**结构化卡片**；与装修公司沟通时，基于这些卡片回答问题，
**严格防止模型幻觉**。粘贴一个抖音分享链接即可自动转写、AI 结构化入库——无需手动誊抄。

> 自用、单机、可自托管的 Web 应用（移动优先 + PWA）；长远目标是推广为微信小程序。

## 📚 文档导航

| 文档 | 内容 |
|---|---|
| [`docs/DESIGN.md`](docs/DESIGN.md) | 总体设计：架构 / 数据模型 / 接口契约 / 防幻觉策略 / 关键决策 |
| [`PROGRESS.md`](PROGRESS.md) | 开发进度、任务分解与验收标准、新 agent 上手指南 |
| [`AGENTS.md`](AGENTS.md) | 云端 agent 环境说明（uv / 测试 / 运行方式）|

## 🚦 当前进度

- ✅ 任务 1~3：知识库存储（SQLite + FTS5 中文检索）、LLM 封装（OpenAI 兼容、可替换供应商）、文本录入与结构化。
- ✅ 任务 4：抖音链接一键入库（异步任务 + 进度查询 + `video_id` 去重）。
- ✅ 任务 5：卡片编辑 / 删除。
- ✅ 任务 6~7：检索 + 问答（带引用）+ 防幻觉（`grounded` 判定 + 无依据声明）。
- ✅ 任务 8：前端三 Tab（提取 / 知识库 / 问答）+ PWA + 移动端适配。

详见 [`PROGRESS.md`](PROGRESS.md)。

## ⚡ 快速开始

```bash
# 1. 安装依赖（项目用 uv 管理，会自动建好 .venv 并装齐依赖）
uv sync

# 2. 配置 LLM / 语音识别密钥（二者可共用一个硅基流动 Key）
export API_KEY="sk-xxx"          # 语音识别（ASR），也作 LLM_API_KEY 的回退
# 可选：替换 LLM 供应商 / 模型
# export LLM_BASE_URL="https://api.siliconflow.cn/v1"
# export LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"

# 3. 启动 WebUI（移动端可“添加到主屏幕”作为 PWA 使用）
uv run python web/app.py        # 访问 http://localhost:8080

# 4. 运行测试（TDD，应全绿）
uv run python -m pytest

# 5. 自测平台 Key 连通性（可选）
uv run python scripts/check_api_keys.py   # --only llm | asr
```

> 💡 获取免费 API Key：[硅基流动](https://cloud.siliconflow.cn/i/TxUlXG3u)（新用户有免费额度）。
> 主要环境变量见 [`docs/DESIGN.md` 第 9 节](docs/DESIGN.md)。

### 🖥️ 三个 Tab

- **提取**：粘贴抖音分享链接 → 获取无水印视频信息 / AI 转写文案，可一键「加入知识库」。
- **知识库**：链接 / 文本两种录入方式；卡片列表支持按阶段筛选、编辑、删除。
- **问答**：基于知识库检索作答并展示引用；无相关知识时显示「未基于个人知识库」黄色警告（防幻觉）。

### 🧩 知识库 API 速查

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/cards/from-text` | 粘贴文案 → AI 结构化 → 入库（支持多卡）|
| `POST` | `/api/cards/from-link` | 抖音链接 → 转写 → 结构化 → 入库（**异步**，返回 `task_id`）|
| `GET` | `/api/cards/task/{task_id}` | 查询链接录入进度（`extracting/structuring/done/duplicate/failed`）|
| `GET` | `/api/cards?stage=` | 卡片列表（可按阶段筛选）|
| `GET` | `/api/cards/{id}` | 卡片详情 |
| `PUT` | `/api/cards/{id}` | 编辑卡片文本（不重新调 AI，同步 `structured_json`）|
| `DELETE` | `/api/cards/{id}` | 删除卡片 |
| `POST` | `/api/chat` | 知识库问答 → 返回 `answer` + `grounded` + `citations`（防幻觉）|

```bash
# 链接一键入库（异步：先拿 task_id，再轮询进度）
curl -X POST localhost:8080/api/cards/from-link -H 'Content-Type: application/json' \
  -d '{"url":"<抖音分享链接或整段分享文案>"}'
curl localhost:8080/api/cards/task/<task_id>

# 基于知识库问答（无相关知识时 grounded=false 并给出声明，不编造）
curl -X POST localhost:8080/api/chat -H 'Content-Type: application/json' \
  -d '{"question":"卫生间防水要刷多高？"}'
```

## 📋 系统要求

| 依赖 | 说明 | 安装方式 |
|------|------|----------|
| uv | Python 包管理 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.10+ | `uv python install 3.12` |
| FFmpeg | 音视频处理（链接转写需要）| `brew install ffmpeg`（macOS）/ `apt install ffmpeg`（Ubuntu）|

## ⚠️ 免责声明

- 本项目仅供学习和研究使用，使用者需遵守相关法律法规。
- 禁止用于侵犯知识产权的行为；作者不对使用本项目产生的损失承担责任。

## 📄 许可证

Apache License 2.0

## 👨‍💻 作者

**yzfly** - [GitHub](https://github.com/yzfly) | [Email](mailto:yz.liu.me@gmail.com)
