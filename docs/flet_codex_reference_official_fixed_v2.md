# Flet Python 官方文档修正版：给 Codex 的开发资料包

> 目标：把本文直接提供给 Codex / Cursor / Claude Code / Roo Code，让它按 Flet 当前官网文档生成、审查和迁移 Python Flet 应用。  
> 核对日期：2026-04-26。  
> 主要依据：Flet 官方文档 `https://flet.dev/docs/`、`https://flet.dev/docs/controls/codeeditor/`、`https://flet.dev/docs/controls/codeeditor/types/codelanguage/`、`https://flet.dev/docs/controls/codeeditor/types/gutterstyle/`。  
> 重点修正：CodeEditor、路由、自动更新、SharedPreferences / SecureStorage、扩展控件导入与第三方控件推荐策略。

---

## 0. 本版修正摘要

上一版资料中容易误导 Codex 的地方已修正：

1. **`page.go()` 不再写成“官方已废弃”**。官方 Page 参考仍列出 `go` 方法；但是官方路由 Cookbook 当前明确推荐 `await page.push_route()` 做编程式导航。因此，新项目优先用 `push_route()`，旧代码遇到 `page.go()` 可以识别，但不要主动生成。
2. **CodeEditor 按官网精确修正**：需要安装 `flet-code-editor`，导入 `import flet_code_editor as fce`，不是 `ft.CodeEditor`。
3. **CodeEditor API 按官网补全**：属性、事件、异步方法按 `CodeEditor` 页面整理；`CodeLanguage` 完整枚举和 `GutterStyle` 字段/默认值按对应类型页面补充。
4. **自动更新规则按官网修正**：Flet 会在 `main()` 和每个事件处理器结束时自动调用 `page.update()` 或最近 isolated ancestor 的 `.update()`；如果处理器里已经显式 `.update()`，自动更新会跳过以避免重复更新。
5. **SharedPreferences 写法补充新 Services 参考**：Cookbook 仍展示 `page.shared_preferences`，但 Page 参考把 `page.shared_preferences` 标为 deprecated；新代码优先用 `ft.SharedPreferences()`。
6. **`e.page.run_task(...)` 不作为默认模板**：官方示例更清楚的写法是直接把 `async def handler(e)` 绑定给 `on_click`。
7. **第三方控件分级**：优先使用 Flet 官方维护扩展包；社区包只作为谨慎候选，必须先核对维护状态、版本兼容、license 和平台支持。

---

## 1. 给 Codex 的系统提示词

```text
你是资深 Flet Python 开发助手。请根据 Flet 官方文档生成代码。

默认约束：
1. 使用 Python 3.10+。
2. 使用 import flet as ft。
3. 应用入口使用 ft.run(main)。不要主动生成旧式 ft.app(target=main)。
4. 简单应用可以命令式；复杂应用应拆分 views、components、services、state。
5. Flet 会在 main() 和事件处理器结束时自动更新 UI；不要机械地在每个事件最后写 page.update()。
6. 需要中途显示 loading、后台任务/线程更新 UI、批量更新、关闭 auto-update、或事件外更新 UI 时，才显式 page.update() / control.update() / page.schedule_update()。
7. 新项目路由优先使用 await page.push_route("/path")、page.route、page.views、page.on_route_change、page.on_view_pop。
8. page.go() 仍能在旧代码中出现，但新代码不要优先生成它；官方路由 Cookbook 推荐 push_route()。
9. 所有 route 字符串以 / 开头；根 route 是 /。
10. 多页面应用使用 ft.View，并从 page.route 派生 page.views，保持 URL、浏览器历史和 UI 一致。
11. CodeEditor 必须安装 flet-code-editor，并使用 import flet_code_editor as fce；不要写 ft.CodeEditor。
12. SharedPreferences 新代码优先使用 ft.SharedPreferences()；遇到 page.shared_preferences 要知道它是旧/兼容写法。
13. 敏感数据优先 flet-secure-storage；不要把密码、长期 token、私钥直接放 SharedPreferences / client storage。
14. 外部 HTTP API 使用 async + httpx，不要在事件处理器里用 requests 阻塞 UI。
15. 所有扩展包都必须写入 pyproject.toml dependencies；不能只依赖本机 pip install。
16. 移动端/Web 打包前核对官方平台支持；Web/Pyodide/WASM 场景避免依赖线程、subprocess 和 native-only 库。
17. 社区第三方包只在官方扩展不能满足时使用，且必须核对维护状态、license、源码仓库、平台支持和 Flet 版本兼容。
```

---

## 2. Flet 是什么

Flet 是用 Python 构建 Web、桌面和移动应用的框架，底层由 Flutter 渲染。它适合快速开发跨平台业务工具、管理后台、数据应用、桌面工具、移动原型和内部系统。

核心导入：

```python
import flet as ft
```

当前官网入门示例入口：

```python
ft.run(main)
```

不要主动写旧式：

```python
ft.app(target=main)
```

---

## 3. 安装、创建、运行

### 3.1 Python 要求

Flet 官方文档要求 Python 3.10 或更高版本。

### 3.2 安装

推荐 `uv`：

```bash
mkdir my-app
cd my-app
uv init --python='>=3.10'
uv venv
source .venv/bin/activate
uv add 'flet[all]'
uv run flet --version
uv run flet doctor
```

或 `pip`：

```bash
python -m venv .venv
source .venv/bin/activate
pip install 'flet[all]'
flet --version
flet doctor
```

升级：

```bash
uv add 'flet[all]' --upgrade
# 或
pip install 'flet[all]' --upgrade
```

### 3.3 创建项目

```bash
uv run flet create
# 或
flet create
```

官方 `flet create` 最小结构：

```text
README.md
pyproject.toml
src/
  assets/
    icon.png
  main.py
storage/
  data/
  temp/
```

注意：如果目录中已有 `README.md` 或 `pyproject.toml`，`flet create` 会替换它们。

### 3.4 运行

桌面运行：

```bash
uv run flet run
# 或
flet run
```

Web 运行：

```bash
uv run flet run --web
# 或
flet run --web
```

监听目录变化：

```bash
flet run --directory src/main.py
flet run --recursive src/main.py
```

---

## 4. 最小应用模板

```python
import flet as ft


def main(page: ft.Page):
    page.title = "Hello Flet"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    counter = ft.Text("0", size=40)

    def plus_click(e: ft.ControlEvent):
        counter.value = str(int(counter.value) + 1)
        # 通常无需 page.update()；事件处理结束会自动更新

    page.add(
        ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                counter,
                ft.IconButton(ft.Icons.ADD, on_click=plus_click),
            ],
        )
    )


if __name__ == "__main__":
    ft.run(main)
```

---

## 5. 自动更新规则

官网规则：Flet 会在 `main()` 和每个事件处理器结束时自动调用 `page.update()` 或最近 isolated ancestor 的 `.update()`。因此多数事件处理器不需要手写 `page.update()`。

```python
def main(page: ft.Page):
    def button_click(e):
        page.controls.append(ft.Text("Clicked!"))
        # 不需要 page.update()

    page.controls.append(ft.Button("Click me", on_click=button_click))
    # main 结束也会自动更新

ft.run(main)
```

如果事件处理器已经显式调用 `.update()`，自动更新会跳过，避免重复更新。

### 5.1 禁用自动更新

```python
import flet as ft


def main(page: ft.Page):
    def add_many_items(e):
        ft.context.disable_auto_update()
        for i in range(100):
            page.controls.append(ft.Text(f"Item {i}"))
        page.update()  # 只发送一次更新

    page.controls.append(ft.Button("Add items", on_click=add_many_items))


ft.run(main)
```

### 5.2 Codex 规则

```text
普通事件：不要写 page.update()。
批量更新：disable_auto_update 后最后 update 一次。
后台线程/任务：需要 page.update() 或 page.schedule_update()。
中途 loading：可以先改状态并 update，再 await 慢操作。
自定义 isolated control：可用 self.update()。
```

---

## 6. Page 核心对象

`Page` 是 `View` 控件的容器。每个新用户 session 会自动创建一个 page 和 root view。

### 6.1 常用属性

```python
page.title = "App"
page.theme_mode = ft.ThemeMode.SYSTEM
page.padding = 20
page.spacing = 10
page.scroll = ft.ScrollMode.AUTO
page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
page.vertical_alignment = ft.MainAxisAlignment.CENTER

page.route
page.query
page.views
page.window
page.platform
page.web
page.pwa
page.pyodide
page.wasm
page.session
page.pubsub
```

注意：Page 参考中 `page.shared_preferences`、`page.clipboard`、`page.url_launcher`、`page.storage_paths` 被标为 deprecated；新代码优先使用相应 Services，例如 `ft.SharedPreferences()`。

### 6.2 常用方法

```python
page.add(control1, control2)
page.update()
page.schedule_update()

await page.push_route("/settings")
page.show_dialog(ft.AlertDialog(...))
page.pop_dialog()

page.run_task(async_func, *args)
page.run_thread(sync_func, *args)
```

`page.go()` 在 Page 参考中仍作为 helper method 存在；但新项目请按 Navigation Cookbook 使用 `await page.push_route()`。

---

## 7. 官方路由模型

官方路由模型的核心：

```text
page.route              当前 route 字符串，例如 /、/store、/settings/mail
page.views              当前导航栈
page.on_route_change    route 改变时重建 views
page.on_view_pop        处理系统返回、AppBar 返回、浏览器返回
```

可靠模式：**把 `page.route` 作为单一事实来源，从它派生 `page.views`**。

### 7.1 官方风格路由模板

```python
import flet as ft


def main(page: ft.Page):
    page.title = "Routes Example"

    async def open_settings(e):
        await page.push_route("/settings")

    async def open_home(e):
        await page.push_route("/")

    def route_change(e=None):
        page.views.clear()

        page.views.append(
            ft.View(
                route="/",
                controls=[
                    ft.SafeArea(
                        content=ft.Column(
                            controls=[
                                ft.AppBar(title=ft.Text("Home")),
                                ft.Text("Home page"),
                                ft.Button("Go to settings", on_click=open_settings),
                            ]
                        )
                    )
                ],
            )
        )

        if page.route == "/settings":
            page.views.append(
                ft.View(
                    route="/settings",
                    controls=[
                        ft.SafeArea(
                            content=ft.Column(
                                controls=[
                                    ft.AppBar(title=ft.Text("Settings")),
                                    ft.Text("Settings page"),
                                    ft.Button("Go home", on_click=open_home),
                                ]
                            )
                        )
                    ],
                )
            )

        page.update()

    async def view_pop(e: ft.ViewPopEvent):
        if e.view is not None:
            page.views.remove(e.view)
            top_view = page.views[-1]
            await page.push_route(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    route_change()


if __name__ == "__main__":
    ft.run(main)
```

### 7.2 参数化路由

```python
troute = ft.TemplateRoute(page.route)

if troute.match("/books/:id"):
    book_id = troute.id
elif troute.match("/account/:account_id/orders/:order_id"):
    account_id = troute.account_id
    order_id = troute.order_id
```

### 7.3 Web URL strategy

```python
ft.run(main, route_url_strategy="hash")
```

可选策略：

```text
path: https://myapp.dev/store
hash: https://myapp.dev/#/store
```

---

## 8. 常用控件速查

### 8.1 文本与展示

```python
ft.Text("Hello", size=20, weight=ft.FontWeight.BOLD)
ft.Markdown("# Title\nSome **markdown**")
ft.SelectionArea(content=ft.Text("Selectable text"))
ft.Image(src="/images/logo.png", width=120)
```

### 8.2 输入

```python
ft.TextField(label="Name", value="", on_change=handler)
ft.Dropdown(label="Role", options=[ft.DropdownOption("admin")])
ft.Checkbox(label="Agree", value=False)
ft.Switch(label="Enabled", value=True)
ft.RadioGroup(content=ft.Column([...]))
ft.Slider(min=0, max=100, value=50)
ft.DatePicker()
ft.TimePicker()
```

### 8.3 按钮

```python
ft.Button("Save", on_click=save)
ft.TextButton("Cancel")
ft.FilledButton("Submit")
ft.OutlinedButton("Back")
ft.IconButton(ft.Icons.DELETE, on_click=delete)
ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=add)
```

### 8.4 布局

```python
ft.Row(controls=[...], alignment=ft.MainAxisAlignment.CENTER)
ft.Column(controls=[...], spacing=12)
ft.Container(content=..., padding=20, border_radius=12)
ft.Stack(controls=[...])
ft.SafeArea(content=..., expand=True)
ft.ResponsiveRow(controls=[...])
ft.ListView(expand=True, spacing=8)
ft.GridView(expand=True, runs_count=3)
ft.Card(content=ft.Container(...))
```

### 8.5 导航

```python
ft.View(route="/", controls=[...])
ft.AppBar(title=ft.Text("Title"))
ft.NavigationBar(destinations=[...])
ft.NavigationRail(destinations=[...])
ft.NavigationDrawer(controls=[...])
ft.Tabs(tabs=[...])
```

### 8.6 反馈

```python
page.show_dialog(ft.AlertDialog(title=ft.Text("Title"), content=ft.Text("Message")))
page.show_dialog(ft.SnackBar(content=ft.Text("Saved")))
page.show_dialog(ft.BottomSheet(content=ft.Text("More actions")))
```

---

## 9. 外部 API 调用模板

```python
import os

import flet as ft
import httpx


API_URL = "https://api.example.com/items"
API_KEY = os.getenv("MY_APP_API_KEY")


async def fetch_items() -> list[dict]:
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(API_URL, headers=headers)
        response.raise_for_status()
        return response.json()


async def main(page: ft.Page):
    page.title = "API Demo"

    status = ft.Text("Ready")
    items = ft.ListView(expand=True, spacing=8)

    async def load(e: ft.ControlEvent):
        status.value = "Loading..."
        page.update()  # 中途 loading 需要立即显示

        try:
            data = await fetch_items()
            items.controls.clear()
            for item in data:
                items.controls.append(
                    ft.ListTile(
                        title=ft.Text(str(item.get("name", "Unnamed"))),
                        subtitle=ft.Text(str(item.get("id", ""))),
                    )
                )
            status.value = f"Loaded {len(data)} items"
        except httpx.HTTPError as ex:
            status.value = f"Network error: {ex}"
        except Exception as ex:
            status.value = f"Error: {ex}"

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[ft.Button("Load", on_click=load), status, items],
            ),
        )
    )


ft.run(main)
```

---

## 10. SharedPreferences / Client Storage / SecureStorage

### 10.1 SharedPreferences：新代码优先 Services 写法

```python
prefs = ft.SharedPreferences()
await prefs.set("acme.my_app.theme", "dark")
theme = await prefs.get("acme.my_app.theme")
exists = await prefs.contains_key("acme.my_app.theme")
keys = await prefs.get_keys("acme.my_app.")
await prefs.remove("acme.my_app.theme")
```

官方 Cookbook 也展示过：

```python
await page.shared_preferences.set("key", "value")
```

但 Page 参考中 `page.shared_preferences` 标为 deprecated。给 Codex 的规则：

```text
新代码用 ft.SharedPreferences()。
旧代码看到 page.shared_preferences 能读懂并逐步迁移。
非敏感设置可以用 SharedPreferences。
密码、长期 token、私钥不要用 SharedPreferences。
key 加应用前缀，例如 acme.my_app.xxx。
慎用 clear()，它可能清掉同一 Flet client 下其他 app 的偏好。
```

### 10.2 SecureStorage

安装：

```bash
uv add flet-secure-storage
# 或
pip install flet-secure-storage
```

用法：

```python
import flet as ft
import flet_secure_storage as fss


async def main(page: ft.Page):
    storage = fss.SecureStorage()

    await storage.set("access_token", "secret")
    token = await storage.get("access_token")
    exists = await storage.contains_key("access_token")
    await storage.remove("access_token")


ft.run(main)
```

注意：Linux 构建/运行可能需要 `libsecret-1-dev`、`libsecret-1-0` 和 keyring service。

---

## 11. CodeEditor 官方修正版（含 CodeLanguage / GutterStyle）

> 官方来源：
> - `https://flet.dev/docs/controls/codeeditor/`
> - `https://flet.dev/docs/controls/codeeditor/types/codelanguage/`
> - `https://flet.dev/docs/controls/codeeditor/types/gutterstyle/`

### 11.1 安装与导入

`CodeEditor` 来自扩展包，不是核心 `flet` 包。必须先把扩展包加入项目依赖：

```bash
uv add flet-code-editor
# 或
pip install flet-code-editor
```

```python
import flet as ft
import flet_code_editor as fce
```

错误写法：

```python
ft.CodeEditor(...)
```

正确写法：

```python
fce.CodeEditor(...)
```

给 Codex 的硬规则：

```text
生成 CodeEditor 相关代码时：
1. 一律 import flet_code_editor as fce。
2. 一律使用 fce.CodeEditor、fce.CodeLanguage、fce.CodeTheme、fce.CustomCodeTheme、fce.GutterStyle。
3. 不要写 ft.CodeEditor、ft.CodeLanguage、ft.CodeTheme、ft.GutterStyle。
4. flet-code-editor 必须进入 pyproject.toml dependencies。
```

### 11.2 CodeEditor 官方属性

| 属性 | 类型/含义 | Codex 使用建议 |
|---|---|---|
| `autocomplete` | `Optional[bool] = False`，是否启用自动完成 | 只有传入 `autocomplete_words` 时才开启 |
| `autocomplete_words` | `Optional[list[str]] = None`，自动完成候选词 | 适合放 Flet 控件名、领域关键词、API 名称 |
| `autofocus` | `Optional[bool] = False`，无其他控件聚焦时是否自动聚焦 | 编辑页可设 `True`，表单页谨慎 |
| `code_theme` | `Optional[Union[fce.CodeTheme, fce.CustomCodeTheme]]` | 简单用内置 `fce.CodeTheme.*`，深度定制用 `fce.CustomCodeTheme` |
| `gutter_style` | `Optional[fce.GutterStyle]` | 控制行号、折叠、错误标记、宽度、背景 |
| `language` | `Optional[fce.CodeLanguage]` | 必须用 `fce.CodeLanguage.PYTHON` 这类 enum，不要传普通字符串 |
| `padding` | `Optional[ft.PaddingValue]` | 常用 `padding=10` |
| `read_only` | `Optional[bool] = False`，是否只读 | 代码预览、日志查看器设 `True` |
| `selection` | `Optional[ft.TextSelection]` | 控制初始选区或移动光标 |
| `text_style` | `Optional[ft.TextStyle]` | 建议设置等宽字体 fallback |
| `value` | `Optional[str]`，完整文本内容 | 读取/保存时用 `editor.value or ""` |

### 11.3 CodeEditor 官方事件

| 事件 | 说明 | 常见用途 |
|---|---|---|
| `on_blur` | 编辑器失焦 | 自动保存草稿、校验 |
| `on_change` | 文本变化 | 更新保存状态、实时字数/行数、debounce 校验 |
| `on_focus` | 编辑器获得焦点 | 改变状态栏、显示快捷键提示 |
| `on_selection_change` | 选区或光标位置变化 | 展示选中文本、光标位置、实现“全选/跳转” |

`on_selection_change` 事件类型示例：

```python
def handle_selection_change(e: ft.TextSelectionChangeEvent[fce.CodeEditor]):
    selected_text = e.selected_text
    start = e.selection.start
    end = e.selection.end
```

### 11.4 CodeEditor 官方异步方法

这些方法是异步方法，必须 `await`：

```python
await editor.focus()
await editor.fold_at(line_number)
await editor.fold_comment_at_line_zero()
await editor.fold_imports()
```

| 方法 | 说明 |
|---|---|
| `focus()` | 请求编辑器获得焦点 |
| `fold_at(line_number: int)` | 折叠指定行开始的代码块 |
| `fold_comment_at_line_zero()` | 折叠第 0 行开始的注释块 |
| `fold_imports()` | 折叠 import 区域 |

### 11.5 CodeLanguage 官方类型

`CodeLanguage` 继承 `enum.Enum`，用于 `CodeEditor.language`。官网列出大量语法高亮语言。生成代码时必须使用：

```python
language=fce.CodeLanguage.PYTHON
```

不要写：

```python
language="python"                 # 不推荐
language=ft.CodeLanguage.PYTHON    # 错误
```

常用映射：

| 文件/用途 | 推荐枚举 |
|---|---|
| Python | `fce.CodeLanguage.PYTHON` |
| JavaScript | `fce.CodeLanguage.JAVASCRIPT` |
| TypeScript | `fce.CodeLanguage.TYPESCRIPT` |
| HTML | `fce.CodeLanguage.XML` 或按内容选择 `HTMLBARS` |
| CSS | `fce.CodeLanguage.CSS` |
| JSON | `fce.CodeLanguage.JSON` |
| YAML | `fce.CodeLanguage.YAML` |
| Markdown | `fce.CodeLanguage.MARKDOWN` |
| Bash/Shell | `fce.CodeLanguage.BASH` / `fce.CodeLanguage.SHELL` |
| SQL | `fce.CodeLanguage.SQL` |
| PostgreSQL | `fce.CodeLanguage.PGSQL` |
| Dart | `fce.CodeLanguage.DART` |
| Flutter/Flet Python 示例 | `fce.CodeLanguage.PYTHON` |
| Dockerfile | `fce.CodeLanguage.DOCKERFILE` |
| Diff/Patch | `fce.CodeLanguage.DIFF` |
| C++ | `fce.CodeLanguage.CPP` |
| C# | `fce.CodeLanguage.CS` |
| Java | `fce.CodeLanguage.JAVA` |
| Go | `fce.CodeLanguage.GO` |
| Rust | `fce.CodeLanguage.RUST` |
| PHP | `fce.CodeLanguage.PHP` |
| Ruby | `fce.CodeLanguage.RUBY` |
| Swift | `fce.CodeLanguage.SWIFT` |
| Kotlin | `fce.CodeLanguage.KOTLIN` |
| R | `fce.CodeLanguage.R` |
| MATLAB | `fce.CodeLanguage.MATLAB` |
| Plain text | `fce.CodeLanguage.PLAINTEXT` |

完整枚举速查（官方 CodeLanguage 页面）：

```text
ABNF - ABNF
ACCESSLOG - Accesslog
ACTIONSCRIPT - ActionScript
ADA - Ada
ANGELSCRIPT - Angelscript
APACHE - Apache
APPLESCRIPT - AppleScript
ARCADE - Arcade
ARDUINO - Arduino
ARMASM - ARM Assembly
ASCIIDOC - AsciiDoc
ASPECTJ - Aspectj
AUTOHOTKEY - AutoHotkey
AUTOIT - AutoIt
AVRASM - AVR Assembly
AWK - Awk
AXAPTA - Axapta
BASH - Bash
BASIC - Basic
BNF - BNF
BRAINFUCK - Brainfuck
CAL - Cal
CAPNPROTO - Cap'n Proto
CEYLON - Ceylon
CLEAN - Clean
CLOJURE - Clojure
CLOJURE_REPL - Clojure REPL
CMAKE - CMake
COFFEESCRIPT - CoffeeScript
COQ - Coq
COS - Cos
CPP - C++
CRMSH - Crmsh
CRYSTAL - Crystal
CS - C#
CSP - Csp
CSS - CSS
D - D
DART - Dart
DELPHI - Delphi
DIFF - Diff
DJANGO - Django
DNS - DNS
DOCKERFILE - Dockerfile
DOS - DOS
DSCONFIG - DSConfig
DTS - DTS
DUST - Dust
EBNF - EBNF
ELIXIR - Elixir
ELM - Elm
ERB - Erb
ERLANG - Erlang
ERLANG_REPL - Erlang REPL
EXCEL - Excel
FIX - Fix
FLIX - Flix
FORTRAN - Fortran
FSHARP - F#
GAMS - Gams
GAUSS - Gauss
GCODE - G-code
GHERKIN - Gherkin
GLSL - GLSL
GML - GML
GN - Gn
GO - Go
GOLO - Golo
GRADLE - Gradle
GRAPHQL - GraphQL
GROOVY - Groovy
HAML - Haml
HANDLEBARS - Handlebars
HASKELL - Haskell
HAXE - Haxe
HSP - Hsp
HTMLBARS - HTMLBars
HTTP - HTTP
HY - Hy
INFORM7 - INFORM7
INI - INI
IRPF90 - IRPF90
ISBL - ISBL
JAVA - Java
JAVASCRIPT - Javascript
JBOSS_CLI - JBoss CLI
JSON - JSON
JULIA - Julia
JULIA_REPL - Julia REPL
KOTLIN - Kotlin
LASSO - Lasso
LDIF - LDIF
LEAF - Leaf
LESS - Less
LISP - Lisp
LIVECODESERVER - LiveCode Server
LIVESCRIPT - Livescript
LLVM - LLVM
LSL - LSL
LUA - Lua
MAKEFILE - Makefile
MARKDOWN - Markdown
MATHEMATICA - Mathematica
MATLAB - Matlab
MAXIMA - Maxima
MEL - Mel
MERCURY - Mercury
MIPSASM - MIPS Assembly
MIZAR - Mizar
MOJOLICIOUS - Mojolicious
MONKEY - Monkey
MOONSCRIPT - MoonScript
N1QL - N1QL
NGINX - Nginx
NIMROD - Nimrod
NIX - Nix
NSIS - NSIS
OBJECTIVEC - Objective-C
OCAML - OCaml
ONE_C - 1C
OPENSCAD - OpenSCAD
OXYGENE - Oxygene
PARSER3 - PARSER3
PERL - Perl
PF - PF
PGSQL - PostgreSQL
PHP - PHP
PLAINTEXT - Plain text
PONY - Pony
POWERSHELL - PowerShell
PROCESSING - Processing
PROFILE - Profile
PROLOG - Prolog
PROPERTIES - Properties
PROTOBUF - Protocol Buffers
PUPPET - Puppet
PUREBASIC - PureBasic
PYTHON - Python
Q - Q
QML - QML
R - R
REASONML - ReasonML
RIB - Rib
ROBOCONF - Roboconf
ROUTEROS - RouterOS
RSL - RSL
RUBY - Ruby
RULESLANGUAGE - Rules language
RUST - Rust
SAS - SAS
SCALA - Scala
SCHEME - Scheme
SCILAB - Scilab
SCSS - SCSS
SHELL - Shell
SMALI - Smali
SMALLTALK - Smalltalk
SML - SML
SOLIDITY - Solidity
SQF - SQF
SQL - SQL
STAN - Stan
STATA - Stata
STEP21 - STEP21
STYLUS - Stylus
SUBUNIT - SubUnit
SWIFT - Swift
TAGGERSCRIPT - Tagger Script
TAP - Tap
TCL - Tcl
TEX - TeX
THRIFT - Thrift
TP - TP
TWIG - Twig
TYPESCRIPT - TypeScript
VALA - Vala
VBNET - VB.NET
VBSCRIPT - VBScript
VBSCRIPT_HTML - VBScript HTML
VERILOG - Verilog
VHDL - VHDL
VIM - Vim script
VUE - Vue
X86ASM - x86 Assembly
XL - Xl
XML - XML
XQUERY - XQuery
YAML - YAML
ZEPHIR - Zephir
```

给 Codex 的选择策略：

```text
根据文件扩展名选择 CodeLanguage：
.py -> PYTHON
.js/.mjs/.cjs -> JAVASCRIPT
.ts/.tsx -> TYPESCRIPT
.json -> JSON
.yaml/.yml -> YAML
.md -> MARKDOWN
.sh/.bash -> BASH 或 SHELL
.sql -> SQL，PostgreSQL 专用脚本可用 PGSQL
Dockerfile -> DOCKERFILE
.diff/.patch -> DIFF
.txt/未知 -> PLAINTEXT
```

### 11.6 GutterStyle 官方类型

`GutterStyle` 用于配置 CodeEditor 左侧 gutter，也就是行号/折叠/错误提示区域。

```python
gutter_style = fce.GutterStyle(
    background_color=ft.Colors.GREY_100,
    margin=0,
    show_errors=True,
    show_folding_handles=True,
    show_line_numbers=True,
    text_style=ft.TextStyle(font_family="monospace", size=12),
    width=72,
)
```

官方字段与默认值：

| 字段 | 类型/默认值 | 说明 | Codex 使用建议 |
|---|---|---|---|
| `background_color` | `Optional[ColorValue] = None` | gutter 背景色 | 与编辑器主题对齐；暗色主题用深灰，亮色主题用浅灰 |
| `margin` | `Optional[Number] = None` | gutter 外边距 | 通常 `0` 或不设置 |
| `show_errors` | `bool = True` | 是否在 gutter 显示错误 | 默认保留 `True` |
| `show_folding_handles` | `bool = True` | 是否显示折叠手柄 | 代码编辑器保留 `True`；只读预览可设 `False` |
| `show_line_numbers` | `bool = True` | 是否显示行号 | 代码编辑/日志排错建议 `True` |
| `text_style` | `Optional[ft.TextStyle] = None` | 行号文本样式 | 建议与编辑器正文共用等宽字体 |
| `width` | `Optional[Number] = None` | gutter 固定宽度 | 常用 `56`、`64`、`72`、`80`；代码行数多时加宽 |

只读预览推荐：

```python
preview_gutter = fce.GutterStyle(
    show_errors=False,
    show_folding_handles=False,
    show_line_numbers=True,
    width=56,
)
```

编辑器推荐：

```python
editor_gutter = fce.GutterStyle(
    show_errors=True,
    show_folding_handles=True,
    show_line_numbers=True,
    width=80,
    text_style=ft.TextStyle(
        font_family="monospace",
        font_family_fallback=["SF Mono", "Menlo", "Roboto Mono", "Consolas", "Ubuntu Mono", "Courier New"],
        size=12,
    ),
)
```

### 11.7 基础示例

```python
import flet as ft
import flet_code_editor as fce


CODE = '''import flet as ft


def main(page: ft.Page):
    page.add(ft.Text("Hello"))


ft.run(main)
'''


def main(page: ft.Page):
    page.title = "CodeEditor Basic"

    page.add(
        ft.SafeArea(
            expand=True,
            content=fce.CodeEditor(
                language=fce.CodeLanguage.PYTHON,
                code_theme=fce.CodeTheme.ATOM_ONE_LIGHT,
                value=CODE,
                expand=True,
                on_change=lambda e: print("Changed:", e.data),
            ),
        )
    )


if __name__ == "__main__":
    ft.run(main)
```

### 11.8 选区、行号、折叠、自动完成

```python
import flet as ft
import flet_code_editor as fce


CODE = '''import json
import textwrap

print("Flet CodeEditor")
'''


FONT_FAMILIES = [
    "SF Mono",
    "Menlo",
    "Roboto Mono",
    "Consolas",
    "Ubuntu Mono",
    "Courier New",
]


def main(page: ft.Page):
    page.title = "CodeEditor Advanced"

    selection_info = ft.Text("No selection")
    caret_info = ft.Text("Caret: -")

    text_style = ft.TextStyle(
        font_family="monospace",
        font_family_fallback=FONT_FAMILIES,
        size=12,
    )

    gutter_style = fce.GutterStyle(
        text_style=text_style,
        show_line_numbers=True,
        show_folding_handles=True,
        show_errors=True,
        width=80,
    )

    def handle_selection_change(e: ft.TextSelectionChangeEvent[fce.CodeEditor]):
        if e.selected_text:
            normalized = " ".join(e.selected_text.split())
            selection_info.value = f"Selection ({len(e.selected_text)} chars): {normalized[:80]}"
        else:
            selection_info.value = "No selection"
        caret_info.value = f"start={e.selection.start}, end={e.selection.end}"

    editor = fce.CodeEditor(
        language=fce.CodeLanguage.PYTHON,
        code_theme=fce.CodeTheme.ATOM_ONE_LIGHT,
        autocomplete=True,
        autocomplete_words=["Container", "Button", "Text", "Row", "Column"],
        value=CODE,
        text_style=text_style,
        gutter_style=gutter_style,
        padding=10,
        on_selection_change=handle_selection_change,
        expand=True,
    )

    async def select_all(e: ft.Event[ft.Button]):
        await editor.focus()
        editor.selection = ft.TextSelection(
            base_offset=0,
            extent_offset=len(editor.value or ""),
        )

    async def move_caret_to_start(e: ft.Event[ft.Button]):
        await editor.focus()
        editor.selection = ft.TextSelection(base_offset=0, extent_offset=0)

    async def fold_imports(e: ft.Event[ft.Button]):
        await editor.fold_imports()

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    editor,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Button("Select all", on_click=select_all),
                            ft.Button("Move caret to start", on_click=move_caret_to_start),
                            ft.Button("Fold imports", on_click=fold_imports),
                        ],
                    ),
                    selection_info,
                    caret_info,
                ],
            ),
        )
    )


if __name__ == "__main__":
    ft.run(main)
```

### 11.9 初始选区与只读预览

```python
editor = fce.CodeEditor(
    language=fce.CodeLanguage.PYTHON,
    value="print('hello')",
    selection=ft.TextSelection(base_offset=0, extent_offset=5),
    autofocus=True,
    expand=True,
)
```

只读代码预览：

```python
preview = fce.CodeEditor(
    language=fce.CodeLanguage.JSON,
    code_theme=fce.CodeTheme.ATOM_ONE_DARK,
    value='{"status": "ok"}',
    read_only=True,
    gutter_style=fce.GutterStyle(
        show_errors=False,
        show_folding_handles=False,
        show_line_numbers=True,
        width=56,
    ),
    expand=True,
)
```

### 11.10 按文件名自动选择 CodeLanguage

```python
from pathlib import Path

import flet_code_editor as fce


LANGUAGE_BY_SUFFIX = {
    ".py": fce.CodeLanguage.PYTHON,
    ".js": fce.CodeLanguage.JAVASCRIPT,
    ".mjs": fce.CodeLanguage.JAVASCRIPT,
    ".cjs": fce.CodeLanguage.JAVASCRIPT,
    ".ts": fce.CodeLanguage.TYPESCRIPT,
    ".tsx": fce.CodeLanguage.TYPESCRIPT,
    ".json": fce.CodeLanguage.JSON,
    ".yaml": fce.CodeLanguage.YAML,
    ".yml": fce.CodeLanguage.YAML,
    ".md": fce.CodeLanguage.MARKDOWN,
    ".sh": fce.CodeLanguage.BASH,
    ".bash": fce.CodeLanguage.BASH,
    ".sql": fce.CodeLanguage.SQL,
    ".css": fce.CodeLanguage.CSS,
    ".xml": fce.CodeLanguage.XML,
    ".html": fce.CodeLanguage.XML,
    ".dockerfile": fce.CodeLanguage.DOCKERFILE,
    ".diff": fce.CodeLanguage.DIFF,
    ".patch": fce.CodeLanguage.DIFF,
    ".txt": fce.CodeLanguage.PLAINTEXT,
}


def guess_code_language(filename: str) -> fce.CodeLanguage:
    path = Path(filename)
    if path.name.lower() == "dockerfile":
        return fce.CodeLanguage.DOCKERFILE
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), fce.CodeLanguage.PLAINTEXT)
```

### 11.11 安全规则

```text
不要默认生成 exec(editor.value)。
如果只是检查 Python 代码，优先 ast.parse。
如果必须运行用户代码，必须有独立沙箱、超时、资源限制、文件系统隔离、网络限制。
移动端和 Web 不要假设 subprocess 可用。
CodeEditor 只是编辑器，不是完整 IDE/LSP。
```

安全语法检查示例：

```python
import ast

import flet as ft
import flet_code_editor as fce


def main(page: ft.Page):
    result = ft.Text()
    editor = fce.CodeEditor(
        language=fce.CodeLanguage.PYTHON,
        value="print('hello')",
        expand=True,
    )

    def check_syntax(e):
        try:
            ast.parse(editor.value or "")
            result.value = "Syntax OK"
        except SyntaxError as exc:
            result.value = f"Syntax error: line {exc.lineno}: {exc.msg}"

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[editor, ft.Button("Check syntax", on_click=check_syntax), result],
            ),
        )
    )


ft.run(main)
```

## 12. 官方扩展控件 / 服务优先清单

优先使用 Flet 官方文档已收录的控件和服务。使用时必须把对应包加入 `pyproject.toml`。

| 能力 | 包名 | 常用导入 | 说明 |
|---|---|---|---|
| 代码编辑器 | `flet-code-editor` | `import flet_code_editor as fce` | 编辑并高亮源代码 |
| 图表 | `flet-charts` | `import flet_charts as fch` | Bar、Line、Pie、Scatter、Radar、Plotly、Matplotlib 等 |
| 增强表格 | `flet-datatable2` | `import flet_datatable2 as fdt` | sticky headers、固定行/列等增强 DataTable |
| 地图 | `flet-map` | `import flet_map as ftm` | 基于 flutter_map，支持瓦片、markers、layers |
| 颜色选择器 | `flet-color-pickers` | 以官方页面为准 | ColorPicker、BlockPicker、HueRingPicker 等 |
| WebView | `flet-webview` | `import flet_webview as fwv` | iOS、Android、macOS、Web 支持；Windows/Linux 不支持 |
| Rive | `flet-rive` | 以官方页面为准 | Rive 动画 |
| Lottie | `flet-lottie` | 以官方页面为准 | Lottie 动画 |
| Video | `flet-video` | 以官方页面为准 | 视频播放器 |
| Camera | `flet-camera` | 以官方页面为准 | 相机预览、拍照、视频、帧流 |
| Audio | `flet-audio` | 以官方页面为准 | 音频播放 |
| AudioRecorder | `flet-audio-recorder` | 以官方页面为准 | 录音 |
| Geolocator | `flet-geolocator` | 以官方页面为准 | 定位 |
| PermissionHandler | `flet-permission-handler` | 以官方页面为准 | 权限请求 |
| SecureStorage | `flet-secure-storage` | `import flet_secure_storage as fss` | 安全 key-value 存储 |
| Flashlight | `flet-flashlight` | 以官方页面为准 | 闪光灯 |
| Ads | `flet-ads` | 以官方页面为准 | 广告 |

安装示例：

```bash
uv add flet-code-editor flet-charts flet-datatable2 flet-map flet-webview flet-secure-storage
```

`pyproject.toml` 示例：

```toml
[project]
name = "my-flet-app"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "flet[all]",
    "flet-code-editor",
    "flet-charts",
    "flet-datatable2",
    "flet-map",
    "flet-webview",
    "flet-secure-storage",
]
```

Codex 规则：

```text
官方扩展包的导入、类名、平台支持，以对应官方文档页为准。
不要凭包名猜所有类名。
打包前确认 target platform 支持。
WebView 官方平台支持：macOS、iOS、Android、Web；Windows/Linux 不支持。
Map 必须遵守 tile provider 的 attribution、rate limit 和 usage policy。
SecureStorage 在 Linux 需要额外 libsecret/keyring 环境。
```

---

## 13. 官方扩展示例

### 13.1 flet-charts

安装：

```bash
uv add flet-charts
```

```python
import flet as ft
import flet_charts as fch


def main(page: ft.Page):
    page.add(
        ft.SafeArea(
            expand=True,
            content=fch.BarChart(
                expand=True,
                interactive=True,
                max_y=100,
                groups=[
                    fch.BarChartGroup(
                        x=0,
                        rods=[fch.BarChartRod(from_y=0, to_y=40)],
                    ),
                    fch.BarChartGroup(
                        x=1,
                        rods=[fch.BarChartRod(from_y=0, to_y=80)],
                    ),
                ],
            ),
        )
    )


ft.run(main)
```

### 13.2 flet-map

安装：

```bash
uv add flet-map
```

```python
import flet as ft
import flet_map as ftm


def main(page: ft.Page):
    page.add(
        ft.SafeArea(
            expand=True,
            content=ftm.Map(
                expand=True,
                layers=[
                    ftm.TileLayer(
                        url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                        on_image_error=lambda e: print("Tile error:", e.data),
                    ),
                ],
            ),
        )
    )


ft.run(main)
```

### 13.3 flet-datatable2

安装：

```bash
uv add flet-datatable2
```

```python
import flet as ft
import flet_datatable2 as fdt


def main(page: ft.Page):
    page.add(
        ft.SafeArea(
            content=fdt.DataTable2(
                empty=ft.Text("This table is empty."),
                columns=[
                    fdt.DataColumn2(label=ft.Text("First name")),
                    fdt.DataColumn2(label=ft.Text("Last name")),
                    fdt.DataColumn2(label=ft.Text("Age"), numeric=True),
                ],
            )
        )
    )


ft.run(main)
```

### 13.4 flet-webview

安装：

```bash
uv add flet-webview
```

```python
import flet as ft
import flet_webview as fwv


def main(page: ft.Page):
    page.add(
        ft.SafeArea(
            expand=True,
            content=fwv.WebView(
                url="https://flet.dev",
                on_page_started=lambda e: print("Page started"),
                on_page_ended=lambda e: print("Page ended"),
                on_web_resource_error=lambda e: print("WebView error:", e.data),
                expand=True,
            ),
        )
    )


ft.run(main)
```

### 13.5 flet-secure-storage

```python
import flet as ft
import flet_secure_storage as fss


async def main(page: ft.Page):
    storage = fss.SecureStorage()
    result = ft.Text()

    async def save(e):
        await storage.set("demo.token", "secret-token")
        result.value = "saved"

    async def load(e):
        result.value = await storage.get("demo.token") or "missing"

    page.add(
        ft.Column(
            controls=[
                ft.Button("Save", on_click=save),
                ft.Button("Load", on_click=load),
                result,
            ]
        )
    )


ft.run(main)
```

---

## 14. 社区第三方控件/库推荐策略

> 原则：Flet 生态以官方扩展为主。社区包只在官方扩展不能满足需求时作为候选，不要让 Codex 默认引入未经核对的包。

### 14.1 谨慎候选

| 包 | 定位 | 使用建议 |
|---|---|---|
| `flet-contrib` | 社区 Python-only 可复用控件集合；公开资料显示包含 ColorPicker | 可用于快速原型；生产前检查维护频率、兼容性和 license |
| `flet-easy` | Flet 路由、装饰器、中间件、JWT 等结构化开发辅助 | 适合想要更强路由/项目结构约束的项目；先确认是否兼容当前 Flet 版本 |
| `fce-enhanced` | 基于 `flet-code-editor` 的增强编辑器，提供文件 I/O、搜索替换、主题选择等 | 适合代码编辑器原型；生产前必须审查源码与安全边界 |
| `flet-fastapi` | 把 Flet web app 挂到 FastAPI / Dashboard 场景 | 适合已有 FastAPI 后端；核对版本与部署方式 |

### 14.2 引入社区包前的检查清单

```text
1. 最近 6-12 个月是否维护。
2. 是否明确支持当前 Flet 版本。
3. 是否支持目标平台：Web / Windows / macOS / Linux / iOS / Android。
4. 是否有源码仓库、license、issue 记录。
5. 是否依赖 native/binary 包，移动端能否 flet build。
6. 是否执行代码、读取文件、开启 WebView bridge 等高风险能力。
7. 能否用官方扩展或少量自写控件替代。
8. 是否会锁死旧 API，例如 ft.app、page.go 老模板、大量强制 page.update。
```

### 14.3 不推荐默认使用

```text
包多年未更新。
没有 license。
没有源码仓库。
只支持旧 Flet API。
需要用户安装复杂 native SDK。
和官方扩展能力重复但维护弱。
PyPI 描述夸张但文档空白。
安全边界不清晰，尤其是文件读写、代码执行、浏览器 bridge。
```

---

## 15. 项目结构模板

```text
my-flet-app/
  README.md
  pyproject.toml
  src/
    main.py
    app/
      __init__.py
      routes.py
      config.py
      state.py
      services/
        __init__.py
        api.py
        storage.py
      views/
        __init__.py
        home.py
        settings.py
        editor.py
      components/
        __init__.py
        layout.py
        forms.py
    assets/
      icon.png
  storage/
    data/
    temp/
```

`src/main.py`：

```python
import flet as ft

from app.routes import setup_routes


def main(page: ft.Page):
    page.title = "My Flet App"
    page.theme_mode = ft.ThemeMode.SYSTEM
    setup_routes(page)


if __name__ == "__main__":
    ft.run(main)
```

`src/app/routes.py`：

```python
import flet as ft

from app.views.home import home_view
from app.views.settings import settings_view


def setup_routes(page: ft.Page):
    async def go_home(e):
        await page.push_route("/")

    async def go_settings(e):
        await page.push_route("/settings")

    def route_change(e=None):
        page.views.clear()
        page.views.append(home_view(on_open_settings=go_settings))

        if page.route == "/settings":
            page.views.append(settings_view(on_open_home=go_home))

        page.update()

    async def view_pop(e: ft.ViewPopEvent):
        if e.view is not None:
            page.views.remove(e.view)
            await page.push_route(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    route_change()
```

`src/app/views/home.py`：

```python
import flet as ft


def home_view(on_open_settings) -> ft.View:
    return ft.View(
        route="/",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    controls=[
                        ft.AppBar(title=ft.Text("Home")),
                        ft.Text("Welcome"),
                        ft.Button("Settings", on_click=on_open_settings),
                    ]
                )
            )
        ],
    )
```

`src/app/views/settings.py`：

```python
import flet as ft


def settings_view(on_open_home) -> ft.View:
    return ft.View(
        route="/settings",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    controls=[
                        ft.AppBar(title=ft.Text("Settings")),
                        ft.Text("Settings page"),
                        ft.Button("Home", on_click=on_open_home),
                    ]
                )
            )
        ],
    )
```

---

## 16. 打包发布要点

`flet build` 可以打包为：

```bash
flet build web
flet build windows
flet build macos
flet build linux
flet build apk
flet build aab
flet build ipa
flet build ios-simulator
```

注意：

```text
Flutter SDK 是构建任何平台目标所需依赖；Flet 可在首次构建时自动下载对应 Flutter 版本。
如果 pyproject.toml 和 requirements.txt 同时存在，flet build 会忽略 requirements.txt。
不要用 pip freeze > requirements.txt 作为打包依赖清单。
只写直接依赖，特别是 Flet 扩展包。
```

查看 Flet 对应 Flutter 版本：

```bash
flet --version
uv run python -c "import flet.version; print(flet.version.flutter_version)"
```

---

## 17. Codex 生成代码检查清单

```text
[入口]
- import flet as ft
- def main(page: ft.Page)
- ft.run(main)
- 不主动生成 ft.app(target=main)

[更新]
- 普通事件不机械 page.update()
- loading / 后台任务 / 批量更新才手动 update
- 旧代码显式 update 可以保留但不要重复

[路由]
- route 以 / 开头
- 新项目使用 await page.push_route(...)
- page.views 从 page.route 派生
- page.on_route_change 集中处理
- page.on_view_pop 处理返回
- 不把 page.go() 写成“已删除/绝对废弃”

[CodeEditor]
- uv add flet-code-editor
- import flet_code_editor as fce
- fce.CodeEditor(...)
- 方法 focus/fold_at/fold_imports 要 await
- 不生成 ft.CodeEditor
- 不 exec 用户代码

[存储]
- 新代码用 ft.SharedPreferences()
- 敏感数据用 flet-secure-storage
- key 加应用前缀

[扩展包]
- 使用官方扩展时写入 pyproject.toml dependencies
- 导入和平台支持以官方页面为准
- WebView 不支持 Windows/Linux
- Map 遵守瓦片服务政策

[第三方]
- 官方扩展优先
- 社区包必须检查维护、license、平台支持、版本兼容、安全风险
```

---

## 18. 官网参考链接

- Flet Introduction: https://flet.dev/docs/
- Installation: https://flet.dev/docs/getting-started/installation/
- Creating a new Flet app: https://flet.dev/docs/getting-started/create-flet-app/
- Running a Flet app: https://flet.dev/docs/getting-started/running-app/
- Navigation and Routing: https://flet.dev/docs/cookbook/navigation-and-routing/
- Page: https://flet.dev/docs/controls/page/
- Controls catalog: https://flet.dev/docs/controls/
- CodeEditor: https://flet.dev/docs/controls/codeeditor/
- Charts: https://flet.dev/docs/controls/charts/
- Map: https://flet.dev/docs/controls/map/
- DataTable2: https://flet.dev/docs/controls/datatable2/
- WebView: https://flet.dev/docs/controls/webview/
- Services: https://flet.dev/docs/services/
- SharedPreferences: https://flet.dev/docs/services/sharedpreferences/
- SecureStorage: https://flet.dev/docs/services/securestorage/
- Publishing: https://flet.dev/docs/publish/
