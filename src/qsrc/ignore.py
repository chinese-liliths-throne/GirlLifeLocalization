from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ast import QsrcLogicalLine


IGNORE_ONCE_RE = re.compile(r"qlint:ignore\s*=\s*(?P<rules>[A-Za-z0-9_,\- ]+)", re.IGNORECASE)
DISABLE_RE = re.compile(r"qlint:disable\s*=\s*(?P<rules>[A-Za-z0-9_,\- ]+)", re.IGNORECASE)
ENABLE_RE = re.compile(r"qlint:enable\s*=\s*(?P<rules>[A-Za-z0-9_,\- ]+)", re.IGNORECASE)


@dataclass(slots=True)
class IgnoreMap:
    disabled_by_line: dict[int, set[str]] = field(default_factory=dict)

    def allows(self, rule_id: str, line: int) -> bool:
        disabled = self.disabled_by_line.get(line, set())
        return rule_id not in disabled and "*" not in disabled


def build_ignore_map(logical_lines: list[QsrcLogicalLine]) -> IgnoreMap:
    ignore_map = IgnoreMap()
    persistent_disabled: set[str] = set()
    single_line_disabled: dict[int, set[str]] = {}

    comment_lines = [line for line in logical_lines if line.token_kind == "COMMENT"]
    for line in comment_lines:
        disabled_once = _extract_rules(IGNORE_ONCE_RE, line.text)
        if disabled_once:
            target_line = _next_non_comment_line(logical_lines, line.index)
            if target_line is not None:
                single_line_disabled.setdefault(target_line.start_line, set()).update(disabled_once)

        disabled_forever = _extract_rules(DISABLE_RE, line.text)
        if disabled_forever:
            persistent_disabled.update(disabled_forever)

        enabled = _extract_rules(ENABLE_RE, line.text)
        if enabled:
            for rule in enabled:
                persistent_disabled.discard(rule)
            if "*" in enabled:
                persistent_disabled.clear()

        ignore_map.disabled_by_line[line.start_line] = set(persistent_disabled)

    current_disabled: set[str] = set()
    for line in logical_lines:
        if line.token_kind == "COMMENT":
            current_disabled = set(ignore_map.disabled_by_line.get(line.start_line, current_disabled))
            continue
        combined = set(current_disabled)
        combined.update(single_line_disabled.get(line.start_line, set()))
        if combined:
            ignore_map.disabled_by_line[line.start_line] = combined
    return ignore_map


def _extract_rules(pattern: re.Pattern[str], text: str) -> set[str]:
    match = pattern.search(text)
    if not match:
        return set()
    return {item.strip() for item in match.group("rules").split(",") if item.strip()}


def _next_non_comment_line(logical_lines: list[QsrcLogicalLine], index: int) -> QsrcLogicalLine | None:
    for candidate in logical_lines[index + 1 :]:
        if candidate.token_kind != "COMMENT":
            return candidate
    return None

