import platform
import sys

from .configuration import settings


PLATFORM_SYSTEM = platform.system()
PLATFORM_ARCHITECTURE = platform.architecture()[0]
SYSTEM_ARGV = sys.argv

REPOSITORY_VERSION = settings.project.version
REPOSITORY_GITLAB_PROJECT_ID_COMMON = 65418391
REPOSITORY_URL_COMMON = "https://gitlab.com/kevinsmartstfg/girl-life"
REPOSITORY_ZIP_URL_COMMON = (
    f"{REPOSITORY_URL_COMMON}/-/archive/{REPOSITORY_VERSION}/girl-life-{REPOSITORY_VERSION}.zip"
)
REPOSITORY_URL_DEV = "https://gitlab.com/kevinsmartstfg/girl-life"
REPOSITORY_ZIP_URL_DEV = "https://gitlab.com/kevinsmartstfg/girl-life/-/archive/master/girl-life-master.zip"
REPOSITORY_COMMITS_URL_COMMON = (
    f"https://gitlab.com/api/v4/projects/{REPOSITORY_GITLAB_PROJECT_ID_COMMON}/repository/commits"
)
REPOSITORY_TAGS_URL_COMMON = (
    f"https://gitlab.com/api/v4/projects/{REPOSITORY_GITLAB_PROJECT_ID_COMMON}/repository/tags"
)


__all__ = [
    "PLATFORM_SYSTEM",
    "PLATFORM_ARCHITECTURE",
    "SYSTEM_ARGV",
    "REPOSITORY_VERSION",
    "REPOSITORY_GITLAB_PROJECT_ID_COMMON",
    "REPOSITORY_URL_COMMON",
    "REPOSITORY_ZIP_URL_COMMON",
    "REPOSITORY_URL_DEV",
    "REPOSITORY_ZIP_URL_DEV",
    "REPOSITORY_COMMITS_URL_COMMON",
    "REPOSITORY_TAGS_URL_COMMON",
]
