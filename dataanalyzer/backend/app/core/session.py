"""The guards the routes use.

They live here so that the upstream's modules stay untouched: the routes import one name
from one place.
"""
from app.core.security import current_session, require_admin

__all__ = ["current_session", "require_admin"]
