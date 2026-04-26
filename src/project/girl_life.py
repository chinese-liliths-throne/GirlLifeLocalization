import shutil
from pathlib import Path
from zipfile import ZipFile

import httpx
from aiofiles import open as aopen

from src.config.configuration import settings
from src.config.constants import (
    REPOSITORY_TAGS_URL_COMMON,
    REPOSITORY_ZIP_URL_COMMON,
    REPOSITORY_ZIP_URL_DEV,
)
from src.config.logging import logger
from src.localization.paratranz import Paratranz
from src.config.paths import paths, safe_extract_zip
from src.config.progress import ProgressBar, extract_zip_with_progress


class ProjectGirlLife:
    """负责准备 Girl Life 上游源码。"""

    def __init__(self):
        self.latest_version: str = ""
        self.source_type = settings.project.source_type
        self.source_label = settings.project.version if self.source_type == "common" else "dev"
        self.common_version = settings.project.version
        self.paratranz = Paratranz()

    def _init_dirs(self) -> None:
        paths.ensure_base_dirs()

    def clean_dirs(self) -> None:
        """清理流水线生成目录。"""

        for path in (paths.source_parent, paths.translation_parent, paths.result):
            shutil.rmtree(paths.ensure_inside_workspace(path), ignore_errors=True)
        self._init_dirs()

    async def fetch_latest_version(self, is_quiet: bool = True) -> str:
        """从 GitLab tags API 获取最新正式版本号。"""

        if self.source_type != "common":
            self.latest_version = "master"
            return self.latest_version

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(REPOSITORY_TAGS_URL_COMMON, follow_redirects=True)
            response.raise_for_status()
            raw_list: list[dict] = response.json()

        if not raw_list:
            raise RuntimeError("GitLab tags API 未返回任何 Girl Life 版本。")

        self.latest_version = raw_list[0].get("name", "")
        if not is_quiet:
            logger.info("Girl Life 最新版本: {}", self.latest_version)
        return self.latest_version

    async def download_from_gitlab(self, force: bool = False, *, show_progress: bool = False) -> None:
        """下载源码压缩包并解压到源码目录。"""

        if force or not self.get_save_path().exists():
            await self.fetch_from_gitlab(show_progress=show_progress)
        else:
            logger.info("已使用缓存源码压缩包: {}", self.get_save_path())
        self.unzip_latest_repository(show_progress=show_progress)

    def get_save_path(self) -> Path:
        return paths.source_archive(self.source_label)

    async def fetch_from_gitlab(self, *, show_progress: bool = False) -> None:
        logger.info("===== 开始获取 {} 仓库内容 ...", self.source_label)
        self._init_dirs()

        zip_url = REPOSITORY_ZIP_URL_COMMON if self.source_type == "common" else REPOSITORY_ZIP_URL_DEV
        save_path = self.get_save_path()

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("GET", zip_url, follow_redirects=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", "0") or 0)
                async with aopen(save_path, "wb") as fp:
                    with ProgressBar(
                        total=total or None,
                        enabled=show_progress,
                        desc="Download Source",
                        unit="B",
                        unit_scale=True,
                    ) as progress:
                        async for chunk in response.aiter_bytes():
                            await fp.write(chunk)
                            progress.update(len(chunk))

        logger.success("##### {} 仓库内容已保存: {}", self.source_label, save_path)

    def unzip_latest_repository(self, *, show_progress: bool = False) -> None:
        """解压源码压缩包。"""

        save_path = self.get_save_path()
        if not save_path.exists():
            raise FileNotFoundError(f"找不到源码压缩包: {save_path}")

        logger.info("===== 开始解压 {} 仓库内容 ...", self.source_label)
        self._empty_dir(paths.source_parent)

        with ZipFile(save_path) as zfp:
            if show_progress:
                extract_zip_with_progress(zfp, paths.source_parent, enabled=True, desc="Extract Source")
            else:
                safe_extract_zip(zfp, paths.source_parent)

        logger.success("##### {} 仓库内容已解压到: {}", self.source_label, paths.source_parent)

    @staticmethod
    def _empty_dir(path: Path) -> None:
        target = paths.ensure_inside_workspace(path)
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)


__all__ = ["ProjectGirlLife"]


if __name__ == "__main__":
    async def _main():
        project_girl_life = ProjectGirlLife()
        await project_girl_life.download_from_gitlab()

    import asyncio

    asyncio.run(_main())
