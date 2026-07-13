"""API 测试：POST /api/chat 检索 → prompt → LLM → answer + grounded + citations。"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from core.llm import LLMError
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


class RecordingLLM:
    def __init__(self, answer="这是回答", raise_error=False):
        self.answer = answer
        self.raise_error = raise_error
        self.last_messages = None

    def chat(self, messages, **kwargs):
        self.last_messages = messages
        if self.raise_error:
            raise LLMError("上游不可用")
        return self.answer


def _seed(conn, user_id, stage, title, raw_text):
    return db.insert_card(
        conn,
        user_id,
        stage=stage,
        title=title,
        raw_text=raw_text,
        structured_json=json.dumps({"stage": stage, "title": title, "steps": []}, ensure_ascii=False),
        source_type="manual",
    )


@pytest.fixture()
def env(tmp_path):
    db_path = str(tmp_path / "chat.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user = ensure_test_user(conn)

    llm = RecordingLLM()
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda llm_model="": llm
    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    override_current_user(user)
    headers = auth_headers(user)

    client = TestClient(webapp.app)
    yield client, conn, user, llm, headers
    webapp.resolve_llm_client = original_resolve
    clear_app_overrides()
    conn.close()


def test_chat_grounded_with_citations(env):
    client, conn, user, llm, headers = env
    cid = _seed(conn, user["id"], "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米，门口做挡水坝。")

    resp = client.post("/api/chat", json={"question": "卫生间的防水应该刷多高？"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["grounded"] is True
    assert data["answer"] == "这是回答"
    assert any(c["id"] == cid and c["title"] == "卫生间防水高度" for c in data["citations"])
    user_msg = llm.last_messages[1]["content"]
    assert "卫生间防水高度" in user_msg


def test_chat_ungrounded_when_no_match(env):
    client, conn, user, llm, headers = env
    _seed(conn, user["id"], "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米。")

    resp = client.post("/api/chat", json={"question": "今天的股票行情怎么样"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["grounded"] is False
    assert data["citations"] == []
    assert "片段" not in llm.last_messages[1]["content"]
    assert "未找到相关标准" in llm.last_messages[0]["content"]


def test_chat_empty_db_is_ungrounded(env):
    client, _, _, _, headers = env
    resp = client.post("/api/chat", json={"question": "卫生间防水刷多高"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["grounded"] is False
    assert resp.json()["citations"] == []


def test_chat_empty_question_returns_400(env):
    client, _, _, _, headers = env
    resp = client.post("/api/chat", json={"question": "   "}, headers=headers)
    assert resp.status_code == 400


def test_chat_with_document_and_grounded(env):
    client, conn, user, llm, headers = env
    cid = _seed(conn, user["id"], "报价阶段", "水电改造单价", "水电改造一般按米计价，含开槽布线。")

    resp = client.post(
        "/api/chat",
        json={
            "question": "水电改造一般怎么计价？这份报价单合理吗？",
            "document_text": "水电改造 120 元/米，共 50 米，合计 6000 元",
            "document_name": "装修公司报价单.xlsx",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["has_document"] is True
    assert data["grounded"] is True
    assert any(c["id"] == cid for c in data["citations"])
    user_msg = llm.last_messages[1]["content"]
    assert "装修公司报价单.xlsx" in user_msg
    assert "6000 元" in user_msg
    assert "水电改造单价" in user_msg
    assert "上传文件" in llm.last_messages[0]["content"]


def test_chat_with_document_ungrounded(env):
    client, _, _, llm, headers = env
    resp = client.post(
        "/api/chat",
        json={
            "question": "请审查这份报价",
            "document_text": "瓷砖铺贴 80 元/平米",
            "document_name": "报价.pdf",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_document"] is True
    assert data["grounded"] is False
    assert "知识库中暂无" in llm.last_messages[0]["content"]
    assert "报价.pdf" in llm.last_messages[1]["content"]


def test_chat_llm_error_returns_502(env, tmp_path):
    db_path = str(tmp_path / "chat_err.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user = ensure_test_user(conn)
    _seed(conn, user["id"], "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米。")
    err_llm = RecordingLLM(raise_error=True)
    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    override_current_user(user)
    headers = auth_headers(user)
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda llm_model="": err_llm
    client = TestClient(webapp.app)
    try:
        resp = client.post("/api/chat", json={"question": "卫生间防水刷多高"}, headers=headers)
        assert resp.status_code == 502
    finally:
        webapp.resolve_llm_client = original_resolve
        clear_app_overrides()
        conn.close()
