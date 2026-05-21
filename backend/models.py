# -*- coding: utf-8 -*-
"""SQLAlchemy database models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class PipeSegment(Base):
    __tablename__ = "pipe_segments"
    __table_args__ = (UniqueConstraint("pipe_code", name="uq_pipe_segments_pipe_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pipe_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    diameter_mm: Mapped[float] = mapped_column(Float, nullable=False)
    region_type: Mapped[str] = mapped_column(String(40), nullable=False, default="normal")
    soil_type: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    reports: Mapped[list["InspectionReport"]] = relationship(
        back_populates="pipe",
        cascade="all, delete-orphan",
    )


class InspectionReport(Base):
    __tablename__ = "inspection_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pipe_id: Mapped[int] = mapped_column(ForeignKey("pipe_segments.id"), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evaluation: Mapped[dict] = mapped_column(JSONB, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    report_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    pipe: Mapped[PipeSegment] = relationship(back_populates="reports")
