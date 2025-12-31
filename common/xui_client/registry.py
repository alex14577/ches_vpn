
from __future__ import annotations
from dataclasses import dataclass
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import json
from urllib.parse import quote, urlparse


from common.db import db_call
from common.xui_client.xui_client import XuiClient, XuiConfig
from common.logger import Logger

from common.models import VpnServer, User

@dataclass(slots=True, frozen=True)
class VpnServerDTO:
    id: uuid.UUID
    code: str
    api_base_url: str
    api_username: str
    api_password: str

def to_dto(s: "VpnServer") -> VpnServerDTO:
    return VpnServerDTO(
        id=s.id,
        code=s.code,
        api_base_url=s.api_base_url,
        api_username=s.api_username,
        api_password=s.api_password,
    )
    

def _jsonLoads(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _firstStr(x, default: str = "") -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list) and x and isinstance(x[0], str):
        return x[0]
    return default


def _encodePath(p: str) -> str:
    # "/" -> "%2F"
    if not p:
        p = "/"
    return quote(p, safe="")


def _serverHostFromApiBase(apiBaseUrl: str) -> str:
    # "https://45.12.135.70:2053" -> "45.12.135.70"
    try:
        return urlparse(apiBaseUrl).hostname or ""
    except Exception:
        return ""


def _buildVlessRealityLink(
    *,
    userId: str,
    email: str,
    serverHost: str,
    port: int,
    streamSettingsRaw: str,
) -> str | None:
    s = _jsonLoads(streamSettingsRaw)

    # protocol/network: в примере query-параметр называется "type"
    type_ = (s.get("network") or "tcp")  # "xhttp" / "tcp" ...
    security = s.get("security") or ""
    if security != "reality":
        return None

    reality = s.get("realitySettings") or {}

    # В твоём ответе publicKey/fingerprint/spiderX лежат в realitySettings.settings :contentReference[oaicite:3]{index=3}
    rset = (reality.get("settings") or {})
    pbk = rset.get("publicKey") or ""
    fp = rset.get("fingerprint") or "chrome"
    spx = rset.get("spiderX") or "/"

    # sni и sid: берем первый элемент массивов (как sid=15 в примере) :contentReference[oaicite:4]{index=4}
    sni = _firstStr(reality.get("serverNames"), "")
    sid = _firstStr(reality.get("shortIds"), "")

    # xhttp settings (для type=xhttp) :contentReference[oaicite:5]{index=5}
    xhttp = s.get("xhttpSettings") or {}
    path = xhttp.get("path") or "/"
    host = xhttp.get("host") or ""
    mode = xhttp.get("mode") or "auto"

    pathEnc = _encodePath(path)
    hostEnc = quote(host, safe="")  # может быть пустой
    spxEnc = _encodePath(spx)

    # fragment (#...) лучше энкодить
    frag = quote(email or "", safe="")
    flow = ""
    if type_ == "tcp":
        flow = f"&flow={quote('xtls-rprx-vision', safe='')}"

    return (
        f"vless://{userId}@{serverHost}:{port}"
        f"?type={quote(str(type_), safe='')}"
        f"&encryption=none"
        f"&path={pathEnc}"
        f"&host={hostEnc}"
        f"{flow}"
        f"&mode={quote(str(mode), safe='')}"
        f"&security=reality"
        f"&pbk={quote(str(pbk), safe='')}"
        f"&fp={quote(str(fp), safe='')}"
        f"&sni={quote(str(sni), safe='')}"
        f"&sid={quote(str(sid), safe='')}"
        f"&spx={spxEnc}"
        f"#{frag}"
    )

    
@dataclass(slots=True)
class ManagedClient:
    server: VpnServerDTO
    client: XuiClient
    
class Manager:
    SYNC_PERIOD = timedelta(hours=1)
    
    def __init__(self) -> None:
        self._clients: dict[uuid.UUID, ManagedClient] = {}
        self._lastSync: datetime | None = None

    def _needSync(self) -> bool:
        now = datetime.now(timezone.utc)

        if self._lastSync is None:
            return True

        return now >= self._lastSync + self.SYNC_PERIOD

    def _markSynced(self) -> None:
        self._lastSync = datetime.now(timezone.utc)

    def _fingerprint(self, s: VpnServerDTO) -> tuple:
        return (s.api_base_url, s.api_username, s.api_password)

    def _make_client(self, s: VpnServerDTO) -> XuiClient:
        return XuiClient(
            cfg=XuiConfig(api_base_url=s.api_base_url),
            username=s.api_username,
            password=s.api_password,
        )

    async def _syncFromDb(self, servers: list["VpnServer"]) -> None:
        desired = {s.id: to_dto(s) for s in servers}

        current_ids = set(self._clients.keys())
        desired_ids = set(desired.keys())

        # 1) REMOVE: в БД больше нет → удаляем из менеджера
        for server_id in (current_ids - desired_ids):
            entry = self._clients.pop(server_id)
            await entry.client.aclose()

        # 2) ADD/UPDATE
        for server_id, dto in desired.items():
            entry = self._clients.get(server_id)

            if entry is None:
                self._clients[server_id] = ManagedClient(
                    server=dto,
                    client=self._make_client(dto),
                )
                continue

            # UPDATE: если в БД поменялись параметры — пересоздаём клиент
            if self._fingerprint(entry.server) != self._fingerprint(dto):
                await entry.client.aclose()
                entry.client = self._make_client(dto)

            # Всегда обновляем “истину” в entry
            entry.server = dto
    
    async def _ensureSynced(self) -> list[VpnServer]:
        if not self._needSync():
            return

        servers = await db_call(lambda db: db.servers.all())
        await self._syncFromDb(servers)
        self._markSynced()

    # добавить клиента на все сервера
    async def syncUser(self, user: User) -> None:
        await self._ensureSynced()

        userId = str(user.id)
        name = user.username or str(user.tg_user_id)

        sem = asyncio.Semaphore(5)  # лимит параллельности

        async def syncOne(managedClient: ManagedClient) -> None:
            async with sem:
                client: XuiClient = managedClient.client
                inbounds = await client.inbounds()

                for inbound in inbounds:
                    if any(c.id == userId for c in inbound.settings.clients):
                        continue
                    email = f"{name}-{inbound.id}"
                    await client.addClient(inbound.id, userId, email)

                Logger.info('Client "%s" synced on server "%s"', name, client.cfg.api_base_url)

        await asyncio.gather(*(syncOne(mc) for mc in self._clients.values()))

    async def collectConfigs(self, userId: str) -> list[str]:
        await self._ensureSynced()

        sem = asyncio.Semaphore(5)

        async def collectOne(managedClient: "ManagedClient") -> list[str]:
            async with sem:
                client: "XuiClient" = managedClient.client
                cfg = client.cfg

                # если у тебя есть отдельный public host — используй его,
                # иначе берём hostname из api_base_url
                serverHost = getattr(cfg, "publicHost", None) or _serverHostFromApiBase(cfg.api_base_url) or "localhost"

                inbounds = await client.inbounds()
                out: list[str] = []

                for inbound in inbounds:

                    email: str | None = None
                    
                    for c in inbound.settings.clients:
                        if str(c.id) == str(userId):
                            email = c.email
                            break

                    if email is None:
                        continue

                    # streamSettings у тебя в ответе строкой JSON :contentReference[oaicite:7]{index=7}
                    streamRaw = getattr(inbound, "streamSettingsRaw", None) or getattr(inbound, "streamSettings", "")
                    link = _buildVlessRealityLink(
                        userId=userId,
                        email=email,
                        serverHost=serverHost,
                        port=int(getattr(inbound, "port", 0)),
                        streamSettingsRaw=streamRaw,
                    )
                    if link:
                        out.append(link)

                return out

        parts = await asyncio.gather(*(collectOne(mc) for mc in self._clients.values()), return_exceptions=True)

        result: list[str] = []
        for p in parts:
            if isinstance(p, Exception):
                # Logger.exception("collectConfigs error: %s", p)
                continue
            result.extend(p)

        return result
        
        