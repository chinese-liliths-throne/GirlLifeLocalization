# GirlLifeLocalization V2

## 核心方向

- 主链：`Lark parser + AST + linter`
- 增强链：`QSP C runtime bridge`
- 外壳兼容：保留 `CLI / data/1~4 / build / ParaTranz JSON`

## 来自 girl-life.wiki 的实现约束

这些约束已经作为 V2 parser/linter 的设计输入：

- `# location_name` 开始，`-` 或 `--- ...` 结束 location
- 文本和 `act` 标签默认在引号内，单引号内的 `'` 需要双写
- `gt/goto`、`gs/gosub`、`xgt/xgoto`、`jump`、`visit` 是运行骨架核心
- `if` / `act` 后的 `:` 是块或单行语义分界
- 多行逻辑行支持末尾 `_` 续行
- `if/elseif/else` 多行块需要 `end`
- `gt` 会清窗口，`xgt` 只清动作区，`gs` 不清窗口
- `$curloc`、`$loc`、`$menu_loc`、`ARGS[0]` 这些返回位置约定不能被翻坏
- 变量和 location 名大小写不敏感，但 Girl Life 约定文件名和 location 名保持匹配
- 注释和内联代码风格要尽量遵循 wiki 的开发约束，避免把语法参考和项目约定混在一起

## 第一阶段已落地目标

- 用 `src/qsrc/` 替代 ANTLR 作为 `runtime-syntax` 主链
- 第三步替换改为 parser 驱动的局部校验
- `runtime-check` 与 `runtime-syntax` 改成统一 issue 模型
- 为 QSP C runtime 预留 `build / ffi / runner` 脚手架

## 第二阶段

- 把 `paratranz_sync.py` 和 `paratranz_precheck.py` 改成 AST 驱动提取
- 完成 QSP runtime 世界装载和 `ExecLocation` 真绑定
- 把 workflow 从 ANTLR 生成切到 Lark + runtime tests
