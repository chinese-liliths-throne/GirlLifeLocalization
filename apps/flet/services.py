from __future__ import annotations

from pathlib import Path

from src.core import BuildCoreService, CoreDocument, CoreProject, EditorCoreService, LocalizationCoreService, ProjectCoreService, RuntimeCoreService

from .models import (
    BuildResultViewModel,
    DocumentModel,
    HostMode,
    ProjectModel,
    RuntimeActionViewModel,
    RuntimeObjectViewModel,
    RuntimeSnapshotViewModel,
    SearchResult,
)


class ProjectService:
    def __init__(self) -> None:
        self.core = ProjectCoreService()

    def open_project(self, target: Path | str) -> ProjectModel:
        project = self.core.open_project(target)
        return ProjectModel(
            root=project.root,
            project_type=project.project_type,
            qsrc_files=project.qsrc_files,
            mod_files=project.mod_files,
            qproj_path=project.qproj_path,
        )

    def search(self, project: ProjectModel, query: str) -> tuple[SearchResult, ...]:
        results = self.core.search(_to_core_project(project), query)
        return tuple(SearchResult(path=item.path, line_no=item.line_no, line_text=item.line_text) for item in results)


class EditorService:
    def __init__(self) -> None:
        self.core = EditorCoreService()

    def open_document(self, project: ProjectModel, path: Path | str) -> DocumentModel:
        core_document = self.core.open_document(_to_core_project(project), path)
        return DocumentModel(
            path=core_document.path,
            relative_path=core_document.relative_path,
            original_text=core_document.original_text,
            current_text=core_document.current_text,
            dirty=core_document.dirty,
            issues=core_document.issues,
        )

    def save_document(self, document: DocumentModel) -> DocumentModel:
        self.core.save_document(_to_core_document(document))
        document.original_text = document.current_text
        document.dirty = False
        return document

    def lint_document(self, document: DocumentModel) -> tuple[object, ...]:
        document.issues = tuple(self.core.lint_document(_to_core_document(document)))
        return document.issues


class RuntimeService:
    def __init__(self, host_mode: HostMode, *, root: Path):
        self.host_mode = host_mode
        self.runner = RuntimeCoreService(root)

    def available(self) -> bool:
        return self.runner.available()

    def load_world(self, world_path: Path | str | None = None) -> RuntimeSnapshotViewModel:
        return self._to_view_model(self.runner.load_world(world_path))

    def exec_location(self, location_name: str, *, world_path: Path | str | None = None) -> RuntimeSnapshotViewModel:
        return self._to_view_model(self.runner.exec_location(location_name, world_path=world_path))

    def execute_action(self, index: int) -> RuntimeSnapshotViewModel:
        return self._to_view_model(self.runner.execute_action(index))

    def submit_input(self, text: str) -> RuntimeSnapshotViewModel:
        return self._to_view_model(self.runner.submit_input(text))

    def snapshot(self) -> RuntimeSnapshotViewModel:
        return self._to_view_model(self.runner.snapshot())

    @staticmethod
    def _to_view_model(snapshot) -> RuntimeSnapshotViewModel:
        return RuntimeSnapshotViewModel(
            loaded=snapshot.loaded,
            world_path=snapshot.world_path,
            current_location=snapshot.current_location,
            main_desc=snapshot.main_desc,
            vars_desc=snapshot.vars_desc,
            actions=tuple(
                RuntimeActionViewModel(index=item.index, text=item.text, image_path=item.image_path)
                for item in snapshot.actions
            ),
            objects=tuple(
                RuntimeObjectViewModel(index=item.index, text=item.text, image_path=item.image_path)
                for item in snapshot.objects
            ),
            runtime_error=snapshot.runtime_error,
        )


class BuildServiceAdapter:
    def __init__(self) -> None:
        self.service = BuildCoreService()

    def build_project(self, project: ProjectModel) -> BuildResultViewModel:
        result = self.service.build_project(_to_core_project(project))
        return BuildResultViewModel(
            success=result.success,
            summary=result.summary,
            output_paths=result.output_paths,
            error_paths=result.error_paths,
        )


class LocalizationServiceAdapter:
    def __init__(self) -> None:
        self.core = LocalizationCoreService()

    def run_replace(self) -> str:
        return self.core.run_replace()


def _to_core_project(project: ProjectModel) -> CoreProject:
    return CoreProject(
        root=project.root,
        project_type=project.project_type,
        qsrc_files=project.qsrc_files,
        mod_files=project.mod_files,
        qproj_path=project.qproj_path,
    )


def _to_core_document(document: DocumentModel) -> CoreDocument:
    return CoreDocument(
        path=document.path,
        relative_path=document.relative_path,
        original_text=document.original_text,
        current_text=document.current_text,
        dirty=document.dirty,
        issues=document.issues,
    )
