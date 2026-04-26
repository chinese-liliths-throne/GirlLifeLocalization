# GirlLifeLocalization

GirlLifeLocalization 是面向 Girl Life / QSP 项目的中文本地化流水线工具。它负责下载 Girl Life 源码、拉取 ParaTranz 翻译导出、按 `<<POS:...>>` 坐标把译文注入 `.qsrc`，并可选调用内置 `txt2gam` 插件打包为 `.qsp`。

## 当前结构

```text
.
├── main.py                         # 极薄启动器，调用 src.cli
├── src/
│   ├── cli.py                      # 中文命令行参数
│   ├── pipeline.py                 # 主流水线编排
│   ├── build_service.py            # 第 4 步源码合成、本体与 mod 打包服务
│   ├── paths.py                    # 统一路径规划与安全检查
│   ├── config.py                   # .env / pydantic-settings 配置
│   ├── consts.py                   # Girl Life 上游仓库常量
│   ├── project_girl_life.py        # GitLab 源码下载与安全解压
│   ├── paratranz.py                # ParaTranz API 客户端
│   ├── localization_manager.py     # qsrc 翻译注入核心逻辑
│   ├── paratranz_sync.py           # ParaTranz 词条提取、版本差异比对与译文迁移
│   ├── file_manager.py             # 文件扫描与 ParaTranz JSON 读取
│   ├── model/                      # 数据模型
│   └── thirdparty/                 # txt2gam 插件
├── docs/
│   └── PROJECT_STRUCTURE.md        # 结构规划说明
└── data/
    ├── 1-SourceFile/               # Girl Life 原始源码
    ├── 2-TranslatedParatranzFile/  # ParaTranz 导出翻译
    ├── 3-SourceTranslatedFile/     # 只保存替换后的 qsrc 文件
    └── 4-BuildSource/              # 最终打包前源码：1 被 3 覆盖后的结果
└── build/
    ├── glife.txt                   # txt2gam 合并后的中间文本
    ├── glife.qsp                   # 最终可运行的 QSP 游戏文件
    ├── mods/                       # 自动打包出的 mod qsp
    └── errors/                     # 按源文件归档的翻译 / JSON / 打包错误日志
```

## 环境配置

推荐使用 uv：

```bash
uv sync
```

或使用项目已有虚拟环境：

```bash
.\.venv\Scripts\python.exe main.py --help
```

在项目根目录创建 `.env`：

```env
PROJECT_VERSION=0.9.8.1
PROJECT_SOURCE_TYPE=common
PROJECT_LANGUAGE=zh_cn

PARATRANZ_PROJECT_ID=你的项目ID
PARATRANZ_TOKEN=你的ParaTranzToken
```

`PROJECT_SOURCE_TYPE=common` 下载指定版本标签；设为 `dev` 时下载 Girl Life 的 `master` 分支。

## 常用命令

执行完整流水线：

```bash
python main.py
```

完整流水线默认会在翻译注入后执行最终打包：

```text
data/1-SourceFile              原始源码
data/2-TranslatedParatranzFile ParaTranz 导出
data/3-SourceTranslatedFile    只保存注入译文后的 qsrc 文件
data/4-BuildSource             用 3 覆盖 1 后得到的最终打包源码
build/glife.qsp                最终 QSP 文件
build/mods/<Mod名>/<mod>.qsp   最终 mod QSP 文件
```

```text
build/glife.qsp
build/mods/
```

只使用本地已有源码和 ParaTranz 导出重新注入：

```bash
python main.py --only-translate
```

只重新打包已有的本地化源码：

```bash
python main.py --skip-source --skip-paratranz --skip-translate --build-game
```

每次执行最终打包前，程序都会先清空目标 `build/` 目录，再重新生成 `build/errors/`、`glife.qsp` 和 `build/mods/`，避免旧产物和旧报错残留干扰排查。

默认重新打包时会同时扫描 `data/4-BuildSource/mods` 中的 `.qproj`，输出到 `build/mods/<Mod名>/`。只限制 mod 部分打包范围：

```bash
python main.py --skip-source --skip-paratranz --skip-translate --build-game --mod Ibiza
```

只打包本体、不打包 mod：

```bash
python main.py --skip-source --skip-paratranz --skip-translate --build-game --skip-mods
```

只准备源码/翻译文件，不注入：

```bash
python main.py --skip-translate --skip-build
```

只注入翻译，不执行最终打包：

```bash
python main.py --only-translate --skip-build
```

强制重新下载源码缓存：

```bash
python main.py --force-source
```

调整并发：

```bash
python main.py --concurrency 16
```

默认情况下，`data/3-SourceTranslatedFile` 只保存替换好的 `.qsrc` 文件，不再复制 README、脚本、配置、工具目录等多余内容。第 4 步会自动复制 `data/1-SourceFile` 的完整源码，再用 `data/3-SourceTranslatedFile` 覆盖同名 `.qsrc`，所以最终打包仍然有完整项目结构。

最终打包目录默认为 `build/`。可以改成其它目录：

```bash
python main.py --build-dir dist
```

第 4 步暂存目录默认是 `data/4-BuildSource`。可以改成其它目录：

```bash
python main.py --process-dir data/4-CustomBuildSource
```

默认打包会跳过内置严格语法检查，避免检查器误报导致没有 qsp。如果需要在打包前强制检查：

```bash
python main.py --strict-build-check
```

即使开启 `--strict-build-check`，现在也不会因为语法错误中止打包流程。错误会统一写入 `build/errors/`，并按源文件归档，例如：

```text
build/errors/translation/locations/foo.qsrc.log
build/errors/paratranz-json/utf8/locations/foo.qsrc.json.log
build/errors/build-syntax/locations/foo.qsrc.log
build/errors/build-merge/locations/foo.qsrc.log
```

## ParaTranz 同步与迁移

可以根据当前源码重新提取 ParaTranz JSON，并尽量把旧版本的译文迁移到新版本：

```bash
python main.py --sync-paratranz
```

常见用法：

```bash
python main.py --sync-paratranz --sync-source-dir data/1-SourceFile/girl-life-0.9.9
python main.py --sync-paratranz --sync-paratranz-dir data/2-TranslatedParatranzFile/0.9.8.1
python main.py --sync-paratranz --sync-output-dir data/2-TranslatedParatranzFile/0.9.9
```

同步逻辑是：

- 从当前源码重新提取可本地化词条，生成新的 `.qsrc.json`
- 优先按“同文件 + 原文”迁移旧译文
- 再按规范化原文做保守匹配迁移
- 把新增待翻译、未匹配、已移除词条写入 `_sync_report.json`
- 被移除的旧词条不会直接丢弃，而是统一标记为过时并输出到 `obsolete/` 目录

输出目录中会生成：

```text
data/2-TranslatedParatranzFile/<版本目录>/
  locations/*.qsrc.json
  mods/**/locations/*.qsrc.json
  obsolete/**/*.qsrc.json
  _sync_report.json
```

## txt2gam 插件

插件说明见 [txt2gam_usage.md](src/thirdparty/txt2gam_usage.md)。

常用命令：

```bash
python src/thirdparty/txt2gam.py --check data/test/glife.txt
python src/thirdparty/txt2gam.py --check-dir data/test/locations --pattern *.qsrc
python src/thirdparty/txt2gam.py -m --qproj data/test/glife.qproj --idir data/test/locations data/test/glife.txt
python src/thirdparty/txt2gam.py data/test/glife.txt data/test/glife.qsp
```

## 编码与风格

- 项目源码统一使用 UTF-8。
- 命令行、日志、文档以中文为主。
- Python 代码遵循 Black/Ruff 风格，配置在 `pyproject.toml`。
- 业务代码尽量使用 `pathlib.Path`，不再混用大量 `os.path`。
- 生成目录、下载目录、日志目录统一通过 `src.paths` 管理。
