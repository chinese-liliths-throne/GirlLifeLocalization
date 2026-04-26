from __future__ import annotations

from src.localization_manager import LocalizationManager
from src.core.paths import detect_source_root, detect_translation_root, paths


class LocalizationCoreService:
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
