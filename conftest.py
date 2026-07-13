"""Pytest 全局配置：把核心模块所在目录加入 import 路径。

这样测试可以直接 `from core import db, llm, structure`，
也能 `from app import app` 加载 WebUI。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
# 让 web/core 可被导入为顶层包 core，app.py 可被导入为 app
sys.path.insert(0, str(ROOT / "web"))
# 抖音下载/转写脚本（app.py 依赖）
sys.path.insert(0, str(ROOT / "douyin-video" / "scripts"))


@pytest.fixture(autouse=True)
def _test_api_key(monkeypatch):
    """测试环境默认提供 API Key（模拟 .env 已配置）。"""
    monkeypatch.setenv("API_KEY", "sk-test")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ALLOW_LOCAL_AUTH", "1")
