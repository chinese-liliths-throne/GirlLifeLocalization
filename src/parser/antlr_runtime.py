from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener


PARSER_ROOT = Path(__file__).resolve().parent
GENERATED_ROOT = PARSER_ROOT / "generated"


@dataclass(slots=True, frozen=True)
class AntlrValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


class _CollectingErrorListener(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        self.errors.append(f"line {line}:{column} {msg}")


class AntlrQsrcValidator:
    def __init__(self) -> None:
        from src.parser.generated.qsrcLexer import qsrcLexer
        from src.parser.generated.qsrcParser import qsrcParser

        self._lexer_cls = qsrcLexer
        self._parser_cls = qsrcParser

    def validate_passage_text(self, text: str) -> AntlrValidationResult:
        listener = _CollectingErrorListener()
        lexer = self._lexer_cls(InputStream(text))
        lexer.removeErrorListeners()
        lexer.addErrorListener(listener)
        tokens = CommonTokenStream(lexer)
        parser = self._parser_cls(tokens)
        parser.removeErrorListeners()
        parser.addErrorListener(listener)
        parser.passage()
        return AntlrValidationResult(ok=not listener.errors, errors=tuple(listener.errors))

    def validate_block(self, lines: Iterable[str], *, location_name: str = "codex_runtime") -> AntlrValidationResult:
        body = "\n".join(lines).rstrip("\n")
        wrapped = f"# {location_name}\n{body}\n--- {location_name} --------------\n"
        return self.validate_passage_text(wrapped)

    def validate_text(self, text: str, *, location_name: str = "codex_runtime") -> AntlrValidationResult:
        return self.validate_block(text.splitlines(), location_name=location_name)


_VALIDATOR: AntlrQsrcValidator | None = None


def get_antlr_validator() -> AntlrQsrcValidator | None:
    global _VALIDATOR
    if _VALIDATOR is not None:
        return _VALIDATOR
    try:
        _VALIDATOR = AntlrQsrcValidator()
    except Exception:
        return None
    return _VALIDATOR
