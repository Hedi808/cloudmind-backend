from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token

from app.core.auth import (
    current_user_from_request,
    hash_password,
    issue_session,
    require_current_user,
    revoke_session,
    user_to_dict,
    verify_password,
)
from app.core.config import settings
from app.db.database import SessionLocal, create_database_tables
from app.db.models import User
from app.schemas.auth import (
    AuthConfigResponse,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)


router = APIRouter(prefix="/api/auth", tags=["Phase 22 - Authentication"])


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(
        google_enabled=bool(
            settings.google_oauth_client_id and settings.google_oauth_client_secret
        )
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response) -> AuthResponse:
    create_database_tables()
    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        user = User(
            email=payload.email,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            email_verified=False,
        )
        db.add(user)
        db.flush()
        issue_session(db=db, user=user, response=response)

        return AuthResponse(
            status="authenticated",
            message="Welcome to CloudMind.",
            user=UserResponse(**user_to_dict(user)),
        )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response) -> AuthResponse:
    create_database_tables()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == payload.email).first()
        password_valid = verify_password(
            payload.password,
            user.password_hash if user else None,
        )

        if user is None or not password_valid or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email or password is incorrect.",
            )

        issue_session(db=db, user=user, response=response)
        return AuthResponse(
            status="authenticated",
            message="Signed in successfully.",
            user=UserResponse(**user_to_dict(user)),
        )


@router.get("/me", response_model=AuthResponse)
def me(user: User = Depends(require_current_user)) -> AuthResponse:
    return AuthResponse(
        status="authenticated",
        message="Current user loaded.",
        user=UserResponse(**user_to_dict(user)),
    )


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    revoke_session(
        token=request.cookies.get(settings.auth_cookie_name),
        response=response,
    )
    return {"status": "signed_out", "message": "Signed out successfully."}


@router.get("/google/start")
def google_auth_start() -> RedirectResponse:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not configured yet.",
        )

    oauth_state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).decode("ascii").rstrip("=")
    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": oauth_state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)
    _set_oauth_cookie(response, "cloudmind_oauth_state", oauth_state)
    _set_oauth_cookie(response, "cloudmind_oauth_verifier", code_verifier)
    return response


@router.get("/google/callback", name="google_auth_callback")
def google_auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        return _google_redirect(error="Google sign-in was cancelled.")

    expected_state = request.cookies.get("cloudmind_oauth_state")
    code_verifier = request.cookies.get("cloudmind_oauth_verifier")
    if (
        not code
        or not state
        or not expected_state
        or not code_verifier
        or not secrets.compare_digest(state, expected_state)
    ):
        return _google_redirect(error="Google sign-in could not be verified.")

    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=20,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        raw_id_token = token_payload.get("id_token")
        if not raw_id_token:
            raise ValueError("Google did not return an identity token.")

        identity = google_id_token.verify_oauth2_token(
            raw_id_token,
            GoogleAuthRequest(),
            settings.google_oauth_client_id,
        )
        email = str(identity.get("email") or "").strip().casefold()
        google_sub = str(identity.get("sub") or "").strip()
        if not email or not google_sub or not bool(identity.get("email_verified")):
            raise ValueError("Google account email is not verified.")

        create_database_tables()
        with SessionLocal() as db:
            user = db.query(User).filter(User.google_sub == google_sub).first()
            if user is None:
                user = db.query(User).filter(User.email == email).first()

            if user is None:
                user = User(
                    email=email,
                    display_name=str(identity.get("name") or email.split("@", 1)[0])[:100],
                    google_sub=google_sub,
                    avatar_url=str(identity.get("picture") or "") or None,
                    email_verified=True,
                )
                db.add(user)
                db.flush()
            else:
                user.google_sub = google_sub
                user.email_verified = True
                user.avatar_url = str(identity.get("picture") or user.avatar_url or "") or None

            response = _google_redirect(success=True)
            issue_session(db=db, user=user, response=response)
            return response
    except Exception:
        return _google_redirect(error="Google sign-in failed. Check the OAuth configuration.")


def _set_oauth_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/auth/google",
    )


def _google_redirect(
    *,
    success: bool = False,
    error: str | None = None,
) -> RedirectResponse:
    query = urlencode(
        {"auth": "google_success"} if success else {"auth_error": error or "Google sign-in failed."}
    )
    response = RedirectResponse(
        f"{settings.auth_frontend_url.rstrip('/')}?{query}",
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie("cloudmind_oauth_state", path="/api/auth/google")
    response.delete_cookie("cloudmind_oauth_verifier", path="/api/auth/google")
    return response
