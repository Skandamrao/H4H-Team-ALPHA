"""SQLAlchemy database engine and session factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# SQLite needs `check_same_thread=False` for multi-threaded FastAPI usage.
connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=settings.app_debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def get_db():
    """FastAPI dependency — yields a database session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

