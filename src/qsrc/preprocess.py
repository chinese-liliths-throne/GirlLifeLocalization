from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ast import QsrcLogicalLine
from .errors import QsrcErrorCode, QsrcIssue


LOCATION_HEADER_RE = re.compile(r"^\s*#\s*(?P<name>[^\r\n]+?)\s*$")
LOCATION_FOOTER_RE = re.compile(r"^\s*(?:-|---.*)\s*$")
COMMENT_RE = re.compile(r"^\s*!!")
LABEL_RE = re.compile(r"^\s*:[A-Za-z_][A-Za-z0-9_]*")
FOR_RE = re.compile(r"^\s*for\b", re.IGNORECASE)
IF_RE = re.compile(r"^\s*if\b", re.IGNORECASE)
ELSEIF_RE = re.compile(r"^\s*elseif\b", re.IGNORECASE)
ELSE_RE = re.compile(r"^\s*else\b", re.IGNORECASE)
ACT_RE = re.compile(r"^\s*act\b", re.IGNORECASE)
END_RE = re.compile(r"^\s*end\b", re.IGNORECASE)
INLINE_CONTINUATION_RE = re.compile(r"[ \t]+_$")


@dataclass(slots=True)
class PreprocessResult:
    logical_lines: list[QsrcLogicalLine] = field(default_factory=list)
    issues: list[QsrcIssue] = field(default_factory=list)
    location_name: str = ""


def preprocess_qsrc_text(text: str, *, location_name: str = "") -> PreprocessResult:
    lines = text.splitlines()
    logical_lines: list[QsrcLogicalLine] = []
    issues: list[QsrcIssue] = []
    buffer: list[str] = []
    start_line = 1
    detected_location = location_name
    in_comment_block = False

    for physical_line_no, raw_line in enumerate(lines, start=1):
        if not buffer:
            start_line = physical_line_no
        buffer.append(raw_line)
        if _ends_with_continuation(raw_line):
            continue
        logical_text = _join_logical_parts(buffer)
        if in_comment_block:
            token_kind = "COMMENT"
            if "}" in raw_line:
                in_comment_block = False
        else:
            token_kind = _classify_logical_line(logical_text)
            stripped = logical_text.lstrip()
            if stripped.startswith("!{") and "}" not in logical_text:
                token_kind = "COMMENT"
                in_comment_block = True
        if token_kind == "HEADER" and not detected_location:
            match = LOCATION_HEADER_RE.match(logical_text)
            if match:
                detected_location = match.group("name").strip()
        logical_lines.append(
            QsrcLogicalLine(
                index=len(logical_lines),
                start_line=start_line,
                end_line=physical_line_no,
                text=logical_text,
                token_kind=token_kind,
                is_multiline=physical_line_no > start_line,
            )
        )
        buffer = []

    if buffer:
        token_kind = "COMMENT" if in_comment_block else _classify_logical_line(_join_logical_parts(buffer))
        logical_lines.append(
            QsrcLogicalLine(
                index=len(logical_lines),
                start_line=start_line,
                end_line=len(lines) or 1,
                text=_join_logical_parts(buffer),
                token_kind=token_kind,
                is_multiline=(len(lines) or 1) > start_line,
            )
        )

    issues.extend(_scan_string_and_bracket_health(text, location_name=detected_location or location_name))
    return PreprocessResult(logical_lines=logical_lines, issues=issues, location_name=detected_location)


def _ends_with_continuation(line: str) -> bool:
    return bool(INLINE_CONTINUATION_RE.search(line))


def _join_logical_parts(parts: list[str]) -> str:
    merged: list[str] = []
    for item in parts:
        if _ends_with_continuation(item):
            merged.append(INLINE_CONTINUATION_RE.sub("", item))
        else:
            merged.append(item)
    return "\n".join(merged)


def _classify_logical_line(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "BLANK"
    if LOCATION_HEADER_RE.match(text):
        return "HEADER"
    if LOCATION_FOOTER_RE.match(text):
        return "FOOTER"
    if COMMENT_RE.match(text):
        return "COMMENT"
    if LABEL_RE.match(text):
        return "LABEL"
    if END_RE.match(text):
        return "END"

    colon_index = _code_colon_index(text)
    has_inline_body = colon_index != -1 and bool(text[colon_index + 1 :].strip())

    if FOR_RE.match(text):
        return "FOR_INLINE" if has_inline_body else "FOR_BLOCK"
    if ELSEIF_RE.match(text):
        return "ELSEIF_INLINE" if has_inline_body else "ELSEIF_BLOCK"
    if ELSE_RE.match(text):
        return "ELSE_INLINE" if has_inline_body else "ELSE_BLOCK"
    if IF_RE.match(text):
        return "IF_INLINE" if has_inline_body else "IF_BLOCK"
    if ACT_RE.match(text):
        return "ACT_INLINE" if has_inline_body else "ACT_BLOCK"
    return "GENERIC"


def _code_colon_index(text: str) -> int:
    quote: str | None = None
    paren_balance = 0
    bracket_balance = 0
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if quote:
            if char == quote:
                if nxt == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            index += 1
            continue
        if char == "(":
            paren_balance += 1
        elif char == ")" and paren_balance:
            paren_balance -= 1
        elif char == "[":
            bracket_balance += 1
        elif char == "]" and bracket_balance:
            bracket_balance -= 1
        elif char == ":" and paren_balance == 0 and bracket_balance == 0:
            return index
        index += 1
    return -1


def _scan_string_and_bracket_health(text: str, *, location_name: str = "") -> list[QsrcIssue]:
    issues: list[QsrcIssue] = []
    quote: str | None = None
    quote_line = 1
    line = 1
    paren_balance = 0
    bracket_balance = 0

    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if char == "\n":
            line += 1
            index += 1
            continue

        if quote:
            if char == quote:
                if nxt == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in ("'", '"'):
            quote = char
            quote_line = line
            index += 1
            continue

        if char == "(":
            paren_balance += 1
        elif char == ")":
            if paren_balance == 0:
                issues.append(
                    QsrcIssue(
                        error_code=QsrcErrorCode.BRACKNOTFOUND,
                        error_desc="存在未匹配的右圆括号。",
                        line=line,
                        location_name=location_name,
                    )
                )
            else:
                paren_balance -= 1
        elif char == "[":
            bracket_balance += 1
        elif char == "]":
            if bracket_balance == 0:
                issues.append(
                    QsrcIssue(
                        error_code=QsrcErrorCode.BRACKNOTFOUND,
                        error_desc="存在未匹配的右方括号。",
                        line=line,
                        location_name=location_name,
                    )
                )
            else:
                bracket_balance -= 1
        index += 1

    if quote:
        issues.append(
            QsrcIssue(
                error_code=QsrcErrorCode.QUOTNOTFOUND,
                error_desc=f"字符串未闭合，起始引号 {quote!r}。",
                line=quote_line,
                location_name=location_name,
            )
        )
    if paren_balance:
        issues.append(
            QsrcIssue(
                error_code=QsrcErrorCode.BRACKNOTFOUND,
                error_desc="圆括号未闭合。",
                line=line,
                location_name=location_name,
            )
        )
    if bracket_balance:
        issues.append(
            QsrcIssue(
                error_code=QsrcErrorCode.BRACKNOTFOUND,
                error_desc="方括号未闭合。",
                line=line,
                location_name=location_name,
            )
        )
    return issues
