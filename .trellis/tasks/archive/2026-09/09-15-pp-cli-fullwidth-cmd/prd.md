# 批量解析预处理命令链全角空格/引号不可用修复（1.23.13）

## Goal

中文输入法**全角状态**下打出的空格（U+3000）与引号（＂ “ ” ‘ ’）不是 ASCII 字符，
`shlex.split` 既不把它们当分隔符也不当引号 → 整串命令被当成**一个命令名**，
批量解析「预处理」执行按钮报「未知命令: find　＂CSG＂」，用户无法执行
（对照：无参数命令 `hex_extract` 等仍可执行，故现场表现是"有的命令能跑、有的报错"）。

## Background / Evidence

现场截图（协议9 批量解析，输入 `find  "CSG"`，日志含 `CSG: 查找入节点信息.`）：

```
预处理失败
  执行预处理命令失败：
  未知命令: find　＂CSG＂
  可用命令: find, excluding, replace, head, tail, skip, hex_extract, tcp_extract, dedup, merge_payloads
```

用真实调用路径（`pp_cli.parse_and_run`，即 GUI 执行按钮的入口）复现：

| 输入 | `shlex.split` 结果 | 结果 |
|---|---|---|
| `find "CSG"`（半角） | `['find', 'CSG']` | 正常，只留 CSG 行 |
| `find<U+3000>＂CSG＂`（全角） | `['find\u3000＂CSG＂']` | `未知命令: find　＂CSG＂` |
| `find<U+3000>“CSG”`（弯引号） | `['find\u3000“CSG”']` | 同上 |
| `find<U+3000>"CSG"`（全角空格+半角引号） | `['find\u3000CSG']` | 同上 |
| `find<NBSP>"CSG"`（不间断空格） | `['find\xa0CSG']` | 同上 |
| `find "＂CSG＂"`（半角空格+全角引号） | `['find', '＂CSG＂']` | find 参数带全角引号 → 0 命中（另一种隐性失败） |

## Requirements

1. GUI（`main_gui._run_cli_preprocessor`）与 Web（`reflex_web.reflex_web` 的
   `parse_batch` / `run_preprocess`）三处命令串拆分必须共用同一份实现，
   接受全角空格/全角引号/不间断空格/窄空格/零宽空格/BOM 等异体字符。
2. 归一化**不得改写参数里刻意保留的全角字符**：`find "A　B"`（半角分隔符）
   必须保持参数为 `A　B`；`replace "　" "_"` 必须保持全角空格作为替换目标。
3. `pp_cli.parse_and_run` 的未知命令报错要能定位不可见字符：附转义形式与码位，
   并给出半角书写提示（旧文案只有原样字符串，全角/零宽字符肉眼无法分辨）。
4. 非法命令、引号不闭合等真实错误**不能被归一化吞掉**：仍要弹出明确错误。
5. 非 ASCII 输入不得进入「静默 0 命中」路径（要求 2 与 1 的组合结果）。

## Acceptance Criteria

- [ ] `pp_cli.split_commands()` 对上述全部异体变体拆分结果与半角写法完全一致
- [ ] `find "A　B"`（参数含全角空格）拆分后参数原样保留
- [ ] `parse_and_run` 未知命令报错含 `U+67E5` 形式码位与「半角空格」提示
- [ ] offscreen `MainWindow._run_cli_preprocessor`：全角命令**不弹**「预处理失败」且正确回填 CSG 行；
      非法命令仍弹 `critical`；引号不闭合仍弹「命令解析错误」；真实 `config.json` 未被测试改写
- [ ] Web 侧同一份实现：真实 reflex `State.run_preprocess()` 驱动，半角/全角/全角空格+半角引号/NBSP
      四种写法产出逐字相同
- [ ] `python test/test_pp_cli.py` 全过并登记 `release_check.py:CORE_TESTS`
- [ ] `python release_check.py` 全绿（`--sync-iss` 同步 `.iss`，README 徽章同步）

## Design Decision (轻量任务，未单独建 design.md)

`split_commands()` 采用**兜底归一化**而非无条件归一化：
先按原样 `shlex.split`；**仅当首个 token 不是已知命令**时才做全角→半角重试。
理由：无条件归一化会让「半角分隔符 + 参数里含全角空格」的合法写法被改写，
而该写法正是 requirement 2 要保护的面；兜底策略同时满足 requirement 1 与 2。
引号不闭合仍抛 `ValueError`（由调用方提示），保证 requirement 4。

已知取舍：完全用全角书写且参数**本意是字面全角引号**的串会被归一化（无法区分），
按"全角引号即引号"处理符合绝大多数输入法场景，已写入代码注释。

## Notes

- 影响面：`pp_cli.py`（新增 `normalize_command_text` / `split_commands` / `_describe_token`）、
  `main_gui.py`（调用点 + tooltip + 帮助对话框）、`reflex_web/reflex_web/reflex_web.py`（两处调用点 + 面板说明）
- 相关陷阱已写入 `AGENTS.md §8` 第 33 条：三处调用点不得再直接 `shlex.split`
- 版本：1.23.13（含 `test/test_pp_cli.py` 47 项）
