"""SQLAlchemy engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

# Sync engine — compatible with Celery workers and FastAPI (run in threadpool for heavy routes if needed)
connect_args = {}
url = str(settings.DATABASE_URL)
if url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
