from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal, create_database_tables
from app.db.models import User, UserSession, now_utc


password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("cloudmind-dummy-password-123")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    candidate_hash = stored_hash or DUMMY_PASSWORD_HASH

    try:
        verified = password_hash.verify(password, candidate_hash)
    except Exception:
        return False

    return verified and stored_hash is not None


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(*, db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(48)
    expires_at = now_utc() + timedelta(days=settings.auth_session_days)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=session_token_hash(token),
            expires_at=expires_at,
        )
    )
    user.last_login_at = now_utc()
    db.commit()

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def revoke_session(*, token: str | None, response: Response) -> None:
    if token:
        create_database_tables()
        with SessionLocal() as db:
            auth_session = (
                db.query(UserSession)
                .filter(UserSession.token_hash == session_token_hash(token))
                .first()
            )
            if auth_session and auth_session.revoked_at is None:
                auth_session.revoked_at = now_utc()
                db.commit()

    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def current_user_from_request(request: Request) -> User | None:
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None

    create_database_tables()
    with SessionLocal() as db:
        auth_session = (
            db.query(UserSession)
            .join(User, User.id == UserSession.user_id)
            .filter(
                UserSession.token_hash == session_token_hash(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now_utc(),
                User.is_active.is_(True),
            )
            .first()
        )

        if auth_session is None:
            return None

        user = auth_session.user
        db.expunge(user)
        return user


def require_current_user(request: Request) -> User:
    user = current_user_from_request(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


def user_to_dict(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "email_verified": user.email_verified,
        "auth_provider": "google" if user.google_sub else "password",
    }
