"""视频缓存与异步转写任务测试。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db


class FakeLLM:
    def chat(self, messages, **kwargs):
        return json.dumps(
            {"cards": [{"title": "测试标题", "content": "整理后的知识内容"}]},
            ensure_ascii=False,
        )


FAKE_RESULT = {
    "video_info": {
        "video_id": "vid_cache_test",
        "title": "测试视频标题",
        "url": "https://example.com/video.mp4",
    },
    "text": "这是转写得到的原始文案内容。",
    "cached_video": False,
    "cached_transcript": False,
}


def _fake_extract(url, api_key=None, show_progress=False, on_progress=None, use_cache=True, **kwargs):
    if on_progress:
        on_progress("parsing", 10, "解析")
        on_progress("downloading", 30, "下载")
        on_progress("transcribing", 70, "转写")
    return dict(FAKE_RESULT)


@pytest.fixture()
def extract_env(tmp_path):
    db_path = str(tmp_path / "extract.db")
    conn = db.connect(db_path)
    db.init_db(conn)

    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    webapp.app.dependency_overrides[webapp.get_extractor] = lambda: _fake_extract
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda llm_model="": FakeLLM()

    client = TestClient(webapp.app)
    yield client, conn, tmp_path
    webapp.resolve_llm_client = original_resolve
    webapp.app.dependency_overrides.clear()
    conn.close()


def test_extract_task_returns_preview(extract_env):
    client, _, _ = extract_env
    resp = client.post(
        "/api/video/extract",
        json={"url": "https://v.douyin.com/test/"},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    task = None
    for _ in range(50):
        r = client.get(f"/api/video/extract/task/{task_id}")
        task = r.json()["task"]
        if task["status"] in ("done", "failed"):
            break
        time.sleep(0.05)

    assert task["status"] == "done"
    assert task["preview"]["title"] == "测试标题"
    assert task["preview"]["video_id"] == "vid_cache_test"
    assert task["preview"]["transcript"] == FAKE_RESULT["text"]


def test_save_card_with_video_id(extract_env):
    client, conn, _ = extract_env
    resp = client.post(
        "/api/cards/save",
        json={
            "title": "我的标题",
            "content": "知识正文",
            "video_id": "vid_unique_001",
            "source_url": "https://v.douyin.com/x/",
            "transcript": "原始转写",
        },
    )
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["video_id"] == "vid_unique_001"
    assert db.get_card_by_video_id(conn, "vid_unique_001") is not None

    dup = client.post(
        "/api/cards/save",
        json={"title": "重复", "content": "x", "video_id": "vid_unique_001"},
    )
    assert dup.status_code == 409


def test_video_cache_helpers(tmp_path, monkeypatch):
    import douyin_downloader as dd

    cache = tmp_path / "cache"
    cache.mkdir(parents=True)
    monkeypatch.setenv("VIDEO_CACHE_DIR", str(cache))

    vid = "7123456789"
    video_file = cache / f"{vid}.mp4"
    video_file.write_bytes(b"x" * 2048)
    assert dd.get_cached_video_path(vid) == video_file

    dd.save_transcript_cache(vid, "转写文本")
    assert dd.get_cached_transcript_path(vid).read_text(encoding="utf-8") == "转写文本"
