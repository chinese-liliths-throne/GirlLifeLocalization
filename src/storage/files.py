from pathlib import Path
from typing import TypeVar

import orjson

from src.models import ParatranzData, paratranz_data_list_adapter


TFile = TypeVar("TFile", bound="File")


class File:
    """在指定根目录下发现的文件包装对象。"""

    def __init__(self, path: Path | str, base_path: Path | str):
        self._path_obj = Path(path).resolve()
        self._base_path = Path(base_path).resolve()

        self.absolute_path = str(self._path_obj)
        self.rel_path = self._path_obj.relative_to(self._base_path)
        self.relative_path_no_ext = str(self.rel_path.with_suffix(""))
        self.relative_dir_path = str(self.rel_path.parent)
        self.file_type = self._path_obj.suffix

    @property
    def path(self) -> Path:
        return self._path_obj

    def read(self, encoding: str = "utf-8") -> str:
        try:
            return self._path_obj.read_text(encoding=encoding)
        except Exception as e:
            raise RuntimeError(f"无法读取文件 {self._path_obj}: {e}") from e

    def __repr__(self):
        return f"<File(type={self.file_type}, rel='{self.relative_path_no_ext}')>"


class ParatranzDataFile(File):
    def get_paratranz_data_list(self) -> list[ParatranzData]:
        raw_json = orjson.loads(self.path.read_bytes())
        return paratranz_data_list_adapter.validate_python(raw_json)


class FileManager:
    @staticmethod
    def _iter_files(root: Path | str, pattern: str, file_cls: type[TFile]) -> list[TFile]:
        base_path = Path(root).resolve()
        if not base_path.exists():
            return []
        if not base_path.is_dir():
            raise NotADirectoryError(base_path)
        return [file_cls(path, base_path) for path in sorted(base_path.rglob(pattern))]

    @staticmethod
    def get_qsrc_scripts(root: Path | str) -> list[File]:
        return FileManager._iter_files(root, "*.qsrc", File)

    @staticmethod
    def get_json_files(root: Path | str) -> list[File]:
        return FileManager._iter_files(root, "*.json", File)

    @staticmethod
    def get_paratranz_data_files(root: Path | str) -> list[ParatranzDataFile]:
        return FileManager._iter_files(root, "*.json", ParatranzDataFile)


if __name__ == "__main__":
    target_dir = Path("./0.9.8.1")
    json_results = FileManager.get_paratranz_data_files(target_dir)
    for f in json_results:
        print(f"[{f.file_type}] 绝对路径: {f.absolute_path} | 相对路径: {f.relative_path_no_ext}")
        for data in f.get_paratranz_data_list():
            print(f"Pos:{data.extract_pos_from_context()} | Stage:{data.stage}")
