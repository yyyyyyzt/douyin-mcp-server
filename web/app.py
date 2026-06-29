#!/usr/bin/env python3
"""
抖音视频文案提取器 WebUI

启动方式:
    cd douyin-mcp-server
    export API_KEY="sk-xxx"
    python web/app.py
    # 访问 http://localhost:8080
"""

import os
import sys
import json
import uuid
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Callable

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))  # 便于 `from core import ...`
sys.path.insert(0, str(Path(__file__).parent.parent / "douyin-video" / "scripts"))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests

# 导入抖音处理模块
from douyin_downloader import get_video_info, extract_text

# 核心模块：知识库存储、LLM、结构化、检索、问答
from core import db, structure, retrieve, qa
from core.llm import LLMClient, LLMError
from core.structure import StructureError

# 知识库数据库路径（可用环境变量覆盖）
DB_PATH = os.getenv(
    "KNOWLEDGE_DB",
    str(Path(__file__).parent.parent / "data" / "knowledge.db"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时确保数据库目录存在并初始化表结构。"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(DB_PATH)
    try:
        db.init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="AI 装修监理助手", version="2.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# 静态资源（PWA 图标 / manifest）
_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# Service Worker：放在根路径以获得整站 scope（缓存静态外壳，API 不缓存）
_SERVICE_WORKER_JS = """
const CACHE = 'reno-assistant-v2';
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


def resolve_llm_client(api_key: str = "") -> LLMClient:
    """请求级 LLM 客户端：浏览器 api_key 优先，其次服务端环境变量。"""
    return LLMClient.resolve(api_key)


def get_extractor() -> Callable:
    """返回抖音解析/转写函数（依赖注入，便于测试 mock，避免真实下载/转写）。"""
    return extract_text


def _serialize_card(row: dict) -> dict:
    """把数据库行转为 API 卡片。"""
    return dict(row)


class VideoRequest(BaseModel):
    """视频请求模型"""
    url: str
    api_key: str = ""  # 可选，从前端传入


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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页面"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """健康检查"""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("API_KEY", "")
    return {
        "status": "ok",
        "api_key_configured": bool(api_key)
    }


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


@app.post("/api/video/extract", response_model=ExtractResponse)
async def extract_transcript(req: VideoRequest):
    """提取视频文案（需要 API_KEY）"""
    # 优先使用请求中的 API Key，其次使用环境变量
    api_key = req.api_key or os.getenv("API_KEY", "")
    if not api_key:
        return ExtractResponse(
            success=False,
            error="请先配置 API Key"
        )

    try:
        result = extract_text(req.url, api_key=api_key, show_progress=False)
        return ExtractResponse(
            success=True,
            video_id=result["video_info"]["video_id"],
            title=result["video_info"]["title"],
            text=result["text"],
            download_url=result["video_info"]["url"]
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


class CardFromTextRequest(BaseModel):
    """文本录入请求。"""
    text: str
    stage: Optional[str] = None
    api_key: str = ""  # 可选，未传则用环境变量 LLM_API_KEY / API_KEY


@app.post("/api/cards/from-text")
async def create_cards_from_text(
    req: CardFromTextRequest,
    conn=Depends(get_db),
):
    """粘贴文案 -> AI 结构化 -> 入库（可生成多张卡片）。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文案内容不能为空")

    llm = resolve_llm_client(req.api_key)
    try:
        cards = structure.structure_text(text, llm)
    except StructureError as e:
        raise HTTPException(status_code=502, detail=f"AI 结构化失败: {e}")
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    created = []
    for card in cards:
        card_id = db.insert_card(
            conn,
            title=card["title"],
            raw_text=card["raw_text"],
            structured_json=card["structured_json"],
            source_type="manual",
        )
        created.append(_serialize_card(db.get_card(conn, card_id)))

    return {"success": True, "cards": created}


# ---------------------------------------------------------------------------
# 抖音链接一键入库（异步任务 + 进度查询 + video_id 去重）
# ---------------------------------------------------------------------------

# 进度阶段：machine status -> 中文展示标签
_TASK_PHASES = {
    "pending": "排队中",
    "extracting": "解析转写中",
    "structuring": "结构化中",
    "done": "已完成",
    "duplicate": "已存在",
    "failed": "失败",
}

# 录入任务注册表（自用单机场景，内存态即可）
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _new_task(url: str) -> str:
    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {
            "task_id": task_id,
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
    extractor: Callable,
    db_path: str,
    llm,
) -> None:
    """后台线程：解析/转写 -> 去重 -> 结构化 -> 入库，并实时更新任务进度。"""
    conn = db.connect(db_path)
    try:
        # 1) 解析 + 下载 + 转写（extract_text 是一体的黑盒步骤）
        _update_task(task_id, status="extracting", progress=20, message="正在解析并转写视频")
        try:
            result = extractor(url, api_key=api_key, show_progress=False)
        except Exception as e:  # 网络/解析/转写失败统一兜底
            _update_task(task_id, status="failed", error=f"解析或转写失败: {e}", message="解析或转写失败")
            return

        video_info = result.get("video_info") or {}
        video_id = video_info.get("video_id")
        title = video_info.get("title")
        text = (result.get("text") or "").strip()
        _update_task(task_id, video_id=video_id, title=title, progress=50)

        if not text:
            _update_task(task_id, status="failed", error="转写结果为空，未识别到文案", message="未能识别到文案")
            return

        # 2) 去重：同一视频不重复入库
        if video_id:
            existing = db.get_card_by_video_id(conn, video_id)
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

        # 3) AI 结构化
        _update_task(task_id, status="structuring", progress=70, message="正在 AI 结构化")
        try:
            cards = structure.structure_text(text, llm)
        except (StructureError, LLMError) as e:
            _update_task(task_id, status="failed", error=f"AI 结构化失败: {e}", message="AI 结构化失败")
            return

        # 4) 入库（video_id 唯一，多卡时只第一张携带 video_id）
        created = []
        for i, card in enumerate(cards):
            try:
                card_id = db.insert_card(
                    conn,
                    title=card["title"],
                    raw_text=card["raw_text"],
                    structured_json=card["structured_json"],
                    source_type="douyin_link",
                    source_url=url,
                    video_id=video_id if i == 0 else None,
                )
            except sqlite3.IntegrityError:
                # 并发下被其他任务抢先写入同一 video_id
                existing = db.get_card_by_video_id(conn, video_id) if video_id else None
                _update_task(
                    task_id,
                    status="duplicate",
                    progress=100,
                    duplicate=True,
                    message="该视频已入库，未重复创建",
                    cards=[_serialize_card(existing)] if existing else [],
                )
                return
            created.append(_serialize_card(db.get_card(conn, card_id)))

        _update_task(task_id, status="done", progress=100, message="入库完成", cards=created)
    except Exception as e:  # noqa: BLE001 兜底：后台任务绝不应静默卡死
        _update_task(task_id, status="failed", error=f"录入任务异常: {e}", message="录入任务异常")
    finally:
        conn.close()


class CardFromLinkRequest(BaseModel):
    """抖音链接录入请求。"""
    url: str
    stage: Optional[str] = None
    api_key: str = ""  # 可选，未传则用环境变量 API_KEY


@app.post("/api/cards/from-link")
async def create_cards_from_link(
    req: CardFromLinkRequest,
    db_path: str = Depends(get_db_path),
    extractor: Callable = Depends(get_extractor),
):
    """抖音分享链接 -> 转写 -> 结构化 -> 入库（异步，返回 task_id 供轮询进度）。"""
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="链接不能为空")

    api_key = req.api_key or os.getenv("API_KEY", "")
    llm = resolve_llm_client(req.api_key)
    task_id = _new_task(url)
    worker = threading.Thread(
        target=_run_import_task,
        args=(task_id, url, req.stage, api_key, extractor, db_path, llm),
        daemon=True,
    )
    worker.start()
    return {"success": True, "task_id": task_id, "task": _get_task(task_id)}


@app.get("/api/cards/task/{task_id}")
async def get_import_task(task_id: str):
    """查询链接录入任务的进度/结果。"""
    task = _get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "task": task}


@app.get("/api/cards")
async def list_cards(stage: Optional[str] = None, conn=Depends(get_db)):
    """列出知识卡片，可按阶段筛选。"""
    rows = db.list_cards(conn, stage=stage)
    return {"success": True, "cards": [_serialize_card(r) for r in rows]}


@app.get("/api/cards/{card_id}")
async def get_card_detail(card_id: int, conn=Depends(get_db)):
    """获取单张卡片详情。"""
    row = db.get_card(conn, card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return {"success": True, "card": _serialize_card(row)}


class CardUpdateRequest(BaseModel):
    """卡片编辑请求：仅标题与正文。"""
    title: Optional[str] = None
    raw_text: Optional[str] = None


@app.put("/api/cards/{card_id}")
async def update_card_endpoint(card_id: int, req: CardUpdateRequest, conn=Depends(get_db)):
    """编辑卡片标题与正文，不重新调 AI，同步重写 structured_json。"""
    provided = req.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(status_code=400, detail="未提供任何可更新字段")

    row = db.get_card(conn, card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    card = dict(row)

    new_title = provided.get("title", card.get("title")) if "title" in provided else card.get("title")
    new_raw = card.get("raw_text")
    if "raw_text" in provided:
        new_raw = (provided["raw_text"] or "").strip()
        if not new_raw:
            raise HTTPException(status_code=400, detail="内容不能为空")

    fields = {
        "title": new_title,
        "structured_json": json.dumps(
            {"title": new_title, "content": new_raw}, ensure_ascii=False
        ),
    }
    if "raw_text" in provided:
        fields["raw_text"] = new_raw

    db.update_card(conn, card_id, **fields)
    return {"success": True, "card": _serialize_card(db.get_card(conn, card_id))}


@app.delete("/api/cards/{card_id}")
async def delete_card_endpoint(card_id: int, conn=Depends(get_db)):
    """删除卡片（FTS 索引由触发器自动同步）。"""
    if not db.delete_card(conn, card_id):
        raise HTTPException(status_code=404, detail="卡片不存在")
    return {"success": True, "deleted": card_id}


class ChatRequest(BaseModel):
    """问答请求。"""
    question: str
    top_k: Optional[int] = None
    api_key: str = ""  # 可选，未传则用环境变量 LLM_API_KEY / API_KEY


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, conn=Depends(get_db)):
    """基于知识库的问答：检索 → 拼 prompt → LLM → 带引用回答（防幻觉）。

    无命中或最高分低于阈值 → grounded=false：prompt 切换为「未找到相关标准 + 通用参考(带声明)」，
    且不返回引用，前端据此展示「未基于个人知识库」的警告。
    """
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    top_k = req.top_k if (req.top_k and req.top_k > 0) else retrieve.DEFAULT_TOP_K
    results = retrieve.retrieve(conn, question, top_k=top_k)
    grounded = retrieve.is_grounded(results)
    cards = results if grounded else []

    messages = qa.build_messages(question, cards, grounded)
    llm = resolve_llm_client(req.api_key)
    try:
        answer = llm.chat(messages)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    return {
        "success": True,
        "answer": answer,
        "grounded": grounded,
        "citations": [qa.to_citation(c) for c in cards],
    }


def main():
    """启动服务"""
    port = int(os.getenv("PORT", "8080"))
    print(f"🚀 启动文案提取器 WebUI: http://localhost:{port}")
    print(f"📝 API_KEY 配置状态: {'已配置' if os.getenv('API_KEY') else '未配置'}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
