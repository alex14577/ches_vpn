import os
from contextlib import asynccontextmanager

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from typing import Any, Awaitable, Callable

from common.adapters import DbAdapters

# пример:
# postgresql+psycopg://localhost:5432/app
# или
# postgresql+asyncpg://localhost:5432/app
DB_DRIVER = os.environ.get("DB_DRIVER") or "postgresql+psycopg"
DB_HOST = os.environ.get("DB_HOST") or "localhost"
DB_PORT = os.environ.get("DB_PORT") or "5432"
DB_NAME = os.environ.get("DB_NAME") or "app"
DB_URL = f"{DB_DRIVER}://{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine: AsyncEngine | None = None

def create_engine_with_credentials(username: str, password: str):
    url = make_url(DB_URL).set(username=username, password=password)
    return create_async_engine(
        url,
        pool_pre_ping=True,
    )

def init_db_engine(username: str, password: str) -> AsyncEngine:
    global engine
    engine = create_engine_with_credentials(username, password)
    SessionLocal.configure(bind=engine)
    return engine

SessionLocal = async_sessionmaker(
    class_=AsyncSession,
    expire_on_commit=False,
)

@asynccontextmanager
async def get_session():
    if engine is None:
        raise RuntimeError("DB engine is not initialized. Call init_db_engine().")
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def db_ctx():
    async with get_session() as s:
        db = DbAdapters(s)
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

async def db_call(fn: Callable[[DbAdapters], Awaitable[Any]]) -> Any:
    async with db_ctx() as db:
        return await fn(db)
