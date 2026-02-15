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
            SimpleNamespace(id="sub-1", expected_amount_minor=130043, user_id="user-1"),
        ]

        msg = RawMessage(
            source="vk",
            text="Поступление 1300.43 RUR по СБП от АЛЕКСЕЙ Т.",
            received_at=datetime.now(timezone.utc),
            meta={"id": 10, "from_id": 123},
        )

        updated_ids = []
        expired_calls = []

        class TestService(PaymentPollingService):
            async def _expire_active(self):
                expired_calls.append(True)
                return 0

            async def _activate_free_and_trial(self):
                return 0

            async def _mark_overdue_pending(self):
                return 0

            async def _load_pending(self):
                return pending

            async def _record_and_activate(self, match, sub_id):
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

        self.assertEqual(len(expired_calls), 1)
        self.assertEqual(updated_ids, ["sub-1"])

    async def test_run_once_skips_when_no_pending(self) -> None:
        msg = RawMessage(
            source="vk",
            text="Поступление 1300.43 RUR по СБП",
            received_at=datetime.now(timezone.utc),
            meta={"id": 11},
        )

        updated_ids = []
        expired_calls = []

        class TestService(PaymentPollingService):
            async def _expire_active(self):
                expired_calls.append(True)
                return 0

            async def _activate_free_and_trial(self):
                return 0

            async def _mark_overdue_pending(self):
                return 0

            async def _load_pending(self):
                return []

            async def _record_and_activate(self, match, sub_id):
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
        self.assertEqual(len(expired_calls), 1)
        self.assertEqual(updated_ids, [])


if __name__ == "__main__":
    unittest.main()
