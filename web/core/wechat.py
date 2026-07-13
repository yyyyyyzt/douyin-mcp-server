"""微信小程序 code2session。"""

from __future__ import annotations

import requests

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WechatAuthError(Exception):
    """微信登录失败。"""


def code2session(code: str, appid: str, secret: str) -> dict:
    code = (code or "").strip()
    if not code:
        raise WechatAuthError("缺少微信登录 code")
    if not appid or not secret:
        raise WechatAuthError("服务端未配置 WECHAT_APPID / WECHAT_SECRET")

    try:
        resp = requests.get(
            WECHAT_CODE2SESSION_URL,
            params={
                "appid": appid,
                "secret": secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise WechatAuthError(f"微信服务暂不可用: {e}") from e

    if data.get("errcode"):
        raise WechatAuthError(data.get("errmsg") or f"微信登录失败({data.get('errcode')})")
    if not data.get("openid"):
        raise WechatAuthError("微信未返回 openid")
    return data
