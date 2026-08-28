# Implement — 协议0本地通信模块接口协议核心完善

前置：`prd.md`（需求与验收）、`design.md`（契约与设计）；
文档源：`协议文档/0.南网协议/13 计量自动化终端本地通信模块接口协议.md`（行号锚点见 design.md）。

## 执行顺序

- [ ] **S1 文档精读**：读 md 的 L1122-1170（下行查询 15/16/A0/A1）、L1481-1560（上行返回）、
      L1678-1730（A0-A3 设置）、L1836-1890（上报 A0/11/12）、L850（返回任务列表），
      抄录每个 DI 的字段表（字段名/格式/字节数），作为解析与组帧的唯一依据
- [ ] **S2 解析器新增 15 DI**：`protocol_parser.py` DI_COMBINATION_MAP（L518+）加名称；
      ~L1098 分派表加函数映射；新增 `_parse_xxx_data` 函数（遵循 design.md 契约2/4/5）
- [ ] **S3 冲突修正 4 处**：按 design.md「冲突修正」节实施（双格式检测/条件解析，
      不破坏 PLUZ 存量行为）
- [ ] **S4 测试先行/同步**：新建 `test/test_nw_lcmi.py`（`import _path_setup`），
      覆盖 AC1/AC2/AC3 全部用例；S2/S3 每步完成后立即运行
- [ ] **S5 组帧 schema 8 条**：`frame_generator_schema.py` DI_FIELD_SCHEMA 新增条目
      （fields 类型参照现有 E8 02 04 02 添加从节点、bcd 时间条目），round-trip 用例入 S4
- [ ] **S6 存量回归**：NW_command.json 14 条预设帧解析不回归（写入 S4 测试）；
      运行 test/ 下相关既有脚本确认无破坏
- [ ] **S7 版本与文档**：`main_gui.py` APP_VERSION 1.14.9 + CHANGELOG 条目；
      AGENTS.md §5.1（新增文档映射：本文档 + docx/md 转换产物路径）、§10、§11；
      验证协议0查询页可见新 DI（DI_COMBINATION_MAP 自动继承，人工或测试确认）

## 验证命令（项目根执行）

```bash
python test/test_nw_lcmi.py          # 本任务核心测试（新增）
python main_gui.py                   # 手工：协议0组帧页新命令可见、查询页新 DI 可见（如需）
```

无 pytest；测试脚本内 assert + print，退出码 0 即通过（注意 GBK 控制台避免 print 特殊符号导致编码异常）。

## 风险与回滚点

- 风险1：冲突点修正误伤存量 PLUZ 帧 → 双格式检测必须先按新文档格式尝试、失败回退，
  S4 双格式用例先行守护；回滚 = revert S3 改动
- 风险2：文档字段表行号因转换格式漂移 → 实现时以 md 内容为准重新定位表格，行号仅导航
- 风险3：组帧 list 字段（黑名单地址列表）类型现有 schema 无完全同款 → 参照
  E8 02 04 02 添加从节点的 list 实现
- 回滚：全部改动集中在 4 个文件 + 1 新测试，单提交，revert 即可

## task.py start 前检查

- [ ] prd.md 验收标准可测、无未决问题
- [ ] design.md / implement.md 完成
- [ ] implement.jsonl / check.jsonl 已填真实条目
