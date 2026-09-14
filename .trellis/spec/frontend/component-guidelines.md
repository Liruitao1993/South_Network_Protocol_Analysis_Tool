# Component Guidelines

> How components are built in this project.

---

## Overview

<!--
Document your project's component conventions here.

Questions to answer:
- What component patterns do you use?
- How are props defined?
- How do you handle composition?
- What accessibility standards apply?
-->

(To be filled by the team)

---

## Component Structure

<!-- Standard structure of a component file -->

(To be filled by the team)

---

## Props Conventions

<!-- How props should be defined and typed -->

(To be filled by the team)

---

## Styling Patterns

<!-- How styles are applied (CSS modules, styled-components, Tailwind, etc.) -->

(To be filled by the team)

---

## Accessibility

<!-- A11y requirements and patterns -->

(To be filled by the team)

---

## Common Mistakes

<!-- Component-related mistakes your team has made -->

(To be filled by the team)

---

## PySide6 新增标签页组件规范（本项目实际约定）

> 源自任务 09-09-csg-batch-sequence-diagram（通信时序图）。新增主窗口标签页时必须遵循以下五步套路，参考实现 `sequence_diagram_widget.py` + `main_gui.py` 接线段。

### Convention: 新标签页 = 独立文件 + 纯逻辑层分离 + 懒加载 + 协议可见性 + 双向联动防循环

1. **独立文件**（AGENTS.md §4.1）：UI 组件拆分到 `<feature>_widget.py`，`main_gui.py` 只导入组合。文件内部分两层：**前半纯逻辑层不 import PySide6**（dataclass 模型 + `build_*_model()` 提取函数，可无 GUI 脚本测试），后半 UI 层 Qt import 用 `try/except ImportError` 包裹保证无 Qt 环境可导入纯逻辑层。
2. **懒加载 tab**：`self._<feat>_placeholder = QWidget()` + `self._<feat>_tab_index = tab_widget.addTab(placeholder, icon, title)`；`_ensure_lazy_tab()` 中追加 `elif index == getattr(self, '_<feat>_tab_index', -1): self._ensure_<feat>_tab()`；`_ensure_<feat>_tab()` 用 `hasattr` 防重复创建、`_replace_lazy_tab()` 替换占位页（自动保留图标）。**tab 索引一律用 addTab 返回值，禁止硬编码数字**（插入新 tab 不影响他页）。
3. **协议可见性**：在 `_on_protocol_changed` 中 `tab_widget.setTabVisible(self._<feat>_tab_index, index == N)` 按需显隐；入口按钮同步 `setEnabled(index == N)`，且创建时按 `self.current_protocol` 设初始态。
4. **双向联动防循环**：跨组件互相触发选中/高亮时，用布尔 guard（如 `_seq_sync_guard`，模式同 `_lazy_tab_guard`）：入口置位、`finally` 复位、对侧回调发现置位直接 return。
5. **行索引映射**：摘要/列表类表格第 0 列 item 的 `Qt.UserRole` 存数据层原始索引（过滤/排序后行号≠索引）；外部组件持原始索引，回查时遍历比对 UserRole。

### Convention: 解析器 table_data 数值提取必须容错

`_table_data` 行的 `parsed_value` 形态不保证是 int（实测为十进制字符串，历史上出现过 `0x` 前缀字符串导致 int() 崩溃）。提取时统一用多级兜底：

```python
def _to_int(value):
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip(), 10)
    except ValueError:
        try:
            return int(str(value).strip(), 0)  # 兼容 0x../0b..
        except ValueError:
            return None
```

### 测试要求

- 纯逻辑层：`test/test_<feat>_model.py` 脚本式断言（复用现有协议样本帧常量，参考 `test_csg_sequence_model.py`）。
- GUI 接线：`test/test_<feat>_gui.py` offscreen（`QT_QPA_PLATFORM=offscreen`），走真实链路断言 tab 注册/协议可见性/按钮启停/双向联动/清空重置（参考 `test_csg_sequence_gui.py` 19 项）。
- 注意：部分旧测试末行 `print("...✓")` 在 GBK 控制台会 UnicodeEncodeError（非失败）；验证时设 `PYTHONIOENCODING=utf-8`。

---

## Scenario: 虚拟表「从站模拟 + 主站下发」双角色（DLT645 / LME 自定义接口）

> 源自任务 09-11-dlt645-sim-lme-query（645虚拟表「模块版本查询」）。参考实现：`dlt645_sim/lme_query.py`（纯逻辑）+ `dlt645_meter_sim_widget.py`（GUI 与串口线程），测试 `test/test_dlt645_sim_lme_query.py`（95 项）。

### 1. Scope / Trigger

虚拟表原本只会「收请求 → 应答」（从站）。一旦需要**主动向模块索取信息**（版本、内部信息条目），就必须在同一串口上同时做两种角色，触发点是跨层契约变化：串口收帧的**方向分流**规则 + 主站请求的**帧数据域契约**。

### 2. Signatures

```python
# dlt645_sim/lme_query.py（纯逻辑，无 Qt）
KIND_SINGLE_STA, KIND_DUAL_STA, KIND_DUAL_SET = "4.2", "4.6", "4.7"
DEFAULT_ADDR = "AAAAAAAAAAAA"          # 手册 §5.1.1 虚拟电表上位机点对点口径
MAX_ENTRY_LEN = 31                     # TLV 长度域仅 5 bit

build_single_sta_query(addr=DEFAULT_ADDR) -> bytes
build_dual_query(addr=DEFAULT_ADDR, entries: str | Sequence = "") -> bytes
build_dual_set(addr=DEFAULT_ADDR, items: str | Sequence = "") -> bytes
build_query(kind: str, addr: str = DEFAULT_ADDR, text: str = "") -> bytes   # UI 统一入口
decode_reply(frame: bytes) -> dict            # DLT645Parser.parse 薄封装
reply_rows(parsed) -> list[tuple[str, str, str, str]]
describe_frame(frame) -> str                  # 控制码/长度/数据域 日志摘要
describe_items(text, kind) -> list[str]       # 4.7 确认框条目明细

# 串口线程信号（dlt645_meter_sim_widget.Dlt645SerialSlaveThread）
log = Signal(str); frame_exchanged = Signal(str, list); slave_frame = Signal(str)
```

### 3. Contracts

**DLT645 帧字节索引（C 在 8、L 在 9、DATA 从 10）** —— 判方向、解数据域一律按此，禁止再数一遍：

| 数据域（未加扰逻辑字节） | 类型 | 说明 |
|---|---|---|
| `DI(4) = 2C DD 32 37` | 4.2（C=11H） | DI `04FFAAF9` 线上低字节在前；**无数据单元**，L=04H |
| `DI(4) + 00 + M + M×2B` | 4.6（C=11H） | 请求头 = 数据ID 6bit \| 分类ID 3bit \| 保留 7bit；M=0 = 读模块全部支持条目 |
| `DI(4) + 00 + M + M×(2B + L)` | 4.7（C=14H） | TLV 头 = 数据ID 6bit \| 分类ID 3bit \| 编码 2bit \| 长度 5bit；**无 645 密码组** |

- 编码格式 1=ASCII / 2=BIN / 3=BCD，取 `LME_INFO_ENTRIES[cat][data_id][1]`；未定义条目按 BIN。
- 4.6 用（**保留位填 0**）2B 头；4.7 用 TLV 头 —— 两者位域不同，不可混用（`pack_lme_query_header` vs `pack_set_header`）。
- 帧封装一律 `DLT645FrameGenerator.build_frame/build_control`（地址低字节在前、数据域 +0x33、CS 覆盖帧首至数据域末）。
- 回包判据：`ctrl = frame[8]`，`ctrl & 0x80`（D7=DIR）为 1 = 从站/模块发出 → 主站方向解析；为 0 = 发给本虚拟表的请求 → 从站引擎应答。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 地址非 12 位 hex | `ValueError`「目标地址必须是 12 位十六进制」 |
| 4.6 条目缺 `/` | `ValueError`「4.6 条目格式应为 分类/数据ID」 |
| 4.7 条目缺 `:` / 数据非偶数位 hex | `ValueError`「4.7 条目格式应为 分类/数据ID:数据hex」 |
| 分类 >7 或 数据ID >63 | `ValueError`（含当前值） |
| 条目数据 >31 字节 | `ValueError`「超出 5bit 上限 31 字节」——4.7 下发前必须拦住 |
| 4.7 条目串为空 | `ValueError`「至少填写 1 个条目」 |
| 串口未监听 | 三按钮自动下发路径：只记日志不弹窗；「下发到串口」：`warning` 提示先「开始监听」 |
| 写串口失败 | 日志 `❌ 下发失败`；手动下发再弹 `critical` |

### 5. Good/Base/Bad Cases

- **Good**：点「读模块版本(4.2)」→ 帧框显示手册 golden 帧 → 已监听则自动下发 → 模块回包经 `slave_frame` → `_fill_resp_table` 逐字段展示（LH / V0102 / v0244 / N0230 / P2008 / V4028）。
- **Base**：未监听时点按钮 → 帧仍生成在帧框 + 日志留「串口未监听」提示，之后可点「下发到串口」补发。
- **Bad**：4.7 不确认直接下发写类条目（本地接口默认信息=波特率/校验位、继电器控制等会改模块参数）→ 必须 `QMessageBox.question` 列出条目明细，取消则不下发（帧保留）。

### 6. Tests Required

`test/test_dlt645_sim_lme_query.py`（脚本式 `check()` 计数）断言点：

1. **逐字节 golden**：`build_single_sta_query() == 68 AA AA AA AA AA AA 68 11 04 2C DD 32 37 53 16`（手册 §5.1.1 发送示例）。
2. **数据域位域**：4.6 M=0/M=1/M=2 → `01DD00FF0000` / `01DD00FF00010F00` / `01DD00FF00020F00C101`；4.7（0/15:0500）→ `01DD00FF00010F140500` 且 TLV 头 `id=15,cat=0,enc=2,len=2`。
3. **回包解析**：手册 §5.1.1 接收帧（135B，`L=0x7B`，`CS=0x56`，`sum(68…数据域末)&0xFF` 自洽）字段全对且**无**「不完整」；同帧数据单元砍到 40B 重封 → 出现「⚠ 数据不完整」且仍给出已解析字段。注意 APS 字段真实值含不可打印层级标志字节（前缀 `\x01`），断言用 `endswith("0135")`。
4. **错误矩阵**：上表每行一条 `raises(...)` 用例。
5. **offscreen GUI**：三按钮/帧框存在；4.2 隐藏并清空条目框、4.6 恢复；生成失败 `warning` 且**不覆盖**帧框；4.7 确认/取消；未监听不弹窗；`slave_frame` → 结果表；离线 DIR=1 直解。
6. **真实串口回环**（本机 ELTIMA COM1↔COM2，缺失时打印 `[SKIP]` 且不计失败）：监听 COM1 → 对端 COM2 逐字节比对下发的 golden 帧 → 写入手册回帧 → 断言结果表出现 `V0102`。

### 7. Wrong vs Correct

#### Wrong
```python
# ① 手写 645 封装（第二套口径：漏 +0x33 / CS 起止错）
frame = bytes([0x68]) + addr + bytes([0x68, 0x11, len(data)]) + data + bytes([cs, 0x16])

# ② 用 4.7 的 TLV 头打 4.6 查询；或把保留位当长度
out += pack_set_header(cat, data_id, enc, length)     # 4.6 请求必须是 pack_lme_query_header

# ③ 串口收到 DIR=1 帧仍送从站引擎
self.slave_frame.emit(...)                            # 缺此分流 → 引擎回「收到非主站帧，忽略」，界面无输出
```

#### Correct
```python
# ① 唯一封装入口
gen = DLT645FrameGenerator()
frame = gen.build_frame(addr, gen.build_control(0x11), encode_di(DI_STA_VERSION_SINGLE))

# ② 4.6 请求头 / 4.7 TLV 头各用各的
payload = encode_di(DI_DUAL_ENTRY) + pack_lme_query_request(entries)      # 4.6
data    = encode_di(DI_DUAL_ENTRY) + bytes([0, M]) + tlv_parts            # 4.7

# ③ 串口按方向分流
if len(frame) > 8 and (frame[8] & 0x80):   # D7=DIR：模块回包
    self.slave_frame.emit(req_hex); continue
engine = self._engine_factory()            # 否则才是发给本虚拟表的请求
```

> **Gotcha**：`parse_sta_version_single`（4.2）只在**字段字节不足**时补「⚠ 数据不完整」。数据单元 123 字节 < 声明 251 字节也可能完整解析（手册示例即如此）——不要把「长度不足声明值」当成错误。

---

## Scenario: 仪器式图表标签页（QPainter 自绘，频谱图）

> 源自任务 09-14-spectrum-plot（`spectrum_widget.py`）。适用于「把一组数值按工程仪表口径画成图」的新页面（频谱/波形/仪表屏幕）。

### 1. Scope / Trigger

页面没有依赖可用的绘图库（本仓 `matplotlib` 被 PyInstaller spec 显式排除、QtCharts 的自动坐标轴模型与「仪器式固定格」语义不合），要求按参数化网格（参考电平 / 每格量程）+ 数据序列画图并导出图片 → 用 QPainter 自绘，零新增依赖。

### 2. 结构契约

- **纯逻辑层不 import PySide6**：模型 dataclass（`SpectrumParams`/`SpectrumTrace`）+ 纯函数（`parse_levels`/`validate_params`/`y_range`/`y_ticks`/`x_tick_labels`/`format_*`/`count_out_of_range`/`resolve_freq_inputs`）。所有「校验错误」用同一个自定义异常类型（`SpectrumInputError`）承载面向用户的消息。
- **绘制只有一个实现**：`Canvas._paint(painter, rect)` 同时被 `paintEvent`（屏幕）与 `render_image(w, h)`（导出/测试）调用；禁止为导出写第二份绘制代码。
- **主题**：模块级 `palette_for(dark)` 返回全部用色 key；组件暴露 `restyle_for_theme(dark)`，主窗口在创建时与 `_restyle_for_theme()` 两处调用（同 `diff_widget`）。
- **参数表单的双向联动**放在纯逻辑函数里（`resolve_freq_inputs(changed, ...)` 返回四元组或抛错），UI 只负责读字段→调用→回写，`_sync_guard` 防重入；**联动触发用 `editingFinished` 而非 `textChanged`**。

### 3. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| 参数非法 / 文本含非法 token | 抛 `SpectrumInputError`，状态行显示 `⚠ <消息>`（含序号与原文） |
| 非法输入 | **保留已有图形**（不清空），只提示（同 AGENTS.md §8 陷阱 23） |
| 数据点越出当前纵轴 | 裁剪到边缘 + 状态行提示个数（不抛错、不返空） |
| 联动结果非法（扫宽 ≤ 0 / 起始 ≤ 0） | 拒绝该次修改、保留原值并提示 |

### 4. Tests Required

- 纯逻辑：解析容错（含中文全角分隔符）、错误矩阵逐行、轴范围/刻度（含退化输入 `max == min`、空数据回落）、格式化、单位换算、联动四方向。
- offscreen GUI：tab 常驻可见（切协议不隐藏）、控件齐全、绘制后状态行/点数、非法输入不破坏图形、开关切换改变轴口径、`render_image` 尺寸与非纯色、导出文件可被 `QImage` 读回、双主题调色板、清空复位。

### 5. 关键陷阱

- **offscreen 平台没有字体**（`QFontDatabase: Cannot find font directory ...`）：`QT_QPA_PLATFORM=offscreen` 下绘制的文字全是「豆腐块」。断言只能查尺寸/颜色/像素多样性；**要目视核对文字排版必须用默认平台**（`QApplication` 用 windows 插件、`widget.grab()`/`QImage.save()` 即可，无需窗口真的可见）。
- 横轴首/末标签若按居中排版会越出画布或压住纵轴刻度 → 首标签左对齐、末标签右对齐，其余居中。
- 自动适配模式的等分刻度会出现 `47.3275` 这类噪声 → 按分格步长定小数位（`auto_tick_decimals`）后再格式化。
- 状态行文字较长时在窄窗口会被挤压 → 保留 tooltip 全文，不要为了塞下而删信息。
