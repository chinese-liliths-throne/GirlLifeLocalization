# 项目结构

当前仓库已经按“宿主层 / 共享核心层 / 数据产物层”拆开。

## 顶层职责

```text
main.py        -> CLI 启动壳
flet_main.py   -> Flet 工作台启动壳
apps/          -> 宿主层
src/           -> 共享核心库
data/          -> 源码、翻译与中间产物
build/         -> 最终打包产物与错误归档
docs/          -> 规划与说明
```

## `apps/`

### `apps/cli/`

只负责：

- 参数解析
- 命令分发
- 调用共享核心流程
- 输出 CLI 结果

不负责：

- 本地化实现
- 构建实现
- parser / runtime 细节

### `apps/flet/`

负责：

- Flet 工作台启动
- 页面、状态、宿主适配
- 把 UI 事件转发给共享核心能力

不负责：

- 重新实现本地化、构建、运行时逻辑
- 重写 parser / validator

## `src/`

### `src/config/`

基础设施：

- `configuration.py`
- `paths.py`
- `logging.py`
- `progress.py`
- `constants.py`
- `exceptions.py`
- `error_reporting.py`

### `src/build/`

构建与流水线：

- `service.py`
- `pipeline.py`

### `src/localization/`

本地化相关：

- `manager.py`
- `paratranz.py`
- `precheck.py`
- `sync.py`
- `legacy_replacer.py`

### `src/project/`

项目源获取：

- `girl_life.py`

### `src/runtime/`

运行前检查：

- `qsrc_checker.py`
- `guard.py`

### `src/storage/`

文件读写与 JSON 装载：

- `files.py`

### `src/models/`

共享模型，目前主要是 ParaTranz 数据模型。

### `src/qsrc/`

QSRC 静态分析主链：

- preprocess
- parser
- AST / transform
- lint passes

### `src/qsp_runtime/`

QSP runtime bridge 与运行会话支持。

### `src/parser/`

仅保留 `.g4` 语法参考文件，不再参与运行时链路。

### `src/thirdparty/`

第三方整合代码，目前主要是 `txt2gam`。

## 数据与产物目录

### `data/1-SourceFile/`

原始 Girl Life 源码目录。

### `data/2-TranslatedParatranzFile/`

ParaTranz 导出与同步结果，包含：

- 正常 `.json`
- `obsolete/`
- `_sync_report.json`

### `data/3-SourceTranslatedFile/`

只保留替换后的 `.qsrc` 文件。

### `data/4-BuildSource/`

最终打包前的完整源码树：

- 先复制原始源码
- 再用第 3 步结果覆盖同名 `.qsrc`

### `build/`

最终输出：

- `build/glife.qsp`
- `build/mods/...`
- `build/errors/...`
