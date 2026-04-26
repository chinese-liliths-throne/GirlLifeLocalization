# GirlLifeLocalization

GirlLifeLocalization 是一个面向 Girl Life / QSP 项目的中文本地化流水线工具。  
它负责源码获取、ParaTranz 词条同步、本地化注入、语法与运行前检查，以及最终 `.qsp` / mod 打包。

## 当前结构

```text
.
├─ main.py                 # CLI 启动壳
├─ flet_main.py            # Flet 工作台启动壳
├─ apps/
│  ├─ cli/                 # 命令行入口层，只做参数解析与流程编排
│  └─ flet/                # Flet UI 层与应用服务
├─ src/
│  ├─ core/                # 共享核心库：配置、路径、日志、构建、运行时、编辑器服务
│  ├─ qsrc/                # QSRC parser / linter / passes
│  ├─ qsp_runtime/         # QSP runtime bridge
│  ├─ model/               # ParaTranz 与项目数据模型
│  └─ thirdparty/          # txt2gam 等第三方整合代码
├─ data/
│  ├─ 1-SourceFile/
│  ├─ 2-TranslatedParatranzFile/
│  ├─ 3-SourceTranslatedFile/
│  └─ 4-BuildSource/
├─ build/                  # 打包产物与 build/errors
└─ docs/
```

## 环境

项目以 `uv` 为主：

```bash
uv sync
```

常用检查：

```bash
uv run ruff check .
uv run black --check .
```

如果当前机器上 `uv` 还没进 PATH，也可以临时使用项目虚拟环境直接运行 Python 入口。

## CLI 用法

查看帮助：

```bash
python main.py --help
```

或：

```bash
uv run girllife-localization --help
```

完整流水线：

```bash
python main.py
```

只做本地替换：

```bash
python main.py --replace-localizations
```

只做 qsrc 检查：

```bash
python main.py --test-qsrc
```

只重新打包：

```bash
python main.py --skip-source --skip-paratranz --skip-translate --build-game
```

## Flet 工作台

桌面模式：

```bash
python flet_main.py
```

或：

```bash
uv run girllife-localization-flet
```

Web 模式：

```bash
python flet_main.py --host web --port 8550
```

Flet 独立打包：

```bash
python flet_main.py --build-target windows
python flet_main.py --build-target web
```

## 数据目录约定

- `data/1-SourceFile/`：原始 Girl Life 源码
- `data/2-TranslatedParatranzFile/`：ParaTranz 导出与同步结果
- `data/3-SourceTranslatedFile/`：仅保留替换后的 `.qsrc`
- `data/4-BuildSource/`：第 4 步打包前完整源码树
- `build/`：最终 `glife.qsp`、mods 和 `build/errors`

## 说明

- `build/errors/` 统一保存翻译、JSON、语法、合并等错误归档
- 打包前会清空 `build/`
- 第三步替换会尽量保留可用汉化，局部有问题的词条会跳过并保留原文
- QSRC 静态检查和运行前检查由 `src/qsrc` 与 `src/qsrc_runtime_checker.py` 共同完成
