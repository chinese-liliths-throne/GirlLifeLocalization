from __future__ import annotations

from pathlib import Path

from src.build.service import BuildService
from src.config.paths import detect_source_root, detect_translation_root, paths
from src.localization.manager import LocalizationManager
from src.qsp_runtime import QspRuntimeRunner, RuntimeSnapshot
from src.qsrc import get_qsrc_validator

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
    def open_project(self, target: Path | str) -> ProjectModel:
        root = Path(target).resolve()
        if root.is_file():
            root = root.parent
        qsrc_files = tuple(sorted(root.rglob("*.qsrc")))
        mod_files = tuple(path for path in qsrc_files if "mods" in path.parts)
        qproj_path = next(iter(root.glob("*.qproj")), None)
        project_type = "girl-life" if (root / "locations").exists() else "qsrc-folder"
        return ProjectModel(
            root=root,
            project_type=project_type,
            qsrc_files=qsrc_files,
            mod_files=mod_files,
            qproj_path=qproj_path,
        )

    def search(self, project: ProjectModel, query: str) -> tuple[SearchResult, ...]:
        needle = query.strip()
        if not needle:
            return ()
        results: list[SearchResult] = []
        for file_path in project.qsrc_files:
            for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
                if needle.casefold() in line.casefold():
                    results.append(SearchResult(path=file_path, line_no=line_no, line_text=line.strip()))
        return tuple(results)


class EditorService:
    def open_document(self, project: ProjectModel, path: Path | str) -> DocumentModel:
        file_path = Path(path).resolve()
        text = file_path.read_text(encoding="utf-8")
        return DocumentModel(
            path=file_path,
            relative_path=file_path.relative_to(project.root),
            original_text=text,
            current_text=text,
        )

    def save_document(self, document: DocumentModel) -> DocumentModel:
        document.path.write_text(document.current_text, encoding="utf-8")
        document.original_text = document.current_text
        document.dirty = False
        return document

    def lint_document(self, document: DocumentModel) -> tuple[object, ...]:
        validator = get_qsrc_validator()
        if document.current_text.lstrip().startswith("#"):
            result = validator.validate_passage_text(document.current_text)
        else:
            result = validator.validate_text(document.current_text, location_name=document.path.stem)
        document.issues = tuple(result.issues)
        return document.issues


class RuntimeService:
    def __init__(self, host_mode: HostMode, *, root: Path):
        self.host_mode = host_mode
        self.runner = QspRuntimeRunner(root)

    def available(self) -> bool:
        return self.runner.available()

    def load_world(self, world_path: Path | str | None = None) -> RuntimeSnapshotViewModel:
        result = self.runner.ensure_loaded(world_path)
        return self._to_view_model(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def exec_location(self, location_name: str, *, world_path: Path | str | None = None) -> RuntimeSnapshotViewModel:
        result = self.runner.exec_location(location_name, world_path=world_path)
        return self._to_view_model(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def execute_action(self, index: int) -> RuntimeSnapshotViewModel:
        result = self.runner.execute_action(index)
        return self._to_view_model(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def submit_input(self, text: str) -> RuntimeSnapshotViewModel:
        result = self.runner.submit_input(text)
        return self._to_view_model(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def snapshot(self) -> RuntimeSnapshotViewModel:
        return self._to_view_model(self.runner.snapshot())

    @staticmethod
    def _to_view_model(snapshot: RuntimeSnapshot) -> RuntimeSnapshotViewModel:
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
        self.service = BuildService()

    def build_project(self, project: ProjectModel) -> BuildResultViewModel:
        build_dir = self.service.reset_build_dir(paths.build)
        if project.qproj_path and (project.root / "locations").exists():
            artifact = self.service.build_game(project.root, build_dir, show_progress=False)
            return BuildResultViewModel(
                success=artifact.success,
                summary=f"已构建 {artifact.name}",
                output_paths=(artifact.output_game, artifact.output_txt),
                error_paths=(paths.build_errors(build_dir),),
            )
        return BuildResultViewModel(
            success=False,
            summary="当前项目没有可用于构建的 glife.qproj 根目录。",
            error_paths=(paths.build_errors(build_dir),),
        )


class LocalizationServiceAdapter:
    def run_replace(self) -> str:
        source_root = detect_source_root(paths.source_parent)
        translation_root = detect_translation_root(paths.translation_parent)
        if not source_root or not translation_root:
            return "缺少源码目录或 ParaTranz 翻译目录。"
        manager = LocalizationManager(
            source_dir=source_root,
            paratranz_dir=translation_root,
            result_dir=paths.result,
            show_progress=False,
        )
        stats = manager.translate()
        return (
            f"替换完成：成功 {stats.translated}，失败 {stats.failed}，"
            f"缺少源文 {stats.missing_source}，跳过词条 {stats.skipped_entries}"
        )


__all__ = [
    "BuildServiceAdapter",
    "EditorService",
    "LocalizationServiceAdapter",
    "ProjectService",
    "RuntimeService",
]
