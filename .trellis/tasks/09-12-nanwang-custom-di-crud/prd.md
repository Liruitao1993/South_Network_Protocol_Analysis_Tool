# 南网查询页「自定义 DI」增删（死按钮收口）

## Goal

协议0（南网）查询页的两个按钮「添加自定义 DI」「删除选中自定义 DI」点了只弹「功能待实现」，而同仓已有三处同类实现可参照。本任务把这两个按钮做成真功能：增删自定义 DI → 落盘 `custom_di.json` → 查询表即时刷新 → 重启保持。

## Confirmed Facts（代码证据）

- 死按钮：`lookup_pages.py:98`、`lookup_pages.py:103`（`QMessageBox.information(parent, "提示", "添加/删除自定义DI功能待实现")`）。
- 已有同类实现（可参照/复用范式）：
  - `main_gui.py:2241` `ConfigDialog`/自定义 DI 对话框（南网，标题「添加自定义DI」）
  - `main_gui.py:4357`「添加自定义DI (DLT645)」
  - `main_gui.py:4051`「添加自定义AFN+Fn」（国网）
- 数据文件：`custom_di.json`（AGENTS.md §3/§4.5：南网自定义 DI，GUI 运行时增删；打包内置，exe 目录缺失时从 `_MEIPASS` 复制种子），定位经 `app_paths.data_path`。
- 查询页数据源：南网查询页由 `main_gui` 的 `_create_*_lookup_content` 构建（AGENTS.md §6），查询内容 builder 由 `protocol_registry.lookup_builder_method` 分派。
- 645/国网的「自定义 DI」对话框已是完成态，说明字段（DI 码/名称/单位/数据类型/长度）与校验规则有既定口径。

## Requirements

### R1 添加自定义 DI
- 对话框字段与既有南网自定义 DI 对话框一致（DI 码 8 位 hex / 名称 / 单位 / 数据类型 / 长度）。
- 校验：DI 必须 8 位十六进制；重复 DI 给出覆盖确认；名称非空。
- 确认后：写 `custom_di.json`（`app_paths.data_path`，保留既有条目），刷新查询表，并在查询页显示新增行（标注「自定义」）。

### R2 删除选中自定义 DI
- 仅允许删除自定义条目（内置 DI 不可删，给出提示）；支持多选批量删除。
- 删除前二次确认；确认后写盘 + 刷新。

### R3 与既有实现共用口径
- 复用既有自定义 DI 的读写/校验工具函数（若散落在 `main_gui`，抽为 `lookup_pages` 可调用的小函数，不复制第二份 JSON 读写逻辑）。
- 打包：`custom_di.json` 已在 spec `datas` 内（`南网协议解析工具.spec:76`），无需改动。

### R4 测试
- 新增 `test/test_nanwang_custom_di.py`：JSON 读写纯逻辑（新增/覆盖/删除/非法 DI 拒绝/内置不可删）+ offscreen GUI（按钮存在且点击不再弹「待实现」、新增后表格行数 +1 且落盘、删除后行数 -1 且落盘、重启（新建 widget/重载）保持）。
- 测试必须沙箱化 `app_paths.data_path` 到临时目录，**不得写用户真身 `custom_di.json`**。
- 保持 `python release_check.py` 全绿（基线 PASS=48 FAIL=0 WARN=0）。

## Acceptance Criteria

1. 两个按钮点击后走真实增删流程，不再出现「功能待实现」文案。
2. 新增/删除后 `custom_di.json` 内容正确（新增条目在、删除条目不在、其余条目不变），查询表即时反映。
3. 内置 DI 删除被拒绝并给出可读提示；非法 DI 码被拒绝。
4. 重启（重新构造 UI）后自定义 DI 仍在。
5. 新测试脚本全过；`release_check.py` 无 FAIL/WARN。

## Out of Scope

- 不动国网/645 的自定义 DI/AFN 对话框（已是完成态）。
- 不做自定义 DI 的导入导出、批量粘贴、编辑已有自定义条目（本次只做增/删；若后续要编辑另开）。
- 不改查询页其它按钮与协议无关逻辑。

## Risks / Deferred

- 南网查询页的自定义 DI 是否参与「单帧解析」的 DI 名称显示需确认：若 `protocol_parser` 另有 DI 名称来源（`custom_di.json` 是否被解析器读取），本任务只保证查询页与落盘，解析侧联动作为可选增强（先查再定）。
- 若 `custom_di.json` 结构在解析侧有额外字段（如描述），读写需保持未知字段不丢（整体读改写，不要按固定 schema 重建）。
