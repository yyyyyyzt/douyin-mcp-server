# AGENTS.md

## Cursor Cloud specific instructions

This is a Python (>=3.10) project managed by **uv** (`pyproject.toml` + `uv.lock`). The
startup update script already runs `uv sync`, so the `.venv` is present and dependencies
(including the `dev` group: `pytest`, `httpx`) are installed before a session starts.

### 必读文档

- [`docs/DESIGN.md`](docs/DESIGN.md)：设计与契约（单一事实来源）。
- [`docs/DEV_PLAN.md`](docs/DEV_PLAN.md)：v2 改版任务分解与验收标准。
- [`PROGRESS.md`](PROGRESS.md)：当前进度与开发规范。

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
- **Backend + Web 调试界面** (FastAPI + uvicorn): `python web/app.py` → http://localhost:8080
 (override port with `PORT`). `web/app.py` imports the downloader from
 `douyin-video/scripts/douyin_downloader.py` by inserting that dir onto `sys.path`.
- **小程序**：微信开发者工具打开 `miniprogram/`（云环境无法运行开发者工具，只能改代码 +
 后端接口级测试；UI 需用户真机/工具验收）。
- **CLI**: `python douyin-video/scripts/douyin_downloader.py --help`.

### Gotchas
- API Key 配置在项目根目录 `.env`（复制 `.env.example`），不在浏览器设置；用户可在界面选择 LLM/ASR 模型。
- Transcript extraction (`extract_*` / "提取文案") requires `API_KEY` in `.env`
 (aliyun/SiliconFlow ASR key). Without it the app returns a graceful "请先配置 API Key"
 error — this is expected, not a bug.
- "获取信息 / parse info" needs live network access to Douyin and a *currently valid*
 share link. Expired/sample links return app-level errors like "list index out of range";
 that means the stack works but the link is stale, not that the environment is broken.

### 微信小程序 / 多用户
- 后端微信登录（`code2session` + HMAC Bearer token）与按 `user_id` 隔离已实现；
 WebUI 用 `ALLOW_LOCAL_AUTH=1` + `POST /api/auth/local` 兼容。
- 配置：`WECHAT_APPID` / `WECHAT_SECRET` / `SESSION_SECRET` / `ALLOW_LOCAL_AUTH`。
- 本地调试小程序：微信开发者工具打开 `miniprogram/`，详情里勾选「不校验合法域名」；
 npm 构建见 `miniprogram/README.md`。
- 不要把 `API_KEY` / `WECHAT_SECRET` 写进小程序代码；密钥只留在服务端 `.env`。
- 上线需：备案域名 + HTTPS，并在微信公众平台配置 request / uploadFile 合法域名。
