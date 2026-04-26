from __future__ import annotations

import re

from src.qsrc.context import LintContext
from src.qsrc.errors import QsrcErrorCode, QsrcIssue
from src.qsrc.preprocess import _code_colon_index
from src.qsrc.statements import STATEMENT_BY_ALIAS, find_statement


class QsrcStatementPass:
    rule_id = "statement"

    def run(self, context: LintContext) -> list[QsrcIssue]:
        issues: list[QsrcIssue] = []
        for line in context.document.logical_lines:
            if line.token_kind in {"BLANK", "COMMENT", "LABEL", "HEADER", "FOOTER", "END"}:
                continue
            for command in _split_commands(line.text):
                issues.extend(_lint_single_command(command, line=line.start_line, context=context, token_kind=line.token_kind))
        return [issue for issue in issues if context.ignore_map.allows(str(issue.error_code), issue.line)]


def _lint_single_command(command: str, *, line: int, context: LintContext, token_kind: str) -> list[QsrcIssue]:
    stripped = command.strip()
    if not stripped:
        return []

    explicit_alias = {
        "IF_INLINE": "if",
        "IF_BLOCK": "if",
        "ELSEIF_INLINE": "elseif",
        "ELSEIF_BLOCK": "elseif",
        "ELSE_INLINE": "else",
        "ELSE_BLOCK": "else",
        "ACT_INLINE": "act",
        "ACT_BLOCK": "act",
        "FOR_INLINE": "for",
        "FOR_BLOCK": "for",
    }.get(token_kind)

    if stripped.startswith(("'", '"', "<<", "*nl", "*pl")):
        return []
    if "=" in stripped and not _starts_with_keyword(stripped):
        return []

    colon_index = _code_colon_index(stripped)
    head = stripped if colon_index == -1 else stripped[:colon_index]
    alias = explicit_alias or _match_statement_alias(head)
    if not alias:
        return []
    spec = find_statement(alias)
    if spec is None:
        return []

    arg_region = head[len(alias) :].strip() if spec.canonical in {"if", "elseif", "act", "for"} else stripped[len(alias) :].strip()
    if spec.canonical in {"if", "elseif", "for"}:
        return [] if arg_region else [_warning(line, context, alias, "缺少必要表达式。", stripped)]
    if spec.canonical == "act":
        return [] if arg_region else [_warning(line, context, alias, "缺少动作文本。", stripped)]

    args = _split_top_level_args(arg_region)
    if spec.min_args <= len(args) <= spec.max_args or spec.canonical in {"clear", "p", "pl", "nl"}:
        return []
    return [
        QsrcIssue(
            error_code=QsrcErrorCode.ARGSCOUNT,
            error_desc=f"语句 {alias} 参数数量异常，当前 {len(args)}，预期 {spec.min_args}~{spec.max_args}。",
            line=line,
            location_name=context.location_name,
            relative_path=context.relative_path,
            severity="warning",
            details=(f"command: {stripped}",),
        )
    ]


def _warning(line: int, context: LintContext, alias: str, message: str, stripped: str) -> QsrcIssue:
    return QsrcIssue(
        error_code=QsrcErrorCode.ARGSCOUNT,
        error_desc=f"语句 {alias} {message}",
        line=line,
        location_name=context.location_name,
        relative_path=context.relative_path,
        severity="warning",
        details=(f"command: {stripped}",),
    )


def _starts_with_keyword(text: str) -> bool:
    return bool(re.match(r"^\s*(if|elseif|act|for|set|let|local)\b", text, re.IGNORECASE))


def _match_statement_alias(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    lowered = stripped.casefold()
    aliases = sorted(STATEMENT_BY_ALIAS, key=len, reverse=True)
    for alias in aliases:
        if lowered.startswith(alias) and (len(lowered) == len(alias) or lowered[len(alias)].isspace()):
            return alias
    return None


def _split_commands(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    paren = 0
    bracket = 0
    brace = 0
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
        elif char == "(":
            paren += 1
        elif char == ")" and paren:
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]" and bracket:
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}" and brace:
            brace -= 1
        elif char == "&" and paren == 0 and bracket == 0 and brace == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return parts


def _split_top_level_args(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts: list[str] = []
    start = 0
    quote: str | None = None
    paren = 0
    bracket = 0
    brace = 0
    index = 0
    while index < len(stripped):
        char = stripped[index]
        nxt = stripped[index + 1] if index + 1 < len(stripped) else ""
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
        elif char == "(":
            paren += 1
        elif char == ")" and paren:
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]" and bracket:
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}" and brace:
            brace -= 1
        elif char == "," and paren == 0 and bracket == 0 and brace == 0:
            parts.append(stripped[start:index].strip())
            start = index + 1
        index += 1
    tail = stripped[start:].strip()
    if tail:
        parts.append(tail)
    return parts
