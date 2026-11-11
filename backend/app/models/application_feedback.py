from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database.database import Base


class ApplicationFeedback(Base):
    __tablename__ = "application_feedback"

    id = Column(Integer, primary_key=True)

    username = Column(String(100), nullable=False)

    # The role the person held in the News Feed when they gave the feedback.
    role = Column(String(20), nullable=False)

    # The role the same person held in Peer Benchmarking. Both are kept, because a person
    # may be an administrator of one application and only a reader of the other.
    role_bench = Column(String(20), nullable=False, default="viewer")

    relevance = Column(Integer, nullable=False)
    accuracy = Column(Integer, nullable=False)
    usefulness = Column(Integer, nullable=False)
    clarity = Column(Integer, nullable=False)
    timeliness = Column(Integer, nullable=False)

    comments = Column(Text)

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
