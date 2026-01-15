from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RawMessage:
    source: str
    text: str
    received_at: datetime
    meta: dict[str, Any]


@dataclass(frozen=True)
class PaymentMatch:
    source: str
    amount_minor: int
    received_at: datetime
    raw: RawMessage
