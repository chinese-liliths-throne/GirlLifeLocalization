# 项目结构

当前目录结构已经按“入口层 / 共享核心层 / 数据层”拆开。

## 顶层职责

```text
main.py        -> CLI 启动壳
flet_main.py   -> Flet 工作台启动壳
apps/          -> 各宿主入口层
src/           -> 共享核心库
data/          -> 源码、翻译、中间产物
build/         -> 最终打包产物与错误归档
docs/          -> 规划与参考文档
```

## `apps/`

### `apps/cli/`

只负责：

- 解析参数
- 选择命令
- 调用核心流程
- 输出 CLI 结果

不负责：

- 具体本地化实现
- 构建实现
- parser / runtime 细节

### `apps/flet/`

负责：

- Flet 工作台启动
- 页面、状态、宿主适配
- 把 UI 事件转发给核心服务

不负责：

- 自己实现本地化、构建、运行时逻辑
- 直接重写 parser / validator

## `src/`

### `src/core/`

共享核心层，当前主要包含：

- `configuration.py`：配置读取
- `paths.py`：路径规划与安全校验
- `logging.py`：统一日志
- `error_reporting.py`：错误归档
- `progress.py`：进度条与文件级进度工具
- `constants.py`：上游仓库与平台常量
- `build.py / project.py / editor.py / runtime.py / localization.py`：核心服务包装层

### 仍在 `src/` 顶层、待继续收拢的核心模块

- `build_service.py`
- `pipeline.py`
- `project_girl_life.py`
- `paratranz.py`
- `paratranz_precheck.py`
- `paratranz_sync.py`
- `localization_manager.py`
- `qsrc_guard.py`
- `qsrc_runtime_checker.py`
- `file_manager.py`

这些模块已经不再属于 CLI/Flet 入口层，但还没有全部物理下沉到 `src/core/*` 子包；后续重构会继续把它们按职责拆分。

### `src/qsrc/`

QSRC 相关静态分析主链：

- preprocess
- parser
- AST / transform
- lint passes

### `src/qsp_runtime/`

QSP runtime bridge 与运行时检查支持。

### `src/model/`

ParaTranz 与共享数据模型。

### `src/thirdparty/`

第三方整合代码，当前主要是 `txt2gam`。

## 数据与产物目录

### `data/1-SourceFile/`
原始 Girl Life 源码目录。

### `data/2-TranslatedParatranzFile/`
ParaTranz 导出与同步结果目录，包含：

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

最终打包输出，包括：

- `build/glife.qsp`
- `build/mods/...`
- `build/errors/...`

## 当前重构边界

已经完成：

- CLI 与 Flet 入口从 `src/` 中抽离
- 基础设施模块下沉到 `src/core/`
- `main.py / flet_main.py / pyproject` 对齐新入口

下一步重点：

- 继续把 `src` 顶层业务模块下沉到 `src/core/*`
- 清理历史乱码与旧说明
- 更新 workflow 和更多文档到新结构
