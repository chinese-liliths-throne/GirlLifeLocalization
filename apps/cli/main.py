from __future__ import annotations

import asyncio
from argparse import ArgumentParser, Namespace
from pathlib import Path

from src.config.error_reporting import ErrorReporter
from src.localization.manager import LocalizationManager
from src.config.logging import logger
from src.localization.precheck import precheck_paratranz
from src.localization.sync import extract_paratranz_to_dir, sync_paratranz
from src.config.paths import detect_source_root, paths
from src.build.pipeline import ApplicationPipeline, PipelineOptions
from src.qsp_runtime import QspRuntimeRunner
from src.qsp_runtime.build import build_qsp_runtime
from src.runtime.qsrc_checker import test_qsrc_runtime


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="GirlLifeLocalization CLI")

    parser.add_argument("--only-translate", action="store_true", help="Use local source and ParaTranz export only.")
    parser.add_argument("--skip-source", action="store_true", help="Skip source download and extraction.")
    parser.add_argument("--skip-paratranz", action="store_true", help="Skip ParaTranz download.")
    parser.add_argument("--skip-translate", action="store_true", help="Skip localization replace step.")
    parser.add_argument("--force-source", action="store_true", help="Force refresh source archive.")
    parser.add_argument("--force-paratranz", action="store_true", help="Force refresh ParaTranz export.")
    parser.add_argument(
        "--precheck-mode",
        choices=("fast", "balanced", "strict"),
        default="fast",
        help="Precheck intensity.",
    )
    parser.add_argument("--no-copy-source", action="store_true", help="Keep result dir minimal.")
    parser.add_argument("--copy-source-to-result", action="store_true", help="Copy source tree into result dir.")
    parser.add_argument("--concurrency", type=int, default=32, help="Localization concurrency.")
    parser.add_argument("--memory-limit-mb", type=int, help="Third-step memory budget in MB.")
    parser.add_argument("--skip-build", action="store_true", help="Skip final game build.")
    parser.add_argument("--build-game", action="store_true", help="Force final game build.")
    parser.add_argument("--skip-mods", action="store_true", help="Skip mod build.")
    parser.add_argument("--mod", action="append", default=[], help="Restrict mod build scope.")
    parser.add_argument("--build-dir", type=Path, help="Final build output directory.")
    parser.add_argument("--process-dir", type=Path, help="Step-4 build source directory.")
    parser.add_argument("--strict-build-check", action="store_true", help="Enable strict build syntax check.")
    parser.add_argument("--qproj", type=Path, help="Override qproj path.")
    parser.add_argument("--output-txt", type=Path, help="Override output txt path.")
    parser.add_argument("--output-game", type=Path, help="Override output qsp/gam path.")

    parser.add_argument("--sync-paratranz", action="store_true", help="Rebuild and migrate ParaTranz JSON.")
    parser.add_argument("--sync-source-dir", type=Path, help="Sync source root.")
    parser.add_argument("--sync-paratranz-dir", type=Path, help="Old ParaTranz root.")
    parser.add_argument("--sync-output-dir", type=Path, help="Sync output root.")
    parser.add_argument("--sync-no-clear", action="store_true", help="Do not clear sync output root.")

    parser.add_argument("--extract-paratranz", action="store_true", help="Extract qsrc text into ParaTranz JSON.")
    parser.add_argument("--extract-source-dir", type=Path, help="Extract source root.")
    parser.add_argument("--extract-output-dir", type=Path, help="Extract output root.")
    parser.add_argument("--extract-no-clear", action="store_true", help="Do not clear extract output root.")

    parser.add_argument("--replace-localizations", action="store_true", help="Run replace/localization only.")
    parser.add_argument("--replace-source-dir", type=Path, help="Replace source root.")
    parser.add_argument("--replace-paratranz-dir", type=Path, help="Replace ParaTranz root.")
    parser.add_argument("--replace-output-dir", type=Path, help="Replace output root.")
    parser.add_argument("--replace-no-clear", action="store_true", help="Do not clear replace output root.")

    parser.add_argument("--test-qsrc", action="store_true", help="Run qsrc syntax/reference check.")
    parser.add_argument("--test-source-dir", type=Path, help="Runtime-check source root.")
    parser.add_argument("--test-translated-dir", type=Path, help="Runtime-check translated root.")
    parser.add_argument("--test-qsrc-runtime", action="store_true", help="Inspect or execute QSP runtime bridge.")
    parser.add_argument("--run-location", help="Location name used with --test-qsrc-runtime.")
    parser.add_argument("--progress", action="store_true", help="Show tqdm progress bars.")
    return parser


def _options_from_args(args: Namespace) -> PipelineOptions:
    build_game = args.build_game or (not args.skip_build and not args.skip_translate)
    return PipelineOptions(
        only_translate=args.only_translate,
        skip_source=args.skip_source,
        skip_paratranz=args.skip_paratranz,
        skip_translate=args.skip_translate,
        force_source=args.force_source,
        force_paratranz=args.force_paratranz,
        precheck_mode=args.precheck_mode,
        concurrency=args.concurrency,
        memory_limit_mb=args.memory_limit_mb,
        copy_source=args.copy_source_to_result and not args.no_copy_source,
        show_progress=args.progress,
        build_game=build_game,
        build_mods=build_game and not args.skip_mods,
        build_dir=args.build_dir,
        process_dir=args.process_dir,
        strict_build_check=args.strict_build_check,
        mod_names=tuple(args.mod),
        qproj=args.qproj,
        output_txt=args.output_txt,
        output_game=args.output_game,
    )


async def run_async(args: Namespace) -> int:
    if args.extract_paratranz:
        extract_paratranz_to_dir(
            source_root=args.extract_source_dir or args.sync_source_dir,
            output_root=args.extract_output_dir or args.sync_output_dir,
            clear_output=not args.extract_no_clear,
            show_progress=args.progress,
        )
        return 0

    if args.sync_paratranz:
        sync_paratranz(
            source_root=args.sync_source_dir,
            old_paratranz_root=args.sync_paratranz_dir,
            output_root=args.sync_output_dir,
            clear_output=not args.sync_no_clear,
            show_progress=args.progress,
        )
        return 0

    if args.replace_localizations:
        checked_paratranz_dir, _ = precheck_paratranz(
            source_root=args.replace_source_dir,
            paratranz_root=args.replace_paratranz_dir,
            show_progress=args.progress,
            mode=args.precheck_mode,
        )
        manager = LocalizationManager(
            source_dir=args.replace_source_dir,
            paratranz_dir=checked_paratranz_dir,
            result_dir=args.replace_output_dir,
            clear_result=not args.replace_no_clear,
            concurrency=args.concurrency,
            memory_limit_mb=args.memory_limit_mb,
            copy_source=args.copy_source_to_result and not args.no_copy_source,
            show_progress=args.progress,
        )
        stats = await manager.translate_all()
        return 0 if not stats.failed else 1

    if args.test_qsrc:
        source_root = args.test_source_dir or detect_source_root(paths.source_parent)
        translated_root = args.test_translated_dir or detect_source_root(paths.result)
        if not source_root:
            logger.error("Cannot find original source root for qsrc test.")
            return 1
        if not translated_root:
            logger.error("Cannot find translated root for qsrc test.")
            return 1
        error_reporter = ErrorReporter(paths.build_errors())
        error_reporter.clear()
        ok, stats = test_qsrc_runtime(
            source_root=source_root,
            translated_root=translated_root,
            show_progress=args.progress,
            error_reporter=error_reporter,
        )
        logger.info(
            "QSRC test summary: total={} legal={} syntax_errors={} locked={}",
            stats.total_files,
            stats.legal_files,
            stats.syntax_error_count,
            stats.locked_files,
        )
        return 0 if ok else 1

    if args.test_qsrc_runtime:
        commands = build_qsp_runtime(root=paths.root)
        logger.info("QSP runtime build command preview: {}", " ".join(commands))
        runner = QspRuntimeRunner(paths.root)
        if not runner.available():
            logger.warning("QSP runtime is not built yet; only build command preview is available.")
            return 1
        if not args.run_location:
            logger.info("QSP runtime is loaded, but --run-location was not provided.")
            return 0
        result = runner.exec_location(args.run_location)
        if result.ok:
            logger.success("QSP runtime executed successfully: {}", args.run_location)
            return 0
        logger.error(
            "QSP runtime execution failed: code={} line={} act={} desc={}",
            result.error_code,
            result.line,
            result.act_index,
            result.error_desc,
        )
        return 1

    pipeline = ApplicationPipeline(_options_from_args(args))
    result = await pipeline.run()
    return result.exit_code


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run_async(args))
    except KeyboardInterrupt:
        logger.warning("Task interrupted by user.")
        return 130
    except Exception:
        logger.exception("Command execution failed.")
        return 1


__all__ = ["build_parser", "main", "run_async"]
