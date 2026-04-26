from __future__ import annotations

import json
import re
import shutil
from base64 import urlsafe_b64encode
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import orjson
from diff_match_patch import diff_match_patch
from thefuzz import fuzz

from src.storage.files import FileManager, ParatranzDataFile
from src.config.logging import logger
from src.models import ParatranzData, StageEnum
from src.config.paths import detect_source_root, detect_translation_root, paths
from src.config.progress import ProgressBar


_DISPLAY_KEYWORDS = ("msg", "*p", "*pl", "p", "pl")
_ACT_PATTERN = re.compile(r"^\s*act\b", re.IGNORECASE)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SLUG_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9]+")
_ASSIGNMENT_PREFIX_PATTERN = re.compile(
    r"^\s*(?:local\s+)?[$A-Za-z_][A-Za-z0-9_$\[\].']*\s*=\s*$",
    re.IGNORECASE,
)
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_MEDIA_TAG_PATTERN = re.compile(r"<\s*/?\s*(img|video|audio|source)\b[^>]*>", re.IGNORECASE)
_PLACEHOLDER_PATTERN = re.compile(r"<<[^>]+>>|&lt;&lt;.*?&gt;&gt;")
_HTML_ENTITY_PATTERN = re.compile(r"&(?:[A-Za-z]+|#\d+);")
_ASSET_PATH_PATTERN = re.compile(
    r"^[A-Za-z0-9_./\\() \-]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg|mp4|webm|avi|mov|mkv)$",
    re.IGNORECASE,
)
_CODE_LABEL_TOKEN_PATTERN = re.compile(r"[$A-Za-z_][A-Za-z0-9_$\[\]'.:-]*$")
_TEMPLATE_EXPR_PATTERN = re.compile(r"\{\{expr_(\d+)\}\}")
_LEGACY_INLINE_ACT_PATTERN = re.compile(
    r"':\s*(?:minut\s*\+=|gt\b|gs\b|msg\b|kla\b|cla\b|killvar\b|\*)",
    re.IGNORECASE,
)
_OBSOLETE_DIRNAME = "obsolete"
_OBSOLETE_MARKER = "[OBSOLETE]"
_FUZZY_MIN_SCORE = 78.0
_FUZZY_MIN_RATIO = 70
_FUZZY_MIN_DIFF_SCORE = 0.55


@dataclass(frozen=True, slots=True)
class SourceLiteral:
    start_quote: int
    start_content: int
    end_quote: int
    quote: str
    line_start: int
    line_end: int
    content: str


@dataclass(frozen=True, slots=True)
class LineTemplate:
    start_pos: int
    end_pos: int
    template: str
    source_snippet: str
    expressions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyncStats:
    files_total: int = 0
    files_written: int = 0
    extracted_entries: int = 0
    migrated_entries: int = 0
    new_entries: int = 0
    removed_entries: int = 0

class QsrcLocalizationExtractor:
    """从 qsrc 源码中提取可写入 ParaTranz 的本地化词条。"""

    def extract_tree(self, source_root: Path) -> dict[Path, list[ParatranzData]]:
        extracted: dict[Path, list[ParatranzData]] = {}
        for file in FileManager.get_qsrc_scripts(source_root):
            relative_path = Path(file.rel_path)
            entries = self.extract_file(file.path, relative_path)
            if entries:
                extracted[relative_path] = entries
        return extracted

    def extract_file(self, source_path: Path, relative_path: Path) -> list[ParatranzData]:
        source = source_path.read_text(encoding="utf-8")
        literals = self._iter_string_literals(source)
        grouped: dict[int, list[SourceLiteral]] = defaultdict(list)
        for literal in literals:
            grouped[literal.line_start].append(literal)

        file_stem = relative_path.stem
        entries: list[ParatranzData] = []
        used_keys: set[str] = set()

        for line_text, line_literals in self._iter_logical_literal_groups(source, grouped):
            stripped_line = line_text.lstrip()
            if not stripped_line:
                continue

            if _ACT_PATTERN.match(stripped_line):
                template = self._build_line_template(source, line_text, line_literals, act_mode=True)
                if template:
                    entries.append(self._build_template_entry(file_stem, "act", template, used_keys))
                else:
                    literal = self._find_act_label_literal(line_text, line_literals)
                    if self._should_keep_literal(literal.content):
                        entries.append(self._build_entry(file_stem, "act", literal, used_keys))
                continue

            if self._is_variable_assignment_line(line_text, line_literals[0]):
                template = self._build_line_template(source, line_text, line_literals, act_mode=False)
                if template:
                    entries.append(self._build_template_entry(file_stem, "var", template, used_keys))
                else:
                    literal = line_literals[0]
                    if self._should_keep_literal(literal.content):
                        entries.append(self._build_entry(file_stem, "var", literal, used_keys))
                continue

            if self._is_display_line(stripped_line, line_text, line_literals[0]):
                entry_type = "msg" if self._starts_with_display_keyword(stripped_line, "msg") else "text"
                template = self._build_line_template(source, line_text, line_literals, act_mode=False)
                if template:
                    entries.append(self._build_template_entry(file_stem, entry_type, template, used_keys))
                elif len(line_literals) == 1:
                    for literal in line_literals:
                        if self._should_keep_literal(literal.content):
                            entries.append(self._build_entry(file_stem, entry_type, literal, used_keys))

        entries.sort(key=lambda item: item.extract_pos_from_context() or 0)
        return entries

    def _iter_logical_literal_groups(
        self,
        source: str,
        grouped: dict[int, list[SourceLiteral]],
    ) -> list[tuple[str, list[SourceLiteral]]]:
        line_starts = sorted(grouped)
        logical_groups: list[tuple[str, list[SourceLiteral]]] = []
        index = 0

        while index < len(line_starts):
            line_start = line_starts[index]
            combined_literals = list(grouped[line_start])
            line_end = combined_literals[-1].line_end
            line_text = source[line_start:line_end]

            while self._has_line_continuation(line_text) and index + 1 < len(line_starts):
                index += 1
                next_start = line_starts[index]
                next_literals = grouped[next_start]
                combined_literals.extend(next_literals)
                line_end = next_literals[-1].line_end
                line_text = source[line_start:line_end]

            logical_groups.append((line_text, combined_literals))
            index += 1

        return logical_groups

    def _has_line_continuation(self, line_text: str) -> bool:
        quote: str | None = None
        in_block_comment = False
        last_code_char = ""
        index = 0

        while index < len(line_text):
            char = line_text[index]

            if in_block_comment:
                if char == "!" and index + 1 < len(line_text) and line_text[index + 1] == "}":
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if quote:
                if char == quote:
                    if index + 1 < len(line_text) and line_text[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
                index += 1
                continue

            if char == "{" and index + 1 < len(line_text) and line_text[index + 1] == "!":
                in_block_comment = True
                index += 2
                continue

            if char == "!" and index + 1 < len(line_text) and line_text[index + 1] == "!":
                break

            if char in ("'", '"'):
                quote = char
                index += 1
                continue

            if char not in (" ", "\t", "\r", "\n"):
                last_code_char = char
            index += 1

        return last_code_char == "_"

    def is_entry_extractable(self, entry: ParatranzData) -> bool:
        return self._should_keep_entry(entry)

    def _iter_string_literals(self, source: str) -> list[SourceLiteral]:
        literals: list[SourceLiteral] = []
        length = len(source)
        index = 0
        in_block_comment = False

        while index < length:
            char = source[index]

            if in_block_comment:
                if char == "!" and index + 1 < length and source[index + 1] == "}":
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if char == "{" and index + 1 < length and source[index + 1] == "!":
                in_block_comment = True
                index += 2
                continue

            if char == "!" and index + 1 < length and source[index + 1] == "!":
                newline = source.find("\n", index)
                if newline == -1:
                    break
                index = newline + 1
                continue

            if char not in ("'", '"'):
                index += 1
                continue

            start_quote = index
            line_start = source.rfind("\n", 0, start_quote) + 1
            quote = char
            index += 1
            start_content = index

            while index < length:
                current = source[index]
                if current == quote:
                    if index + 1 < length and source[index + 1] == quote:
                        index += 2
                        continue
                    end_quote = index
                    line_end = source.find("\n", line_start)
                    if line_end == -1:
                        line_end = length
                    literals.append(
                        SourceLiteral(
                            start_quote=start_quote,
                            start_content=start_content,
                            end_quote=end_quote,
                            quote=quote,
                            line_start=line_start,
                            line_end=line_end,
                            content=source[start_content:end_quote],
                        )
                    )
                    index += 1
                    break
                index += 1
            else:
                break

        return literals

    @staticmethod
    def _starts_with_display_keyword(stripped_line: str, keyword: str) -> bool:
        lower = stripped_line.casefold()
        return lower.startswith(keyword + " ")

    def _is_display_line(self, stripped_line: str, line_text: str, first_literal: SourceLiteral) -> bool:
        if stripped_line.startswith(("'", '"')):
            return True
        if any(self._starts_with_display_keyword(stripped_line, keyword) for keyword in _DISPLAY_KEYWORDS):
            return True
        prefix = line_text[: first_literal.start_quote - first_literal.line_start].rstrip()
        return prefix.endswith((":", "&", "+", "(", ","))

    @staticmethod
    def _is_variable_assignment_line(line_text: str, first_literal: SourceLiteral) -> bool:
        prefix = line_text[: first_literal.start_quote - first_literal.line_start]
        return bool(_ASSIGNMENT_PREFIX_PATTERN.fullmatch(prefix))

    @staticmethod
    def _should_keep_literal(content: str) -> bool:
        if not content:
            return False
        stripped = content.strip()
        if not stripped:
            return False
        if stripped in ("'", '"'):
            return False
        if stripped.startswith("<<POS:"):
            return False
        if QsrcLocalizationExtractor._looks_like_asset_path(stripped):
            return False
        if QsrcLocalizationExtractor._is_media_only_markup(stripped):
            return False
        visible_text = QsrcLocalizationExtractor._extract_visible_text(stripped)
        if not visible_text:
            return False
        if QsrcLocalizationExtractor._looks_like_code_label(visible_text):
            return False
        return True

    @classmethod
    def _should_keep_entry(cls, entry: ParatranzData) -> bool:
        original = entry.original.strip()
        if not cls._should_keep_literal(original):
            return False
        if cls._looks_like_legacy_inline_action(entry):
            return False
        return True

    @staticmethod
    def _looks_like_legacy_inline_action(entry: ParatranzData) -> bool:
        key = entry.key or ""
        original = entry.original.strip()
        if "|act|" not in key:
            return False
        return bool(_LEGACY_INLINE_ACT_PATTERN.search(original))

    @staticmethod
    def _extract_visible_text(content: str) -> str:
        text = _PLACEHOLDER_PATTERN.sub(" ", content)
        text = _HTML_ENTITY_PATTERN.sub(" ", text)
        text = _HTML_TAG_PATTERN.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _is_media_only_markup(content: str) -> bool:
        if not (_MEDIA_TAG_PATTERN.search(content) or "src=" in content.casefold()):
            return False
        visible_text = QsrcLocalizationExtractor._extract_visible_text(content)
        if not visible_text:
            return True
        compact_text = visible_text.replace(" ", "")
        return (
            QsrcLocalizationExtractor._looks_like_asset_path(visible_text)
            or QsrcLocalizationExtractor._looks_like_asset_path(compact_text)
        )

    @staticmethod
    def _looks_like_asset_path(content: str) -> bool:
        candidate = content.strip().strip('"').strip("'")
        if not candidate:
            return False
        if not _ASSET_PATH_PATTERN.fullmatch(candidate):
            return False
        return "/" in candidate or "\\" in candidate or "." in candidate

    @staticmethod
    def _looks_like_code_label(visible_text: str) -> bool:
        if not any(marker in visible_text for marker in ("$", "_", "[", "]")):
            return False
        tokens = [token for token in visible_text.split() if token]
        return bool(tokens) and all(_CODE_LABEL_TOKEN_PATTERN.fullmatch(token) for token in tokens)

    def _build_line_template(
        self,
        source: str,
        line_text: str,
        line_literals: list[SourceLiteral],
        *,
        act_mode: bool,
    ) -> LineTemplate | None:
        line_start = line_literals[0].line_start
        expr_start = line_literals[0].start_quote
        expr_end = line_start + len(line_text.rstrip())
        if act_mode:
            colon_index = self._find_act_colon(line_text)
            if colon_index == -1:
                return None
            expr_end = line_start + colon_index

        source_snippet = source[expr_start:expr_end].rstrip()
        if "+" not in source_snippet:
            return None
        segments = self._split_top_level_concat(source_snippet)
        if len(segments) < 2:
            return None

        expressions: list[str] = []
        template_parts: list[str] = []
        string_count = 0
        for segment in segments:
            literal_text = self._parse_string_token(segment)
            if literal_text is not None:
                string_count += 1
                template_parts.append(literal_text)
                continue
            expression = segment.strip()
            if not expression:
                continue
            expressions.append(expression)
            template_parts.append(expression)

        if string_count == 0 or not expressions:
            return None

        template = "".join(template_parts).strip()
        if not template:
            return None
        if self._is_media_only_markup(template):
            return None
        visible_text = self._extract_visible_text(template)
        if not visible_text or self._looks_like_asset_path(visible_text) or self._looks_like_code_label(visible_text):
            return None

        return LineTemplate(
            start_pos=expr_start,
            end_pos=expr_end,
            template=template,
            source_snippet=source_snippet,
            expressions=tuple(expressions),
        )

    @staticmethod
    def _split_top_level_concat(expression: str) -> list[str]:
        parts: list[str] = []
        quote: str | None = None
        paren_depth = 0
        start = 0
        index = 0

        while index < len(expression):
            char = expression[index]
            if quote:
                if char == quote:
                    if index + 1 < len(expression) and expression[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
                index += 1
                continue

            if char in ("'", '"'):
                quote = char
                index += 1
                continue
            if char == "_":
                lookahead = index + 1
                while lookahead < len(expression) and expression[lookahead] in (" ", "\t", "\r"):
                    lookahead += 1
                if lookahead < len(expression) and expression[lookahead] == "\n":
                    index = lookahead + 1
                    start = index
                    continue
            if char == "(":
                paren_depth += 1
                index += 1
                continue
            if char == ")" and paren_depth > 0:
                paren_depth -= 1
                index += 1
                continue
            if char == "+" and paren_depth == 0:
                parts.append(expression[start:index].strip())
                start = index + 1
            index += 1

        parts.append(expression[start:].strip())
        return [part for part in parts if part]

    @staticmethod
    def _parse_string_token(token: str) -> str | None:
        candidate = token.strip()
        if len(candidate) < 2:
            return None
        quote = candidate[0]
        if quote not in ("'", '"') or candidate[-1] != quote:
            return None
        return candidate[1:-1].replace(quote * 2, quote)

    @staticmethod
    def _find_act_colon(line_text: str) -> int:
        quote: str | None = None
        index = 0
        while index < len(line_text):
            char = line_text[index]
            if quote:
                if char == quote:
                    if index + 1 < len(line_text) and line_text[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
                index += 1
                continue
            if char in ("'", '"'):
                quote = char
                index += 1
                continue
            if char == ":":
                return index
            index += 1
        return -1

    def _find_act_label_literal(self, line_text: str, line_literals: list[SourceLiteral]) -> SourceLiteral:
        colon_index = self._find_act_colon(line_text)
        if colon_index == -1:
            return line_literals[0]

        colon_abs = line_literals[0].line_start + colon_index
        for literal in line_literals:
            if literal.end_quote < colon_abs:
                return literal
        return line_literals[0]

    def _build_entry(
        self,
        file_stem: str,
        entry_type: str,
        literal: SourceLiteral,
        used_keys: set[str],
    ) -> ParatranzData:
        position = literal.start_content
        base_key = f"{file_stem}|{entry_type}|{self._slugify(literal.content, position)}"
        key = base_key
        if key in used_keys:
            key = f"{base_key}_{position:08d}"
        used_keys.add(key)
        return ParatranzData(
            key=key,
            original=literal.content,
            translation="",
            stage=StageEnum(0),
            context=f"<<POS:{position:08d}>>",
        )

    def _build_template_entry(
        self,
        file_stem: str,
        entry_type: str,
        template: LineTemplate,
        used_keys: set[str],
    ) -> ParatranzData:
        position = template.start_pos
        base_key = f"{file_stem}|{entry_type}|{self._slugify(template.template, position)}"
        key = base_key
        if key in used_keys:
            key = f"{base_key}_{position:08d}"
        used_keys.add(key)
        payload = {
            "kind": "line-template",
            "source": template.source_snippet,
            "expressions": list(template.expressions),
        }
        encoded_payload = urlsafe_b64encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        context = f"<<POS:{position:08d}>><<RANGE_END:{template.end_pos:08d}>><<TPL:{encoded_payload}>>"
        return ParatranzData(
            key=key,
            original=template.source_snippet,
            translation="",
            stage=StageEnum(0),
            context=context,
        )

    @staticmethod
    def _slugify(content: str, position: int) -> str:
        candidate = content.replace("\r", " ").replace("\n", " ").replace("&lt;", " ").replace("&gt;", " ")
        candidate = _SLUG_SANITIZE_PATTERN.sub("_", candidate).strip("_")
        if not candidate:
            return f"pos_{position:08d}"
        return candidate[:72]


class ParatranzSyncService:
    """根据源码提取 ParaTranz 词条，并把旧 JSON 中可复用的翻译迁移到新版本。"""

    def __init__(self, extractor: QsrcLocalizationExtractor | None = None):
        self.extractor = extractor or QsrcLocalizationExtractor()

    def extract_entries(self, source_root: Path) -> dict[Path, list[ParatranzData]]:
        return self.extractor.extract_tree(source_root)

    def export_entries(
        self,
        *,
        source_root: Path | None = None,
        output_root: Path | None = None,
        clear_output: bool = True,
        show_progress: bool = False,
    ) -> SyncStats:
        source_root = Path(source_root).resolve() if source_root else detect_source_root()
        if not source_root:
            raise FileNotFoundError("未检测到源码目录，无法提取 ParaTranz 词条。")

        output_root = (
            Path(output_root).resolve()
            if output_root
            else (paths.sync / source_root.name / "extract").resolve()
        )
        output_root = paths.ensure_inside_workspace(output_root)

        if clear_output:
            shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)

        extracted = self.extract_entries(source_root)
        written = 0
        with ProgressBar(total=len(extracted), enabled=show_progress, desc="Extract", unit="file") as progress:
            for relative_qsrc, entries in sorted(extracted.items()):
                relative_json = relative_qsrc.with_suffix(".qsrc.json")
                output_path = output_root / relative_json
                self._write_entries(output_path, entries)
                written += 1
                progress.set_postfix_str(str(relative_json).replace("\\", "/"))
                progress.update()

        return SyncStats(
            files_total=len(extracted),
            files_written=written,
            extracted_entries=sum(len(items) for items in extracted.values()),
            migrated_entries=0,
            new_entries=0,
            removed_entries=0,
        )

    def merge_entries(
        self,
        new_entries: list[ParatranzData],
        old_entries: list[ParatranzData],
    ) -> tuple[list[ParatranzData], list[ParatranzData], dict[str, int]]:
        return self._merge_entries(new_entries, old_entries)

    def sync(
        self,
        *,
        source_root: Path | None = None,
        old_paratranz_root: Path | None = None,
        output_root: Path | None = None,
        clear_output: bool = True,
        show_progress: bool = False,
    ) -> SyncStats:
        source_root = Path(source_root).resolve() if source_root else detect_source_root()
        if not source_root:
            raise FileNotFoundError("未检测到源码目录，无法提取 ParaTranz 词条。")

        old_paratranz_root = Path(old_paratranz_root).resolve() if old_paratranz_root else detect_translation_root()
        output_root = (
            Path(output_root).resolve()
            if output_root
            else (paths.sync / source_root.name / "sync").resolve()
        )
        output_root = paths.ensure_inside_workspace(output_root)

        if clear_output:
            shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        obsolete_root = output_root / _OBSOLETE_DIRNAME

        logger.info("开始同步 ParaTranz 词条: {} -> {}", source_root, output_root)
        extracted = self.extract_entries(source_root)
        migrated = self._load_old_entries(old_paratranz_root) if old_paratranz_root and old_paratranz_root.exists() else {}

        stats = SyncStats(files_total=len(extracted), extracted_entries=sum(len(items) for items in extracted.values()))
        migrated_entries = 0
        new_entries = 0
        removed_entries = 0
        written = 0
        report_files: list[dict[str, object]] = []
        obsolete_files: list[str] = []

        with ProgressBar(total=len(extracted), enabled=show_progress, desc="Sync", unit="file") as progress:
            for relative_qsrc, new_entries_list in sorted(extracted.items()):
                relative_json = relative_qsrc.with_suffix(".qsrc.json")
                old_entries = migrated.pop(relative_json, [])
                merged_entries, removed_file_entries, file_report = self._merge_entries(new_entries_list, old_entries)
                removed_file_entries = [entry for entry in removed_file_entries if self._should_archive_obsolete(entry)]
                file_report["removed"] = len(removed_file_entries)
                migrated_entries += int(file_report["migrated"])
                new_entries += int(file_report["new"])
                removed_entries += int(file_report["removed"])
                report_files.append({
                    "file": str(relative_json).replace("\\", "/"),
                    **file_report,
                })

                output_path = output_root / relative_json
                output_path.parent.mkdir(parents=True, exist_ok=True)
                payload = [entry.model_dump(mode="json") for entry in merged_entries]
                output_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
                written += 1
                progress.set_postfix_str(str(relative_json).replace("\\", "/"))
                progress.update()
                if removed_file_entries:
                    obsolete_path = obsolete_root / relative_json
                    self._write_entries(obsolete_path, removed_file_entries)
                    obsolete_files.append(str((Path(_OBSOLETE_DIRNAME) / relative_json).as_posix()))

        removed_file_reports: list[str] = []
        for relative_json, old_entries in sorted(migrated.items()):
            obsolete_entries = [
                self._mark_entry_obsolete(entry, "源文件已不再出现在当前源码提取结果中。")
                for entry in old_entries
                if self._should_archive_obsolete(entry)
            ]
            if not obsolete_entries:
                continue
            removed_entries += len(obsolete_entries)
            obsolete_path = obsolete_root / relative_json
            self._write_entries(obsolete_path, obsolete_entries)
            relative_obsolete = str((Path(_OBSOLETE_DIRNAME) / relative_json).as_posix())
            obsolete_files.append(relative_obsolete)
            removed_file_reports.append(str(relative_json).replace("\\", "/"))

        report = {
            "source_root": str(source_root),
            "old_paratranz_root": str(old_paratranz_root) if old_paratranz_root and old_paratranz_root.exists() else None,
            "output_root": str(output_root),
            "obsolete_root": str(obsolete_root),
            "stats": {
                "files_total": stats.files_total,
                "files_written": written,
                "extracted_entries": stats.extracted_entries,
                "migrated_entries": migrated_entries,
                "new_entries": new_entries,
                "removed_entries": removed_entries,
            },
            "files": report_files,
            "removed_files": removed_file_reports,
            "obsolete_files": sorted(obsolete_files),
        }
        (output_root / "_sync_report.json").write_bytes(orjson.dumps(report, option=orjson.OPT_INDENT_2))

        logger.success(
            "ParaTranz 同步完成: 文件 {}，提取 {}，迁移 {}，新增 {}，移除 {}",
            written,
            stats.extracted_entries,
            migrated_entries,
            new_entries,
            removed_entries,
        )
        return SyncStats(
            files_total=stats.files_total,
            files_written=written,
            extracted_entries=stats.extracted_entries,
            migrated_entries=migrated_entries,
            new_entries=new_entries,
            removed_entries=removed_entries,
        )

    def _load_old_entries(self, paratranz_root: Path) -> dict[Path, list[ParatranzData]]:
        loaded: dict[Path, list[ParatranzData]] = {}
        for data_file in FileManager.get_paratranz_data_files(paratranz_root):
            relative_json = Path(data_file.rel_path)
            if relative_json.name == "_sync_report.json":
                continue
            if relative_json.parts and relative_json.parts[0] == _OBSOLETE_DIRNAME:
                relative_json = Path(*relative_json.parts[1:])
            entries = [
                entry
                for entry in data_file.get_paratranz_data_list()
                if self._should_keep_old_entry(entry)
            ]
            if not entries:
                continue
            loaded.setdefault(relative_json, []).extend(entries)
        return loaded

    def _merge_entries(
        self,
        new_entries: list[ParatranzData],
        old_entries: list[ParatranzData],
    ) -> tuple[list[ParatranzData], list[ParatranzData], dict[str, int]]:
        exact_map: dict[str, list[ParatranzData]] = defaultdict(list)
        normalized_map: dict[str, list[ParatranzData]] = defaultdict(list)
        template_map: dict[str, list[ParatranzData]] = defaultdict(list)
        template_shape_map: dict[str, list[ParatranzData]] = defaultdict(list)
        matched_old_ids: set[int] = set()

        for entry in old_entries:
            exact_map[entry.original].append(entry)
            normalized_map[self._normalize_text(entry.original)].append(entry)
            template_signature = self._extract_template_signature(entry)
            if template_signature:
                template_map[template_signature].append(entry)
            template_shape = self._extract_template_shape(entry)
            if template_shape:
                template_shape_map[template_shape].append(entry)

        merged: list[ParatranzData] = []
        removed: list[ParatranzData] = []
        migrated_count = 0
        new_count = 0
        unmatched_new_slots: list[tuple[int, ParatranzData]] = []

        for new_entry in new_entries:
            old_entry = self._select_best_match(
                new_entry,
                exact_map=exact_map,
                normalized_map=normalized_map,
                template_map=template_map,
                template_shape_map=template_shape_map,
                matched_old_ids=matched_old_ids,
            )

            if old_entry and old_entry.translation:
                translation = self._migrate_entry_translation(old_entry, new_entry)
                merged.append(
                    ParatranzData(
                        key=old_entry.key or new_entry.key,
                        original=new_entry.original,
                        translation=translation,
                        stage=self._resolve_migrated_stage(old_entry),
                        context=new_entry.context,
                    )
                )
                migrated_count += 1
                continue

            merged.append(new_entry)
            unmatched_new_slots.append((len(merged) - 1, new_entry))
            new_count += 1

        for old_entry in old_entries:
            if id(old_entry) in matched_old_ids or not old_entry.translation:
                continue
            fuzzy_match = self._take_fuzzy_context_match(old_entry, unmatched_new_slots)
            if fuzzy_match is None:
                continue

            slot_index, new_entry = fuzzy_match
            translation = self._migrate_entry_translation(old_entry, new_entry)
            merged[slot_index] = ParatranzData(
                key=old_entry.key or new_entry.key,
                original=new_entry.original,
                translation=translation,
                stage=self._resolve_migrated_stage(old_entry),
                context=new_entry.context,
            )
            matched_old_ids.add(id(old_entry))
            unmatched_new_slots = [item for item in unmatched_new_slots if item[0] != slot_index]
            migrated_count += 1
            new_count -= 1

        merged_exact = {entry.original for entry in merged}
        merged_normalized = {self._normalize_text(entry.original) for entry in merged}
        merged_template_signatures = {
            signature
            for entry in merged
            if (signature := self._extract_template_signature(entry))
        }
        merged_template_shapes = {
            shape
            for entry in merged
            if (shape := self._extract_template_shape(entry))
        }

        for old_entry in old_entries:
            if id(old_entry) in matched_old_ids:
                continue
            if not self._should_archive_obsolete(old_entry):
                continue
            if self._is_superseded_old_entry(
                old_entry,
                merged_exact=merged_exact,
                merged_normalized=merged_normalized,
                merged_template_signatures=merged_template_signatures,
                merged_template_shapes=merged_template_shapes,
            ):
                continue
            removed.append(self._mark_entry_obsolete(old_entry, "词条在新版源码中未匹配到，已归档为过时。"))

        removed_count = len(removed)
        return merged, removed, {"migrated": migrated_count, "new": new_count, "removed": removed_count}

    def _select_best_match(
        self,
        new_entry: ParatranzData,
        *,
        exact_map: dict[str, list[ParatranzData]],
        normalized_map: dict[str, list[ParatranzData]],
        template_map: dict[str, list[ParatranzData]],
        template_shape_map: dict[str, list[ParatranzData]],
        matched_old_ids: set[int],
    ) -> ParatranzData | None:
        candidate_ranks: dict[int, tuple[tuple[int, int, int, int], ParatranzData]] = {}

        self._collect_match_candidates(
            candidate_ranks,
            exact_map.get(new_entry.original, []),
            matched_old_ids,
            strategy_priority=0,
        )
        self._collect_match_candidates(
            candidate_ranks,
            normalized_map.get(self._normalize_text(new_entry.original), []),
            matched_old_ids,
            strategy_priority=1,
        )

        template_signature = self._extract_template_signature(new_entry)
        if template_signature:
            self._collect_match_candidates(
                candidate_ranks,
                template_map.get(template_signature, []),
                matched_old_ids,
                strategy_priority=2,
            )

        template_shape = self._extract_template_shape(new_entry)
        if template_shape:
            self._collect_match_candidates(
                candidate_ranks,
                template_shape_map.get(template_shape, []),
                matched_old_ids,
                strategy_priority=3,
            )

        similarity_candidate = self._take_template_similarity_match(new_entry, template_shape_map, matched_old_ids)
        if similarity_candidate is not None:
            self._collect_match_candidates(
                candidate_ranks,
                [similarity_candidate],
                matched_old_ids,
                strategy_priority=4,
            )

        if not candidate_ranks:
            return None

        _, best_entry = min(candidate_ranks.values(), key=lambda item: item[0])
        matched_old_ids.add(id(best_entry))
        return best_entry

    @staticmethod
    def _collect_match_candidates(
        candidate_ranks: dict[int, tuple[tuple[int, int, int, int], ParatranzData]],
        candidates: list[ParatranzData],
        matched_old_ids: set[int],
        *,
        strategy_priority: int,
    ) -> None:
        for index, candidate in enumerate(candidates):
            candidate_id = id(candidate)
            if candidate_id in matched_old_ids:
                continue
            rank = (
                0 if candidate.translation else 1,
                strategy_priority,
                0 if int(candidate.stage) != -1 else 1,
                index,
            )
            current = candidate_ranks.get(candidate_id)
            if current is None or rank < current[0]:
                candidate_ranks[candidate_id] = (rank, candidate)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.replace("\r\n", "\n").strip()

    @classmethod
    def _normalize_qsp_code_for_match(cls, text: str) -> str:
        normalized = cls._normalize_text(text)
        segments = cls._split_qsp_expression_segments(normalized)
        if segments is None:
            return normalized.casefold()

        parts: list[str] = []
        for is_string, segment in segments:
            if is_string:
                parts.append(segment)
            else:
                parts.append(re.sub(r"\s+", " ", segment).strip().casefold())
        return "".join(parts)

    @classmethod
    def _extract_template_signature(cls, entry: ParatranzData) -> str | None:
        template_data = cls._extract_template_data(entry)
        if template_data is None:
            return None
        source, expressions = template_data

        normalized_source = ParatranzSyncService._normalize_qsp_code_for_match(source)
        normalized_expressions = tuple(
            ParatranzSyncService._normalize_qsp_code_for_match(str(item))
            for item in expressions
        )
        return json.dumps(
            {
                "source": normalized_source,
                "expressions": normalized_expressions,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @classmethod
    def _extract_template_shape(cls, entry: ParatranzData) -> str | None:
        template_data = cls._extract_template_data(entry)
        if template_data is None:
            return None
        source, expressions = template_data

        shape = ParatranzSyncService._placeholderize_template_text(source, expressions)
        if shape is None:
            return None
        return json.dumps(
            {
                "shape": ParatranzSyncService._normalize_qsp_code_for_match(shape),
                "expr_count": len(expressions),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @classmethod
    def _extract_template_data(cls, entry: ParatranzData) -> tuple[str, list[str]] | None:
        payload = entry.extract_template_payload_from_context()
        if payload and payload.get("kind") == "line-template":
            source = payload.get("source", "")
            expressions = payload.get("expressions", [])
            if source and isinstance(expressions, list):
                return str(source), [str(item) for item in expressions]

        inferred = cls._infer_template_data_from_original(entry.original)
        if inferred is None:
            return None
        return inferred

    @classmethod
    def _infer_template_data_from_original(cls, original: str) -> tuple[str, list[str]] | None:
        source = cls._normalize_text(original)
        if not source or "+" not in source:
            return None
        segments = QsrcLocalizationExtractor._split_top_level_concat(source)
        if len(segments) < 2:
            return None

        expressions: list[str] = []
        string_count = 0
        for segment in segments:
            literal_text = QsrcLocalizationExtractor._parse_string_token(segment)
            if literal_text is not None:
                string_count += 1
                continue
            expression = segment.strip()
            if expression:
                expressions.append(expression)
        if string_count == 0 or not expressions:
            return None
        return source, expressions

    @staticmethod
    def _placeholderize_template_text(text: str, expressions: list[str]) -> str | None:
        if not text:
            return None

        if _TEMPLATE_EXPR_PATTERN.search(text):
            return _TEMPLATE_EXPR_PATTERN.sub("{{expr}}", text)

        parts: list[str] = []
        cursor = 0
        for expression in expressions:
            expr_text = str(expression).strip()
            if not expr_text:
                return None
            expr_pos = text.find(expr_text, cursor)
            if expr_pos == -1:
                return None
            parts.append(text[cursor:expr_pos])
            parts.append("{{expr}}")
            cursor = expr_pos + len(expr_text)
        parts.append(text[cursor:])
        return "".join(parts)

    @staticmethod
    def _migrate_entry_translation(old_entry: ParatranzData, new_entry: ParatranzData) -> str:
        translation = old_entry.translation
        old_template_data = ParatranzSyncService._extract_template_data(old_entry)
        new_template_data = ParatranzSyncService._extract_template_data(new_entry)
        if not old_template_data or not new_template_data:
            return translation

        old_source, old_exprs = old_template_data
        new_source, new_exprs = new_template_data
        migrated_source_style = ParatranzSyncService._migrate_source_style_translation(
            translation,
            old_source,
            new_source,
        )
        if migrated_source_style is not None:
            return migrated_source_style

        if len(old_exprs) != len(new_exprs):
            return translation

        if _TEMPLATE_EXPR_PATTERN.search(translation):
            for index, new_expr in enumerate(new_exprs, start=1):
                translation = translation.replace(f"{{{{expr_{index}}}}}", str(new_expr).strip())
            return translation

        parts: list[str] = []
        cursor = 0
        for old_expr, new_expr in zip(old_exprs, new_exprs):
            old_expr_text = str(old_expr).strip()
            new_expr_text = str(new_expr).strip()
            if not old_expr_text:
                return translation
            expr_pos = translation.find(old_expr_text, cursor)
            if expr_pos == -1:
                return translation
            parts.append(translation[cursor:expr_pos])
            parts.append(new_expr_text)
            cursor = expr_pos + len(old_expr_text)
        parts.append(translation[cursor:])
        return "".join(parts)

    @staticmethod
    def _migrate_source_style_translation(
        translation: str,
        old_source: str,
        new_source: str,
    ) -> str | None:
        if not translation or not old_source or not new_source:
            return None
        if not (translation.lstrip().startswith(("'", '"')) and "+" in translation):
            return None

        old_segments = QsrcLocalizationExtractor._split_top_level_concat(old_source)
        new_segments = QsrcLocalizationExtractor._split_top_level_concat(new_source)
        translated_segments = QsrcLocalizationExtractor._split_top_level_concat(translation)
        if len(old_segments) < 2 or len(new_segments) < 2 or len(translated_segments) < 2:
            return None
        if len(old_segments) != len(new_segments) or len(old_segments) != len(translated_segments):
            return None

        result_parts: list[str] = []
        for old_segment, new_segment, translated_segment in zip(old_segments, new_segments, translated_segments):
            old_literal = QsrcLocalizationExtractor._parse_string_token(old_segment)
            new_literal = QsrcLocalizationExtractor._parse_string_token(new_segment)
            translated_literal = QsrcLocalizationExtractor._parse_string_token(translated_segment)

            if old_literal is not None or new_literal is not None or translated_literal is not None:
                if translated_literal is None or old_literal is None or new_literal is None:
                    return None
                result_parts.append(translated_segment.strip())
                continue

            migrated_segment = ParatranzSyncService._migrate_mixed_code_segment(
                old_segment.strip(),
                new_segment.strip(),
                translated_segment.strip(),
            )
            if migrated_segment is None:
                return None
            result_parts.append(migrated_segment)

        return " + ".join(result_parts)

    @staticmethod
    def _migrate_mixed_code_segment(
        old_segment: str,
        new_segment: str,
        translated_segment: str,
    ) -> str | None:
        old_parts = ParatranzSyncService._split_qsp_expression_segments(old_segment)
        new_parts = ParatranzSyncService._split_qsp_expression_segments(new_segment)
        translated_parts = ParatranzSyncService._split_qsp_expression_segments(translated_segment)
        if old_parts is None or new_parts is None or translated_parts is None:
            return None
        if len(old_parts) != len(new_parts) or len(old_parts) != len(translated_parts):
            return None

        old_kinds = [is_string for is_string, _ in old_parts]
        new_kinds = [is_string for is_string, _ in new_parts]
        translated_kinds = [is_string for is_string, _ in translated_parts]
        if old_kinds != new_kinds or old_kinds != translated_kinds:
            return None

        result_parts: list[str] = []
        for (is_string, _), (_, new_part), (_, translated_part) in zip(old_parts, new_parts, translated_parts):
            result_parts.append(translated_part if is_string else new_part)
        return "".join(result_parts)

    @staticmethod
    def _split_qsp_expression_segments(text: str) -> list[tuple[bool, str]] | None:
        if not text:
            return []

        segments: list[tuple[bool, str]] = []
        code_start = 0
        index = 0
        length = len(text)

        while index < length:
            char = text[index]
            if char not in ("'", '"'):
                index += 1
                continue

            if code_start < index:
                segments.append((False, text[code_start:index]))

            quote = char
            string_start = index
            index += 1

            while index < length:
                current = text[index]
                if current == quote:
                    if index + 1 < length and text[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    segments.append((True, text[string_start:index]))
                    code_start = index
                    break
                index += 1
            else:
                return None

        if code_start < length:
            segments.append((False, text[code_start:]))
        return segments

    def _take_template_similarity_match(
        self,
        new_entry: ParatranzData,
        template_shape_map: dict[str, list[ParatranzData]],
        matched_old_ids: set[int],
    ) -> ParatranzData | None:
        new_payload = new_entry.extract_template_payload_from_context()
        if not new_payload or new_payload.get("kind") != "line-template":
            return None

        new_exprs = new_payload.get("expressions", [])
        new_source = new_payload.get("source", "")
        if not new_source or not isinstance(new_exprs, list):
            return None

        new_shape = self._placeholderize_template_text(new_source, new_exprs)
        if not new_shape:
            return None

        best_key: str | None = None
        best_score = 0.0

        for shape_key, candidates in template_shape_map.items():
            if self._peek_unmatched_candidate(candidates, matched_old_ids) is None:
                continue
            try:
                shape_data = json.loads(shape_key)
            except Exception:
                continue
            if shape_data.get("expr_count") != len(new_exprs):
                continue
            old_shape = str(shape_data.get("shape", ""))
            score = SequenceMatcher(None, self._normalize_qsp_code_for_match(new_shape), old_shape).ratio()
            if score < 0.92 or score <= best_score:
                continue
            best_key = shape_key
            best_score = score

        if best_key is None:
            return None
        return self._peek_best_candidate(template_shape_map.get(best_key, []), matched_old_ids)

    def _take_fuzzy_context_match(
        self,
        old_entry: ParatranzData,
        unmatched_new_slots: list[tuple[int, ParatranzData]],
    ) -> tuple[int, ParatranzData] | None:
        old_type = self._extract_entry_type(old_entry)
        old_text = self._normalize_entry_for_fuzzy(old_entry)
        old_human_text = self._normalize_human_text_for_fuzzy(old_entry)
        if not old_text:
            return None

        old_pos = old_entry.extract_pos_from_context()
        dmp = diff_match_patch()
        best_match: tuple[float, int, ParatranzData] | None = None

        for slot_index, new_entry in unmatched_new_slots:
            if old_type != self._extract_entry_type(new_entry):
                continue

            new_text = self._normalize_entry_for_fuzzy(new_entry)
            new_human_text = self._normalize_human_text_for_fuzzy(new_entry)
            if not new_text:
                continue

            ratio_score = max(fuzz.ratio(old_text, new_text), fuzz.partial_ratio(old_text, new_text))
            token_score = fuzz.token_set_ratio(old_text, new_text)
            human_ratio = 0
            human_token_score = 0
            if old_human_text and new_human_text:
                human_ratio = max(fuzz.ratio(old_human_text, new_human_text), fuzz.partial_ratio(old_human_text, new_human_text))
                human_token_score = fuzz.token_set_ratio(old_human_text, new_human_text)

            if (
                ratio_score < _FUZZY_MIN_RATIO
                and token_score < _FUZZY_MIN_RATIO
                and human_ratio < _FUZZY_MIN_RATIO
                and human_token_score < _FUZZY_MIN_RATIO
            ):
                continue

            diff_score = self._calculate_diff_similarity(dmp, old_text, new_text)
            if diff_score < _FUZZY_MIN_DIFF_SCORE:
                continue

            position_score = self._calculate_position_similarity(old_pos, new_entry.extract_pos_from_context())
            combined = (
                ratio_score * 0.28
                + token_score * 0.14
                + human_ratio * 0.18
                + human_token_score * 0.12
                + diff_score * 100 * 0.18
                + position_score * 0.10
            )
            if combined < _FUZZY_MIN_SCORE:
                continue

            if best_match is None or combined > best_match[0]:
                best_match = (combined, slot_index, new_entry)

        if best_match is None:
            return None
        return best_match[1], best_match[2]

    @staticmethod
    def _peek_unmatched_candidate(
        candidates: list[ParatranzData],
        matched_old_ids: set[int],
    ) -> ParatranzData | None:
        for candidate in candidates:
            if id(candidate) not in matched_old_ids:
                return candidate
        return None

    @staticmethod
    def _peek_best_candidate(
        candidates: list[ParatranzData],
        matched_old_ids: set[int],
    ) -> ParatranzData | None:
        best_rank: tuple[int, int, int] | None = None
        best_candidate: ParatranzData | None = None
        for index, candidate in enumerate(candidates):
            if id(candidate) in matched_old_ids:
                continue
            rank = (
                0 if candidate.translation else 1,
                0 if int(candidate.stage) != -1 else 1,
                index,
            )
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_candidate = candidate
        return best_candidate

    def _is_superseded_old_entry(
        self,
        old_entry: ParatranzData,
        *,
        merged_exact: set[str],
        merged_normalized: set[str],
        merged_template_signatures: set[str],
        merged_template_shapes: set[str],
    ) -> bool:
        if old_entry.original in merged_exact:
            return True
        if self._normalize_text(old_entry.original) in merged_normalized:
            return True

        template_signature = self._extract_template_signature(old_entry)
        if template_signature and template_signature in merged_template_signatures:
            return True

        template_shape = self._extract_template_shape(old_entry)
        if template_shape and template_shape in merged_template_shapes:
            return True

        return False

    @classmethod
    def _normalize_entry_for_fuzzy(cls, entry: ParatranzData) -> str:
        template_data = cls._extract_template_data(entry)
        if template_data is not None:
            source, _ = template_data
            return cls._normalize_qsp_code_for_match(source)
        return cls._normalize_text(entry.original)

    @classmethod
    def _normalize_human_text_for_fuzzy(cls, entry: ParatranzData) -> str:
        text = cls._extract_human_text_from_entry(entry)
        text = re.sub(r"\s+", " ", text).strip().casefold()
        return text

    @classmethod
    def _extract_human_text_from_entry(cls, entry: ParatranzData) -> str:
        template_data = cls._extract_template_data(entry)
        if template_data is not None:
            source, _ = template_data
            segments = QsrcLocalizationExtractor._split_top_level_concat(source)
            literal_parts: list[str] = []
            for segment in segments:
                literal_text = QsrcLocalizationExtractor._parse_string_token(segment)
                if literal_text is not None:
                    visible = QsrcLocalizationExtractor._extract_visible_text(literal_text)
                    if visible:
                        literal_parts.append(visible)
            if literal_parts:
                return " ".join(literal_parts)
        return QsrcLocalizationExtractor._extract_visible_text(entry.original)

    @staticmethod
    def _extract_entry_type(entry: ParatranzData) -> str:
        parts = (entry.key or "").split("|")
        for part in parts:
            if part in {"act", "text", "var", "msg"}:
                return part
        return ""

    @staticmethod
    def _calculate_diff_similarity(dmp: diff_match_patch, left: str, right: str) -> float:
        diffs = dmp.diff_main(left, right)
        dmp.diff_cleanupSemantic(diffs)
        max_length = max(len(left), len(right), 1)
        distance = dmp.diff_levenshtein(diffs)
        return max(0.0, 1.0 - (distance / max_length))

    @staticmethod
    def _calculate_position_similarity(old_pos: int | None, new_pos: int | None) -> float:
        if old_pos is None or new_pos is None:
            return 50.0
        distance = abs(old_pos - new_pos)
        if distance >= 6000:
            return 0.0
        return max(0.0, 100.0 - (distance / 60.0))

    @staticmethod
    def _should_archive_obsolete(entry: ParatranzData) -> bool:
        extractor = QsrcLocalizationExtractor()
        return extractor.is_entry_extractable(entry)

    def _should_keep_old_entry(self, entry: ParatranzData) -> bool:
        return self.extractor.is_entry_extractable(entry)

    @staticmethod
    def _resolve_migrated_stage(entry: ParatranzData) -> StageEnum:
        if entry.translation and int(entry.stage) == -1:
            return StageEnum(1)
        return entry.stage

    @staticmethod
    def _mark_entry_obsolete(entry: ParatranzData, reason: str) -> ParatranzData:
        context = entry.context.strip()
        marker = f"{_OBSOLETE_MARKER} {reason}".strip()
        if context:
            context = f"{context}\n{marker}"
        else:
            context = marker
        return ParatranzData(
            key=entry.key,
            original=entry.original,
            translation=entry.translation,
            stage=StageEnum(-1),
            context=context,
        )

    @staticmethod
    def _write_entries(output_path: Path, entries: list[ParatranzData]) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.model_dump(mode="json") for entry in entries]
        output_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def sync_paratranz(
    *,
    source_root: Path | None = None,
    old_paratranz_root: Path | None = None,
    output_root: Path | None = None,
    clear_output: bool = True,
    show_progress: bool = False,
) -> SyncStats:
    service = ParatranzSyncService()
    return service.sync(
        source_root=source_root,
        old_paratranz_root=old_paratranz_root,
        output_root=output_root,
        clear_output=clear_output,
        show_progress=show_progress,
    )


def extract_paratranz_entries(
    *,
    source_root: Path,
) -> dict[Path, list[ParatranzData]]:
    service = ParatranzSyncService()
    return service.extract_entries(Path(source_root).resolve())


def extract_paratranz_to_dir(
    *,
    source_root: Path | None = None,
    output_root: Path | None = None,
    clear_output: bool = True,
    show_progress: bool = False,
) -> SyncStats:
    service = ParatranzSyncService()
    return service.export_entries(
        source_root=Path(source_root).resolve() if source_root else None,
        output_root=Path(output_root).resolve() if output_root else None,
        clear_output=clear_output,
        show_progress=show_progress,
    )


__all__ = [
    "ParatranzSyncService",
    "QsrcLocalizationExtractor",
    "SyncStats",
    "extract_paratranz_entries",
    "extract_paratranz_to_dir",
    "sync_paratranz",
]
