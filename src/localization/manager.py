import asyncio
import ctypes
import gc
import re
import shutil
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

import aiofiles

from src.config.error_reporting import ErrorReporter
from src.storage.files import FileManager, ParatranzDataFile
from src.config.logging import logger
from src.models import StageEnum
from src.config.paths import detect_source_root, detect_translation_root, paths
from src.config.progress import ProgressBar
from src.runtime.guard import QsrcBuildGuard
from src.runtime.qsrc_checker import QsrcRuntimeChecker, QsrcRuntimeStats


LOGGER_COLOR = logger.opt(colors=True)
TEMPLATE_EXPR_PATTERN = re.compile(r"\{\{expr_(\d+)\}\}")
CODE_TOKEN_PATTERN = re.compile(r"(?:\$?[A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]\r\n]+\])?")
TRANSLATED_STAGES = frozenset({StageEnum(1), StageEnum(3), StageEnum(5)})
CHECKPOINT_INTERVAL = 64
DEFAULT_MEMORY_BUDGET = 512 * 1024 * 1024
MIN_MEMORY_BUDGET = 128 * 1024 * 1024
MAX_MEMORY_BUDGET = 768 * 1024 * 1024
MIN_USER_MEMORY_BUDGET = 64 * 1024 * 1024


@dataclass(slots=True)
class TranslationStats:
    total_files: int = 0
    translated: int = 0
    failed: int = 0
    missing_source: int = 0
    skipped_entries: int = 0

    def add(self, other: "TranslationStats") -> None:
        self.total_files += other.total_files
        self.translated += other.translated
        self.failed += other.failed
        self.missing_source += other.missing_source
        self.skipped_entries += other.skipped_entries


@dataclass(slots=True)
class ApplyState:
    text: str
    offset: int
    applied_entries: int = 0


@dataclass(slots=True)
class TranslationArtifact:
    relative_path: Path
    text: str
    stats: TranslationStats


def _find_text_in_window(source: str, target: str, start: int, end: int) -> tuple[int, int, str]:
    if not target:
        return -1, 0, "empty-target"

    real_pos = source.find(target, start, end)
    if real_pos != -1:
        return real_pos, len(target), "exact"

    if "\n" in target:
        crlf_target = target.replace("\n", "\r\n")
        real_pos = source.find(crlf_target, start, end)
        if real_pos != -1:
            return real_pos, len(crlf_target), "crlf"

    return -1, len(target), "not-found"


def _is_case_only_change(source_text: str, original_text: str) -> bool:
    return bool(source_text) and source_text != original_text and source_text.casefold() == original_text.casefold()


def _nearby_preview(text: str, position: int, length: int, radius: int = 80) -> str:
    start = max(0, position - radius)
    end = min(len(text), position + max(length, 1) + radius)
    return text[start:end].replace("\r", "\\r").replace("\n", "\\n")


def _line_bounds(text: str, position: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, max(0, position)) + 1
    end = text.find("\n", max(0, position))
    if end == -1:
        end = len(text)
    return start, end


def _extract_code_tokens(line: str) -> tuple[str, ...]:
    masked = QsrcBuildGuard._mask_non_code_regions(line)
    return tuple(token.casefold() for token in CODE_TOKEN_PATTERN.findall(masked))


def _line_has_unclosed_quote(line: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        next_char = line[index + 1] if index + 1 < len(line) else ""
        if quote:
            if char == quote:
                if next_char == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char == "!" and next_char == "!":
            break
        if char in ("'", '"'):
            quote = char
        index += 1
    return quote is not None


def _analyze_line_candidate(source_line: str, candidate_line: str) -> tuple[str, ...]:
    issues: list[str] = []
    if _extract_code_tokens(source_line) != _extract_code_tokens(candidate_line):
        issues.append("当前行代码变量或调用签名发生变化")
    if _line_has_unclosed_quote(candidate_line):
        issues.append("当前行存在未闭合字符串")
    return tuple(issues)


def _render_context_diff(expected: str, actual: str, *, expected_label: str, actual_label: str) -> tuple[str, ...]:
    diff_lines = tuple(
        unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=expected_label,
            tofile=actual_label,
            lineterm="",
            n=2,
        )
    )
    if diff_lines:
        return diff_lines
    if expected == actual:
        return ("(diff) ?????????",)
    return (
        f"--- {expected_label}",
        f"+++ {actual_label}",
        f"- {expected}",
        f"+ {actual}",
    )


def _escape_qsp_string(text: str) -> str:
    return text.replace("'", "''")


def _append_template_text(parts: list[str], text: str) -> None:
    if text:
        parts.append(f"'{_escape_qsp_string(text)}'")


def _rebuild_placeholder_template_expression(translation: str, expressions: list[str]) -> str | None:
    parts: list[str] = []
    cursor = 0
    for match in TEMPLATE_EXPR_PATTERN.finditer(translation):
        _append_template_text(parts, translation[cursor:match.start()])
        expr_index = int(match.group(1)) - 1
        if expr_index < 0 or expr_index >= len(expressions):
            return None
        expression = expressions[expr_index].strip()
        if not expression:
            return None
        parts.append(expression)
        cursor = match.end()
    _append_template_text(parts, translation[cursor:])
    return " + ".join(parts) if parts else "''"


def _rebuild_inline_template_expression(translation: str, expressions: list[str]) -> str | None:
    parts: list[str] = []
    cursor = 0
    for expression in expressions:
        expr_text = str(expression).strip()
        if not expr_text:
            return None
        expr_pos = translation.find(expr_text, cursor)
        if expr_pos == -1:
            return None
        _append_template_text(parts, translation[cursor:expr_pos])
        parts.append(expr_text)
        cursor = expr_pos + len(expr_text)
    _append_template_text(parts, translation[cursor:])
    return " + ".join(parts) if parts else "''"


def _rebuild_template_expression(translation: str, expressions: list[str]) -> str | None:
    if TEMPLATE_EXPR_PATTERN.search(translation):
        return _rebuild_placeholder_template_expression(translation, expressions)
    if translation.lstrip().startswith(("'", '"')) and "+" in translation:
        return translation
    return _rebuild_inline_template_expression(translation, expressions)


class LocalizationManager:
    def __init__(
        self,
        source_dir: Path | str | None = None,
        paratranz_dir: Path | str | None = None,
        result_dir: Path | str | None = None,
        *,
        clear_result: bool = True,
        copy_source: bool = False,
        concurrency: int = 32,
        show_progress: bool = False,
        error_reporter: ErrorReporter | None = None,
        memory_limit_mb: int | None = None,
    ):
        self.source_dir = Path(source_dir).resolve() if source_dir else detect_source_root()
        self.paratranz_dir = Path(paratranz_dir).resolve() if paratranz_dir else detect_translation_root()
        self.result_dir = Path(result_dir).resolve() if result_dir else paths.result.resolve()
        self.copy_source = copy_source
        self.concurrency = max(1, concurrency)
        self.show_progress = show_progress
        self.error_reporter = error_reporter
        self.memory_limit_mb = memory_limit_mb

        if clear_result:
            self._prepare_result_dir()
        else:
            self.result_dir.mkdir(parents=True, exist_ok=True)

        if not self.source_dir:
            LOGGER_COLOR.warning("未检测到源码目录: {}", paths.source_parent)
        if not self.paratranz_dir:
            LOGGER_COLOR.warning("未检测到 ParaTranz 目录: {}", paths.translation_parent)

        self.raw_paratranz = FileManager.get_paratranz_data_files(self.paratranz_dir) if self.paratranz_dir else []

    def translate(self) -> TranslationStats:
        return asyncio.run(self.translate_all())

    async def translate_all(self) -> TranslationStats:
        LOGGER_COLOR.info("Start localization batch pipeline...")
        stats = TranslationStats(total_files=len(self.raw_paratranz))

        if not self.raw_paratranz:
            LOGGER_COLOR.warning("No ParaTranz files to process.")
            return stats
        if not self.source_dir:
            stats.failed = len(self.raw_paratranz)
            stats.missing_source = len(self.raw_paratranz)
            LOGGER_COLOR.error("Source directory is missing; cannot apply translations.")
            return stats

        stats = TranslationStats()
        semaphore = asyncio.Semaphore(self.concurrency)
        memory_budget = self._detect_memory_budget_bytes()
        batches = self._build_translation_batches(memory_budget)
        runtime_checker = QsrcRuntimeChecker(
            source_root=self.source_dir,
            translated_root=self.result_dir,
            error_reporter=self.error_reporter,
            show_progress=self.show_progress,
        )
        total_runtime_files = 0
        total_runtime_legal = 0
        total_runtime_locked = 0
        total_runtime_syntax = 0

        with ProgressBar(total=len(self.raw_paratranz), enabled=self.show_progress, desc="Replace", unit="file") as progress:
            for batch_index, batch_files in enumerate(batches, start=1):
                if self.error_reporter:
                    self.error_reporter.begin_buffering()

                source_cache: dict[Path, str] = {}
                translated_texts: dict[Path, str] = {}
                try:
                    source_cache = self._load_source_cache(
                        batch_files,
                        batch_index=batch_index,
                        batch_total=len(batches),
                    )

                    async def run_one(paratranz_file: ParatranzDataFile) -> tuple[str, TranslationArtifact]:
                        async with semaphore:
                            localization = Localization(
                                paratranz_file,
                                source_dir=self.source_dir,
                                result_dir=self.result_dir,
                                source_cache=source_cache,
                                paratranz_root=self.paratranz_dir,
                                error_reporter=self.error_reporter,
                            )
                            artifact = await asyncio.to_thread(localization.translate)
                            return paratranz_file.path.name, artifact

                    tasks = [asyncio.create_task(run_one(file)) for file in batch_files]
                    for task in asyncio.as_completed(tasks):
                        filename, artifact = await task
                        stats.add(artifact.stats)
                        if artifact.relative_path and (artifact.text or artifact.relative_path in source_cache):
                            translated_texts[artifact.relative_path] = artifact.text or source_cache.get(artifact.relative_path, "")
                        progress.set_postfix_str(
                            f"{batch_index}/{len(batches)} {filename} | {self._format_memory_status(memory_budget)}"
                        )
                        progress.update()

                    texts_to_validate = {
                        relative_path: text
                        for relative_path, text in translated_texts.items()
                        if source_cache.get(relative_path) != text
                    }
                    if texts_to_validate:
                        runtime_locked, runtime_stats = runtime_checker.collect_reference_locked_texts(texts_to_validate)
                        syntax_candidates = {
                            relative_path: text
                            for relative_path, text in texts_to_validate.items()
                            if relative_path not in runtime_locked
                        }
                        syntax_locked, syntax_stats = runtime_checker.collect_syntax_locked_texts(syntax_candidates)
                        locked_files = runtime_locked | syntax_locked
                        runtime_stats.syntax_error_count = syntax_stats.syntax_error_count
                        runtime_stats.locked_files = len(locked_files)
                        runtime_stats.legal_files = max(0, runtime_stats.total_files - runtime_stats.locked_files)
                        for relative_path in locked_files:
                            if relative_path in source_cache:
                                translated_texts[relative_path] = source_cache[relative_path]
                    else:
                        runtime_stats = QsrcRuntimeStats(total_files=0)

                    self._run_memory_gc(f"batch {batch_index} before export")
                    await self._write_artifacts(
                        translated_texts,
                        batch_index=batch_index,
                        batch_total=len(batches),
                    )
                    if self.error_reporter:
                        self.error_reporter.flush_buffer()
                except Exception:
                    if self.error_reporter:
                        self.error_reporter.discard_buffer()
                    raise
                finally:
                    translated_texts.clear()
                    source_cache.clear()
                    self._run_memory_gc(f"batch {batch_index} after export")

                total_runtime_files += runtime_stats.total_files
                total_runtime_legal += runtime_stats.legal_files
                total_runtime_locked += runtime_stats.locked_files
                total_runtime_syntax += runtime_stats.syntax_error_count

        LOGGER_COLOR.info(
            "In-memory validation finished: checked {}, legal {}, rolled back {}, syntax errors {}",
            total_runtime_files,
            total_runtime_legal,
            total_runtime_locked,
            total_runtime_syntax,
        )
        LOGGER_COLOR.success(
            "Localization finished: success {} / failed {} / skipped entries {}",
            stats.translated,
            stats.failed,
            stats.skipped_entries,
        )
        return stats

    def _load_source_cache(
        self,
        batch_files: list[ParatranzDataFile],
        *,
        batch_index: int,
        batch_total: int,
    ) -> dict[Path, str]:
        cache: dict[Path, str] = {}
        seen: set[Path] = set()
        files: list[tuple[Path, Path]] = []
        for paratranz_file in batch_files:
            relative_path = Path(str(paratranz_file.relative_path_no_ext)).with_suffix(".qsrc")
            if relative_path in seen:
                continue
            seen.add(relative_path)
            files.append((relative_path, self.source_dir / relative_path))

        with ProgressBar(
            total=len(files),
            enabled=self.show_progress,
            desc=f"Cache Source {batch_index}/{batch_total}",
            unit="file",
        ) as progress:
            for relative_path, source_path in files:
                if source_path.exists():
                    cache[relative_path] = source_path.read_text(encoding="utf-8")
                progress.set_postfix_str(relative_path.name)
                progress.update()
        LOGGER_COLOR.info("第三步第 {} 批已缓存原版源码 {} 个 qsrc 到内存。", batch_index, len(cache))
        return cache

    async def _write_artifacts(self, translated_texts: dict[Path, str], *, batch_index: int, batch_total: int) -> None:
        items = sorted(translated_texts.items(), key=lambda item: item[0].as_posix())
        with ProgressBar(
            total=len(items),
            enabled=self.show_progress,
            desc=f"Save Result {batch_index}/{batch_total}",
            unit="file",
        ) as progress:
            for relative_path, text in items:
                target_path = self.result_dir / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(target_path, "w", encoding="utf-8", newline="") as handle:
                    await handle.write(text)
                progress.set_postfix_str(relative_path.name)
                progress.update()

    def _build_translation_batches(self, memory_budget: int) -> list[list[ParatranzDataFile]]:
        batches: list[list[ParatranzDataFile]] = []
        current_batch: list[ParatranzDataFile] = []
        current_size = 0

        for paratranz_file in self.raw_paratranz:
            relative_path = Path(str(paratranz_file.relative_path_no_ext)).with_suffix(".qsrc")
            source_path = self.source_dir / relative_path
            source_size = source_path.stat().st_size if source_path.exists() else 64 * 1024
            estimated_cost = max(source_size * 3, 64 * 1024)

            if current_batch and current_size + estimated_cost > memory_budget:
                batches.append(current_batch)
                current_batch = []
                current_size = 0

            current_batch.append(paratranz_file)
            current_size += estimated_cost

        if current_batch:
            batches.append(current_batch)

        LOGGER_COLOR.info(
            "Batched translation plan: {} batch(es), target {:.1f} MB each",
            len(batches),
            memory_budget / 1024 / 1024,
        )
        return batches

    def _detect_memory_budget_bytes(self) -> int:
        total_memory = DEFAULT_MEMORY_BUDGET
        available_memory = DEFAULT_MEMORY_BUDGET
        try:
            if hasattr(ctypes, "windll"):
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                memory_status = MEMORYSTATUSEX()
                memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
                    total_memory = int(memory_status.ullTotalPhys)
                    available_memory = int(memory_status.ullAvailPhys)
        except Exception:
            total_memory = DEFAULT_MEMORY_BUDGET
            available_memory = DEFAULT_MEMORY_BUDGET

        auto_budget = min(int(total_memory * 0.12), int(available_memory * 0.35), MAX_MEMORY_BUDGET)
        if self.memory_limit_mb is not None:
            requested = max(MIN_USER_MEMORY_BUDGET, self.memory_limit_mb * 1024 * 1024)
            budget = min(requested, max(MIN_USER_MEMORY_BUDGET, int(available_memory * 0.5)))
        else:
            budget = auto_budget

        budget = max(MIN_USER_MEMORY_BUDGET, budget)
        LOGGER_COLOR.info(
            "Memory budget: {:.1f} MB / available {:.1f} MB / total {:.1f} MB",
            budget / 1024 / 1024,
            available_memory / 1024 / 1024,
            total_memory / 1024 / 1024,
        )
        return budget

    def _run_memory_gc(self, phase: str) -> None:
        collected = gc.collect()
        LOGGER_COLOR.info("第三步{}已执行 GC，回收对象 {}", phase, collected)

    def _get_memory_status(self) -> tuple[int, int]:
        total_memory = DEFAULT_MEMORY_BUDGET
        available_memory = DEFAULT_MEMORY_BUDGET
        try:
            if hasattr(ctypes, "windll"):
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                memory_status = MEMORYSTATUSEX()
                memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
                    total_memory = int(memory_status.ullTotalPhys)
                    available_memory = int(memory_status.ullAvailPhys)
        except Exception:
            pass
        return total_memory, available_memory

    def _format_memory_status(self, memory_budget: int) -> str:
        _, available_memory = self._get_memory_status()
        return f"free {available_memory // 1024 // 1024}MB / budget {memory_budget // 1024 // 1024}MB"

    def _prepare_result_dir(self) -> None:
        result = paths.ensure_inside_workspace(self.result_dir)
        shutil.rmtree(result, ignore_errors=True)
        if self.copy_source and self.source_dir:
            shutil.copytree(self.source_dir, result)
            LOGGER_COLOR.info("已复制完整源码树到输出目录: {}", result)
        else:
            result.mkdir(parents=True, exist_ok=True)
            LOGGER_COLOR.info("已清空 3-SourceTranslatedFile，只写入替换后的 qsrc 文件。")


class Localization:
    def __init__(
        self,
        paratranz_data: ParatranzDataFile,
        *,
        source_dir: Path,
        result_dir: Path,
        source_cache: dict[Path, str],
        paratranz_root: Path | None = None,
        error_reporter: ErrorReporter | None = None,
    ):
        self.paratranz_data = paratranz_data
        self.source_dir = source_dir
        self.result_dir = result_dir
        self.source_cache = source_cache
        self.paratranz_root = paratranz_root
        self.error_reporter = error_reporter
        self.qsrc_path = (self.source_dir / self.paratranz_data.relative_path_no_ext).with_suffix(".qsrc")
        self.relative_path = Path(str(self.paratranz_data.relative_path_no_ext)).with_suffix(".qsrc")

    def exists(self) -> bool:
        return self.relative_path in self.source_cache

    def translate(self) -> TranslationArtifact:
        stats = TranslationStats(total_files=1)
        if not self.exists():
            self._report_translation_error(
                "目标 qsrc 不存在，无法回写译文。",
                details=(f"目标文件: {self.qsrc_path}", f"ParaTranz 文件: {self.paratranz_data.path}"),
            )
            stats.failed = 1
            stats.missing_source = 1
            return TranslationArtifact(relative_path=self.relative_path, text="", stats=stats)

        try:
            source = self.source_cache[self.relative_path]
            entries = self.paratranz_data.get_paratranz_data_list()
        except Exception as exc:
            self._report_paratranz_error(
                "ParaTranz JSON 读取或解析失败。",
                details=(
                    f"JSON 文件: {self.paratranz_data.path}",
                    f"目标 qsrc: {self.qsrc_path}",
                    f"异常: {exc}",
                ),
            )
            stats.failed = 1
            return TranslationArtifact(relative_path=self.relative_path, text="", stats=stats)

        entries.sort(key=lambda item: item.extract_pos_from_context() if item.extract_pos_from_context() is not None else 10**18)

        applied_state = self._apply_entries_incrementally(source, entries, stats)
        final_text = applied_state.text
        final_issues = QsrcRuntimeChecker.analyze_candidate_syntax(final_text, location_name=self.relative_path.stem)

        if final_issues:
            self._report_translation_error(
                "整文件总检查失败，已回退为源文件版本。",
                details=final_issues,
            )
            final_text = source

        stats.translated = 1
        artifact = TranslationArtifact(relative_path=self.relative_path, text=final_text, stats=stats)
        del applied_state, entries
        return artifact

    def _apply_entries_incrementally(
        self,
        source: str,
        entries: list,
        stats: TranslationStats,
    ) -> ApplyState:
        state = ApplyState(text=source, offset=0, applied_entries=0)

        for entry in entries:
            if entry.stage not in TRANSLATED_STAGES or not entry.original or not entry.translation:
                stats.skipped_entries += 1
                continue
            applied = self._apply_entry(entry, state, source_text=source)
            if applied is None:
                stats.skipped_entries += 1
                continue
            state = applied
        return state

    def _apply_entry(self, entry, state: ApplyState, *, source_text: str) -> ApplyState | None:
        if entry.extract_template_payload_from_context():
            return self._apply_template_entry(entry, state, source_text=source_text)
        return self._apply_plain_entry(entry, state, source_text=source_text)

    def _apply_template_entry(self, entry, state: ApplyState, *, source_text: str) -> ApplyState | None:
        position = entry.extract_pos_from_context()
        range_end = entry.extract_range_end_from_context()
        payload = entry.extract_template_payload_from_context()
        expressions = payload.get("expressions", []) if payload else []
        source_snippet = payload.get("source", "") if payload else ""

        if position is None or range_end is None or range_end <= position or not isinstance(expressions, list) or not source_snippet:
            self._report_translation_error("模板词条上下文不完整，无法回写。", details=(f"词条 key: {entry.key}",))
            return None

        current_position = position + state.offset
        current_range_end = range_end + state.offset
        actual_snippet = state.text[current_position:current_range_end]
        if actual_snippet != source_snippet:
            search_start = max(0, current_position - 500)
            search_end = min(len(state.text), current_range_end + 500)
            real_pos, matched_length, _ = _find_text_in_window(state.text, source_snippet, search_start, search_end)
            if real_pos == -1:
                self._report_translation_error(
                    "模板源码片段丢失，无法定位整行拼接词条。",
                    details=(f"词条 key: {entry.key}", f"模板原文: {entry.original}"),
                )
                return None
            current_position = real_pos
            current_range_end = real_pos + matched_length

        rebuilt_expression = _rebuild_template_expression(entry.translation, expressions)
        if rebuilt_expression is None:
            self._report_translation_error(
                "模板译文缺少或改乱了表达式片段，无法重建整行拼接表达式。",
                details=(f"词条 key: {entry.key}", f"模板原文: {entry.original}"),
            )
            return None

        candidate_text = state.text[:current_position] + rebuilt_expression + state.text[current_range_end:]
        issues = self._validate_replacement_window(
            source_text=source_text,
            candidate_text=candidate_text,
            source_start=position,
            source_end=range_end,
            candidate_start=current_position,
            candidate_end=current_position + len(rebuilt_expression),
        )
        if issues:
            self._report_translation_error("当前模板替换未通过单行检查，已跳过该词条。", details=issues)
            return None

        new_offset = state.offset + len(rebuilt_expression) - (current_range_end - current_position)
        return ApplyState(text=candidate_text, offset=new_offset, applied_entries=state.applied_entries + 1)

    def _apply_plain_entry(self, entry, state: ApplyState, *, source_text: str) -> ApplyState | None:
        position = entry.extract_pos_from_context()
        if position is None:
            self._report_translation_error("词条缺少 POS 坐标，已跳过。", details=(f"词条 key: {entry.key}",))
            return None

        original_length = len(entry.original)
        translation = entry.translation
        current_position = position + state.offset
        actual_text = state.text[current_position: current_position + original_length]

        if actual_text != entry.original and not _is_case_only_change(actual_text, entry.original):
            search_start = max(0, current_position - 500)
            search_end = min(len(state.text), current_position + original_length + 500)
            real_pos, matched_length, match_reason = _find_text_in_window(state.text, entry.original, search_start, search_end)
            if real_pos == -1:
                preview = _nearby_preview(state.text, current_position, original_length)
                diff_lines = _render_context_diff(entry.original, actual_text, expected_label="expected-original", actual_label="actual-source")
                self._report_translation_error(
                    "目标文本丢失，无法定位该词条。",
                    details=(f"词条 key: {entry.key}", f"附近文本: {preview}", *diff_lines),
                )
                return None
            current_position = real_pos
            if match_reason == "crlf":
                translation = translation.replace("\n", "\r\n")
                original_length = matched_length

        candidate_text = state.text[:current_position] + translation + state.text[current_position + original_length:]
        issues = self._validate_replacement_window(
            source_text=source_text,
            candidate_text=candidate_text,
            source_start=position,
            source_end=position + len(entry.original),
            candidate_start=current_position,
            candidate_end=current_position + len(translation),
        )
        if issues:
            self._report_translation_error("当前替换未通过单行检查，已跳过该词条。", details=issues)
            return None

        new_offset = state.offset + len(translation) - original_length
        return ApplyState(text=candidate_text, offset=new_offset, applied_entries=state.applied_entries + 1)

    def _validate_replacement_window(
        self,
        *,
        source_text: str,
        candidate_text: str,
        source_start: int,
        source_end: int,
        candidate_start: int,
        candidate_end: int,
    ) -> tuple[str, ...]:
        is_multiline = "\n" in source_text[source_start:source_end] or "\n" in candidate_text[candidate_start:candidate_end]
        source_window = self._extract_context_window(source_text, source_start, source_end, multiline=is_multiline)
        candidate_window = self._extract_context_window(candidate_text, candidate_start, candidate_end, multiline=is_multiline)

        if is_multiline:
            issues = list(QsrcRuntimeChecker.analyze_multiline_references(source_window, candidate_window))
        else:
            issues = list(QsrcRuntimeChecker.analyze_line_references(source_window, candidate_window))

        warnings = list(QsrcBuildGuard.analyze_string_pair(source_window, candidate_window))
        for item in warnings:
            self._report_translation_warning("当前替换触发字符串结构警告，但未阻止替换。", details=(item,))

        syntax_scope = candidate_window if candidate_window.strip() else candidate_text
        issues.extend(QsrcRuntimeChecker.analyze_candidate_syntax(syntax_scope, location_name=self.relative_path.stem))
        return tuple(issues)
    @staticmethod
    def _extract_context_window(text: str, start: int, end: int, *, multiline: bool) -> str:
        if multiline:
            context_start = text.rfind("\n", 0, max(start - 1, 0))
            context_start = 0 if context_start == -1 else context_start + 1
            context_end = text.find("\n", max(end, 0))
            if context_end == -1:
                context_end = len(text)
            next_end = text.find("\n", min(len(text), context_end + 1))
            if next_end != -1:
                context_end = next_end
            return text[context_start:context_end]

        line_start = text.rfind("\n", 0, max(start, 0))
        line_start = 0 if line_start == -1 else line_start + 1
        line_end = text.find("\n", max(end, 0))
        if line_end == -1:
            line_end = len(text)
        return text[line_start:line_end]

    def _report_translation_error(self, message: str, *, details: tuple[str, ...] = ()) -> None:
        if self.error_reporter:
            self.error_reporter.report("translation", self.qsrc_path, message, details=details, source_root=self.source_dir)

    def _report_translation_warning(self, message: str, *, details: tuple[str, ...] = ()) -> None:
        LOGGER_COLOR.warning("[{}] {}", self.qsrc_path.name, message)
        if self.error_reporter:
            self.error_reporter.report(
                "translation-warning",
                self.qsrc_path,
                message,
                details=details,
                source_root=self.source_dir,
            )

    def _report_paratranz_error(self, message: str, *, details: tuple[str, ...] = ()) -> None:
        if self.error_reporter:
            source_root = self.paratranz_root if self.paratranz_root else self.paratranz_data.path.parent
            self.error_reporter.report(
                "paratranz-json",
                self.paratranz_data.path,
                message,
                details=details,
                source_root=source_root,
            )


__all__ = ["LocalizationManager", "Localization", "TranslationStats", "replace_localizations"]


def replace_localizations(
    source_dir: Path | str | None = None,
    paratranz_dir: Path | str | None = None,
    result_dir: Path | str | None = None,
    *,
    clear_result: bool = True,
    copy_source: bool = False,
    concurrency: int = 32,
    show_progress: bool = False,
    error_reporter: ErrorReporter | None = None,
    memory_limit_mb: int | None = None,
) -> TranslationStats:
    manager = LocalizationManager(
        source_dir=source_dir,
        paratranz_dir=paratranz_dir,
        result_dir=result_dir,
        clear_result=clear_result,
        copy_source=copy_source,
        concurrency=concurrency,
        show_progress=show_progress,
        error_reporter=error_reporter,
        memory_limit_mb=memory_limit_mb,
    )
    return manager.translate()
