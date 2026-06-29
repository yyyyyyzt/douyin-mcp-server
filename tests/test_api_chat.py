"""API 测试：POST /api/chat 检索 → prompt → LLM → answer + grounded + citations。

mock LLM（记录收到的 messages），断言 prompt 注入命中卡片、响应含 citations 与 grounded。
"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from core.llm import LLMError


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


def _seed(conn, stage, title, raw_text):
    return db.insert_card(
        conn,
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

    llm = RecordingLLM()
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda api_key="": llm
    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path

    client = TestClient(webapp.app)
    yield client, conn, llm
    webapp.resolve_llm_client = original_resolve
    webapp.app.dependency_overrides.clear()
    conn.close()


def test_chat_grounded_with_citations(env):
    client, conn, llm = env
    cid = _seed(conn, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米，门口做挡水坝。")

    resp = client.post("/api/chat", json={"question": "卫生间的防水应该刷多高？"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["grounded"] is True
    assert data["answer"] == "这是回答"
    # 引用包含命中卡片
    assert any(c["id"] == cid and c["title"] == "卫生间防水高度" for c in data["citations"])
    # prompt 注入了命中卡片标题
    user_msg = llm.last_messages[1]["content"]
    assert "卫生间防水高度" in user_msg


def test_chat_ungrounded_when_no_match(env):
    client, conn, llm = env
    _seed(conn, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米。")

    resp = client.post("/api/chat", json={"question": "今天的股票行情怎么样"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["grounded"] is False
    assert data["citations"] == []
    # 未注入任何卡片
    assert "片段" not in llm.last_messages[1]["content"]
    assert "未找到相关标准" in llm.last_messages[0]["content"]


def test_chat_empty_db_is_ungrounded(env):
    client, conn, llm = env
    resp = client.post("/api/chat", json={"question": "卫生间防水刷多高"})
    assert resp.status_code == 200
    assert resp.json()["grounded"] is False
    assert resp.json()["citations"] == []


def test_chat_empty_question_returns_400(env):
    client, _, _ = env
    resp = client.post("/api/chat", json={"question": "   "})
    assert resp.status_code == 400


def test_chat_with_document_and_grounded(env):
    client, conn, llm = env
    cid = _seed(conn, "报价阶段", "水电改造单价", "水电改造一般按米计价，含开槽布线。")

    resp = client.post(
        "/api/chat",
        json={
            "question": "水电改造一般怎么计价？这份报价单合理吗？",
            "document_text": "水电改造 120 元/米，共 50 米，合计 6000 元",
            "document_name": "装修公司报价单.xlsx",
        },
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
    client, conn, llm = env
    resp = client.post(
        "/api/chat",
        json={
            "question": "请审查这份报价",
            "document_text": "瓷砖铺贴 80 元/平米",
            "document_name": "报价.pdf",
        },
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
    _seed(conn, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米。")
    err_llm = RecordingLLM(raise_error=True)
    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = lambda api_key="": err_llm
    client = TestClient(webapp.app)
    try:
        resp = client.post("/api/chat", json={"question": "卫生间防水刷多高"})
        assert resp.status_code == 502
    finally:
        webapp.resolve_llm_client = original_resolve
        webapp.app.dependency_overrides.clear()
        conn.close()
