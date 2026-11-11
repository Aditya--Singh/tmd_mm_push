from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.roles import bench_role_label, news_role_label
from app.auth.security import (
    create_access_token,
    verify_password,
)
from app.database.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Sign in to the platform.

    The account name is matched without regard to case, because people type "Admin" and
    "admin" for the same account and neither spelling should be the wrong one.

    Both roles of the person are returned: the role in the News Feed and the role in Peer
    Benchmarking. Each application is given the one that belongs to it.
    """

    username = request.username.strip()

    user = (
        db.query(User)
        .filter(func.lower(User.username) == username.lower())
        .first()
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    access_token = create_access_token(
        username=user.username,
        role_news=user.role_news,
        role_bench=user.role_bench,
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        role_news=user.role_news,
        role_news_label=news_role_label(user.role_news),
        role_bench=user.role_bench,
        role_bench_label=bench_role_label(user.role_bench),
    )


@router.get(
    "/me",
    response_model=MeResponse,
)
def me(
    current_user: User = Depends(get_current_user),
):
    """
    Resolve the currently authenticated user.

    Used by the landing page to validate a restored session and to
    confirm the roles carried by an existing access token.
    """

    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        role_news=current_user.role_news,
        role_news_label=news_role_label(current_user.role_news),
        role_bench=current_user.role_bench,
        role_bench_label=bench_role_label(current_user.role_bench),
    )
