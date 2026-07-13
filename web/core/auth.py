"""会话令牌：HMAC 签名 Bearer token。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

DEFAULT_TTL_SECONDS = 30 * 24 * 3600


class AuthError(Exception):
    """令牌无效或已过期。"""


def session_secret() -> str:
    secret = os.getenv("SESSION_SECRET", "").strip()
    if not secret:
        secret = "dev-insecure-change-me"
    return secret


def issue_token(user_id: int, openid: str, ttl: int = DEFAULT_TTL_SECONDS) -> str:
    payload = {
        "uid": int(user_id),
        "oid": openid,
        "exp": int(time.time()) + int(ttl),
    }
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    sig = hmac.new(session_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def decode_token(token: str) -> dict[str, Any]:
    token = (token or "").strip()
    if not token or "." not in token:
        raise AuthError("无效的登录凭证")
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(session_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise AuthError("无效的登录凭证")
    pad = "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except (json.JSONDecodeError, ValueError) as e:
        raise AuthError("无效的登录凭证") from e
    exp = int(payload.get("exp", 0))
    if exp < int(time.time()):
        raise AuthError("登录已过期，请重新登录")
    if "uid" not in payload or "oid" not in payload:
        raise AuthError("无效的登录凭证")
    return payload
