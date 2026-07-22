"""日志配置测试。"""

import logging

from core import log_config


def test_enable_dev_mode_sets_debug(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("ZIZHUANG_DEV", raising=False)
    log_config.enable_dev_mode()
    assert log_config.is_dev_mode()
    assert logging.getLogger().level == logging.DEBUG
