import asyncio
from argparse import ArgumentParser, Namespace
from pathlib import Path

from src.log import logger
from src.localization_manager import LocalizationManager, replace_localizations
from src.paratranz_precheck import precheck_paratranz
from src.paratranz_sync import extract_paratranz_to_dir, sync_paratranz
from src.pipeline import ApplicationPipeline, PipelineOptions
from src.qsrc_runtime_checker import test_qsrc_runtime
from src.paths import detect_source_root, paths
from src.error_reporter import ErrorReporter


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="GirlLifeLocalization：下载 Girl Life 源码、拉取 ParaTranz 翻译并注入中文本地化。"
    )
    parser.add_argument("--only-translate", action="store_true", help="只使用本地已有源码与 ParaTranz 导出执行翻译注入。")
    parser.add_argument("--skip-source", action="store_true", help="跳过 Girl Life GitLab 源码下载与解压。")
    parser.add_argument("--skip-paratranz", action="store_true", help="跳过 ParaTranz 翻译文件下载。")
    parser.add_argument("--skip-translate", action="store_true", help="只准备源码/翻译文件，不执行本地化注入。")
    parser.add_argument("--force-source", action="store_true", help="即使缓存 zip 已存在，也重新下载 Girl Life 源码。")
    parser.add_argument("--force-paratranz", action="store_true", help="忽略本地 ParaTranz 缓存，强制重新下载导出包。")
    parser.add_argument(
        "--precheck-mode",
        choices=("fast", "balanced", "strict"),
        default="fast",
        help="第二步预检查强度：fast=只过滤无效词条，balanced=再检查字符串结构，strict=预留更严格规则。",
    )
    parser.add_argument("--no-copy-source", action="store_true", help="兼容参数：默认已经只输出 qsrc。")
    parser.add_argument("--copy-source-to-result", action="store_true", help="调试用：让 3-SourceTranslatedFile 复制完整源码。")
    parser.add_argument("--concurrency", type=int, default=32, help="翻译注入并发数量，默认 32。")
    parser.add_argument("--memory-limit-mb", type=int, help="限制第三步单批内存预算，单位 MB。默认自动按可用内存估算。")
    parser.add_argument("--skip-build", action="store_true", help="跳过最终 qsp 打包。")
    parser.add_argument("--build-game", action="store_true", help="兼容参数：强制执行最终 qsp 打包。")
    parser.add_argument("--skip-mods", action="store_true", help="打包本体时跳过 mods 目录下的 mod qsp 打包。")
    parser.add_argument("--mod", action="append", default=[], help="限制 mod 打包范围，可重复传入；支持 mod 目录名或 qproj 名。")
    parser.add_argument("--build-dir", type=Path, help="最终打包输出目录，默认 build。")
    parser.add_argument("--process-dir", type=Path, help="第 4 步打包源码目录，默认 data/4-BuildSource。")
    parser.add_argument("--strict-build-check", action="store_true", help="打包前启用严格 QSP 语法检查。")
    parser.add_argument("--qproj", type=Path, help="打包时使用的 glife.qproj 路径；默认从输出源码根目录查找。")
    parser.add_argument("--output-txt", type=Path, help="打包生成的中间 glife.txt 路径。")
    parser.add_argument("--output-game", type=Path, help="打包生成的 glife.qsp / glife.gam 路径，默认 build/glife.qsp。")
    parser.add_argument("--sync-paratranz", action="store_true", help="根据当前源码重新提取 ParaTranz JSON，并尽量迁移旧版本译文。")
    parser.add_argument("--sync-source-dir", type=Path, help="ParaTranz 同步时使用的源码根目录。默认自动识别 1-SourceFile。")
    parser.add_argument("--sync-paratranz-dir", type=Path, help="ParaTranz 同步时读取的旧 JSON 根目录。默认自动识别 2-TranslatedParatranzFile。")
    parser.add_argument("--sync-output-dir", type=Path, help="ParaTranz 同步输出目录。默认输出到 sync/<源码目录名>/sync。")
    parser.add_argument("--sync-no-clear", action="store_true", help="同步 ParaTranz 时不清空输出目录。")
    parser.add_argument("--extract-paratranz", action="store_true", help="Only extract qsrc texts to ParaTranz JSON.")
    parser.add_argument("--extract-source-dir", type=Path, help="Source root for extract-only mode.")
    parser.add_argument("--extract-output-dir", type=Path, help="Output directory for extract-only mode. Default: sync/<源码目录名>/extract")
    parser.add_argument("--extract-no-clear", action="store_true", help="Do not clear extract output directory.")
    parser.add_argument("--replace-localizations", action="store_true", help="Only apply ParaTranz translations back to qsrc.")
    parser.add_argument("--replace-source-dir", type=Path, help="Source root for replace-only mode.")
    parser.add_argument("--replace-paratranz-dir", type=Path, help="ParaTranz root for replace-only mode.")
    parser.add_argument("--replace-output-dir", type=Path, help="Output directory for replace-only mode.")
    parser.add_argument("--replace-no-clear", action="store_true", help="Do not clear replace output directory.")
    parser.add_argument("--test-qsrc", action="store_true", help="只运行 qsrc 语法/跳转骨架测试。")
    parser.add_argument("--test-source-dir", type=Path, help="qsrc 测试使用的原版源码目录。默认自动识别 1-SourceFile。")
    parser.add_argument("--test-translated-dir", type=Path, help="qsrc 测试使用的本地化源码目录。默认使用 3-SourceTranslatedFile。")
    parser.add_argument("--progress", action="store_true", help="显示提取/同步进度条。")
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
            logger.error("找不到 qsrc 测试所需的原版源码目录。")
            return 1
        if not translated_root:
            logger.error("找不到 qsrc 测试所需的本地化源码目录。")
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
            "QSRC 测试汇总：总计 {}，合法 {}，语法错误 {}，锁定 {}。",
            stats.total_files,
            stats.legal_files,
            stats.syntax_error_count,
            stats.locked_files,
        )
        return 0 if ok else 1
    pipeline = ApplicationPipeline(_options_from_args(args))
    result = await pipeline.run()
    return result.exit_code


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run_async(args))
    except KeyboardInterrupt:
        logger.warning("任务已被用户中断。")
        return 130
    except Exception:
        logger.exception("流水线执行失败。")
        return 1


__all__ = ["build_parser", "main", "run_async"]
