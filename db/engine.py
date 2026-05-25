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
    # Configure pool size via env variables to prevent EMAXCONNSESSION on Supabase (max 15)
    # Defaulting to 3+2=5 sync and 2+1=3 async connections is safe for multi-process (Web + Celery) setups.
    db_pool_size = int(os.environ.get("DB_POOL_SIZE", 3))
    db_max_overflow = int(os.environ.get("DB_MAX_OVERFLOW", 2))
    
    _connect_args = {
        "sslmode": "require",
        "connect_timeout": 15,
        "options": "-c statement_timeout=30000",  # 30 s hard kill for runaway queries
    }
    engine = create_engine(
        DATABASE_URL,
        connect_args=_connect_args,
        pool_pre_ping=True,
        pool_recycle=300,      # recycle stale connections every 5 min (was 10 min)
        pool_size=db_pool_size,
        max_overflow=db_max_overflow,
        pool_timeout=20,       # wait max 20 s for a free connection before raising
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_REPLICA_URL = os.environ.get("DATABASE_REPLICA_URL") or DATABASE_URL

if not _is_sqlite:
    _async_url = _REPLICA_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_pool_size = int(os.environ.get("DB_ASYNC_POOL_SIZE", 2))
    async_max_overflow = int(os.environ.get("DB_ASYNC_MAX_OVERFLOW", 1))
    
    async_engine = create_async_engine(
        _async_url,
        connect_args={"ssl": "require"},
        pool_pre_ping=True,
        pool_recycle=300,  # was 600
        pool_size=async_pool_size,
        max_overflow=async_max_overflow,
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
