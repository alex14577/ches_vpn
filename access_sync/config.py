from dataclasses import dataclass
import os


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return int(value)


@dataclass(frozen=True)
class AccessSyncConfig:
    interval_seconds: int


def load_config() -> AccessSyncConfig:
    return AccessSyncConfig(
        interval_seconds=_get_int("ACCESS_SYNC_INTERVAL_SECONDS", 60),
    )
