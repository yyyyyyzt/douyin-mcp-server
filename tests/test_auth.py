"""鉴权模块测试：token 签发、校验、过期。"""

import time

import pytest

from core import auth


def test_issue_and_decode_token():
    token = auth.issue_token(42, "openid-test")
    payload = auth.decode_token(token)
    assert payload["uid"] == 42
    assert payload["oid"] == "openid-test"
    assert payload["exp"] > int(time.time())


def test_decode_invalid_token_raises():
    with pytest.raises(auth.AuthError):
        auth.decode_token("not-a-valid-token")
    with pytest.raises(auth.AuthError):
        auth.decode_token("abc.def")


def test_decode_tampered_token_raises():
    token = auth.issue_token(1, "x")
    body, _sig = token.split(".", 1)
    bad = body + ".0000"
    with pytest.raises(auth.AuthError):
        auth.decode_token(bad)


def test_decode_expired_token_raises(monkeypatch):
    fixed = int(time.time()) + 100
    monkeypatch.setattr(time, "time", lambda: fixed)
    token = auth.issue_token(1, "x", ttl=1)
    monkeypatch.setattr(time, "time", lambda: fixed + 10)
    with pytest.raises(auth.AuthError):
        auth.decode_token(token)
