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
from pathlib import Path
from typing import Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))  # 便于 `from core import ...`
sys.path.insert(0, str(Path(__file__).parent.parent / "douyin-video" / "scripts"))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests

# 导入抖音处理模块
from douyin_downloader import get_video_info, extract_text, HEADERS

# 核心模块：知识库存储、LLM、结构化
from core import db, structure
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


def get_db():
    """每个请求一个连接（依赖注入，便于测试覆盖）。"""
    conn = db.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def get_llm_client() -> LLMClient:
    """从环境变量构造 LLM 客户端（依赖注入，便于测试覆盖）。"""
    return LLMClient.from_env()


def _serialize_card(row: dict) -> dict:
    """把数据库行转为 API 卡片：附带解析后的 steps。"""
    card = dict(row)
    steps = []
    if card.get("structured_json"):
        try:
            steps = json.loads(card["structured_json"]).get("steps", [])
        except (json.JSONDecodeError, AttributeError):
            steps = []
    card["steps"] = steps
    return card


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
    api_key = os.getenv("API_KEY", "")
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


@app.post("/api/cards/from-text")
async def create_cards_from_text(
    req: CardFromTextRequest,
    conn=Depends(get_db),
    llm=Depends(get_llm_client),
):
    """粘贴文案 -> AI 结构化 -> 入库（可生成多张卡片）。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文案内容不能为空")

    try:
        cards = structure.structure_text(text, llm)
    except StructureError as e:
        raise HTTPException(status_code=502, detail=f"AI 结构化失败: {e}")
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    created = []
    for card in cards:
        stage = req.stage or card["stage"]
        card_id = db.insert_card(
            conn,
            stage=stage,
            title=card["title"],
            raw_text=card["raw_text"],
            structured_json=card["structured_json"],
            source_type="manual",
        )
        created.append(_serialize_card(db.get_card(conn, card_id)))

    return {"success": True, "cards": created}


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


def main():
    """启动服务"""
    port = int(os.getenv("PORT", "8080"))
    print(f"🚀 启动文案提取器 WebUI: http://localhost:{port}")
    print(f"📝 API_KEY 配置状态: {'已配置' if os.getenv('API_KEY') else '未配置'}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
