"""文档上传解析 API 测试。"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import app as webapp
from core import db
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["项目", "金额"])
    ws.append(["防水工程", "3500"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "doc.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user = ensure_test_user(conn)
    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    override_current_user(user)
    headers = auth_headers(user)
    yield TestClient(webapp.app), headers
    clear_app_overrides()
    conn.close()


def test_parse_document_xlsx(client):
    c, headers = client
    data = _xlsx_bytes()
    resp = c.post(
        "/api/documents/parse",
        files={"file": ("报价单.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["filename"] == "报价单.xlsx"
    assert "防水工程" in body["text"]
    assert body["char_count"] > 0


def test_parse_document_unsupported_type(client):
    c, headers = client
    resp = c.post(
        "/api/documents/parse",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]


def test_parse_document_empty_file(client):
    c, headers = client
    resp = c.post(
        "/api/documents/parse",
        files={"file": ("empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert resp.status_code == 400
