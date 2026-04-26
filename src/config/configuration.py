from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class ProjectSettings(BaseSettings):
    """项目级配置。"""

    model_config = SettingsConfigDict(env_prefix="PROJECT_")

    name: str = Field(default="GirlLife-Paratranz")
    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="<g>{time:HH:mm:ss}</g> | [<lvl>{level:^7}</lvl>] | "
        "{extra[project_name]}{message:<35}{extra[filepath]}"
    )
    language: str = Field(default="zh_cn")
    version: str = Field(default="0.9.8.1")
    source_type: Literal["common", "dev"] = Field(default="common")


class FilepathSettings(BaseSettings):
    """项目文件与目录配置。"""

    model_config = SettingsConfigDict(env_prefix="PATH_")

    root: Path = Field(default=Path(__file__).resolve().parents[2])
    data: Path = Field(default=Path("data"))
    tmp: Path = Field(default=Path("tmp"))
    source: Path = Field(default=Path("data/1-SourceFile"))
    download: Path = Field(default=Path("data/2-TranslatedParatranzFile"))
    result: Path = Field(default=Path("data/3-SourceTranslatedFile"))
    process: Path = Field(default=Path("data/4-BuildSource"))
    build: Path = Field(default=Path("build"))
    repo: Path = Field(default=Path("repositories"))


class GitHubSettings(BaseSettings):
    """GitHub/GitLab token 配置。"""

    model_config = SettingsConfigDict(env_prefix="GITHUB_")

    access_token: str = Field(default="")


class ParatranzSettings(BaseSettings):
    """ParaTranz API 配置。"""

    model_config = SettingsConfigDict(env_prefix="PARATRANZ_")

    project_id: int = Field(default=0)
    token: str = Field(default="")

    @field_validator("project_id", mode="before")
    @classmethod
    def blank_project_id_to_zero(cls, value):
        if value in ("", None):
            return 0
        return value


class Settings(BaseSettings):
    """应用配置。"""

    github: GitHubSettings = GitHubSettings()
    project: ProjectSettings = ProjectSettings()
    filepath: FilepathSettings = FilepathSettings()
    paratranz: ParatranzSettings = ParatranzSettings()


settings = Settings()

__all__ = ["Settings", "settings"]
