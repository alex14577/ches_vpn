from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import json


def _as_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
    return default


def _as_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


@dataclass(slots=True)
class InboundClientSettings:
    id: str  # UUID или произвольная строка
    email: str
    enable: bool
    expiryTime: int
    subId: str
    reset: int

    # опциональные поля
    flow: Optional[str] = None
    limitIp: Optional[int] = None
    totalGB: Optional[int] = None
    tgId: Optional[int] = None
    comment: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None

    @staticmethod
    def from_api(data: dict[str, Any]) -> InboundClientSettings:
        return InboundClientSettings(
            id=_as_str(data.get("id")),
            email=_as_str(data.get("email")),
            enable=_as_bool(data.get("enable"), True),
            expiryTime=_as_int(data.get("expiryTime"), 0),
            subId=_as_str(data.get("subId")),
            reset=_as_int(data.get("reset"), 0),
            flow=data.get("flow"),
            limitIp=data.get("limitIp"),
            totalGB=data.get("totalGB"),
            tgId=data.get("tgId"),
            comment=data.get("comment"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass(slots=True)
class InboundSettings:
    clients: list[InboundClientSettings]
    decryption: Optional[str] = None
    fallbacks: Optional[list[Any]] = None

    @staticmethod
    def from_json(raw: str) -> InboundSettings:
        # settings приходит как JSON-строка; иногда бывает пусто/мусор
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}

        raw_clients = data.get("clients", [])
        clients: list[InboundClientSettings] = []
        if isinstance(raw_clients, list):
            for c in raw_clients:
                if isinstance(c, dict):
                    try:
                        clients.append(InboundClientSettings.from_api(c))
                    except Exception:
                        # если конкретный клиент "битый" — просто пропускаем
                        pass

        fallbacks = data.get("fallbacks")
        if fallbacks is not None and not isinstance(fallbacks, list):
            fallbacks = None

        return InboundSettings(
            clients=clients,
            decryption=data.get("decryption"),
            fallbacks=fallbacks,
        )


@dataclass(slots=True)
class ClientStats:
    id: int  # id записи статистики
    inboundId: int
    enable: bool

    email: str
    uuid: str  # связь с settings.clients.id

    up: int
    down: int
    allTime: int
    total: int

    expiryTime: int
    reset: int
    subId: str
    lastOnline: int

    @staticmethod
    def from_api(data: dict[str, Any]) -> ClientStats:
        return ClientStats(
            id=_as_int(data.get("id"), 0),
            inboundId=_as_int(data.get("inboundId"), 0),
            enable=_as_bool(data.get("enable"), True),
            email=_as_str(data.get("email")),
            uuid=_as_str(data.get("uuid")),
            up=_as_int(data.get("up"), 0),
            down=_as_int(data.get("down"), 0),
            allTime=_as_int(data.get("allTime"), 0),
            total=_as_int(data.get("total"), 0),
            expiryTime=_as_int(data.get("expiryTime"), 0),
            reset=_as_int(data.get("reset"), 0),
            subId=_as_str(data.get("subId")),
            lastOnline=_as_int(data.get("lastOnline"), 0),
        )


@dataclass(slots=True)
class Inbound:
    id: int
    port: int
    protocol: str
    tag: str
    enable: bool

    remark: str
    listen: str

    up: int
    down: int
    total: int

    expiryTime: int
    reset: int

    sniffing: Any  # в реальном API часто dict, а не bool

    settingsRaw: str
    streamSettingsRaw: str

    clientStats: list[ClientStats]

    # вычисляемое поле
    settings: InboundSettings

    @staticmethod
    def from_api(data: dict[str, Any]) -> Inbound:
        settings_raw = _as_str(data.get("settings"), "{}")
        stream_settings_raw = _as_str(data.get("streamSettings"), "{}")

        raw_stats = data.get("clientStats", [])
        stats: list[ClientStats] = []
        if isinstance(raw_stats, list):
            for cs in raw_stats:
                if isinstance(cs, dict):
                    try:
                        stats.append(ClientStats.from_api(cs))
                    except Exception:
                        pass

        return Inbound(
            id=_as_int(data.get("id"), 0),
            port=_as_int(data.get("port"), 0),
            protocol=_as_str(data.get("protocol")),
            tag=_as_str(data.get("tag")),
            enable=_as_bool(data.get("enable"), True),

            remark=_as_str(data.get("remark")),
            listen=_as_str(data.get("listen")),

            up=_as_int(data.get("up"), 0),
            down=_as_int(data.get("down"), 0),
            total=_as_int(data.get("total"), 0),

            expiryTime=_as_int(data.get("expiryTime"), 0),
            reset=_as_int(data.get("reset"), 0),

            sniffing=data.get("sniffing"),

            settingsRaw=settings_raw,
            streamSettingsRaw=stream_settings_raw,

            clientStats=stats,

            settings=InboundSettings.from_json(settings_raw),
        )


@dataclass(slots=True)
class InboundsResponse:
    success: bool
    obj: list[Inbound]

    @staticmethod
    def from_api(data: dict[str, Any]) -> InboundsResponse:
        raw_obj = data.get("obj", [])
        inbounds: list[Inbound] = []
        if isinstance(raw_obj, list):
            for i in raw_obj:
                if isinstance(i, dict):
                    try:
                        inbounds.append(Inbound.from_api(i))
                    except Exception:
                        pass

        return InboundsResponse(
            success=_as_bool(data.get("success"), False),
            obj=inbounds,
        )
