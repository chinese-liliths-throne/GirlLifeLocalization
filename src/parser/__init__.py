from __future__ import annotations

from src.qsrc.parser import LarkQsrcValidator, ParseResult, get_qsrc_validator


def get_antlr_validator():
    try:
        from .antlr_runtime import get_antlr_validator as _get_antlr_validator
    except Exception:
        return None
    return _get_antlr_validator()


__all__ = ["LarkQsrcValidator", "ParseResult", "get_antlr_validator", "get_qsrc_validator"]
