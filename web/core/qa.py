"""问答 prompt 组装与引用（citation）构造。

防幻觉核心：把检索到的卡片正文注入 prompt，并约束模型「只能依据片段作答」。
支持结合用户上传的报价单/合同 PDF、Excel 与知识库进行审查分析。
"""

EXCERPT_LEN = 140

SYSTEM_GROUNDED = """你是一名私人自装助手，只能根据下面提供的「知识库片段」回答问题。
要求：
1. 只依据所提供的片段作答，绝对不要编造片段中没有的数据、数字或标准。
2. 回答时尽量引用片段中的标题与关键内容，让用户知道依据来自哪条知识。
3. 如果这些片段其实并不能回答该问题，请明确说明「根据你当前的知识库，未找到相关标准」，
   再补充一段以「以下是通用知识，仅供参考：」开头的一般性建议。"""

SYSTEM_UNGROUNDED = """你是一名私人自装助手。用户的知识库里没有与该问题相关的内容。
你必须：
1. 先用一句话明确声明：「根据你当前的知识库，未找到相关标准」。
2. 然后另起一段，以「以下是通用知识，仅供参考：」开头，给出简明的一般性建议。
3. 绝对不要假装这些通用建议来自用户的知识库。"""

SYSTEM_DOC_GROUNDED = """你是一名私人自装助手，擅长结合用户上传的合同/报价单与知识库进行审查分析。
要求：
1. 上传文件中的金额、项目、条款以文件原文为准，不要编造文件中不存在的内容。
2. 结合知识库片段，指出报价合理性、遗漏项、风险条款及与常规做法的差异。
3. 回答结构清晰：先结论，再分点说明依据（标注来自「上传文件」或「知识库」）。
4. 知识库未覆盖的部分可基于文件分析，但需标明「知识库未覆盖该点」。"""

SYSTEM_DOC_UNGROUNDED = """你是一名私人自装助手。用户上传了合同或报价单，但知识库中暂无相关内容。
要求：
1. 基于上传文件原文进行分析（金额、项目、条款不得编造）。
2. 从装修监理角度指出可关注点、潜在风险与建议补充确认的条款。
3. 明确说明「知识库中暂无相关标准可对照」，分析仅供参考。"""


def _format_card(idx: int, card: dict) -> str:
    title = (card.get("title") or "(无标题)").strip()
    raw = (card.get("raw_text") or "").strip()
    block = [f"【片段{idx}】标题：{title}"]
    if raw:
        block.append("内容：" + raw)
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
        system = SYSTEM_DOC_GROUNDED if grounded and cards else SYSTEM_DOC_UNGROUNDED
        blocks = [f"用户问题：{question}", _format_document(document)]
        if grounded and cards:
            context = "\n\n".join(_format_card(i + 1, c) for i, c in enumerate(cards))
            blocks.append(f"以下是知识库中检索到的相关片段：\n\n{context}")
        blocks.append("请结合上传文件与知识库（如有）回答用户问题，进行合同/报价审查或答疑。")
        user = "\n\n".join(blocks)
    elif grounded and cards:
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
        "excerpt": excerpt,
        "score": round(float(card.get("score", 0.0) or 0.0), 4),
    }
