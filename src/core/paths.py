from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from .configuration import settings


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """集中管理项目目录，避免各模块各自拼路径。"""

    root: Path
    data: Path
    tmp: Path
    source_parent: Path
    translation_parent: Path
    result: Path
    process: Path
    build: Path
    sync: Path
    logs: Path

    @classmethod
    def from_settings(cls) -> "ProjectPaths":
        filepath = settings.filepath
        root = filepath.root.resolve()
        return cls(
            root=root,
            data=(root / filepath.data).resolve(),
            tmp=(root / filepath.tmp).resolve(),
            source_parent=(root / filepath.source).resolve(),
            translation_parent=(root / filepath.download).resolve(),
            result=(root / filepath.result).resolve(),
            process=(root / filepath.process).resolve(),
            build=(root / filepath.build).resolve(),
            sync=(root / "sync").resolve(),
            logs=(root / filepath.data / "logs").resolve(),
        )

    def ensure_base_dirs(self) -> None:
        for path in (
            self.data,
            self.tmp,
            self.source_parent,
            self.translation_parent,
            self.result,
            self.process,
            self.build,
            self.sync,
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def ensure_inside_workspace(self, path: Path) -> Path:
        target = path.resolve()
        if target == self.root or self.root not in target.parents:
            raise ValueError(f"拒绝操作项目目录之外或项目根目录本身: {target}")
        return target

    def source_archive(self, source_label: str) -> Path:
        return self.tmp / f"girl_life_{source_label}.zip"

    def build_txt(self) -> Path:
        return self.build / "glife.txt"

    def build_game(self) -> Path:
        return self.build / "glife.qsp"

    def build_errors(self, build_dir: Path | None = None) -> Path:
        return (build_dir or self.build).resolve() / "errors"


paths = ProjectPaths.from_settings()


def _contains_project_markers(root: Path) -> bool:
    return any((root / name).exists() for name in ("locations", "mods", "glife.qproj"))


def _first_subdir(root: Path) -> Path | None:
    if not root.exists():
        return None
    subdirs = sorted(path for path in root.iterdir() if path.is_dir())
    return subdirs[0] if subdirs else None


def detect_source_root(source_parent: Path | None = None) -> Path | None:
    """识别 Girl Life 源码根目录。"""

    root = (source_parent or paths.source_parent).resolve()
    if _contains_project_markers(root):
        return root
    return _first_subdir(root)


def detect_translation_root(translation_parent: Path | None = None) -> Path | None:
    """识别 ParaTranz 导出根目录。"""

    root = (translation_parent or paths.translation_parent).resolve()
    if not root.exists():
        return None
    if _contains_project_markers(root) or list(root.glob("*.json")):
        return root
    first = _first_subdir(root)
    if first and (_contains_project_markers(first) or list(first.rglob("*.json"))):
        return first
    return root if list(root.rglob("*.json")) else None


def safe_extract_zip(archive: ZipFile, destination: Path) -> None:
    """安全解压 zip，阻止路径穿越。"""

    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != destination and destination not in target.parents:
            raise RuntimeError(f"压缩包包含不安全路径: {member.filename}")
    archive.extractall(destination)


__all__ = ["ProjectPaths", "paths", "detect_source_root", "detect_translation_root", "safe_extract_zip"]
