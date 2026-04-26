from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from src.config.error_reporting import ErrorReporter
from src.storage.files import FileManager
from src.config.logging import logger
from src.config.progress import ProgressBar


TOKEN_PATTERN = re.compile(r"\b(if|elseif|else|end|act|loop|while)\b", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"(<<[^>]+>>|&lt;&lt;.*?&gt;&gt;)")
HTML_TAG_PATTERN = re.compile(r"<\s*(/)?\s*([A-Za-z0-9]+)(?:\s+[^>]*)?\s*(/?)>")


@dataclass(slots=True, frozen=True)
class QsrcGuardIssue:
    relative_path: Path
    reason: str
    details: tuple[str, ...] = ()


@dataclass(slots=True)
class QsrcGuardStats:
    total_files: int = 0
    checked_files: int = 0
    locked_files: int = 0


class QsrcBuildGuard:
    def __init__(
        self,
        *,
        source_root: Path | str,
        translated_root: Path | str,
        error_reporter: ErrorReporter | None = None,
        show_progress: bool = False,
    ):
        self.source_root = Path(source_root).resolve()
        self.translated_root = Path(translated_root).resolve()
        self.error_reporter = error_reporter
        self.show_progress = show_progress

    @classmethod
    def analyze_text_pair(cls, source_text: str, translated_text: str) -> tuple[str, ...]:
        scan_issues = cls._scan_code_health(translated_text)
        if scan_issues:
            return tuple(f"静态检查: {item}" for item in scan_issues)

        source_profile = cls._structure_profile(source_text)
        translated_profile = cls._structure_profile(translated_text)
        issues: list[str] = []
        for token in ("if", "elseif", "else", "end", "act", "loop", "while"):
            if source_profile[token] != translated_profile[token]:
                issues.append(f"结构漂移: {token} source={source_profile[token]}, translated={translated_profile[token]}")

        if source_profile["if"] - source_profile["end"] != translated_profile["if"] - translated_profile["end"]:
            issues.append(
                "结构漂移: if/end 平衡 "
                f"source={source_profile['if'] - source_profile['end']}, "
                f"translated={translated_profile['if'] - translated_profile['end']}"
            )
        return tuple(issues)


    @classmethod
    def analyze_string_pair(cls, source_text: str, translated_text: str) -> tuple[str, ...]:
        issues: list[str] = []
        if cls._placeholder_signature(source_text) != cls._placeholder_signature(translated_text):
            issues.append("占位符数量或顺序发生变化")
        if cls._html_tag_signature(source_text) != cls._html_tag_signature(translated_text):
            issues.append("HTML 标签结构发生变化")
        return tuple(issues)

    @classmethod
    def analyze_line_pair(cls, source_line: str, translated_line: str) -> tuple[str, ...]:
        return cls.analyze_text_pair(source_line, translated_line)

    def collect_string_locked_texts(self, translated_texts: dict[Path, str]) -> tuple[set[Path], QsrcGuardStats]:
        stats = QsrcGuardStats(total_files=len(translated_texts))
        locked: set[Path] = set()

        with ProgressBar(total=len(translated_texts), enabled=self.show_progress, desc="String Check", unit="file") as progress:
            for relative_path, translated_text in translated_texts.items():
                source_path = self.source_root / relative_path
                if not source_path.exists():
                    locked.add(relative_path)
                    stats.locked_files += 1
                    progress.set_postfix_str(relative_path.name)
                    progress.update()
                    continue

                issues = self.analyze_string_pair(source_path.read_text(encoding="utf-8"), translated_text)
                stats.checked_files += 1
                if issues:
                    locked.add(relative_path)
                    stats.locked_files += 1
                    self._report_issue(
                        QsrcGuardIssue(
                            relative_path,
                            "?????????????????",
                            details=issues,
                        )
                    )
                progress.set_postfix_str(relative_path.name)
                progress.update()

        return locked, stats

    def collect_locked_files(self) -> tuple[set[Path], QsrcGuardStats]:
        files = FileManager.get_qsrc_scripts(self.translated_root)
        stats = QsrcGuardStats(total_files=len(files))
        locked: set[Path] = set()

        with ProgressBar(total=len(files), enabled=self.show_progress, desc="Guard Source", unit="file") as progress:
            for file in files:
                relative_path = Path(file.rel_path)
                issue = self._check_file(relative_path)
                stats.checked_files += 1
                if issue:
                    locked.add(relative_path)
                    stats.locked_files += 1
                    self._report_issue(issue)
                progress.set_postfix_str(file.path.name)
                progress.update()

        if stats.locked_files:
            logger.warning("构建前护栏已锁定 {} 个本地化 qsrc，打包时将回退为源文件。", stats.locked_files)
        else:
            logger.success("构建前护栏检查通过，未发现需要锁定的本地化 qsrc。")
        return locked, stats

    def _check_file(self, relative_path: Path) -> QsrcGuardIssue | None:
        source_path = self.source_root / relative_path
        translated_path = self.translated_root / relative_path
        if not source_path.exists():
            return QsrcGuardIssue(relative_path, "本地化文件找不到对应源文件，已锁定。")

        source_text = source_path.read_text(encoding="utf-8")
        translated_text = translated_path.read_text(encoding="utf-8")
        issues = self.analyze_text_pair(source_text, translated_text)
        if not issues:
            return None
        return QsrcGuardIssue(
            relative_path,
            "本地化文件与源文件的代码结构不一致，已锁定。",
            details=(*issues, *self._build_diff_details(source_text, translated_text, "source", "translated")),
        )

    def _report_issue(self, issue: QsrcGuardIssue) -> None:
        if not self.error_reporter:
            return
        self.error_reporter.report(
            "build-guard",
            issue.relative_path,
            issue.reason,
            details=issue.details,
            source_root=self.translated_root,
        )

    @staticmethod
    def _build_diff_details(source_text: str, translated_text: str, source_label: str, translated_label: str) -> tuple[str, ...]:
        diff_lines = tuple(
            unified_diff(
                source_text.splitlines(),
                translated_text.splitlines(),
                fromfile=source_label,
                tofile=translated_label,
                lineterm="",
                n=2,
            )
        )
        return diff_lines or ("# 文件内容无法生成有效 diff，但结构检查已失败。",)

    @classmethod
    def _structure_profile(cls, text: str) -> dict[str, int]:
        masked = cls._mask_non_code_regions(text)
        counts = {token: 0 for token in ("if", "elseif", "else", "end", "act", "loop", "while")}
        for match in TOKEN_PATTERN.finditer(masked):
            counts[match.group(1).casefold()] += 1
        return counts


    @staticmethod
    def _placeholder_signature(text: str) -> tuple[str, ...]:
        return tuple(match.group(1) for match in PLACEHOLDER_PATTERN.finditer(text))

    @staticmethod
    def _html_tag_signature(text: str) -> tuple[str, ...]:
        tags: list[str] = []
        stripped = PLACEHOLDER_PATTERN.sub("", text)
        for closing, name, self_closing in HTML_TAG_PATTERN.findall(stripped):
            normalized_name = name.casefold()
            if self_closing:
                tags.append(f"<{normalized_name}/>")
            elif closing:
                tags.append(f"</{normalized_name}>")
            else:
                tags.append(f"<{normalized_name}>")
        return tuple(tags)

    @staticmethod
    def _mask_non_code_regions(text: str) -> str:
        chars = list(text)
        index = 0
        quote: str | None = None
        in_line_comment = False
        in_block_comment = False

        while index < len(chars):
            char = chars[index]
            next_char = chars[index + 1] if index + 1 < len(chars) else ""

            if in_line_comment:
                if char == "\n":
                    in_line_comment = False
                else:
                    chars[index] = " "
                index += 1
                continue

            if in_block_comment:
                chars[index] = " "
                if char == "!" and next_char == "}":
                    chars[index + 1] = " "
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if quote:
                chars[index] = " "
                if char == quote:
                    if next_char == quote:
                        chars[index + 1] = " "
                        index += 2
                        continue
                    quote = None
                index += 1
                continue

            if char == "!" and next_char == "!":
                chars[index] = " "
                chars[index + 1] = " "
                in_line_comment = True
                index += 2
                continue

            if char == "{" and next_char == "!":
                chars[index] = " "
                chars[index + 1] = " "
                in_block_comment = True
                index += 2
                continue

            if char in ("'", '"'):
                chars[index] = " "
                quote = char
                index += 1
                continue

            index += 1

        return "".join(chars)

    @staticmethod
    def _scan_code_health(text: str) -> tuple[str, ...]:
        issues: list[str] = []
        index = 0
        line = 1
        quote: str | None = None
        quote_line: int | None = None
        in_line_comment = False
        in_block_comment = False
        block_comment_line: int | None = None

        while index < len(text):
            char = text[index]
            next_char = text[index + 1] if index + 1 < len(text) else ""

            if char == "\n":
                line += 1
                if in_line_comment:
                    in_line_comment = False
                index += 1
                continue

            if in_line_comment:
                index += 1
                continue

            if in_block_comment:
                if char == "!" and next_char == "}":
                    in_block_comment = False
                    block_comment_line = None
                    index += 2
                    continue
                index += 1
                continue

            if quote:
                if char == quote:
                    if next_char == quote:
                        index += 2
                        continue
                    quote = None
                    quote_line = None
                index += 1
                continue

            if char == "!" and next_char == "!":
                in_line_comment = True
                index += 2
                continue

            if char == "{" and next_char == "!":
                in_block_comment = True
                block_comment_line = line
                index += 2
                continue

            if char in ("'", '"'):
                quote = char
                quote_line = line
                index += 1
                continue

            index += 1

        if quote and quote_line is not None:
            issues.append(f"存在未闭合字符串，起始行 {quote_line}，引号 {quote}")
        if in_block_comment and block_comment_line is not None:
            issues.append(f"存在未闭合块注释，起始行 {block_comment_line}")
        return tuple(issues)


__all__ = ["QsrcBuildGuard", "QsrcGuardIssue", "QsrcGuardStats"]
