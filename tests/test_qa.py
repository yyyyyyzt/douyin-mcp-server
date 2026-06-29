"""问答 prompt 组装与引用构造测试。"""

from core import qa


def _card(id=1, title="卫生间防水高度",
          raw_text="卫生间防水要刷到1.8米，门口做挡水坝。", score=2.0):
    return {
        "id": id,
        "title": title,
        "raw_text": raw_text,
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
    cit = qa.to_citation(_card(raw_text=long_raw, score=3.14159))
    assert cit["id"] == 1
    assert cit["title"] == "卫生间防水高度"
    assert len(cit["excerpt"]) <= qa.EXCERPT_LEN + 1
    assert cit["excerpt"].endswith("…")
    assert cit["score"] == 3.1416
