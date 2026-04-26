# txt2gam 插件说明

`txt2gam.py` 是 GirlLifeLocalization 内置的 QSP 工具插件，来自 QSPFoundation/txt2gam 思路的 Python 版本实现。它既可以作为库被项目调用，也可以作为命令行工具直接运行。

它主要解决三件事：

- 检查 `.qsrc` / `.txt` 里的常见 QSP 语法问题。
- 按 `.qproj` 声明顺序合并多个 `.qsrc` 为单个 `.txt`。
- 将 `.txt` 打包为 `.qsp` / `.gam`，或把 `.qsp` 解包回 `.txt`。

## 在项目中调用

### 默认测试打包

在 GirlLifeLocalization 项目里可以直接调用默认打包流程：

```python
from src.thirdparty.txt2gam import run_project_test_build

ok = run_project_test_build()
```

默认路径来自 `src.config.settings.filepath`，处理下面这一组文件：

```text
data/test/locations
data/test/glife.qproj
data/test/glife.txt
data/test/glife.qsp
```

### 检查单个文件

```python
from src.thirdparty.txt2gam import analyze_qsp_file

result = analyze_qsp_file("data/test/glife.txt")

if result.ok:
    print("语法检查通过")
else:
    print(f"发现 {result.error_count} 个问题")
```

### 检查目录下所有 qsrc

```python
from src.thirdparty.txt2gam import analyze_qsp_directory

result = analyze_qsp_directory("data/test/locations", pattern="*.qsrc")

if not result.ok:
    raise RuntimeError(f"QSP 源码检查失败，共 {result.error_count} 个问题")
```

### txt 打包为 qsp

```python
from src.thirdparty.txt2gam import build_txt_to_gam

ok = build_txt_to_gam(
    input_txt="data/test/glife.txt",
    output_game="data/test/glife.qsp",
)
```

`build_txt_to_gam()` 会先做语法检查，检查通过后才会生成游戏文件。

### qproj + qsrc 一键打包

```python
from src.thirdparty.txt2gam import build_qproj_to_gam

ok = build_qproj_to_gam(
    input_dir="data/test/locations",
    qproj_file="data/test/glife.qproj",
    output_txt="data/test/glife.txt",
    output_game="data/test/glife.qsp",
)
```

流程顺序：

1. 读取 `.qproj`。
2. 按声明顺序检查每个 `.qsrc`。
3. 合并为 `.txt`。
4. 将 `.txt` 转换为 `.qsp` / `.gam`。

## 命令行调用

在项目根目录直接运行且不带参数时，会执行默认测试打包：

```bash
python src/thirdparty/txt2gam.py
```

### 只检查单个文件

```bash
python src/thirdparty/txt2gam.py --check data/test/glife.txt
```

### 批量检查 qsrc 目录

```bash
python src/thirdparty/txt2gam.py --check-dir data/test/locations --pattern *.qsrc
```

### 合并 qsrc 为 txt

```bash
python src/thirdparty/txt2gam.py -m --qproj data/test/glife.qproj --idir data/test/locations data/test/glife.txt
```

### txt 打包为 qsp

```bash
python src/thirdparty/txt2gam.py data/test/glife.txt data/test/glife.qsp
```

### qsp 解包为 txt

```bash
python src/thirdparty/txt2gam.py -d data/test/glife.qsp data/test/glife_out.txt
```

## 返回值

`analyze_qsp_file()` 和 `analyze_qsp_directory()` 返回 `QSPCheckResult`：

```python
QSPCheckResult(
    ok=True,
    error_count=0,
    file_count=12,
    files=["..."],
)
```

字段含义：

- `ok`: 是否通过检查。
- `error_count`: 发现的问题数量。
- `file_count`: 检查过的文件数量。
- `files`: 检查过的文件路径。

## 当前检查范围

这个检查器不是完整 QSP 解释器，它的目标是在打包前提前暴露最常见、最影响定位的问题：

- 字符串引号未闭合。
- 多行注释 `{! ... !}` 未闭合。
- `ACT`、`IF`、`ELSEIF`、`FOR` 缺少冒号。
- `IF` / `ACT` / `FOR` 与 `END` 不匹配。
- `FOR` 缺少 `TO`。
- `JUMP` 找不到目标标签。
- 命令参数数量不符合 QSP 语句注册表。
- 代码区出现中文全角冒号或中文引号。

如果你只需要完整流水线，不必手动调用这个插件；`python main.py` 会在翻译注入后自动执行第 4 步，将 `data/3-SourceTranslatedFile` 中的 qsrc 增量文件覆盖到 `data/1-SourceFile` 的完整源码副本上，再把最终文件输出到 `build/glife.qsp`，并自动扫描 `mods` 目录，把 mod 输出到 `build/mods/<Mod名>/<qproj名>.qsp`。如果开启严格检查，语法错误也不会阻止打包，相关信息会写入 `build/errors/build-syntax/`。手动调用插件主要用于单独检查、调试或重新打包。

只限制 mod 部分打包范围时，可使用项目主入口：

```bash
python main.py --skip-source --skip-paratranz --skip-translate --build-game --mod Ibiza
```
