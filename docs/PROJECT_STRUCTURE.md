# 项目结构规划

本项目的结构目标是：入口薄、路径统一、业务分层、插件隔离、中文可读。

## 分层说明

```text
main.py
└── src.cli
    └── src.pipeline
        ├── src.project_girl_life
        ├── src.paratranz
        ├── src.localization_manager
        ├── src.build_service
        └── src.thirdparty.txt2gam
```

### 入口层

- `main.py`: 只负责调用 `src.cli.main()`。
- `src/cli.py`: 负责中文命令行参数解析，不写业务细节。

### 编排层

- `src/pipeline.py`: 串联下载源码、下载翻译、注入译文、可选打包。
- 编排层只决定“先做什么、后做什么”，不处理具体文件格式。

### 构建服务层

- `src/build_service.py`: 负责第 4 步打包源码合成、本体 qsp 打包、`mods` 目录下 mod qproj 自动发现与打包。
- 默认输出本体到 `build/glife.qsp`，输出 mod 到 `build/mods/<Mod名>/<qproj名>.qsp`。
- 每次打包前会先清空整个 `build/` 目录，再重新生成新的产物和错误归档。

### 基础设施层

- `src/paths.py`: 唯一路径规划入口，包含目录识别、安全删除、安全解压。
- `src/config.py`: 从 `.env` 读取配置。
- `src/log.py`: 日志输出。
- `src/consts.py`: 上游仓库 URL 与平台常量。

### 业务层

- `src/project_girl_life.py`: Girl Life 源码下载与解压。
- `src/paratranz.py`: ParaTranz API 调用。
- `src/localization_manager.py`: ParaTranz JSON 到 `.qsrc` 的译文注入。
- `src/paratranz_sync.py`: 从源码重新提取 ParaTranz 词条，并把旧版本 JSON 中可复用的翻译迁移到新版本。
- `src/file_manager.py`: 文件扫描和 JSON 读取。
- `src/model/`: ParaTranz 数据模型。

### 插件层

- `src/thirdparty/txt2gam.py`: QSP 语法检查、qproj/qsrc 合并、qsp/gam 打包。
- `src/thirdparty/txt2gam_usage.md`: 插件中文说明。

## 输出目录约定

```text
data/1-SourceFile
```

保存下载并解压后的 Girl Life 源码。

```text
data/2-TranslatedParatranzFile
```

保存 ParaTranz 的 UTF-8 导出包内容。
也可以作为版本升级后的迁移输出目录，额外生成 `_sync_report.json` 记录新增、迁移和移除的词条，并把被移除的旧词条统一放到 `obsolete/` 目录。

```text
data/3-SourceTranslatedFile
```

只保存替换好的 `.qsrc` 文件。这里是翻译增量目录，不保存 README、构建脚本、工具文件或其它原始源码附属文件。

```text
data/4-BuildSource
```

第 4 步最终打包源码。打包前会先复制 `data/1-SourceFile` 检测到的源码根目录，再用 `data/3-SourceTranslatedFile` 覆盖同名 `.qsrc` 文件，确保最终打包输入同时包含完整原始项目结构和最新译文。

```text
build
```

保存最终打包产物。默认完整流水线会生成：

- `build/glife.txt`: `txt2gam` 合并 `.qproj` / `.qsrc` 后得到的中间文本。
- `build/glife.qsp`: 最终可运行的 QSP 游戏文件。
- `build/mods/<Mod名>/<qproj名>.txt`: mod 合并后的中间文本。
- `build/mods/<Mod名>/<qproj名>.qsp`: 最终可运行的 mod QSP 文件。
- `build/errors/translation/...`: 翻译回写错误，按 `.qsrc` 文件归档。
- `build/errors/paratranz-json/...`: ParaTranz JSON 读取/解析错误，按 `.json` 文件归档。
- `build/errors/build-syntax/...`: 打包语法检查错误，按 `.qsrc` 或合并后的 `.txt` 文件归档。
- `build/errors/build-merge/...`: qproj 合并、缺文件、读写失败等错误，按对应源文件归档。

## 兼容说明

- `src/model/ParatranzData.py` 保留为兼容导入，新的规范文件是 `src/model/paratranz_data.py`。
- `src/old_replacer.py` 是旧版 Twine 流程遗留模块，现在只保留明确的弃用提示。
