import asyncio
import os
import signal

from common.db import init_db_engine
from common.logger import Level, Logger
from pay_verifier.config import load_config
from pay_verifier.matchers import VkSbpMatcher
from pay_verifier.service import PaymentPollingService
from pay_verifier.sources import VkMessageSource


def main() -> None:
    Logger.configure("pay-verifier", level=Level.INFO)
    Logger.silence("vk_api", "urllib3", level=Level.WARNING)

    init_db_engine(
        os.environ["VPN_PAY_VERIFIER_DB_USERNAME"],
        os.environ["VPN_PAY_VERIFIER_DB_PASSWORD"],
    )

    cfg = load_config()
    source = VkMessageSource(
        token=cfg.vk_token,
        peer_id=cfg.vk_peer_id,
        incoming_only=cfg.vk_incoming_only,
        max_messages=cfg.vk_max_messages,
    )
    service = PaymentPollingService(
        sources=[source],
        matchers=[VkSbpMatcher()],
        poll_interval_seconds=cfg.poll_interval_seconds,
        vk_lookback_minutes=cfg.vk_lookback_minutes,
        pending_lookback_days=cfg.pending_lookback_days,
    )

    async def _run() -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await service.run_forever(stop_event)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
