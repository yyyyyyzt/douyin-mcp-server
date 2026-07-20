"""问答 prompt 组装与引用构造测试。"""

from core import qa


def _card(
    id=1,
    title="卫生间防水高度",
    content_md="卫生间防水要刷到1.8米，门口做挡水坝。",
    score=2.0,
):
    return {
        "id": id,
        "title": title,
        "content_md": content_md,
        "score": score,
    }


def test_build_messages_grounded_injects_cards():
    msgs = qa.build_messages("卫生间防水刷多高？", [_card()], grounded=True)
    assert msgs[0]["role"] == "system"
    assert "只能根据" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "卫生间防水高度" in user
    assert "1.8米" in user
    assert "卫生间防水刷多高" in user


def test_build_messages_ungrounded_excludes_cards():
    msgs = qa.build_messages("今天天气如何？", [], grounded=False)
    assert "未找到相关标准" in msgs[0]["content"]
    assert "仅供参考" in msgs[0]["content"]
    assert "片段" not in msgs[1]["content"]


def test_to_citation_shape():
    long_raw = "防" * 300
    cit = qa.to_citation(_card(content_md=long_raw, score=3.14159))
    assert cit["id"] == 1
    assert cit["title"] == "卫生间防水高度"
    assert len(cit["excerpt"]) <= qa.EXCERPT_LEN + 1
    assert cit["excerpt"].endswith("…")
    assert cit["score"] == 3.1416


def test_build_messages_with_document_and_cards():
    doc = {"filename": "报价单.xlsx", "text": "水电改造 6000 元"}
    msgs = qa.build_messages("这份报价合理吗？", [_card()], grounded=True, document=doc)
    assert "上传文件" in msgs[0]["content"]
    assert "合同/报价单" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "报价单.xlsx" in user
    assert "水电改造 6000" in user
    assert "卫生间防水高度" in user


def test_build_messages_with_document_only():
    doc = {"filename": "合同.pdf", "text": "总价 15 万元，工期 60 天"}
    msgs = qa.build_messages("有哪些风险？", [], grounded=False, document=doc)
    assert "知识库中暂无" in msgs[0]["content"]
    assert "合同.pdf" in msgs[1]["content"]
    assert "15 万元" in msgs[1]["content"]
    assert "片段" not in msgs[1]["content"]
