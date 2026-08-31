from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from api.security import (
    SESSION_COOKIE,
    create_session_token,
    get_auth_config,
    password_matches,
    require_api_auth,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class AuthenticationState(BaseModel):
    authenticated: bool


@router.post("/login", response_model=AuthenticationState)
def login(body: LoginRequest, response: Response) -> AuthenticationState:
    config = get_auth_config()
    if not config.enabled:
        return AuthenticationState(authenticated=True)
    if not password_matches(body.password, config):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
        )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(config),
        max_age=config.session_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="strict",
        path="/",
    )
    return AuthenticationState(authenticated=True)


@router.post("/logout", response_model=AuthenticationState)
def logout(response: Response) -> AuthenticationState:
    config = get_auth_config()
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=config.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return AuthenticationState(authenticated=False)


@router.get(
    "/me",
    response_model=AuthenticationState,
    dependencies=[Depends(require_api_auth)],
)
def me() -> AuthenticationState:
    return AuthenticationState(authenticated=True)
