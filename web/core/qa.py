"""问答 prompt 组装与引用（citation）构造。

防幻觉核心：把检索到的卡片原文 + 结构化步骤注入 prompt，并约束模型「只能依据片段作答」。
- grounded=True：注入命中卡片，要求严格基于片段回答。
- grounded=False：不注入任何卡片，要求先声明「未找到相关标准」，再给出带免责声明的通用参考。
"""

import json
from typing import Any

EXCERPT_LEN = 140

SYSTEM_GROUNDED = """你是一名私人装修监理助手，只能根据下面提供的「知识库片段」回答问题。
要求：
1. 只依据所提供的片段作答，绝对不要编造片段中没有的数据、数字或标准。
2. 回答时尽量引用片段中的标题与关键步骤/标准，让用户知道依据来自哪条知识。
3. 如果这些片段其实并不能回答该问题，请明确说明「根据你当前的知识库，未找到相关标准」，
   再补充一段以「以下是通用知识，仅供参考：」开头的一般性建议。"""

SYSTEM_UNGROUNDED = """你是一名私人装修监理助手。用户的知识库里没有与该问题相关的内容。
你必须：
1. 先用一句话明确声明：「根据你当前的知识库，未找到相关标准」。
2. 然后另起一段，以「以下是通用知识，仅供参考：」开头，给出简明的一般性建议。
3. 绝对不要假装这些通用建议来自用户的知识库。"""


def _format_steps(steps: Any) -> str:
    if not isinstance(steps, list) or not steps:
        return ""
    lines = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        order = s.get("order", "")
        parts = [str(s.get("action", "")).strip()]
        for label, key in (("细节", "detail"), ("标准", "standard"), ("注意", "warning")):
            val = str(s.get(key, "")).strip()
            if val:
                parts.append(f"{label}：{val}")
        text = "｜".join(p for p in parts if p)
        if text:
            lines.append(f"  {order}. {text}")
    return "\n".join(lines)


def _format_card(idx: int, card: dict) -> str:
    title = (card.get("title") or "(无标题)").strip()
    stage = (card.get("stage") or "未分类").strip()
    raw = (card.get("raw_text") or "").strip()
    steps_text = ""
    if card.get("structured_json"):
        try:
            steps = json.loads(card["structured_json"]).get("steps", [])
            steps_text = _format_steps(steps)
        except (json.JSONDecodeError, AttributeError, TypeError):
            steps_text = ""
    block = [f"【片段{idx}】标题：{title}（阶段：{stage}）"]
    if steps_text:
        block.append("步骤/标准：\n" + steps_text)
    if raw:
        block.append("原文：" + raw)
    return "\n".join(block)


def build_messages(question: str, cards: list[dict], grounded: bool) -> list[dict]:
    """组装 chat messages。grounded=False 时不注入卡片。"""
    question = (question or "").strip()
    if grounded and cards:
        context = "\n\n".join(_format_card(i + 1, c) for i, c in enumerate(cards))
        user = (
            f"用户问题：{question}\n\n"
            f"以下是知识库中检索到的相关片段：\n\n{context}\n\n"
            f"请基于上述片段回答用户问题，并指出依据的片段标题。"
        )
        system = SYSTEM_GROUNDED
    else:
        user = f"用户问题：{question}"
        system = SYSTEM_UNGROUNDED
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def to_citation(card: dict) -> dict:
    """把命中卡片转为精简引用对象。"""
    raw = (card.get("raw_text") or "").strip()
    excerpt = raw[:EXCERPT_LEN] + ("…" if len(raw) > EXCERPT_LEN else "")
    return {
        "id": card.get("id"),
        "title": card.get("title"),
        "stage": card.get("stage"),
        "excerpt": excerpt,
        "score": round(float(card.get("score", 0.0) or 0.0), 4),
    }
