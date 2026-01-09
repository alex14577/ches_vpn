from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import asyncio
import uuid
import json
from urllib.parse import quote, urlparse
from typing import Optional, Iterable

from common.db import db_call
from common.xui_client.xui_client import XuiClient, XuiConfig
from common.logger import Logger
from common.models import VpnServer, User


# ----------------------------
# DTO / utils
# ----------------------------

@dataclass(slots=True, frozen=True)
class VpnServerDTO:
    id: uuid.UUID
    code: str
    api_base_url: str
    api_username: str
    api_password: str


def to_dto(s: VpnServer) -> VpnServerDTO:
    return VpnServerDTO(
        id=s.id,
        code=s.code,
        api_base_url=s.api_base_url,
        api_username=s.api_username,
        api_password=s.api_password,
    )


def _json_loads(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _first_str(x, default: str = "") -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list) and x and isinstance(x[0], str):
        return x[0]
    return default


def _encode_path(p: str) -> str:
    if not p:
        p = "/"
    return quote(p, safe="")


def _server_host_from_api_base(api_base_url: str) -> str:
    try:
        return urlparse(api_base_url).hostname or ""
    except Exception:
        return ""


def _build_vless_reality_link(
    *,
    user_id: str,
    email: str,
    server_host: str,
    port: int,
    stream_settings_raw: str,
) -> str | None:
    s = _json_loads(stream_settings_raw)

    type_ = (s.get("network") or "tcp")
    security = s.get("security") or ""
    if security != "reality":
        return None

    reality = s.get("realitySettings") or {}
    rset = (reality.get("settings") or {})
    pbk = rset.get("publicKey") or ""
    fp = rset.get("fingerprint") or "chrome"
    spx = rset.get("spiderX") or "/"

    sni = _first_str(reality.get("serverNames"), "")
    sid = _first_str(reality.get("shortIds"), "")

    xhttp = s.get("xhttpSettings") or {}
    path = xhttp.get("path") or "/"
    host = xhttp.get("host") or ""
    mode = xhttp.get("mode") or "auto"

    path_enc = _encode_path(path)
    host_enc = quote(host, safe="")
    spx_enc = _encode_path(spx)
    frag = quote(email or "", safe="")

    flow = ""
    if type_ == "tcp":
        flow = f"&flow={quote('xtls-rprx-vision', safe='')}"

    return (
        f"vless://{user_id}@{server_host}:{port}"
        f"?type={quote(str(type_), safe='')}"
        f"&encryption=none"
        f"&path={path_enc}"
        f"&host={host_enc}"
        f"{flow}"
        f"&mode={quote(str(mode), safe='')}"
        f"&security=reality"
        f"&pbk={quote(str(pbk), safe='')}"
        f"&fp={quote(str(fp), safe='')}"
        f"&sni={quote(str(sni), safe='')}"
        f"&sid={quote(str(sid), safe='')}"
        f"&spx={spx_enc}"
        f"#{frag}"
    )


# ----------------------------
# Manager
# ----------------------------

@dataclass(slots=True)
class ManagedClient:
    server: VpnServerDTO
    client: XuiClient


class Manager:
    SYNC_PERIOD = timedelta(hours=1)

    def __init__(self) -> None:
        self._clients: dict[uuid.UUID, ManagedClient] = {}
        self._last_sync: datetime | None = None
        self._sync_lock = asyncio.Lock()
        self._io_sem = asyncio.Semaphore(5)  # общий лимит параллельности

    # ---- sync helpers ----

    def _need_sync(self) -> bool:
        if self._last_sync is None:
            return True
        return datetime.now(timezone.utc) >= (self._last_sync + self.SYNC_PERIOD)

    def _mark_synced(self) -> None:
        self._last_sync = datetime.now(timezone.utc)

    @staticmethod
    def _fingerprint(s: VpnServerDTO) -> tuple[str, str, str]:
        return (s.api_base_url, s.api_username, s.api_password)

    @staticmethod
    def _make_client(s: VpnServerDTO) -> XuiClient:
        return XuiClient(
            cfg=XuiConfig(api_base_url=s.api_base_url),
            username=s.api_username,
            password=s.api_password,
        )

    async def _sync_from_db(self, servers: list[VpnServer]) -> None:
        desired: dict[uuid.UUID, VpnServerDTO] = {s.id: to_dto(s) for s in servers}

        current_ids = set(self._clients.keys())
        desired_ids = set(desired.keys())

        # REMOVE: в БД больше нет -> закрыть и убрать
        for server_id in (current_ids - desired_ids):
            entry = self._clients.pop(server_id)
            try:
                await entry.client.aclose()
            except Exception as e:
                Logger.warning("Failed to close XuiClient for %s: %s", server_id, e)

        # ADD/UPDATE
        for server_id, dto in desired.items():
            entry = self._clients.get(server_id)

            if entry is None:
                self._clients[server_id] = ManagedClient(server=dto, client=self._make_client(dto))
                continue

            if self._fingerprint(entry.server) != self._fingerprint(dto):
                try:
                    await entry.client.aclose()
                except Exception as e:
                    Logger.warning("Failed to close old XuiClient for %s: %s", server_id, e)
                entry.client = self._make_client(dto)

            entry.server = dto

    async def _ensure_synced(self) -> None:
        if not self._need_sync():
            return

        async with self._sync_lock:
            # double-check внутри лока, чтобы не синкаться параллельно
            if not self._need_sync():
                return

            servers = await db_call(lambda db: db.servers.all())
            await self._sync_from_db(servers)
            self._mark_synced()

    async def sync_servers_now(self) -> None:
        """Принудительная синхронизация (не по таймеру)."""
        async with self._sync_lock:
            servers = await db_call(lambda db: db.servers.all())
            await self._sync_from_db(servers)
            self._mark_synced()

    def _get_managed(self, server_id: uuid.UUID) -> ManagedClient:
        mc = self._clients.get(server_id)
        if mc is None:
            raise KeyError(f"Server {server_id} not found")
        return mc

    # ---- public API ----

    async def sync_server(self, user: User, server_id: uuid.UUID) -> None:
        await self._ensure_synced()

        user_id = str(user.id)
        display_name = user.username or str(user.tg_user_id)

        mc = self._get_managed(server_id)
        client = mc.client

        async with self._io_sem:
            inbounds = await client.inbounds()

            missing = [ib for ib in inbounds if not any(c.id == user_id for c in ib.settings.clients)]

            if not missing:
                Logger.debug('User "%s" already present on server "%s"', display_name, client.cfg.api_base_url)
                return

            for inbound in missing:
                email = f"{display_name}-{inbound.id}"
                await client.addClient(inbound.id, user_id, email)

            Logger.info('User "%s" synced on server "%s" (%d inbound(s) updated)',
                        display_name, client.cfg.api_base_url, len(missing))

    async def sync_user(self, user: User) -> None:
        """Добавить пользователя на все сервера."""
        await self._ensure_synced()

        tasks = [
            self.sync_server(user, server_id)
            for server_id in self._clients.keys()
        ]
        # если один сервер упал — остальные продолжают
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                Logger.warning("sync_user partial failure: %s", r)

    async def del_user(self, user: User) -> None:
        """Удалить пользователя со всех серверов."""
        await self._ensure_synced()

        user_id = str(user.id)
        display_name = user.username or str(user.tg_user_id)

        async def del_one(mc: ManagedClient) -> None:
            async with self._io_sem:
                client = mc.client
                inbounds = await client.inbounds()

                for inbound in inbounds:
                    if any(c.id == user_id for c in inbound.settings.clients):
                        await client.delClient(inbound.id, user_id)

                Logger.info('User "%s" removed from server "%s"', display_name, client.cfg.api_base_url)

        results = await asyncio.gather(*(del_one(mc) for mc in self._clients.values()), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                Logger.warning("del_user partial failure: %s", r)

    @staticmethod
    def _client_total_bytes(cs) -> int:
        total = int(getattr(cs, "up", 0)) + int(getattr(cs, "down", 0))
        if total <= 0:
            total = int(getattr(cs, "allTime", 0))
        return max(0, total)

    async def collect_user_totals(self) -> dict[uuid.UUID, int]:
        """Собрать суммарный трафик (up+down) по пользователям со всех серверов."""
        await self._ensure_synced()

        async def collect_one(mc: ManagedClient):
            async with self._io_sem:
                return await mc.client.inbounds()

        results = await asyncio.gather(*(collect_one(mc) for mc in self._clients.values()), return_exceptions=True)

        totals: dict[uuid.UUID, int] = {}
        for r in results:
            if isinstance(r, Exception):
                Logger.warning("collect_user_totals partial failure: %s", r)
                continue
            for inbound in r:
                for cs in inbound.clientStats:
                    try:
                        user_id = uuid.UUID(str(cs.uuid))
                    except Exception:
                        continue
                    total_bytes = self._client_total_bytes(cs)
                    if total_bytes <= 0:
                        continue
                    totals[user_id] = totals.get(user_id, 0) + total_bytes

        return totals

    async def collect_configs(self, user_id: str) -> list[str]:
        """Собрать конфиги (ссылки) по всем серверам для конкретного user_id."""
        await self._ensure_synced()

        async def collect_one(mc: ManagedClient) -> list[str]:
            async with self._io_sem:
                client = mc.client
                cfg = client.cfg

                server_host = getattr(cfg, "publicHost", None) or _server_host_from_api_base(cfg.api_base_url) or "localhost"
                inbounds = await client.inbounds()

                out: list[str] = []
                for inbound in inbounds:
                    email: Optional[str] = None
                    for c in inbound.settings.clients:
                        if str(c.id) == str(user_id):
                            email = c.email
                            break
                    if email is None:
                        continue

                    stream_raw = getattr(inbound, "streamSettingsRaw", None) or getattr(inbound, "streamSettings", "")
                    link = _build_vless_reality_link(
                        user_id=user_id,
                        email=email,
                        server_host=server_host,
                        port=int(getattr(inbound, "port", 0)),
                        stream_settings_raw=stream_raw,
                    )
                    if link:
                        out.append(link)

                return out

        parts = await asyncio.gather(*(collect_one(mc) for mc in self._clients.values()), return_exceptions=True)

        result: list[str] = []
        for p in parts:
            if isinstance(p, Exception):
                Logger.warning("collect_configs partial failure: %s", p)
                continue
            result.extend(p)

        return result
