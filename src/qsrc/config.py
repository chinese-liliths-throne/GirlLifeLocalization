from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import orjson


@dataclass(slots=True)
class QsrcLintConfig:
    disabled_rules: set[str] = field(default_factory=set)
    warning_as_error: bool = False
    max_line_length: int = 180
    enable_project_style_passes: bool = True
    enable_runtime_bridge_checks: bool = False

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "QsrcLintConfig":
        disabled = payload.get("disabled_rules", payload.get("disable", []))
        if not isinstance(disabled, list):
            disabled = []
        return cls(
            disabled_rules={str(item).strip() for item in disabled if str(item).strip()},
            warning_as_error=bool(payload.get("warning_as_error", False)),
            max_line_length=int(payload.get("max_line_length", 180)),
            enable_project_style_passes=bool(payload.get("enable_project_style_passes", True)),
            enable_runtime_bridge_checks=bool(payload.get("enable_runtime_bridge_checks", False)),
        )


def load_qsrc_lint_config(start: Path | str | None = None) -> QsrcLintConfig:
    base = Path(start).resolve() if start else Path.cwd().resolve()
    for root in (base, *base.parents):
        candidate = root / ".qsrclintrc"
        if candidate.exists():
            try:
                payload = orjson.loads(candidate.read_bytes())
            except Exception:
                return QsrcLintConfig()
            if isinstance(payload, dict):
                return QsrcLintConfig.from_mapping(payload)
            return QsrcLintConfig()
    return QsrcLintConfig()
