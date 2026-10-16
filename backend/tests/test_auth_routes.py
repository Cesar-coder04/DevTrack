import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
from app import config
from app.api import deps
from app.api.routes import auth as auth_routes
from app.db.session import get_db


TRUSTED_ORIGIN = "http://localhost:5173"
SESSION_COOKIE = config.SESSION_COOKIE_NAME
ACCESS_TOKEN = "test-access-token"
BACKEND_DIR = Path(__file__).resolve().parents[1]

TEST_USER = SimpleNamespace(
    id=37,
    username="test-user",
    email="test@example.com",
    display_name="Test User",
    bio=None,
    avatar_key=None,
    is_active=True,
    email_verified_at=None,
    created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    password_hash="password-hash",
)


class ApiPrefixStrippingApp:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            scope = dict(scope)
            scope["path"] = scope["path"][4:]
            scope["raw_path"] = scope["path"].encode()
        await self.app(scope, receive, send)


@pytest.fixture
def client_and_db():
    fake_db = MagicMock()

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(ApiPrefixStrippingApp(app)) as client:
            yield client, fake_db
    finally:
        app.dependency_overrides.pop(get_db, None)


def configure_auth(
    monkeypatch,
    fake_db,
    *,
    user=TEST_USER,
    token=ACCESS_TOKEN,
    expires_at=None,
):
    sessions = []
    expires_at = expires_at or (
        datetime.now(timezone.utc) + timedelta(minutes=30)
    )

    monkeypatch.setattr(
        auth_routes,
        "get_user_by_username",
        lambda db, username: user,
    )
    monkeypatch.setattr(
        auth_routes,
        "verify_password",
        lambda password, password_hash: True,
    )
    monkeypatch.setattr(
        auth_routes,
        "create_access_token",
        lambda user_id: (token, expires_at),
    )
    monkeypatch.setattr(
        auth_routes,
        "hash_access_token",
        lambda value: f"hash:{value}",
    )
    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda value: {"sub": str(user.id)},
    )
    monkeypatch.setattr(
        deps,
        "hash_access_token",
        lambda value: f"hash:{value}",
    )
    fake_db.add.side_effect = sessions.append
    fake_db.scalar.side_effect = lambda statement: (
        sessions[-1] if sessions else None
    )
    fake_db.get.return_value = user
    monkeypatch.setattr(config, "TRUSTED_WEB_ORIGINS", frozenset({TRUSTED_ORIGIN}))
    return sessions, expires_at


def test_cookie_login_sets_http_only_cookie_without_returning_token(
    client_and_db, monkeypatch
):
    client, fake_db = client_and_db
    fixed_now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    expires_at = fixed_now + timedelta(seconds=125, microseconds=900_000)
    configure_auth(monkeypatch, fake_db, expires_at=expires_at)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    monkeypatch.setattr(auth_routes, "datetime", FixedDateTime)
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", True)

    response = client.post(
        "/api/auth/cookie-login",
        data={"username": TEST_USER.username, "password": "password"},
        headers={"Origin": TRUSTED_ORIGIN},
    )

    assert response.status_code == 204
    assert ACCESS_TOKEN not in response.text
    cookie_header = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE}={ACCESS_TOKEN}" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "secure" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()
    assert "path=/api" in cookie_header.lower()
    assert "domain=" not in cookie_header.lower()
    assert "max-age=125" in cookie_header.lower()


def test_cookie_secure_defaults_to_true():
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "production",
            "DEVTRACK_DB_MODE": "development",
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
        }
    )
    environment.pop("DEVTRACK_COOKIE_SECURE", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import SESSION_COOKIE_SECURE; "
            "print(SESSION_COOKIE_SECURE)",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "True"


@pytest.mark.parametrize("app_env", ["production", "dev"])
def test_cookie_secure_cannot_be_disabled_outside_local_development(app_env):
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": app_env,
            "DEVTRACK_DB_MODE": "development",
            "DEVTRACK_COOKIE_SECURE": "false",
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import SESSION_COOKIE_SECURE",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "allowed only in local development" in result.stderr


@pytest.mark.parametrize("app_env", ["development", "local"])
def test_cookie_secure_can_be_disabled_in_local_development(app_env):
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": app_env,
            "DEVTRACK_DB_MODE": "development",
            "DEVTRACK_COOKIE_SECURE": "false",
            "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-123",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import SESSION_COOKIE_SECURE; "
            "print(SESSION_COOKIE_SECURE)",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"


@pytest.mark.parametrize(
    ("active", "password_valid", "expected_status"),
    [(True, False, 401), (False, True, 403)],
)
def test_cookie_login_rejects_invalid_credentials_or_inactive_user(
    client_and_db, monkeypatch, active, password_valid, expected_status
):
    client, fake_db = client_and_db
    user = SimpleNamespace(**{**vars(TEST_USER), "is_active": active})
    configure_auth(monkeypatch, fake_db, user=user)
    monkeypatch.setattr(
        auth_routes,
        "verify_password",
        lambda password, password_hash: password_valid,
    )

    response = client.post(
        "/auth/cookie-login",
        data={"username": user.username, "password": "password"},
        headers={"Origin": TRUSTED_ORIGIN},
    )

    assert response.status_code == expected_status
    assert "set-cookie" not in response.headers
    fake_db.add.assert_not_called()


def test_bearer_login_keeps_existing_json_contract(client_and_db, monkeypatch):
    client, fake_db = client_and_db
    configure_auth(monkeypatch, fake_db)

    response = client.post(
        "/auth/login",
        data={"username": TEST_USER.username, "password": "password"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": ACCESS_TOKEN,
        "token_type": "bearer",
    }
    assert "set-cookie" not in response.headers


def test_cookie_login_authenticates_users_me(client_and_db, monkeypatch):
    client, fake_db = client_and_db
    sessions, _ = configure_auth(monkeypatch, fake_db)
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", False)

    login_response = client.post(
        "/api/auth/cookie-login",
        data={"username": TEST_USER.username, "password": "password"},
        headers={"Origin": TRUSTED_ORIGIN},
    )
    profile_response = client.get("/api/users/me")

    assert login_response.status_code == 204
    assert profile_response.status_code == 200
    assert profile_response.json()["id"] == TEST_USER.id
    assert len(sessions) == 1
    assert sessions[0].token_hash == f"hash:{ACCESS_TOKEN}"
    assert client.cookies.get(SESSION_COOKIE) == ACCESS_TOKEN


@pytest.mark.parametrize(
    "session_state",
    ["invalid_token", "missing", "revoked", "expired"],
)
def test_cookie_auth_rejects_invalid_or_unusable_session(
    client_and_db, monkeypatch, session_state
):
    client, fake_db = client_and_db
    sessions, _ = configure_auth(monkeypatch, fake_db)
    if session_state == "invalid_token":
        monkeypatch.setattr(
            deps,
            "decode_access_token",
            lambda token: (_ for _ in ()).throw(jwt.InvalidTokenError()),
        )
    elif session_state == "missing":
        fake_db.scalar.side_effect = lambda statement: None
    else:
        session = SimpleNamespace(
            revoked_at=(
                datetime.now(timezone.utc)
                if session_state == "revoked"
                else None
            ),
            expires_at=(
                datetime.now(timezone.utc) - timedelta(minutes=1)
                if session_state == "expired"
                else datetime.now(timezone.utc) + timedelta(minutes=30)
            ),
        )
        fake_db.scalar.side_effect = lambda statement: session

    response = client.get(
        "/users/me",
        headers={"Cookie": f"{SESSION_COOKIE}={ACCESS_TOKEN}"},
    )

    assert response.status_code == 401
    assert sessions == []


def test_invalid_bearer_does_not_fall_back_to_valid_cookie(
    client_and_db, monkeypatch
):
    client, fake_db = client_and_db
    configure_auth(monkeypatch, fake_db)
    monkeypatch.setattr(
        deps,
        "decode_access_token",
        lambda token: (_ for _ in ()).throw(jwt.InvalidTokenError()),
    )

    response = client.get(
        "/users/me",
        headers={
            "Authorization": "Bearer invalid-token",
            "Cookie": f"{SESSION_COOKIE}={ACCESS_TOKEN}",
        },
    )

    assert response.status_code == 401
    fake_db.scalar.assert_not_called()


def test_cookie_login_and_mutation_reject_untrusted_origins(
    client_and_db, monkeypatch
):
    client, fake_db = client_and_db
    configure_auth(monkeypatch, fake_db)

    login_response = client.post(
        "/auth/cookie-login",
        data={"username": TEST_USER.username, "password": "password"},
        headers={"Origin": "https://attacker.example"},
    )
    mutation_response = client.patch(
        "/notifications/read-all",
        headers={
            "Cookie": f"{SESSION_COOKIE}={ACCESS_TOKEN}",
            "Origin": "https://attacker.example",
        },
    )

    assert login_response.status_code == 403
    assert mutation_response.status_code == 403
    fake_db.add.assert_not_called()


def test_cookie_auth_requires_origin_for_preferences_get_write(
    client_and_db, monkeypatch
):
    client, fake_db = client_and_db
    configure_auth(monkeypatch, fake_db)

    response = client.get(
        "/users/me/preferences/",
        headers={
            "Cookie": f"{SESSION_COOKIE}={ACCESS_TOKEN}",
            "Origin": "https://attacker.example",
        },
    )

    assert response.status_code == 403
    fake_db.scalar.assert_not_called()


def test_bearer_request_does_not_depend_on_cookie_or_origin(
    client_and_db, monkeypatch
):
    client, fake_db = client_and_db
    configure_auth(monkeypatch, fake_db)
    valid_session = SimpleNamespace(
        revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    fake_db.scalar.side_effect = lambda statement: valid_session

    response = client.get(
        "/users/me",
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == TEST_USER.id
    assert SESSION_COOKIE not in client.cookies
