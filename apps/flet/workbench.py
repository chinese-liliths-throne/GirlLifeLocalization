from __future__ import annotations

import flet as ft

from .models import HostMode


def launch_workbench(*, host_mode: HostMode = HostMode.DESKTOP, port: int = 8550) -> None:
    from .workbench_page import build_workbench_page

    def main(page: ft.Page) -> None:
        build_workbench_page(page, host_mode=host_mode)

    view = ft.AppView.WEB_BROWSER if host_mode == HostMode.WEB else ft.AppView.FLET_APP
    kwargs = {"view": view}
    if host_mode == HostMode.WEB:
        kwargs["port"] = port
        kwargs["host"] = "127.0.0.1"
    ft.run(main, **kwargs)
