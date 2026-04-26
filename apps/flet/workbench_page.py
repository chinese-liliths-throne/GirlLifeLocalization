from __future__ import annotations

from pathlib import Path

import flet as ft

from src.core.paths import detect_source_root, paths
from src.qsrc import QsrcIssue

from .editor import code_editor_support, create_code_editor, default_autocomplete_words
from .host import is_mobile_host
from .models import DocumentModel, HostMode, ProjectModel, RuntimeSnapshotViewModel, WorkbenchState
from .services import BuildServiceAdapter, EditorService, LocalizationServiceAdapter, ProjectService, RuntimeService


class WorkbenchController:
    def __init__(self, page: ft.Page, *, host_mode: HostMode):
        self.page = page
        self.state = WorkbenchState(host_mode=host_mode)
        self.project_service = ProjectService()
        self.editor_service = EditorService()
        self.runtime_service = RuntimeService(host_mode, root=paths.root)
        self.build_service = BuildServiceAdapter()
        self.localization_service = LocalizationServiceAdapter()
        self.code_editor_support = code_editor_support()
        self.editor_controls: dict[Path, ft.Control] = {}

        self.project_filter = ft.TextField(label="筛选文件", dense=True, on_change=self._refresh_tree)
        self.search_field = ft.TextField(label="项目搜索", dense=True, on_submit=self._run_search)
        self.location_field = ft.TextField(label="地点", dense=True, value="start")
        self.input_field = ft.TextField(label="运行输入", dense=True, on_submit=self._submit_runtime_input)
        self.status_text = ft.Text(value=self.state.status_text, size=12)
        self.project_list = ft.ListView(expand=True, spacing=2)
        self.search_results = ft.ListView(expand=False, spacing=2, height=160)
        self.issues_list = ft.ListView(expand=True, spacing=4)
        self.runtime_actions = ft.ListView(expand=True, spacing=2)
        self.runtime_objects = ft.ListView(expand=True, spacing=2)
        self.main_desc = ft.TextField(label="主描述", multiline=True, min_lines=10, max_lines=18, read_only=True, expand=True)
        self.vars_desc = ft.TextField(label="变量描述", multiline=True, min_lines=8, max_lines=12, read_only=True, expand=True)
        self.build_output = ft.TextField(label="构建 / 任务", multiline=True, min_lines=6, max_lines=10, read_only=True, expand=True)

        self.editor_tabbar = ft.TabBar(tabs=[ft.Tab(label="欢迎")], scrollable=True)
        self.editor_tabview = ft.TabBarView(
            controls=[ft.Container(content=ft.Text("请先从项目树中打开一个 .qsrc 文件开始编辑。"), padding=16)],
            expand=True,
        )
        self.editor_tabs = ft.Tabs(
            content=ft.Column([self.editor_tabbar, self.editor_tabview], spacing=0, expand=True),
            length=1,
            expand=1,
            selected_index=0,
            animation_duration=150,
        )

        self.side_tabbar = ft.TabBar(
            tabs=[ft.Tab(label="问题"), ft.Tab(label="运行"), ft.Tab(label="构建")],
            scrollable=False,
        )
        self.side_tabview = ft.TabBarView(
            controls=[self.issues_list, self._runtime_panel(), self.build_output],
            expand=True,
        )
        self.side_tabs = ft.Tabs(
            content=ft.Column([self.side_tabbar, self.side_tabview], spacing=0, expand=True),
            length=3,
            expand=1,
            selected_index=0,
        )

    def build(self) -> None:
        self.page.title = f"GirlLife 工作台 ({self.state.host_mode.value})"
        self.page.window_min_width = 1200 if not is_mobile_host(self.state.host_mode) else 380
        self.page.window_min_height = 760 if not is_mobile_host(self.state.host_mode) else 720
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 10
        self.page.appbar = ft.AppBar(
            title=ft.Text("GirlLife 工作台"),
            actions=[
                ft.TextButton("打开目录", on_click=self._pick_directory),
                ft.TextButton("打开文件", on_click=self._pick_file),
                ft.TextButton("替换", on_click=self._run_replace),
                ft.TextButton("构建", on_click=self._build_project),
                ft.TextButton("加载世界", on_click=self._load_world),
            ],
        )
        self.page.add(self._layout())
        default_root = detect_source_root(paths.source_parent) or paths.root
        self._open_project(default_root)
        if self.code_editor_support.available:
            self._set_status(f"{self.state.status_text} | CodeEditor 已启用（当前为近似 QSP 高亮）")
        else:
            self._set_status(f"{self.state.status_text} | CodeEditor 不可用")

    def _layout(self) -> ft.Control:
        left_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Text("项目", size=16, weight=ft.FontWeight.BOLD),
                    self.project_filter,
                    self.search_field,
                    self.search_results,
                    ft.Divider(),
                    self.project_list,
                ],
                spacing=8,
                expand=True,
            ),
            width=280 if not is_mobile_host(self.state.host_mode) else None,
            padding=8,
        )
        center_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.FilledButton("保存", on_click=self._save_current_document),
                            ft.OutlinedButton("检查", on_click=self._lint_current_document),
                            ft.OutlinedButton("刷新运行", on_click=lambda _: self._set_runtime_snapshot(self.runtime_service.snapshot())),
                        ]
                    ),
                    self.editor_tabs,
                ],
                expand=True,
            ),
            expand=2,
            padding=8,
        )
        right_panel = ft.Container(content=self.side_tabs, expand=1, padding=8)
        body = (
            ft.Column([left_panel, center_panel, right_panel], expand=True)
            if is_mobile_host(self.state.host_mode)
            else ft.Row([left_panel, ft.VerticalDivider(width=1), center_panel, ft.VerticalDivider(width=1), right_panel], expand=True)
        )
        return ft.Column([body, ft.Divider(height=1), self.status_text], expand=True)

    def _runtime_panel(self) -> ft.Control:
        return ft.Column(
            [
                ft.Row([self.location_field, ft.FilledButton("运行", on_click=self._run_location)]),
                self.input_field,
                ft.Text("动作", weight=ft.FontWeight.BOLD),
                ft.Container(self.runtime_actions, height=180),
                ft.Text("物品", weight=ft.FontWeight.BOLD),
                ft.Container(self.runtime_objects, height=140),
                self.main_desc,
                self.vars_desc,
            ],
            spacing=8,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _open_project(self, target: Path) -> None:
        project = self.project_service.open_project(target)
        self.state.project = project
        self._refresh_tree()
        self._set_status(f"已打开项目：{project.root}")

    def _refresh_tree(self, *_args) -> None:
        project = self.state.project
        if not project:
            return
        needle = self.project_filter.value.strip().casefold() if self.project_filter.value else ""
        self.project_list.controls = []
        for file_path in project.qsrc_files:
            rel = file_path.relative_to(project.root)
            if needle and needle not in str(rel).casefold():
                continue
            self.project_list.controls.append(ft.TextButton(str(rel), on_click=lambda _e, p=file_path: self._open_document(p)))
        self.page.update()

    def _open_document(self, path: Path) -> None:
        project = self.state.project
        if not project:
            return
        document = self.state.open_documents.get(path)
        if document is None:
            document = self.editor_service.open_document(project, path)
            self.editor_service.lint_document(document)
        self.state.open_documents[path] = document
        self.state.active_document = path
        self._rebuild_tabs()
        self._render_issues(document)
        self._set_status(f"已打开文件：{document.relative_path}")

    def _rebuild_tabs(self) -> None:
        tabs: list[ft.Tab] = []
        views: list[ft.Control] = []
        self.editor_controls = {}
        active_paths = list(self.state.open_documents.keys())
        selected_index = 0
        for index, path in enumerate(active_paths):
            document = self.state.open_documents[path]
            if path == self.state.active_document:
                selected_index = index
            field = create_code_editor(
                value=document.current_text,
                autocomplete_words=self._autocomplete_words(document),
                on_change=lambda e, p=path: self._on_document_changed(p, self._event_value(e)),
            )
            self.editor_controls[path] = field
            tabs.append(ft.Tab(label=document.relative_path.name + (" *" if document.dirty else "")))
            views.append(field)
        if not tabs:
            tabs = [ft.Tab(label="欢迎")]
            views = [ft.Container(content=ft.Text("请先从项目树中打开一个 .qsrc 文件开始编辑。"), padding=16)]
            selected_index = 0
        self.editor_tabbar.tabs = tabs
        self.editor_tabview.controls = views
        self.editor_tabs.length = len(tabs)
        self.editor_tabs.selected_index = selected_index
        self.page.update()

    def _on_document_changed(self, path: Path, value: str) -> None:
        document = self.state.open_documents[path]
        was_dirty = document.dirty
        document.current_text = value
        document.dirty = document.current_text != document.original_text
        self.state.active_document = path
        self.editor_service.lint_document(document)
        self._render_issues(document)
        if was_dirty != document.dirty:
            self._rebuild_tabs()

    def _save_current_document(self, _event=None) -> None:
        document = self._current_document()
        if not document:
            return
        self.editor_service.save_document(document)
        self._rebuild_tabs()
        self._set_status(f"已保存：{document.relative_path}")

    def _lint_current_document(self, _event=None) -> None:
        document = self._current_document()
        if not document:
            return
        issues = self.editor_service.lint_document(document)
        self._render_issues(document)
        self._set_status(f"已检查 {document.relative_path}：{len(issues)} 个问题")

    def _render_issues(self, document: DocumentModel) -> None:
        self.issues_list.controls = []
        for issue in document.issues:
            if isinstance(issue, QsrcIssue):
                severity = "警告" if issue.severity == "warning" else "错误"
                label = f"[{severity}] {issue.error_code} 第 {issue.line} 行：{issue.error_desc}"
                self.issues_list.controls.append(
                    ft.TextButton(
                        label,
                        on_click=lambda _e, p=document.path, line=issue.line, column=issue.column: self._focus_issue(p, line, column),
                    )
                )
            else:
                self.issues_list.controls.append(ft.Text(str(issue), selectable=True))
        if not self.issues_list.controls:
            self.issues_list.controls.append(ft.Text("没有问题。"))
        self.page.update()

    def _run_search(self, _event=None) -> None:
        project = self.state.project
        if not project:
            return
        results = self.project_service.search(project, self.search_field.value or "")
        self.search_results.controls = [
            ft.TextButton(
                f"{item.path.relative_to(project.root)}:{item.line_no} {item.line_text}",
                on_click=lambda _e, p=item.path: self._open_document(p),
            )
            for item in results[:100]
        ]
        self.page.update()

    def _load_world(self, _event=None) -> None:
        snapshot = self.runtime_service.load_world()
        self._set_runtime_snapshot(snapshot)
        self._set_status("已加载运行世界。")

    def _run_location(self, _event=None) -> None:
        target = self.location_field.value.strip() or "start"
        snapshot = self.runtime_service.exec_location(target)
        self._set_runtime_snapshot(snapshot)
        self._set_status(f"已执行地点：{target}")

    def _submit_runtime_input(self, _event=None) -> None:
        snapshot = self.runtime_service.submit_input(self.input_field.value or "")
        self._set_runtime_snapshot(snapshot)
        self._set_status("已提交运行输入。")

    def _set_runtime_snapshot(self, snapshot: RuntimeSnapshotViewModel) -> None:
        self.state.runtime_snapshot = snapshot
        self.main_desc.value = snapshot.main_desc or snapshot.runtime_error
        self.vars_desc.value = snapshot.vars_desc
        self.runtime_actions.controls = [
            ft.TextButton(item.text or f"动作 {item.index}", on_click=lambda _e, idx=item.index: self._execute_action(idx))
            for item in snapshot.actions
        ] or [ft.Text("没有动作。")]
        self.runtime_objects.controls = [ft.Text(item.text or f"物品 {item.index}") for item in snapshot.objects] or [ft.Text("没有物品。")]
        if snapshot.current_location:
            self.location_field.value = snapshot.current_location
        self.page.update()

    def _execute_action(self, index: int) -> None:
        snapshot = self.runtime_service.execute_action(index)
        self._set_runtime_snapshot(snapshot)
        self._set_status(f"已执行动作 #{index}")

    def _build_project(self, _event=None) -> None:
        project = self.state.project
        if not project:
            return
        result = self.build_service.build_project(project)
        self.state.last_build = result
        details = [result.summary, *(str(path) for path in result.output_paths), *(str(path) for path in result.error_paths)]
        self.build_output.value = "\n".join(details)
        self.page.update()
        self._set_status(result.summary)

    def _run_replace(self, _event=None) -> None:
        message = self.localization_service.run_replace()
        self.build_output.value = message
        self.page.update()
        self._set_status(message)

    async def _pick_file(self, _event=None) -> None:
        files = await ft.FilePicker().pick_files(allow_multiple=False)
        if files:
            self._open_project(Path(files[0].path))

    async def _pick_directory(self, _event=None) -> None:
        picked = await ft.FilePicker().get_directory_path()
        if picked:
            self._open_project(Path(picked))

    def _current_document(self) -> DocumentModel | None:
        if not self.state.active_document:
            return None
        return self.state.open_documents.get(self.state.active_document)

    def _focus_issue(self, path: Path, line: int, column: int) -> None:
        document = self.state.open_documents.get(path)
        if document is None:
            self._open_document(path)
            document = self.state.open_documents.get(path)
        if document is None:
            return
        self.state.active_document = path
        control = self.editor_controls.get(path)
        if control is not None and hasattr(control, "selection") and line > 0:
            start, end = self._line_offsets(document.current_text, line, column)
            control.selection = ft.TextSelection(base_offset=start, extent_offset=end)
        self._set_status(f"已定位问题：{document.relative_path} 第 {line} 行")
        self.page.update()

    @staticmethod
    def _line_offsets(text: str, line: int, column: int) -> tuple[int, int]:
        lines = text.splitlines(keepends=True)
        if line <= 0 or line > len(lines):
            return 0, 0
        start = sum(len(item) for item in lines[: line - 1])
        current = lines[line - 1].rstrip("\r\n")
        col = max(column - 1, 0)
        col = min(col, len(current))
        return start + col, start + len(current)

    def _autocomplete_words(self, document: DocumentModel) -> list[str]:
        project_words: list[str] = []
        if self.state.project:
            project_words.extend(path.stem for path in self.state.project.qsrc_files[:4000])
        project_words.append(document.relative_path.stem)
        return default_autocomplete_words(project_words)

    @staticmethod
    def _event_value(event) -> str:
        if getattr(event, "data", None) is not None:
            return event.data
        control = getattr(event, "control", None)
        return getattr(control, "value", "") if control is not None else ""

    def _set_status(self, text: str) -> None:
        self.state.status_text = text
        self.status_text.value = text
        self.page.update()


def build_workbench_page(page: ft.Page, *, host_mode: HostMode) -> None:
    controller = WorkbenchController(page, host_mode=host_mode)
    controller.build()
