"""The roles of the platform and how they map onto each service.

The landing page is the single sign-in for the whole platform, so the role a person holds is
recorded once, in the `users` table of this backend, and every service asks this module what
that role means.

The platform knows five roles:

``admin``     full access everywhere, including administration.
``approver`` checks the figures other people extracted.
``analyst``   collects the figures and drafts the reports.
``gm``        reads the approved figures; the top management view.
``user``      reads the news feed. A news reader has no work in the benchmarking app, so
              they are given the same read-only view as the general manager.

Peer Benchmarking keeps its own names for the same jobs. The mapping below is the only place
where the two vocabularies meet.
"""

from typing import Iterable

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.user import User


ROLE_ADMIN = "admin"

ROLE_APPROVER = "approver"

ROLE_ANALYST = "analyst"

ROLE_GM = "gm"

ROLE_USER = "user"


#: Every role a person may hold on the platform.
ROLES: tuple[str, ...] = (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_ANALYST,
    ROLE_GM,
    ROLE_USER,
)


#: How each role is shown in the interface.
ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "Administrator",
    ROLE_APPROVER: "Approver",
    ROLE_ANALYST: "Analyst",
    ROLE_GM: "General Manager",
    ROLE_USER: "Reader",
}


#: The roles that carry work in Peer Benchmarking.
BENCHMARKING_ROLES: tuple[str, ...] = (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_ANALYST,
    ROLE_GM,
)


#: The role to hand to Peer Benchmarking for each platform role.
#
#: Peer Benchmarking names its roles admin, maker, checker and viewer:
#: maker collects the figures, checker approves them, viewer reads them.
BENCHMARKING_ROLE_MAP: dict[str, str] = {
    ROLE_ADMIN: "admin",
    ROLE_APPROVER: "checker",
    ROLE_ANALYST: "maker",
    ROLE_GM: "viewer",
    ROLE_USER: "viewer",
}


def is_role(value: object) -> bool:
    """Whether the value is one of the platform's roles."""
    return isinstance(value, str) and value in ROLES


def role_label(role: str) -> str:
    """A name for the role, for the interface and for the audit trail."""
    return ROLE_LABELS.get(role, role.title() if role else "Unknown")


def benchmarking_role(role: str) -> str:
    """The Peer Benchmarking role that goes with a platform role.

    A role the platform does not know about is treated as the read-only view, so that an
    unexpected value in the user table can never grant more than reading.
    """
    return BENCHMARKING_ROLE_MAP.get(role, "viewer")


def require_roles(*roles: str):
    """Require the signed-in user to hold one of the given roles."""

    allowed: Iterable[str] = roles

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action needs one of these roles: "
                    f"{', '.join(role_label(role) for role in allowed)}"
                ),
            )

        return current_user

    return dependency
