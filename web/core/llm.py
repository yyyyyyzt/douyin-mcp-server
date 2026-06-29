"""OpenAI 兼容的 LLM 客户端。

设计目标：
- 供应商可替换：通过 base_url / model / api_key 配置，默认硅基流动，
  也兼容 OpenAI、DeepSeek、本地 vLLM/Ollama 等任何 OpenAI 兼容接口。
- 健壮性：内置超时与指数退避重试（网络错误 / 5xx / 429）。
- 易测试：允许注入 session，便于单元测试 mock。
"""

import os
import time
from typing import Optional

import requests

# 默认指向硅基流动（与本仓库语音识别同一平台，可只配一个 key）
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_RETRIES = 3

# 触发重试的 HTTP 状态码
_RETRY_STATUS = {429, 500, 502, 503, 504}


class LLMError(Exception):
    """LLM 调用相关错误。"""


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session=None,
    ):
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self._session = session or requests

    @classmethod
    def from_env(cls) -> "LLMClient":
        """从环境变量构造。LLM_API_KEY 缺失时回退到 API_KEY（与语音识别共用）。"""
        return cls.resolve()

    @classmethod
    def resolve(cls, api_key: str = "") -> "LLMClient":
        """解析 API Key：请求体优先，其次 LLM_API_KEY，再回退 API_KEY。"""
        resolved = (api_key or "").strip() or os.getenv("LLM_API_KEY") or os.getenv("API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
        model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
        timeout = int(os.getenv("LLM_TIMEOUT", str(DEFAULT_TIMEOUT)))
        max_retries = int(os.getenv("LLM_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
        return cls(
            api_key=resolved,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
        )

    def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        """调用 chat/completions，返回首条回复的文本内容。"""
        if not self.api_key:
            raise LLMError("未配置 LLM API Key（请设置 LLM_API_KEY 或 API_KEY）")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )
                status = getattr(resp, "status_code", 200)
                if status in _RETRY_STATUS:
                    last_error = LLMError(f"上游返回可重试状态码 {status}")
                    self._backoff(attempt)
                    continue

                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                self._backoff(attempt)
            except requests.HTTPError as e:
                # 非重试类的 HTTP 错误直接抛出
                raise LLMError(f"LLM 请求失败: {e}") from e
            except (KeyError, ValueError, IndexError) as e:
                raise LLMError(f"LLM 响应解析失败: {e}") from e

        raise LLMError(f"LLM 调用在 {self.max_retries} 次尝试后仍失败: {last_error}")

    def _backoff(self, attempt: int) -> None:
        """指数退避：2s, 4s, 8s ...（最后一次尝试后不再睡眠）。"""
        if attempt < self.max_retries - 1:
            time.sleep(2 ** (attempt + 1))
