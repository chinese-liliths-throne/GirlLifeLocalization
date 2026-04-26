from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class HostMode(StrEnum):
    DESKTOP = "desktop"
    WEB = "web"
    ANDROID = "android"


@dataclass(slots=True)
class ProjectModel:
    root: Path
    project_type: str
    qsrc_files: tuple[Path, ...]
    mod_files: tuple[Path, ...]
    qproj_path: Path | None = None


@dataclass(slots=True)
class DocumentModel:
    path: Path
    relative_path: Path
    original_text: str
    current_text: str
    dirty: bool = False
    issues: tuple[object, ...] = ()


@dataclass(slots=True)
class SearchResult:
    path: Path
    line_no: int
    line_text: str


@dataclass(slots=True)
class BuildResultViewModel:
    success: bool
    summary: str
    output_paths: tuple[Path, ...] = ()
    error_paths: tuple[Path, ...] = ()


@dataclass(slots=True)
class RuntimeActionViewModel:
    index: int
    text: str
    image_path: str = ""


@dataclass(slots=True)
class RuntimeObjectViewModel:
    index: int
    text: str
    image_path: str = ""


@dataclass(slots=True)
class RuntimeSnapshotViewModel:
    loaded: bool = False
    world_path: str = ""
    current_location: str = ""
    main_desc: str = ""
    vars_desc: str = ""
    actions: tuple[RuntimeActionViewModel, ...] = ()
    objects: tuple[RuntimeObjectViewModel, ...] = ()
    runtime_error: str = ""


@dataclass(slots=True)
class WorkbenchState:
    host_mode: HostMode
    project: ProjectModel | None = None
    open_documents: dict[Path, DocumentModel] = field(default_factory=dict)
    active_document: Path | None = None
    runtime_snapshot: RuntimeSnapshotViewModel = field(default_factory=RuntimeSnapshotViewModel)
    last_build: BuildResultViewModel | None = None
    status_text: str = "就绪"
