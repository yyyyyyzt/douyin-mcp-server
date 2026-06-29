"""应用配置：从项目根目录 `.env` 与环境变量加载 API Key、模型等。

密钥仅保存在服务端 `.env`，不暴露给浏览器。用户可在界面选择模型（覆盖默认）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 项目根目录（web/core/settings.py -> web -> root）
ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_LLM_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_LLM_MODEL = "Qwen/Qwen3-8B"
DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"
DEFAULT_LLM_TIMEOUT = 60
DEFAULT_LLM_MAX_RETRIES = 3

# 可选模型目录（tier: standard 免费档 / premium 高级档，后期可对 premium 做付费 gating）
LLM_MODEL_CATALOG = [
    {
        "id": "Qwen/Qwen3-8B",
        "name": "Qwen3 8B",
        "tier": "standard",
        "description": "速度快，适合日常知识整理与问答",
    },
    {
        "id": "Qwen/Qwen2.5-7B-Instruct",
        "name": "Qwen2.5 7B",
        "tier": "standard",
        "description": "轻量模型，响应快",
    },
    {
        "id": "Qwen/Qwen2.5-72B-Instruct",
        "name": "Qwen2.5 72B",
        "tier": "premium",
        "description": "理解力强，知识提炼更详尽（适合复杂文案）",
    },
    {
        "id": "deepseek-ai/DeepSeek-V3",
        "name": "DeepSeek V3",
        "tier": "premium",
        "description": "深度推理，合同审查与风险分析更佳",
    },
]

ASR_MODEL_CATALOG = [
    {
        "id": "FunAudioLLM/SenseVoiceSmall",
        "name": "SenseVoice Small",
        "tier": "standard",
        "description": "默认语音识别，速度快",
    },
    {
        "id": "FunAudioLLM/SenseVoiceLarge",
        "name": "SenseVoice Large",
        "tier": "premium",
        "description": "识别准确率更高（适合嘈杂背景）",
    },
]


def load_env_file(path: Path | None = None) -> None:
    """解析 `.env` 写入 os.environ（不覆盖已有环境变量）。"""
    env_path = path or ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key, val)


# 模块导入时加载 .env
load_env_file()


@dataclass(frozen=True)
class Settings:
    api_key: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    asr_model: str
    llm_timeout: int
    llm_max_retries: int

    @property
    def api_configured(self) -> bool:
        return bool(self.api_key or self.llm_api_key)


def get_settings() -> Settings:
    """读取当前配置（每次调用读环境变量，便于测试 monkeypatch）。"""
    api_key = os.getenv("API_KEY", "").strip()
    llm_api_key = (os.getenv("LLM_API_KEY") or api_key).strip()
    try:
        timeout = int(os.getenv("LLM_TIMEOUT", str(DEFAULT_LLM_TIMEOUT)))
    except (TypeError, ValueError):
        timeout = DEFAULT_LLM_TIMEOUT
    try:
        max_retries = int(os.getenv("LLM_MAX_RETRIES", str(DEFAULT_LLM_MAX_RETRIES)))
    except (TypeError, ValueError):
        max_retries = DEFAULT_LLM_MAX_RETRIES
    return Settings(
        api_key=api_key,
        llm_api_key=llm_api_key,
        llm_base_url=os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip() or DEFAULT_LLM_BASE_URL,
        llm_model=os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL,
        asr_model=os.getenv("ASR_MODEL", DEFAULT_ASR_MODEL).strip() or DEFAULT_ASR_MODEL,
        llm_timeout=timeout,
        llm_max_retries=max_retries,
    )


def resolve_llm_model(request_model: str = "") -> str:
    """请求指定模型优先，否则用配置默认。"""
    chosen = (request_model or "").strip()
    return chosen or get_settings().llm_model


def resolve_asr_model(request_model: str = "") -> str:
    chosen = (request_model or "").strip()
    return chosen or get_settings().asr_model
