from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Optional, Protocol

from pay_verifier.types import PaymentMatch, RawMessage


class PaymentMatcher(Protocol):
    def match(self, msg: RawMessage) -> Optional[PaymentMatch]:
        ...


@dataclass(frozen=True)
class VkSbpMatcher:
    _re_sbp: re.Pattern[str] = re.compile(
        r"Поступление\s+([\d\s]+[.,]\d{2})\s*RUR\s+по\s+СБП",
        re.IGNORECASE,
    )
    _re_card: re.Pattern[str] = re.compile(
        r"Деньги\s+пришли!\s*([\d\s]+[.,]\d{2})\s*₽",
        re.IGNORECASE,
    )

    def match(self, msg: RawMessage) -> Optional[PaymentMatch]:
        if msg.source != "vk":
            return None

        m = self._re_sbp.search(msg.text) or self._re_card.search(msg.text)
        if not m:
            return None

        amount_str = m.group(1).replace(" ", "").replace(",", ".")
        try:
            amount = Decimal(amount_str)
        except InvalidOperation:
            return None

        amount_minor = int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return PaymentMatch(
            source=msg.source,
            amount_minor=amount_minor,
            received_at=msg.received_at,
            raw=msg,
        )
