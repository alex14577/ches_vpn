from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import User, Task, Subscription, Plan, VpnServer


@dataclass(frozen=True)
class TaskDTO:
    id: str
    user_id: str
    type: str
    status: str
    payload: dict
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


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

    async def getOrCreate(self, tg_user_id: int, username: Optional[str] = None, refer_id: Optional[str] = None) -> User:
        u = await self.byTgId(tg_user_id)
        if u:
            return u

        u = User(tg_user_id=tg_user_id, username=username, refer_id=refer_id)
        self.s.add(u)
        await self.s.flush()
        return u

class TasksAdapter:
    ACTIVE_STATUSES = ("pending", "running")
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    def __init__(self, session: AsyncSession):
        self.s = session

    @staticmethod
    def _to_uuid(task_id: uuid.UUID | str) -> uuid.UUID:
        return task_id if isinstance(task_id, uuid.UUID) else uuid.UUID(str(task_id))

    async def create_task(
        self,
        *,
        type_: str,
        payload: dict,
        idempotency_key: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> Task:
        """
        Создать задачу идемпотентно по idempotency_key.
        user_id теперь optional (nullable в таблице).
        """
        res = await self.s.execute(
            select(Task).where(Task.idempotency_key == idempotency_key)
        )
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        t = Task(
            user_id=user_id,
            type=type_,
            status=self.STATUS_PENDING,
            payload=payload,
            idempotency_key=idempotency_key,
            last_error=None,
        )
        self.s.add(t)
        await self.s.flush()
        return t

    async def get(self, task_id: uuid.UUID | str) -> Optional[Task]:
        tid = self._to_uuid(task_id)
        res = await self.s.execute(select(Task).where(Task.id == tid))
        return res.scalar_one_or_none()

    async def find_active_for_user(
        self, user_id: uuid.UUID, type_: Optional[str] = None
    ) -> list[Task]:
        stmt = select(Task).where(
            Task.user_id == user_id,
            Task.status.in_(self.ACTIVE_STATUSES),
        )
        if type_:
            stmt = stmt.where(Task.type == type_)
        stmt = stmt.order_by(Task.created_at.asc())

        res = await self.s.execute(stmt)
        return list(res.scalars().all())
    
    async def get_and_mark_running(self) -> Task | None:
        stmt = (
            update(Task)
            .where(Task.status == self.STATUS_PENDING)
            .values(
                status=self.STATUS_RUNNING,
                updated_at=func.now(),
            )
            .returning(Task)
        )

        res = await self.s.execute(stmt)
        task = res.scalar_one_or_none()

        return task

    async def mark_done(
        self, task_id: uuid.UUID | str, result_payload: Optional[dict] = None
    ) -> None:
        t = await self.get(task_id)
        if not t:
            return
        t.status = self.STATUS_DONE
        t.last_error = None
        if result_payload is not None:
            t.payload = dict(t.payload or {})
            t.payload["result"] = result_payload
        await self.s.flush()

    async def mark_failed(self, task_id: uuid.UUID | str, *, error: str) -> None:
        t = await self.get(task_id)
        if not t:
            return
        t.status = self.STATUS_FAILED
        t.last_error = error
        await self.s.flush()

class SubscriptionAdapter:
    ACTIVE = "active"
    EXPIRED = "expired"
    
    def __init__(self, session: AsyncSession):
        self.s = session
    
    async def add(self, userId, planId, validFrom, validUntil):
        sub = Subscription(user_id=userId, plan_id=planId, valid_from=validFrom, valid_until=validUntil)
        sub.status = self.EXPIRED
        now = datetime.now(timezone.utc)
        if validUntil == None or validFrom <= now and validUntil >= now:
            sub.status = self.ACTIVE
        self.s.add(sub)
        await self.s.flush()
        return sub
    
    async def get(self, userId, planId):
        sub = await self.s.execute(select(Subscription).where(Subscription.user_id == userId and Subscription.plan_id == planId))
        return sub.scalar_one_or_none()
    
class PlanAdapter:
    def __init__(self, session: AsyncSession):
        self.s = session
        
    async def getByCode(self, code: str) -> Plan:
        res = await self.s.execute(select(Plan).where(Plan.code == code))
        return res.scalar_one_or_none()
        
class VpnServerAdapter:
    def __init__(self, session: AsyncSession):
        self.s = session
        
    async def all(self) -> list[VpnServer]:
        res = await self.s.execute(select(VpnServer))
        return res.scalars().all()

class DbAdapters:
    def __init__(self, session: AsyncSession):
        self.users = UsersAdapter(session)
        self.tasks = TasksAdapter(session)
        self.subscriptions = SubscriptionAdapter(session)
        self.plans = PlanAdapter(session)
        self.servers = VpnServerAdapter(session)
        self._s = session

    async def commit(self) -> None:
        await self._s.commit()

    async def rollback(self) -> None:
        await self._s.rollback()

    async def close(self) -> None:
        await self._s.close()
