# 发布 1.24.0：编译 exe + GitHub Release

## Goal

把工作区已完成的 1.24.0 批次（协议15 Modbus、协议2 HDLC 字段级重写、645 无线模组组帧、串口工具蓝牙通道等）编译成单文件 exe，提交产品代码与版本四件套，打 tag `1.24.0` 并在 GitHub 建 Release（与 1.23.96 同格式）。

## Requirements

- 版本源：`main_gui.py` 的 `APP_VERSION=1.24.0` / `BUILD_DATE=2026-10-24`（已在工作区，不另行 bump）
- 门禁：`PYTHONIOENCODING=utf-8 python release_check.py` → FAIL=0 / WARN=0；本轮已修两处门禁红（`test_web_landing.py` 协议表缺 Modbus 行、`test_self_test.py` 写死「12 个解析器」）
- 提交范围：**产品代码 + 版本四件套**（`main_gui.py`、`README.md`、`AGENTS.md`、`南网解析工具.iss`、`2222.iss`）与 1.24.0 批次其余产品文件；**排除** `.trellis/` `.claude/` `.agents/` 模板升级（与发布无关，留在工作区）
- 产物：`南网协议解析工具.spec`（onefile）；Release 资产改名为 `v1.24.0_<YYYYMMDDHHMMSS>.exe` + `SHA256SUMS-1.24.0.txt`
- Release：tag `1.24.0`（与 `APP_VERSION` 同名，沿用 1.23.96/1.23.94 惯例），标题 `1.24.0`，正文以 1.23.96 的正文为模板改写

## Acceptance Criteria

- [x] `python release_check.py` → FAIL=0 WARN=0（含 test_web_landing / test_self_test 全绿）
- [x] `dist/南网协议解析工具_v1.24.0_<时间戳>.exe` 生成，`VersionInfo.FileVersion == 1.24.0.0`
- [x] `exe --self-test` 退出码 0，打印「解析器：13 个已加载 / 75 字节样例一致 / OK」
- [x] `exe --parse "<南网样例帧>" --protocol 0` 退出码 0（冻结态可起来且解析链路可用）
- [x] `git tag 1.24.0` 指向含 1.24.0 源码的提交（tag 内容与 exe 版本一致）
- [x] `gh release view 1.24.0` 存在，资产为 `v1.24.0_*.exe` 与 `SHA256SUMS-1.24.0.txt`，且 exe 的 sha256 与 SUM 文件一致
- [x] 工作区仅剩 `.trellis/.claude/.agents` 模板升级未提交（不误带他人 WIP）

## Notes

- 发布属外部副作用操作，用户已在本轮显式授权（"编译exe，发布到github，建立release"）并确认：提交范围=产品代码+版本四件套、资产=单文件 exe + SHA256SUMS。

## 结果

- 门禁：`release_check.py` → **PASS=145 FAIL=0 WARN=0**（先修两处红：Web 落地页协议表缺 Modbus 行、`test_self_test` 写死「12 个解析器」）
- 提交：`6dc01b2`（42 文件，8586+/449-），已推 `main`；tag `1.24.0` 指向该提交
- 产物：`dist/南网协议解析工具_v1.24.0_20261024160025.exe`（100.2 MB，FileVersion `1.24.0.0`）
- 冻结态冒烟：`--self-test` → 「解析器：13 个已加载 / 75 字节样例一致 / OK」，退出码 0（证明 modbus 等新模块真的进包）
- Release：<https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool/releases/tag/1.24.0>
  资产 `v1.24.0_20261024160025.exe`（sha256 `ca7d9708…f15fce`，与本地及远程 digest 三方一致）+ `SHA256SUMS-1.24.0.txt`
- 未入库（按用户确认的范围）：`.trellis/.claude/.agents` 模板升级、`协议文档/2.DLMS协议/`（44 MB 参考 PDF）、运行时 `archive_data.json` / `logs/`
