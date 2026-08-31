import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Cookie, HTTPException, status

from core.secrets import get_secret

SESSION_COOKIE = "tracker_session"
DEFAULT_SESSION_SECONDS = 60 * 60 * 24 * 30


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    password: str | None
    signing_key: str | None
    cookie_secure: bool
    session_seconds: int


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_auth_config() -> AuthConfig:
    enabled = _as_bool(get_secret("AUTH_ENABLED", "false"))
    password = get_secret("APP_PASSWORD")
    signing_key = get_secret("APP_SESSION_SECRET") or password
    seconds_value = get_secret("APP_SESSION_SECONDS", str(DEFAULT_SESSION_SECONDS))
    try:
        session_seconds = int(seconds_value or DEFAULT_SESSION_SECONDS)
    except ValueError as exc:
        raise RuntimeError("APP_SESSION_SECONDS must be an integer") from exc
    if session_seconds <= 0:
        raise RuntimeError("APP_SESSION_SECONDS must be positive")
    if enabled and (not password or not signing_key):
        raise RuntimeError(
            "AUTH_ENABLED requires APP_PASSWORD and a signing key. "
            "Set APP_SESSION_SECRET or allow APP_PASSWORD to be used as the key."
        )
    return AuthConfig(
        enabled=enabled,
        password=password,
        signing_key=signing_key,
        cookie_secure=_as_bool(get_secret("COOKIE_SECURE", "false")),
        session_seconds=session_seconds,
    )


def password_matches(candidate: str, config: AuthConfig) -> bool:
    return bool(
        config.password
        and hmac.compare_digest(
            candidate.encode("utf-8"), config.password.encode("utf-8")
        )
    )


def create_session_token(config: AuthConfig, *, now: int | None = None) -> str:
    if not config.signing_key:
        raise RuntimeError("Session signing key is not configured")
    issued_at = int(time.time()) if now is None else now
    payload = json.dumps(
        {"v": 1, "iat": issued_at, "exp": issued_at + config.session_seconds},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _encode(payload)
    signature = hmac.new(
        config.signing_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode(signature)}"


def session_is_valid(
    token: str | None, config: AuthConfig, *, now: int | None = None
) -> bool:
    if not token or not config.signing_key:
        return False
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        expected = hmac.new(
            config.signing_key.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_decode(encoded_signature), expected):
            return False
        payload = json.loads(_decode(encoded_payload))
        current_time = int(time.time()) if now is None else now
        return payload.get("v") == 1 and current_time < int(payload["exp"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def require_api_auth(
    tracker_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> None:
    config = get_auth_config()
    if config.enabled and not session_is_valid(tracker_session, config):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
