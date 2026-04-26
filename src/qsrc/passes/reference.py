from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.qsrc.errors import QsrcErrorCode, QsrcIssue


HEADER_PATTERN = re.compile(r"(?mi)^\s*#\s*([^\r\n]+?)\s*$")
VISIT_DEF_PATTERN = re.compile(
    r"""(?ix)
    \b(?:if|elseif)\s+
    \$args?\[0\]\s*=\s*
    (?P<quote>'|")
    (?P<value>(?:''|""|\\.|(?!\1).)*?)
    (?P=quote)
    """
)
CALL_PATTERN = re.compile(
    r"""(?ix)
    \b(?P<cmd>gt|gs|gosub|xgt|xgoto|goto|jump|visit)\s+
    (?P<loc>'(?:''|[^'])*'|"(?:\"\"|[^"])*"|''(?:[^']|'(?!'))*'')
    (?:\s*,\s*(?P<visit>'(?:''|[^'])*'|"(?:\"\"|[^"])*"|''(?:[^']|'(?!'))*''))?
    """
)


@dataclass(slots=True, frozen=True)
class RuntimeReference:
    command: str
    location: str
    visit: str | None = None


@dataclass(slots=True, frozen=True)
class ReferenceSnapshot:
    location_name: str
    visits: frozenset[str]
    references: frozenset[RuntimeReference]
    visit_lines: dict[str, tuple[int, str]]
    reference_lines: dict[RuntimeReference, tuple[int, str]]


class QsrcReferencePass:
    rule_id = "reference"

    @classmethod
    def compare_texts(
        cls,
        source_text: str,
        translated_text: str,
        *,
        relative_path: Path | None = None,
        fallback_name: str = "",
    ) -> list[QsrcIssue]:
        source = cls.snapshot(source_text, fallback_name=fallback_name)
        translated = cls.snapshot(translated_text, fallback_name=fallback_name)
        issues: list[QsrcIssue] = []

        if source.location_name != translated.location_name:
            issues.append(
                QsrcIssue(
                    error_code=QsrcErrorCode.LOCATION_NAME_DRIFT,
                    error_desc="location 名称与原版源码不一致。",
                    line=1,
                    location_name=translated.location_name,
                    relative_path=relative_path,
                    details=(f"source: {source.location_name}", f"translated: {translated.location_name}"),
                )
            )

        missing_visits = sorted(source.visits - translated.visits)
        added_visits = sorted(translated.visits - source.visits)
        if missing_visits or added_visits:
            issues.append(
                QsrcIssue(
                    error_code=QsrcErrorCode.VISIT_DRIFT,
                    error_desc="visit 定义与原版源码不一致。",
                    line=1,
                    location_name=translated.location_name,
                    relative_path=relative_path,
                    details=tuple(
                        item
                        for item in (
                            f"missing visits: {', '.join(missing_visits[:20])}" if missing_visits else "",
                            f"added visits: {', '.join(added_visits[:20])}" if added_visits else "",
                        )
                        if item
                    ),
                )
            )

        missing_refs = sorted(source.references - translated.references, key=cls.reference_sort_key)
        added_refs = sorted(translated.references - source.references, key=cls.reference_sort_key)
        if missing_refs or added_refs:
            issues.append(
                QsrcIssue(
                    error_code=QsrcErrorCode.REFERENCE_DRIFT,
                    error_desc="静态跳转骨架与原版源码不一致。",
                    line=1,
                    location_name=translated.location_name,
                    relative_path=relative_path,
                    details=tuple(
                        item
                        for item in (
                            f"missing refs: {', '.join(cls._render_reference(item) for item in missing_refs[:12])}" if missing_refs else "",
                            f"added refs: {', '.join(cls._render_reference(item) for item in added_refs[:12])}" if added_refs else "",
                        )
                        if item
                    ),
                )
            )
        return issues

    @classmethod
    def snapshot(cls, text: str, *, fallback_name: str) -> ReferenceSnapshot:
        header_match = HEADER_PATTERN.search(text)
        location_name = (header_match.group(1).strip() if header_match else fallback_name).strip()
        visits: set[str] = set()
        visit_lines: dict[str, tuple[int, str]] = {}
        references: set[RuntimeReference] = set()
        reference_lines: dict[RuntimeReference, tuple[int, str]] = {}

        for line_no, line_text in enumerate(text.splitlines(), start=1):
            code_mask = cls.build_code_mask(line_text)
            for match in VISIT_DEF_PATTERN.finditer(line_text):
                if not cls.is_code_match(code_mask, match.start()):
                    continue
                visit = cls.decode_quoted(match.group("value"), match.group("quote"))
                visits.add(visit)
                visit_lines.setdefault(visit, (line_no, line_text.rstrip()))

            for match in CALL_PATTERN.finditer(line_text):
                if not cls.is_code_match(code_mask, match.start()):
                    continue
                reference = RuntimeReference(
                    command=match.group("cmd").casefold(),
                    location=cls.decode_literal(match.group("loc")),
                    visit=cls.decode_literal(match.group("visit")) if match.group("visit") else None,
                )
                references.add(reference)
                reference_lines.setdefault(reference, (line_no, line_text.rstrip()))

        return ReferenceSnapshot(
            location_name=location_name,
            visits=frozenset(visits),
            references=frozenset(references),
            visit_lines=visit_lines,
            reference_lines=reference_lines,
        )

    @staticmethod
    def build_code_mask(line: str) -> list[bool]:
        mask = [True] * len(line)
        quote: str | None = None
        index = 0
        while index < len(line):
            char = line[index]
            next_char = line[index + 1] if index + 1 < len(line) else ""
            if quote:
                mask[index] = False
                if char == quote:
                    if next_char == quote:
                        mask[index + 1] = False
                        index += 2
                        continue
                    quote = None
                index += 1
                continue
            if char == "!" and next_char == "!":
                for pos in range(index, len(line)):
                    mask[pos] = False
                break
            if char in ("'", '"'):
                mask[index] = False
                quote = char
            index += 1
        return mask

    @staticmethod
    def is_code_match(mask: list[bool], start: int) -> bool:
        return 0 <= start < len(mask) and mask[start]

    @staticmethod
    def decode_literal(raw: str | None) -> str:
        if not raw:
            return ""
        value = raw.strip()
        if value.startswith("''") and value.endswith("''") and len(value) >= 4:
            inner = value[2:-2]
            return inner.replace("''''", "''")
        if value[0] == value[-1] and value[0] in ("'", '"'):
            return QsrcReferencePass.decode_quoted(value[1:-1], value[0])
        return value

    @staticmethod
    def decode_quoted(value: str, quote: str) -> str:
        return value.replace(quote * 2, quote)

    @staticmethod
    def reference_sort_key(reference: RuntimeReference) -> tuple[str, str, str]:
        return (reference.command, reference.location, reference.visit or "")

    @staticmethod
    def _render_reference(reference: RuntimeReference) -> str:
        return f"{reference.command} {reference.location}" + (f", {reference.visit}" if reference.visit else "")


def compare_reference_texts(
    source_text: str,
    translated_text: str,
    *,
    relative_path: Path | None = None,
    fallback_name: str = "",
) -> list[QsrcIssue]:
    return QsrcReferencePass.compare_texts(
        source_text,
        translated_text,
        relative_path=relative_path,
        fallback_name=fallback_name,
    )
