# 开发进度

> 新 agent 上手入口：先读 [`docs/DESIGN.md`](docs/DESIGN.md)（设计与契约），
> 再读 [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md)（任务分解与验收标准），最后看本文件确认进度。
> 环境与运行方式见 [`AGENTS.md`](AGENTS.md)。

## 当前阶段：v2 改版（对话为中心 + 存储精简 + 共享知识）

| 任务 | 内容 | 状态 |
|---|---|---|
| M0 | 清理遗留（删 MCP server / skill 打包 / 过时文档），文档改版 | ✅ 本 PR 完成 |
| M1 | 后端：知识 Markdown 化 + schema 精简 | ⬜ 待确认后开工 |
| M2 | 后端：每日 LLM 限额 + 转写共享缓存 | ⬜ |
| M3 | 小程序：Tab 重排（对话居中为首页）+ 登录引导 | ⬜ |
| M4 | 小程序：知识库管理页 Markdown 渲染 + 收集页适配 | ⬜ |
| M5 | 共享知识检索与引用标注 | ⬜ |
| M6 | 收尾：Web 调试端适配 + 真机验收 + 部署清单 | ⬜ |

任务详情、改动文件与验收标准见 [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md)。
**开工前需用户确认 DEV_PLAN 末尾「待确认事项」。**

## 已完成的历史阶段（v1，均已合入 main）

- **任务 1~9**：SQLite+FTS5 数据层、LLM 封装、文本/链接录入（异步+去重）、卡片
  CRUD、检索+问答、防幻觉、Web 三 Tab PWA 及手机极简 UI。
- **任务 10~14**：微信登录（`code2session` + HMAC token）、按 `user_id` 隔离、
  Web `ALLOW_LOCAL_AUTH` 兼容、原生小程序三 Tab（TDesign + custom-tab-bar +
  可扩展对话架构）、后端测试补齐。
- **M0**：删除 `douyin_mcp_server/`、`douyin-video.skill`、`douyin-video.png`、
  `douyin-video/SKILL.md`；`pyproject.toml` 更名 `zizhuang-assistant`、移除 `mcp`
  依赖；文档收敛为 DESIGN + DEV_PLAN 两份。

> v1 的实现细节不再单独维护文档，以代码 + `tests/` 为准；设计口径见
> [`docs/DESIGN.md`](docs/DESIGN.md)。

## 开发规范（必读）

1. **TDD**：先在 `tests/` 写用例再实现；`python -m pytest` 保持全绿。
2. **依赖注入**：新接口复用 `get_db / get_llm_client / get_current_user`，测试不触网。
3. **密钥只在服务端**：LLM/ASR/微信密钥全部走 `.env`，绝不进小程序代码。
4. **小程序改动**必须手动验证（微信开发者工具），留截图/录屏。
5. **Git**：`cursor/` 前缀特性分支，小步提交，一个逻辑改动一个 commit，完成后开 PR。
6. **完成任务后**：更新本文件状态表再提交。
