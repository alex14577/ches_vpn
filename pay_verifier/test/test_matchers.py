import unittest
from datetime import datetime, timezone

from pay_verifier.matchers import VkSbpMatcher
from pay_verifier.types import RawMessage


class VkSbpMatcherTest(unittest.TestCase):
    def test_matches_amount(self) -> None:
        msg = RawMessage(
            source="vk",
            text="Поступление 1300.43 RUR по СБП от АЛЕКСЕЙ Т.",
            received_at=datetime.now(timezone.utc),
            meta={"id": 1},
        )
        match = VkSbpMatcher().match(msg)
        self.assertIsNotNone(match)
        self.assertEqual(match.amount_minor, 130043)

    def test_ignores_other_sources(self) -> None:
        msg = RawMessage(
            source="sms",
            text="Поступление 1300.43 RUR по СБП",
            received_at=datetime.now(timezone.utc),
            meta={},
        )
        match = VkSbpMatcher().match(msg)
        self.assertIsNone(match)


if __name__ == "__main__":
    unittest.main()
