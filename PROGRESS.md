# 开发进度

> 新 agent 上手入口：先读 [`docs/DESIGN.md`](docs/DESIGN.md)，再读 [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md)，最后看本文件。
> 环境与运行方式见 [`AGENTS.md`](AGENTS.md)。

## 当前阶段：v2 改版（对话为中心 + 存储精简）

| 任务 | 内容 | 状态 |
|---|---|---|
| M0 | 清理遗留（删 MCP server / skill / 过时文档），文档改版 | ✅ |
| M1 | 后端：知识 Markdown 化 + schema 精简 | ✅ |
| M2 | 后端：只限链接提取 + 转写共享缓存 | ✅ |
| M3 | 小程序：Tab 重排（AI 助手居中首页）+ 登录引导 | ✅ |
| M4 | 小程序：知识库 Markdown 渲染 + 收集页适配 | ✅ |
| M5 | 共享知识检索与分享 | ⏸ 延期 |
| M6 | Web 调试端最小适配 + 收尾 | ✅ |

### 已确认决策

1. 知识默认私有（`is_public=0`）；公开分享下一步规划。
2. 不限制对话；只限制链接提取（默认 10 次/日）。
3. 中间 Tab 文案：**AI 助手**。
4. Web 冻结，仅调试用。
5. 无历史数据，直接改 schema。

### M1~M6 落地要点

- Schema：`content_md`、`is_public`、`users.level`、`llm_usage.extract_calls`、`transcripts`；删除 `raw_text`/`structured_json` 与迁移代码。
- 小程序：默认落地 `pages/chat/chat`；Tab = 收集 | AI 助手 | 知识库；`login-guard` 组件；`utils/markdown.js` 轻量渲染。
- 转写缓存命中不计入提取限额；对话永不限额。

## 已完成的历史阶段（v1，均已合入 main）

- 任务 1~9：知识库 MVP、检索问答、防幻觉、Web PWA。
- 任务 10~14：微信登录、用户隔离、小程序三 Tab（TDesign）。

## 开发规范

1. TDD：`python -m pytest` 保持全绿。
2. 依赖注入：`get_db / get_llm_client / get_current_user / get_extractor / get_video_info_fn`。
3. 密钥只在服务端 `.env`。
4. 小程序改动需开发者工具/真机验证。
5. `cursor/` 前缀分支，完成后更新本文件。
