from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from src.qsrc.statements import STATEMENT_BY_ALIAS

try:
    import flet_code_editor as fce
except Exception:  # pragma: no cover - optional dependency
    fce = None


@dataclass(slots=True, frozen=True)
class CodeEditorSupport:
    available: bool
    reason: str = ""


def code_editor_support() -> CodeEditorSupport:
    if fce is None:
        return CodeEditorSupport(False, "flet-code-editor 未安装。")
    return CodeEditorSupport(True)


def _gutter_style():
    if fce is None:
        return None
    return fce.GutterStyle(
        text_style=ft.TextStyle(font_family="Consolas", size=12, color=ft.Colors.BLUE_GREY_200),
        background_color=ft.Colors.with_opacity(0.14, ft.Colors.BLACK),
        width=60,
        show_errors=True,
        show_folding_handles=True,
        show_line_numbers=True,
    )


def default_autocomplete_words(extra_words: list[str] | None = None) -> list[str]:
    words = set(STATEMENT_BY_ALIAS.keys())
    words.update(
        {
            "ARGS",
            "$ARGS",
            "$COUNTER",
            "$RESULT",
            "$CURLOC",
            "result",
            "input",
            "iif",
            "rand",
            "func",
            "dyneval",
            "killvar",
            "gt",
            "gs",
            "xgt",
            "xgoto",
            "goto",
            "gosub",
            "jump",
            "msg",
            "view",
            "play",
            "addobj",
            "delobj",
            "settimer",
            "showacts",
            "showobjs",
            "showstat",
            "showinput",
        }
    )
    if extra_words:
        words.update(word for word in extra_words if word)
    return sorted(words)


def create_code_editor(*, value: str, autocomplete_words: list[str] | None, on_change, read_only: bool = False) -> ft.Control:
    support = code_editor_support()
    if not support.available:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("CodeEditor 不可用", color=ft.Colors.RED_300, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        support.reason or "当前环境缺少 flet-code-editor，无法启用代码编辑器。",
                        color=ft.Colors.GREY_300,
                    ),
                ],
                spacing=8,
            ),
            expand=True,
            padding=16,
        )

    return fce.CodeEditor(
        language=fce.CodeLanguage.RUBY,
        code_theme=fce.CodeTheme.ATOM_ONE_DARK,
        text_style=ft.TextStyle(font_family="Consolas", size=13),
        gutter_style=_gutter_style(),
        value=value,
        padding=10,
        autocomplete=True,
        autocomplete_words=autocomplete_words or [],
        read_only=read_only,
        expand=True,
        on_change=on_change,
    )
