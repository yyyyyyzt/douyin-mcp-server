"""链接提取每日限额 + 转写共享缓存。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from core.settings import get_daily_extract_limit
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


class FakeLLM:
    def chat(self, messages, **kwargs):
        return json.dumps(
            {"cards": [{"title": "标题", "content_md": "正文"}]},
            ensure_ascii=False,
        )


VIDEO = {
    "video_id": "vid_limit_1",
    "title": "测试",
    "url": "https://example.com/v.mp4",
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DAILY_EXTRACT_LIMIT", "2")
    db_path = str(tmp_path / "limit.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user = ensure_test_user(conn)

    extract_calls = []

    def _fake_extract(url, api_key=None, show_progress=False, on_progress=None, **kwargs):
        extract_calls.append(1)
        if on_progress:
            on_progress("transcribing", 70, "转写")
        return {
            "video_info": dict(VIDEO),
            "text": f"转写文案-{len(extract_calls)}",
            "cached_video": False,
        }

    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    webapp.app.dependency_overrides[webapp.get_extractor] = lambda: _fake_extract
    webapp.app.dependency_overrides[webapp.get_video_info_fn] = lambda: (lambda url: dict(VIDEO))
    override_current_user(user)
    original = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda llm_model="": FakeLLM()
    headers = auth_headers(user)
    client = TestClient(webapp.app)
    yield client, conn, user, headers, extract_calls
    webapp.resolve_llm_client = original
    clear_app_overrides()
    conn.close()


def _wait_extract(client, task_id, headers, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/video/extract/task/{task_id}", headers=headers).json()["task"]
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"timeout: {last}")


def test_get_daily_extract_limit_env_override(monkeypatch):
    monkeypatch.setenv("DAILY_EXTRACT_LIMIT", "3")
    assert get_daily_extract_limit(0) == 3
    assert get_daily_extract_limit(1) == 50


def test_extract_increments_usage_and_blocks_over_limit(env):
    client, conn, user, headers, extract_calls = env
    for i in range(2):
        VIDEO["video_id"] = f"vid_limit_{i}"
        resp = client.post(
            "/api/video/extract",
            json={"url": f"https://v.douyin.com/{i}/"},
            headers=headers,
        )
        assert resp.status_code == 200
        task = _wait_extract(client, resp.json()["task_id"], headers)
        assert task["status"] == "done", task
        assert task["cached_transcript"] is False

    assert db.get_extract_calls(conn, user["id"]) == 2
    assert len(extract_calls) == 2

    VIDEO["video_id"] = "vid_limit_over"
    resp = client.post(
        "/api/video/extract",
        json={"url": "https://v.douyin.com/over/"},
        headers=headers,
    )
    assert resp.status_code == 200
    task = _wait_extract(client, resp.json()["task_id"], headers)
    assert task["status"] == "failed"
    assert "今日链接提取次数已用完" in (task.get("error") or "")
    assert len(extract_calls) == 2


def test_transcript_cache_hit_skips_asr_and_quota(env):
    from core.settings import get_settings

    client, conn, user, headers, extract_calls = env
    VIDEO["video_id"] = "vid_cached"
    db.save_transcript(
        conn, "vid_cached", get_settings().asr_model, "缓存的转写文本"
    )

    # 先把配额用完
    db.increment_extract_calls(conn, user["id"])
    db.increment_extract_calls(conn, user["id"])
    assert db.get_extract_calls(conn, user["id"]) == 2

    resp = client.post(
        "/api/video/extract",
        json={"url": "https://v.douyin.com/cached/"},
        headers=headers,
    )
    task = _wait_extract(client, resp.json()["task_id"], headers)
    assert task["status"] == "done", task
    assert task["cached_transcript"] is True
    assert task["preview"]["transcript"] == "缓存的转写文本"
    assert len(extract_calls) == 0
    # 缓存命中不扣次
    assert db.get_extract_calls(conn, user["id"]) == 2


def test_chat_not_limited(env):
    client, conn, user, headers, _ = env
    # 配额用尽也不影响对话
    db.increment_extract_calls(conn, user["id"])
    db.increment_extract_calls(conn, user["id"])
    resp = client.post(
        "/api/chat",
        json={"question": "卫生间防水要注意什么？"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
