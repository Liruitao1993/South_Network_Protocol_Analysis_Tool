# 国网新一代 PB-only 手动指定标准版本

## 背景
- 国网新一代(协议索引10)解析器 `gw_new_gen_parser.py:156` 已支持 `std_version` kwarg(0=HDC 1.0 旧版双模 / 1=HDC 2.0 新一代)：
  - 无FC模式(`app`/`mac_only`/`pb_only`)默认 `std_version=1`，**可由 kwargs 指定**；
  - FC模式(`auto`/`fc_pb`/`fc_only`/`fc_mac`)由 FC 字节12 D[7:4] 自动覆盖(`gw_new_gen_parser.py:213`)。
- GUI 已有「解析级别」下拉(`gw_parse_level_combo`, L510)和「帧类型」下拉(`gw_pb_frame_type_combo`, L530, 仅 pb_only 可见)，但**缺少标准版本选择**，导致无FC模式下静默按 HDC 2.0 解析。

## 目标
- 完整帧(含FC)：继续由 FC 字节12 自动判别(不变)。
- 无FC模式(`pb_only`/`mac_only`/`app`)：新增「标准版本」下拉，人工选择 HDC 2.0(新一代) / HDC 1.0(旧版双模)。

## 改动范围(仅 `main_gui.py` + 测试；解析器本身不改)

### 1. 新增 UI 控件 — 在 L538 PB帧类型下拉之后、`proto_layout.addStretch()`(L540)之前
- `self.gw_std_version_label`(QLabel "标准版本：") + `self.gw_std_version_combo`(QComboBox)：
  - items: `"HDC 2.0(新一代)" → 1`, `"HDC 1.0(旧版双模)" → 0`；默认选中 1(向后兼容)
  - `setMinimumWidth(150)`；tooltip：仅PB/仅MAC/应用层模式无FC可读标准版本号时需手动指定；完整帧由FC字节12自动判别，本选择不生效
  - 默认 `setVisible(False)`

### 2. `_on_gw_parse_level_changed` (L1717-1726)
- 新增：`show_std_version = self._gw_parse_level in ("pb_only","mac_only","app")`；据此显隐 `gw_std_version_label`/`gw_std_version_combo`。
- 既有帧类型显隐逻辑不变。

### 3. 协议切换显隐 (L1677-1680)
- 在 `show_gw_level = (index == 10)` 之后增加：
  `show_std_ver = show_gw_level and self._gw_parse_level in ("pb_only","mac_only","app")`
  并对标准版本 label/combo `setVisible(show_std_ver)`。
- 保证离开协议10 或 auto 等FC模式时下拉隐藏。

### 4. 调度包装器传参 — `GWGenGuiParser` (L2691-2701)
- 读取 `std_version = self.gw_std_version_combo.currentData()`(默认1)；
- `GWGenGuiParser.__init__` 增加 `std_ver=1` 字段；`parse_to_table` 的 kwargs 增加 `'std_version': self.std_version`。
- FC模式下解析器会从FC字节12覆盖此值，故始终传入安全，仅在无FC模式生效。

### 5. 测试 — `test_gw_parse_levels.py`
- 新增用例：`pb_only`(SOF) 与 `mac_only` 模式下 `std_version=0` vs `1` 的输出差异断言(1.0 下 聚合MAC帧标识/发送帧序号/链路标识符 显示为"保留"，2.0 下为实际字段)。实现时先验证分支确实改变输出再写断言。
- 回归：FC自动判别用例(`test_gw_new_gen.py` 的 `_fc_with_version`)保持通过。

## 不在范围
- 双击深度解析路径 `main_gui.py:4459-4464` 直接调用解析器，通常处理完整帧，沿用自动判别；如需支持PB深解析另议。
- `reflex_web` 网页版同样有协议10入口，如需同步另议。
- 解析器 `gw_new_gen_parser.py` 无需改动(`std_version` 已支持)。

## 兼容性
- 默认 HDC 2.0 与现状一致，不改变现有解析行为；仅新增控件与传参，无破坏性变更。
