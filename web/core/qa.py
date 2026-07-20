"""问答 prompt 组装与引用（citation）构造。

防幻觉核心：把检索到的卡片正文注入 prompt，并约束模型「只能依据片段作答」。
系统提示词由 core.prompts 集中管理，可在管理界面调试。
"""

from core import prompts

EXCERPT_LEN = 140


def _format_card(idx: int, card: dict) -> str:
    title = (card.get("title") or "(无标题)").strip()
    body = (card.get("content_md") or "").strip()
    block = [f"【片段{idx}】标题：{title}"]
    if body:
        block.append("内容：" + body)
    return "\n".join(block)


def _format_document(document: dict) -> str:
    name = (document.get("filename") or "上传文件").strip()
    text = (document.get("text") or "").strip()
    return f"【上传文件：{name}】\n{text}"


def build_messages(
    question: str,
    cards: list[dict],
    grounded: bool,
    document: dict | None = None,
) -> list[dict]:
    """组装 chat messages。可注入知识库片段与上传文档。"""
    question = (question or "").strip()
    has_doc = bool(document and (document.get("text") or "").strip())

    if has_doc:
        system = (
            prompts.get("qa_doc_grounded")
            if grounded and cards
            else prompts.get("qa_doc_ungrounded")
        )
        blocks = [f"用户问题：{question}", _format_document(document)]
        if grounded and cards:
            context = "\n\n".join(_format_card(i + 1, c) for i, c in enumerate(cards))
            blocks.append(f"以下是知识库中检索到的相关片段：\n\n{context}")
        blocks.append(prompts.get("qa_doc_user_suffix"))
        user = "\n\n".join(blocks)
    elif grounded and cards:
        context = "\n\n".join(_format_card(i + 1, c) for i, c in enumerate(cards))
        user = (
            f"用户问题：{question}\n\n"
            f"以下是知识库中检索到的相关片段：\n\n{context}\n\n"
            f"{prompts.get('qa_user_grounded_suffix')}"
        )
        system = prompts.get("qa_grounded")
    else:
        user = f"用户问题：{question}"
        system = prompts.get("qa_ungrounded")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def to_citation(card: dict) -> dict:
    """把命中卡片转为精简引用对象。"""
    body = (card.get("content_md") or "").strip()
    excerpt = body[:EXCERPT_LEN] + ("…" if len(body) > EXCERPT_LEN else "")
    return {
        "id": card.get("id"),
        "title": card.get("title"),
        "excerpt": excerpt,
        "score": round(float(card.get("score", 0.0) or 0.0), 4),
    }
