"""GirlLifeLocalization shared core library."""

from .config.configuration import Settings, settings
from .config.logging import logger
from .config.paths import ProjectPaths, paths

__all__ = ["ProjectPaths", "Settings", "logger", "paths", "settings"]
