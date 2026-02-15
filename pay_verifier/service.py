from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select, update as sa_update, func, and_

from common.db import db_call
from common.logger import Logger
from common.models import PaymentEvent, Subscription, Plan
from pay_verifier.matchers import PaymentMatcher
from pay_verifier.sources import MessageSource
from pay_verifier.types import PaymentMatch, RawMessage


class PaymentPollingService:
    def __init__(
        self,
        *,
        sources: Iterable[MessageSource],
        matchers: Iterable[PaymentMatcher],
        poll_interval_seconds: int,
        vk_lookback_minutes: int,
        pending_lookback_days: int,
    ) -> None:
        self._sources = list(sources)
        self._matchers = list(matchers)
        self._poll_interval_seconds = poll_interval_seconds
        self._vk_lookback = timedelta(minutes=vk_lookback_minutes)
        self._pending_lookback = timedelta(days=pending_lookback_days)
        self._seen_ids: dict[int, datetime] = {}

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        while stop_event is None or not stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                Logger.exception("Pay verifier loop failed")
            if stop_event is None:
                await asyncio.sleep(self._poll_interval_seconds)
            else:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass

    async def run_once(self) -> None:
        expired = await self._expire_active()
        if expired:
            Logger.info("Expired active subscriptions: %d", expired)

        auto_activated = await self._activate_free_and_trial()
        if auto_activated:
            Logger.info("Auto-activated free/trial subscriptions: %d", auto_activated)

        overdue_marked = await self._mark_overdue_pending()
        if overdue_marked:
            Logger.info("Marked overdue pending subscriptions: %d", overdue_marked)

        pending = await self._load_pending()
        if not pending:
            return

        Logger.info("Pending subscriptions: %d", len(pending))
        pending_by_amount = self._index_pending(pending)
        if not pending_by_amount:
            return
        since = datetime.now(timezone.utc) - self._vk_lookback

        for source in self._sources:
            messages = await source.fetch_messages(since=since)
            Logger.info("Fetched %d messages from %s", len(messages), type(source).__name__)
            for msg in messages:
                if self._is_seen(msg):
                    continue
                match = self._match_message(msg)
                if not match:
                    continue
                sub = self._pick_subscription(pending_by_amount, match.amount_minor)
                if not sub:
                    Logger.info("No pending subscription for amount_minor=%s", match.amount_minor)
                    continue
                updated = await self._record_and_activate(match, sub.id)
                if updated:
                    Logger.info("Subscription activated: id=%s amount_minor=%s, user: %s", sub.id, match.amount_minor, sub.user_id)

    async def _load_pending(self) -> list[Subscription]:
        cutoff = datetime.now(timezone.utc) - self._pending_lookback

        async def work(db):
            stmt = (
                select(Subscription)
                .where(
                    Subscription.status == "pending_payment",
                    Subscription.created_at >= cutoff,
                )
                .order_by(Subscription.created_at.asc())
            )
            res = await db._s.execute(stmt)
            return list(res.scalars().all())

        return await db_call(work)

    @staticmethod
    def _index_pending(subs: list[Subscription]) -> dict[int, list[Subscription]]:
        by_amount: dict[int, list[Subscription]] = {}
        for sub in subs:
            if sub.expected_amount_minor is None:
                continue
            by_amount.setdefault(sub.expected_amount_minor, []).append(sub)
        return by_amount

    def _pick_subscription(
        self,
        by_amount: dict[int, list[Subscription]],
        amount_minor: int,
    ) -> Subscription | None:
        subs = by_amount.get(amount_minor)
        if not subs:
            return None
        return subs.pop(0)

    def _match_message(self, msg: RawMessage) -> PaymentMatch | None:
        for matcher in self._matchers:
            match = matcher.match(msg)
            if match is not None:
                return match
        return None

    async def _record_and_activate(self, match: PaymentMatch, sub_id) -> bool:
        payload = {
            "text": match.raw.text,
            **match.raw.meta,
        }
        msg_id = match.raw.meta.get("id")

        async def work(db):
            if isinstance(msg_id, (int, str)):
                dedupe_stmt = (
                    select(PaymentEvent.id)
                    .where(
                        and_(
                            PaymentEvent.source == match.source,
                            PaymentEvent.payload["id"].astext == str(msg_id),
                        )
                    )
                    .limit(1)
                )
                already_processed = (await db._s.execute(dedupe_stmt)).scalar_one_or_none()
                if already_processed is not None:
                    return False

            event = PaymentEvent(
                source=match.source,
                received_at=match.received_at,
                payload=payload,
                amount_minor=match.amount_minor,
            )
            db._s.add(event)
            await db._s.flush()
            stmt = (
                sa_update(Subscription)
                .where(
                    Subscription.id == sub_id,
                    Subscription.status == "pending_payment",
                )
                .values(status="active", matched_event_id=event.id, updated_at=func.now())
            )
            res = await db._s.execute(stmt)
            updated = (res.rowcount or 0) > 0
            if not updated:
                await db._s.delete(event)
                await db._s.flush()
                return False

            await db._s.flush()
            return True

        return await db_call(work)

    async def _expire_active(self) -> int:
        async def work(db):
            stmt = (
                sa_update(Subscription)
                .where(
                    Subscription.status == "active",
                    Subscription.valid_until.isnot(None),
                    Subscription.valid_until < func.now(),
                )
                .values(status="expired", notified_expired=False, updated_at=func.now())
                .execution_options(synchronize_session=False)
            )
            res = await db._s.execute(stmt)
            await db._s.flush()
            return int(res.rowcount or 0)

        return await db_call(work)

    async def _activate_free_and_trial(self) -> int:
        async def work(db):
            stmt = (
                sa_update(Subscription)
                .where(
                    Subscription.status == "pending_payment",
                    Subscription.plan_id == Plan.id,
                    Plan.code.in_(["free", "trial"]),
                )
                .values(status="active", updated_at=func.now())
                .execution_options(synchronize_session=False)
            )
            res = await db._s.execute(stmt)
            await db._s.flush()
            return int(res.rowcount or 0)

        return await db_call(work)

    async def _mark_overdue_pending(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

        async def work(db):
            stmt = (
                sa_update(Subscription)
                .where(
                    Subscription.status == "pending_payment",
                    Subscription.created_at < cutoff,
                    Subscription.plan_id == Plan.id,
                    ~Plan.code.in_(["free", "trial"]),
                )
                .values(status="payment_overdue", notified_overdue=False, updated_at=func.now())
                .execution_options(synchronize_session=False)
            )
            res = await db._s.execute(stmt)
            await db._s.flush()
            return int(res.rowcount or 0)

        return await db_call(work)

    def _is_seen(self, msg: RawMessage) -> bool:
        msg_id = msg.meta.get("id")
        if not isinstance(msg_id, int):
            return False

        now = datetime.now(timezone.utc)
        self._prune_seen(now)
        if msg_id in self._seen_ids:
            return True
        self._seen_ids[msg_id] = now
        return False

    def _prune_seen(self, now: datetime) -> None:
        cutoff = now - self._vk_lookback
        stale = [mid for mid, ts in self._seen_ids.items() if ts < cutoff]
        for mid in stale:
            del self._seen_ids[mid]
