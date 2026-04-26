from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CoreProject:
    root: Path
    project_type: str
    qsrc_files: tuple[Path, ...]
    mod_files: tuple[Path, ...]
    qproj_path: Path | None = None


@dataclass(slots=True)
class CoreSearchResult:
    path: Path
    line_no: int
    line_text: str


class ProjectCoreService:
    def open_project(self, target: Path | str) -> CoreProject:
        root = Path(target).resolve()
        if root.is_file():
            root = root.parent
        qsrc_files = tuple(sorted(root.rglob("*.qsrc")))
        mod_files = tuple(path for path in qsrc_files if "mods" in path.parts)
        qproj_path = next(iter(root.glob("*.qproj")), None)
        project_type = "girl-life" if (root / "locations").exists() else "qsrc-folder"
        return CoreProject(
            root=root,
            project_type=project_type,
            qsrc_files=qsrc_files,
            mod_files=mod_files,
            qproj_path=qproj_path,
        )

    def search(self, project: CoreProject, query: str) -> tuple[CoreSearchResult, ...]:
        needle = query.strip()
        if not needle:
            return ()
        results: list[CoreSearchResult] = []
        for file_path in project.qsrc_files:
            for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
                if needle.casefold() in line.casefold():
                    results.append(CoreSearchResult(path=file_path, line_no=line_no, line_text=line.strip()))
        return tuple(results)
