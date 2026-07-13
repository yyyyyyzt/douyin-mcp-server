# AGENTS.md

## Cursor Cloud specific instructions

This is a Python (>=3.10) project managed by **uv** (`pyproject.toml` + `uv.lock`). The
startup update script already runs `uv sync`, so the `.venv` is present and dependencies
(including the `dev` group: `pytest`, `httpx`) are installed before a session starts.

### Environment notes
- `~/.bashrc` auto-activates `/workspace/.venv` and adds `~/.local/bin` (uv) to `PATH`.
  So in a normal login shell, `python`, `pytest`, and `uv` are all available directly.
- `ffmpeg` is a system dependency used by audio extraction; it is preinstalled on the image.
  If it is ever missing, install with `apt-get install -y ffmpeg` (not part of `uv sync`).

### Tests
- Run directly: `python -m pytest` (equivalently `uv run python -m pytest`).
- Smoke tests live in `tests/` and avoid network calls (they only check imports and the
  WebUI `/api/health` endpoint via httpx's ASGI transport).

### Services / how to run
- **WebUI** (FastAPI + uvicorn): `python web/app.py` → http://localhost:8080
  (override port with `PORT`). `web/app.py` imports the downloader from
  `douyin-video/scripts/douyin_downloader.py` by inserting that dir onto `sys.path`.
- **MCP server** (stdio): `douyin-mcp-server` or `python -m douyin_mcp_server`.
- **CLI**: `python douyin-video/scripts/douyin_downloader.py --help`.

### Gotchas
- API Key 配置在项目根目录 `.env`（复制 `.env.example`），不在浏览器设置；用户可在界面选择 LLM/ASR 模型。
- Transcript extraction (`extract_*` / "提取文案") requires `API_KEY` in `.env`
  (aliyun/SiliconFlow ASR key). Without it the app returns a graceful "请先配置 API Key"
  error — this is expected, not a bug.
- "获取信息 / parse info" needs live network access to Douyin and a *currently valid*
  share link. Expired/sample links return app-level errors like "list index out of range";
  that means the stack works but the link is stale, not that the environment is broken.

### 微信小程序 / 多用户（任务 10~14，见 docs/WECHAT_MINIPROGRAM_PLAN.md）
- 计划已确认：保留 FastAPI JSON API；新增微信原生小程序 `miniprogram/`；后端微信登录 +
  按 `user_id` 隔离；WebUI 用 `ALLOW_LOCAL_AUTH=1` + `POST /api/auth/local` 兼容。
- 配置（实施后）：`WECHAT_APPID` / `WECHAT_SECRET` / `SESSION_SECRET` / `ALLOW_LOCAL_AUTH`。
- 本地调试小程序：微信开发者工具打开 `miniprogram/`，详情里勾选「不校验合法域名」；
  后端需对本机或内网 HTTPS（或工具关闭域名校验后用 http 开发地址）。
- 不要把 `API_KEY` / `WECHAT_SECRET` 写进小程序代码；密钥只留在服务端 `.env`。
- 上线需：备案域名 + HTTPS，并在微信公众平台配置 request / uploadFile 合法域名。
