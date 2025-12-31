from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from common.xui_client.types.inbounds import ClientStats, Inbound, InboundClientSettings, InboundSettings, InboundsResponse

import json
import time
import uuid

import httpx


class XuiError(RuntimeError):
    pass


@dataclass(frozen=True)
class XuiConfig:
    api_base_url: str = "127.0.0.1"


class XuiClient:
    """
    Async client for 3x-ui panel API.

    - Uses cookie-based auth after /login
    - Auto re-login by TTL and cookie presence
    - httpx.AsyncClient to avoid blocking asyncio (important for your PTB bot)
    """

    def __init__(
        self,
        cfg: XuiConfig,
        *,
        username: str,
        password: str,
        timeout_sec: float = 10.0,
        verify_tls: bool = False,
        user_agent: str = "tg-bot/1.0",
        login_ttl_sec: float = 55 * 60,
    ) -> None:
        self.cfg = cfg
        self.username = username
        self.password = password
        self.timeout = timeout_sec
        self.verify_tls = verify_tls
        self.user_agent = user_agent

        self._login_ttl_sec = float(login_ttl_sec)
        self._last_login_monotonic: float | None = None

        self._client: httpx.AsyncClient = self._new_client()

    # ---------- lifecycle ----------

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self.cfg.api_base_url}",
            timeout=self.timeout,
            verify=self.verify_tls,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": self.user_agent,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def reset(self) -> None:
        await self._client.aclose()
        self._client = self._new_client()
        self._last_login_monotonic = None

    # ---------- helpers ----------

    def _has_cookie(self) -> bool:
        # 3x-ui обычно ставит cookie с именем "3x-ui"
        return "3x-ui" in self._client.cookies

    def _login_stale(self) -> bool:
        if self._last_login_monotonic is None:
            return True
        return (time.monotonic() - self._last_login_monotonic) >= self._login_ttl_sec

    def _raise_http(self, where: str, r: httpx.Response) -> None:
        raise XuiError(f"{where} failed: http={r.status_code} body={r.text[:300]}")

    def _parse_success_obj_list(self, where: str, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict) and data.get("success") is True and isinstance(data.get("obj"), list):
            return data["obj"]
        raise XuiError(f"{where} unexpected response: {data!r}")

    def _parse_success_dict(self, where: str, data: Any) -> dict[str, Any]:
        if isinstance(data, dict) and data.get("success") is True:
            return data
        raise XuiError(f"{where} unexpected response: {data!r}")

    async def ensure_login(self, *, force: bool = False) -> None:
        if force or (not self._has_cookie()) or self._login_stale():
            await self.login()

    # ---------- API ----------
    async def aclose(self) -> None:
        await self._client.aclose()
        

    async def login(self) -> None:
        """
        POST /login
        body: {"username": "...", "password": "..."}
        expects: {"success": true, ...} and cookie "3x-ui"
        """
        await self.reset()

        r = await self._client.post(
            "/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
        )
        if r.status_code != 200:
            self._raise_http("login", r)

        try:
            data = r.json()
        except Exception:
            raise XuiError(f"login failed: invalid json http={r.status_code} body={r.text[:300]}")

        self._parse_success_dict("login", data)

        if not self._has_cookie():
            raise XuiError("login ok, but 3x-ui cookie not found in session")

        self._last_login_monotonic = time.monotonic()

    async def inbounds(self) -> list[Inbound]:
        await self.ensure_login()

        r = await self._client.get("/panel/api/inbounds/list")
        if r.status_code != 200:
            self._raise_http("panel/api/inbounds/list", r)
            
        res: InboundsResponse = InboundsResponse.from_api(r.json())
        return res.obj


    async def del_client(self, inboundId: int, email: str) -> dict[str, Any]:
        """
        POST /panel/api/inbounds/{inboundId}/delClientByEmail/{email}
        """
        await self.ensure_login()

        r = await self._client.post(f"/panel/api/inbounds/{inboundId}/delClientByEmail/{email}")
        if r.status_code != 200:
            self._raise_http("del_client", r)

        try:
            data = r.json()
        except Exception:
            raise XuiError(f"del_client failed: invalid json http={r.status_code} body={r.text[:300]}")
        if isinstance(data, dict):
            return data
        raise XuiError(f"del_client unexpected response: {data!r}")
    
    async def clientExists(self, clientId: str) -> bool:
        await self.ensure_login()

        inbounds = await self.inbounds()
        for inbound in inbounds:
            if any(c.id == clientId for c in inbound.settings.clients):
                return True
        return False

    def _make_client_settings(self, client_uuid: uuid.UUID, email: str) -> dict[str, Any]:
        return {
            "clients": [{
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
            }]
        }

    async def addClient(
        self,
        inboundId: int,
        client_uuid: uuid.UUID | str,
        email: str,
        *,
        retry_on_duplicate: bool = True,
    ) -> dict[str, Any]:
        """
        POST /panel/api/inbounds/addClient
        - если "Duplicate email" -> удаляем и пробуем 1 раз ещё (как было)
        """
        await self.ensure_login()

        cu = uuid.UUID(str(client_uuid))
        settings = self._make_client_settings(cu, email)

        async def do_request() -> httpx.Response:
            return await self._client.post(
                "/panel/api/inbounds/addClient",
                data={
                    "id": str(inboundId),
                    "settings": json.dumps(settings, separators=(",", ":")),
                },
                headers={"Accept": "application/json"},
            )

        def parse_json(where: str, r: httpx.Response) -> dict[str, Any]:
            try:
                data = r.json()
            except Exception:
                raise XuiError(f"{where} failed: invalid json http={r.status_code} body={r.text[:300]}")
            if not isinstance(data, dict):
                raise XuiError(f"{where} failed: unexpected response type: {type(data).__name__}")
            return data

        r = await do_request()
        if r.status_code != 200:
            self._raise_http("add_client", r)

        data = parse_json("add_client", r)
        msg = str(data.get("msg", ""))

        if retry_on_duplicate and ("Duplicate email" in msg):
            await self.del_client(inboundId, email)

            r2 = await do_request()
            if r2.status_code != 200:
                self._raise_http("add_client retry", r2)

            return parse_json("add_client retry", r2)

        return data
