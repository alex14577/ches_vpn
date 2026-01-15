from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Iterable, Protocol

import vk_api

from pay_verifier.types import RawMessage


class MessageSource(Protocol):
    async def fetch_messages(self, *, since: datetime) -> Iterable[RawMessage]:
        ...


class VkMessageSource:
    def __init__(
        self,
        *,
        token: str,
        peer_id: int,
        incoming_only: bool = True,
        max_messages: int = 500,
    ) -> None:
        self._peer_id = peer_id
        self._incoming_only = incoming_only
        self._max_messages = max_messages
        self._vk = vk_api.VkApi(token=token).get_api()

    def _fetch_sync(self, *, since: datetime) -> list[RawMessage]:
        since_ts = int(since.timestamp())
        offset = 0
        count = 200
        messages: list[RawMessage] = []

        while offset < self._max_messages:
            batch_count = min(count, self._max_messages - offset)
            response = self._vk.messages.getHistory(
                peer_id=self._peer_id,
                offset=offset,
                count=batch_count,
            )

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                msg_ts = item.get("date", 0)
                if msg_ts < since_ts:
                    continue
                if self._incoming_only and item.get("from_id") != self._peer_id:
                    continue
                text = item.get("text", "") or ""
                messages.append(
                    RawMessage(
                        source="vk",
                        text=text,
                        received_at=datetime.fromtimestamp(msg_ts, tz=timezone.utc),
                        meta={
                            "id": item.get("id"),
                            "from_id": item.get("from_id"),
                        },
                    )
                )

            if items[-1].get("date", 0) < since_ts:
                break

            offset += batch_count

        messages.sort(key=lambda m: m.received_at)
        return messages

    async def fetch_messages(self, *, since: datetime) -> list[RawMessage]:
        return await asyncio.to_thread(self._fetch_sync, since=since)
