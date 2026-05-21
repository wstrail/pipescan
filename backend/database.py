# -*- coding: utf-8 -*-
"""Database connection helpers for PostgreSQL."""

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv(Path(__file__).parent / ".env")


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://pipescan:pipescan@localhost:5432/pipescan",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> tuple[bool, str]:
    """Create tables when PostgreSQL is reachable."""

    try:
        from models import PipeSegment, InspectionReport  # noqa: F401

        Base.metadata.create_all(bind=engine)
        return True, "database ready"
    except SQLAlchemyError as exc:
        return False, str(exc)


def ping_db() -> tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return True, "database connected"
    except SQLAlchemyError as exc:
        return False, str(exc)
