from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "generated"
PYTHON_GRAMMAR_DIR = ROOT / "python_grammar"
ANTLR_JAR = ROOT / "antlr-4.13.2-complete.jar"


def _adapt_grammar(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    text = text.replace("this.", "self.")
    text = text.replace("-Dlanguage=JavaScript", "-Dlanguage=Python3")
    destination.write_text(text, encoding="utf-8", newline="\n")


def generate() -> None:
    if not ANTLR_JAR.exists():
        raise FileNotFoundError(f"ANTLR jar not found: {ANTLR_JAR}")

    PYTHON_GRAMMAR_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    lexer_grammar = ROOT / "qsrcLexer.g4"
    parser_grammar = ROOT / "qsrcParser.g4"
    lexer_out = PYTHON_GRAMMAR_DIR / lexer_grammar.name
    parser_out = PYTHON_GRAMMAR_DIR / parser_grammar.name
    _adapt_grammar(lexer_grammar, lexer_out)
    _adapt_grammar(parser_grammar, parser_out)

    command = [
        "java",
        "-jar",
        str(ANTLR_JAR),
        "-Dlanguage=Python3",
        "-visitor",
        "-no-listener",
        "-o",
        str(GENERATED_DIR),
        str(lexer_out),
        str(parser_out),
    ]
    subprocess.run(command, check=True, cwd=ROOT)

    init_path = GENERATED_DIR / "__init__.py"
    if not init_path.exists():
        init_path.write_text("", encoding="utf-8")
    shim_path = GENERATED_DIR / "qsrcLexerBase.py"
    shim_path.write_text("from src.parser.qsrcLexerBase import qsrcLexerBase\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
