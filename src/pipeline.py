from dataclasses import dataclass
from pathlib import Path

from src.build_service import BuildArtifact, BuildService
from src.error_reporter import ErrorReporter
from src.localization_manager import LocalizationManager, TranslationStats
from src.log import logger
from src.paratranz_precheck import precheck_paratranz
from src.paths import detect_source_root, detect_translation_root, paths
from src.progress import ProgressBar
from src.project_girl_life import ProjectGirlLife


@dataclass(slots=True)
class PipelineOptions:
    only_translate: bool = False
    skip_source: bool = False
    skip_paratranz: bool = False
    skip_translate: bool = False
    force_source: bool = False
    force_paratranz: bool = False
    precheck_mode: str = "fast"
    concurrency: int = 32
    memory_limit_mb: int | None = None
    copy_source: bool = False
    show_progress: bool = False
    build_game: bool = True
    build_mods: bool = True
    build_dir: Path | None = None
    process_dir: Path | None = None
    strict_build_check: bool = False
    mod_names: tuple[str, ...] = ()
    qproj: Path | None = None
    output_txt: Path | None = None
    output_game: Path | None = None


@dataclass(slots=True)
class PipelineResult:
    exit_code: int = 0
    translation_stats: TranslationStats | None = None
    built_game: bool = False
    built_mods: tuple[BuildArtifact, ...] = ()
    missing_mods: tuple[str, ...] = ()


class ApplicationPipeline:
    def __init__(self, options: PipelineOptions):
        self.options = options
        self.project = ProjectGirlLife()
        self.build_service = BuildService()

    async def run(self) -> PipelineResult:
        result = PipelineResult()
        skip_source = self.options.only_translate or self.options.skip_source
        skip_paratranz = self.options.only_translate or self.options.skip_paratranz
        build_dir = (self.options.build_dir or paths.build).resolve()
        if self.options.build_game:
            build_dir = self.build_service.reset_build_dir(build_dir)

        error_reporter = ErrorReporter(paths.build_errors(build_dir))
        error_reporter.clear()

        stage_total = 0
        stage_total += 1 if not skip_source else 0
        stage_total += 1 if not skip_paratranz else 0
        stage_total += 1 if not self.options.skip_translate else 0
        stage_total += 1 if not self.options.skip_translate else 0
        stage_total += 1 if self.options.build_game else 0
        stage_total += 1 if self.options.build_game and self.options.build_mods else 0

        source_root: Path | None = None
        working_paratranz_root: Path | None = None

        with ProgressBar(total=stage_total, enabled=self.options.show_progress, desc="Pipeline", unit="stage") as progress:
            if not skip_source:
                await self.project.download_from_gitlab(
                    force=self.options.force_source,
                    show_progress=self.options.show_progress,
                )
                progress.set_postfix_str("source")
                progress.update()
            else:
                logger.info("已跳过 Girl Life 源码下载。")

            source_root = detect_source_root()

            if not skip_paratranz:
                self.project.paratranz.download(
                    force=self.options.force_paratranz,
                    show_progress=self.options.show_progress,
                )
                progress.set_postfix_str("paratranz")
                progress.update()
            else:
                logger.info("已跳过 ParaTranz 翻译文件下载。")

            if not self.options.skip_translate:
                raw_paratranz_root = detect_translation_root()
                working_paratranz_root, _ = precheck_paratranz(
                    source_root=source_root,
                    paratranz_root=raw_paratranz_root,
                    show_progress=self.options.show_progress,
                    error_reporter=error_reporter,
                    mode=self.options.precheck_mode,
                )
                progress.set_postfix_str("precheck")
                progress.update()

                manager = LocalizationManager(
                    source_dir=source_root,
                    paratranz_dir=working_paratranz_root,
                    concurrency=self.options.concurrency,
                    memory_limit_mb=self.options.memory_limit_mb,
                    copy_source=self.options.copy_source,
                    show_progress=self.options.show_progress,
                    error_reporter=error_reporter,
                )
                result.translation_stats = await manager.translate_all()
                progress.set_postfix_str("replace")
                progress.update()
                if result.translation_stats.failed:
                    result.exit_code = 1
            else:
                logger.info("已跳过本地化注入。")

            if self.options.build_game:
                build_source_root = self.build_service.prepare_build_source(
                    self.options.process_dir,
                    skip_validation=not self.options.skip_translate,
                    show_progress=self.options.show_progress,
                    error_reporter=error_reporter,
                )
                if not build_source_root:
                    result.exit_code = 1
                else:
                    game_artifact = self.build_service.build_game(
                        build_source_root=build_source_root,
                        build_dir=build_dir,
                        strict_check=self.options.strict_build_check,
                        qproj=self.options.qproj,
                        output_txt=self.options.output_txt,
                        output_game=self.options.output_game,
                        show_progress=self.options.show_progress,
                        error_reporter=error_reporter,
                    )
                    progress.set_postfix_str("build-game")
                    progress.update()
                    result.built_game = game_artifact.success
                    if not game_artifact.success:
                        result.exit_code = 1

                    if self.options.build_mods:
                        mod_summary = self.build_service.build_mods(
                            build_source_root=build_source_root,
                            build_dir=build_dir,
                            strict_check=self.options.strict_build_check,
                            selected_mods=self.options.mod_names,
                            show_progress=self.options.show_progress,
                            error_reporter=error_reporter,
                        )
                        progress.set_postfix_str("build-mods")
                        progress.update()
                        result.built_mods = mod_summary.artifacts
                        result.missing_mods = mod_summary.missing_mods
                        if not mod_summary.success:
                            result.exit_code = 1

        if result.exit_code == 0:
            logger.success("GirlLifeLocalization 流水线执行完成。")
        else:
            logger.warning("GirlLifeLocalization 流水线完成，但存在失败项。")
        return result


__all__ = ["ApplicationPipeline", "PipelineOptions", "PipelineResult"]
