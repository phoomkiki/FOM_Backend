"""Optional direct-PostgreSQL session support for maintenance/migrations.

The runtime API uses Supabase Data API and does not need DATABASE_URL.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine = None
_SessionLocal = None

if settings.database_url:
    _engine = create_engine(settings.database_url, pool_pre_ping=True)
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        raise RuntimeError(
            "Direct PostgreSQL sessions are disabled. Configure DATABASE_URL "
            "only if a feature explicitly requires SQLAlchemy; the API should "
            "use Supabase Data API."
        )

    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
