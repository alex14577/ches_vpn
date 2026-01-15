from dataclasses import dataclass
import os
import re


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return int(value)


def _get_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def _parse_vk_peer_id(raw_value: str) -> int:
    value = raw_value.strip()
    if not value:
        raise ValueError("VK peer id is empty")
    match = re.match(r"^(?:peer=?)(-?\d+)$", value)
    if match:
        return int(match.group(1))
    return int(value)


@dataclass(frozen=True)
class PayVerifierConfig:
    vk_token: str
    vk_peer_id: int
    poll_interval_seconds: int
    vk_lookback_minutes: int
    pending_lookback_days: int
    vk_incoming_only: bool
    vk_max_messages: int


def load_config() -> PayVerifierConfig:
    vk_token = os.environ.get("VK_TOKEN", "").strip()
    if not vk_token:
        raise RuntimeError("VK_TOKEN is required")

    peer_raw = os.environ.get("VK_PEER_ID", "").strip() or os.environ.get("VK_TARGET_USER_ID", "").strip()
    if not peer_raw:
        raise RuntimeError("VK_PEER_ID (or VK_TARGET_USER_ID) is required")
    vk_peer_id = _parse_vk_peer_id(peer_raw)

    return PayVerifierConfig(
        vk_token=vk_token,
        vk_peer_id=vk_peer_id,
        poll_interval_seconds=_get_int("POLL_INTERVAL_SECONDS", 5),
        vk_lookback_minutes=_get_int("VK_LOOKBACK_MINUTES", 15),
        pending_lookback_days=_get_int("PENDING_LOOKBACK_DAYS", 7),
        vk_incoming_only=_get_bool("VK_INCOMING_ONLY", True),
        vk_max_messages=_get_int("VK_MAX_MESSAGES", 500),
    )
