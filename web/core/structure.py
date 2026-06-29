"""文案 -> 结构化知识卡片。

调用 LLM 把一段装修文案提炼为标题 + 正文的知识卡片。
默认每次录入只生成一张卡片（一段视频 / 一次粘贴对应一条知识）。
"""

import json
import re
from typing import Any

_SYSTEM_PROMPT = """你是一名专业的家庭装修知识整理助手。
你的任务：把用户提供的装修相关文案，提炼为一条简洁、实用的知识记录。

要求：
1. 仅依据原文内容提炼，不要编造原文没有的信息、数字或标准。
2. 只输出一张卡片，不要拆分为多条记录（多个要点写在 content 里即可）。
3. 字段说明：
   - title: 简洁标题，概括这段内容（15 字以内为佳）
   - content: 知识正文（条理清晰，可用换行或「1. 2. 3.」列出多个要点）
4. 不要输出阶段、步骤、标准等额外结构，只保留 title 与 content。
5. 严格输出 JSON 对象，格式为：{"cards": [ {"title": "...", "content": "..."} ]}
   不要输出 JSON 以外的任何文字、解释或 Markdown 代码块标记。"""


class StructureError(Exception):
    """结构化失败（如多次解析 JSON 均失败）。"""


def build_messages(raw_text: str, hint_title: str = "") -> list[dict]:
    user = f"请把下面这段装修文案提炼为一条知识记录：\n\n{raw_text}"
    if hint_title:
        user += f"\n\n（可参考的视频标题：{hint_title}）"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
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


def _normalize_card(card: dict, full_text: str) -> dict:
    title = (card.get("title") or "").strip()
    content = (
        (card.get("content") or card.get("raw_excerpt") or card.get("raw_text") or "").strip()
        or full_text
    )
    structured = {"title": title, "content": content}
    return {
        "title": title,
        "raw_text": content,
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
        content = llm.chat(messages, json_mode=True)
        try:
            cards = _parse_cards(content)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue
        return _merge_cards(cards, full_text)

    raise StructureError(f"结构化失败，多次解析 JSON 均未成功: {last_error}")
