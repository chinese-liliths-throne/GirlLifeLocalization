from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ast import QsrcDocument
from .config import QsrcLintConfig
from .ignore import IgnoreMap


@dataclass(slots=True)
class LintContext:
    document: QsrcDocument
    source_text: str
    location_name: str
    relative_path: Path | None
    config: QsrcLintConfig
    ignore_map: IgnoreMap

