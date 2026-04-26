class GirlLifeLocalizationError(Exception):
    """项目基础异常。"""


class ProjectStructureException(GirlLifeLocalizationError):
    def __init__(self, message: str = "项目目录结构不完整。", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class UnknownFileTypeException(GirlLifeLocalizationError):
    def __init__(self, message: str = "未知文件类型。", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class PipelineConfigurationError(GirlLifeLocalizationError):
    """流水线配置错误。"""


class SafePathError(GirlLifeLocalizationError):
    """路径安全检查失败。"""


__all__ = [
    "GirlLifeLocalizationError",
    "ProjectStructureException",
    "UnknownFileTypeException",
    "PipelineConfigurationError",
    "SafePathError",
]
