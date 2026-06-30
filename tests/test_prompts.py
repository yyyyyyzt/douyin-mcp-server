"""提示词集中管理测试。"""

import json

from core import prompts


def test_get_returns_default_when_no_file(tmp_path, monkeypatch):
    path = tmp_path / "prompts.json"
    monkeypatch.setattr(prompts, "PROMPTS_PATH", path)
    text = prompts.get("qa_grounded")
    assert "知识库片段" in text
    assert prompts.list_for_admin()[0]["is_custom"] is False


def test_save_and_load_custom_prompt(tmp_path, monkeypatch):
    path = tmp_path / "prompts.json"
    monkeypatch.setattr(prompts, "PROMPTS_PATH", path)
    custom = "自定义问答系统提示"
    prompts.save({"qa_grounded": custom})
    assert prompts.get("qa_grounded") == custom
    item = next(x for x in prompts.list_for_admin() if x["key"] == "qa_grounded")
    assert item["is_custom"] is True


def test_reset_clears_custom(tmp_path, monkeypatch):
    path = tmp_path / "prompts.json"
    monkeypatch.setattr(prompts, "PROMPTS_PATH", path)
    prompts.save({"qa_grounded": "临时"})
    prompts.reset()
    assert not path.exists()
    assert "知识库片段" in prompts.get("qa_grounded")


def test_structure_build_messages_uses_prompts(tmp_path, monkeypatch):
    path = tmp_path / "prompts.json"
    monkeypatch.setattr(prompts, "PROMPTS_PATH", path)
    prompts.save({"structure_user_intro": "【测试引导】"})
    from core.structure import build_messages

    msgs = build_messages("防水要刷到1.8米")
    assert msgs[0]["content"] == prompts.get("structure_system")
    assert "【测试引导】" in msgs[1]["content"]
