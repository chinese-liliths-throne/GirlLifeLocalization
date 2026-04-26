from __future__ import annotations

import re
import shutil
from collections import Counter
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

import orjson

from src.error_reporter import ErrorReporter
from src.file_manager import FileManager, ParatranzDataFile
from src.log import logger
from src.model import ParatranzData, StageEnum
from src.paratranz_sync import QsrcLocalizationExtractor
from src.paths import detect_source_root, detect_translation_root, paths
from src.progress import ProgressBar


TRANSLATED_STAGES = frozenset({StageEnum(1), StageEnum(3), StageEnum(5)})
HTML_TAG_SIGNATURE_PATTERN = re.compile(r"<\s*(/)?\s*([A-Za-z0-9]+)(?:\s+[^>]*)?\s*(/?)>")
PLACEHOLDER_PATTERN = re.compile(r"(<<[^>]+>>|&lt;&lt;.*?&gt;&gt;)")


@dataclass(slots=True)
class PrecheckStats:
    files_total: int = 0
    files_written: int = 0
    entries_total: int = 0
    filtered_entries: int = 0
    symbol_blocked_entries: int = 0
    json_failed_files: int = 0
    mode: str = "fast"


class ParatranzPrechecker:
    def __init__(
        self,
        *,
        source_root: Path | str | None = None,
        paratranz_root: Path | str | None = None,
        output_root: Path | str | None = None,
        clear_output: bool = True,
        show_progress: bool = False,
        error_reporter: ErrorReporter | None = None,
        mode: str = "fast",
    ):
        self.source_root = Path(source_root).resolve() if source_root else detect_source_root()
        self.paratranz_root = Path(paratranz_root).resolve() if paratranz_root else detect_translation_root()
        if not self.paratranz_root:
            raise FileNotFoundError(f"未检测到 ParaTranz 目录: {paths.translation_parent}")

        default_output = paths.tmp / "prechecked_paratranz" / self.paratranz_root.name
        self.output_root = Path(output_root).resolve() if output_root else default_output.resolve()
        self.clear_output = clear_output
        self.show_progress = show_progress
        self.error_reporter = error_reporter
        self.extractor = QsrcLocalizationExtractor()
        self.mode = mode.casefold()

    def run(self) -> tuple[Path, PrecheckStats]:
        target = paths.ensure_inside_workspace(self.output_root)
        if self.clear_output:
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)

        files = FileManager.get_paratranz_data_files(self.paratranz_root)
        stats = PrecheckStats(files_total=len(files), mode=self.mode)
        logger.info("开始预检查 ParaTranz 词条: {} -> {}", self.paratranz_root, target)

        with ProgressBar(total=len(files), enabled=self.show_progress, desc="Precheck", unit="file") as progress:
            for data_file in files:
                self._process_file(data_file, target, stats)
                progress.set_postfix_str(data_file.path.name)
                progress.update()

        logger.success(
            "ParaTranz 预检查完成: 模式 {}，写入 {} 个文件, 过滤 {} 条, 符号拦截 {} 条, JSON 失败 {} 个",
            stats.mode,
            stats.files_written,
            stats.filtered_entries,
            stats.symbol_blocked_entries,
            stats.json_failed_files,
        )
        return target, stats

    def _process_file(self, data_file: ParatranzDataFile, target_root: Path, stats: PrecheckStats) -> None:
        try:
            entries = data_file.get_paratranz_data_list()
        except Exception as exc:
            stats.json_failed_files += 1
            self._report_json_error(
                data_file,
                "ParaTranz JSON 预检查读取失败。",
                details=(f"JSON 文件: {data_file.path}", f"异常: {exc}"),
            )
            return

        sanitized: list[ParatranzData] = []
        for entry in entries:
            stats.entries_total += 1

            filter_reason = self._classify_filter_reason(entry)
            if filter_reason:
                stats.filtered_entries += 1
                if entry.translation or entry.stage in TRANSLATED_STAGES:
                    self._report_filter_error(
                        data_file,
                        filter_reason,
                        entry,
                    )
                continue

            if self.mode in {"balanced", "strict"}:
                blocked_entry, report_details = self._sanitize_symbol_issue(entry)
                if report_details is not None:
                    stats.symbol_blocked_entries += 1
                    self._report_symbol_error(data_file, entry, report_details)
                    sanitized.append(blocked_entry)
                    continue

            sanitized.append(entry)

        relative = data_file.path.relative_to(self.paratranz_root)
        target_path = target_root / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in sanitized]
        target_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        stats.files_written += 1

    def _classify_filter_reason(self, entry: ParatranzData) -> str | None:
        original = (entry.original or "").strip()
        if not original:
            return None
        if not self.extractor.is_entry_extractable(entry):
            if self.extractor._looks_like_asset_path(original):
                return "原文仅为图片或媒体资源路径，已在预检查中过滤。"
            if self.extractor._is_media_only_markup(original):
                return "原文仅为 HTML 图片/媒体标签，已在预检查中过滤。"
            visible_text = self.extractor._extract_visible_text(original)
            if not visible_text:
                return "原文仅包含标签或占位内容，没有可翻译文本，已在预检查中过滤。"
            return "原文判定为不可翻译内容，已在预检查中过滤。"
        return None

    def _sanitize_symbol_issue(self, entry: ParatranzData) -> tuple[ParatranzData, tuple[str, ...] | None]:
        translation = entry.translation or ""
        if not translation or entry.stage not in TRANSLATED_STAGES:
            return entry, None

        issues = self._validate_symbol_integrity(entry.original or "", translation)
        if not issues:
            return entry, None

        blocked = entry.model_copy(update={"translation": "", "stage": StageEnum(0)})
        diff_lines = tuple(
            unified_diff(
                (entry.original or "").splitlines(),
                translation.splitlines(),
                fromfile="original",
                tofile="translation",
                lineterm="",
                n=2,
            )
        )
        details = (
            f"词条 key: {entry.key}",
            f"问题: {'; '.join(issues)}",
            f"原文: {entry.original}",
            f"译文: {translation}",
            *diff_lines,
        )
        return blocked, details

    def _validate_symbol_integrity(self, original: str, translation: str) -> list[str]:
        issues: list[str] = []

        if self._placeholder_signature(original) != self._placeholder_signature(translation):
            issues.append("占位符数量或顺序不一致")

        if self._html_tag_signature(original) != self._html_tag_signature(translation):
            issues.append("HTML 标签结构不一致")

        return issues

    @staticmethod
    def _placeholder_signature(text: str) -> tuple[str, ...]:
        tokens = [match.group(1) for match in PLACEHOLDER_PATTERN.finditer(text)]
        counts = Counter(tokens)
        return tuple(f"{key}*{counts[key]}" for key in sorted(counts))

    @staticmethod
    def _html_tag_signature(text: str) -> tuple[str, ...]:
        tags: list[str] = []
        stripped = PLACEHOLDER_PATTERN.sub("", text)
        for closing, name, self_closing in HTML_TAG_SIGNATURE_PATTERN.findall(stripped):
            normalized_name = name.casefold()
            if self_closing:
                tags.append(f"<{normalized_name}/>")
            elif closing:
                tags.append(f"</{normalized_name}>")
            else:
                tags.append(f"<{normalized_name}>")
        counts = Counter(tags)
        return tuple(f"{key}*{counts[key]}" for key in sorted(counts))

    @staticmethod
    def _looks_like_source_expression(text: str) -> bool:
        stripped = text.lstrip()
        if not stripped:
            return False
        if stripped.startswith(("'", '"')) and "+" in stripped:
            return True
        return any(token in text for token in ("iif(", "$func(", "$(", " arrsize(", " rand(", " + ", "'+", "+'"))

    @staticmethod
    def _code_structure_signature(text: str) -> tuple[int, int, int, int, int]:
        single_quotes = 0
        left_paren = 0
        right_paren = 0
        left_bracket = 0
        right_bracket = 0
        quote: str | None = None
        index = 0

        while index < len(text):
            char = text[index]
            if quote:
                if char == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
                index += 1
                continue

            if char not in ("'", '"'):
                if char == "(":
                    left_paren += 1
                elif char == ")":
                    right_paren += 1
                elif char == "[":
                    left_bracket += 1
                elif char == "]":
                    right_bracket += 1
                index += 1
                continue

            quote = char
            if char == "'":
                single_quotes += 1
            index += 1
        return (single_quotes, left_paren, right_paren, left_bracket, right_bracket)

    def _report_filter_error(self, data_file: ParatranzDataFile, message: str, entry: ParatranzData) -> None:
        if not self.error_reporter:
            return
        self.error_reporter.report(
            "precheck-filter",
            data_file.path,
            message,
            details=(
                f"词条 key: {entry.key}",
                f"原文: {entry.original}",
                f"译文: {entry.translation}",
            ),
            source_root=self.paratranz_root,
        )

    def _report_symbol_error(
        self,
        data_file: ParatranzDataFile,
        entry: ParatranzData,
        details: tuple[str, ...],
    ) -> None:
        if not self.error_reporter:
            return
        self.error_reporter.report(
            "precheck-symbol",
            data_file.path,
            "原文与译文的符号结构不一致，已在预检查副本中禁用该译文。",
            details=details,
            source_root=self.paratranz_root,
        )

    def _report_json_error(self, data_file: ParatranzDataFile, message: str, *, details: tuple[str, ...]) -> None:
        if not self.error_reporter:
            return
        self.error_reporter.report(
            "paratranz-json",
            data_file.path,
            message,
            details=details,
            source_root=self.paratranz_root,
        )


def precheck_paratranz(
    *,
    source_root: Path | str | None = None,
    paratranz_root: Path | str | None = None,
    output_root: Path | str | None = None,
    clear_output: bool = True,
    show_progress: bool = False,
    error_reporter: ErrorReporter | None = None,
    mode: str = "fast",
) -> tuple[Path, PrecheckStats]:
    checker = ParatranzPrechecker(
        source_root=source_root,
        paratranz_root=paratranz_root,
        output_root=output_root,
        clear_output=clear_output,
        show_progress=show_progress,
        error_reporter=error_reporter,
        mode=mode,
    )
    return checker.run()


__all__ = ["ParatranzPrechecker", "PrecheckStats", "precheck_paratranz"]
