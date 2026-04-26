from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import subprocess

from src.core.paths import paths

from .models import HostMode
from .workbench import launch_workbench


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="GirlLife Flet 工作台")
    parser.add_argument("--host", choices=("desktop", "web", "android"), default="desktop", help="工作台宿主模式。")
    parser.add_argument("--port", type=int, default=8550, help="Web 模式端口。")
    parser.add_argument(
        "--build-target",
        choices=("web", "windows", "macos", "linux", "apk", "aab", "ipa", "ios-simulator"),
        help="使用 Flet 独立打包工作台。",
    )
    parser.add_argument("--build-output", type=Path, help="Flet 构建输出目录。")
    return parser


def build_flet_command(*, target: str, output_dir: Path | None = None) -> list[str]:
    command = ["uv", "run", "flet", "build", target, str(paths.root / "flet_main.py")]
    if output_dir is not None:
        command.extend(["--output", str(output_dir)])
    return command


def main() -> int:
    args = build_parser().parse_args()
    if args.build_target:
        command = build_flet_command(target=args.build_target, output_dir=args.build_output)
        completed = subprocess.run(command, cwd=paths.root)
        return completed.returncode
    launch_workbench(host_mode=HostMode(args.host), port=args.port)
    return 0
