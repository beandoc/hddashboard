import os
from dotenv import load_dotenv
load_dotenv()

from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


Base = declarative_base()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hd_dashboard.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    _connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=_connect_args)
else:
    _connect_args = {
        "sslmode": "require",
        "connect_timeout": 30,
    }
    engine = create_engine(
        DATABASE_URL,
        connect_args=_connect_args,
        pool_pre_ping=False,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_REPLICA_URL = os.environ.get("DATABASE_REPLICA_URL") or DATABASE_URL

if not _is_sqlite:
    _async_url = _REPLICA_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(
        _async_url,
        connect_args={"ssl": "require"},
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )
else:
    async_engine = None  # type: ignore[assignment]

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
) if async_engine is not None else None  # type: ignore[assignment]


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async DB sessions (analytics / API routes)."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Async engine is not configured (SQLite dev mode).")
    async with AsyncSessionLocal() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Inject the tenant_id into the PostgreSQL session so RLS policies evaluate correctly.

    Must be called at the start of every async request that touches clinical tables.
    The SET LOCAL is transaction-scoped and resets automatically on commit/rollback.
    """
    from sqlalchemy import text as _text
    await session.execute(_text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))  # noqa: S608


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
