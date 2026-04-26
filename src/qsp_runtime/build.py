from __future__ import annotations

import platform
from pathlib import Path


def build_qsp_runtime(*, root: Path | str) -> list[str]:
    root_path = Path(root).resolve()
    qsp_root = root_path / "qsp"
    output_dir = root_path / "tmp" / "qsp_runtime"
    output_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    common_sources = sorted(str(path) for path in qsp_root.glob("*.c"))
    default_binding_sources = sorted(str(path) for path in (qsp_root / "bindings" / "default").glob("*.c"))
    sources = common_sources + default_binding_sources

    if system == "windows":
        output = output_dir / "qsp.dll"
        return [
            "cl",
            "/LD",
            "/I",
            str(qsp_root),
            "/I",
            str(qsp_root / "bindings" / "default"),
            *sources,
            "/Fe:" + str(output),
        ]

    output = output_dir / "libqsp.so"
    return [
        "gcc",
        "-shared",
        "-fPIC",
        "-I",
        str(qsp_root),
        "-I",
        str(qsp_root / "bindings" / "default"),
        *sources,
        "-o",
        str(output),
    ]
