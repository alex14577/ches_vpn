from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import asyncio
import json
import time
import uuid

import httpx

from common.xui_client.types.inbounds import Inbound, InboundsResponse


class XuiError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class XuiConfig:
    api_base_url: str
    publicHost: str | None = None


class XuiClient:
    """
    Async client for 3x-ui panel API.

    ✔ cookie-based auth
    ✔ auto re-login with TTL
    ✔ retry on network / 5xx errors
    ✔ login protected by asyncio.Lock
    """

    COOKIE_NAME = "3x-ui"

    def __init__(
        self,
        cfg: XuiConfig,
        *,
        username: str,
        password: str,
        verify_tls: bool = False,
        user_agent: str = "tg-bot/1.0",
        login_ttl_sec: float = 55 * 60,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
    ) -> None:
        self.cfg = cfg
        self.username = username
        self.password = password

        self._verify_tls = verify_tls
        self._user_agent = user_agent
        self._login_ttl_sec = float(login_ttl_sec)

        self._last_login_monotonic: float | None = None
        self._login_lock = asyncio.Lock()

        self._max_retries = int(max_retries)
        self._retry_backoff = float(retry_backoff)

        self._client = self._new_client()

    # ---------- lifecycle ----------

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.cfg.api_base_url.rstrip("/"),
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
            verify=self._verify_tls,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": self._user_agent,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def reset(self) -> None:
        await self._client.aclose()
        self._client = self._new_client()
        self._last_login_monotonic = None

    # ---------- auth ----------

    def _has_cookie(self) -> bool:
        return self.COOKIE_NAME in self._client.cookies

    def _login_stale(self) -> bool:
        if self._last_login_monotonic is None:
            return True
        return (time.monotonic() - self._last_login_monotonic) >= self._login_ttl_sec

    async def ensure_login(self, *, force: bool = False) -> None:
        if not force and self._has_cookie() and not self._login_stale():
            return

        async with self._login_lock:
            if not force and self._has_cookie() and not self._login_stale():
                return
            await self.login()

    async def login(self) -> None:
        await self.reset()

        r = await self._client.post(
            "/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
        )
        if r.status_code != 200:
            raise XuiError(f"login failed: http={r.status_code} body={r.text[:300]}")

        try:
            data = r.json()
        except Exception:
            raise XuiError("login failed: invalid json")

        if not (isinstance(data, dict) and data.get("success") is True):
            raise XuiError(f"login unexpected response: {data!r}")

        if not self._has_cookie():
            raise XuiError("login ok, but cookie not found")

        self._last_login_monotonic = time.monotonic()

    # ---------- request helper ----------

    @staticmethod
    def _retryable_status(code: int) -> bool:
        return code in (408, 429) or 500 <= code <= 599

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        await self.ensure_login()

        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                r = await self._client.request(method, url, **kwargs)

                if r.status_code in (401, 403):
                    await self.ensure_login(force=True)
                    r = await self._client.request(method, url, **kwargs)

                if self._retryable_status(r.status_code) and attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff * (2 ** (attempt - 1)))
                    continue

                return r

            except (
                httpx.ReadTimeout,
                httpx.ReadError,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
            ) as e:
                last_exc = e
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(self._retry_backoff * (2 ** (attempt - 1)))

        raise XuiError(f"request failed after retries: {method} {url}: {last_exc!r}")

    @staticmethod
    def _json_dict(where: str, r: httpx.Response) -> dict[str, Any]:
        try:
            data = r.json()
        except Exception:
            raise XuiError(f"{where} invalid json http={r.status_code}")
        if not isinstance(data, dict):
            raise XuiError(f"{where} unexpected response type")
        return data

    # ---------- API ----------

    async def inbounds(self) -> list[Inbound]:
        r = await self._request("GET", "/panel/api/inbounds/list")
        if r.status_code != 200:
            raise XuiError(f"inbounds failed http={r.status_code}")
        res: InboundsResponse = InboundsResponse.from_api(r.json())
        return res.obj

    async def delClient(self, inboundId: int, client_uuid: uuid.UUID | str) -> dict[str, Any]:
        client_uuid = uuid.UUID(str(client_uuid))
        r = await self._request("POST", f"/panel/api/inbounds/{inboundId}/delClient/{client_uuid}")
        if r.status_code != 200:
            raise XuiError(f"delClient failed http={r.status_code}")
        return self._json_dict("delClient", r)

    async def clientExists(self, clientId: str) -> bool:
        inbounds = await self.inbounds()
        return any(
            any(c.id == clientId for c in inbound.settings.clients)
            for inbound in inbounds
        )

    def _make_client_settings(self, client_uuid: uuid.UUID, email: str) -> dict[str, Any]:
        return {
            "clients": [
                {
                    "id": str(client_uuid),
                    "email": email,
                    "enable": True,
                    "flow": "xtls-rprx-vision",
                    "limitIp": 0,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "tgId": "",
                    "subId": "",
                    "comment": "",
                    "reset": 0,
                }
            ]
        }

    async def addClient(
        self,
        inboundId: int,
        client_uuid: uuid.UUID | str,
        email: str,
        *,
        retry_on_duplicate: bool = True,
    ) -> dict[str, Any]:
        client_uuid = uuid.UUID(str(client_uuid))
        settings = self._make_client_settings(client_uuid, email)

        r = await self._request(
            "POST",
            "/panel/api/inbounds/addClient",
            data={
                "id": str(inboundId),
                "settings": json.dumps(settings, separators=(",", ":")),
            },
            headers={"Accept": "application/json"},
        )

        if r.status_code != 200:
            raise XuiError(f"addClient failed http={r.status_code}")

        data = self._json_dict("addClient", r)
        msg = str(data.get("msg", ""))

        if retry_on_duplicate and "Duplicate email" in msg:
            # если uuid уже есть — считаем успехом (идемпотентность)
            inbounds = await self.inbounds()
            for ib in inbounds:
                if ib.id == inboundId and any(str(c.id) == str(client_uuid) for c in ib.settings.clients):
                    return data

            # иначе — меняем email
            email2 = f"{email}-{client_uuid.hex[:6]}"
            settings = self._make_client_settings(client_uuid, email2)

            r2 = await self._request(
                "POST",
                "/panel/api/inbounds/addClient",
                data={
                    "id": str(inboundId),
                    "settings": json.dumps(settings, separators=(",", ":")),
                },
                headers={"Accept": "application/json"},
            )
            if r2.status_code != 200:
                raise XuiError(f"addClient retry failed http={r2.status_code}")

            return self._json_dict("addClient retry", r2)

        return data
