"""settings 配置加载测试。"""

from pathlib import Path

import pytest

from core import settings


def test_get_settings_reads_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "sk-asr")
    monkeypatch.setenv("LLM_API_KEY", "sk-llm")
    monkeypatch.setenv("LLM_MODEL", "test-llm")
    monkeypatch.setenv("ASR_MODEL", "test-asr")
    s = settings.get_settings()
    assert s.api_key == "sk-asr"
    assert s.llm_api_key == "sk-llm"
    assert s.llm_model == "test-llm"
    assert s.asr_model == "test-asr"
    assert s.api_configured is True


def test_llm_api_key_falls_back_to_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "sk-shared")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    s = settings.get_settings()
    assert s.llm_api_key == "sk-shared"


def test_resolve_llm_model_prefers_request(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "default-model")
    assert settings.resolve_llm_model("user-model") == "user-model"
    assert settings.resolve_llm_model("") == "default-model"


def test_load_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "API_KEY=sk-from-file\nLLM_MODEL=from-file-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    settings.load_env_file(env_file)
    assert settings.get_settings().api_key == "sk-from-file"
    assert settings.get_settings().llm_model == "from-file-model"


def test_model_catalog_not_empty():
    assert len(settings.LLM_MODEL_CATALOG) >= 2
    assert len(settings.ASR_MODEL_CATALOG) >= 1
    assert all("id" in m and "tier" in m for m in settings.LLM_MODEL_CATALOG)
