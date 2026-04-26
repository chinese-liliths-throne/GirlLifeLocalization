from __future__ import annotations

import ctypes
import platform
from dataclasses import dataclass, field
from pathlib import Path

from src.core.paths import paths

from .ffi import QspRuntimeBindings, load_qsp_runtime


@dataclass(slots=True)
class RuntimeAction:
    index: int
    text: str
    image_path: str = ""


@dataclass(slots=True)
class RuntimeObject:
    index: int
    text: str
    image_path: str = ""


@dataclass(slots=True)
class RuntimeSnapshot:
    loaded: bool = False
    world_path: str = ""
    current_location: str = ""
    main_desc: str = ""
    vars_desc: str = ""
    actions: list[RuntimeAction] = field(default_factory=list)
    objects: list[RuntimeObject] = field(default_factory=list)
    runtime_error: str = ""


@dataclass(slots=True)
class RuntimeExecutionResult:
    ok: bool
    error_code: int = 0
    error_desc: str = ""
    location_name: str = ""
    line: int = 0
    act_index: int = -1
    snapshot: RuntimeSnapshot | None = None


class QspRuntimeRunner:
    def __init__(self, root: Path | str, *, library_path: Path | str | None = None):
        self.root = Path(root).resolve()
        self.bindings = load_qsp_runtime(self.root, library_path=library_path)
        self.default_world_path = paths.build_game()
        self.loaded_world_path: Path | None = None
        self._initialized = False

    def available(self) -> bool:
        return self.bindings is not None

    def can_execute(self) -> bool:
        return self.bindings is not None and self.bindings.ready and platform.system().lower() == "windows"

    def ensure_loaded(self, world_path: Path | str | None = None) -> RuntimeExecutionResult:
        if self.bindings is None:
            return RuntimeExecutionResult(ok=False, error_desc="QSP runtime 未构建或未加载。")
        if platform.system().lower() != "windows":
            return RuntimeExecutionResult(ok=False, error_desc="当前运行桥接仅在 Windows 上完成了可执行调用链。")
        if not self.bindings.ready:
            return RuntimeExecutionResult(ok=False, error_desc="QSP runtime 已加载，但缺少执行所需导出符号。")
        target_world = Path(world_path).resolve() if world_path else self.default_world_path.resolve()
        if not target_world.exists():
            return RuntimeExecutionResult(ok=False, error_desc=f"未找到可加载的游戏包：{target_world}")
        try:
            self._init_runtime()
            if not self._load_world(target_world):
                return self._last_error("")
            self.loaded_world_path = target_world
            return RuntimeExecutionResult(ok=True, snapshot=self.snapshot())
        except Exception as exc:
            return RuntimeExecutionResult(ok=False, error_desc=f"QSP runtime 载入异常：{exc}")

    def exec_location(self, location_name: str, *, world_path: Path | str | None = None) -> RuntimeExecutionResult:
        load_result = self.ensure_loaded(world_path)
        if not load_result.ok:
            return RuntimeExecutionResult(
                ok=False,
                error_code=load_result.error_code,
                error_desc=load_result.error_desc,
                location_name=location_name,
                line=load_result.line,
                act_index=load_result.act_index,
                snapshot=load_result.snapshot,
            )
        try:
            if not self._exec_location(location_name):
                return self._last_error(location_name)
            return RuntimeExecutionResult(ok=True, location_name=location_name, snapshot=self.snapshot())
        except Exception as exc:
            return RuntimeExecutionResult(ok=False, error_desc=f"QSP runtime 执行异常：{exc}", location_name=location_name)

    def execute_action(self, index: int) -> RuntimeExecutionResult:
        if not self._ready_for_interaction():
            return RuntimeExecutionResult(ok=False, error_desc="QSP runtime 尚未加载 world。")
        try:
            if not self._set_selected_action(index):
                return self._last_error("")
            if not self._execute_selected_action():
                return self._last_error("")
            return RuntimeExecutionResult(ok=True, snapshot=self.snapshot())
        except Exception as exc:
            return RuntimeExecutionResult(ok=False, error_desc=f"执行动作失败：{exc}")

    def submit_input(self, text: str) -> RuntimeExecutionResult:
        if not self._ready_for_interaction():
            return RuntimeExecutionResult(ok=False, error_desc="QSP runtime 尚未加载 world。")
        try:
            if not self._set_input_text(text):
                return self._last_error("")
            if not self._exec_user_input():
                return self._last_error("")
            return RuntimeExecutionResult(ok=True, snapshot=self.snapshot())
        except Exception as exc:
            return RuntimeExecutionResult(ok=False, error_desc=f"提交输入失败：{exc}")

    def snapshot(self) -> RuntimeSnapshot:
        if not self._ready_for_interaction():
            return RuntimeSnapshot(loaded=False, world_path=str(self.loaded_world_path or ""))
        bindings = self.bindings
        assert bindings is not None
        current_location = self._read_wchar_result(bindings.get_cur_loc)
        main_desc = self._read_wchar_result(bindings.get_main_desc)
        vars_desc = self._read_wchar_result(bindings.get_vars_desc)
        actions = self._read_actions()
        objects = self._read_objects()
        return RuntimeSnapshot(
            loaded=True,
            world_path=str(self.loaded_world_path or ""),
            current_location=current_location,
            main_desc=main_desc,
            vars_desc=vars_desc,
            actions=actions,
            objects=objects,
        )

    def close(self) -> None:
        self._deinit_runtime()
        self.loaded_world_path = None

    def _ready_for_interaction(self) -> bool:
        return self._initialized and self.bindings is not None and self.loaded_world_path is not None

    def _init_runtime(self) -> None:
        bindings = self.bindings
        assert bindings is not None
        if self._initialized:
            return
        if bindings.init_runtime is not None:
            bindings.init_runtime.restype = None
            bindings.init_runtime()
        self._initialized = True

    def _deinit_runtime(self) -> None:
        bindings = self.bindings
        if bindings is None or not self._initialized:
            return
        if bindings.deinit_runtime is not None:
            bindings.deinit_runtime.restype = None
            bindings.deinit_runtime()
        self._initialized = False

    def _load_world(self, world_path: Path) -> bool:
        bindings = self.bindings
        assert bindings is not None and bindings.load_game_world is not None
        bindings.load_game_world.argtypes = [ctypes.c_wchar_p]
        bindings.load_game_world.restype = ctypes.c_int
        return bool(bindings.load_game_world(str(world_path)))

    def _exec_location(self, location_name: str) -> bool:
        bindings = self.bindings
        assert bindings is not None and bindings.exec_location_code is not None
        bindings.exec_location_code.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        bindings.exec_location_code.restype = ctypes.c_int
        return bool(bindings.exec_location_code(location_name, 0))

    def _set_selected_action(self, index: int) -> bool:
        bindings = self.bindings
        assert bindings is not None and bindings.set_sel_action_index is not None
        bindings.set_sel_action_index.argtypes = [ctypes.c_int, ctypes.c_int]
        bindings.set_sel_action_index.restype = ctypes.c_int
        return bool(bindings.set_sel_action_index(index, 0))

    def _execute_selected_action(self) -> bool:
        bindings = self.bindings
        assert bindings is not None and bindings.exec_sel_action_code is not None
        bindings.exec_sel_action_code.argtypes = [ctypes.c_int]
        bindings.exec_sel_action_code.restype = ctypes.c_int
        return bool(bindings.exec_sel_action_code(0))

    def _set_input_text(self, text: str) -> bool:
        bindings = self.bindings
        assert bindings is not None and bindings.set_input_str_text is not None
        bindings.set_input_str_text.argtypes = [ctypes.c_wchar_p]
        bindings.set_input_str_text.restype = None
        bindings.set_input_str_text(text)
        return True

    def _exec_user_input(self) -> bool:
        bindings = self.bindings
        assert bindings is not None and bindings.exec_user_input is not None
        bindings.exec_user_input.argtypes = [ctypes.c_int]
        bindings.exec_user_input.restype = ctypes.c_int
        return bool(bindings.exec_user_input(0))

    def _read_actions(self) -> list[RuntimeAction]:
        bindings = self.bindings
        assert bindings is not None
        if bindings.get_actions_count is None or bindings.get_action_data is None:
            return []
        bindings.get_actions_count.argtypes = []
        bindings.get_actions_count.restype = ctypes.c_int
        count = max(0, int(bindings.get_actions_count()))
        bindings.get_action_data.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(ctypes.c_wchar_p)]
        bindings.get_action_data.restype = None
        actions: list[RuntimeAction] = []
        for index in range(count):
            img = ctypes.c_wchar_p()
            desc = ctypes.c_wchar_p()
            bindings.get_action_data(index, ctypes.byref(img), ctypes.byref(desc))
            actions.append(RuntimeAction(index=index, text=desc.value or "", image_path=img.value or ""))
        return actions

    def _read_objects(self) -> list[RuntimeObject]:
        bindings = self.bindings
        assert bindings is not None
        if bindings.get_objects_count is None or bindings.get_object_data is None:
            return []
        bindings.get_objects_count.argtypes = []
        bindings.get_objects_count.restype = ctypes.c_int
        count = max(0, int(bindings.get_objects_count()))
        bindings.get_object_data.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(ctypes.c_wchar_p)]
        bindings.get_object_data.restype = None
        objects: list[RuntimeObject] = []
        for index in range(count):
            img = ctypes.c_wchar_p()
            desc = ctypes.c_wchar_p()
            bindings.get_object_data(index, ctypes.byref(img), ctypes.byref(desc))
            objects.append(RuntimeObject(index=index, text=desc.value or "", image_path=img.value or ""))
        return objects

    def _read_wchar_result(self, func: object | None) -> str:
        if func is None:
            return ""
        func.argtypes = []
        func.restype = ctypes.c_wchar_p
        value = func()
        return value or ""

    def _last_error(self, location_name: str) -> RuntimeExecutionResult:
        bindings = self.bindings
        if bindings is None or bindings.get_last_error_data is None:
            return RuntimeExecutionResult(ok=False, error_desc="QSP runtime 未返回错误细节。", location_name=location_name)

        error_num = ctypes.c_int()
        error_loc = ctypes.c_wchar_p()
        error_act_index = ctypes.c_int(-1)
        error_line = ctypes.c_int(0)
        bindings.get_last_error_data.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        bindings.get_last_error_data.restype = None
        bindings.get_last_error_data(
            ctypes.byref(error_num),
            ctypes.byref(error_loc),
            ctypes.byref(error_act_index),
            ctypes.byref(error_line),
        )

        desc = ""
        if bindings.get_error_desc is not None:
            bindings.get_error_desc.argtypes = [ctypes.c_int]
            bindings.get_error_desc.restype = ctypes.c_wchar_p
            desc = bindings.get_error_desc(error_num.value) or ""

        return RuntimeExecutionResult(
            ok=False,
            error_code=error_num.value,
            error_desc=desc or "QSP runtime 返回了错误，但未提供描述。",
            location_name=error_loc.value or location_name,
            line=error_line.value,
            act_index=error_act_index.value,
            snapshot=self.snapshot(),
        )
