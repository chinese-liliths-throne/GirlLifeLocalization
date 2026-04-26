from __future__ import annotations

from antlr4 import Lexer


class qsrcLexerBase(Lexer):
    def __init__(self, input=None, output=None):
        super().__init__(input, output)
        self._template_depth = 0

    def IsInTemplateString(self) -> bool:
        return self._template_depth > 0

    def ProcessTemplateOpen(self) -> None:
        self._template_depth += 1

    def ProcessTemplateClose(self) -> None:
        if self._template_depth > 0:
            self._template_depth -= 1
