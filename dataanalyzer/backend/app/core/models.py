"""The tables of the Data Analyzer."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Document(Base):
    """A document a person shared, and what was found in it."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    filename: Mapped[str] = mapped_column(String(256))
    sheet: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(120), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # The profile of the data, the summary and the insights, as they are found.
    profile: Mapped[str] = mapped_column(Text, default="{}")
    preview: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    insights: Mapped[str] = mapped_column(Text, default="[]")
    plots: Mapped[str] = mapped_column(Text, default="[]")
    summary_reason: Mapped[str] = mapped_column(String(256), default="")
