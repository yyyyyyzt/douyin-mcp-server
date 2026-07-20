"""文案 -> Markdown 知识卡片。

调用 LLM 把一段装修文案提炼为标题 + Markdown 正文。
默认每次录入只生成一张卡片（一段视频 / 一次粘贴对应一条知识）。
"""

from __future__ import annotations

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


def _format_steps_md(steps: Any) -> str:
    if not steps or not isinstance(steps, list):
        return ""
    lines = []
    for i, step in enumerate(steps, 1):
        if isinstance(step, str) and step.strip():
            lines.append(f"{i}. {step.strip()}")
            continue
        if not isinstance(step, dict):
            continue
        action = (step.get("action") or "").strip()
        detail = (step.get("detail") or "").strip()
        if action and detail:
            lines.append(f"{i}. **{action}**：{detail}")
        elif action:
            lines.append(f"{i}. **{action}**")
    return "\n".join(lines)


def _build_content_md(card: dict, full_text: str) -> str:
    """把 LLM 字段拼成 Markdown 正文。"""
    # 优先直接使用 content_md / content
    direct = (
        card.get("content_md")
        or card.get("content")
        or card.get("raw_excerpt")
        or card.get("raw_text")
        or ""
    )
    direct = str(direct).strip()

    parts: list[str] = []
    if direct:
        parts.append(direct)

    steps_md = _format_steps_md(card.get("steps"))
    if steps_md and "操作步骤" not in direct and "步骤" not in direct[:80]:
        parts.append("## 操作步骤\n\n" + steps_md)

    for label, key in (
        ("验收标准", "standards"),
        ("风险提示", "warnings"),
        ("材料工具", "materials"),
    ):
        items = _as_str_list(card.get(key))
        if items and label not in direct:
            bullet = "\n".join(f"- {x}" for x in items)
            parts.append(f"## {label}\n\n{bullet}")

    tags = _as_str_list(card.get("tags"))
    if tags and "标签" not in direct:
        parts.append("标签：" + "、".join(tags))

    body = "\n\n".join(parts).strip()
    return body or full_text


def _normalize_card(card: dict, full_text: str) -> dict:
    title = (card.get("title") or "").strip()
    stage = (card.get("stage") or "").strip() or None
    content_md = _build_content_md(card, full_text)
    return {
        "title": title,
        "stage": stage,
        "content_md": content_md,
    }


def _merge_cards(cards: list[dict], full_text: str) -> dict:
    if not cards:
        return _normalize_card({}, full_text)
    if len(cards) == 1:
        return _normalize_card(cards[0] if isinstance(cards[0], dict) else {}, full_text)
    title = (
        (cards[0].get("title") or "装修知识要点").strip()
        if isinstance(cards[0], dict)
        else "装修知识要点"
    )
    parts = []
    for i, c in enumerate(cards, 1):
        if not isinstance(c, dict):
            continue
        t = (c.get("title") or f"要点{i}").strip()
        body = (
            c.get("content_md") or c.get("content") or c.get("raw_excerpt") or ""
        ).strip()
        if body:
            parts.append(f"## {i}. {t}\n\n{body}")
        else:
            parts.append(f"## {i}. {t}")
    merged = "\n\n".join(parts) or full_text
    return _normalize_card({"title": title, "content_md": merged}, full_text)


def structure_text(raw_text: str, llm, max_retries: int = 2, hint_title: str = "") -> list[dict]:
    card = structure_text_single(raw_text, llm, max_retries=max_retries, hint_title=hint_title)
    return [card]


def structure_text_single(
    raw_text: str,
    llm,
    max_retries: int = 2,
    hint_title: str = "",
) -> dict:
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
