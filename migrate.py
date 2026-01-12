import asyncio
import os
from sqlmodel import SQLModel

from common.db import engine, init_db_engine
from common.models import User  # важно: импортировать модели, чтобы они зарегистрировались


async def main() -> None:
    init_db_engine(
        os.environ["VPN_SUBSCRIPTION_DB_USERNAME"],
        os.environ["VPN_SUBSCRIPTION_DB_PASSWORD"],
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(main())
