import asyncio
import os
import traceback
from sqlmodel import SQLModel

from common.db import init_db_engine
from common.models import User  # noqa: F401


async def main() -> None:
    user = os.getenv("VPN_SUBSCRIPTION_DB_USERNAME")
    pwd = os.getenv("VPN_SUBSCRIPTION_DB_PASSWORD")


    engine = init_db_engine(user, pwd)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("OK: таблицы созданы/проверены.")
    except Exception:
        traceback.print_exc()
