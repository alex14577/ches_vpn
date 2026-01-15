from __future__ import annotations

import asyncio
import json
import uuid

from common.db import db_call
from common.logger import Logger
from common.models import User
from common.xui_client.registry import Manager


class AccessSyncService:
    def __init__(self, manager: Manager, *, interval_seconds: int) -> None:
        self._manager = manager
        self._interval_seconds = max(10, int(interval_seconds))

    async def run_once(self) -> None:
        active_users: list[User] = await db_call(lambda db: db.users.active_subscription_users())
        active_ids = {u.id for u in active_users}

        await self._manager.sync_servers_now()

        if active_users:
            results = await asyncio.gather(
                *(self._manager.sync_user(u) for u in active_users),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    Logger.warning("sync_user partial failure: %s", r)

        server_ids = await self._manager.list_user_ids()
        stale_ids = server_ids - active_ids

        if not stale_ids:
            Logger.info("Access sync: %d active user(s), nothing to remove", len(active_ids))
            return

        stale_users = await db_call(lambda db: db.users.by_ids(stale_ids))
        stale_map = {u.id: u for u in stale_users}

        tasks = []
        for user_id in stale_ids:
            user = stale_map.get(user_id)
            if user:
                display_name = user.username or str(user.tg_user_id)
            else:
                display_name = str(user_id)
            tasks.append(self._manager.del_user_id(user_id, display_name=display_name))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                Logger.warning("del_user_id partial failure: %s", r)

        Logger.info(
            "Access sync: %d active user(s), %d removed",
            len(active_ids),
            len(stale_ids),
        )

    async def handle_notification(self, payload: str | None) -> None:
        if not payload:
            return
        try:
            data = json.loads(payload)
            user_id = uuid.UUID(str(data.get("user_id")))
        except Exception:
            Logger.warning("Access sync: invalid payload %r", payload)
            return

        await self._sync_user_id(user_id)

    async def _sync_user_id(self, user_id: uuid.UUID) -> None:
        has_active = await db_call(lambda db: db.subscriptions.has_active(user_id))
        user = await db_call(lambda db: db.users.get(user_id))

        if has_active and user is not None:
            await self._manager.sync_user(user)
            return

        pending_free_trial = await db_call(
            lambda db: db.subscriptions.pending_free_or_trial_for_user(user_id)
        )
        if pending_free_trial:
            if user is not None:
                Logger.info("Access sync: pending free/trial for user %s, syncing", user_id)
                await self._manager.sync_user(user)
            else:
                Logger.info("Access sync: pending free/trial for user %s, user not found", user_id)
            return

        if user is not None:
            display_name = user.username or str(user.tg_user_id)
        else:
            display_name = str(user_id)
        await self._manager.del_user_id(user_id, display_name=display_name)
