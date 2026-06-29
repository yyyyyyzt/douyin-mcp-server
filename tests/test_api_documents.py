"""文档上传解析 API 测试。"""

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from web.app import app


def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["项目", "金额"])
    ws.append(["防水工程", "3500"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_document_xlsx():
    client = TestClient(app)
    data = _xlsx_bytes()
    resp = client.post(
        "/api/documents/parse",
        files={"file": ("报价单.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["filename"] == "报价单.xlsx"
    assert "防水工程" in body["text"]
    assert body["char_count"] > 0


def test_parse_document_unsupported_type():
    client = TestClient(app)
    resp = client.post(
        "/api/documents/parse",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]


def test_parse_document_empty_file():
    client = TestClient(app)
    resp = client.post(
        "/api/documents/parse",
        files={"file": ("empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 400
