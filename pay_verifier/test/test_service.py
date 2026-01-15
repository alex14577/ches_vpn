import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from common.logger import Logger, Level
from pay_verifier.matchers import VkSbpMatcher
from pay_verifier.service import PaymentPollingService
from pay_verifier.types import RawMessage


class FakeSource:
    def __init__(self, messages):
        self._messages = messages

    async def fetch_messages(self, *, since):
        return self._messages


class PaymentPollingServiceTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Logger.configure("pay-verifier-test", level=Level.WARNING)

    async def test_run_once_matches_and_updates(self) -> None:
        pending = [
            SimpleNamespace(id="sub-1", expected_amount_minor=130043),
        ]

        msg = RawMessage(
            source="vk",
            text="Поступление 1300.43 RUR по СБП от АЛЕКСЕЙ Т.",
            received_at=datetime.now(timezone.utc),
            meta={"id": 10, "from_id": 123},
        )

        updated_ids = []
        recorded = []

        class TestService(PaymentPollingService):
            async def _load_pending(self):
                return pending

            async def _record_event(self, match):
                recorded.append(match)

            async def _activate_subscription(self, sub_id):
                updated_ids.append(sub_id)
                return True

        service = TestService(
            sources=[FakeSource([msg])],
            matchers=[VkSbpMatcher()],
            poll_interval_seconds=1,
            vk_lookback_minutes=60,
            pending_lookback_days=7,
        )

        await service.run_once()

        self.assertEqual(updated_ids, ["sub-1"])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].amount_minor, 130043)

    async def test_run_once_skips_when_no_pending(self) -> None:
        msg = RawMessage(
            source="vk",
            text="Поступление 1300.43 RUR по СБП",
            received_at=datetime.now(timezone.utc),
            meta={"id": 11},
        )

        updated_ids = []

        class TestService(PaymentPollingService):
            async def _load_pending(self):
                return []

            async def _activate_subscription(self, sub_id):
                updated_ids.append(sub_id)
                return True

        service = TestService(
            sources=[FakeSource([msg])],
            matchers=[VkSbpMatcher()],
            poll_interval_seconds=1,
            vk_lookback_minutes=60,
            pending_lookback_days=7,
        )

        await service.run_once()
        self.assertEqual(updated_ids, [])


if __name__ == "__main__":
    unittest.main()
