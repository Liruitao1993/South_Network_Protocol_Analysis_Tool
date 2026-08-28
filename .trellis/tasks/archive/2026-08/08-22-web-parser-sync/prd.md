# Web版同步协议解析增强(mac_only+PB帧类型)

## Goal

让 Reflex Web 版完整支持同事在 GUI 解析器侧新增的协议解析能力（当前未提交的 parser 改动），重点补齐 Web UI 缺失的两个入口，并运行时验证动态生效的 EB/EBE0 能力。Web 版与 GUI 公用相同解析器（`reflex_web/reflex_web/reflex_web.py` 直接 import 根目录 parser 模块）。

## Background / Confirmed Facts（仓库证据）

- 协议9（南网新一代载波）`csg_new_gen_parser.py` 新增第 7 种输入模式 `mac_only`（仅MAC帧：PBH(4B)+MAC帧；信标=0 无 PBH 直接解析载荷 表51；SACK/NET 报 ❌ 不适合仅MAC帧解析），定界符类型由 `pb_frame_type {sof:1,beacon:0,sack:2,net:3}` 推导。
- **GAP#1**：Web 协议9 解析级别下拉 `reflex_web/reflex_web/reflex_web.py` L3434-3444 只有 auto/fc_pb/fc_efc/fc_only/pb_only/app，缺 `仅MAC帧 value="mac_only"`。管线通用：on_change=State.set_csg_level → State.csg_parse_level → `parser.parse_to_table(frame_bytes, parse_level=...)` L548(单帧)/L800(批量)。修复 = 加一个 rx.el.option。
- **GAP#2**：全文件检索 `pb_frame_type|PB帧类型` 在 reflex_web.py 零命中 → Web 无 PB帧类型选择器（GUI pb_only 可选 SOF/信标/ACK/NET；新 mac_only 也依赖该参数推导定界符）。缺失时依赖解析器默认推断。
- EB/EBE0 冻结等新增能力（gdw_eb_di_lookup +20、gdw_eb_di_fields +91、dl_t698_45_apdu_parser +748）经动态 import 自动流入 Web，预期零代码改动、仅运行时验证。
- 文档漂移：AGENTS.md §1 称「Reflex Web 版支持索引 0-10」，但工作区 reflex_web.py 已含协议11 HDC 1.0 支持。本任务收尾时修正文档表述。

## Requirements

1. R1 (GAP#1)：Web 协议9 解析级别下拉新增「仅MAC帧」选项（value=`mac_only`），单帧/批量两条路径均可触发 mac_only 解析。
2. R2 (GAP#2)：Web 为协议9 新增 PB帧类型选择器（SOF/信标/ACK/NET，映射 pb_frame_type 1/0/2/3），在 pb_only 与 mac_only 模式下生效并传入 parse 调用；默认不选择时由解析器自行推断（保持现状行为）。
3. R3：启动 Web 版实测——mac_only 帧解析正确渲染；EBE0 冻结类报文在 Web 单帧解析中显示 数据业务/645帧头 等深度字段。
4. R4：回归 `python test/test_web_frame_gen_utils.py` 全部通过（基线 63 项）。
5. R5：更新 AGENTS.md 中 Web 版协议覆盖表述（支持 0-11）。

## Acceptance Criteria

- [ ] AC1：Web 协议9 下拉出现「仅MAC帧」，选择后粘贴 PBH+MAC 帧可正常解析出 MAC头/MSDU 字段（信标型输入走无 PBH 分支）。
- [ ] AC2：pb_only/mac_only 下可选 SOF/信标/ACK/NET，选择结果传入 parse_to_table 并影响定界符判定；SACK/NET 输入按解析器行为显示 ❌ 提示行。
- [ ] AC3：浏览器实测 EBE0 冻结报文解析显示操作者/密码/PA/值 与 645帧头 子结构。
- [ ] AC4：`python test/test_web_frame_gen_utils.py` 通过，无回归。
- [ ] AC5：AGENTS.md Web 覆盖描述已更正。

## Out of Scope

- 不修改任何根目录 parser / validator / GUI 文件（那是同事的进行中工作）。
- 不为协议10/11 增加新的解析级别或通道能力（已存在）。
- 不处理 reflex_web 打包/部署脚本变更。

## Notes

- 任务性质：轻量偏中等——改动集中在 reflex_web.py 两处 UI + State 透传，PRD-only 即可满足；实现细节以 git 工作区证据为准，不单列 design.md/implement.md。