from __future__ import annotations

import ctypes
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class QspRuntimeBindings:
    library_path: Path
    library: ctypes.CDLL
    platform_name: str
    init_runtime: object | None = None
    deinit_runtime: object | None = None
    load_game_world: object | None = None
    load_game_world_from_data: object | None = None
    exec_location_code: object | None = None
    exec_user_input: object | None = None
    set_input_str_text: object | None = None
    get_last_error_data: object | None = None
    get_error_desc: object | None = None
    get_cur_loc: object | None = None
    get_main_desc: object | None = None
    get_vars_desc: object | None = None
    get_actions_count: object | None = None
    get_action_data: object | None = None
    set_sel_action_index: object | None = None
    exec_sel_action_code: object | None = None
    get_objects_count: object | None = None
    get_object_data: object | None = None
    set_sel_object_index: object | None = None

    @property
    def ready(self) -> bool:
        return all(
            item is not None
            for item in (
                self.exec_location_code,
                self.get_last_error_data,
                self.get_main_desc,
                self.get_vars_desc,
                self.get_actions_count,
                self.get_action_data,
                self.get_cur_loc,
            )
        )


def load_qsp_runtime(root: Path | str, library_path: Path | str | None = None) -> QspRuntimeBindings | None:
    root_path = Path(root).resolve()
    candidate = Path(library_path).resolve() if library_path else _default_library_path(root_path)
    if not candidate.exists():
        return None
    library = ctypes.CDLL(str(candidate))
    bindings = QspRuntimeBindings(
        library_path=candidate,
        library=library,
        platform_name=platform.system().lower(),
    )
    bindings.init_runtime = _bind_optional(library, "QSPInit")
    bindings.deinit_runtime = _bind_optional(library, "QSPDeInit")
    bindings.load_game_world = _bind_optional(library, "QSPLoadGameWorld")
    bindings.load_game_world_from_data = _bind_optional(library, "QSPLoadGameWorldFromData")
    bindings.exec_location_code = _bind_optional(library, "QSPExecLocationCode")
    bindings.exec_user_input = _bind_optional(library, "QSPExecUserInput")
    bindings.set_input_str_text = _bind_optional(library, "QSPSetInputStrText")
    bindings.get_last_error_data = _bind_optional(library, "QSPGetLastErrorData")
    bindings.get_error_desc = _bind_optional(library, "QSPGetErrorDesc")
    bindings.get_cur_loc = _bind_optional(library, "QSPGetCurLoc")
    bindings.get_main_desc = _bind_optional(library, "QSPGetMainDesc")
    bindings.get_vars_desc = _bind_optional(library, "QSPGetVarsDesc")
    bindings.get_actions_count = _bind_optional(library, "QSPGetActionsCount")
    bindings.get_action_data = _bind_optional(library, "QSPGetActionData")
    bindings.set_sel_action_index = _bind_optional(library, "QSPSetSelActionIndex")
    bindings.exec_sel_action_code = _bind_optional(library, "QSPExecuteSelActionCode")
    bindings.get_objects_count = _bind_optional(library, "QSPGetObjectsCount")
    bindings.get_object_data = _bind_optional(library, "QSPGetObjectData")
    bindings.set_sel_object_index = _bind_optional(library, "QSPSetSelObjectIndex")
    return bindings


def _bind_optional(library: ctypes.CDLL, name: str):
    try:
        return getattr(library, name)
    except AttributeError:
        return None


def _default_library_path(root: Path) -> Path:
    base = root / "tmp" / "qsp_runtime"
    return base / ("qsp.dll" if platform.system().lower() == "windows" else "libqsp.so")
