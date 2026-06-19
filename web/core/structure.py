"""文案 -> 结构化知识卡片。

调用 LLM 把一段装修文案抽取为固定 schema 的知识卡片，支持一段文案拆成多张卡片。
返回的每张卡片包含可直接入库的字段：stage / title / steps / raw_text / structured_json。
"""

import json
import re
from typing import Any

DEFAULT_STAGE = "未分类"

_SYSTEM_PROMPT = """你是一名专业的家庭装修知识整理助手。
你的任务：把用户提供的装修相关文案，抽取为结构化的「知识卡片」。

要求：
1. 仅依据原文内容抽取，不要编造原文没有的数据、数字或标准。
2. 如果一段文案包含多个相对独立的主题，拆分为多张卡片；否则只输出一张。
3. 每张卡片包含字段：
   - stage: 所属阶段（如 水电改造 / 泥木 / 油漆 / 防水 / 拆改 / 验收 等），无法判断填 "未分类"
   - title: 简洁的标题
   - steps: 步骤数组，每个步骤含 order(序号), action(动作), detail(细节), standard(标准/规范), warning(注意事项)；没有则给空数组
   - raw_excerpt: 该卡片对应的原文片段（尽量摘自原文）
4. 严格输出 JSON 对象，格式为：{"cards": [ {卡片1}, {卡片2}, ... ]}
   不要输出 JSON 以外的任何文字、解释或 Markdown 代码块标记。"""


class StructureError(Exception):
    """结构化失败（如多次解析 JSON 均失败）。"""


def build_messages(raw_text: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"请把下面这段装修文案结构化为知识卡片：\n\n{raw_text}"},
    ]


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    # 去掉 ```json ... ``` 或 ``` ... ``` 包裹
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
        # 直接给了单张卡片
        cards = [data]
    else:
        raise ValueError("无法识别的结构")

    if not isinstance(cards, list) or not cards:
        raise ValueError("cards 为空或非列表")
    return cards


def _normalize_step(step: Any, index: int) -> dict:
    if not isinstance(step, dict):
        return {"order": index + 1, "action": str(step), "detail": "", "standard": "", "warning": ""}
    return {
        "order": step.get("order", index + 1),
        "action": step.get("action", ""),
        "detail": step.get("detail", ""),
        "standard": step.get("standard", ""),
        "warning": step.get("warning", ""),
    }


def _normalize_card(card: dict, full_text: str) -> dict:
    stage = (card.get("stage") or DEFAULT_STAGE).strip() or DEFAULT_STAGE
    title = (card.get("title") or "").strip()
    raw_steps = card.get("steps") or []
    steps = [_normalize_step(s, i) for i, s in enumerate(raw_steps)] if isinstance(raw_steps, list) else []

    raw_text = (card.get("raw_excerpt") or "").strip() or full_text

    structured = {"stage": stage, "title": title, "steps": steps}
    return {
        "stage": stage,
        "title": title,
        "steps": steps,
        "raw_text": raw_text,
        "structured_json": json.dumps(structured, ensure_ascii=False),
    }


def structure_text(raw_text: str, llm, max_retries: int = 2) -> list[dict]:
    """把文案结构化为一张或多张知识卡片。

    参数:
        raw_text: 原始文案
        llm: 具备 chat(messages, json_mode=...) 方法的客户端
        max_retries: JSON 解析失败时的最大尝试次数
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("文案内容不能为空")

    full_text = raw_text.strip()
    messages = build_messages(full_text)

    last_error: Exception | None = None
    for _ in range(max(1, max_retries)):
        content = llm.chat(messages, json_mode=True)
        try:
            cards = _parse_cards(content)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue
        return [_normalize_card(c if isinstance(c, dict) else {}, full_text) for c in cards]

    raise StructureError(f"结构化失败，多次解析 JSON 均未成功: {last_error}")
