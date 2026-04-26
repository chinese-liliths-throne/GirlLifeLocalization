from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.qsp_runtime import QspRuntimeRunner, RuntimeSnapshot


@dataclass(slots=True)
class CoreRuntimeAction:
    index: int
    text: str
    image_path: str = ""


@dataclass(slots=True)
class CoreRuntimeObject:
    index: int
    text: str
    image_path: str = ""


@dataclass(slots=True)
class CoreRuntimeSnapshot:
    loaded: bool = False
    world_path: str = ""
    current_location: str = ""
    main_desc: str = ""
    vars_desc: str = ""
    actions: tuple[CoreRuntimeAction, ...] = ()
    objects: tuple[CoreRuntimeObject, ...] = ()
    runtime_error: str = ""


class RuntimeCoreService:
    def __init__(self, root: Path) -> None:
        self.runner = QspRuntimeRunner(root)

    def available(self) -> bool:
        return self.runner.available()

    def load_world(self, world_path: Path | str | None = None) -> CoreRuntimeSnapshot:
        result = self.runner.ensure_loaded(world_path)
        return self._to_snapshot(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def exec_location(self, location_name: str, *, world_path: Path | str | None = None) -> CoreRuntimeSnapshot:
        result = self.runner.exec_location(location_name, world_path=world_path)
        return self._to_snapshot(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def execute_action(self, index: int) -> CoreRuntimeSnapshot:
        result = self.runner.execute_action(index)
        return self._to_snapshot(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def submit_input(self, text: str) -> CoreRuntimeSnapshot:
        result = self.runner.submit_input(text)
        return self._to_snapshot(result.snapshot or RuntimeSnapshot(runtime_error=result.error_desc))

    def snapshot(self) -> CoreRuntimeSnapshot:
        return self._to_snapshot(self.runner.snapshot())

    def _to_snapshot(self, snapshot: RuntimeSnapshot) -> CoreRuntimeSnapshot:
        return CoreRuntimeSnapshot(
            loaded=snapshot.loaded,
            world_path=snapshot.world_path,
            current_location=snapshot.current_location,
            main_desc=snapshot.main_desc,
            vars_desc=snapshot.vars_desc,
            actions=tuple(CoreRuntimeAction(index=item.index, text=item.text, image_path=item.image_path) for item in snapshot.actions),
            objects=tuple(CoreRuntimeObject(index=item.index, text=item.text, image_path=item.image_path) for item in snapshot.objects),
            runtime_error=snapshot.runtime_error,
        )
