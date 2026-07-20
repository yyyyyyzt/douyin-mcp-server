# 自装助手

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

刷到认可的装修知识 → 粘贴分享链接自动转写、整理，存进**自己的知识库** →
和 AI 对话时，AI **严格基于这些知识**回答，绝不编造（防幻觉）。

主形态为**微信原生小程序**（`miniprogram/`，AI 对话为中心）；Web 端（`web/`）仅作
开发调试与自托管兼容入口。

## 📚 文档导航

| 文档 | 内容 |
|---|---|
| [`docs/DESIGN.md`](docs/DESIGN.md) | 总体设计：信息架构 / 数据模型 / API 契约 / 限额与缓存 / 防幻觉 |
| [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md) | v2 改版开发计划（任务分解 + 验收标准，**待确认**）|
| [`PROGRESS.md`](PROGRESS.md) | 进度追踪与开发规范，新 agent 上手入口 |
| [`AGENTS.md`](AGENTS.md) | 云端 agent 环境说明（uv / 测试 / 运行方式）|
| [`miniprogram/README.md`](miniprogram/README.md) | 小程序本地开发（开发者工具 / npm 构建）|

## ⚡ 快速开始

```bash
# 1. 安装依赖（uv 管理，自动建 .venv）
uv sync

# 2. 配置密钥（LLM / 语音识别可共用一个硅基流动 Key）
cp .env.example .env   # 编辑填入 API_KEY 等

# 3. 启动后端（Web 调试界面同端口）
uv run python web/app.py        # http://localhost:8080

# 4. 运行测试（TDD，应全绿）
uv run python -m pytest

# 5. 可选：自测平台 Key 连通性
uv run python scripts/check_api_keys.py   # --only llm | asr
```

> 💡 免费 API Key：[硅基流动](https://cloud.siliconflow.cn/i/TxUlXG3u)。
> 环境变量清单见 [`docs/DESIGN.md` 第 7 节](docs/DESIGN.md)。
> 小程序调试：微信开发者工具打开 `miniprogram/`，见 [`miniprogram/README.md`](miniprogram/README.md)。

## 🖥️ 产品形态（小程序三 Tab）

- **收集**（左）：粘贴抖音分享链接或文字，一键读取、整理并保存到知识库。
- **AI 对话**（中，默认落地页）：基于知识库回答，展示引用；未登录时提供微信一键登录。
- **知识库**（右）：搜索 / 筛选 / 查看 / 编辑 / 删除自己的知识（Markdown）。

## 🧩 API 速查

业务接口需 `Authorization: Bearer <token>`
（`POST /api/auth/wechat/login` 小程序登录；`POST /api/auth/local` 仅 `ALLOW_LOCAL_AUTH=1`）。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/cards/from-text` | 粘贴文字 → AI 整理 → 入库 |
| `POST` | `/api/cards/from-link` | 抖音链接 → 转写 → 整理 → 入库（异步，返回 `task_id`）|
| `GET` | `/api/cards/task/{task_id}` | 查询链接录入进度 |
| `GET/PUT/DELETE` | `/api/cards*` | 列表（`?stage=`）/ 详情 / 编辑 / 删除 |
| `POST` | `/api/documents/parse` | 上传报价单/合同解析 |
| `POST` | `/api/chat` | 对话 → `answer + grounded + citations`（防幻觉）|

完整契约见 [`docs/DESIGN.md` 第 5 节](docs/DESIGN.md)。

## 📋 系统要求

| 依赖 | 说明 | 安装方式 |
|------|------|----------|
| uv | Python 包管理 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.10+ | `uv python install 3.12` |
| FFmpeg | 音视频处理（链接转写需要）| `brew install ffmpeg` / `apt install ffmpeg` |

小程序上线另需：公网 HTTPS + 备案域名、微信公众平台 request/uploadFile 合法域名。

## ⚠️ 免责声明

- 本项目仅供学习和研究使用，使用者需遵守相关法律法规。
- 禁止用于侵犯知识产权的行为；作者不对使用本项目产生的损失承担责任。

## 📄 许可证

Apache License 2.0

## 👨‍💻 作者

**yzfly** - [GitHub](https://github.com/yzfly) | [Email](mailto:yz.liu.me@gmail.com)
