from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.roles import role_label
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
    user = db.query(User).filter(User.username == request.username).first()

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
        role=user.role,
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        role=user.role,
        role_label=role_label(user.role),
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
    confirm the role carried by an existing access token.
    """

    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        role_label=role_label(current_user.role),
    )
