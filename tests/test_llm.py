"""llm 层测试（TDD）：OpenAI 兼容、可替换供应商、超时与重试退避。"""

import pytest

from core import llm


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status {self.status_code}", response=self)


class FakeSession:
    """记录调用并按脚本返回/抛出。"""

    def __init__(self, responses):
        # responses: 列表，每个元素为 FakeResponse 或 Exception 实例
        self._responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok_response(content="你好"):
    return FakeResponse(
        status_code=200,
        json_data={"choices": [{"message": {"content": content}}]},
    )


def test_chat_returns_content():
    session = FakeSession([_ok_response("结构化结果")])
    client = llm.LLMClient(api_key="sk-test", base_url="https://api.example.com/v1", model="test-model", session=session)
    out = client.chat([{"role": "user", "content": "hi"}])
    assert out == "结构化结果"


def test_chat_sends_auth_and_model():
    session = FakeSession([_ok_response()])
    client = llm.LLMClient(api_key="sk-secret", base_url="https://api.example.com/v1", model="my-model", session=session)
    client.chat([{"role": "user", "content": "hi"}])

    call = session.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer sk-secret"
    assert call["json"]["model"] == "my-model"
    assert "timeout" in call  # 必须带超时


def test_chat_passes_timeout():
    session = FakeSession([_ok_response()])
    client = llm.LLMClient(api_key="k", base_url="https://x/v1", model="m", timeout=12, session=session)
    client.chat([{"role": "user", "content": "hi"}])
    assert session.calls[0]["timeout"] == 12


def test_chat_supports_json_response_format():
    session = FakeSession([_ok_response('{"a":1}')])
    client = llm.LLMClient(api_key="k", base_url="https://x/v1", model="m", session=session)
    client.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert session.calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_chat_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    import requests

    session = FakeSession([
        requests.ConnectionError("boom"),
        FakeResponse(status_code=503, text="busy"),
        _ok_response("终于成功"),
    ])
    client = llm.LLMClient(api_key="k", base_url="https://x/v1", model="m", max_retries=3, session=session)
    out = client.chat([{"role": "user", "content": "hi"}])
    assert out == "终于成功"
    assert len(session.calls) == 3


def test_chat_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    import requests

    session = FakeSession([requests.ConnectionError("x")] * 5)
    client = llm.LLMClient(api_key="k", base_url="https://x/v1", model="m", max_retries=2, session=session)
    with pytest.raises(llm.LLMError):
        client.chat([{"role": "user", "content": "hi"}])
    # max_retries=2 表示最多尝试 2 次
    assert len(session.calls) == 2


def test_missing_api_key_raises():
    with pytest.raises(llm.LLMError):
        llm.LLMClient(api_key="", base_url="https://x/v1", model="m").chat([{"role": "user", "content": "hi"}])


def test_from_env_reads_config(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-env")
    monkeypatch.setenv("LLM_BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    client = llm.LLMClient.from_env()
    assert client.api_key == "sk-env"
    assert client.base_url == "https://env.example.com/v1"
    assert client.model == "env-model"


def test_from_env_falls_back_to_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("API_KEY", "sk-shared")
    client = llm.LLMClient.from_env()
    assert client.api_key == "sk-shared"
