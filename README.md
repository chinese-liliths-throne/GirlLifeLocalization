# GirlLifeLocalization

GirlLifeLocalization 是一个面向 Girl Life / QSP 项目的中文本地化流水线工具。

它负责：

- 源码获取
- ParaTranz 词条同步 / 预检查
- 本地化替换
- QSRC 语法与运行前检查
- 本体与 mod 打包
- Flet 工作台交互

## 当前结构

```text
.
├─ main.py                  # CLI 启动壳
├─ flet_main.py             # Flet 工作台启动壳
├─ apps/
│  ├─ cli/                  # CLI 宿主层
│  └─ flet/                 # Flet 宿主层
├─ src/
│  ├─ build/                # 构建与流水线
│  ├─ config/               # 配置、路径、日志、进度、错误报告
│  ├─ localization/         # ParaTranz / 替换 / 预检查 / 同步
│  ├─ models/               # 共享数据模型
│  ├─ parser/               # 语法参考，仅保留 .g4
│  ├─ project/              # Girl Life 项目源获取
│  ├─ qsp_runtime/          # QSP runtime bridge
│  ├─ qsrc/                 # QSRC parser / linter / passes
│  ├─ runtime/              # 运行前检查与 guard
│  ├─ storage/              # 文件读写与数据装载
│  └─ thirdparty/           # txt2gam 等第三方整合
├─ data/
├─ build/
└─ docs/
```

## 环境

优先使用 `uv`：

```bash
uv sync
uv run ruff check .
uv run black --check .
```

如果当前环境里还没接好 `uv`，也可以直接用项目虚拟环境执行入口脚本。

## CLI

查看帮助：

```bash
python main.py --help
```

或：

```bash
uv run girllife-localization --help
```

常用命令：

```bash
python main.py
python main.py --replace-localizations
python main.py --test-qsrc
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
- `data/4-BuildSource/`：最终打包前完整源码树
- `build/`：最终 `glife.qsp`、mods 和 `build/errors`

## 说明

- 打包前会清空 `build/`
- `build/errors/` 统一保存翻译、JSON、语法、合并等错误归档
- 第三步替换会尽量保留可用汉化，局部有问题的词条会跳过并保留原文
- QSRC 静态检查主链由 `src/qsrc` 提供，运行前检查由 `src/runtime` 提供
