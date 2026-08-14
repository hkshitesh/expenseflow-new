"""Database engine, session factory, and declarative base for ExpenseFlow."""

from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = "sqlite:///expenseflow.db"

engine: Engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for a single request and close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables registered on Base.metadata that do not yet exist."""
    Base.metadata.create_all(bind=engine)
