"""The roles of the platform and how they map onto each service.

The landing page is the single sign-in for the whole platform, so the roles a person holds are
recorded once, in the `users` table of this backend, and every service asks this module what
those roles mean.

The two applications do different work, so a person holds a role in each of them and the two
are kept apart:

``role_news``  the News Feed.
    ``admin``  full access to the news application, including the summary, the application
               insights and the pipeline control.
    ``user``   reads the news feed. A news reader has no part in the pipeline control.

``role_bench`` the Peer Benchmarking application, in that application's own words.
    ``admin``   everything, including the user list.
    ``maker``   collects the figures and drafts the reports.
    ``checker`` approves the figures other people collected.
    ``viewer``  reads the approved figures; the top management view.
    ``user``    reads the approved figures and nothing else.

The names are the ones each application uses, so a value taken from the `users` table can be
handed to the application it belongs to without being translated. The only translation left
is the one an existing installation needs, and that lives in `app/database/migrate.py`.
"""

from typing import Iterable

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.user import User


# ----------------------------------------------------------------------------- the News Feed

NEWS_ROLE_ADMIN = "admin"

NEWS_ROLE_USER = "user"

#: Every role a person may hold in the News Feed.
NEWS_ROLES: tuple[str, ...] = (
    NEWS_ROLE_ADMIN,
    NEWS_ROLE_USER,
)

#: How each role of the News Feed is shown in the interface.
NEWS_ROLE_LABELS: dict[str, str] = {
    NEWS_ROLE_ADMIN: "Administrator",
    NEWS_ROLE_USER: "Reader",
}


# --------------------------------------------------------------------- Peer Benchmarking

BENCH_ROLE_ADMIN = "admin"

BENCH_ROLE_MAKER = "maker"

BENCH_ROLE_CHECKER = "checker"

BENCH_ROLE_VIEWER = "viewer"

BENCH_ROLE_USER = "user"

#: Every role a person may hold in Peer Benchmarking.
BENCH_ROLES: tuple[str, ...] = (
    BENCH_ROLE_ADMIN,
    BENCH_ROLE_MAKER,
    BENCH_ROLE_CHECKER,
    BENCH_ROLE_VIEWER,
    BENCH_ROLE_USER,
)

#: How each role of Peer Benchmarking is shown in the interface. The names are the ones that
#: application uses, so the two never disagree.
BENCH_ROLE_LABELS: dict[str, str] = {
    BENCH_ROLE_ADMIN: "Administrator",
    BENCH_ROLE_MAKER: "Analyst (Maker)",
    BENCH_ROLE_CHECKER: "Approver (Checker)",
    BENCH_ROLE_VIEWER: "Top Management (Viewer)",
    BENCH_ROLE_USER: "Reader",
}

#: The roles of Peer Benchmarking that carry no work of their own. These are the roles that
#: may be handed over without the application being configured to accept staff sign-ins.
BENCH_READ_ONLY_ROLES: tuple[str, ...] = (
    BENCH_ROLE_VIEWER,
    BENCH_ROLE_USER,
)


def is_news_role(value: object) -> bool:
    """Whether the value is one of the News Feed's roles."""
    return isinstance(value, str) and value in NEWS_ROLES


def is_bench_role(value: object) -> bool:
    """Whether the value is one of Peer Benchmarking's roles."""
    return isinstance(value, str) and value in BENCH_ROLES


def news_role_label(role: str) -> str:
    """A name for the News Feed role, for the interface and for the audit trail."""
    return NEWS_ROLE_LABELS.get(role, role.title() if role else "Unknown")


def bench_role_label(role: str) -> str:
    """A name for the Peer Benchmarking role, for the interface and for the audit trail."""
    return BENCH_ROLE_LABELS.get(role, role.title() if role else "Unknown")


def require_news_roles(*roles: str):
    """Require the signed-in user to hold one of the given roles in the News Feed."""

    allowed: Iterable[str] = roles

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role_news not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action needs one of these roles: "
                    f"{', '.join(news_role_label(role) for role in allowed)}"
                ),
            )

        return current_user

    return dependency


def require_bench_roles(*roles: str):
    """Require the signed-in user to hold one of the given roles in Peer Benchmarking."""

    allowed: Iterable[str] = roles

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role_bench not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action needs one of these roles: "
                    f"{', '.join(bench_role_label(role) for role in allowed)}"
                ),
            )

        return current_user

    return dependency
