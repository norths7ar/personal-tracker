"""Editable application settings, independent from historical business records."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api.security import (
    SESSION_COOKIE,
    create_session_token,
    get_auth_config,
    require_api_auth,
)
from core.settings_models import (
    AccessSettingsUpdate,
    ModelSettingsUpdate,
    RecordSettingsUpdate,
    SettingsResponse,
    StoredSettings,
)
from core.settings_store import (
    SettingsConflict,
    encrypt_secret,
    hash_password,
    public_settings,
    update_settings,
)

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_api_auth)],
)


def save(revision: str, change) -> SettingsResponse:
    try:
        return update_settings(revision, change)
    except SettingsConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=SettingsResponse)
def settings(response: Response) -> SettingsResponse:
    response.headers["Cache-Control"] = "no-store"
    return public_settings()


@router.put("/model", response_model=SettingsResponse)
def update_model(body: ModelSettingsUpdate) -> SettingsResponse:
    def change(settings: StoredSettings) -> None:
        settings.model = body.model
        if body.api_key is not None:
            settings.api_key_encrypted = encrypt_secret(body.api_key.strip())

    return save(body.revision, change)


@router.put("/records", response_model=SettingsResponse)
def update_records(body: RecordSettingsUpdate) -> SettingsResponse:
    def change(settings: StoredSettings) -> None:
        settings.records = body.records

    return save(body.revision, change)


@router.put("/access", response_model=SettingsResponse)
def update_access(
    body: AccessSettingsUpdate, request: Request, response: Response
) -> SettingsResponse:
    # A Secure cookie over plain HTTP can lock the user out of this local app.
    if body.enabled and body.cookie_secure and request.url.scheme != "https":
        raise HTTPException(422, "当前通过 HTTP 访问，不能启用仅 HTTPS 登录 Cookie")

    def change(settings: StoredSettings) -> None:
        access = settings.access
        password = access.password_hash
        if body.password is not None:
            password = hash_password(body.password)
        if body.enabled and not password:
            raise ValueError("启用访问密码前请设置密码")
        invalidate = (
            body.reset_sessions
            or body.password is not None
            or access.enabled != body.enabled
            or access.session_seconds != body.session_seconds
            or access.cookie_secure != body.cookie_secure
        )
        access.enabled = body.enabled
        access.password_hash = password
        access.cookie_secure = body.cookie_secure
        access.session_seconds = body.session_seconds
        if invalidate:
            settings.signing_key_encrypted = encrypt_secret(secrets.token_urlsafe(48))

    result = save(body.revision, change)
    config = get_auth_config()
    if config.enabled:
        # Keep the authorizing browser signed in; invalidate other sessions.
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(config),
            max_age=config.session_seconds,
            httponly=True,
            secure=config.cookie_secure,
            samesite="strict",
            path="/",
        )
    else:
        response.delete_cookie(SESSION_COOKIE, path="/")
    return result
