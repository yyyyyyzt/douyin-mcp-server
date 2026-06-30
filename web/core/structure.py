"""文案 -> 结构化知识卡片。

调用 LLM 把一段装修文案提炼为标题 + 正文的知识卡片。
默认每次录入只生成一张卡片（一段视频 / 一次粘贴对应一条知识）。
"""

import json
import re
from typing import Any

from core import prompts


class StructureError(Exception):
    """结构化失败（如多次解析 JSON 均失败）。"""


def build_messages(raw_text: str, hint_title: str = "") -> list[dict]:
    intro = prompts.get("structure_user_intro")
    user = intro + "\n\n" + raw_text
    if hint_title:
        user += f"\n\n（可参考的视频标题：{hint_title}）"
    return [
        {"role": "system", "content": prompts.get("structure_system")},
        {"role": "user", "content": user},
    ]


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_json_object(text: str) -> str:
    """从文本中截取第一个完整的 JSON 对象（容忍前后噪声）。"""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_cards(content: str) -> list[dict]:
    cleaned = _strip_code_fences(content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = json.loads(_extract_json_object(cleaned))

    if isinstance(data, dict) and "cards" in data:
        cards = data["cards"]
    elif isinstance(data, list):
        cards = data
    elif isinstance(data, dict):
        cards = [data]
    else:
        raise ValueError("无法识别的结构")

    if not isinstance(cards, list) or not cards:
        raise ValueError("cards 为空或非列表")
    return cards


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                action = (item.get("action") or "").strip()
                detail = (item.get("detail") or "").strip()
                if action and detail:
                    out.append(f"{action}：{detail}")
                elif action:
                    out.append(action)
        return out
    return []


def _format_steps(steps: Any) -> str:
    if not steps or not isinstance(steps, list):
        return ""
    lines = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        action = (step.get("action") or "").strip()
        detail = (step.get("detail") or "").strip()
        if action and detail:
            lines.append(f"{i}. {action}：{detail}")
        elif action:
            lines.append(f"{i}. {action}")
    return "\n".join(lines)


def _build_raw_text(card: dict, full_text: str) -> str:
    """把结构化字段拼成可检索的正文（供 FTS 与展示）。"""
    content = (
        (card.get("content") or card.get("raw_excerpt") or card.get("raw_text") or "").strip()
        or full_text
    )
    parts = [content]
    stage = (card.get("stage") or "").strip()
    if stage:
        parts.insert(0, f"【阶段：{stage}】")

    steps_text = _format_steps(card.get("steps"))
    if steps_text:
        parts.append("操作步骤：\n" + steps_text)

    for label, key in (
        ("验收标准", "standards"),
        ("风险提示", "warnings"),
        ("材料工具", "materials"),
    ):
        items = _as_str_list(card.get(key))
        if items:
            parts.append(f"{label}：\n" + "\n".join(f"- {x}" for x in items))

    tags = _as_str_list(card.get("tags"))
    if tags:
        parts.append("标签：" + "、".join(tags))

    return "\n\n".join(parts).strip() or full_text


def _normalize_card(card: dict, full_text: str) -> dict:
    title = (card.get("title") or "").strip()
    stage = (card.get("stage") or "").strip() or None
    raw_text = _build_raw_text(card, full_text)

    structured: dict[str, Any] = {
        "title": title,
        "stage": stage or "",
        "content": (card.get("content") or "").strip() or raw_text,
        "steps": card.get("steps") if isinstance(card.get("steps"), list) else [],
        "standards": _as_str_list(card.get("standards")),
        "warnings": _as_str_list(card.get("warnings")),
        "materials": _as_str_list(card.get("materials")),
        "tags": _as_str_list(card.get("tags")),
    }

    return {
        "title": title,
        "stage": stage,
        "raw_text": raw_text,
        "structured_json": json.dumps(structured, ensure_ascii=False),
    }


def _merge_cards(cards: list[dict], full_text: str) -> dict:
    """将多张卡片合并为一条（兜底）。"""
    if not cards:
        return _normalize_card({}, full_text)
    if len(cards) == 1:
        return _normalize_card(cards[0] if isinstance(cards[0], dict) else {}, full_text)
    title = (cards[0].get("title") or "装修知识要点").strip() if isinstance(cards[0], dict) else "装修知识要点"
    parts = []
    for i, c in enumerate(cards, 1):
        if not isinstance(c, dict):
            continue
        t = (c.get("title") or f"要点{i}").strip()
        body = (c.get("content") or c.get("raw_excerpt") or "").strip()
        parts.append(f"{i}. {t}\n{body}" if body else f"{i}. {t}")
    merged = "\n\n".join(parts) or full_text
    return _normalize_card({"title": title, "content": merged}, full_text)


def structure_text(raw_text: str, llm, max_retries: int = 2, hint_title: str = "") -> list[dict]:
    """把文案结构化为知识卡片（默认只返回一张）。"""
    card = structure_text_single(raw_text, llm, max_retries=max_retries, hint_title=hint_title)
    return [card]


def structure_text_single(
    raw_text: str,
    llm,
    max_retries: int = 2,
    hint_title: str = "",
) -> dict:
    """把文案结构化为单条知识卡片。"""
    if not raw_text or not raw_text.strip():
        raise ValueError("文案内容不能为空")

    full_text = raw_text.strip()
    messages = build_messages(full_text, hint_title=hint_title)

    last_error: Exception | None = None
    for _ in range(max(1, max_retries)):
        content = llm.chat(messages, json_mode=True, temperature=0.35)
        try:
            cards = _parse_cards(content)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue
        return _merge_cards(cards, full_text)

    raise StructureError(f"结构化失败，多次解析 JSON 均未成功: {last_error}")
