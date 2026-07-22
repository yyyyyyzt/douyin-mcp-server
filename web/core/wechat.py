"""微信小程序 code2session。"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger("zizhuang.wechat")

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WechatAuthError(Exception):
    """微信登录失败。"""


def code2session(code: str, appid: str, secret: str) -> dict:
    code = (code or "").strip()
    if not code:
        raise WechatAuthError("缺少微信登录 code")
    if not appid or not secret:
        logger.warning("code2session skipped: WECHAT_APPID or WECHAT_SECRET not configured")
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
        logger.warning("code2session network error: %s", e)
        raise WechatAuthError(f"微信服务暂不可用: {e}") from e

    if data.get("errcode"):
        logger.warning(
            "code2session rejected errcode=%s errmsg=%s appid_suffix=%s",
            data.get("errcode"),
            data.get("errmsg"),
            appid[-4:] if len(appid) >= 4 else appid,
        )
        raise WechatAuthError(data.get("errmsg") or f"微信登录失败({data.get('errcode')})")
    if not data.get("openid"):
        logger.warning("code2session missing openid keys=%s", list(data.keys()))
        raise WechatAuthError("微信未返回 openid")
    logger.debug("code2session ok openid_prefix=%s", str(data.get("openid", ""))[:8])
    return data
