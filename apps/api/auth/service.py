import hashlib
import secrets

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select

from apps.api.config import settings
from apps.api.db import Session, User, now, transaction

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("dummy-unusable-password")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_session(request: Request) -> Session:
    bearer = request.headers.get("authorization", "")
    token = bearer.removeprefix("Bearer ") if bearer.startswith("Bearer ") else request.cookies.get("gigbid_session", "")
    with transaction() as db:
        session = db.get(Session, token_hash(token))
        if not session or session.expires <= now():
            raise HTTPException(401, "Sign in to continue")
        # Bearer callers do not rely on ambient browser cookies.
        if not bearer and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") != settings().web_origin or not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), session.csrf
            ):
                raise HTTPException(403, "Invalid origin or CSRF token")
        return session


def current_user(session: Session = Depends(current_session)) -> User:
    with transaction() as db:
        user = db.get(User, session.tenant)
        if not user:
            raise HTTPException(401, "User no longer exists")
        return user


def issue_session(db, tenant: str):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token), tenant=tenant, csrf=csrf,
                   expires=now() + settings().session_hours * 3600))
    return token, csrf


def authenticate(email: str, password: str):
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == email.lower().strip()))
        valid = passwords.verify(password, user.password_hash if user else DUMMY_HASH)
        if not valid or not user:
            raise HTTPException(401, "Invalid email or password")
        return user
