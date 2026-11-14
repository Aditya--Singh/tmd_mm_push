"""Login, session and user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import admin_user, client_ip, current_user
from app.core.db import get_db
from app.core.models import User, utcnow
from app.core.security import (
    create_access_token,
    hash_password,
    login_guard,
    password_policy_errors,
    verify_password,
)
from app.core.utils import iso
from app.observability import audit

router = APIRouter(prefix="/api", tags=["auth"])


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "created_at": iso(u.created_at),
        "last_login_at": iso(u.last_login_at),
    }


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    email = body.email.strip().lower()
    wait = login_guard.locked_for(email, ip)
    if wait:
        audit.record(email, "auth.login.locked", details={"retry_after_s": wait}, ip=ip)
        raise HTTPException(429, f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        login_guard.fail(email, ip)
        audit.record(email, "auth.login.failed", ip=ip)
        raise HTTPException(401, "Email or password is incorrect.")
    login_guard.reset(email, ip)
    user.last_login_at = utcnow()
    db.commit()
    audit.record(email, "auth.login", ip=ip)
    return {"access_token": create_access_token(user.id, user.email, user.role), "token_type": "bearer", "user": user_out(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/auth/logout")
def logout(request: Request, user: User = Depends(current_user)):
    audit.record(user.email, "auth.logout", ip=client_ip(request))
    return {"ok": True}


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/change-password")
def change_password(body: PasswordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(User, user.id)
    if not verify_password(body.current_password, row.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    errs = password_policy_errors(body.new_password)
    if errs:
        raise HTTPException(400, "New password needs " + ", ".join(errs) + ".")
    row.password_hash = hash_password(body.new_password)
    row.must_change_password = False
    db.commit()
    audit.record(user.email, "auth.password.changed", ip=client_ip(request))
    return {"ok": True}


class UserIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str
    role: str = "analyst"


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


@router.get("/users")
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users")
def create_user(body: UserIn, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.role not in ("admin", "analyst"):
        raise HTTPException(400, "Role must be admin or analyst.")
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "A user with this email already exists.")
    errs = password_policy_errors(body.password)
    if errs:
        raise HTTPException(400, "Password needs " + ", ".join(errs) + ".")
    u = User(email=body.email.lower(), name=body.name, role=body.role, password_hash=hash_password(body.password), must_change_password=True)
    db.add(u)
    db.commit()
    audit.record(admin.email, "user.create", resource=u.email, details={"role": u.role}, ip=client_ip(request))
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    changes = {}
    if body.name is not None:
        u.name = changes["name"] = body.name
    if body.role is not None:
        if body.role not in ("admin", "analyst"):
            raise HTTPException(400, "Role must be admin or analyst.")
        if u.id == admin.id and body.role != "admin":
            raise HTTPException(400, "You cannot remove your own administrator role.")
        u.role = changes["role"] = body.role
    if body.is_active is not None:
        if u.id == admin.id and not body.is_active:
            raise HTTPException(400, "You cannot deactivate your own account.")
        u.is_active = changes["is_active"] = body.is_active
    if body.password:
        errs = password_policy_errors(body.password)
        if errs:
            raise HTTPException(400, "Password needs " + ", ".join(errs) + ".")
        u.password_hash = hash_password(body.password)
        u.must_change_password = True
        changes["password"] = "reset"
    db.commit()
    audit.record(admin.email, "user.update", resource=u.email, details=changes, ip=client_ip(request))
    return user_out(u)
