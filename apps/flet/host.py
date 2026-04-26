from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config.paths import paths

from .models import HostMode


@dataclass(slots=True)
class MobileFileService:
    def pick_game_file(self) -> Path | None:
        return None

    def pick_project_root(self) -> Path | None:
        return None

    def resolve_uri_to_runtime_path(self, uri_or_path: str) -> Path:
        return Path(uri_or_path).resolve()

    def get_save_root(self) -> Path:
        target = paths.tmp / "android_saves"
        target.mkdir(parents=True, exist_ok=True)
        return target


def is_mobile_host(host_mode: HostMode) -> bool:
    return host_mode == HostMode.ANDROID
