"""问答 prompt 组装与引用构造测试。"""

import json

from core import qa


def _card(id=1, title="卫生间防水高度", stage="防水阶段",
          raw_text="卫生间防水要刷到1.8米，门口做挡水坝。", steps=None, score=2.0):
    steps = steps if steps is not None else [
        {"order": 1, "action": "刷防水", "detail": "墙面", "standard": "高度1.8米", "warning": "阴角加强"}
    ]
    return {
        "id": id,
        "title": title,
        "stage": stage,
        "raw_text": raw_text,
        "structured_json": json.dumps({"stage": stage, "title": title, "steps": steps}, ensure_ascii=False),
        "score": score,
    }


def test_build_messages_grounded_injects_cards():
    msgs = qa.build_messages("卫生间防水刷多高？", [_card()], grounded=True)
    assert msgs[0]["role"] == "system"
    assert "只能根据" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "卫生间防水高度" in user  # 标题注入
    assert "1.8米" in user  # 步骤/原文注入
    assert "卫生间防水刷多高" in user  # 原始问题


def test_build_messages_ungrounded_excludes_cards():
    msgs = qa.build_messages("今天天气如何？", [], grounded=False)
    assert "未找到相关标准" in msgs[0]["content"]
    assert "仅供参考" in msgs[0]["content"]
    # 不应注入任何卡片上下文
    assert "片段" not in msgs[1]["content"]


def test_to_citation_shape():
    long_raw = "防" * 300
    cit = qa.to_citation(_card(raw_text=long_raw, score=3.14159))
    assert cit["id"] == 1
    assert cit["title"] == "卫生间防水高度"
    assert cit["stage"] == "防水阶段"
    assert len(cit["excerpt"]) <= qa.EXCERPT_LEN + 1  # 截断 + 省略号
    assert cit["excerpt"].endswith("…")
    assert cit["score"] == 3.1416
