"""文档解析单元测试（PDF / Excel）。"""

from io import BytesIO

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter

from core.documents import (
    ALLOWED_SUFFIXES,
    DocumentParseError,
    MAX_TEXT_CHARS,
    parse_document,
)


def _make_xlsx_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_blank_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestParseDocumentExcel:
    def test_parse_xlsx(self):
        data = _make_xlsx_bytes([
            ["项目", "单价", "数量", "小计"],
            ["水电改造", "120", "50", "6000"],
            ["瓷砖铺贴", "80", "100", "8000"],
        ])
        result = parse_document("装修公司报价单.xlsx", data)
        assert result["filename"] == "装修公司报价单.xlsx"
        assert result["file_type"] == "excel"
        assert "水电改造" in result["text"]
        assert "瓷砖铺贴" in result["text"]
        assert result["truncated"] is False
        assert result["char_count"] > 0

    def test_parse_xlsm(self):
        data = _make_xlsx_bytes([["备注", "含主材"]])
        result = parse_document("quote.xlsm", data)
        assert result["file_type"] == "excel"
        assert "含主材" in result["text"]

    def test_empty_workbook(self):
        data = _make_xlsx_bytes([])
        with pytest.raises(DocumentParseError, match="未识别到有效单元格"):
            parse_document("empty.xlsx", data)


class TestParseDocumentPdf:
    def test_parse_pdf_no_text_raises(self):
        data = _make_blank_pdf_bytes()
        with pytest.raises(DocumentParseError, match="未识别到可提取文本|扫描件"):
            parse_document("scan.pdf", data)

    def test_parse_pdf_with_text(self, monkeypatch):
        def fake_parse_pdf(content: bytes) -> str:
            return "装修公司报价：水电 6000 元，瓷砖 8000 元"

        monkeypatch.setattr("core.documents.parse_pdf", fake_parse_pdf)
        result = parse_document("报价单.pdf", b"%PDF-fake")
        assert "水电 6000" in result["text"]
        assert result["file_type"] == "pdf"


class TestParseDocumentValidation:
    def test_unsupported_extension(self):
        with pytest.raises(DocumentParseError, match="不支持"):
            parse_document("notes.txt", b"hello")

    def test_legacy_xls(self):
        with pytest.raises(DocumentParseError, match="xlsx"):
            parse_document("old.xls", b"fake")

    def test_file_too_large(self):
        huge = b"x" * (11 * 1024 * 1024)
        with pytest.raises(DocumentParseError, match="10MB"):
            parse_document("big.xlsx", huge)

    def test_truncation(self, monkeypatch):
        long_text = "甲" * (MAX_TEXT_CHARS + 500)

        def fake_parse_pdf(content: bytes) -> str:
            return long_text

        monkeypatch.setattr("core.documents.parse_pdf", fake_parse_pdf)
        result = parse_document("long.pdf", b"%PDF")
        assert result["truncated"] is True
        assert result["char_count"] == MAX_TEXT_CHARS + len("\n\n…（内容过长，已截断）")

    def test_allowed_suffixes_constant(self):
        assert ".pdf" in ALLOWED_SUFFIXES
        assert ".xlsx" in ALLOWED_SUFFIXES
