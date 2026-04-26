from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.build_service import BuildService
from src.core.paths import paths

from .project import CoreProject


@dataclass(slots=True)
class CoreBuildResult:
    success: bool
    summary: str
    output_paths: tuple[Path, ...] = ()
    error_paths: tuple[Path, ...] = ()


class BuildCoreService:
    def __init__(self) -> None:
        self.service = BuildService()

    def build_project(self, project: CoreProject) -> CoreBuildResult:
        build_dir = self.service.reset_build_dir(paths.build)
        if project.qproj_path and (project.root / "locations").exists():
            artifact = self.service.build_game(project.root, build_dir, show_progress=False)
            return CoreBuildResult(
                success=artifact.success,
                summary=f"已构建 {artifact.name}",
                output_paths=(artifact.output_game, artifact.output_txt),
                error_paths=(paths.build_errors(build_dir),),
            )
        return CoreBuildResult(
            success=False,
            summary="当前项目没有可用于构建的 glife.qproj 根目录。",
            error_paths=(paths.build_errors(build_dir),),
        )
