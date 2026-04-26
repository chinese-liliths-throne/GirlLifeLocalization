from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.qsrc import get_qsrc_validator

from .project import CoreProject


@dataclass(slots=True)
class CoreDocument:
    path: Path
    relative_path: Path
    original_text: str
    current_text: str
    dirty: bool = False
    issues: tuple[object, ...] = ()


class EditorCoreService:
    def open_document(self, project: CoreProject, path: Path | str) -> CoreDocument:
        file_path = Path(path).resolve()
        text = file_path.read_text(encoding="utf-8")
        return CoreDocument(
            path=file_path,
            relative_path=file_path.relative_to(project.root),
            original_text=text,
            current_text=text,
        )

    def save_document(self, document: CoreDocument) -> CoreDocument:
        document.path.write_text(document.current_text, encoding="utf-8")
        document.original_text = document.current_text
        document.dirty = False
        return document

    def lint_document(self, document: CoreDocument) -> tuple[object, ...]:
        validator = get_qsrc_validator()
        if document.current_text.lstrip().startswith("#"):
            result = validator.validate_passage_text(document.current_text)
        else:
            result = validator.validate_text(document.current_text, location_name=document.path.stem)
        document.issues = tuple(result.issues)
        return document.issues
