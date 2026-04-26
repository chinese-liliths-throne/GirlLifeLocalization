import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.paths import paths


@dataclass(slots=True)
class BufferedReport:
    target: Path
    lines: list[str]


class ErrorReporter:
    """把错误按分类和源文件归档到 errors 目录。"""

    def __init__(self, root: Path | str):
        self.root = paths.ensure_inside_workspace(Path(root).resolve())
        self.root.mkdir(parents=True, exist_ok=True)
        self._buffer_enabled = False
        self._buffer: list[BufferedReport] = []
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root.mkdir(parents=True, exist_ok=True)
            self._buffer.clear()

    def begin_buffering(self) -> None:
        with self._lock:
            self._buffer_enabled = True
            self._buffer.clear()

    def flush_buffer(self) -> None:
        with self._lock:
            for item in self._buffer:
                item.target.parent.mkdir(parents=True, exist_ok=True)
                with item.target.open("a", encoding="utf-8", newline="\n") as file:
                    file.write("\n".join(item.lines).rstrip())
                    file.write("\n\n")
            self._buffer.clear()
            self._buffer_enabled = False

    def discard_buffer(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._buffer_enabled = False

    def report(
        self,
        category: str,
        source_path: Path | str,
        message: str,
        *,
        details: Iterable[str] = (),
        source_root: Path | str | None = None,
    ) -> Path:
        target = self._target_path(category, Path(source_path), source_root=source_root)
        target.parent.mkdir(parents=True, exist_ok=True)

        lines = self._format_report_lines(
            category=category,
            source_path=Path(source_path),
            source_root=source_root,
            message=message,
            details=details,
        )
        with self._lock:
            if self._buffer_enabled:
                self._buffer.append(BufferedReport(target=target, lines=lines))
                return target
            with target.open("a", encoding="utf-8", newline="\n") as file:
                file.write("\n".join(lines).rstrip())
                file.write("\n\n")
        return target

    def _target_path(self, category: str, source_path: Path, *, source_root: Path | str | None) -> Path:
        relative = self._relative_source_path(source_path, source_root=source_root)
        target = self.root / category / relative
        if target.suffix:
            return target.with_suffix(target.suffix + ".diff")
        return target / "_error.diff"

    def _format_report_lines(
        self,
        *,
        category: str,
        source_path: Path,
        source_root: Path | str | None,
        message: str,
        details: Iterable[str],
    ) -> list[str]:
        relative = self._relative_source_path(source_path, source_root=source_root).as_posix()
        lines = [
            f"# category: {category}",
            f"# source: {relative}",
            f"# message: {message}",
            "#",
        ]
        for item in details:
            if item is None:
                continue
            for line in str(item).splitlines() or [""]:
                lines.append(self._format_detail_line(line))
        return lines

    @staticmethod
    def _format_detail_line(line: str) -> str:
        if not line:
            return "#"
        if line.startswith(("--- ", "+++ ", "@@ ", "-", "+", " ")):
            return line
        return f"# {line}"

    def _relative_source_path(self, source_path: Path, *, source_root: Path | str | None) -> Path:
        normalized = source_path
        if source_root is not None:
            root = Path(source_root).resolve()
            if not normalized.is_absolute():
                normalized = (root / normalized).resolve()
            else:
                normalized = normalized.resolve()
            try:
                return normalized.relative_to(root)
            except ValueError:
                pass

        if normalized.is_absolute():
            normalized = normalized.resolve()
            try:
                return normalized.relative_to(paths.root)
            except ValueError:
                return Path("_external") / normalized.name

        clean_parts = [part for part in normalized.parts if part not in ("", ".", "..")]
        if clean_parts:
            return Path(*clean_parts)
        return Path("_misc") / "unknown"


__all__ = ["ErrorReporter"]
