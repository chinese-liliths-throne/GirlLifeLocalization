class LegacyReplacerUnavailable(RuntimeError):
    """旧版 Twine 替换器不可用。"""


class Replacer:
    """
    旧版 Twine/SugarCube 替换器兼容占位。

    当前项目已经迁移到 Girl Life / QSP 的 `.qsrc` 本地化流程，
    旧实现依赖未定义目录常量与额外 JSON 结构，继续保留会造成导入错误。
    如需处理 Girl Life 翻译，请使用 `src.localization_manager.LocalizationManager`。
    """

    def __init__(self, *args, **kwargs):
        raise LegacyReplacerUnavailable(
            "old_replacer 是旧版 Twine 流程遗留模块，当前项目请改用 LocalizationManager。"
        )


__all__ = ["LegacyReplacerUnavailable", "Replacer"]
