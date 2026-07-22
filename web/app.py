#!/usr/bin/env python3
"""
自装助手 WebUI

启动方式:
    cp .env.example .env   # 填入 API_KEY
    python web/app.py
    # 访问 http://localhost:8080
"""

import os
import sys
import json
import uuid
import sqlite3
import threading
import logging
import time
from pathlib import Path
from typing import Optional, Callable

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))  # 便于 `from core import ...`
sys.path.insert(0, str(Path(__file__).parent.parent / "douyin-video" / "scripts"))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
import requests

# 导入抖音处理模块
from douyin_downloader import get_video_info, extract_text

# 核心模块：知识库存储、LLM、结构化、检索、问答
from core import db, structure, retrieve, qa, documents, prompts
from core import auth as auth_core
from core import wechat as wechat_auth
from core.log_config import setup_logging
from core.llm import LLMClient, LLMError
from core.structure import StructureError
from core.documents import DocumentParseError
from core.settings import (
    ASR_MODEL_CATALOG,
    LLM_MODEL_CATALOG,
    get_daily_extract_limit,
    get_settings,
    resolve_asr_model,
)

setup_logging()
logger = logging.getLogger("zizhuang.app")
http_logger = logging.getLogger("zizhuang.http")

# 知识库数据库路径（可用环境变量覆盖）
DB_PATH = os.getenv(
    "KNOWLEDGE_DB",
    str(Path(__file__).parent.parent / "data" / "knowledge.db"),
)


def _local_auth_enabled() -> bool:
    return os.getenv("ALLOW_LOCAL_AUTH", "0").strip().lower() in ("1", "true", "yes")


def _wechat_configured() -> bool:
    return bool(os.getenv("WECHAT_APPID", "").strip() and os.getenv("WECHAT_SECRET", "").strip())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时确保数据库目录存在并初始化表结构。"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(DB_PATH)
    try:
        db.init_db(conn)
    finally:
        conn.close()
    wechat_ok = _wechat_configured()
    logger.info(
        "started db=%s wechat_configured=%s allow_local_auth=%s",
        DB_PATH,
        wechat_ok,
        _local_auth_enabled(),
    )
    yield


class RequestLogMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求：方法、路径、状态码、耗时。"""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        client = request.client.host if request.client else "-"
        path = request.url.path
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            http_logger.exception(
                "%s %s %s -> error %.1fms",
                client,
                request.method,
                path,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        if path.startswith("/api/"):
            http_logger.info(
                "%s %s %s -> %s %.1fms",
                client,
                request.method,
                path,
                response.status_code,
                elapsed_ms,
            )
        return response


app = FastAPI(title="自装助手", version="2.0.0", lifespan=lifespan)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# 静态资源（PWA 图标 / manifest）
_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# Service Worker：放在根路径以获得整站 scope（缓存静态外壳，API 不缓存）
_SERVICE_WORKER_JS = """
const CACHE = 'zizhuang-assistant-v1';
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.pathname.startsWith('/api/')) return;  // 接口实时请求，不走缓存
  e.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(req))
  );
});
"""


@app.get("/sw.js")
async def service_worker():
    """Service Worker 脚本（根 scope，支持离线外壳与“添加到主屏幕”）。"""
    return Response(content=_SERVICE_WORKER_JS, media_type="application/javascript")


def get_db_path() -> str:
    """知识库 sqlite 路径（依赖注入，便于测试指向临时库）。"""
    return DB_PATH


def get_db(db_path: str = Depends(get_db_path)):
    """每个请求一个连接（依赖注入，便于测试覆盖）。"""
    conn = db.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_llm_client() -> LLMClient:
    """从环境变量构造 LLM 客户端（依赖注入，便于测试覆盖）。"""
    return LLMClient.from_env()


def resolve_llm_client(llm_model: str = "") -> LLMClient:
    """请求级 LLM 客户端：模型可由前端选择，密钥来自服务端 .env。"""
    return LLMClient.resolve(llm_model)


def get_extractor() -> Callable:
    """返回抖音解析/转写函数（依赖注入，便于测试 mock，避免真实下载/转写）。"""
    return extract_text


def get_video_info_fn() -> Callable:
    """返回抖音视频信息解析函数（依赖注入，便于测试 mock）。"""
    return get_video_info


EXTRACT_LIMIT_MSG = "今日链接提取次数已用完，明天再来吧"


def get_current_user(request: Request, conn=Depends(get_db)) -> dict:
    """校验 Bearer token 并返回当前用户。"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = auth_header[7:].strip()
    try:
        payload = auth_core.decode_token(token)
    except auth_core.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    user = db.get_user_by_id(conn, int(payload["uid"]))
    if user is None or user["openid"] != payload["oid"]:
        raise HTTPException(status_code=401, detail="会话无效")
    return user


def _assert_task_owner(task: Optional[dict], user_id: int) -> dict:
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    return task


def _serialize_card(row: dict) -> dict:
    """把数据库行转为 API 卡片（含 content 别名便于前端）。"""
    out = dict(row)
    # 兼容别名：前端可用 content 读写 markdown 正文
    if "content_md" in out and "content" not in out:
        out["content"] = out["content_md"]
    return out


class VideoRequest(BaseModel):
    """视频请求模型"""
    url: str
    llm_model: str = ""  # 可选，覆盖默认 LLM
    asr_model: str = ""  # 可选，覆盖默认 ASR


class VideoInfoResponse(BaseModel):
    """视频信息响应"""
    success: bool
    video_id: str = ""
    title: str = ""
    download_url: str = ""
    error: str = ""


class ExtractResponse(BaseModel):
    """文案提取响应"""
    success: bool
    video_id: str = ""
    title: str = ""
    text: str = ""
    download_url: str = ""
    error: str = ""


class WechatLoginRequest(BaseModel):
    code: str


auth_logger = logging.getLogger("zizhuang.auth")


@app.post("/api/auth/wechat/login")
async def wechat_login(req: WechatLoginRequest, request: Request, conn=Depends(get_db)):
    """小程序 wx.login 的 code → 会话 token。"""
    client = request.client.host if request.client else "-"
    code = (req.code or "").strip()
    code_hint = f"{code[:8]}..." if len(code) > 8 else "(empty)"
    auth_logger.info("wechat login attempt client=%s code=%s", client, code_hint)

    if not code:
        auth_logger.warning("wechat login rejected: empty code client=%s", client)
        raise HTTPException(status_code=400, detail="缺少微信登录 code")

    appid = os.getenv("WECHAT_APPID", "").strip()
    secret = os.getenv("WECHAT_SECRET", "").strip()
    if not appid or not secret:
        auth_logger.warning("wechat login rejected: server not configured client=%s", client)
        raise HTTPException(status_code=503, detail="服务端未配置 WECHAT_APPID / WECHAT_SECRET")

    try:
        data = wechat_auth.code2session(code, appid, secret)
    except wechat_auth.WechatAuthError as e:
        auth_logger.warning("wechat login failed client=%s reason=%s", client, e)
        raise HTTPException(status_code=401, detail=str(e)) from e

    user_id = db.ensure_user(conn, data["openid"], data.get("unionid"))
    db.touch_user_login(conn, user_id)
    user = db.get_user_by_id(conn, user_id)
    token = auth_core.issue_token(user_id, user["openid"])
    auth_logger.info(
        "wechat login ok client=%s user_id=%s openid_prefix=%s",
        client,
        user_id,
        str(user["openid"])[:8],
    )
    return {"success": True, "token": token, "user": user}


@app.post("/api/auth/local")
async def local_login(conn=Depends(get_db)):
    """Web 兼容本地登录（仅 ALLOW_LOCAL_AUTH=1）。"""
    if not _local_auth_enabled():
        raise HTTPException(status_code=403, detail="本地登录未启用")
    user_id = db.ensure_local_web_user(conn)
    db.touch_user_login(conn, user_id)
    user = db.get_user_by_id(conn, user_id)
    token = auth_core.issue_token(user_id, user["openid"])
    return {"success": True, "token": token, "user": user}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页面"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """健康检查"""
    settings = get_settings()
    return {
        "status": "ok",
        "api_key_configured": settings.api_configured,
        "wechat_configured": _wechat_configured(),
    }


@app.get("/api/config")
async def app_config():
    """前端模型选择：可选模型目录与默认值（密钥不暴露）。"""
    settings = get_settings()
    return {
        "api_key_configured": settings.api_configured,
        "wechat_configured": _wechat_configured(),
        "defaults": {
            "llm_model": settings.llm_model,
            "asr_model": settings.asr_model,
        },
        "llm_models": LLM_MODEL_CATALOG,
        "asr_models": ASR_MODEL_CATALOG,
        "admin_token_required": bool(os.getenv("ADMIN_TOKEN", "").strip()),
    }


def _verify_admin(request: Request) -> None:
    """可选管理员令牌：未配置 ADMIN_TOKEN 时视为单机自用开放。"""
    expected = os.getenv("ADMIN_TOKEN", "").strip()
    if not expected:
        return
    got = request.headers.get("X-Admin-Token", "").strip()
    if got != expected:
        raise HTTPException(status_code=403, detail="需要管理员令牌")


class PromptsUpdateRequest(BaseModel):
    prompts: dict[str, str]


@app.get("/api/admin/prompts")
async def admin_list_prompts(request: Request):
    """列出全部系统提示词（含元数据），供超级管理员调试。"""
    _verify_admin(request)
    return {
        "success": True,
        "prompts": prompts.list_for_admin(),
        "admin_token_required": bool(os.getenv("ADMIN_TOKEN", "").strip()),
    }


@app.put("/api/admin/prompts")
async def admin_save_prompts(req: PromptsUpdateRequest, request: Request):
    """保存自定义提示词到 data/prompts.json。"""
    _verify_admin(request)
    prompts.save(req.prompts)
    return {"success": True, "prompts": prompts.list_for_admin()}


@app.post("/api/admin/prompts/reset")
async def admin_reset_prompts(request: Request):
    """恢复全部提示词为内置默认。"""
    _verify_admin(request)
    prompts.reset()
    return {"success": True, "prompts": prompts.list_for_admin()}


@app.post("/api/video/info", response_model=VideoInfoResponse)
async def get_info(req: VideoRequest):
    """获取视频信息（无需 API_KEY）"""
    try:
        info = get_video_info(req.url)
        return VideoInfoResponse(
            success=True,
            video_id=info["video_id"],
            title=info["title"],
            download_url=info["url"]
        )
    except Exception as e:
        return VideoInfoResponse(success=False, error=str(e))


@app.post("/api/video/extract")
async def extract_transcript_async(
    req: VideoRequest,
    user: dict = Depends(get_current_user),
    db_path: str = Depends(get_db_path),
    extractor: Callable = Depends(get_extractor),
    video_info_fn: Callable = Depends(get_video_info_fn),
):
    """异步转写：解析 →（转写缓存命中则跳过 ASR）→ AI 整理。链接提取计入每日限额。"""
    settings = get_settings()
    if not settings.api_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 API Key，请在 .env 中设置 API_KEY")

    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="链接不能为空")

    api_key = settings.api_key
    asr_model = resolve_asr_model(req.asr_model)
    llm = resolve_llm_client(req.llm_model)
    task_id = _new_extract_task(url, user["id"])
    worker = threading.Thread(
        target=_run_extract_task,
        args=(
            task_id,
            url,
            api_key,
            asr_model,
            extractor,
            video_info_fn,
            llm,
            db_path,
            user["id"],
            int(user.get("level") or 0),
        ),
        daemon=True,
    )
    worker.start()
    return {"success": True, "task_id": task_id, "task": _get_extract_task(task_id)}


@app.get("/api/video/extract/task/{task_id}")
async def get_extract_task(task_id: str, user: dict = Depends(get_current_user)):
    """查询转写任务进度与结构化预览结果。"""
    task = _assert_task_owner(_get_extract_task(task_id), user["id"])
    return {"success": True, "task": task}


def _new_extract_task(url: str, user_id: int) -> str:
    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _extract_tasks[task_id] = {
            "task_id": task_id,
            "user_id": user_id,
            "status": "pending",
            "phase": _TASK_PHASES["pending"],
            "progress": 0,
            "url": url,
            "video_id": None,
            "title": None,
            "message": "已加入队列",
            "error": None,
            "transcript": "",
            "preview": None,
            "cached_video": False,
            "cached_transcript": False,
        }
    return task_id


def _update_extract_task(task_id: str, *, status: Optional[str] = None, **fields) -> None:
    with _tasks_lock:
        task = _extract_tasks.get(task_id)
        if task is None:
            return
        if status is not None:
            task["status"] = status
            task["phase"] = _TASK_PHASES.get(status, status)
        task.update(fields)


def _get_extract_task(task_id: str) -> Optional[dict]:
    with _tasks_lock:
        task = _extract_tasks.get(task_id)
        return dict(task) if task else None


def _run_extract_task(
    task_id: str,
    url: str,
    api_key: str,
    asr_model: str,
    extractor: Callable,
    video_info_fn: Callable,
    llm,
    db_path: str,
    user_id: int,
    user_level: int,
) -> None:
    """后台：转写（可命中共享缓存）+ Markdown 预览（不入库）。"""

    def on_progress(phase: str, progress: int, message: str) -> None:
        _update_extract_task(task_id, status=phase, progress=progress, message=message)

    conn = db.connect(db_path)
    try:
        _update_extract_task(task_id, status="parsing", progress=5, message="正在解析链接…")
        try:
            video_info = video_info_fn(url) or {}
        except Exception as e:  # noqa: BLE001
            _update_extract_task(task_id, status="failed", error=str(e), message="解析链接失败")
            return

        video_id = video_info.get("video_id")
        title = video_info.get("title")
        _update_extract_task(task_id, video_id=video_id, title=title, progress=15)

        cached_text = (
            db.get_transcript(conn, video_id, asr_model) if video_id else None
        )
        cached_video = False
        if cached_text:
            text = cached_text.strip()
            _update_extract_task(
                task_id,
                transcript=text,
                cached_video=False,
                cached_transcript=True,
                progress=75,
                message="命中转写缓存，跳过下载与识别",
            )
        else:
            limit = get_daily_extract_limit(user_level)
            if db.get_extract_calls(conn, user_id) >= limit:
                _update_extract_task(
                    task_id,
                    status="failed",
                    error=EXTRACT_LIMIT_MSG,
                    message=EXTRACT_LIMIT_MSG,
                )
                return
            try:
                result = extractor(
                    url,
                    api_key=api_key,
                    asr_model=asr_model,
                    show_progress=False,
                    on_progress=on_progress,
                    use_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                _update_extract_task(task_id, status="failed", error=str(e), message="转写失败")
                return

            video_info = result.get("video_info") or video_info
            video_id = video_info.get("video_id") or video_id
            title = video_info.get("title") or title
            text = (result.get("text") or "").strip()
            cached_video = bool(result.get("cached_video"))
            if video_id and text:
                db.save_transcript(conn, video_id, asr_model, text)
            db.increment_extract_calls(conn, user_id)
            _update_extract_task(
                task_id,
                video_id=video_id,
                title=title,
                transcript=text,
                cached_video=cached_video,
                cached_transcript=False,
            )

        if not text:
            _update_extract_task(
                task_id, status="failed", error="转写结果为空", message="未能识别到文案"
            )
            return

        _update_extract_task(
            task_id, status="structuring", progress=82, message="正在整理知识…"
        )
        try:
            card = structure.structure_text_single(text, llm, hint_title=title or "")
        except (StructureError, LLMError) as e:
            _update_extract_task(
                task_id, status="failed", error=f"AI 整理失败: {e}", message="AI 整理失败"
            )
            return

        preview = {
            "title": card.get("title") or title or "",
            "content": card.get("content_md") or text,
            "content_md": card.get("content_md") or text,
            "stage": card.get("stage") or "",
            "transcript": text,
            "video_id": video_id,
            "source_url": url,
            "video_title": title,
            "download_url": video_info.get("url"),
        }
        _update_extract_task(
            task_id,
            status="done",
            progress=100,
            message="整理完成，请编辑后点击入库保存",
            preview=preview,
        )
    finally:
        conn.close()


# 保留同步接口供测试/脚本兼容（无进度）
@app.post("/api/video/extract-sync", response_model=ExtractResponse)
async def extract_transcript_sync(req: VideoRequest):
    """同步提取视频文案（兼容旧调用，无进度条）。"""
    settings = get_settings()
    if not settings.api_configured:
        return ExtractResponse(success=False, error="服务端未配置 API Key，请在 .env 中设置 API_KEY")
    try:
        result = extract_text(
            req.url,
            api_key=settings.api_key,
            asr_model=resolve_asr_model(req.asr_model),
            show_progress=False,
        )
        return ExtractResponse(
            success=True,
            video_id=result["video_info"]["video_id"],
            title=result["video_info"]["title"],
            text=result["text"],
            download_url=result["video_info"]["url"],
        )
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))


@app.get("/api/video/download")
async def download_video(url: str, filename: str = "video.mp4"):
    """代理下载视频（解决跨域和请求头问题）"""
    print(f"[Download] URL: {url}")
    print(f"[Download] Filename: {filename}")
    try:
        # 完整的请求头，模拟浏览器访问
        download_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.douyin.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
        }

        response = requests.get(url, headers=download_headers, stream=True, allow_redirects=True)
        print(f"[Download] Response status: {response.status_code}")
        print(f"[Download] Final URL: {response.url}")
        response.raise_for_status()

        content_length = response.headers.get("content-length", "")

        def iter_content():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if content_length:
            headers["Content-Length"] = content_length

        return StreamingResponse(
            iter_content(),
            media_type="video/mp4",
            headers=headers
        )
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"下载失败: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CardStructureRequest(BaseModel):
    """AI 整理请求（仅生成预览，不入库）。"""
    text: str
    hint_title: Optional[str] = ""
    llm_model: str = ""


class CardSaveRequest(BaseModel):
    """保存知识卡片（纯存储，不调用 AI）。"""
    title: str = ""
    content: str = ""  # markdown 正文别名
    content_md: str = ""
    stage: Optional[str] = None
    video_id: Optional[str] = None
    source_url: Optional[str] = None
    transcript: Optional[str] = None  # 保留字段，当前不落库
    is_public: int = 0


@app.post("/api/cards/structure")
async def structure_card_preview(
    req: CardStructureRequest,
    user: dict = Depends(get_current_user),
):
    """将文案 AI 整理为 Markdown 预览（标题 + content_md），不入库。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文案内容不能为空")

    llm = resolve_llm_client(req.llm_model)
    try:
        card = structure.structure_text_single(text, llm, hint_title=(req.hint_title or "").strip())
    except StructureError as e:
        raise HTTPException(status_code=502, detail=f"AI 整理失败: {e}")
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    body = card.get("content_md") or text
    return {
        "success": True,
        "preview": {
            "title": card.get("title") or "",
            "stage": card.get("stage") or "",
            "content": body,
            "content_md": body,
        },
    }


@app.post("/api/cards/save")
async def save_card(
    req: CardSaveRequest,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db),
):
    """保存单条知识卡片（纯存储，不调用 AI）。"""
    title = (req.title or "").strip()
    content = (req.content_md or req.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")

    user_id = user["id"]
    video_id = (req.video_id or "").strip() or None
    if video_id:
        existing = db.get_card_by_video_id(conn, video_id, user_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="该视频已入库，可在知识库中编辑或先删除旧记录",
            )

    try:
        card_id = db.insert_card(
            conn,
            user_id,
            title=title,
            content_md=content,
            stage=(req.stage or "").strip() or None,
            source_type="douyin_link" if video_id else "manual",
            source_url=req.source_url,
            video_id=video_id,
            is_public=int(req.is_public or 0),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="该视频已入库")

    return {"success": True, "card": _serialize_card(db.get_card(conn, card_id, user_id))}


# 兼容旧路径：仅整理预览，不入库（请优先使用 /api/cards/structure）
@app.post("/api/cards/from-text")
async def structure_card_legacy(
    req: CardStructureRequest,
    user: dict = Depends(get_current_user),
):
    """已废弃入库语义：与 /api/cards/structure 相同，仅返回整理预览。"""
    return await structure_card_preview(req)


# ---------------------------------------------------------------------------
# 抖音链接一键入库（异步任务 + 进度查询 + video_id 去重）
# ---------------------------------------------------------------------------

# 进度阶段：machine status -> 中文展示标签
_TASK_PHASES = {
    "pending": "排队中",
    "parsing": "解析链接",
    "downloading": "下载视频",
    "extracting_audio": "提取音频",
    "transcribing": "语音识别",
    "structuring": "AI 整理",
    "extracting": "解析转写中",
    "done": "已完成",
    "duplicate": "已存在",
    "failed": "失败",
}

# 任务注册表（自用单机场景，内存态即可）
_tasks: dict[str, dict] = {}
_extract_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _new_task(url: str, user_id: int) -> str:
    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "user_id": user_id,
            "status": "pending",
            "phase": _TASK_PHASES["pending"],
            "progress": 0,
            "url": url,
            "video_id": None,
            "title": None,
            "message": "已加入队列",
            "error": None,
            "duplicate": False,
            "cards": [],
        }
    return task_id


def _update_task(task_id: str, *, status: Optional[str] = None, **fields) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            return
        if status is not None:
            task["status"] = status
            task["phase"] = _TASK_PHASES.get(status, status)
        task.update(fields)


def _get_task(task_id: str) -> Optional[dict]:
    with _tasks_lock:
        task = _tasks.get(task_id)
        return dict(task) if task else None


def _run_import_task(
    task_id: str,
    url: str,
    stage: Optional[str],
    api_key: str,
    asr_model: str,
    extractor: Callable,
    video_info_fn: Callable,
    db_path: str,
    llm,
    user_id: int,
    user_level: int,
) -> None:
    """后台线程：解析/转写(可缓存) -> 去重 -> 结构化 -> 入库。"""
    conn = db.connect(db_path)
    try:
        _update_task(task_id, status="parsing", progress=10, message="正在解析链接")
        try:
            video_info = video_info_fn(url) or {}
        except Exception as e:  # noqa: BLE001
            _update_task(task_id, status="failed", error=f"解析失败: {e}", message="解析失败")
            return

        video_id = video_info.get("video_id")
        title = video_info.get("title")
        _update_task(task_id, video_id=video_id, title=title, progress=20)

        # 去重：同一视频不重复入库
        if video_id:
            existing = db.get_card_by_video_id(conn, video_id, user_id)
            if existing:
                _update_task(
                    task_id,
                    status="duplicate",
                    progress=100,
                    duplicate=True,
                    message="该视频已入库，未重复创建",
                    cards=[_serialize_card(existing)],
                )
                return

        cached_text = db.get_transcript(conn, video_id, asr_model) if video_id else None
        if cached_text:
            text = cached_text.strip()
            _update_task(
                task_id,
                status="extracting",
                progress=55,
                message="命中转写缓存，跳过下载与识别",
            )
        else:
            limit = get_daily_extract_limit(user_level)
            if db.get_extract_calls(conn, user_id) >= limit:
                _update_task(
                    task_id,
                    status="failed",
                    error=EXTRACT_LIMIT_MSG,
                    message=EXTRACT_LIMIT_MSG,
                )
                return

            _update_task(task_id, status="extracting", progress=30, message="正在解析并转写视频")

            def _on_progress(phase, progress, message):
                _update_task(task_id, status=phase, progress=progress, message=message)

            try:
                result = extractor(
                    url,
                    api_key=api_key,
                    asr_model=asr_model,
                    show_progress=False,
                    on_progress=_on_progress,
                    use_cache=True,
                )
            except Exception as e:  # noqa: BLE001
                _update_task(
                    task_id,
                    status="failed",
                    error=f"解析或转写失败: {e}",
                    message="解析或转写失败",
                )
                return

            video_info = result.get("video_info") or video_info
            video_id = video_info.get("video_id") or video_id
            title = video_info.get("title") or title
            text = (result.get("text") or "").strip()
            if video_id and text:
                db.save_transcript(conn, video_id, asr_model, text)
            db.increment_extract_calls(conn, user_id)
            _update_task(task_id, video_id=video_id, title=title, progress=55)

        if not text:
            _update_task(
                task_id,
                status="failed",
                error="转写结果为空，未识别到文案",
                message="未能识别到文案",
            )
            return

        _update_task(task_id, status="structuring", progress=70, message="正在整理知识")
        try:
            card = structure.structure_text_single(text, llm, hint_title=title or "")
        except (StructureError, LLMError) as e:
            _update_task(
                task_id, status="failed", error=f"AI 整理失败: {e}", message="AI 整理失败"
            )
            return

        try:
            card_id = db.insert_card(
                conn,
                user_id,
                stage=stage or card.get("stage"),
                title=card.get("title") or "",
                content_md=card.get("content_md") or text,
                source_type="douyin_link",
                source_url=url,
                video_id=video_id,
            )
        except sqlite3.IntegrityError:
            existing = (
                db.get_card_by_video_id(conn, video_id, user_id) if video_id else None
            )
            _update_task(
                task_id,
                status="duplicate",
                progress=100,
                duplicate=True,
                message="该视频已入库，未重复创建",
                cards=[_serialize_card(existing)] if existing else [],
            )
            return
        created = [_serialize_card(db.get_card(conn, card_id, user_id))]
        _update_task(task_id, status="done", progress=100, message="入库完成", cards=created)
    except Exception as e:  # noqa: BLE001
        _update_task(task_id, status="failed", error=f"录入任务异常: {e}", message="录入任务异常")
    finally:
        conn.close()


class CardFromLinkRequest(BaseModel):
    """抖音链接录入请求。"""
    url: str
    stage: Optional[str] = None
    llm_model: str = ""
    asr_model: str = ""


@app.post("/api/cards/from-link")
async def create_cards_from_link(
    req: CardFromLinkRequest,
    user: dict = Depends(get_current_user),
    db_path: str = Depends(get_db_path),
    extractor: Callable = Depends(get_extractor),
    video_info_fn: Callable = Depends(get_video_info_fn),
):
    """抖音分享链接 -> 转写(可缓存) -> 结构化 -> 入库（异步）。"""
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="链接不能为空")

    settings = get_settings()
    if not settings.api_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 API Key，请在 .env 中设置 API_KEY")

    api_key = settings.api_key
    asr_model = resolve_asr_model(req.asr_model)
    llm = resolve_llm_client(req.llm_model)
    task_id = _new_task(url, user["id"])
    worker = threading.Thread(
        target=_run_import_task,
        args=(
            task_id,
            url,
            req.stage,
            api_key,
            asr_model,
            extractor,
            video_info_fn,
            db_path,
            llm,
            user["id"],
            int(user.get("level") or 0),
        ),
        daemon=True,
    )
    worker.start()
    return {"success": True, "task_id": task_id, "task": _get_task(task_id)}


@app.get("/api/cards/task/{task_id}")
async def get_import_task(task_id: str, user: dict = Depends(get_current_user)):
    """查询链接录入任务的进度/结果。"""
    task = _assert_task_owner(_get_task(task_id), user["id"])
    return {"success": True, "task": task}


@app.get("/api/cards")
async def list_cards(
    stage: Optional[str] = None,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db),
):
    """列出知识卡片，可按阶段筛选。"""
    rows = db.list_cards(conn, user["id"], stage=stage)
    return {"success": True, "cards": [_serialize_card(r) for r in rows]}


@app.get("/api/cards/{card_id}")
async def get_card_detail(
    card_id: int,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db),
):
    """获取单张卡片详情。"""
    row = db.get_card(conn, card_id, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return {"success": True, "card": _serialize_card(row)}


class CardUpdateRequest(BaseModel):
    """卡片编辑请求：标题 / Markdown 正文 / 阶段 / 公开标记。"""
    title: Optional[str] = None
    content_md: Optional[str] = None
    content: Optional[str] = None  # 别名
    raw_text: Optional[str] = None  # 兼容旧字段名 → content_md
    stage: Optional[str] = None
    is_public: Optional[int] = None


@app.put("/api/cards/{card_id}")
async def update_card_endpoint(
    card_id: int,
    req: CardUpdateRequest,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db),
):
    """编辑卡片，不重新调 AI。"""
    provided = req.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(status_code=400, detail="未提供任何可更新字段")

    user_id = user["id"]
    row = db.get_card(conn, card_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="卡片不存在")

    fields: dict = {}
    if "title" in provided:
        fields["title"] = provided.get("title") or ""
    body_key = next((k for k in ("content_md", "content", "raw_text") if k in provided), None)
    if body_key is not None:
        new_body = (provided.get(body_key) or "").strip()
        if not new_body:
            raise HTTPException(status_code=400, detail="内容不能为空")
        fields["content_md"] = new_body
    if "stage" in provided:
        fields["stage"] = (provided.get("stage") or "").strip() or None
    if "is_public" in provided:
        fields["is_public"] = int(provided.get("is_public") or 0)

    if not fields:
        raise HTTPException(status_code=400, detail="未提供任何可更新字段")

    db.update_card(conn, card_id, user_id, **fields)
    return {"success": True, "card": _serialize_card(db.get_card(conn, card_id, user_id))}


@app.delete("/api/cards/{card_id}")
async def delete_card_endpoint(
    card_id: int,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db),
):
    """删除卡片（FTS 索引由触发器自动同步）。"""
    if not db.delete_card(conn, card_id, user["id"]):
        raise HTTPException(status_code=404, detail="卡片不存在")
    return {"success": True, "deleted": card_id}


class ChatRequest(BaseModel):
    """问答请求。"""
    question: str
    top_k: Optional[int] = None
    llm_model: str = ""  # 可选，覆盖默认 LLM
    document_text: Optional[str] = None  # 上传文件解析后的正文
    document_name: Optional[str] = None  # 原始文件名


@app.post("/api/documents/parse")
async def parse_uploaded_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """解析上传的 PDF / Excel 报价单，返回提取文本（供问答/合同审查）。"""
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    content = await file.read()
    try:
        result = documents.parse_document(filename, content)
    except DocumentParseError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, **result}


@app.post("/api/chat")
async def chat_endpoint(
    req: ChatRequest,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db),
):
    """基于知识库的问答：检索 → 拼 prompt → LLM → 带引用回答（防幻觉）。

    可附带 document_text/document_name（报价单 PDF/Excel 解析结果），
    结合知识库进行合同审查等分析。
    """
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    document = None
    doc_text = (req.document_text or "").strip()
    if doc_text:
        document = {
            "filename": (req.document_name or "上传文件").strip(),
            "text": doc_text,
        }

    top_k = req.top_k if (req.top_k and req.top_k > 0) else retrieve.DEFAULT_TOP_K
    results = retrieve.retrieve(conn, question, user["id"], top_k=top_k)
    grounded = retrieve.is_grounded(results)
    cards = results if grounded else []

    messages = qa.build_messages(question, cards, grounded, document=document)
    llm = resolve_llm_client(req.llm_model)
    try:
        answer = llm.chat(messages)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    return {
        "success": True,
        "answer": answer,
        "grounded": grounded,
        "citations": [qa.to_citation(c) for c in cards],
        "has_document": bool(document),
    }


def main():
    """启动服务"""
    port = int(os.getenv("PORT", "8080"))
    print(f"🚀 启动文案提取器 WebUI: http://localhost:{port}")
    settings = get_settings()
    print(f"📝 API Key: {'已配置 (.env)' if settings.api_configured else '未配置 — 请复制 .env.example 为 .env'}")
    print(f"🤖 默认模型: LLM={settings.llm_model}  ASR={settings.asr_model}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
