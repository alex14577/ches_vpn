import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel
from typing import Any, Awaitable, Callable

from common.adapters import DbAdapters

DB_URL = os.environ["DATABASE_URL"]
# пример:
# postgresql+psycopg://alex:1234@localhost:5432/app
# или
# postgresql+asyncpg://alex:1234@localhost:5432/app

engine = create_async_engine(
    DB_URL,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@asynccontextmanager
async def get_session():
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