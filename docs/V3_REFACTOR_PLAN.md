# GirlLifeLocalization V3

## 核心主链

- `preprocess -> parser -> CST/AST -> lint passes -> runtime checker`
- 解析主链使用 `Lark`
- 运行增强链保留 `QSP C runtime bridge`

## 直接参考的上游资料

### qsp 源码

- `qsp/codetools.c`
  - 续行 `_`
  - 注释与字符串范围
  - 行初始化与块扫描
- `qsp/statements.c`
  - 语句目录
  - 别名
  - 参数数量契约
- `qsp/errors.c` / `qsp/qsp.h`
  - 错误码模型
  - `location + line + act_index`

### girl-life.wiki

- `QSP-Language-Reference.md`
  - location 必须以 `# name` 开始，以 `-` 结束
  - `if/elseif/else` 多行块需要 `end`
  - `act` 多行块需要 `end`
  - `gt/goto`、`gs/gosub`、`xgt/xgoto`、`jump`、`visit` 是运行骨架核心
  - `ARGS[0]` 是 Girl Life 中常见的 visit 分块约定
  - ` _` 结尾表示逻辑续行
  - 缩进推荐用 `TAB`
- `Coding-Guide.md`
  - `act '...': ...`
  - `if ...: ...`
  - 单行块与多行块混用习惯
  - `gt/gs/xgt` 的项目约定
  - 一般建议一行一个操作，`&` 只在必要时做链式语句
- `Developer-Instruction.md`
  - 优先保持项目既有代码风格
  - 谨慎处理位置变量、返回位置变量和分块入口

## V3 第一阶段范围

- 用 `src/qsrc/` 替换 ANTLR 主链
- 用 pass 架构拆分 lint：
  - `structure`
  - `statement`
  - `reference`
  - `style`
- 第三步替换接 parser/linter
- `runtime-syntax` 和 `runtime-check` 统一 issue 模型
- `.qsrclintrc` 作为项目级默认配置

## 已落地约束

- 占位符和 HTML 结构变化默认仅作 warning，不阻断替换
- 第三步优先检查：
  1. jump/reference
  2. syntax
  3. statement contract
- `build/errors` 只记录最终落盘版本的问题，不记录中间态候选错误
