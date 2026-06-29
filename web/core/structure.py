"""文案 -> 结构化知识卡片。

调用 LLM 把一段装修文案提炼为标题 + 正文的知识卡片。
默认每次录入只生成一张卡片（一段视频 / 一次粘贴对应一条知识）。
"""

import json
import re
from typing import Any

_SYSTEM_PROMPT = """你是一名专业的家庭装修知识整理助手。
你的任务：把用户提供的装修相关文案，提炼为一条详尽、实用的知识记录。

要求：
1. 仅依据原文内容提炼，不要编造原文没有的信息、数字或标准。
2. 只输出一张卡片，不要拆分为多条记录（多个要点写入各字段即可）。
3. 尽量充分挖掘原文信息，保留关键数字、尺寸、工艺名称、材料品牌；原文较长时不要过度压缩。
4. 字段说明：
   - title: 简洁标题，概括这段内容（15 字以内为佳）
   - stage: 装修阶段（如：拆改、水电、防水、瓦工、木工、油漆、安装、软装、验收；从原文推断，无则留空）
   - content: 核心知识正文（条理清晰，可用换行或「1. 2. 3.」列出要点）
   - steps: 操作步骤数组，每项为 {"action": "做什么", "detail": "怎么做/注意点"}
   - standards: 验收标准或规范要点（字符串数组，每条一句话）
   - warnings: 常见坑点/风险提示（字符串数组）
   - materials: 涉及的材料/工具（字符串数组，无则 []）
   - tags: 关键词标签（3-6 个，便于检索）
5. 严格输出 JSON 对象，格式为：
   {"cards": [{"title":"...","stage":"...","content":"...","steps":[],"standards":[],"warnings":[],"materials":[],"tags":[]}]}
   不要输出 JSON 以外的任何文字、解释或 Markdown 代码块标记。"""


class StructureError(Exception):
    """结构化失败（如多次解析 JSON 均失败）。"""


def build_messages(raw_text: str, hint_title: str = "") -> list[dict]:
    user = (
        "请把下面这段装修文案提炼为一条详尽的知识记录，"
        "尽量保留原文中的工艺细节、数字标准与注意事项：\n\n"
        + raw_text
    )
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
