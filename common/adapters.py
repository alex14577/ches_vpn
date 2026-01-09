from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
from typing import Optional
import uuid

from sqlalchemy import BigInteger, Column, DateTime, String
from sqlalchemy import select, update as sa_update, delete, cast, or_, and_, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import (
    DailyUsageStat,
    Plan,
    Subscription,
    User,
    UserTrafficSnapshot,
    VpnServer,
)


class UsersAdapter:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def all(self) -> list[User]:
        res = await self.s.execute(select(User))
        return list(res.scalars().all())

    async def byTgId(self, tg_user_id: int) -> Optional[User]:
        res = await self.s.execute(select(User).where(User.tg_user_id == tg_user_id))
        return res.scalar_one_or_none()
    
    async def byToken(self, token: str) -> Optional[User]:
        res = await self.s.execute(select(User).where(User.subscription_token == token))
        return res.scalar_one_or_none()    
        
    async def get(self, user_id: uuid.UUID) -> Optional[User]:
        res = await self.s.execute(select(User).where(User.id == user_id))
        return res.scalar_one_or_none()        

    async def getOrCreate(self, tg_user_id: int, username: Optional[str] = None, refer_id: Optional[str] = None) -> User:
        u = await self.byTgId(tg_user_id)
        if u:
            return u

        u = User(tg_user_id=tg_user_id, username=username, refer_id=refer_id)
        self.s.add(u)
        await self.s.flush()
        return u
    
    async def update(self, user: User):        
        stmt = (
            sa_update(User)
            .where(User == user)
            .values(username=user.username, refer_id=user.refer_id)
        )
        await self.s.execute(stmt)
        self.s.flush()

    async def delete(self, user_id: uuid.UUID) -> bool:
        user = await self.get(user_id)
        if user is None:
            return False
        await self.s.delete(user)
        return True
    
    async def active_subscription_users(self) -> list[User]:
        now = datetime.now(timezone.utc)

        stmt = (
            select(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.status == "active",
                Subscription.valid_from <= now,
                or_(Subscription.valid_until.is_(None), Subscription.valid_until >= now),
            )
            .distinct()
            .order_by(User.created_at.desc())
        )

        res = await self.s.execute(stmt)
        return list(res.scalars().all())
    
    async def list_with_source_stats(
        self,
        q: Optional[str] = None,
    ) -> tuple[list[User], list[dict[str, object]]]:
        """
        Возвращает:
          - users: список пользователей (с учётом поиска q), отсортированный по created_at desc
          - source_stats: агрегат по source для ВСЕХ пользователей (глобально), вида:
              [{"refer_id": "yndx", "count": 43}, {"refer_id": "—", "count": 8}, ...]
        """
        q = (q or "").strip()

        # -------- список пользователей --------
        stmt = select(User).order_by(User.created_at.desc())

        if q:
            conds = []
            if q.isdigit():
                conds.append(User.tg_user_id == int(q))

            like = f"%{q}%"
            conds.append(User.username.ilike(like))
            conds.append(User.refer_id.ilike(like))
            conds.append(cast(User.subscription_token, String).ilike(like))

            stmt = stmt.where(or_(*conds))

        res = await self.s.execute(stmt)
        users = list(res.scalars().all())

        # -------- статистика по source --------
        stats_stmt = (
            select(User.refer_id, func.count())
            .group_by(User.refer_id)
            .order_by(func.count().desc())
        )

        stats_res = await self.s.execute(stats_stmt)
        source_stats = [
            {"refer_id": (src or "—"), "count": cnt}
            for (src, cnt) in stats_res.all()
        ]

        return users, source_stats


class SubscriptionAdapter:
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"

    def __init__(self, session: AsyncSession):
        self.s = session

    @staticmethod
    def _calc_status(valid_from: datetime, valid_until: Optional[datetime]) -> str:
        now = datetime.now(timezone.utc)

        if valid_from > now:
            return "pending"

        if valid_until is None:
            return "active"

        return "active" if now <= valid_until else "expired"

    async def add(
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        valid_from: datetime,
        valid_until: Optional[datetime],
    ) -> Subscription:
        sub = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            valid_from=valid_from,
            valid_until=valid_until,
            status=self._calc_status(valid_from, valid_until),
        )
        self.s.add(sub)
        await self.s.flush()
        return sub

    async def get(self, userId, planId):
        res = await self.s.execute(
            select(Subscription).where(and_(Subscription.user_id == userId, Subscription.plan_id == planId))
        )
        return res.scalar_one_or_none()
    
    async def update(
            self,
            *,
            sub_id: uuid.UUID,
            valid_from: datetime,
            valid_until: Optional[datetime]
        ) -> bool:
            stmt = (
                sa_update(Subscription)
                .where(Subscription.id == sub_id)
                .values(
                    valid_from=valid_from,
                    valid_until=valid_until,
                    status=self._calc_status(valid_from, valid_until),
                )
            )

            res = await self.s.execute(stmt)
            await self.s.flush()

            return (res.rowcount or 0) > 0
        
    
    async def last_for_user(self, user_id):
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(
                Subscription.valid_until.desc().nullsfirst(),  # NULL (бессрочная) считаем “самой новой”
                Subscription.valid_from.desc(),
                Subscription.created_at.desc(),
            )
            .limit(1)
        )
        res = await self.s.execute(stmt)
        return res.scalar_one_or_none()

    async def add_by_plan_code(
        self,
        *,
        user_id: uuid.UUID,
        plan_code: str,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
    ) -> Subscription:
        """
        Добавляет подписку по коду плана.
        - Проверяет, что план существует и активен.
        - Если valid_from не передан -> now(UTC)
        - Если valid_until не передан:
            - если plan.duration_days задан -> valid_from + duration_days
            - если plan.duration_days None -> valid_until остаётся None (бессрочная)
        """
        plan_code = plan_code.strip()

        res = await self.s.execute(select(Plan).where(Plan.code == plan_code))
        plan = res.scalar_one_or_none()
        if plan is None:
            raise ValueError(f"Plan not found: {plan_code}")

        if not plan.is_active:
            raise ValueError(f"Plan is not active: {plan_code}")

        vf = valid_from or datetime.now(timezone.utc)

        vu = valid_until
        if vu is None and plan.duration_days is not None:
            # duration_days дней от valid_from
            vu = vf + timedelta(days=int(plan.duration_days))

        return await self.add(user_id=user_id, plan_id=plan.id, valid_from=vf, valid_until=vu)

    
class PlanAdapter:
    def __init__(self, session: AsyncSession):
        self.s = session
        
    async def getByCode(self, code: str) -> Plan:
        res = await self.s.execute(select(Plan).where(Plan.code == code))
        return res.scalar_one_or_none()
        
    async def active(self) -> list[Plan]:
        res = await self.s.execute(
            select(Plan).where(Plan.is_active == True).order_by(Plan.created_at.desc())
        )
        return list(res.scalars().all())

class VpnServerAdapter:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def all(self) -> list[VpnServer]:
        res = await self.s.execute(select(VpnServer))
        return list(res.scalars().all())

    async def get(self, server_id: uuid.UUID) -> VpnServer | None:
        res = await self.s.execute(select(VpnServer).where(VpnServer.id == server_id))
        return res.scalar_one_or_none()

    async def create(self, server: VpnServer) -> VpnServer:
        self.s.add(server)
        await self.s.flush()
        return server

    async def delete(self, server_id: uuid.UUID) -> None:
        server = await self.get(server_id)
        if server is None:
            return
        await self.s.delete(server)
        await self.s.flush()


class StatsAdapter:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def user_snapshot_map(self, day: date) -> dict[uuid.UUID, int]:
        stmt = select(UserTrafficSnapshot).where(UserTrafficSnapshot.day == day)
        res = await self.s.execute(stmt)
        return {row.user_id: row.total_bytes for row in res.scalars().all()}

    async def upsert_user_snapshots(self, day: date, totals: dict[uuid.UUID, int]) -> None:
        if not totals:
            return

        rows = [
            {"day": day, "user_id": user_id, "total_bytes": total_bytes}
            for user_id, total_bytes in totals.items()
        ]
        stmt = insert(UserTrafficSnapshot).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["day", "user_id"],
            set_={"total_bytes": stmt.excluded.total_bytes},
        )
        await self.s.execute(stmt)
        await self.s.flush()

    async def upsert_daily_usage(self, day: date, active_users: int, total_bytes: int) -> None:
        stmt = insert(DailyUsageStat).values(
            day=day,
            active_users=int(active_users),
            total_bytes=int(total_bytes),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["day"],
            set_={
                "active_users": int(active_users),
                "total_bytes": int(total_bytes),
            },
        )
        await self.s.execute(stmt)
        await self.s.flush()

    async def list_daily_usage(self, limit: int = 30) -> list[DailyUsageStat]:
        stmt = select(DailyUsageStat).order_by(DailyUsageStat.day.desc()).limit(limit)
        res = await self.s.execute(stmt)
        return list(res.scalars().all())

class DbAdapters:
    def __init__(self, session: AsyncSession):
        self.users = UsersAdapter(session)
        self.subscriptions = SubscriptionAdapter(session)
        self.plans = PlanAdapter(session)
        self.servers = VpnServerAdapter(session)
        self.stats = StatsAdapter(session)
        self._s = session

    async def commit(self) -> None:
        await self._s.commit()

    async def rollback(self) -> None:
        await self._s.rollback()

    async def close(self) -> None:
        await self._s.close()
