from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal, get_current_principal
from app.db import get_db
from app.modules.identity import service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    signup_intent: str | None = Field(default=None, description="reception | campaigns | both (A01)")
    interface_language: str = "da"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    email_verified: bool
    signup_intent: str | None
    interface_language: str
    created_at: datetime


def user_out(u) -> UserOut:
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, email_verified=u.email_verified_at is not None,
                   signup_intent=u.signup_intent, interface_language=u.interface_language, created_at=u.created_at)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    current: bool


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, db: OrmSession = Depends(get_db)):
    user = service.register(db, email=body.email, password=body.password, display_name=body.display_name,
                            signup_intent=body.signup_intent, interface_language=body.interface_language,
                            request_id=request.state.request_id)
    db.commit()
    return user_out(user)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: OrmSession = Depends(get_db), user_agent: str | None = Header(default=None)):
    user, raw = service.login(db, email=body.email, password=body.password, user_agent=user_agent)
    db.commit()
    return LoginOut(access_token=raw, user=user_out(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    service.logout(db, principal.session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(principal: Principal = Depends(get_current_principal)):
    return user_out(principal.user)


@router.post("/verify-email", response_model=UserOut)
def verify_email(body: TokenIn, db: OrmSession = Depends(get_db)):
    user = service.verify_email(db, body.token)
    db.commit()
    return user_out(user)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    if principal.user.email_verified_at is None:
        service.issue_verification(db, principal.user)
        db.commit()
    return {"status": "queued"}


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ResetRequestIn, db: OrmSession = Depends(get_db)):
    service.request_password_reset(db, body.email)
    db.commit()
    return {"status": "queued"}


@router.post("/password/reset", response_model=UserOut)
def reset_password(body: ResetIn, db: OrmSession = Depends(get_db)):
    user = service.reset_password(db, raw_token=body.token, new_password=body.password)
    db.commit()
    return user_out(user)


@router.get("/sessions", response_model=list[SessionOut])
def sessions(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    return [SessionOut(id=s.id, created_at=s.created_at, last_seen_at=s.last_seen_at, expires_at=s.expires_at,
                       user_agent=s.user_agent, current=s.id == principal.session.id)
            for s in service.list_sessions(db, principal.user.id)]
