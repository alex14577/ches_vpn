import asyncio
import os
import signal
import psycopg

from common.db import init_db_engine
from common.logger import Level, Logger
from common.xui_client.registry import Manager
from access_sync.config import load_config
from access_sync.service import AccessSyncService


def main() -> None:
    Logger.configure("access-sync", level=Level.INFO)

    init_db_engine(
        os.environ["VPN_SUBSCRIPTION_DB_USERNAME"],
        os.environ["VPN_SUBSCRIPTION_DB_PASSWORD"],
    )

    cfg = load_config()
    service = AccessSyncService(Manager(), interval_seconds=cfg.interval_seconds)

    async def _listen_loop(stop_event: asyncio.Event, retry_delay: int) -> None:
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = os.environ.get("DB_PORT", "5432")
        db_name = os.environ.get("DB_NAME", "app")
        db_user = os.environ["VPN_SUBSCRIPTION_DB_USERNAME"]
        db_password = os.environ["VPN_SUBSCRIPTION_DB_PASSWORD"]
        dsn = f"dbname={db_name} user={db_user} password={db_password} host={db_host} port={db_port}"

        while not stop_event.is_set():
            try:
                async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
                    await conn.execute("LISTEN subscriptions_changed")
                    Logger.info("Access sync: listening for subscription changes")

                    notify_iter = conn.notifies()
                    while not stop_event.is_set():
                        notify_task = asyncio.create_task(anext(notify_iter))
                        stop_task = asyncio.create_task(stop_event.wait())
                        done, pending = await asyncio.wait(
                            {notify_task, stop_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()

                        if stop_task in done:
                            break

                        notify = notify_task.result()
                        await service.handle_notification(getattr(notify, "payload", None))
            except Exception:
                Logger.exception("Access sync listen failed")
                await asyncio.sleep(retry_delay)

    async def _periodic_loop(stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await service.run_once()
            except Exception:
                Logger.exception("Access sync periodic run failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=max(1, int(cfg.interval_seconds)))
            except asyncio.TimeoutError:
                pass

    async def _run() -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        await service.run_once()
        periodic_task = asyncio.create_task(_periodic_loop(stop_event))
        try:
            await _listen_loop(stop_event, max(1, int(cfg.interval_seconds)))
        finally:
            periodic_task.cancel()
            try:
                await periodic_task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())


if __name__ == "__main__":
    main()
