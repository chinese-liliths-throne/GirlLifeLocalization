from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

from src.error_reporter import ErrorReporter
from src.file_manager import FileManager
from src.log import logger
from src.parser import get_antlr_validator
from src.progress import ProgressBar
from src.thirdparty.txt2gam import analyze_qsp_text


HEADER_PATTERN = re.compile(r"(?mi)^\s*#\s*([^\r\n]+?)\s*$")
VISIT_DEF_PATTERN = re.compile(
    r"""(?ix)
    \b(?:if|elseif)\s+
    \$args?\[0\]\s*=\s*
    (?P<quote>'|")
    (?P<value>(?:''|""|\\.|(?!\1).)*?)
    (?P=quote)
    """
)
CALL_PATTERN = re.compile(
    r"""(?ix)
    \b(?P<cmd>gt|gs|gosub|xgt|xgoto|goto|jump|visit)\s+
    (?P<loc>'(?:''|[^'])*'|"(?:\"\"|[^"])*"|''(?:[^']|'(?!'))*'')
    (?:\s*,\s*(?P<visit>'(?:''|[^'])*'|"(?:\"\"|[^"])*"|''(?:[^']|'(?!'))*''))?
    """
)


@dataclass(slots=True, frozen=True)
class RuntimeReference:
    command: str
    location: str
    visit: str | None = None


@dataclass(slots=True, frozen=True)
class LocatedReference:
    reference: RuntimeReference
    line_no: int
    line_text: str


@dataclass(slots=True, frozen=True)
class QsrcRuntimeSnapshot:
    location_name: str
    visits: frozenset[str]
    references: frozenset[RuntimeReference]
    visit_lines: dict[str, tuple[int, str]]
    reference_lines: dict[RuntimeReference, tuple[int, str]]


@dataclass(slots=True, frozen=True)
class QsrcRuntimeIssue:
    relative_path: Path
    error_code: str
    reason: str
    details: tuple[str, ...] = ()


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
        self._source_snapshots: dict[Path, QsrcRuntimeSnapshot] | None = None

    def collect_locked_files(self) -> tuple[set[Path], QsrcRuntimeStats]:
        translated_texts = {
            Path(file.rel_path): file.path.read_text(encoding="utf-8")
            for file in FileManager.get_qsrc_scripts(self.translated_root)
        }
        return self.collect_locked_texts(translated_texts)

    def collect_locked_texts(self, translated_texts: dict[Path, str]) -> tuple[set[Path], QsrcRuntimeStats]:
        reference_locked, reference_stats = self.collect_reference_locked_texts(translated_texts)
        survivors = {
            relative_path: text
            for relative_path, text in translated_texts.items()
            if relative_path not in reference_locked
        }
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

        source_snapshots = self._get_source_snapshots()
        with ProgressBar(total=len(translated_texts), enabled=self.show_progress, desc="Jump Check", unit="file") as progress:
            for relative_path, translated_text in translated_texts.items():
                issue = self._check_text(relative_path, translated_text, source_snapshots)
                stats.checked_files += 1
                if issue:
                    locked.add(relative_path)
                    stats.issue_counts[issue.error_code] = stats.issue_counts.get(issue.error_code, 0) + 1
                    self._report_issue(issue)
                progress.set_postfix_str(relative_path.name)
                progress.update()

        stats.locked_files = len(locked)
        stats.legal_files = max(0, stats.total_files - stats.locked_files)
        return locked, stats

    def collect_syntax_locked_texts(self, translated_texts: dict[Path, str]) -> tuple[set[Path], QsrcRuntimeStats]:
        stats = QsrcRuntimeStats(total_files=len(translated_texts))
        locked: set[Path] = set()
        antlr_validator = get_antlr_validator()

        with ProgressBar(total=len(translated_texts), enabled=self.show_progress, desc="Closure Check", unit="file") as progress:
            for relative_path, text in translated_texts.items():
                syntax_errors = self._analyze_syntax_errors(relative_path, text, antlr_validator=antlr_validator)
                if syntax_errors:
                    stats.syntax_error_count += 1
                    locked.add(relative_path)
                    source_path = self.source_root / relative_path
                    if self.error_reporter and source_path.exists():
                        source_text = source_path.read_text(encoding="utf-8")
                        diff_lines = tuple(
                            unified_diff(
                                source_text.splitlines(),
                                text.splitlines(),
                                fromfile="source",
                                tofile="translated",
                                lineterm="",
                                n=2,
                            )
                        )
                        self.error_reporter.report(
                            "runtime-syntax",
                            relative_path,
                            "运行语法检查失败，附加原文与替换结果对比。",
                            details=(
                                *syntax_errors,
                                *(diff_lines or ("# 无法生成 diff，但该文件未通过运行语法检查。",)),
                            ),
                            source_root=self.translated_root,
                        )
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
        antlr_validator = get_antlr_validator()
        if antlr_validator is None:
            return ()
        if text.lstrip().startswith("#"):
            result = antlr_validator.validate_passage_text(text)
        else:
            result = antlr_validator.validate_text(text, location_name=location_name)
        if result.ok:
            return ()
        return tuple(f"ANTLR 语法错误: {item}" for item in result.errors)

    @classmethod
    def analyze_line_references(cls, source_line: str, translated_line: str) -> tuple[str, ...]:
        source_snapshot = cls._snapshot(source_line, fallback_name="_line_")
        translated_snapshot = cls._snapshot(translated_line, fallback_name="_line_")
        issues: list[str] = []
        if source_snapshot.visits != translated_snapshot.visits:
            issues.append(
                f"visit 漂移: source={sorted(source_snapshot.visits)}, translated={sorted(translated_snapshot.visits)}"
            )
        if source_snapshot.references != translated_snapshot.references:
            issues.append(
                "跳转漂移: "
                f"source={sorted(source_snapshot.references, key=cls._reference_sort_key)}, "
                f"translated={sorted(translated_snapshot.references, key=cls._reference_sort_key)}"
            )
        return tuple(issues)

    @classmethod
    def analyze_multiline_references(cls, source_text: str, translated_text: str) -> tuple[str, ...]:
        source_snapshot = cls._snapshot(source_text, fallback_name="_block_")
        translated_snapshot = cls._snapshot(translated_text, fallback_name="_block_")
        issues: list[str] = []
        if source_snapshot.visits != translated_snapshot.visits:
            issues.append(
                f"visit 漂移: source={sorted(source_snapshot.visits)}, translated={sorted(translated_snapshot.visits)}"
            )
        if source_snapshot.references != translated_snapshot.references:
            issues.append(
                "跳转漂移: "
                f"source={sorted(source_snapshot.references, key=cls._reference_sort_key)}, "
                f"translated={sorted(translated_snapshot.references, key=cls._reference_sort_key)}"
            )
        return tuple(issues)

    def _get_source_snapshots(self) -> dict[Path, QsrcRuntimeSnapshot]:
        if self._source_snapshots is None:
            self._source_snapshots = self._collect_snapshots(self.source_root)
        return self._source_snapshots

    def _analyze_syntax_errors(self, relative_path: Path, text: str, *, antlr_validator) -> tuple[str, ...]:
        if antlr_validator is not None:
            result = antlr_validator.validate_passage_text(text)
            if result.ok:
                return ()
            return tuple(f"ANTLR 语法错误: {item}" for item in result.errors)

        result = analyze_qsp_text(
            text,
            filename=str(self.translated_root / relative_path),
            error_reporter=self.error_reporter,
            error_category="runtime-syntax",
            source_root=str(self.translated_root),
            verbose=False,
        )
        if result.ok:
            return ()
        return ("txt2gam 静态检查失败。",)

    def _collect_snapshots(self, root: Path) -> dict[Path, QsrcRuntimeSnapshot]:
        snapshots: dict[Path, QsrcRuntimeSnapshot] = {}
        for file in FileManager.get_qsrc_scripts(root):
            relative_path = Path(file.rel_path)
            snapshots[relative_path] = self._snapshot(file.path.read_text(encoding="utf-8"), fallback_name=file.path.stem)
        return snapshots

    def _check_file(self, relative_path: Path, source_snapshots: dict[Path, QsrcRuntimeSnapshot]) -> QsrcRuntimeIssue | None:
        source_snapshot = source_snapshots.get(relative_path)
        if source_snapshot is None:
            return QsrcRuntimeIssue(
                relative_path=relative_path,
                error_code="SOURCE_MISSING",
                reason="本地化文件找不到对应的原版源码文件，已锁定。",
            )

        translated_path = self.translated_root / relative_path
        translated_text = translated_path.read_text(encoding="utf-8")
        return self._check_text(relative_path, translated_text, source_snapshots)

    def _check_text(
        self,
        relative_path: Path,
        translated_text: str,
        source_snapshots: dict[Path, QsrcRuntimeSnapshot],
    ) -> QsrcRuntimeIssue | None:
        source_snapshot = source_snapshots.get(relative_path)
        if source_snapshot is None:
            return QsrcRuntimeIssue(
                relative_path=relative_path,
                error_code="SOURCE_MISSING",
                reason="本地化文件找不到对应的原版源码文件，已锁定。",
            )

        translated_snapshot = self._snapshot(translated_text, fallback_name=relative_path.stem)

        location_issue = self._build_location_issue(relative_path, source_snapshot, translated_snapshot)
        if location_issue:
            return location_issue

        visit_issue = self._build_visit_issue(relative_path, source_snapshot, translated_snapshot, translated_text)
        if visit_issue:
            return visit_issue

        reference_issue = self._build_reference_issue(relative_path, source_snapshot, translated_snapshot, translated_text)
        if reference_issue:
            return reference_issue

        return None

    def _build_location_issue(
        self,
        relative_path: Path,
        source_snapshot: QsrcRuntimeSnapshot,
        translated_snapshot: QsrcRuntimeSnapshot,
    ) -> QsrcRuntimeIssue | None:
        if translated_snapshot.location_name == source_snapshot.location_name:
            return None
        return QsrcRuntimeIssue(
            relative_path=relative_path,
            error_code="LOCATION_NAME_DRIFT",
            reason="location 名称与原版源码不一致，运行入口可能失效。",
            details=(
                f"原版 location: {source_snapshot.location_name}",
                f"本地化 location: {translated_snapshot.location_name}",
            ),
        )

    def _build_visit_issue(
        self,
        relative_path: Path,
        source_snapshot: QsrcRuntimeSnapshot,
        translated_snapshot: QsrcRuntimeSnapshot,
        translated_text: str,
    ) -> QsrcRuntimeIssue | None:
        missing_visits = sorted(source_snapshot.visits - translated_snapshot.visits)
        added_visits = sorted(translated_snapshot.visits - source_snapshot.visits)
        if not missing_visits and not added_visits:
            return None

        details: list[str] = []
        if missing_visits:
            details.append(f"缺失的 visit: {', '.join(missing_visits[:20])}")
            details.extend(self._format_visit_lines("原版", source_snapshot.visit_lines, missing_visits))
        if added_visits:
            details.append(f"异常新增的 visit: {', '.join(added_visits[:20])}")
            details.extend(self._format_visit_lines("本地化", translated_snapshot.visit_lines, added_visits))
        details.extend(self._build_file_diff(relative_path))
        return QsrcRuntimeIssue(
            relative_path=relative_path,
            error_code="VISIT_DRIFT",
            reason="visit 定义与原版源码不一致，可能导致 gt/gs 进入错误分支。",
            details=tuple(details),
        )

    def _build_reference_issue(
        self,
        relative_path: Path,
        source_snapshot: QsrcRuntimeSnapshot,
        translated_snapshot: QsrcRuntimeSnapshot,
        translated_text: str,
    ) -> QsrcRuntimeIssue | None:
        missing_refs = sorted(source_snapshot.references - translated_snapshot.references, key=self._reference_sort_key)
        added_refs = sorted(translated_snapshot.references - source_snapshot.references, key=self._reference_sort_key)
        if not missing_refs and not added_refs:
            return None

        details: list[str] = []
        if missing_refs:
            details.append("缺失的静态跳转骨架:")
            details.extend(self._format_reference_lines("原版", source_snapshot.reference_lines, missing_refs))
        if added_refs:
            details.append("异常新增的静态跳转骨架:")
            details.extend(self._format_reference_lines("本地化", translated_snapshot.reference_lines, added_refs))
        details.extend(self._build_file_diff(relative_path))
        return QsrcRuntimeIssue(
            relative_path=relative_path,
            error_code="REFERENCE_DRIFT",
            reason="静态跳转骨架与原版源码不一致，可能导致 location 或 visit 跳转失效。",
            details=tuple(details),
        )

    @staticmethod
    def _snapshot(text: str, *, fallback_name: str) -> QsrcRuntimeSnapshot:
        header_match = HEADER_PATTERN.search(text)
        location_name = (header_match.group(1).strip() if header_match else fallback_name).strip()

        visits: set[str] = set()
        visit_lines: dict[str, tuple[int, str]] = {}
        references: set[RuntimeReference] = set()
        reference_lines: dict[RuntimeReference, tuple[int, str]] = {}

        for line_no, line_text in enumerate(text.splitlines(), start=1):
            code_mask = QsrcRuntimeChecker._build_code_mask(line_text)
            for match in VISIT_DEF_PATTERN.finditer(line_text):
                if not QsrcRuntimeChecker._is_code_match(code_mask, match.start()):
                    continue
                visit = QsrcRuntimeChecker._decode_quoted(match.group("value"), match.group("quote"))
                visits.add(visit)
                visit_lines.setdefault(visit, (line_no, line_text.rstrip()))

            for match in CALL_PATTERN.finditer(line_text):
                if not QsrcRuntimeChecker._is_code_match(code_mask, match.start()):
                    continue
                reference = RuntimeReference(
                    command=match.group("cmd").casefold(),
                    location=QsrcRuntimeChecker._decode_literal(match.group("loc")),
                    visit=QsrcRuntimeChecker._decode_literal(match.group("visit")) if match.group("visit") else None,
                )
                references.add(reference)
                reference_lines.setdefault(reference, (line_no, line_text.rstrip()))

        return QsrcRuntimeSnapshot(
            location_name=location_name,
            visits=frozenset(visits),
            references=frozenset(references),
            visit_lines=visit_lines,
            reference_lines=reference_lines,
        )

    def _report_issue(self, issue: QsrcRuntimeIssue) -> None:
        if not self.error_reporter:
            return
        self.error_reporter.report(
            "runtime-check",
            issue.relative_path,
            issue.reason,
            details=(f"错误代码: {issue.error_code}", *issue.details),
            source_root=self.translated_root,
        )

    def _log_summary(self, stats: QsrcRuntimeStats) -> None:
        if stats.syntax_error_count:
            logger.warning("QSRC 运行测试发现 {} 个语法错误。", stats.syntax_error_count)
        if stats.locked_files:
            logger.warning(
                "QSRC 运行测试完成：总计 {}，合法 {}，锁定 {}。",
                stats.total_files,
                stats.legal_files,
                stats.locked_files,
            )
            if stats.issue_counts:
                rendered = ", ".join(f"{key}={value}" for key, value in sorted(stats.issue_counts.items()))
                logger.warning("QSRC 运行骨架问题分布：{}", rendered)
        else:
            logger.success("QSRC 运行测试通过：总计 {}，全部合法。", stats.total_files)

    def _build_file_diff(self, relative_path: Path) -> tuple[str, ...]:
        source_path = self.source_root / relative_path
        translated_path = self.translated_root / relative_path
        source_text = source_path.read_text(encoding="utf-8")
        translated_text = translated_path.read_text(encoding="utf-8")
        return tuple(
            unified_diff(
                source_text.splitlines(),
                translated_text.splitlines(),
                fromfile="source",
                tofile="translated",
                lineterm="",
                n=2,
            )
        )

    @staticmethod
    def _decode_literal(raw: str | None) -> str:
        if not raw:
            return ""
        value = raw.strip()
        if value.startswith("''") and value.endswith("''") and len(value) >= 4:
            inner = value[2:-2]
            return inner.replace("''''", "''")
        if value[0] == value[-1] and value[0] in ("'", '"'):
            return QsrcRuntimeChecker._decode_quoted(value[1:-1], value[0])
        return value

    @staticmethod
    def _decode_quoted(value: str, quote: str) -> str:
        return value.replace(quote * 2, quote)

    @staticmethod
    def _build_code_mask(line: str) -> list[bool]:
        mask = [True] * len(line)
        quote: str | None = None
        index = 0
        while index < len(line):
            char = line[index]
            next_char = line[index + 1] if index + 1 < len(line) else ""

            if quote:
                mask[index] = False
                if char == quote:
                    if next_char == quote:
                        mask[index + 1] = False
                        index += 2
                        continue
                    quote = None
                index += 1
                continue

            if char == "!" and next_char == "!":
                for pos in range(index, len(line)):
                    mask[pos] = False
                break

            if char in ("'", '"'):
                mask[index] = False
                quote = char
                index += 1
                continue

            index += 1
        return mask

    @staticmethod
    def _is_code_match(mask: list[bool], start: int) -> bool:
        return 0 <= start < len(mask) and mask[start]

    @staticmethod
    def _reference_sort_key(reference: RuntimeReference) -> tuple[str, str, str]:
        return (reference.command, reference.location, reference.visit or "")

    @staticmethod
    def _format_visit_lines(prefix: str, visit_lines: dict[str, tuple[int, str]], visits: list[str]) -> tuple[str, ...]:
        lines: list[str] = []
        for visit in visits[:12]:
            line_no, line_text = visit_lines.get(visit, (-1, ""))
            if line_no > 0:
                lines.append(f"{prefix} 第 {line_no} 行 visit: {visit}")
                lines.append(f"{prefix} 代码: {line_text}")
            else:
                lines.append(f"{prefix} visit: {visit}")
        return tuple(lines)

    @staticmethod
    def _format_reference_lines(
        prefix: str,
        reference_lines: dict[RuntimeReference, tuple[int, str]],
        references: list[RuntimeReference],
    ) -> tuple[str, ...]:
        lines: list[str] = []
        for reference in references[:12]:
            line_no, line_text = reference_lines.get(reference, (-1, ""))
            label = f"{reference.command} {reference.location}" + (f", {reference.visit}" if reference.visit else "")
            if line_no > 0:
                lines.append(f"{prefix} 第 {line_no} 行跳转: {label}")
                lines.append(f"{prefix} 代码: {line_text}")
            else:
                lines.append(f"{prefix} 跳转: {label}")
        if len(references) > 12:
            lines.append(f"... 其余 {len(references) - 12} 条已省略")
        return tuple(lines)


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
