import shutil
from dataclasses import dataclass, field
from pathlib import Path

from src.error_reporter import ErrorReporter
from src.file_manager import FileManager
from src.log import logger
from src.paths import detect_source_root, paths
from src.progress import ProgressBar, copy_tree_with_progress
from src.qsrc_guard import QsrcBuildGuard
from src.qsrc_runtime_checker import QsrcRuntimeChecker
from src.thirdparty.txt2gam import build_qproj_to_gam


@dataclass(frozen=True, slots=True)
class BuildArtifact:
    """一次 qproj 打包产物。"""

    name: str
    qproj: Path
    locations_dir: Path
    output_txt: Path
    output_game: Path
    success: bool


@dataclass(frozen=True, slots=True)
class ModBuildSummary:
    """Mod 打包汇总。"""

    artifacts: tuple[BuildArtifact, ...] = ()
    missing_mods: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return not self.missing_mods and all(artifact.success for artifact in self.artifacts)


@dataclass(frozen=True, slots=True)
class ModBuildTarget:
    """可打包的 mod qproj。"""

    name: str
    qproj: Path
    locations_dir: Path
    output_dir: Path
    aliases: frozenset[str] = field(default_factory=frozenset)


class BuildService:
    """负责生成第 4 步源码，并打包本体与 mod。"""

    def reset_build_dir(self, build_dir: Path) -> Path:
        """打包前重建 build 输出目录。"""
        output_dir = paths.ensure_inside_workspace(build_dir.resolve())
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("已清空打包输出目录: {}", output_dir)
        return output_dir

    def prepare_build_source(
        self,
        process_dir: Path | None = None,
        *,
        skip_validation: bool = False,
        show_progress: bool = False,
        error_reporter: ErrorReporter | None = None,
    ) -> Path | None:
        """第 4 步：用 3-SourceTranslatedFile 覆盖 1-SourceFile，生成打包源码。"""

        source_root = detect_source_root(paths.source_parent)
        translated_root = detect_source_root(paths.result)
        process_root = (process_dir or paths.process).resolve()

        if not source_root:
            logger.error("无法准备第 4 步：找不到 1-SourceFile 源码根目录。")
            self._report_build_error(
                error_reporter,
                "build-prepare",
                paths.source_parent,
                "找不到 1-SourceFile 源码根目录，无法生成第 4 步打包源码。",
                source_root=paths.root,
            )
            return None
        if not translated_root:
            logger.error("无法准备第 4 步：找不到 3-SourceTranslatedFile 本地化源码目录。")
            self._report_build_error(
                error_reporter,
                "build-prepare",
                paths.result,
                "找不到 3-SourceTranslatedFile 本地化源码目录，无法生成第 4 步打包源码。",
                source_root=paths.root,
            )
            return None

        process_root = paths.ensure_inside_workspace(process_root)
        shutil.rmtree(process_root, ignore_errors=True)
        copy_tree_with_progress(source_root, process_root, enabled=show_progress, desc="Build Source")
        locked_files: set[Path] = set()
        if not skip_validation:
            locked_files, _ = QsrcBuildGuard(
                source_root=source_root,
                translated_root=translated_root,
                error_reporter=error_reporter,
                show_progress=show_progress,
            ).collect_locked_files()
            runtime_locked_files, _ = QsrcRuntimeChecker(
                source_root=source_root,
                translated_root=translated_root,
                error_reporter=error_reporter,
                show_progress=show_progress,
            ).collect_locked_files()
            locked_files |= runtime_locked_files
        self._overlay_translated_files(
            translated_root=translated_root,
            process_root=process_root,
            locked_files=locked_files,
            show_progress=show_progress,
        )
        logger.success("第 4 步打包源码已生成: {}", process_root)
        return process_root

    def build_game(
        self,
        build_source_root: Path,
        build_dir: Path,
        *,
        strict_check: bool = False,
        qproj: Path | None = None,
        output_txt: Path | None = None,
        output_game: Path | None = None,
        show_progress: bool = False,
        error_reporter: ErrorReporter | None = None,
    ) -> BuildArtifact:
        build_dir = self._prepare_output_dir(build_dir)
        qproj = (qproj or (build_source_root / "glife.qproj")).resolve()
        locations_dir = (build_source_root / "locations").resolve()
        output_txt = (output_txt or (build_dir / "glife.txt")).resolve()
        output_game = (output_game or (build_dir / "glife.qsp")).resolve()

        success = self._build_target(
            name="Girl Life 本体",
            qproj=qproj,
            locations_dir=locations_dir,
            output_txt=output_txt,
            output_game=output_game,
            strict_check=strict_check,
            source_root=build_source_root,
            show_progress=show_progress,
            error_reporter=error_reporter,
        )
        return BuildArtifact(
            name="Girl Life 本体",
            qproj=qproj,
            locations_dir=locations_dir,
            output_txt=output_txt,
            output_game=output_game,
            success=success,
        )

    def build_mods(
        self,
        build_source_root: Path,
        build_dir: Path,
        *,
        strict_check: bool = False,
        selected_mods: tuple[str, ...] = (),
        show_progress: bool = False,
        error_reporter: ErrorReporter | None = None,
    ) -> ModBuildSummary:
        targets = self.discover_mods(build_source_root, build_dir)
        selected_targets, missing_mods = self._filter_mods(targets, selected_mods)

        if not targets:
            logger.info("未发现可打包的 mod qproj，已跳过 mod 打包。")
            return ModBuildSummary(missing_mods=missing_mods)
        if selected_mods and not selected_targets:
            logger.warning("没有匹配到指定 mod: {}", ", ".join(missing_mods))
            return ModBuildSummary(missing_mods=missing_mods)

        artifacts: list[BuildArtifact] = []
        with ProgressBar(total=len(selected_targets), enabled=show_progress, desc="Build Mods", unit="mod") as progress:
            for target in selected_targets:
                output_txt = target.output_dir / f"{target.qproj.stem}.txt"
                output_game = target.output_dir / f"{target.qproj.stem}.qsp"
                success = self._build_target(
                    name=f"Mod {target.name}",
                    qproj=target.qproj,
                    locations_dir=target.locations_dir,
                    output_txt=output_txt,
                    output_game=output_game,
                    strict_check=strict_check,
                    source_root=build_source_root,
                    show_progress=False,
                    error_reporter=error_reporter,
                )
                artifacts.append(
                    BuildArtifact(
                        name=target.name,
                        qproj=target.qproj,
                        locations_dir=target.locations_dir,
                        output_txt=output_txt,
                        output_game=output_game,
                        success=success,
                    )
                )
                progress.set_postfix_str(target.name)
                progress.update()

        if missing_mods:
            logger.warning("部分指定 mod 没有匹配到: {}", ", ".join(missing_mods))
        return ModBuildSummary(artifacts=tuple(artifacts), missing_mods=missing_mods)

    def discover_mods(self, build_source_root: Path, build_dir: Path) -> tuple[ModBuildTarget, ...]:
        mods_root = build_source_root / "mods"
        if not mods_root.exists():
            return ()

        mod_output_root = self._prepare_output_dir(build_dir) / "mods"
        targets: list[ModBuildTarget] = []
        for qproj in sorted(mods_root.rglob("*.qproj")):
            locations_dir = qproj.parent / "locations"
            mod_root = self._detect_mod_root(mods_root, qproj)
            name = mod_root.name
            aliases = frozenset(
                item.casefold()
                for item in (
                    name,
                    qproj.stem,
                    qproj.name,
                    str(qproj.relative_to(mods_root)),
                )
            )
            targets.append(
                ModBuildTarget(
                    name=name,
                    qproj=qproj,
                    locations_dir=locations_dir,
                    output_dir=mod_output_root / name,
                    aliases=aliases,
                )
            )
        return tuple(targets)

    def _build_target(
        self,
        *,
        name: str,
        qproj: Path,
        locations_dir: Path,
        output_txt: Path,
        output_game: Path,
        strict_check: bool,
        source_root: Path,
        show_progress: bool,
        error_reporter: ErrorReporter | None,
    ) -> bool:
        if not qproj.exists():
            logger.error("无法打包 {}：找不到 qproj 文件: {}", name, qproj)
            self._report_build_error(
                error_reporter,
                "build-prepare",
                qproj,
                f"找不到 qproj 文件，无法打包 {name}。",
                source_root=source_root,
            )
            return False
        if not locations_dir.exists():
            logger.error("无法打包 {}：找不到 locations 目录: {}", name, locations_dir)
            self._report_build_error(
                error_reporter,
                "build-prepare",
                locations_dir,
                f"找不到 locations 目录，无法打包 {name}。",
                source_root=source_root,
            )
            return False

        output_txt = paths.ensure_inside_workspace(output_txt.resolve())
        output_game = paths.ensure_inside_workspace(output_game.resolve())
        output_txt.parent.mkdir(parents=True, exist_ok=True)
        output_game.parent.mkdir(parents=True, exist_ok=True)
        logger.info("开始打包 {}: {} -> {}", name, locations_dir, output_game)

        with ProgressBar(total=1, enabled=show_progress, desc=name, unit="task") as progress:
            ok = build_qproj_to_gam(
                input_dir=str(locations_dir),
                qproj_file=str(qproj),
                output_txt=str(output_txt),
                output_game=str(output_game),
                check_syntax=strict_check,
                error_reporter=error_reporter,
                source_root=str(source_root),
            )
            progress.update()
        if ok:
            logger.success("{} 已输出: {}", name, output_game)
        return ok

    @staticmethod
    def _overlay_translated_files(
        *,
        translated_root: Path,
        process_root: Path,
        locked_files: set[Path],
        show_progress: bool,
    ) -> None:
        files = FileManager.get_qsrc_scripts(translated_root)
        with ProgressBar(total=len(files), enabled=show_progress, desc="Overlay Source", unit="file") as progress:
            for file in files:
                relative_path = Path(file.rel_path)
                if relative_path not in locked_files:
                    target_path = process_root / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file.path, target_path)
                progress.set_postfix_str(file.path.name)
                progress.update()

    @staticmethod
    def _detect_mod_root(mods_root: Path, qproj: Path) -> Path:
        relative = qproj.relative_to(mods_root)
        return mods_root / relative.parts[0] if len(relative.parts) > 1 else qproj.parent

    @staticmethod
    def _filter_mods(
        targets: tuple[ModBuildTarget, ...],
        selected_mods: tuple[str, ...],
    ) -> tuple[tuple[ModBuildTarget, ...], tuple[str, ...]]:
        if not selected_mods:
            return targets, ()

        selected: list[ModBuildTarget] = []
        missing: list[str] = []
        for mod_name in selected_mods:
            wanted = mod_name.casefold()
            target = next((item for item in targets if wanted in item.aliases), None)
            if target:
                selected.append(target)
            else:
                missing.append(mod_name)
        return tuple(dict.fromkeys(selected)), tuple(missing)

    @staticmethod
    def _prepare_output_dir(build_dir: Path) -> Path:
        output_dir = paths.ensure_inside_workspace(build_dir.resolve())
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @staticmethod
    def _report_build_error(
        error_reporter: ErrorReporter | None,
        category: str,
        source_path: Path,
        message: str,
        *,
        source_root: Path,
    ) -> None:
        if not error_reporter:
            return
        error_reporter.report(
            category,
            source_path,
            message,
            source_root=source_root,
        )


__all__ = [
    "BuildArtifact",
    "BuildService",
    "ModBuildSummary",
    "ModBuildTarget",
]
