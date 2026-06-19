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
- Transcript extraction (`extract_*` / "提取文案") requires the `API_KEY` env var
  (aliyun/SiliconFlow ASR key). Without it the app returns a graceful "请先配置 API Key"
  error — this is expected, not a bug.
- "获取信息 / parse info" needs live network access to Douyin and a *currently valid*
  share link. Expired/sample links return app-level errors like "list index out of range";
  that means the stack works but the link is stale, not that the environment is broken.
