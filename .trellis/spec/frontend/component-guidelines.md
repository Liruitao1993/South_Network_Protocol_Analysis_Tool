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

### 7. 解析摘要（summary）约定

> 源自任务 09-14-batch-test-frame-summary（批量解析摘要体现测试帧的测试模式）。

- **摘要逻辑只有一份实现**：`main_gui.MainWindow._get_csg_new_gen_summary` / `_get_gw_new_gen_summary`（协议10/11 共用）/ `_extract_csg_core_content` / `_extract_test_mode_content`。测试里**禁止复刻**一份（历史教训：`test/test_csg_summary.py` 曾把摘要逻辑抄进测试文件，抄件与产品实现漂移后仍在“全绿”，实际验证的是抄件：产品输出「网络管理消息/业务标识:确认(0x00)」，抄件输出「网络层/业务标识:确认」）。范式：`class Host: _get_xxx = main_gui.MainWindow._get_xxx`（未绑定方法，免 QApplication）；**staticmethod 必须 `staticmethod(...)` 显式包裹**，否则挂到类体后变成实例方法多传一个 self；摘要方法若内部调用其它 helper（如 `_extract_test_mode_content`）或读类属性（`_TEST_MODE_SENTINELS`），Host 必须一并提供，否则运行期 AttributeError。
- **同一语义字段在不同解析器里槽位可能相反**：`_f(table, name, raw, parsed, comment, ...)` 的前三列语义由各解析器自行决定——协议9 表61 把**模式名放 comment**（`parsed` 是数字），协议10 检测扩展命令把**模式名放 parsed**（`comment` 是描述串）。跨协议取名称时用「**parsed 非数值则名称在 parsed，否则在 comment，再退回 raw**」的槽位探测，**不要**用描述文本黑名单（漏掉一条描述句就会静默取错名称，模式15 曾因此把「转发数据规约类型字段扩展为新一代测试模式」当子模式名）。
- **行名共享 = 隐式契约，必须显式设防**：`上行负载` 这类行名被多个非测试业务共用（sid 0x01/0x03/0x04/0x06 的上行帧都只有这一行），helper 单独调用会把它们写成「测试帧上行」。两道防线：helper 内用**自证条件**（表中 `业务标识` == 240/0xF0）限定分支；调用点用**哨兵行 gate**（仅当 `测试模式/配置操作`/`安全测试模式`/`新一代测试模式` 之一存在时才调用）。
- **把新分支放在正确的优先级**：测试帧的帧类型域是「命令帧」，测试帧摘要必须在 `_extract_csg_core_content` 的**第一个分支**返回，否则会落到通用命令帧列表被淹没。
- **新用例走整链而非直调 helper**：只断言 helper 时，gate/分支接线写错也测不出（复盘：gate 改成永不成立，直调用例仍全绿）。用**整帧 → parse_to_table → 摘要**断言，并补一条「同类非目标帧不被污染」的回归网。
- **名称自带括号时不要追加数值**：解析器的保留项写成 `保留(14)`、`…测试模式(暂未使用)`，直接拼 `({value})` 会得到 `保留(14)(14)`。

### 7b. 协议9 2.0 测试扩展 ID 的新增契约

> 源自任务 10-13-csg-test-ext-0009（新增扩展 ID `0x0009`「报文聚合传输测试模式」）。

- **新增一个扩展 ID 必须同时改四处，缺一处就是「半通」**：
  ① 解析：`csg_new_gen_cmd_payloads._TEST_EXT_ID_MAP` + `_parse_test_ext_<id>` + `_parse_test_ext_payload` 的 `parsers` 分派；
  ② 组帧：`csg_new_gen_frame_gen.TEST_EXT_ID_MAP` + `build_ext_<id>` + `_EXT_BUILDERS` + **`test_modes()`**；
  ③ 仿照回填：`csg_frame_reverse._fill_ext` 的 `elif ext_id == 0x<id>` 分支；
  ④ 摘要：只要进 ① 的表就自动生效（`batch_core.extract_test_mode_content` 的 `扩展ID:<名称>` 回退），但**必须补断言**。
  只加映射表不加 `test_modes()` 的典型症状：能解析却**不能在组帧页选到**、仿照回填提示「扩展ID=N 无对应模式」。
- **`test_modes()` 是「组帧页模式下拉 + 仿照回填候选 + `mode_by_key`」的公共入口**（界面不硬编码模式清单）；新增模式后 `test_csg_frame_gen_gui.test_all_test_modes_build_linked_frames`（遍历全部模式组帧 + 校验回读）与 `test_csg_frame_reverse`（全量反解）会自动覆盖新模式，**必须全绿**才算接线正确。
- **字节口径**：`ext_data[x] = 文档字节 x+3`（见 `_parse_test_ext_0005` docstring）——文档各扩展表用「字节3/4/5…」编号，而扩展数据从文档字节 3 开始。新增字段前先核这条，别按表里的字面下标切。
- **界面不得写死模式数量**：`csg_test_frame_gen_widget._MODE_COUNT = len(fg.test_modes())` 是唯一来源（历史坑：docstring 写 26、下拉写 24、tooltip 写 26，三者互不一致且都错）。
- **字段名 / 模式 key / 参数名要同名同值贯穿四处**（解析行名、`TestMode.key`、`ModeField.name`）——摘要按行名匹配、反解按 key+参数名回填，改名会静默失效。

### 7c. 串口工具断帧（协议特征 / 前导 FE / 可调超时）

> 源自任务 10-13-serial-rx-framing（1.23.78：修「带前导 FE 的一帧被切成两条 `[RX]`」+ 断帧设置）。

- **前导 FE 只有一个来源**：`wakeup_prefix.wakeup_prefix_len`（经 `serial_tool_widget._wakeup_base` 调用）。
  **禁止**在分帧层另写 FE 扫描（同 AGENTS §8 陷阱 75 的单一来源原则）。
- **长度返回值「含前导」**：`frame_length_for` / `declared_frame_len` 返回 `base + 结构长度`，
  这样三个调用点（`_emit_protocol_frames` / `_emit_structured_frames` / `_flush_raw_display`）
  的 `buf[need-1] == 0x16` 自证与 `del buf[:need]` 语义**零改动**。改这里时别「顺手」改成返回结构长度。
- **前导只对 68 家族生效**（`ft12_68` / `dlt645` / `dlt698_45` + 未指定协议的启发式）；
  HDLC（`7EH` 定界）与 DLMS Wrapper（`00 01`）**不得**加前导容忍（首字节另有语义）。
- **「只有 FE」= 帧已开始未收全**：`_frame_incomplete` 必须先算 `base`，`base >= len(buf)` 返回 True；
  纯 FE 噪声由「协议帧等待上限」兜底刷出 —— 任何情况下**不得丢字节**。
- **断帧设置 5 键**（`rx_framing_mode` + 4 个超时）：默认值 = 原模块常量（`FRAME_TIMEOUT_DEFAULTS` 是唯一来源）
  ⇒ **只新增键，`CONFIG_VERSION` 不动**（改既有默认值才需要迁移）。`FRAME_TIMEOUT_RANGES`
  同时是 UI spin range 与 `merge_params` 夹紧的来源，**不要**在两处各写一份范围。
- **`timeout_only` 必须三处同时跳过结构路径**：`_on_raw_data`（收到即切）、`_flush_raw_display`（定时器）、
  `_flush_raw_display_now`（切模式/收尾）。漏一处就会出现「选了仅按字节超时却仍按协议切帧」。
- **说明行只在该输出时输出**：`_log_framing_summary()` 仅在**设置变更 / 协议变化 / 每轮开始**时调用；
  逐帧打印会冲垮日志（AGENTS §8 陷阱 58 的 burst 精神）。
- **回归**：`test/test_serial_proto_frame.py` [12]/[13]（前导 FE 矩阵 + 参数默认/夹紧）、
  `test/test_serial_tool_widget.py` [34]（现场帧两块交付只出 1 行、`timeout_only` 对照、持久化、控件不裁字）。

### 7d. 蓝牙特征码优选与探测

> 源自任务 10-13-bt-char-autodetect（1.23.79：连上即可收发，不再让用户在特征码列表里挑）。

- **打分优选只有一个实现**：`bluetooth_core.rank_characteristics` / `pick_auto`（权重 `CHAR_SCORE_*`、
  族谱 `PASSTHROUGH_UUIDS` 均在 `bluetooth_core`）。**界面禁止再写「取第一个可用」** —— 历史实现正是那样，
  实测常选到设备名 `2A00` / 电量 `2A19` / DFU；反例自检见 `test_bluetooth_widget.py` [11]。
- **接线顺序**：`_on_characteristics_updated` = 「① 按设备地址沿用 → ② 打分优选 → ③ 提示」；
  **换到没记过的设备要先清掉上一台的选择**（`_on_connected` 里按 `last_device` 比较），否则上一台的通道会压住优选。
- **探测必须等 `subscribe_finished` 再写**：订阅是异步的；状态机 `core.ProbeSession`
  （`select → write → wait`，事件 `on_subscribed / on_written / on_frame / on_timeout`）纯逻辑，
  界面只「按意图调 worker + QTimer + 喂事件」，且**仅当 `session.step` 变化时才推进**（防重复下发同一意图），
  **不许 sleep 阻塞 GUI**。
- **全败恢复原选择**；成功才写 `char_map[address] = {recv, send, source, ts}`（`remember_choice`；
  `CHAR_MAP_MAX=20` 按 `ts` 淘汰；坏条目逐条丢弃）。
- **探测载荷**：`core.resolve_probe_payload(..., parse)` 的 `parse` **由界面注入** `parse_plain_text`
  （纯逻辑层不 import Qt 侧实现，也不写第二份「什么算合法 HEX」）；HEX 写错 → 拒绝且一个字节都不写。
- **对话框结论要文字化**：不可用方向标「（不可写）/（不可通知）」（置灰在 QSS 主题下不可见 —— 陷阱 71），
  列表按打分置顶并预选优选结果。

### 7e. 蓝牙 MTU / 写上限实时化（连接后轮询 + 发送前重读）

> 源自任务 10-13-bt-mtu-live-limit（1.23.80：修「同一台设备有时 20 字节、有时 512 字节」）。

- **现象与根因**：`ATT_MTU` 由**操作系统异步协商**（Windows 上应用层只能读、不能请求 ——
  MS 文档 `GattSession.MaxPduSizeChanged`：*you can't change the value used by Windows itself*），
  连接瞬间读到的常常还是 ATT 默认值 **23**（负载 `23-3=20`）；bleak 官方文档亦写明「可能先读到 20、
  过一会儿再读才是高值」。旧实现只在连接时读一次快照 ⇒ 一旦读到 20 就整条连接期都用 20。
- **判据单一来源**：`bluetooth_core.mtu_is_unnegotiated(value)`（`≤ MTU_DEFAULT=23`，含 0/`None`/非法值）；
  `MTU_POLL_INTERVAL=0.25` / `MTU_POLL_TIMEOUT=3.0` 与 `MIN_CHUNK` 同处。
  **「对端确实只支持 23」与「结果还没回报」在读数上不可区分** ⇒ 超时**只打一行提示，不得报错**。
- **两条措施（缺一不可）**：
  ① `_connect_coro` 在 `connected` 与订阅**之后** `await self._poll_mtu_if_needed(client)`
  （放前面会让界面/订阅白等 3 秒；断开/换 client/`_closing` 立即静默返回）；
  ② `_write_coro` 在 `_chunk_plan()` **之前** `self._refresh_live_limits()` —— 分包按**发送那一刻**的真实值。
- **活对象私有持有**：`_collect_characteristics` 顺手把 bleak 特征码对象存进 `self._char_objects`
  （重读实时 property 用），**不进**投给界面的 dict；断开/掉线时 `clear()`。
- **`mtu_updated = Signal(int, list)`**（MTU, 最新特征码 dict）与 `characteristics_updated` **不可互相替代**：
  后者语义是「枚举完成」，界面收到会走「沿用/优选 → `set_characteristics`（**重新订阅**）」，
  拿它刷上限会产生多余重订阅、改写用户已选通道。界面 `_on_limits_updated` 只更新 `_chars` 缓存 +
  MTU/特征码标签 + 刷新**打开中**的对话框（`CharacteristicSelectDialog.refresh_chars`，保勾选与当前行）；
  MTU 文案抽在 `_mtu_text()`（连接时与实时更新共用），默认值时必须写出「ATT 默认值，协商结果未回」。
- **有变化才发**：无变化时 `_refresh_live_limits` 完全静默（不刷日志、不发信号），否则每包都会刷 UI。
- **回归**：`test_bluetooth_core.py` [11]（判据边界 + 常量关系）、`test_bluetooth_worker.py` [7]
  （迟到协商 / 只支持默认值 / 发送前重读 MTU 与特征码两条路径 / 断开打断）、`test_bluetooth_widget.py` [12]
  （标签、缓存、**不重订阅**用 `worker.char_sets` 计数钉住、对话框刷新）。
  **测轮询时先改特征码上限、再改 MTU**（轮询只认「MTU 变了」就结束该轮，反序会出现中间态 ⇒ 随机红）。
- **变异反证（本任务已做，均干净变红后还原）**：① 去掉连接后轮询 → 5 项红；
  ② 去掉发送前刷新 → 5 项红（分包退回 `[20]*15`）；③ `mtu_is_unnegotiated` 改 `<`（不含 23）→ 2 项红。

### 7f. 蓝牙自定义按钮「按协议替换地址 + 重算校验」（`frame_addr_fix.py`）

> 源自任务 10-13-bt-button-addr-checksum（1.23.81：按钮能填协议与地址，发送时按协议换地址并重算校验）。

- **单一职责**：新模块 `frame_addr_fix.py`（纯逻辑、无 Qt）只做三件事 —— 声明字段（`fields_for`）、
  解析地址文本（`parse_address`）、替换+重算（`apply`）。**界面不硬编码协议细节**：对话框按 `fields_for`
  动态生成 1~2 个输入框，标签/提示都来自字段声明。
- **地址定位与校验算法一律复用既有实现**（禁止第二份偏移/算法表）：
  645 → `DLT645FrameGenerator.build_frame(..., scramble=False)`；698.45 →
  `DLT69845FrameGenerator._assemble_frame`（HCS/FCS 自动）；依瓦 → `yw645_wire.encode_frame`；
  南网上行 → `csg_uplink_wire.encode_frame`（保留 `resolve_layout` 的原长度域形态）；
  南网/国网 → 字节拼接 + `Frame.calculate_checksum` / `GDWFrame.calculate_checksum`。
- **布局事实（探针实测，改前先看 `research/layout-probe`）**：南网 `68 L L C [源6B+目的6B] …`（地址仅当
  控制域 **D5=0x20**，**无第二个 68H**）；国网 `68 L L C 信息域6B [源6B+中继6B×n+目的6B] AFN …`（地址存在
  当且仅当信息域 byte0 **bit2=1**，长度 `12+6×高 4 位`，福建增补 AFN 0x50~0x56 不支持）；
  645/依瓦 `68 A6 68 C L DATA CS 16`（前者低字节在前、后者高字节在前）；698.45
  `68 L(2) C 地址特征(1B) SA(1+低4位) CA(1B) HCS(2) APDU FCS(2) 16`；南网上行见 `resolve_layout`。
- **先自证再改**：结构（`68…16`、长度域自洽）+ **原帧校验**都必须通过才允许替换；地址在线长度必须与帧内
  一致；无地址域/协议不支持/福建增补 → 可读错误（**不猜、不静默发原帧**）。
- **地址写法双认**：含分隔符/`0x` → 在线顺序原样；纯书写序 → 协议编码（自动字节序/BCD）。提示行必须回显
  「将写入 N 字节：…」，且内容框可解析时给出替换后预览（校验旧→新）。
- **依赖**：协议模块**按需导入**（`dl_t698_45_frame_gen` 依赖可选 `crcmod`，模块级导入会让没装 crcmod
  的机器连蓝牙页都打不开）。
- **回归**：`test/test_bluetooth_addr_fix.py`（96 项：六协议真帧 oracle + 错误矩阵 + 反例自检）、
  `test_bluetooth_core.py` [12]（按钮新键）、`test_bluetooth_widget.py` [13]（对话框联动/预览/发送替换/
  失败不发/发送框不被改写）。**变异反证**（本任务已做）：645 不重算校验 → 2 项红；地址不反转 → 9 项红；
  698 不重算 HCS/FCS → 2 项红；不校验长度 → 2 项红。

### 7g. 蓝牙自定义报文区的空间治理（按钮随空间自动 + 工具栏常驻，1.23.82）

> 源自任务 10-14-bt-custom-buttons-space（按钮越加越多 → 改前 64 个 ≈ 22 行 ≈ 700px 把日志压没）
> 与 10-14-bt-custom-buttons-fit（复核后修正：固定 3 行封顶会「腾出空间还白白滚动」，编辑按钮也不该被折叠藏起来）。

- **结构**：右栏 = `QSplitter(Vertical)`（`日志` ↔ `发送区 + 自定义区`，`childrenCollapsible=False`）；
  自定义区 = `CollapsibleSection(key="custom_buttons")`，内容 = `ButtonScrollArea`（本页子类，包 3 列按钮网格）；
  **5 个编辑按钮 + 提示在折叠区外面**（`_build_custom_group()` 返回的容器持有），折叠/展开都可见。
- **高度语义（不要退回硬封顶）**：`_custom_scroll_limits() -> (下限, 上限)`：
  下限 = 1 行按钮高（`core.CUSTOM_MIN_ROWS`）；上限 = **按钮全部显示所需高度**（按行数×行高+间距算，
  **不要读 `custom_host.sizeHint()`**，重建后它是旧值/0）。⇒ 空间够就全显示、不够才滚动。
- **`ButtonScrollArea` 不可换成裸 `QScrollArea`**：后者的 `minimumSizeHint()` 会跟着内层网格走，
  按钮一多就把「最小高度」透传给分栏器（实测下半区最小 559px、日志只剩 177px）。
  **下半区也不要加尾部 `addStretch()`**，否则腾出的空间被弹性空隙吃掉。
- **折叠**：收起时本区尺寸策略锁 `Maximum`（标题与工具栏之间不留大片空白），展开恢复 `Preferred`；
  状态写 `settings["custom_collapsed"]`。
- **配置键**：`custom_collapsed`(bool) / `right_split`([日志,下半区] px)，走
  `bluetooth_core.merge_settings` → `normalize_right_split()` 宽容夹紧（坏值不抛）；
  `right_split` **只在两侧都有真实高度时才采集**。
- **效果（实测，offscreen 1200×800）**：10 个按钮 + 腾出空间（分栏 ≈ [177,559]）→ 按钮区 96px（=内容）、
  **滚动条 0**；64 个按钮 + 同样空间 → 按钮区用满 396px、滚动条 128（内容 528）；默认分栏（[496,240]）
  + 64 个按钮 → 日志 496px 不被挤；收起 → 本区 23px（标题行）+ 工具栏仍可见。
  **对照旧实现（上限钉死 3 行）**：同样腾出空间 → 10 个按钮仍只 3 行 + 滚动条。
- **测试注意**：几何断言前要 `settle()` 多泵几次事件；**必须分别量「默认分栏」与「拖大分栏」两档**
  （只在默认档量会漏掉「腾出空间后仍滚动」这个缺陷）。
- **回归**：`test_bluetooth_widget.py` [14]、`test_bluetooth_core.py` [13]。
- **变异反证（本任务已做，均干净变红后逐字节还原）**：① 上限改回固定封顶 → 2 项红；
  ② 工具栏放回折叠内容 → 3 项红；③ 不设最小高度提示 → 1 项红；④ 不采集分栏尺寸 → 2 项红。

### 7h. 串口工具「批量替换通信地址」（复用 `frame_addr_fix`，写回表内）

> 源自任务 10-14-serial-batch-addr（1.23.83：用户 → 「串口工具页添加报文时也应该能批量替换通信地址，
> 按对应协议替换并重新计算校验」）。与 §7f（蓝牙页「发送时替换」）**同一引擎、不同时机**。

- **Scope / Trigger**：一批报文（尤其「加载报文文件」导入的、`protocol=None`）要发给另一台表计，
  需要**按协议改地址域 + 重算校验**。触发点是「写回表内」而非「发送时套用」——
  表里看到的就是要发的内容，导出/复制一致。
- **单一职责**：串口页只做**编排**，地址定位/字节序/校验算法全部走 `frame_addr_fix`
  （§7f 的复用表照旧，**禁止第二份偏移或算法清单**）。新增纯逻辑：
  `fix_frame_text(data_hex, protocol, values) -> (new_hex, notes, error)`、
  `batch_fix_commands(commands, indices, protocol, values, write_protocol, fix_match) -> List[AddrBatchItem]`
  （**不修改入参**）、`addr_batch_summary(items) -> (首行, 明细)`；GUI 侧 `_on_batch_addr_clicked` /
  `_apply_addr_batch`（返回撤销快照）/ `_undo_addr_batch`。
- **三态语义**（`ADDR_STATUS_*`）：`ok`（已替换，`data_hex` 是新帧）/ `kept`（尝试失败：结构或**原帧校验**不符、
  地址写错、协议不支持 → **原样保留 + `error` 可读**）/ `skipped`（发送数据本身不是有效 HEX）。
  **失败绝不洗白、绝不静默改半条**（同陷阱 23 精神）；一条出错只影响该条（整批不中断）。
- **前导 FEH**：只在 `FE_WAKEUP_PROTOCOLS = (6, 8)` 内剥离并**原样恢复**（依据 DL/T 645 §5.3.1、
  DL/T 698.45 §6.3.1 b)）；其余协议带前导必须报错 —— 剥了等于「救活」错帧（AGENTS §8 陷阱 75）。
  剥离走 `wakeup_prefix.strip_wakeup_prefix`（**唯一实现**）。
- **协议列写入与替换成败解耦**：勾选时对作用范围内**每条**命令写 `protocol`（「这批报文属于协议 X」是用户声明；
  导入的报文协议为空 → 写入后接收侧才能按它断帧解析）。UI 用三态计数 + 逐条原因区分，避免用户误读成「都换成功了」。
- **预期响应**：只在发送数据**替换成功**时尝试，且只动 `HEX_MATCH_TYPES = ("contains","equals","starts_with","ends_with")`
  当 `match_hex` 非空；「能自证才替换」由 `frame_addr_fix.apply` 的第一步（结构 + 原帧校验）天然保证；
  通配 / 正则 / 自证失败 → 保持原样 + `notes` 说明（**不得静默改坏匹配规则**）。
- **作用范围**：对话框显式选择（默认「勾选的命令（N 条）」，无勾选时默认「全部命令（M 条）」）；
  `indices` 里越界 / 非 int / bool 一律忽略。
- **撤销**：`_apply_addr_batch` 返回 `[(原下标, (原 data_hex, 原 protocol, 原 match_hex)), …]`，
  只保留最近一次（再次替换覆盖）；汇总弹框内 `addButton("撤销本次替换", ActionRole)`（**无改动时不给按钮**）。
  发送中禁止替换。回滚范围明确：只恢复这 3 个键。
- **日志/弹框节流**：明细上限 `ADDR_BATCH_LOG_LIMIT = 20` 行 + 「另有 N 条」（同 AGENTS §8 陷阱 58 的 burst 精神）；
  汇总弹框每类最多 3 条原因。弹框走 `QMessageBox.exec`，**测试要 patch 掉 `exec`**（否则 offscreen 阻塞）。
- **对话框**：协议下拉取自 `frame_addr_fix.supported_choices()`；地址输入行按 `fields_for` 动态重建（保输入值）；
  提示行回显「将写入 N 字节：…」，并给作用范围内**样例命令**的替换预览（成功给 notes，失败给 error）。
  确定前只拦「空地址 / 写法非法」；**698 SA 的长度由帧内地址特征字节决定**（此处推导不出 → 放行，精确长度交给
  `apply` 判定并给出可读结论）。
- **回归**：`test/test_serial_addr_fix.py`（104 项：六协议真帧 oracle = 替换后**该协议校验器 0 fail** +
  非地址/校验字节不变、前导 FE 门控、预期响应五类、作用范围/无效下标、不修改入参、兜底不中断、汇总文案）+
  `test_serial_tool_widget.py` [35]（536 项：按钮不裁字、对话框字段联动/预览/校验、端到端替换（含带前导 645 帧）
  与落盘读回、撤销、只处理勾选行、发送中禁止）。
- **变异反证（本任务已做，均干净变红后逐字节还原）**：① 前导 FE 不恢复 → 4+1 项红；
  ② 前导门控失效（全协议剥）→ 5 项红；③ 发送未成功也去改预期响应 → 1 项红；
  ④ 就地修改入参 → 2 项红；⑤ 关闭协议列写入失效 → 1+1 项红。
- **已知边界（复用既有引擎的固有口径，勿当缺陷修）**：依瓦定制645 的帧与 645 **同形**（结构 + 原帧校验都过），
  因此选「645」处理依瓦帧也会成功（地址按 645 字节序写）—— 用户需选对协议；
  `frame_addr_fix` v1 只支持 0/6/7/8/13/14，9/10/11/12 给出可读「暂不支持」。

### 7i. 蓝牙自定义按钮的「按协议类别批量替换地址」（1.23.84）

> 源自任务 10-14-bt-batch-address（用户 →「自定义按钮也需要支持批量替换地址的能力，通过按照协议类别统一进行替换」）。
> 与 §7f（单按钮「发送时替换」）、§7h（串口表内写回）**同一引擎**：地址字段/长度/算法都走 `frame_addr_fix`。

- **入口 / 结构**：底部工具栏「批量地址…」→ `BatchAddressDialog`。对话框**只产出补丁**
  （`result_patches()` → `{下标: {"protocol": int|None, "addr": dict}}`），写回由页面统一走 `_set_buttons`
  （重建网格 + 落盘一次）。**不要在对话框里直接改按钮列表**（否则「全或无」与日志无法集中处理）。
- **默认作用域 = 已绑定所选协议**（清除模式 = 已绑定任意协议），另有 全选 / 全不选 / 只选本协议；
  协议下拉第 0 项 =「（清除协议与地址）」（此时 `protocol_index() is None`）。
- **逐按钮用「自己的报文」预检**（不是只按第一个按钮）：`_precheck` → `parse_plain_text` →
  `frame_addr_fix.check_values(protocol, values, frame)` → `frame_addr_fix.apply(frame, ...)`。
  理由：698.45 的 SA 长度由**该帧的地址特征字节**决定，不同按钮可以不同。
- **只对勾选的行算错误**：未勾选的行不许出现 ⚠（给南网按钮换地址时，645 的按钮不该被标「不是南网帧」
  —— 那是噪声，会把用户带偏）。勾选变化要触发重算（`_on_item_changed` → `_refresh_marks`）。
- **失败项语义（本任务的核心口径）**：预检失败的行标原因且**默认不勾**（用户不动勾选 ⇒ 天然全或无）；
  用户强行勾上 → `QMessageBox.question` 二次确认「将跳过这 N 个」→ 确认后只改可应用者、跳过项逐条 warn
  日志；**拒绝确认则一个按钮都不改**；全部失败时不 `accept()` 且 `result_patches()` 为空（状态自洽）。
- **清除模式**：返回 `{"protocol": None, "addr": {}}`，页面侧 `pop` 掉两个键（发送时恢复按原样发送）。
- **共用校验入口（单一来源）**：`frame_addr_fix.addr_lengths_for_frame(frame)`（由帧定 698.45 SA 长度）与
  `check_values(...) -> (回显项, [(标签, 原因)])` 由单按钮编辑对话框与批量对话框共用（单按钮侧行为/文案
  逐字符不变）。纯逻辑层**不拼 UI 文案**（`✓`/`⚠` 由界面拼）。
- **工具栏宽度**：本区工具栏 6 个按钮 + 尾部 stretch，**无行内提示标签**（「右键可编辑 / 删除 / 移位」在按钮
  tooltip 末行）。**不要**用 `setFixedWidth`（陷阱 63）；新按钮走 `fit_btn_width`（只设下限）。
- **本页不得 import `main_gui`** ⇒ 工具栏没有 FlowLayout（它住 `main_gui.py`）可用：靠「删掉占宽的提示标签」
  换宽度，实测 10 / 14 / 16 / 24 号字全不裁字。若将来字号再变导致裁字，再单独立项抽 `flow_layout.py`。
- **回归**：`test_bluetooth_widget.py` [16]（对话框直测 + 端到端写回 / tooltip / 日志 / 落盘 / 发送用新地址 /
  清除还原 / 工具栏宽度）；`test_bluetooth_addr_fix.py` [6]（共享入口边界 + 与 `apply()` 对拍同源）。
- **变异反证（本任务已做，均干净变红后逐字节还原）**：① 默认勾选改成「全勾」→ 9 项红；
  ② `_select_scope` 改成全选 → 5 项红；③ 跳过失败项时不弹二次确认（静默跳过）→ 2 项红；
  ④ 清除模式只删 `protocol` 不删 `addr` → 1 项红。

### 7j. 协议专属「光伏升级」页 / 长流程串口传输页（698.45 文件传输升级）

> 源自任务 10-14-dlt698-file-transfer-upgrade（协议8 分布式产品升级：启动传输 → 写文件×N → 执行升级）。
> 适用面：**任何协议专属、走共享串口、需要逐帧确认的长流程页面**（下一候选：批量写参数 / 任务下发）。

- **创建即隐藏**：`setup_ui` 里 `addTab` 之后**当场** `self.tab_widget.setTabVisible(idx, False)`。构造期
  `_on_protocol_changed` 可能一次都不触发（`protocol_combo.addItem` 在 `connect` 之前，`main_gui.py:2792` vs `:2802`），
  只靠协议回调设初值会把空 tab 露出来。实例：`main_gui.py` `_upgrade_placeholder` / `_upgrade_tab_index`（tab 创建段，蓝牙工具之后）。
- **显隐一律读注册表**：`_on_protocol_changed` 里 `setTabVisible(self._upgrade_tab_index, spec.has_upgrade)`。能力字段
  `has_upgrade` 声明在 `protocol_registry.ProtocolSpec`（紧跟 `has_sequence_diagram`），**只有协议8 `True`**，
  helper `protocols_with_upgrade()`；断言 `test_protocol_registry.py::test_upgrade_only_698`，
  可见性矩阵对拍 `test_yw645_gui.py::test_tab_visibility` 的 `pairs` 行 `("_upgrade_tab_index", spec.has_upgrade, "升级")`。
- **懒加载三件套**：`_ensure_lazy_tab` 加分支 → `_ensure_upgrade_tab()`：`hasattr` 守卫 → **函数内** import
  `dlt698_upgrade_widget.Dlt698UpgradeWidget` → `tab.set_serial_worker(self.serial_worker)` → `_replace_lazy_tab(...)` →
  `apply_chinese_context_menus(tab)`（样板照 `_ensure_serial_tool_tab`）。函数内 import 是铁律：`dl_t698_45_*` 顶层
  `import crcmod`（可选依赖），模块级导入会让没装 crcmod 的机器连主窗口都打不开。
  新增 `def` **绝不能插进 `__init__`/`setup_ui` 的语句流中间**（AGENTS §8 陷阱 68：后续 UI 代码会变成上一个方法内的死代码）。
- **共享串口只订阅 `raw_data_received`、只用 `write_raw` 发送，不得用 `frame_received`**：`SerialWorker._process_buffer` 只认
  645 双 68H 与 FT1.2；698 整帧长度 = `L+2` ⇒ 必落「找第一个 0x16」容错分支被截断（600B 载荷含 0x16 概率 ≈90%）。
  页面自组帧走单一来源 `frame_deframe.frame_length_for("dlt698_45", buf)`（L+2 + 末字节 `16H` 自证 + 前导 FEH 容忍，
  见 §7c 同源判据）。发送用 `write_raw`（静默）+ 本页自建 TX/RX 日志行（`send_frame` 的 `[发送]` 会刷屏，AGENTS 陷阱 58）。
- **逐包确认 = 单发 `QTimer` + 状态标志位，不建 `QThread`**：状态机 `idle → starting → transferring(i) → finishing → done/failed/aborted`；
  每发一帧起一次 `setSingleShot(True)` 定时器，收到匹配确认停表推进；超时/否定 → 同一包重试（PIID 自增），**重试用尽整体停止**、
  不再发后续帧。照 `test_plan_widget.TestPlanWidget` 既有范式（免线程回收、免 `thread_registry`）。
  确认判定用 `DLT69845Parser` 的解析结果（APDU 类型 + OMD + DAR），不用字符串/字节比对。
- **耗时 / 失败 / 超时必外显**：进度只按**已确认**包累加（`已确认字节/总字节` + `第 x/N 包`）；失败与超时**既写日志行、又弹框**
  （结束态），绝不静默停在半截（口径同 §7f/§7h 的「不静默跳过」）。
- **TX/RX 日志的帧显示口径 = `fmt_hex(data, limit=HEX_LOG_LIMIT)`（唯一入口，`HEX_LOG_LIMIT = 200`）**：**≤200 字节整帧打印**
  （启动传输帧约 62 字节、执行升级帧几十字节 —— 尾部校验值/结束符 `16H` 必须看得见；按旧口径截到 48 字节时现场连校验值都核对不了）；
  超过则**头尾各 100 字节 + 中间 `...` + `(共 N 字节)`**（头段给帧头/APDU 头/块序号，尾段给帧尾，省略掉的正是升级包数据体本身）。
  **不要退回「只显前 N 字节」**：那既丢帧尾、又让小帧被无谓截断。回归：`test_dl698_upgrade_gui.py` 的 `test_helpers`（`fmt_hex` 边界矩阵）
  与 `test_happy_path`（真实日志行：启动帧无 `...`、写文件行 200 token + `共 N 字节`）；变异反证 = 把上限改回 48、或把尾段去掉，两者都必须变红。
- **可选「读版本信息」两步（1.23.85 追加，用户需求）**：`升级前读版本信息` / `升级完成后读版本信息` 两个勾选项
  （**默认都不勾**、落盘；传输中与「每包字节数」一起冻结 + `_finish_buttons` 统一解冻），状态机新增
  `ver_pre` / `ver_post` 两阶段。帧 = `build_read_version(sa, ca, piid, oad=…)`（GET-Request Normal +
  **TimeTag `00`**，SA/CA 取页面同一份配置）；判定 = `check_get_response(frame, oad)`（HCS/FCS +
  服务码 `0x85` + `GetResponseNormal` + OAD 回显 + Get-Result CHOICE：`00`=错误信息 DAR / `01`=数据）。
  **失败一律不阻断升级**（重试用尽 → 记日志继续，用户裁决）；版本内容进日志（命名业务字段优先，
  厂家扩展对象退化为数据值串）。`generate_get_request_normal` 的 TimeTag 走**新增可选参数**
  （默认不补 ⇒ `frame_gen_widget` 等既有调用方逐字节不变）。
- **「升级完成后读版本」与「是否发执行升级命令」解耦，且读之前先等设备复位（1.23.85 用户纠错追加）**：
  ① 勾了「传完后自动执行升级」⇒ 执行升级**被确认后**读；② **没勾** ⇒ **最后一包写文件被确认后**读
  （有的设备收全升级包会**自动复位升级**，`不读` 是错的）；两种情形都先经过 `PHASE_WAIT_RESET`
  —— 「升级后等待(s)」`spin_read_after_delay`（**默认 10 秒**、范围 0~600、落盘）用**1 秒重复 QTimer**
  倒计时，`_step_label()` 显示 `等待设备复位（剩余 N 秒）`（状态行实时可见），归零 → 记日志 → 进 `ver_post`；
  等待 = 0 ⇒ 不起定时器、立即读（日志写明）。**等待期间状态仍是 `finishing`**（不新增 `STATE_*`，避免动
  「传输中」那批守卫：换文件/开始/清除/状态行），等待期间收到的帧记 `忽略（等待设备复位中）` 且不当确认；
  `中止`/`清除`/`cleanup()` 都必须停该定时器（`_finish_buttons` 统一停）。**`_retry_or_fail` 必须有等待期守卫**：
  `QTimer.stop()` 不撤已投递的 timeout 事件（真实竞态）⇒ 等待期若被触发超时槽，放行会按 `_expected_omd()`
  落到 `OMD_EXEC` **凭空发出「执行升级」帧**、重试用尽还会把等待误判成失败 ⇒ 等待期直接忽略（记 warn）。
  回归段：`test_dl698_upgrade_gui.py` [22]（含真实事件循环倒计时、等待中忽略杂帧/中止/清除/连续两轮）。
- **「读版本内容」下拉的两条命令（同批追加）**：通用版本 `OAD 43 00 03 00` 与**厂家扩展内部版本**
  `OAD FF 10 04 00`（OI `0xFF00` 起为厂商自定义区间，解析器标「未知对象(0xFF10)」）。下拉只存
  `common`/`internal` 键，**OAD 字节只在 `dl_t698_45_upgrade` 一份**（`OAD_VERSION` / `OAD_INTERNAL_VERSION`，
  经 `_read_oad(upg)` 取 —— 页面顶层不能 import 该模块，它顶层 import 可选依赖 crcmod）。组帧与判定
  **都**按所选 OAD ⇒ 两条命令的响应**互斥**（OAD 不符即忽略）。两条现场实帧都被逐字节复现：
  通用 `<PII=1, SA=单址+AA×6>` = `68 17 00 43 05 AA×6 00 AA 2A 05 01 01 43 00 03 00 00 6D 5C 16`、
  内部 `<PIID=0x2C, SA=单址+032408042620>` = `68 17 00 43 05 03 24 08 04 26 20 00 CD 9A 05 01 2C FF 10 04 00 00 C2 8A 16`；
  回归 `test_dl698_upgrade.py`（A10/A11）+ `test_dl698_upgrade_gui.py`（[17]~[20]，含 OAD 互斥与「非阻断」反例）。
- **读版本信息的「展示」两条契约（1.23.85 现场反馈追加）**：
  ① **日志：解析内容写在帧的下面若干行，不贴在帧尾** —— `[RX] <整帧 hex>` 单独一行，下一行
  `  → 版本信息（升级前·内部）读取成功（N 项）`，再往下每字段一行（缩进 4 空格）。理由：日志是 `NoWrap`，
  70 字节响应帧 ≈215 字符会把尾部内容顶到屏幕外（用户原话「还得拉到后面才看得见」）。**不要在帧行尾部再拼解析结果**。
  ② **展示区**：参数栏**之下**新增「版本信息」区，`升级前`/`升级完成后` **并排两栏**（现场要的是前后对比；
  竖排会互相挤进滚动条）——每栏「标题（升级前 · 内部 · 时刻）+ 逐字段行」、只读可复制、`WidgetWidth` 换行；
  每栏 `minimumHeight` 必须 ≥ 7 行行距（`fontMetrics().lineSpacing()*7`，标题 + 6 字段；**不许「还得滚动才看得见」**），
  `maximumHeight` 有上限防挤掉日志区。未读 = `（未读取）`；读失败 = `—— 未读到：<原因>`；
  **`开始升级` 与 `清除` 都重置**（不留上一轮结果误导）。回归段：`test_dl698_upgrade_gui.py` [13] 几何护栏 + [17]/[20]/[21]。
- **版本逐字段解析必须走 `dl_t698_45_data_decode` 的单一来源**（1.23.85 追加）：`VERSION_FIELDS`（表191 六个字段名）+
  `VERSION_FIELD_BYTES=(4,4,6,4,6,8)` + `version_like_members()`（形状：**6×visible-string**）+
  `version_lengths_match()`（长度强自证）+ `decode_version_info()`（日期 `YYMMDD`→`20YY-MM-DD`）；
  `CLASS_ATTR_TEMPLATES[(19, 3)]["fields"]` 引用它。`dl_t698_45_upgrade.version_rows(apdu)` 产出
  `[{"名称","值","原始","长度"}]`：**长度与表191 声明不符时命名照给但必须追加 `⚠ 长度未自证` 行**（写明声明值/实发值，
  不静默也不假装自证）；非结构数据 ⇒ 一行 `数据`（值 + 原始字节）兜底。厂家扩展对象（内部版本 OAD `FF 10 04 00`，
  实机回同形 6 项）与标准对象（`43 00 03 00`）**共用**这条路径 —— 不要在页面或解析器里再写一份字段名/日期规则。
- **发送通道：串口（默认）/ 蓝牙（1.23.85 追加，用户需求）**：蓝牙通道**复用「蓝牙工具」页已建立的连接**
  —— 升级页不建/不断连接，只经 `main_gui._upgrade_bluetooth_source()` 注入的**取值回调**拿 worker
  （蓝牙 worker 是蓝牙页惰性创建的，注入时可能还不存在；不要在升级页缓存连接状态、更不要自建 `BluetoothWorker`）。
  发送走 `_BleSendPort`（把 worker 适配成 `is_open`/`write_raw`，`write_raw` ⇒ `send_data(frame, single_write=True)`
  = **一整帧一次 ATT 写**，超上限由 worker 拒发并报错，绝不静默分包）；**接收走 `notification_received`
  → 本页 `_on_raw_data`**（698 分帧归本页，不依赖蓝牙页的静默切帧），且只在传输中吃通知。
  **每包上限自动算**：`worker.single_write_limit()`（= 特征码免响应写上限 或 `MTU−3`，**不叠**蓝牙页那个 200 字节
  `_max_chunk`；单一实现 `_limit_plan`，蓝牙页 `_chunk_plan` 也用它）→ `dl_t698_45_upgrade.max_block_bytes_for_frame_limit()`
  用**真实组帧**二分反推块长（例：MTU 512 ⇒ 一次写 509 ⇒ 每包 **475**；用户口径「≤480」成立），随后
  `spin_block.setMaximum(cap)` + 夹当前值 + 状态标签写明计算过程（标签 `wordWrap`，窄窗不截断）。
  **幂等重算时机**：通道切换 / 连接变化 / `mtu_updated` / SA 配置变化 —— 上限缓存进 `_bt_cap`，
  `_worker()` 在蓝牙通道下**要求该缓存非 None**（算不出上限就别放行，免得块长超限半途失败）。
  上限算不出（未连接 / `mtu_is_unnegotiated` / 放不下 698 帧头）时**不设人为上限**，禁用「开始升级」并把原因写进标签。
  回归段：`test_dl698_upgrade_gui.py` [23]、`test_bluetooth_worker.py` [8]、`test_dl698_upgrade.py` A13、
  `test_dl698_upgrade_tab_wiring.py` [5]/[5b]。
- **该 tab 标题是「光伏升级」**（1.23.85 改名，索引仍是 `_upgrade_tab_index`、能力仍是 `spec.has_upgrade`）；
  改名后必须同步 `test_dl698_upgrade_tab_wiring.py` 的标题断言与 `test_yw645_gui.py` 的可见性矩阵文案。
- **按钮宽度一律 `gui_utils.fit_btn_width`**（只设下限、不 `setFixedWidth`，陷阱 63）。
- **大文件分包参数必须可配且持久化**：每包字节数 / 超时(ms) / 重试次数（连同 SA、CA、文件信息、校验类型与值）全可编辑，
  落 `app_paths.data_path("dlt698_upgrade_config.json")`（原子写 + 坏文件宽容；**按属性访问** `app_paths.data_path`，
  便于测试沙箱重定向）。`cleanup()` = 停表 + 断串口信号 + 落盘，**不得关闭串口**；主题走 `restyle_for_theme(dark)`，
  在 `_restyle_for_theme` 里带 `getattr(...) is not None` 守卫 + `except RuntimeError: pass`。

- **RX 重同步必须能丢弃「不可能成为帧头」的字节**（1.23.85 独立复核发现）：只跳过「首字节非 `68`/`FE`」不足以防卡死 —— 一次线噪（`FE FE 99 …`，或长度域被噪成「按长度到齐却非 `16H`」）会让缓冲头**永久占位**，此后所有确认都收不到（HOLD 上限 262144B 实际不可达）⇒ 一次噪声 = 整轮失败。正确判据：**只有「当前既无半截帧在等、也切不出整帧」时才丢弃**，丢多少交给 `frame_deframe`（不在页面里另写分帧算术）。回归段：`test_dl698_upgrade_gui.py::test_resync_edges`（含「真半帧一个字节都不许丢」反例）。
- **传输进行中必须冻结会改变计划的输入**（同轮发现）：换升级包 / 改 SA·块大小 / 点「清除」三类操作，要么**拒绝并提示先「中止」**，要么**完整复位状态与按钮门控**。否则轻则 `_on_ack` 抛 `IndexError`（在 Qt 槽里被吞掉 → 状态机静默卡死），重则**静默改发另一个文件的数据**（新文件包数够时顺序继续）。回归段：`test_mid_transfer_controls`。
- 新增的「测试断言」必须自查判别力：**只投「整帧」验证「断信号后不再处理」是恒真的**（整帧会被正常处理掉、缓冲恒为 0），要投一段**半帧**才能区分「断/未断」（1.23.85 实测：把 `_detach` 换 no-op，只投整帧的版本照样绿）。

### 7k. 桌面「粘性入口」：托盘菜单内嵌输入框 / 任务栏缩略图按钮（1.23.85）

> 用户问「能不能像汽水音乐那样在 Win11 任务栏上放可交互控件」。**先记结论**：Win11 的任务栏对第三方是封闭的
> （Win10 的「任务栏自定义工具栏 / deskband」已移除），**任意控件（尤其输入框）不可能放进任务栏那一行**；
> 截图里那种「封面 + 标题 + 播放键」是 **SMTC 系统媒体卡片**（只有媒体会话能占）。可做的受支持挂载点是三条：
> ① 托盘菜单内嵌输入框；② 任务栏**缩略图工具栏按钮**（悬停图标预览里）；③ 屏幕边缘 AppBar 常驻条。

- **托盘菜单内嵌输入框**（`system_integration/sys_tray.py`）：`QWidgetAction` + `setDefaultWidget(输入框 + 「解析」按钮)`；
  回车/点按钮 → `parse_text_requested(str)` 信号（菜单 `hide()` + 输入清空）；**解析路径由主窗口注入**
  （`MainWindow._on_tray_parse_text` → `_parse_text_input`），托盘模块**不 import 解析器**。不受理时
  **状态栏 + 托盘气泡**说明（不静默、不弹模态）。`set_input_enabled(False, tip)` 供解析器不可用时禁用。
- **任务栏缩略图按钮**（`system_integration/taskbar_buttons.py`，纯 ctypes）：`available()` / `set_buttons(win, [(提示, QIcon)])`
  / `clear(win)`，点击经 `WM_COMMAND` → `QAbstractNativeEventFilter` → `clicked(int)` 信号。
  三条**必须照做**（都实测踩过）：
  1. **取接口先试 `IID_ITaskbarList4`，再 3 / 2**：Win11(10.0.26300) 上 `IID_ITaskbarList3` 直接返回
     `E_NOINTERFACE(0x80004002)` 而 `ITaskbarList4` 正常（`HrInit`/`ThumbBarAddButtons`/`SetThumbnailTooltip` 均 `S_OK`）；
     三者的 vtable 槽位对我们要用的方法是**同一个索引**（`HrInit`=3 / `ThumbBarAddButtons`=15 / `ThumbBarUpdateButtons`=16
     / `ThumbBarSetImageList`=17 / `SetThumbnailTooltip`=19），别按名字乱排。
  2. **所有涉及 HANDLE 的 Win32 调用必须显式声明 `argtypes`**：64 位下不声明会被当 C int ⇒
     `DeleteObject(hbm)` 抛 `OverflowError: int too long to convert`（图标转换处实测）。
  3. **`nativeEventFilter` 在 PySide6 返回单个 `bool`**（True = 吞掉）；返回元组会被当 truthy **把所有 WM_COMMAND 都吞掉**。
  另注：`QImage.constBits()` 返回 `memoryview`，`ctypes.memmove` 前要 `.tobytes()`；HICON 由
  32bpp top-down DIB + 全 0 掩码 `CreateIconIndirect` 得到（不引新资源、用 `icons/lucide/*.svg`）。
- **主窗口接线**（`main_gui`）：`showEvent` 里 `QTimer.singleShot(0, self._setup_taskbar_buttons)`（句柄变化才重挂，
  避免重复 `ThumbBarAddButtons` 叠加）；4 个按钮 = 解析剪贴板 / 快捷解析 / 批量解析 / 光伏升级（`TASKBAR_BUTTONS`
  是一份清单，分派在 `_on_taskbar_button`）；`closeEvent` 真实退出路径 `clear()`。
  **按钮只在窗口有任务栏按钮时可见**（`hide()` 到托盘后没有），所以「关到托盘」的老行为不改时它们只在窗口
  显示/最小化期间可用 —— 想常驻要另议。
- 回归：`test/test_tray_taskbar_entries.py`（27 项：托盘提交/清空/禁用、HICON 转换、`set_buttons`/`clear` 降级、
  合成 `WM_COMMAND` 的命中/不吞别的消息、`_parse_text_input` 两条路径与不受理提示、4 个按钮分派）。
  真机冒烟（非 offscreen）：`_setup_taskbar_buttons()` → True、按钮 id `0x7700..0x7703`、`PostMessage(WM_COMMAND)`
  能触发 `clicked`；「光伏升级」按钮 → 协议 8 + tab 文案「光伏升级」。

### 8. Qt 陷阱（本项目实测）
- **offscreen 无字体**：`QT_QPA_PLATFORM=offscreen` 下 `QFontDatabase: Cannot find font directory ...`，绘制出的文字是豆腐块 → 断言只能查尺寸/颜色/像素多样性；**要目视核对文字排版必须用默认平台**（`QApplication([])` 不设 offscreen + `widget.grab()` / `QImage.save()`，不需要窗口真的可见）。
- **`bytes(image.constBits())` 必须持有 QImage 引用**：`bytes(canvas.render_image(w, h).constBits())`（临时对象上取 buffer）会 **access violation（0xC0000005）**；先 `img = ...` 再 `bytes(img.constBits())`。
- **`QSplitter` 显隐子控件不自动让空间**：新显示的表格会被分到 0 高度 → 显隐后要显式重分配 `setSizes()`（并考虑 `sum(sizes)` 与各子控件 `minimumHeight()`，避免算出负高度）；**未 `show()` 时 `sizes()` 不反映真实布局**，不能用它判定溢出。
- **`QTableWidget` 子控件的 `isVisible()` 在父窗口隐藏时为 False**：测试断言「表格是否显示」用 `isHidden()`。
- **测试点按钮要用真实信号**：测量类操作至少各覆盖一次 `btn.click()`（+`processEvents()`），只直调 `_on_xxx()` 私有方法会漏掉 `.clicked.connect` 漏挂这类最易回归的缺陷。同样，用鼠标测交互时**每次点击前重新取 `plot_rect()`**——表格显隐会改变画布高度，复用旧矩形会以「布局」而非「逻辑」原因失败。

### 8. 关键陷阱（承接上文）

- 横轴首/末标签若按居中排版会越出画布或压住纵轴刻度 → 首标签左对齐、末标签右对齐，其余居中。
- 自动适配模式的等分刻度会出现 `47.3275` 这类噪声 → 按分格步长定小数位（`auto_tick_decimals`）后再格式化。
- 状态行文字较长时在窄窗口会被挤压 → 保留 tooltip 全文，不要为了塞下而删信息。


---

## Scenario: Reflex Web 版与桌面版的解析能力对齐（双实现收口）

### 1. Scope / Trigger
Web 版（`reflex_web/reflex_web/`）与 PySide6 版（`main_gui.py`）**共享 parser/validator，但预处理/帧提取/摘要/DLT645 转表/字段层级/查询数据源各写一份**。任何跨端行为改动、或「Web 上解析结果与桌面不一致」的报障，都落在这个场景。

### 2. 契约（已落地 + 待收口）
- **解析内核**：`parser_*.py` / `validator/*` 是唯一实现，两端调用；**不要在 Web 侧再包一层同义实现**。
- **判据进纯函数**：`web_utils.py`（无 Qt / 无 reflex）承载 `hex_to_bytes_strict` / `strip_frame_bytes` / `batch_frame_outcome` / `parse_kwargs_for` / `clean_hex_input` / `strip_*` / `extract_*` / 摘要；`reflex_web.py` 的 State 只做「取状态 → 调纯函数 → 赋值前端字段」。理由：Reflex `State` 不能随便实例化，逻辑留在 State 就等于不可测。测试可用 `State(_reflex_internal_init=True)` 拿真实实例，并可用 `async for _ in st.parse_batch()` 驱动批量链路（见 `test/test_web_parse_fixes.py` §11/§12）。
- **失败判定唯一口径**：结果表中**存在以 `❌` 开头的行**（解析器会把失败行写在表中途，实测协议9 `mac_only` 短 MAC 帧：`csg_new_gen_parser.py:843` 先写「解析模式」行，`_parse_mac_frame` 再追加 ❌）→ 失败（类型列「解析失败」、摘要取 ❌ 行说明）；**空表 = 失败**。两端一致（Web `batch_frame_outcome`，桌面 `main_gui.parse_batch` + `_get_frame_type_name`）。
- **输入清洗唯一口径**：奇数长度/空输入**报错**（`输入长度为奇数，十六进制字符串必须是偶数长度！`），禁止 `[:-1]` 静默截断。
- **解析级别参数**：一律经 `parse_kwargs_for(protocol, parse_level, pb_frame_type, gw_frame_type, channel)`；协议10/11 仅 `pb_only` 下发 `frame_type`（不下发时 `gw_new_gen_parser` 落「未知(None)」、`hdc10_parser` 恒 SOF）。
- **ED..EE 监控包装格式判别单源**：`csg_new_gen_parser.detect_ed_wrapper` + `_parse_ed_wrapper`（plc2 9B / gx 8B 两套偏移），桌面 `main_gui._detect_ed_wrapper` 只委托（手动下拉值作 fallback）；摘要侧按「字段名含 `监控包装头`」判定，不用 `PLC2.0` 字样（否则 gx 帧掉到兜底分支）。
- **协议能力元数据**：桌面查 `protocol_registry.ProtocolSpec`；Web 侧尚未接入（子任务 `09-15-web-shared-parse-core`），现阶段改动必须**同时改两侧**。

### 3. 已知漂移清单（改这些逻辑时必须对拍）
前缀剥离（`strip_gw_new_gen_prefix` 缺 `fc_payload_data := '…'` 跨行状态机、缺 EDA5）、帧提取返回契约（纯字符串 vs `(hex, ed_type, line_no)`）、摘要分派（协议10 曾错用协议9 摘要、`get_hdc10_summary` 的 `业务类型ID` 键名与解析器字段不匹配恒不命中、缺测试模式片段）、查询数据源（协议10 曾抄协议9 表；南网 AFN 曾算成 `di3 & 0x0F`；698 属性/方法曾恒为 `-`）。

### 4. Tests Required
- Web 侧断言走 `test/test_web_parse_fixes.py` 的范式：纯函数直测 + parser 端到端 + `State(_reflex_internal_init=True)` 真实实例（校验分派/剔除重算/参数下发都能这样测，无需浏览器）。
- **断言必须能在实现回退时变红**：写「修复前后差异」的判据（例：不下发 `frame_type` 时断言出现 `未知(None)`，下发后断言 `仅PB - SOF帧`），不要只断言「有结果/不抛异常」。
- 桌面回归网（ED 相关必跑）：`test_ed_gx_wrapper.py` / `test_ed_fallback_fix.py` / `test_csg_summary.py` / `test_csg_batch_prefix.py` / `test_csg_sequence_model.py` / `test_gw_monitor_summary.py` / `test_batch_src_line_jump.py`。

### 5. Web 版复用桌面纯逻辑层（本项目范式，1.23.12 起）

**什么时候适用**：桌面某个功能是「纯逻辑 + Qt 绘制」两层结构（如 `spectrum_widget.py`：前 ~950 行只依赖 `math/bisect/re`，后 ~1400 行是 QPainter/QWidget）。
**做法**：
1. Web 侧**直接 `import` 桌面模块**，只调用其纯逻辑 API（`spectrum_widget` 的 Qt 层被 `try: from PySide6 … except ImportError` 守护，Web 进程天然走 except 分支 → 纯逻辑可用）；
2. 新增一个**纯** Web 模块承载「绘制层专有逻辑」（如 `reflex_web/spectrum_web.py` 的 SVG 坐标换算），不改桌面行为；
3. State 只做「取输入 → 调纯函数 → 组装前端渲染模型」。

**收益实测**：频谱图移植零算法重写——参数校验、trace 日志清洗、刻度、标记吸附、峰值搜索（O(n) 单调栈）、积分带宽（含移位求和/RBW 归一化口径）全部复用，桌面既有 225 项纯逻辑测试直接成为 Web 回归网。

**Reflex/SVG 坑（实测）**：
- `el` 没有 `polyline`（只有 `path`/`polygon`），且 `polygon` 会自动闭合首尾（多一条回边）→ 迹线用 `rx.el.path(d="M…L…")`；
- SVG 数值属性只接受 `str | int`：`rect.x`/`circle.r`/`stroke_width`/`font_size` 给 float 会 `TypeError`；几何层统一输出**字符串**（`f"{v:.2f}"`），常量用 int；
- `rx.el.text(children=...)` 与 `_create()` 的 children 参数冲突 → 文本内容用**第一个位置参数**传，且必须写在关键字参数之前；
- 条件样式用 `class_name=rx.cond(...)`（`style=rx.cond({...})` 实测不落 DOM，见下条）；
- 鼠标坐标拿不到（Reflex 不暴露 DOM 事件）→ 首版把绘图区切成 N 个透明带（`id="sp-band-i"`）各带 `on_click=State.xxx(i)`，点击按带中心频率吸附到最近数据点；需要更高精度或悬停时再上 JS 桥。

### 6. Web 主题契约（1.23.12 起，改任何样式前先读）

- **单一来源**：颜色只在 `reflex_web/reflex_web/theme_web.py` 的 `TOKENS_LIGHT`/`TOKENS_DARK` 里定义；
  `GLOBAL_CSS`、组件、SVG 一律引用 `var(--token)`。**禁止在组件里写裸 hex**（`test/test_web_theme.py` 有一条守卫断言）。
- **浅色 = 现状值**：`TOKENS_LIGHT` 必须等于改造前的实际硬编码值（测试逐 token 断言）→ 新增主题不会悄悄改掉默认观感。
- **模式**：由 `html.light` / `html.dark` 类驱动（Reflex/Radix 约定）。我们自己的模式选择写 `localStorage['nw-theme']` 并**同时**镜像 provider 读取的 `theme` 键；挂载后 Provider 可能重写根节点类，故 `theme_web.apply_mode_js` 里装了一个 class 观察器把最终态纠回（幂等，不会自激）。
- **强调色**：Radix 组件走 `rx.theme(accent_color=ThemeState.accent, …)`；自定义 CSS 走页面根容器上的 `.nw-accent-<id>` 覆盖块。**主题 class 必须挂在包含 header 的根容器上**——header 在 `.app-container` 之外，挂在里层会导致顶栏不跟强调色。
- **每个页面都要挂样式**：`theme_style()`（SEARCHABLE_CSS + GLOBAL_CSS + 主题 token）必须在 `index` / `share_page` / `feedback_page` / `feedback_admin_page` 的根容器上都渲染；独立页面漏挂会让 `var(--accent)` 等解析失败（顶栏背景透明、白字不可见——1.23.12 真实踩过）。
- **SVG 上色**：`fill/stroke="var(--token)"`（Reflex 会落到 CSS）；标记配色用 `var(--sp-mN)`（由 `spectrum_widget.MARKER_COLORS_*` 生成 CSS 变量，图与标记表同源）。
- **Reflex 坑**：`rx.el.text(children=…)` 与 `_create()` 冲突（内容用位置参数，且在关键字参数之前）；SVG 数值属性只收 `str|int`。

### 7. 方法论陷阱（本次实测）
- **`style=rx.cond(cond, {...}, {})` 在本项目不落到 DOM**：批量摘要行原用该写法做选中高亮，实测所有行的 `style` 属性为 `null`（选中行也不高亮）。改用 `class_name=rx.cond(cond, "batch-row-selected", "")` + `GLOBAL_CSS` 里一条 `.batch-row-selected{border:2px solid #2563eb!important}` 即生效（`class_name=rx.cond` 在 tab 高亮等处以证实可用）。凡「条件样式」优先 class，不要用 `style` 传 dict 条件。
- **Reflex State 字段即 WebSocket 载荷**：`batch_results` 这类"结果集字段"一旦到万级就会整批序列化下发（本项目实测 24MB 告警）。**大结果集必须只把当前页放进 State**（全量放 `_private` 字段），分页数学走纯函数 `web_utils.paginate`。
- **推断型缺陷结论必须先用真实调用路径复现再改代码**：只读审计曾断言「Web 剔除不幂等（连点两次 = 二次裁剪）」，依据仅是「没有缓存」；实测发现 Web 每次都从**未被回写的** `frame_hex` 重算，本就幂等——按该结论加缓存后第二次解析反而拿到**未剔除**的原始字节（真回归），已撤销。凡结论带「因此/必然/会」的推断，先写 3 行脚本跑一遍。
- **子代理审计结论要抽检**：本次 4 份审计里 1 条误判、1 条口径偏差（桌面失败判定比 Web 更窄，两侧都不完备），其余成立。抽样复现成本远低于改错成本。
- **浏览器里验证 Web 交互时按 placeholder 定位控件**：多个 tab 面板同时挂载，`querySelectorAll("textarea")[0/1]` 会选中别的面板的输入框（本次两次踩到：一次把工具输入填进了批量框，一次把 250 行日志填成了空行）；`tab.run(fn, {args:[...]})` 的参数要放进 `args`，否则回调收到 `undefined`。

---

## Scenario: Web 产品首页（落地页）与路由搬迁（1.23.14 起）

> 源任务 `09-15-web-landing-page`。参考实现：`reflex_web/reflex_web/landing_web.py`（纯展示）+ `reflex_web/reflex_web/reflex_web.py`（State 注入 + 路由），测试 `test/test_web_landing.py`（100 项）。

### 1. Scope / Trigger

Web 版需要一条**对外介绍型页面**（宣传桌面客户端 + 下载/在线入口），并把干活用的工具页从 `/` 让位。触发条件：新增/搬迁顶层路由、页面里出现图片等**后端静态资源**、或新增站内链接。跨层契约（路由 ↔ 导航 ↔ 打包 ↔ 测试）必须写清，否则出现死链或 dev/prod 行为分叉。

### 2. Signatures

```python
# reflex_web/reflex_web/landing_web.py（纯展示层：不 import reflex_web）
INTERNAL_LINKS = {"home": "/", "tool": "/app", "feedback": "/feedback", "share": "/share"}
SECTION_IDS = ("features", "protocols", "quickstart", "download")
ANCHORS = {k: f"#{k}" for k in SECTION_IDS}
ALLOWED_HREFS = set(INTERNAL_LINKS.values()) | set(ANCHORS.values())
PROTOCOLS: list[dict[str, str]]      # 12 项 index/name/standard/endian/check
FEATURES: list[dict[str, str]]       # 12 项 icon/title/desc
CLI_ACTIONS: list[dict[str, str]]    # 4 项 label/cmd（cmd 里的参数名对 main_gui 源码对拍）
SYSTEM_INTEGRATIONS: list[dict[str, str]]
HERO_STATS: list[dict[str, str]]     # _key == "protocols" 的项取 len(PROTOCOLS)
LANDING_CSS: str

def landing_page(*, version="", version_date="", exe_name="", exe_size_mb="",
                 exe_available=False, image_src="", image_available=False,
                 on_download=None, theme_controls=None) -> rx.Component: ...

# reflex_web/reflex_web/reflex_web.py（组合层）
def tool_page() -> rx.Component: ...        # 原 index()，挂 /app
def landing_page() -> rx.Component: ...     # 挂 /，注入 State + ThemeState
def theme_controls_compact() -> rx.Component: ...   # 工具页与首页共用

app.add_page(landing_page, route="/", on_load=[ThemeState.theme_boot, State.load_download_info])
app.add_page(tool_page, route="/app", on_load=ThemeState.theme_boot)
```

### 3. Contracts

- **路由语义**：`/` = 产品首页；`/app` = 在线工具；`/share` `/feedback` `/feedback-admin` 不变。**回介绍页用 `/`，回工具用 `/app`**；登录弹窗与反馈列表 Tab 只挂在工具页 → 独立页的「管理员登录」必须跳 `/app`。
- **依赖方向**：`landing_web.py` **不得 import `reflex_web`**（与 `web_utils`/`theme_web` 同向）；运行时值一律参数注入。收益：整页可脱离 `State` 与浏览器构建并断言。
- **静态分支模式**：形参既可能是编译期字面量（纯逻辑测试）也可能是 `rx.Var`（生产）。需要分支时走
  `if isinstance(v, bool): 取 Python 分支 else: rx.cond(...)`（`_either()` 封装）——既少一层运行期 cond，又让「缺图降级」这类行为能被**字符串断言**验证（`rx.cond` 会把两个分支都编进 JSX）。
- **testid 契约**：`landing-root / nav-brand / nav-online / theme-preset / theme-mode / hero-title / hero-download / hero-online / hero-shot | hero-shot-placeholder（互斥）/ feature-grid / protocol-table / quickstart-cli / cta-download / cta-online / landing-footer`。
- **首页数据源**（`reflex_web/downloads/`，由 `State.load_download_info` 读）：`version.json`（版本号/日期/下载地址）、`*.exe`（`stat().st_size`→`download_exe_size_mb`）、`client_screenshot.png`（缺失时降级占位卡）。
- **主题**：首页复用 `theme_style()` + `ThemeState.root_class` + `rx.theme(appearance="inherit", …)`；顶栏控件复用 `theme_controls_compact()`（不要复制第二份）。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| 无 exe（`download_exe_available=False`） | 下载按钮 `disabled` 且文案改「客户端 exe 未就绪」（**不隐藏**，避免用户找不到入口） |
| 无截图（`download_image_available=False`） | 渲染 `hero-shot-placeholder`，**不得**出现 `src=""` 的 `<img>` |
| `version.json` 缺失/字段空 | 徽章退回平台文案（`Windows 10 / 11 桌面客户端`），体积显示「体积待统计」 |
| `<900px` 视口 | Hero/快速上手单列、锚点导航隐藏、**顶栏允许换行**（不换行会横向溢出：实测 420px 下 `.landing-nav-actions` 宽 389px 而父级 `overflow: visible`，页面 `scrollWidth` 484 > 420） |
| 深色 + 浅色强调色（`ACCENT_OVERRIDES_DARK`） | 强调色表面上的文字改 `var(--bg)`（`html.dark .landing-btn-primary / .landing-cta-inner / …`）——否则白字落在浅底上对比度不足 |
| 站内链接不在 `ALLOWED_HREFS` | `test/test_web_landing.py` 死链守卫变红 |

### 5. Good/Base/Bad Cases

- **Good**：`/` 渲染落地页（12 协议行 + 12 功能卡 + Hero 截图 `naturalWidth>0` + 零 console error/4xx），点 `nav-online` 落到 `/app` 且单帧解析出结果，点工具页 `nav-brand` 回 `/`。
- **Base**：`downloads/` 缺 exe/截图 → 页面仍完整，按钮禁用、截图占位，无破图。
- **Bad**：
  - 用相对 URL 引后端静态资源（`<img src="/api/download/x.png">`）→ **dev 下必破图**（见 §7 陷阱）。
  - 只改 `add_page(route=…)` 不改导航 href → 死链（老 `/` 语义已变）。
  - 在 `landing_web.py` 里 `import reflex_web` 取 `State` → 循环导入。

### 6. Tests Required

`test/test_web_landing.py`（脚本式 `check()` 计数，**不启服务**）断言点：

1. 内容不变式：12 协议（`index` 连续唯一）、12 功能卡（title 唯一/icon 非空）、4 CLI、≥5 系统集成、≥3 统计条。
2. **防漂移对拍**：`len(PROTOCOLS) == protocol_registry.protocol_count()`，且**逐行**「`name` 首个关键词 ∈ 同索引的 `combo_labels()[i]`」（本次即靠它抓出协议10 少写「通信」二字）；`CLI_ACTIONS` 里的 `--xxx` 必须在 `main_gui.py` 源码中出现。
3. 组件树：无参 + 带假数据都能构建；全部 testid 存在；12 协议名/12 功能卡标题出现在（反转义后的）渲染串里。
4. 缺图降级互斥（`image_available` 真/假两个方向都断言）。
5. 死链守卫：扫 `to:"/…"` **且断言集合非空**（正则失效不得变成假绿）。
6. 路由搬迁：`app._unevaluated_pages` 含 `/`（键为 `index`）与 `/app`；`index` 函数名已不存在；`tool_page()` 仍含 9 个 tab testid。

浏览器验收（人工/自动化）：浅色 + 深色 + 至少 1 个强调色截图；360/420/768/1024/1440/1920 六档 `scrollWidth == innerWidth`；`nav-online`/`hero-online` → `/app`；`/app` 单帧解析实测；「客户端下载」Tab 截图仍显示（防图片通道回归）。

### 7. Wrong vs Correct

#### Wrong
```python
# ① 首页 Hero 用相对 URL 引后端静态资源（dev 必破图：:3000 不代理 /api/*）
rx.el.img(src="/api/download/client_screenshot.png")
# ② 只改路由不改导航：老 / 语义已变，独立页的「返回主页」href="/" 变成"回首页"
app.add_page(tool_page, route="/app")          # href="/" 未同步
# ③ 在纯展示模块里反向 import 组合层
from .reflex_web import State                  # 循环导入
```

#### Correct
```python
# ① 用已验证的图片通道（base64 data URL，dev/prod 都成立）
rx.el.img(src=State.download_image_data_url)
# ② 链接单一来源 + 语义化改指
INTERNAL_LINKS = {"home": "/", "tool": "/app"}
rx.el.a("在线工具", href=INTERNAL_LINKS["tool"])   # 独立页/顶栏
# ③ 依赖单向：展示层只收参数
def landing_page(*, version: Any = "", exe_available: Any = False, ...) -> rx.Component: ...
```

> **Warning（dev/prod 分叉）**：`reflex run --env dev` 时前端(:3000)与后端(:8000)是**跨源绝对地址**通信，**没有任何代理规则**——`:3000/api/*`、`/download/*`、`/fbimg/*`、`/ping` 全部返回 `200 + text/html`（SPA 兜底），只有直连 `:8000` 才是真资源（`.web/env.json` 的 `EVENT: ws://localhost:8000/_event` 是判据）。**Web 页面里不要用相对 URL 引用后端静态资源**；prod（`run_app.py` 单端口挂载）才同源可用。相关遗留缺陷见 `AGENTS.md §8` 陷阱 35。


---

## Scenario: 68 家族前导 FEH 唤醒字节（协议8 / 协议6，1.23.76 起）

> 源自任务 `10-13-wakeup-fe-prefix`（用户报障：蓝牙工具收到 `FE FE FE FE 68 21 00 C3 …` 的 39 字节 698 回包，报「起始字符错误: 0xFE」，一字段都解不出）。适用于「输入字节流里含有**不属于帧内容**的链路层包裹」的任何协议改动。

### 1. Scope / Trigger

- Trigger：**链路层契约变化**（帧首允许前导码）+ **跨层数据变形**（同一份字节偏移在「剥离前 / 剥离后」两套坐标系间位移）+ 规范依据（DL/T 698.45-2017 §6.3.1 b)「在有效数据帧前加 4 个 FEH 作为前导码」；DL/T 645-2007 §5.3.1「建议先发送 4 个字节 FEH，以唤醒接收方」）。
- 不适用：协议 0/7/9/10/11/12/13（无规范依据，行为必须保持不变）。

### 2. Signatures

```python
# wakeup_prefix.py —— 全仓唯一判定实现（纯逻辑，无 Qt，不 import 任何 parser）
WAKEUP_BYTE = 0xFE
WAKEUP_FIELD_NAME = "唤醒前导字节"
def wakeup_prefix_len(data: bytes) -> int                      # 帧首连续 0xFE 个数
def strip_wakeup_prefix(data: bytes) -> tuple[bytes, int]      # 无前导时**恒等返回**
def wakeup_display(skipped: int) -> str                        # "FE FE FE FE"
def make_wakeup_row(skipped: int, note: str) -> tuple          # (行名, 原始值, "-", note, 0, n-1)
def shift_row_offsets(rows: list, delta: int) -> list          # 仅位移「第5、6列同时为 int」的行

# 协议8：DLT69845Parser.parse → 结果新增 result["唤醒前导"] = {字节数, 原始值, 说明}
# 协议6：DLT645Parser.parse  → 结果新增 result["wakeup_len"] = int
# 两者 parse_to_table 首行 = make_wakeup_row(...)（6 元组，偏移 0..skip-1）
```

### 3. Contracts

| 项 | 契约 |
|---|---|
| 剥离口径 | 只剥**帧首连续** `0xFE`（0~N 个，不假定恰好 4 个）；**帧中间的 FE 不动**；68 家族首字节恒 `68` ⇒ 零误伤 |
| `原始数据` / `raw_hex` | **必须保留用户原始输入（含 FE）**，便于追溯与高亮 |
| 表格偏移坐标系 | = **用户输入**（含 FE）：解析器内部按剥离后帧计算，表格构建方整体 `+skip`（`起始字符` = skip~skip） |
| 校验器 | 与解析**同预处理**：先剥离再走全部检查；`skip > 0` 时首项追加 PASS `前导唤醒字节`（否则出现「解析成功但校验报起始符错误」） |
| 协议6 细节 | `check_structure` / `check_frame` / `calc_checksum` **都要**按剥离后帧判定（否则 CS 把前导算进和里）；`DLT645GuiParser.frame_len` 必须用剥离后长度（否则「校验和 / 帧结束符」偏移越界）；`fields` 列表**不加**前导行（形状守卫依赖） |
| 不动的地方 | 批量/Web 帧提取（本就从 `68H` 起同步）、串口/蓝牙分帧策略表（带 FE 走既有时间聚合，整段交链路层兜住） |

### 4. Validation & Error Matrix

| 输入 | 期望 |
|---|---|
| `FE×4 + 合法帧` | 解析成功、HCS/FCS 通过、表格首行为前导行、偏移整体 +4、校验全 PASS |
| `FE×1 / ×2 / ×8 + 合法帧` | 同上（起止偏移 = `(0, k-1)`） |
| 无 FE 合法帧 | **逐行逐字节与改动前相同**（硬约束） |
| 全 `FE` | 剥离后为空 → 失败「帧长度不足」（不臆造、不空白） |
| `FE…` 后非 `68` | 失败（起始字符错误），前导行偏移仍正确 |
| 带 FE 但 CS 错 | 解析继续并给出「⚠ 校验和错误 / 正确值」；校验器 FAIL（**前导不放宽任何判据**） |

### 5. Good / Base / Bad Cases

- **Good**：链路层剥离 + 表格位移 + 校验器剥离三处同时落地，且判定只有 `wakeup_prefix.py` 一份。
- **Base**：无前导帧走恒等路径 —— 既有测试（`test_dlt645_tolerant_parse.py` 13 行基线、`test_dlt645_table_offsets.py` 偏移矩阵）继续作为零回归锚点。
- **Bad**：在调用点各自 `strip()`（5~6 处，且未来调用方会漏）；只改解析不改表格（高亮落到错误字节，比解析失败更隐蔽）；只改解析不改校验器（自相矛盾）。

### 6. Tests Required

`test/test_wakeup_fe_prefix.py`（73 项，`release_check.py:CORE_TESTS`），断言点：

1. `wakeup_prefix` 纯逻辑：0/1/2/4/8 前缀、帧内 FE 不动、空输入、全 FE、`make_wakeup_row` 形状、`shift_row_offsets` 跳过 `None` 与 `delta=0` 恒等
2. 协议8：报障帧 golden（状态/HCS/FCS/OAD/数据）+ 首行与 `(4,4)/(16,17)/(36,37)/(38,38)` 偏移 + 无 FE 冻结锚点（行数、关键行值）+ 局部/全 FE/非 68 降级
3. 协议6：`valid`/CS/`wakeup_len`/`raw_hex` + 表格逐行 `+4` + 13 行基线不变 + 虚拟表从站不受影响
4. 两个校验器：带 FE 全 PASS（含前导项）、无 FE 项不变、坏 CS 仍 FAIL
5. 护栏：协议 0/7/9/10/11/12/13 对带 FE 输入**不产生前导行且行为不变**
6. 批量/Web：`batch_core._extract_69845_frames` 与 `web_utils.extract_69845_frames` 结果一致
7. offscreen GUI：单帧页粘贴报障帧 → 首行为前导行；`MainWindow._serial_parse_provider`（串口/蓝牙共用）返回非失败表；`verify_single` 通过
8. 反例自检 + 单一来源源码守卫（按 `import` 锚定，文档提及不算）

**变异反证（必须实测变红后还原，本任务已做）**：① `wakeup_prefix_len` 恒返回 0 → 4 项红；② 表格不位移 → 4 项红；③ 校验器不剥离 → 2 项红；④ 协议6 `parse` 不剥离 → 6 项红。

### 7. Wrong vs Correct

#### Wrong
```python
# ① 各调用点各自剥离（parse_single / _serial_parse_provider / 快捷小窗 / Web / 校验…必漏一处）
frame = frame_bytes.lstrip(b"\xfe")          # 连帧中间的 FE 一起剥，且 5~6 处复制
# ② 只改解析不改表格：高亮按「剥离后」坐标系，点「起始字符」落到第 0 字节
table_data = self.parse(frame)["..."].build()  # 偏移未 +skip
# ③ 只改解析不改校验器：用户看到「解析成功」+「校验：起始字符错误」
checks.append(self._check_start_char(frame_bytes, 0x68, 0))   # frame_bytes 仍含 FE
```

#### Correct
```python
# ① 链路层唯一判定（wakeup_prefix.py），解析器入口就地重绑，下游零改动
frame_bytes, skipped = strip_wakeup_prefix(frame_bytes)
# ② 表格层用同一位移函数（协议8 与协议6 共用，禁止各写一份）
table_data = shift_row_offsets(table_data, skip)
table_data.insert(0, make_wakeup_row(skip, "…非帧内容，解析已跳过"))
# ③ 校验器同一判定；HCS/FCS 交给已容忍的解析器（传原始字节，不复制剥离逻辑）
frame, skip = strip_wakeup_prefix(frame_bytes)
```
