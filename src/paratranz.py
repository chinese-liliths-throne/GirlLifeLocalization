import contextlib
import shutil
from pathlib import Path
from zipfile import ZipFile

import httpx

from src.core.configuration import settings
from src.core.logging import logger
from src.core.paths import paths, safe_extract_zip
from src.core.progress import ProgressBar, extract_zip_with_progress


class Paratranz:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=60)
        self._base_url = "https://paratranz.cn/api"
        self._project_id = settings.paratranz.project_id

    def get_files(self) -> list:
        self._ensure_configured()
        url = f"{self.base_url}/projects/{self.project_id}/files"
        response = self.client.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def update_file(self, file: Path | str, fileid: int) -> dict:
        self._ensure_configured()
        file_path = Path(file)
        url = f"{self.base_url}/projects/{self.project_id}/files/{fileid}"
        with file_path.open("rb") as fp:
            response = self.client.post(
                url,
                headers=self.headers,
                files={"file": (file_path.name, fp, "application/octet-stream")},
            )
        response.raise_for_status()
        payload = response.json()
        logger.bind(filepath=payload).success("ParaTranz 文件更新成功。")
        return payload

    def create_file(self, file: Path | str, path: Path | str) -> dict:
        self._ensure_configured()
        file_path = Path(file)
        remote_path = str(path)
        url = f"{self.base_url}/projects/{self.project_id}/files"
        with file_path.open("rb") as fp:
            response = self.client.post(
                url,
                headers=self.headers,
                data={"path": remote_path},
                files={"file": (file_path.name, fp, "application/octet-stream")},
            )
        response.raise_for_status()
        payload = response.json()
        logger.bind(filepath=payload).success("ParaTranz 文件创建成功。")
        return payload

    def download(self, *, force: bool = False, show_progress: bool = False) -> None:
        self._ensure_configured()
        logger.info("")
        logger.info("======= PARATRANZ START =======")
        logger.info("开始准备 ParaTranz 翻译导出包...")
        paths.ensure_base_dirs()

        export_zip = paths.tmp / "paratranz_export.zip"
        if not force and self._has_extracted_cache():
            logger.info("已使用本地 ParaTranz 缓存目录: {}", paths.translation_parent)
            return
        if not force and export_zip.exists():
            logger.info("已使用本地 ParaTranz 缓存压缩包: {}", export_zip)
            self._extract_artifacts(show_progress=show_progress)
            logger.success("ParaTranz 翻译导出包已从缓存解压。")
            return

        with contextlib.suppress(httpx.HTTPError):
            self._trigger_export()

        self._download_artifacts(show_progress=show_progress)
        self._extract_artifacts(show_progress=show_progress)
        logger.success("ParaTranz 翻译导出包下载完成。")

    def _trigger_export(self) -> None:
        url = f"{self.base_url}/projects/{self.project_id}/artifacts"
        response = self.client.post(url, headers=self.headers)
        response.raise_for_status()

    def _download_artifacts(self, *, show_progress: bool = False) -> None:
        url = f"{self.base_url}/projects/{self.project_id}/artifacts/download"
        output_file = paths.tmp / "paratranz_export.zip"
        with self.client.stream("GET", url, headers=self.headers, follow_redirects=True) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", "0") or 0)
            with output_file.open("wb") as fp:
                with ProgressBar(
                    total=total or None,
                    enabled=show_progress,
                    desc="Download ParaTranz",
                    unit="B",
                    unit_scale=True,
                ) as progress:
                    for chunk in response.iter_bytes():
                        fp.write(chunk)
                        progress.update(len(chunk))

    def _extract_artifacts(self, *, show_progress: bool = False) -> None:
        export_zip = paths.tmp / "paratranz_export.zip"
        extracted_utf8_dir = paths.tmp / "utf8"
        download_dir = paths.translation_parent

        shutil.rmtree(paths.ensure_inside_workspace(extracted_utf8_dir), ignore_errors=True)
        with ZipFile(export_zip) as zfp:
            if show_progress:
                extract_zip_with_progress(zfp, paths.tmp, enabled=True, desc="Extract ParaTranz")
            else:
                safe_extract_zip(zfp, paths.tmp)

        if not extracted_utf8_dir.exists():
            raise FileNotFoundError(f"ParaTranz 导出包中找不到 utf8 目录: {extracted_utf8_dir}")

        shutil.rmtree(paths.ensure_inside_workspace(download_dir), ignore_errors=True)
        shutil.copytree(extracted_utf8_dir, download_dir)

    def _has_extracted_cache(self) -> bool:
        return paths.translation_parent.exists() and any(paths.translation_parent.rglob("*.json"))

    def _ensure_configured(self) -> None:
        if not settings.paratranz.project_id or not settings.paratranz.token:
            raise ValueError("请先在 .env 中配置 PARATRANZ_PROJECT_ID 和 PARATRANZ_TOKEN。")

    @property
    def client(self) -> httpx.Client:
        return self._client

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def headers(self) -> dict:
        return {"Authorization": settings.paratranz.token}

    @property
    def project_id(self) -> int:
        return self._project_id


__all__ = ["Paratranz"]
