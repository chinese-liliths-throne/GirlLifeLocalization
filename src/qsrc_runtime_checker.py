from __future__ import annotations

from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

from src.core.error_reporting import ErrorReporter
from src.file_manager import FileManager
from src.core.logging import logger
from src.core.progress import ProgressBar
from src.qsrc import QsrcErrorCode, QsrcIssue, get_qsrc_validator
from src.qsrc.passes import compare_reference_texts


@dataclass(slots=True)
class QsrcRuntimeStats:
    total_files: int = 0
    syntax_error_count: int = 0
    checked_files: int = 0
    legal_files: int = 0
    locked_files: int = 0
    issue_counts: dict[str, int] = field(default_factory=dict)


class QsrcRuntimeChecker:
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

    def collect_locked_files(self) -> tuple[set[Path], QsrcRuntimeStats]:
        translated_texts = {
            Path(file.rel_path): file.path.read_text(encoding="utf-8")
            for file in FileManager.get_qsrc_scripts(self.translated_root)
        }
        return self.collect_locked_texts(translated_texts)

    def collect_locked_texts(self, translated_texts: dict[Path, str]) -> tuple[set[Path], QsrcRuntimeStats]:
        reference_locked, reference_stats = self.collect_reference_locked_texts(translated_texts)
        survivors = {path: text for path, text in translated_texts.items() if path not in reference_locked}
        syntax_locked, syntax_stats = self.collect_syntax_locked_texts(survivors)
        locked = reference_locked | syntax_locked
        stats = QsrcRuntimeStats(
            total_files=len(translated_texts),
            syntax_error_count=syntax_stats.syntax_error_count,
            checked_files=reference_stats.checked_files,
            legal_files=max(0, len(translated_texts) - len(locked)),
            locked_files=len(locked),
            issue_counts=dict(reference_stats.issue_counts),
        )
        self._log_summary(stats)
        return locked, stats

    def collect_reference_locked_texts(self, translated_texts: dict[Path, str]) -> tuple[set[Path], QsrcRuntimeStats]:
        stats = QsrcRuntimeStats(total_files=len(translated_texts))
        locked: set[Path] = set()
        with ProgressBar(total=len(translated_texts), enabled=self.show_progress, desc="Jump Check", unit="file") as progress:
            for relative_path, translated_text in translated_texts.items():
                source_path = self.source_root / relative_path
                issues: list[QsrcIssue]
                if not source_path.exists():
                    issues = [
                        QsrcIssue(
                            error_code=QsrcErrorCode.SOURCE_MISSING,
                            error_desc="本地化文件找不到对应的原版源文件。",
                            line=1,
                            location_name=relative_path.stem,
                            relative_path=relative_path,
                        )
                    ]
                else:
                    source_text = source_path.read_text(encoding="utf-8")
                    issues = compare_reference_texts(
                        source_text,
                        translated_text,
                        relative_path=relative_path,
                        fallback_name=relative_path.stem,
                    )
                stats.checked_files += 1
                blocking_issues = [issue for issue in issues if issue.severity == "error"]
                if blocking_issues:
                    locked.add(relative_path)
                    for issue in blocking_issues:
                        code = str(issue.error_code)
                        stats.issue_counts[code] = stats.issue_counts.get(code, 0) + 1
                        self._report_issue("runtime-check", issue, translated_text)
                progress.set_postfix_str(relative_path.name)
                progress.update()

        stats.locked_files = len(locked)
        stats.legal_files = max(0, stats.total_files - stats.locked_files)
        return locked, stats

    def collect_syntax_locked_texts(self, translated_texts: dict[Path, str]) -> tuple[set[Path], QsrcRuntimeStats]:
        stats = QsrcRuntimeStats(total_files=len(translated_texts))
        locked: set[Path] = set()
        with ProgressBar(total=len(translated_texts), enabled=self.show_progress, desc="Syntax Check", unit="file") as progress:
            for relative_path, text in translated_texts.items():
                syntax_issues = self._analyze_syntax_issues(relative_path, text)
                if syntax_issues:
                    stats.syntax_error_count += 1
                    locked.add(relative_path)
                    for issue in syntax_issues:
                        self._report_issue("runtime-syntax", issue, text)
                progress.set_postfix_str(relative_path.name)
                progress.update()
        stats.locked_files = len(locked)
        stats.legal_files = max(0, stats.total_files - stats.locked_files)
        return locked, stats

    def run(self) -> tuple[bool, QsrcRuntimeStats]:
        locked, stats = self.collect_locked_files()
        return (not locked and stats.syntax_error_count == 0), stats

    @classmethod
    def analyze_candidate_syntax(cls, text: str, *, location_name: str = "codex_runtime") -> tuple[str, ...]:
        validator = get_qsrc_validator()
        result = validator.validate_passage_text(text) if text.lstrip().startswith("#") else validator.validate_text(
            text,
            location_name=location_name,
        )
        if result.ok:
            return ()
        return tuple(issue.format_compact() for issue in result.issues if issue.severity == "error")

    @classmethod
    def analyze_line_references(cls, source_line: str, translated_line: str) -> tuple[str, ...]:
        issues = compare_reference_texts(source_line, translated_line, fallback_name="_line_")
        return tuple(issue.format_compact() for issue in issues if issue.severity == "error")

    @classmethod
    def analyze_multiline_references(cls, source_text: str, translated_text: str) -> tuple[str, ...]:
        issues = compare_reference_texts(source_text, translated_text, fallback_name="_block_")
        return tuple(issue.format_compact() for issue in issues if issue.severity == "error")

    def _analyze_syntax_issues(self, relative_path: Path, text: str) -> tuple[QsrcIssue, ...]:
        validator = get_qsrc_validator()
        result = validator.validate_passage_text(text)
        if result.ok:
            return ()
        return tuple(
            QsrcIssue(
                error_code=issue.error_code,
                error_desc=issue.error_desc,
                line=issue.line,
                column=issue.column,
                location_name=issue.location_name or relative_path.stem,
                act_index=issue.act_index,
                relative_path=relative_path,
                severity=issue.severity,
                details=issue.details,
                context_diff=issue.context_diff,
            )
            for issue in result.issues
            if issue.severity == "error"
        )

    def _report_issue(self, category: str, issue: QsrcIssue, translated_text: str) -> None:
        if not self.error_reporter or not issue.relative_path:
            return
        source_path = self.source_root / issue.relative_path
        source_text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        diff_lines = tuple(
            unified_diff(
                source_text.splitlines(),
                translated_text.splitlines(),
                fromfile="source",
                tofile="translated",
                lineterm="",
                n=2,
            )
        )
        self.error_reporter.report(
            category,
            issue.relative_path,
            issue.error_desc,
            details=(
                f"error_code: {issue.error_code}",
                f"location: {issue.location_name or issue.relative_path.stem}",
                f"line: {issue.line}",
                f"act_index: {issue.act_index}",
                *issue.details,
                *(diff_lines or ("# 无法生成 diff，但该文件未通过检查。",)),
            ),
            source_root=self.translated_root,
        )

    def _log_summary(self, stats: QsrcRuntimeStats) -> None:
        if stats.syntax_error_count:
            logger.warning("QSRC 运行检查发现 {} 个语法错误。", stats.syntax_error_count)
        if stats.locked_files:
            logger.warning(
                "QSRC 运行检查完成：总计 {}，合法 {}，锁定 {}。",
                stats.total_files,
                stats.legal_files,
                stats.locked_files,
            )
            if stats.issue_counts:
                rendered = ", ".join(f"{key}={value}" for key, value in sorted(stats.issue_counts.items()))
                logger.warning("QSRC 运行骨架问题分布：{}", rendered)
        else:
            logger.success("QSRC 运行检查通过：总计 {}，全部合法。", stats.total_files)


def test_qsrc_runtime(
    *,
    source_root: Path | str,
    translated_root: Path | str,
    show_progress: bool = False,
    error_reporter: ErrorReporter | None = None,
) -> tuple[bool, QsrcRuntimeStats]:
    checker = QsrcRuntimeChecker(
        source_root=source_root,
        translated_root=translated_root,
        error_reporter=error_reporter,
        show_progress=show_progress,
    )
    return checker.run()


__all__ = ["QsrcRuntimeChecker", "QsrcRuntimeStats", "test_qsrc_runtime"]
