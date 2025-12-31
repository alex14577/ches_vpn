import asyncio
from sqlmodel import SQLModel

from common.db import engine
from common.models import User, Task  # важно: импортировать модели, чтобы они зарегистрировались


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(main())