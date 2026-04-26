from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from lark import Lark, UnexpectedInput

from .ast import QsrcDocument
from .errors import QsrcErrorCode, QsrcIssue
from .grammar import GRAMMAR
from .linter import QsrcLinter
from .preprocess import PreprocessResult, preprocess_qsrc_text
from .transform import transform_tree


@dataclass(slots=True, frozen=True)
class ParseResult:
    ok: bool
    issues: tuple[QsrcIssue, ...] = ()
    parser_mode: str = "lalr"
    document: QsrcDocument | None = None

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(issue.format_compact() for issue in self.issues)


class LarkQsrcValidator:
    def __init__(self) -> None:
        self._linter = QsrcLinter()

    def validate_passage_text(self, text: str) -> ParseResult:
        return self.parse_text(text)

    def validate_block(self, lines: Iterable[str], *, location_name: str = "codex_runtime") -> ParseResult:
        body = "\n".join(lines).rstrip("\n")
        wrapped = f"# {location_name}\n{body}\n-\n"
        return self.parse_text(wrapped, location_name=location_name)

    def validate_text(self, text: str, *, location_name: str = "codex_runtime") -> ParseResult:
        return self.validate_block(text.splitlines(), location_name=location_name)

    def parse_text(self, text: str, *, location_name: str = "") -> ParseResult:
        preprocessed = preprocess_qsrc_text(text, location_name=location_name)
        if preprocessed.issues:
            return ParseResult(ok=False, issues=tuple(preprocessed.issues), parser_mode="preprocess")

        token_source = "\n".join(line.token_kind for line in preprocessed.logical_lines)
        if not token_source.strip():
            document = QsrcDocument(logical_lines=preprocessed.logical_lines)
            return ParseResult(ok=True, document=document)

        parser_mode = "lalr"
        try:
            tree = _build_lark("lalr").parse(token_source)
        except UnexpectedInput as exc:
            parser_mode = "earley"
            try:
                tree = _build_lark("earley").parse(token_source)
            except UnexpectedInput as inner_exc:
                issue = _unexpected_to_issue(inner_exc, preprocessed)
                return ParseResult(ok=False, issues=(issue,), parser_mode=parser_mode)

        document = transform_tree(tree, preprocessed.logical_lines)
        lint_result = self._linter.lint_document(
            document,
            location_name=preprocessed.location_name or location_name,
            source_text=text,
        )
        issues = tuple(lint_result.issues)
        return ParseResult(ok=lint_result.ok, issues=issues, parser_mode=parser_mode, document=document)


def _unexpected_to_issue(exc: UnexpectedInput, preprocessed: PreprocessResult) -> QsrcIssue:
    line_no = getattr(exc, "line", 0) or 0
    logical_line = preprocessed.logical_lines[line_no - 1] if 0 < line_no <= len(preprocessed.logical_lines) else None
    physical_line = logical_line.start_line if logical_line else 1
    token_kind = logical_line.token_kind if logical_line else ""
    if token_kind in {"ELSE_BLOCK", "ELSE_INLINE", "ELSEIF_BLOCK", "ELSEIF_INLINE", "END"}:
        code = QsrcErrorCode.ENDNOTFOUND
        desc = "块结构不合法，可能缺失或错位了 if/act/for 的 end。"
    else:
        code = QsrcErrorCode.SYNTAX
        desc = "语法结构无法组成合法的 QSP 代码块。"
    details = tuple(
        item
        for item in (
            f"logical token: {token_kind}" if token_kind else "",
            f"expected: {sorted(exc.expected)}" if getattr(exc, "expected", None) else "",
        )
        if item
    )
    return QsrcIssue(
        error_code=code,
        error_desc=desc,
        line=physical_line,
        column=0,
        location_name=preprocessed.location_name,
        details=details,
    )


@lru_cache(maxsize=2)
def _build_lark(mode: str) -> Lark:
    parser_name = "lalr" if mode == "lalr" else "earley"
    return Lark(GRAMMAR, parser=parser_name, start="start", maybe_placeholders=False)


_VALIDATOR: LarkQsrcValidator | None = None


def get_qsrc_validator() -> LarkQsrcValidator:
    global _VALIDATOR
    if _VALIDATOR is None:
        _VALIDATOR = LarkQsrcValidator()
    return _VALIDATOR
