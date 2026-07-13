"""测试辅助：用户、鉴权头、FastAPI 依赖覆盖。"""

from __future__ import annotations

import app as webapp
from core import auth, db


def ensure_test_user(conn, openid: str = "test-user") -> dict:
    user_id = db.ensure_user(conn, openid)
    user = db.get_user_by_id(conn, user_id)
    assert user is not None
    return user


def auth_headers(user: dict) -> dict[str, str]:
    token = auth.issue_token(user["id"], user["openid"])
    return {"Authorization": f"Bearer {token}"}


def override_current_user(user: dict) -> None:
    def _dep():
        return user

    webapp.app.dependency_overrides[webapp.get_current_user] = _dep


def clear_app_overrides() -> None:
    webapp.app.dependency_overrides.clear()
