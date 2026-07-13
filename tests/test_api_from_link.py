"""API 测试（TDD）：/api/cards/from-link 抖音链接异步入库 + 进度查询 + 去重。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


class FakeLLM:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def chat(self, messages, **kwargs):
        return self._outputs.pop(0)


def _card_payload(cards):
    return json.dumps({"cards": cards}, ensure_ascii=False)


SAMPLE_CARDS = [
    {
        "title": "瓦工施工 12 个细节",
        "content": "贴砖前充分湿润墙面，基层无空鼓、无浮灰，避免直接在腻子层贴砖。",
    }
]

FAKE_EXTRACT_RESULT = {
    "video_info": {
        "video_id": "vid_abc123",
        "title": "假如你第一次装修这12个细节",
        "url": "https://aweme.snssdk.com/play/vid_abc123",
    },
    "text": "假如你第一次装修，这12个细节一定要提前跟瓦工师傅交代清楚……",
    "output_path": None,
}


def _make_fake_extract(result=FAKE_EXTRACT_RESULT, calls=None):
    def _fake_extract(url, api_key=None, show_progress=False, **kwargs):
        if calls is not None:
            calls.append({"url": url, "api_key": api_key})
        return result

    return _fake_extract


@pytest.fixture()
def env(tmp_path):
    db_path = str(tmp_path / "link.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user = ensure_test_user(conn)

    fake_llm = FakeLLM([_card_payload(SAMPLE_CARDS)])
    extract_calls = []
    fake_extract = _make_fake_extract(calls=extract_calls)

    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    webapp.app.dependency_overrides[webapp.get_extractor] = lambda: fake_extract
    override_current_user(user)
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda llm_model="": fake_llm
    headers = auth_headers(user)

    client = TestClient(webapp.app)
    yield client, conn, db_path, extract_calls, user, headers

    webapp.resolve_llm_client = original_resolve
    clear_app_overrides()
    conn.close()


def _wait_task(client, task_id, headers, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/cards/task/{task_id}", headers=headers)
        assert resp.status_code == 200
        last = resp.json()["task"]
        if last["status"] in ("done", "duplicate", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"任务未在 {timeout}s 内结束，最后状态: {last}")


def test_from_link_creates_card(env):
    client, conn, _, extract_calls, user, headers = env
    resp = client.post("/api/cards/from-link", json={"url": "https://v.douyin.com/abc/"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    task_id = body["task_id"]
    assert task_id

    task = _wait_task(client, task_id, headers)
    assert task["status"] == "done"
    assert task["video_id"] == "vid_abc123"
    assert len(task["cards"]) == 1

    card = task["cards"][0]
    assert card["title"] == "瓦工施工 12 个细节"
    assert card["source_type"] == "douyin_link"
    assert card["source_url"] == "https://v.douyin.com/abc/"
    assert card["video_id"] == "vid_abc123"

    assert db.get_card_by_video_id(conn, "vid_abc123", user["id"]) is not None
    assert extract_calls and extract_calls[0]["url"] == "https://v.douyin.com/abc/"


def test_from_link_dedup_blocks_reimport(env):
    client, conn, _, _, user, headers = env
    db.insert_card(
        conn,
        user["id"],
        title="已存在的瓦工卡片",
        raw_text="旧文案",
        structured_json=json.dumps({"title": "已存在的瓦工卡片", "content": "旧文案"}, ensure_ascii=False),
        source_type="douyin_link",
        source_url="https://v.douyin.com/old/",
        video_id="vid_abc123",
    )

    resp = client.post("/api/cards/from-link", json={"url": "https://v.douyin.com/abc/"}, headers=headers)
    task_id = resp.json()["task_id"]
    task = _wait_task(client, task_id, headers)

    assert task["status"] == "duplicate"
    assert task["duplicate"] is True
    assert task["video_id"] == "vid_abc123"
    rows = db.list_cards(conn, user["id"])
    assert len(rows) == 1
    assert task["cards"][0]["title"] == "已存在的瓦工卡片"


def test_from_link_extract_failure(env):
    client, conn, db_path, _, user, headers = env

    def _boom(url, api_key=None, show_progress=False, **kwargs):
        raise RuntimeError("解析视频失败：list index out of range")

    webapp.app.dependency_overrides[webapp.get_extractor] = lambda: _boom

    resp = client.post("/api/cards/from-link", json={"url": "https://v.douyin.com/bad/"}, headers=headers)
    task_id = resp.json()["task_id"]
    task = _wait_task(client, task_id, headers)

    assert task["status"] == "failed"
    assert task["error"]
    assert "list index out of range" in task["error"]
    assert db.list_cards(conn, user["id"]) == []


def test_from_link_empty_transcript_fails(env):
    client, conn, _, _, user, headers = env
    empty_result = {
        "video_info": {"video_id": "vid_empty", "title": "无人声视频", "url": "x"},
        "text": "   ",
        "output_path": None,
    }
    webapp.app.dependency_overrides[webapp.get_extractor] = lambda: _make_fake_extract(result=empty_result)

    resp = client.post("/api/cards/from-link", json={"url": "https://v.douyin.com/silent/"}, headers=headers)
    task_id = resp.json()["task_id"]
    task = _wait_task(client, task_id, headers)

    assert task["status"] == "failed"
    assert "空" in task["error"]
    assert db.list_cards(conn, user["id"]) == []


def test_from_link_empty_url_returns_400(env):
    client, _, _, _, _, headers = env
    resp = client.post("/api/cards/from-link", json={"url": "   "}, headers=headers)
    assert resp.status_code == 400


def test_task_not_found_returns_404(env):
    client, _, _, _, _, headers = env
    resp = client.get("/api/cards/task/does-not-exist", headers=headers)
    assert resp.status_code == 404


def test_from_link_multi_cards_merged_to_one(env):
    client, conn, _, _, user, headers = env
    multi = [
        {"title": "瓦工细节A", "content": "细节 A 正文"},
        {"title": "防水细节B", "content": "细节 B 正文"},
    ]
    webapp.resolve_llm_client = lambda llm_model="": FakeLLM([_card_payload(multi)])

    resp = client.post("/api/cards/from-link", json={"url": "https://v.douyin.com/multi/"}, headers=headers)
    task_id = resp.json()["task_id"]
    task = _wait_task(client, task_id, headers)

    assert task["status"] == "done"
    assert len(task["cards"]) == 1
    assert task["cards"][0]["video_id"] == "vid_abc123"
    assert "细节 A" in task["cards"][0]["raw_text"]
    assert len(db.list_cards(conn, user["id"])) == 1
