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

### 6. 测量/交互（MARK 标记、光标读数、两点 Δ、积分带宽）

> 源自 2026-09-14 追加需求：标记颜色区分 + Δ 标注哪两点 + 积分带宽两竖线；以及在复核中修掉的 6 个真实缺陷。

- **图↔表对应**：每个标记一种**与序号绑定的固定颜色**（`MARKER_COLORS_DARK/LIGHT` + `marker_color(dark, order)` 是唯一取色源）。图上竖虚线/圆点/`M?` 标签与标记表**行文字**同色；`restyle_for_theme` 后重算表格色。凡「图上一组图元 + 一张明细表」的界面，都要给同色对应，否则用户在两边找不到同一对象。
- **区域量（积分带宽/限值线类）的画法**：边沿 = 中心 ± 带宽/2，用**与既有图元都不撞色的独立 palette 键**（`ibw`/`ibw_fill`）画两条点划线 + 半透明填充 + 带内标签，并在右上读数框追加一行（**短行**：完整口径文本留给侧栏，否则窄画布下读数框会压住纵轴刻度）。**填充与边线画在迹线之下**（区域带是背景，画在上层会把迹线/标记压暗）；带内标签必须与 plot 求交/夹取，否则窄带靠右缘时会画到绘图区外。关闭开关后必须与未启用状态**逐像素一致**（不留半透明残留）。
- **功率类计算的单位口径**：dB 域求和要在**线性域**做，且必须用**移位求和**（log-sum-exp：`peak + 10log10(Σ10^((v-peak)/10))`）——直接 `10**(L/10)` 在 ±数千 dB 的极端电平上会抛 `OverflowError` 或 `log10(0)` 域错，而异常从 Qt 槽里逃出会让 UI 停在「半更新」状态（轨迹换了、图元没换）。dBm↔dBμV↔dBmV 是常量偏移，在求和前后抵消 → 直接对显示值求和即得该单位下的结果（可用「dBμV 结果 = dBm 结果 + 107」做回归断言）。带宽归一化系数 = `频率步进 / RBW`，未归一化时必须写明**原因**（RBW 未填 / 点数不足），不要用一句“未归一化”掩盖两种不同成因。
- **差值一律标注是哪两点**：Δ 单元格与测量栏文案都带 `M?↔M?` 前缀，参考标记恒在左；提供参考切换下拉。只给一个裸数字的 Δ 在多点测量里无法解读。
- **重计算入口**：`_refresh_markers()` 返回被丢弃的标记数，由调用方拼状态文本；**告警要追加而不是覆盖**已有状态（否则丢点数的提示被吞）。
- **表单参数 vs 已绘制数据必须单源**：画布/标记表一律用 `trace.params`；表单改动未重绘时，只读标签追加「（参数已改，点「绘制」生效）」，不要用新表单参数去渲染同一屏的另一个角落。
- **性能红线**：任何在按钮回调里同步跑的纯 Python 循环都要按最坏形态估复杂度。本例显著度算法逐点左右扫描在「一侧没有更高点」的频谱上是 O(n²)（16000 点 3.74 s 冻结 GUI）；改单调栈后 O(n)（5.3 ms）。**改算法时用「与朴素实现逐例等价」验证语义**（9000 组随机/边界数据 0 不一致），比补几个样例断言可靠得多。
- **状态与数据同源**：`set_trace()` 要清掉悬停读数等「基于上一条轨迹」的 UI 状态，否则十字用新轨迹、读数框显示旧值。
- **粘贴文本要能容忍日志前缀**：现场数据几乎都是带前缀的日志行（时间戳 + 序号 + 中文标签 + `--USER--` 之类线程标记），真实数值在**行尾**。清洗规则要「按行尾数值提取 + 明确统计」，并用**分隔边界**（数值前必须是空格/冒号/等号/逗号/括号等）排除 `12a3` 这类尾部截取。**规则顺序即优先级**：`跳过` 规则绝不能盖在 `报错` 规则前面——第一版把「含日志结构」的行整体丢进「取不到行尾数值就跳过」分支，导致「行内有数值却无法确定行尾值」的行被静默丢弃（旧实现是硬报错，等于把响亮报错降级成静默丢行）。正确写法：先试行尾提取，**取不到且该行含数值 → 报错并指出行号**，只有「整行确实没有数值」才计入跳过。**时间戳必须两层防护**：整行是时间戳要跳过，行尾形如 `HH:MM:SS[:.]mmm`（`12:24:26`、`2026/09/14 12:24:26`、用户日志里嵌的 `12:24:26:295`）也要跳过，否则毫秒会变成 `295 dBm` 假点。**单位白名单只放该列真正会出现的单位**（这里只放电平 `dBm/dBμV/dBmV`；把 `Hz/MHz/GHz` 放进去会让「中心频率 600 MHz」变成假电平）。数值提取路径必须与主路径共用同一个 finite 校验（否则 `1e999` 在一条路径报错、在另一条静默进 inf）。清洗/跳过行数必须回显给用户（`TraceInput.note()` → 状态行），且**任何重写状态行的路径都要带上它**（`_compose_status()` 单一入口，别再各处手拼）。
- **参数区会越来越长**：新增分组后必须把参数面板放进 `QScrollArea`（`setWidgetResizable(True)` + 无边框 + 关横向滚动条），否则矮窗口直接裁掉底部控件。

### 7. Qt 陷阱（本项目实测）

- **offscreen 无字体**：`QT_QPA_PLATFORM=offscreen` 下 `QFontDatabase: Cannot find font directory ...`，绘制出的文字是豆腐块 → 断言只能查尺寸/颜色/像素多样性；**要目视核对文字排版必须用默认平台**（`QApplication([])` 不设 offscreen + `widget.grab()` / `QImage.save()`，不需要窗口真的可见）。
- **`bytes(image.constBits())` 必须持有 QImage 引用**：`bytes(canvas.render_image(w, h).constBits())`（临时对象上取 buffer）会 **access violation（0xC0000005）**；先 `img = ...` 再 `bytes(img.constBits())`。
- **`QSplitter` 显隐子控件不自动让空间**：新显示的表格会被分到 0 高度 → 显隐后要显式重分配 `setSizes()`（并考虑 `sum(sizes)` 与各子控件 `minimumHeight()`，避免算出负高度）；**未 `show()` 时 `sizes()` 不反映真实布局**，不能用它判定溢出。
- **`QTableWidget` 子控件的 `isVisible()` 在父窗口隐藏时为 False**：测试断言「表格是否显示」用 `isHidden()`。
- **测试点按钮要用真实信号**：测量类操作至少各覆盖一次 `btn.click()`（+`processEvents()`），只直调 `_on_xxx()` 私有方法会漏掉 `.clicked.connect` 漏挂这类最易回归的缺陷。同样，用鼠标测交互时**每次点击前重新取 `plot_rect()`**——表格显隐会改变画布高度，复用旧矩形会以「布局」而非「逻辑」原因失败。

### 8. 关键陷阱（承接上文）

- 横轴首/末标签若按居中排版会越出画布或压住纵轴刻度 → 首标签左对齐、末标签右对齐，其余居中。
- 自动适配模式的等分刻度会出现 `47.3275` 这类噪声 → 按分格步长定小数位（`auto_tick_decimals`）后再格式化。
- 状态行文字较长时在窄窗口会被挤压 → 保留 tooltip 全文，不要为了塞下而删信息。
