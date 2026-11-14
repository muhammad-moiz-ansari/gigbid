from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from apps.api.auth.service import (
    SESSION_LIFETIME_SECONDS,
    authenticate,
    current_session,
    current_user,
    issue_session,
    passwords,
)
from apps.api.config import settings
from apps.api.db import Session, User, now, transaction
from apps.api.schemas.api import Credentials, Profile, Registration, SessionView

router = APIRouter(prefix="/auth", tags=["auth"])


def session_response(db, user, response):
    token, csrf = issue_session(db, user.id)
    response.set_cookie("gigbid_session", token, httponly=True, secure=settings().cookie_secure,
                        samesite="lax", max_age=SESSION_LIFETIME_SECONDS, path="/")
    return SessionView(id=user.id, email=user.email, csrf=csrf, profile=user.profile)


def login_rate(request):
    from apps.api.db import digest, get_record, put_record
    address = request.client.host if request.client else "unknown"
    with transaction() as db:
        key = digest({"ip": address, "window": int(now() // 60)})
        row = get_record(db, "auth", "login_limit", key)
        count = row.value["count"] if row else 0
        if count >= 20:
            raise HTTPException(429, "Too many attempts; retry in a minute")
        put_record(db, "auth", "login_limit", key, {"count": count + 1})


@router.post("/register", response_model=SessionView)
def register(data: Registration, response: Response, request: Request):
    login_rate(request)
    if request.headers.get("origin") not in (None, *settings().web_origins):
        raise HTTPException(403, "Open GigBid at the web address configured in WEB_ORIGIN and try again.")
    try:
        with transaction() as db:
            profile = Profile(**data.profile.model_dump()).model_dump()
            profile["name"] = profile["name"].strip()
            user = User(email=data.email, password_hash=passwords.hash(data.password), profile=profile)
            db.add(user)
            db.flush()
            return session_response(db, user, response)
    except IntegrityError:
        raise HTTPException(409, "Email already registered") from None


@router.post("/login", response_model=SessionView)
def login(data: Credentials, response: Response, request: Request):
    login_rate(request)
    if request.headers.get("origin") not in (None, *settings().web_origins):
        raise HTTPException(403, "Open GigBid at the web address configured in WEB_ORIGIN and try again.")
    user = authenticate(data.email, data.password)
    with transaction() as db:
        return session_response(db, user, response)


@router.get("/me", response_model=SessionView)
def me(user: User = Depends(current_user), session: Session = Depends(current_session)):
    return SessionView(id=user.id, email=user.email, csrf=session.csrf, profile=user.profile)


@router.post("/logout")
def logout(response: Response, session: Session = Depends(current_session)) -> dict:
    with transaction() as db:
        db.delete(db.get(Session, session.token_hash))
    response.delete_cookie("gigbid_session", path="/")
    return {"ok": True}


@router.put("/profile", response_model=Profile)
def update_profile(data: Profile, user: User = Depends(current_user)):
    if data.marketplace_mode is not None and data.marketplace_mode != settings().marketplace_mode:
        raise HTTPException(409, "This marketplace is unavailable in the current workspace")
    if settings().marketplace_mode != "mock" and data.interval_seconds < 14400:
        raise HTTPException(422, "Live search interval must be at least four hours")
    with transaction() as db:
        db.get(User, user.id).profile = data.model_dump()
    return data
