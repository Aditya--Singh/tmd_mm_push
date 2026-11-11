from sqlalchemy import Column, DateTime, Integer, String

from app.database.database import Base


class User(Base):
    """A person who may sign in to the platform.

    A person holds one role in each application, and the two are kept apart because the
    applications do different work:

    ``role_news``  the role in the News Feed. ``admin`` may also open the summary, the
                   application insights and the pipeline control; ``user`` reads the news.
    ``role_bench`` the role in Peer Benchmarking, in that application's own words:
                   ``admin``, ``maker`` collects the figures, ``checker`` approves them,
                   ``viewer`` reads them, and ``user`` is a reader with no part in the work.

    Both are read from this table and from nowhere else, so a browser can never choose
    either of them.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    role_news = Column(
        String(20),
        nullable=False,
        default="user",
        # One of: admin, user.
        # See app/auth/roles.py for what each role may do.
    )

    role_bench = Column(
        String(20),
        nullable=False,
        default="viewer",
        # One of: admin, maker, checker, viewer, user.
        # These are the names Peer Benchmarking uses for the same jobs.
    )

    is_active = Column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at = Column(
        DateTime,
        nullable=False,
    )
