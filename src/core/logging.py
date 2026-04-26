"""Output infos during running."""

from __future__ import annotations

import datetime
import os
import sys

from loguru import logger as logger_
from tqdm.auto import tqdm

from .configuration import settings

DIR_LOGS = settings.filepath.root / settings.filepath.data / "logs"
os.makedirs(DIR_LOGS, exist_ok=True)


def add_project_name(record):
    if record["extra"].get("project_name", False):
        record["extra"]["project_name"] = f"[{record['extra']['project_name']}] | "
    else:
        record["extra"]["project_name"] = ""


def add_filepath(record):
    if record["extra"].get("filepath", False):
        record["extra"]["filepath"] = f" | {record['extra']['filepath']}"
    else:
        record["extra"]["filepath"] = ""


def tqdm_sink(message):
    text = str(message).rstrip("\n")
    if not text:
        return
    try:
        tqdm.write(text)
    except Exception:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


logger_.remove()
logger_ = logger_.patch(add_project_name)
logger_ = logger_.patch(add_filepath)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
logger_.add(sink=tqdm_sink, format=settings.project.log_format, colorize=True, level=settings.project.log_level)
logger_.add(
    sink=DIR_LOGS / f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log",
    format=settings.project.log_format,
    colorize=False,
    level="INFO",
    encoding="utf-8",
)
logger_.add(
    sink=DIR_LOGS / f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.debug",
    format=settings.project.log_format,
    colorize=False,
    level="DEBUG",
    encoding="utf-8",
)

logger = logger_

__all__ = ["logger"]
