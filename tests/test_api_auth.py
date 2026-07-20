"""API 鉴权与用户隔离测试（TDD）。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_LOCAL_AUTH", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    db_path = str(tmp_path / "auth.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user_a = ensure_test_user(conn, "user-a")
    user_b = ensure_test_user(conn, "user-b")

    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    client = TestClient(webapp.app)
    yield client, conn, user_a, user_b
    clear_app_overrides()
    conn.close()


def test_local_login_issues_token(env):
    client, conn, user_a, _ = env
    resp = client.post("/api/auth/local")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["token"]
    assert data["user"]["openid"] == db.LOCAL_WEB_OPENID


def test_local_login_disabled_without_flag(env, monkeypatch):
    client, _, _, _ = env
    monkeypatch.delenv("ALLOW_LOCAL_AUTH", raising=False)
    resp = client.post("/api/auth/local")
    assert resp.status_code == 403


def test_wechat_login_issues_token(env, monkeypatch):
    client, conn, _, _ = env
    monkeypatch.setenv("WECHAT_APPID", "wx-test")
    monkeypatch.setenv("WECHAT_SECRET", "secret-test")

    def fake_code2session(code, appid, secret):
        assert code == "mock-code"
        return {"openid": "wx-openid-1", "unionid": "union-1"}

    monkeypatch.setattr(webapp.wechat_auth, "code2session", fake_code2session)
    resp = client.post("/api/auth/wechat/login", json={"code": "mock-code"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["token"]
    assert data["user"]["openid"] == "wx-openid-1"
    assert db.get_user_by_openid(conn, "wx-openid-1") is not None


def test_cards_requires_auth(env):
    client, _, _, _ = env
    resp = client.get("/api/cards")
    assert resp.status_code == 401


def test_user_a_cannot_read_user_b_card(env):
    client, conn, user_a, user_b = env
    cid = db.insert_card(
        conn,
        user_b["id"],
        title="B 私密",
        content_md="只有 B 能看",
    )
    headers = auth_headers(user_a)
    resp = client.get(f"/api/cards/{cid}", headers=headers)
    assert resp.status_code == 404


def test_task_poll_cross_user_forbidden(env, monkeypatch):
    client, conn, user_a, user_b = env
    monkeypatch.setenv("API_KEY", "sk-test")

    # 用 user_b 创建任务（通过内部 API 模拟：直接写任务表不可行，走 extract）
    override_current_user(user_b)

    class FakeLLM:
        def chat(self, messages, **kwargs):
            return json.dumps({"title": "t", "content": "c"}, ensure_ascii=False)

    def fake_extract(url, api_key=None, show_progress=False, **kwargs):
        return {
            "video_info": {"video_id": "v1", "title": "t", "url": "x"},
            "text": "文案",
        }

    webapp.app.dependency_overrides[webapp.get_extractor] = lambda: fake_extract
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda llm_model="": FakeLLM()

    try:
        resp = client.post(
            "/api/video/extract",
            json={"url": "https://v.douyin.com/x/"},
            headers=auth_headers(user_b),
        )
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        # user_a 轮询应 403
        override_current_user(user_a)
        poll = client.get(f"/api/video/extract/task/{task_id}", headers=auth_headers(user_a))
        assert poll.status_code == 403
    finally:
        webapp.resolve_llm_client = original_resolve
        webapp.app.dependency_overrides.pop(webapp.get_extractor, None)


def _wait_extract(client, task_id, headers, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/video/extract/task/{task_id}", headers=headers)
        if r.status_code != 200:
            return r
        st = r.json()["task"]["status"]
        if st in ("done", "failed"):
            return r
        time.sleep(0.02)
    raise AssertionError("extract task timeout")
