from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class QsrcErrorCode(StrEnum):
    LOCNOTFOUND = "LOCNOTFOUND"
    ENDNOTFOUND = "ENDNOTFOUND"
    LABELNOTFOUND = "LABELNOTFOUND"
    QUOTNOTFOUND = "QUOTNOTFOUND"
    BRACKNOTFOUND = "BRACKNOTFOUND"
    ARGSCOUNT = "ARGSCOUNT"
    SYNTAX = "SYNTAX"
    REFERENCE_DRIFT = "REFERENCE_DRIFT"
    VISIT_DRIFT = "VISIT_DRIFT"
    LOCATION_NAME_DRIFT = "LOCATION_NAME_DRIFT"
    SOURCE_MISSING = "SOURCE_MISSING"


@dataclass(slots=True, frozen=True)
class QsrcIssue:
    error_code: QsrcErrorCode
    error_desc: str
    line: int = 0
    column: int = 0
    location_name: str = ""
    act_index: int = -1
    relative_path: Path | None = None
    severity: str = "error"
    details: tuple[str, ...] = field(default_factory=tuple)
    context_diff: tuple[str, ...] = field(default_factory=tuple)

    def format_compact(self) -> str:
        location = f" [{self.location_name}]" if self.location_name else ""
        position = f" line {self.line}:{self.column}" if self.line else ""
        return f"{self.error_code}{location}{position} {self.error_desc}".strip()
