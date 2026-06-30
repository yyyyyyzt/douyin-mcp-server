"""集中管理 LLM 系统提示词，供超级管理员在界面或 data/prompts.json 中调试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.settings import ROOT

PROMPTS_PATH = Path(
    __import__("os").getenv("PROMPTS_FILE", str(ROOT / "data" / "prompts.json"))
)

# 注册表：key -> 元数据 + 默认正文
PROMPT_REGISTRY: dict[str, dict[str, str]] = {
    "structure_system": {
        "label": "知识整理 · 系统提示",
        "description": "把装修文案结构化为知识卡片时发给模型的系统指令。",
        "used_in": "收集页 · 链接转写 / 文字整理",
        "default": """你是一名专业的家庭装修知识整理助手。
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
   不要输出 JSON 以外的任何文字、解释或 Markdown 代码块标记。""",
    },
    "structure_user_intro": {
        "label": "知识整理 · 用户消息开头",
        "description": "整理时拼在用户原文前面的引导语。",
        "used_in": "收集页 · 知识整理",
        "default": "请把下面这段装修文案提炼为一条详尽的知识记录，尽量保留原文中的工艺细节、数字标准与注意事项：",
    },
    "qa_grounded": {
        "label": "问答 · 有知识依据",
        "description": "检索到相关知识片段时的系统提示。",
        "used_in": "问答页 · 有引用回答",
        "default": """你是一名私人自装助手，只能根据下面提供的「知识库片段」回答问题。
要求：
1. 只依据所提供的片段作答，绝对不要编造片段中没有的数据、数字或标准。
2. 回答时尽量引用片段中的标题与关键内容，让用户知道依据来自哪条知识。
3. 如果这些片段其实并不能回答该问题，请明确说明「根据你当前的知识库，未找到相关标准」，
   再补充一段以「以下是通用知识，仅供参考：」开头的一般性建议。""",
    },
    "qa_ungrounded": {
        "label": "问答 · 无知识依据",
        "description": "知识库未命中时的系统提示。",
        "used_in": "问答页 · 无引用回答",
        "default": """你是一名私人自装助手。用户的知识库里没有与该问题相关的内容。
你必须：
1. 先用一句话明确声明：「根据你当前的知识库，未找到相关标准」。
2. 然后另起一段，以「以下是通用知识，仅供参考：」开头，给出简明的一般性建议。
3. 绝对不要假装这些通用建议来自用户的知识库。""",
    },
    "qa_doc_grounded": {
        "label": "问答 · 报价单 + 有知识依据",
        "description": "上传文件且检索到知识片段时的系统提示。",
        "used_in": "问答页 · 合同/报价审查（有知识库）",
        "default": """你是一名私人自装助手，擅长结合用户上传的合同/报价单与知识库进行审查分析。
要求：
1. 上传文件中的金额、项目、条款以文件原文为准，不要编造文件中不存在的内容。
2. 结合知识库片段，指出报价合理性、遗漏项、风险条款及与常规做法的差异。
3. 回答结构清晰：先结论，再分点说明依据（标注来自「上传文件」或「知识库」）。
4. 知识库未覆盖的部分可基于文件分析，但需标明「知识库未覆盖该点」。""",
    },
    "qa_doc_ungrounded": {
        "label": "问答 · 报价单 + 无知识依据",
        "description": "上传文件但知识库未命中时的系统提示。",
        "used_in": "问答页 · 合同/报价审查（无知识库）",
        "default": """你是一名私人自装助手。用户上传了合同或报价单，但知识库中暂无相关内容。
要求：
1. 基于上传文件原文进行分析（金额、项目、条款不得编造）。
2. 从装修监理角度指出可关注点、潜在风险与建议补充确认的条款。
3. 明确说明「知识库中暂无相关标准可对照」，分析仅供参考。""",
    },
    "qa_user_grounded_suffix": {
        "label": "问答 · 有依据时用户消息结尾",
        "description": "注入知识片段后，追加给模型的结尾引导。",
        "used_in": "问答页 · 有引用回答",
        "default": "请基于上述片段回答用户问题，并指出依据的片段标题。",
    },
    "qa_doc_user_suffix": {
        "label": "问答 · 报价单用户消息结尾",
        "description": "结合上传文件与知识库时的结尾引导。",
        "used_in": "问答页 · 合同/报价审查",
        "default": "请结合上传文件与知识库（如有）回答用户问题，进行合同/报价审查或答疑。",
    },
}


def _default_values() -> dict[str, str]:
    return {key: meta["default"] for key, meta in PROMPT_REGISTRY.items()}


def _load_overrides() -> dict[str, str]:
    if not PROMPTS_PATH.is_file():
        return {}
    try:
        data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(v) for k, v in data.items() if k in PROMPT_REGISTRY and isinstance(v, str)}


def get_all() -> dict[str, str]:
    """返回合并后的全部提示词（默认 + 自定义覆盖）。"""
    merged = _default_values()
    merged.update(_load_overrides())
    return merged


def get(key: str) -> str:
    """读取单条提示词。"""
    if key not in PROMPT_REGISTRY:
        raise KeyError(f"未知提示词: {key}")
    overrides = _load_overrides()
    if key in overrides:
        return overrides[key]
    return PROMPT_REGISTRY[key]["default"]


def list_for_admin() -> list[dict[str, Any]]:
    """供管理界面展示：含元数据、当前内容与是否自定义。"""
    overrides = _load_overrides()
    items = []
    for key, meta in PROMPT_REGISTRY.items():
        content = overrides.get(key, meta["default"])
        items.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "used_in": meta["used_in"],
            "content": content,
            "is_custom": key in overrides,
        })
    return items


def save(updates: dict[str, str]) -> None:
    """保存自定义提示词（仅接受已注册 key）。"""
    current = _load_overrides()
    defaults = _default_values()
    for key, value in updates.items():
        if key not in PROMPT_REGISTRY:
            continue
        text = (value or "").strip()
        if not text:
            current.pop(key, None)
            continue
        if text == defaults[key]:
            current.pop(key, None)
        else:
            current[key] = text
    PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if current:
        PROMPTS_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif PROMPTS_PATH.is_file():
        PROMPTS_PATH.unlink()


def reset() -> None:
    """清除全部自定义，恢复默认。"""
    if PROMPTS_PATH.is_file():
        PROMPTS_PATH.unlink()


def example_path() -> Path:
    return ROOT / "prompts.example.json"
