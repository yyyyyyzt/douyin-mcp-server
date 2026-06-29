"""structure 层测试（TDD）：文案 -> 结构化卡片。单卡/多卡/去围栏/异常。"""

import json

import pytest

from core import structure


class FakeLLM:
    """按预设脚本依次返回 chat 内容。"""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self._outputs.pop(0)


def _card_payload(cards):
    return json.dumps({"cards": cards}, ensure_ascii=False)


def test_structure_single_card():
    llm = FakeLLM([
        _card_payload([
            {
                "title": "冷热水管走顶规范",
                "content": "冷热水管建议走顶，弹线定位误差应控制在 2mm 以内，避开承重墙。",
            }
        ])
    ])
    cards = structure.structure_text("一段水电改造文案……", llm)
    assert len(cards) == 1
    c = cards[0]
    assert c["title"] == "冷热水管走顶规范"
    assert "走顶" in c["raw_text"]


def test_structure_multiple_cards():
    llm = FakeLLM([
        _card_payload([
            {"title": "卡片1", "content": "内容一"},
            {"title": "卡片2", "content": "内容二"},
        ])
    ])
    cards = structure.structure_text("很长的多主题文案……", llm)
    assert len(cards) == 2
    assert {c["title"] for c in cards} == {"卡片1", "卡片2"}


def test_structure_strips_code_fences():
    raw = "```json\n" + _card_payload([{"title": "T", "content": "正文"}]) + "\n```"
    llm = FakeLLM([raw])
    cards = structure.structure_text("文案", llm)
    assert len(cards) == 1
    assert cards[0]["title"] == "T"


def test_structure_attaches_excerpt_as_raw_text():
    llm = FakeLLM([
        _card_payload([
            {"title": "T", "content": "这是该卡片对应的原文片段"}
        ])
    ])
    cards = structure.structure_text("整段原文……", llm)
    assert cards[0]["raw_text"] == "这是该卡片对应的原文片段"


def test_structure_falls_back_to_full_text_when_no_content():
    full = "完整原始文案内容"
    llm = FakeLLM([_card_payload([{"title": "T"}])])
    cards = structure.structure_text(full, llm)
    assert cards[0]["raw_text"] == full


def test_structure_normalizes_missing_fields():
    llm = FakeLLM([json.dumps({"cards": [{"title": "只有标题"}]}, ensure_ascii=False)])
    cards = structure.structure_text("文案", llm)
    assert cards[0]["title"] == "只有标题"
    assert cards[0]["raw_text"]


def test_structure_builds_structured_json():
    llm = FakeLLM([_card_payload([{"title": "T", "content": "正文"}])])
    cards = structure.structure_text("文案", llm)
    parsed = json.loads(cards[0]["structured_json"])
    assert parsed["title"] == "T"
    assert parsed["content"] == "正文"


def test_structure_retries_on_invalid_json(monkeypatch):
    llm = FakeLLM(["这不是JSON", _card_payload([{"title": "重试成功", "content": "正文"}])])
    cards = structure.structure_text("文案", llm, max_retries=2)
    assert cards[0]["title"] == "重试成功"
    assert len(llm.calls) == 2


def test_structure_raises_after_retries():
    llm = FakeLLM(["坏数据", "还是坏数据"])
    with pytest.raises(structure.StructureError):
        structure.structure_text("文案", llm, max_retries=2)


def test_structure_empty_text_raises():
    llm = FakeLLM([])
    with pytest.raises(ValueError):
        structure.structure_text("   ", llm)
