"""structure 层测试：文案 -> 单条 Markdown 知识卡片。"""

import json

import pytest

from core import structure


class FakeLLM:
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
                "content_md": "冷热水管建议走顶，弹线定位误差应控制在 2mm 以内。",
            }
        ])
    ])
    card = structure.structure_text_single("一段水电改造文案……", llm)
    assert card["title"] == "冷热水管走顶规范"
    assert "走顶" in card["content_md"]
    assert "structured_json" not in card
    assert "raw_text" not in card


def test_structure_merges_multiple_cards_into_one():
    llm = FakeLLM([
        _card_payload([
            {"title": "卡片1", "content_md": "内容一"},
            {"title": "卡片2", "content_md": "内容二"},
        ])
    ])
    cards = structure.structure_text("很长的多主题文案……", llm)
    assert len(cards) == 1
    assert "内容一" in cards[0]["content_md"]
    assert "内容二" in cards[0]["content_md"]


def test_structure_strips_code_fences():
    raw = "```json\n" + _card_payload([{"title": "T", "content_md": "正文"}]) + "\n```"
    llm = FakeLLM([raw])
    card = structure.structure_text_single("文案", llm)
    assert card["title"] == "T"


def test_structure_falls_back_to_full_text_when_no_content():
    full = "完整原始文案内容"
    llm = FakeLLM([_card_payload([{"title": "T"}])])
    card = structure.structure_text_single(full, llm)
    assert card["content_md"] == full


def test_structure_accepts_legacy_content_field():
    llm = FakeLLM([_card_payload([{"title": "T", "content": "正文"}])])
    card = structure.structure_text_single("文案", llm)
    assert card["content_md"] == "正文"


def test_structure_retries_on_invalid_json():
    llm = FakeLLM(["这不是JSON", _card_payload([{"title": "重试成功", "content_md": "正文"}])])
    card = structure.structure_text_single("文案", llm, max_retries=2)
    assert card["title"] == "重试成功"
    assert len(llm.calls) == 2


def test_structure_raises_after_retries():
    llm = FakeLLM(["坏数据", "还是坏数据"])
    with pytest.raises(structure.StructureError):
        structure.structure_text_single("文案", llm, max_retries=2)


def test_structure_rich_fields_into_markdown():
    llm = FakeLLM([
        _card_payload([
            {
                "title": "卫生间防水",
                "stage": "防水",
                "content": "防水高度应刷到 1.8 米",
                "steps": [{"action": "基层处理", "detail": "清理干净后涂刷"}],
                "standards": ["闭水试验 24 小时无渗漏"],
                "warnings": ["门口要做挡水坝"],
                "materials": ["防水涂料"],
                "tags": ["防水", "卫生间"],
            }
        ])
    ])
    card = structure.structure_text_single("防水要刷到1.8米……", llm)
    assert card["stage"] == "防水"
    assert "1.8 米" in card["content_md"]
    assert "闭水试验" in card["content_md"]
    assert "挡水坝" in card["content_md"]
    assert "基层处理" in card["content_md"]


def test_structure_empty_text_raises():
    llm = FakeLLM([])
    with pytest.raises(ValueError):
        structure.structure_text_single("   ", llm)
