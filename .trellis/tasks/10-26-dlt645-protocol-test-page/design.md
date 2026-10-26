# 设计：645 协议测试页

> PRD 见 `prd.md`。核心事实：**645 的帧封装/DI 编码/响应解析都已存在**（`dlt645_frame_gen` 是唯一封装，
> `dlt645_frame_schema` 是字段与命令 schema，`DLT645Parser` 是唯一解析），本任务只补
> 「分类库 + 响应判定 + 页面」，**不新增任何地址/DI/校验算法**。

## 1. 边界与文件

| 文件 | 角色 | 动作 |
|---|---|---|
| `test_page_render.py` | 四列文本渲染（CJK 宽度/截断/`format_table_rows`） | **新增**（698 与 645 共用一份） |
| `dlt698_test_core.py` | 698 纯逻辑 | 仅把 4 个渲染函数改为从共享模块导入（输出逐字不变，`_display_width` 等名字保留） |
| `dlt645_test_core.py` | 645 纯逻辑（分类库/命令库/组帧/判定） | **新增** |
| `dlt645_test_widget.py` | 645 页面（Qt） | **新增** |
| `protocol_registry.py` | 能力位 | `+ has_dlt645_test` / `protocols_with_dlt645_test()` |
| `main_gui.py` | 接线 | 第二套 placeholder/index/ensure/显隐/主题/cleanup/single-parse 注入 |
| `test/test_dlt645_testbench.py` | 核心 + offscreen GUI | **新增** |
| `test/test_dlt645_test_tab_wiring.py` | 真实 MainWindow 接线 | **新增** |
| `release_check.py` | 门禁 | +2 行 |

不改：`dlt645_frame_gen.py` / `dlt645_frame_schema.py` / `dlt645_di.json` / `dlt645_pv_ext.py` /
`DLT645Parser` / Web / 698 页面行为。

## 2. `dlt645_test_core.py` 契约

```python
# 分类库（数据全部来自 merge_pv_di_map，不手写 DI 名称）
@dataclass(frozen=True)
class DiItem:   di: str; name: str; unit: str; data_type: str; length: int; pv: bool
@dataclass(frozen=True)
class SubGroup: name: str; items: Tuple[DiItem, ...]
@dataclass(frozen=True)
class Category: name: str; subgroups: Tuple[SubGroup, ...]
def catalog() -> Tuple[Category, ...]
def item_count() -> int
def find_di(di: str) -> Optional[DiItem]
def filter_items(keyword: str) -> ...        # 名称 / DI 十六进制

# 命令库（来自 DLT645_CMD_SCHEMA 的 REQ 项；字段原样透传）
@dataclass(frozen=True)
class Command: func: int; name: str; hint: str; fields: Tuple[dict, ...]; addr_default: str
@dataclass(frozen=True)
class CommandGroup: name: str; commands: Tuple[Command, ...]
def command_groups() -> Tuple[CommandGroup, ...]

# 组帧（一律走 DLT645FrameGenerator；禁止手拼 68…16）
def build_read(di, addr="000000000000") -> bytes
def build_read_next(di, addr, extra=b"") -> bytes
def build_write(di, addr, field_values) -> bytes
def build_command(func, addr, field_values) -> bytes
def quick_read_address() -> bytes                  # 13H + AA×6 + L=00
def quick_write_address(new_addr) -> bytes         # 15H + AA×6 + 新地址(6B)
def build_broadcast_time(when: datetime|None) -> bytes   # 08H + 99×6 + ss mm hh DD MM YY
def command_effective_addr(cmd: Command, page_addr: str) -> str   # addr_default 非 0 → 用它

# 响应
def parse_table(frame) -> list                     # protocol_registry.DLT645GuiParser
def detail_lines(frame, title="帧结构") -> List[str]
def evaluate_response(frame, expect: dict) -> dict
def extract_address(frame) -> str                  # 13H 应答 / 帧地址域
def format_hex(data, limit=0) -> str
def parse_hex(text) -> bytes
```

### 2.1 分类规则（实测 DI 分布驱动，不是猜）

- 顶层按 DI3（DI 字符串前两位）——名称表：
  `00 电能量`、`01 最大需量`、`02 电压/电流`、`03 功率与谐波`、`04 参变量`、`05 结算日电能`、
  `06 记录`、`07 冻结次数`、`FF LME 自定义`；`DI2 == "E6"` 的一律抽到独立顶层 **光伏扩展**
  （子类按 DI3：`02` 变量 / `04` 参数 / `03` 事件）；其余未知 DI3 归「其他（NNH）」。
- 二级按 DI2，名称取该组首条目的语义（若已知表内映射则用映射：如 `00` 下 `01 正向有功`、
  `02 反向有功`、`60 正向有功（精确）`…）；`05`（508 条 = 254 个结算日 × 2）按
  **20 个结算日一桶**（`结算日 1~20` …）避免 254 个子节点。
- 叶子 = 一条 DI；`pv=True` 表示可用 `build_di_fields` 生成结构化写入字段。
- 排序：顶层按固定顺序；子类按 DI2 数值；叶子按 DI 字典序。**同一 DI 只出现一次**
  （有测试断言 `len(set(all di)) == sum`）。

### 2.2 组帧

- 所有帧 = `DLT645FrameGenerator().generate_frame((REQ, func), fv, addr)`；
  `fv` 的键必须与 schema 字段名**逐字一致**（`数据标识 DI` / `写入数据` / `密码权限 PA` …）。
- 读数据 `fv={"数据标识 DI": di}`；写数据 `fv=公共参数 + build_di_fields 的字段`；
  特殊命令 `fv=命令字段`；地址取 `command_effective_addr`（13H/08H/15H 用 schema 默认 AA/99）。
- **不提供 `scramble=False`**（UI 不暴露），不手写 CS。

### 2.3 `evaluate_response`（不冒充成功）

```python
expect = {"func": 0x11, "di": "02010100", "kind": "read"}   # kind: read/write/command/address
```

判定顺序（任一不满足即 `status="失败"` + 可读原因，但**仍返回 lines** 供日志）：
1. `DLT645Parser.parse` 结构/校验：`checksum_valid` False → 失败（帧内/应为 0x..）；
2. 控制码 D7=0 → 「不是从站应答」；
3. 功能码不符 → 「应答功能码 0xNN，期望 0xNN」；
4. D6=1（异常应答）→ 失败 + `decode_err(data)` 位解释；
5. `kind=="address"` → 取 `address_in_data`（缺则失败）；`kind=="write"` → 校验 DI 回显；
   `kind=="read"` → 校验 DI 回显 + `decode_value(data[4:], data_type, unit)` 得值文本；
6. `no_reply`（08H 广播校时）→ 由页面直接记「已发送（无需应答）」，不走超时判失败。

返回：`{status, code, summary, lines, address, di, value_text}`。

## 3. `dlt645_test_widget.py`

```
root(V)
├─ 设备操作（QGroupBox，两行）
│   行1：表地址[____] [读地址]    写入地址[____] [写入地址]   [广播校时]
│   行2：●串口状态   读取超时[__]ms  □循环发送  [发送] [停止]  收发计数
├─ QSplitter(H)
│   ├─ 左：公共参数（PA / P0P1P2 / C0~C3 / 提示）
│   ├─ 中：QTabWidget(读数据 / 写数据 / 特殊命令)
│   │     每页 = 筛选[____] + QTreeWidget（叶子 checkable）+ 当前项（QGroupBox）+ 帧预览
│   └─ 右：收发日志（QPlainTextEdit + 主题调色板）
└─ 底部 QTabWidget：信息表（7 列）/ 报文表（5 列，双击 → frame_to_single_parse）
```

- **发送队列**：`_build_entries()` 取勾选叶子（无勾选用当前叶子）→ 每条 `frame + expect`；
  `_send_next()` 发一条 → 启动 `_reply_timer` → 收到匹配帧（`_on_frame`）即判、记录、发下一条；
  超时 → 记录「超时」→ 下一条；`停止` 清队列并复位按钮；`循环发送` 在队列空后重建一轮。
- **收帧**：`_rx_buf` + `frame_deframe.frame_length_for("dlt645", buf)` + 末字节 `0x16` 自证；
  切不出帧时按 `frame_deframe` 的「无半帧在等才丢」原则重同步（AGENTS 陷阱 77 的同一口径）。
- **主题**：`restyle_for_theme(dark)` 只改日志/帧预览的调色板与 QSS 类，不写死背景。
- **落盘**：`app_paths.data_path("dlt645_testbench.json")`，`merge` 宽容（坏值逐项回落默认），
  定时器防抖保存；`cleanup()` 停表、断信号、flush、落盘，不关串口。

## 4. 接线

```python
# protocol_registry.ProtocolSpec
has_dlt645_test: bool = False
# index=6: has_dlt645_test=True  （has_test 保持「仅 698」，既有断言不变）
def protocols_with_dlt645_test() -> Tuple[int, ...]

# main_gui
self._dlt645_test_placeholder = QWidget()
self._dlt645_test_tab_index = self.tab_widget.addTab(..., "645协议测试")
setTabVisible(..., False)                       # 创建即隐藏（构造期协议回调可能不触发）
_ensure_lazy_tab: elif index == _dlt645_test_tab_index → _ensure_dlt645_test_tab()
_ensure_dlt645_test_tab(): 惰性 import → set_serial_worker → frame_to_single_parse.connect →
    restyle_for_theme(self._is_dark_theme()) → _replace_lazy_tab
_on_protocol_changed: setTabVisible(index, spec.has_dlt645_test)
_restyle_for_theme / _shutdown_threads: 与 test_tab 同款各加一段
```

## 5. 测试计划

### `test/test_dlt645_testbench.py`

| 段 | 断言 |
|---|---|
| [1] 分类库 | 顶层名称/顺序；1781 条 DI 全覆盖且不重复；叶子名称/长度与 DI 表一致；`02E6/03E6/04E6` 在「光伏扩展」；结算日分桶数 = ⌈254/20⌉；`find_di` |
| [2] 命令库 | 覆盖 schema 全部 REQ 功能码；分组非空；字段与 `get_command` 同源 |
| [3] 组帧 golden | 读 A 相电压 `02010100`（11H）、写 `04000101` 日期（14H）、读地址（13H）、写地址（15H）、广播校时（08H）、冻结（16H）、事件清零（1BH）、读后续（12H）：逐字节 + CS 自洽 + `DLT645Parser` 回读 DI/控制码/数据域一致 |
| [4] 判定矩阵 | 正常读应答成功且值正确；异常应答失败且给 ERR 位；方向错/功能码错/DI 不符各失败；13H 回填地址；08H 不走失败 |
| [5] offscreen GUI | 3 页树与当前项、帧预览随选中/输入变化、发送队列（假串口注入响应帧，顺序 3 条）、超时继续、停止复位、空地址拦截、落盘重开、主题、`cleanup` |
| [6] 共享渲染 | `format_table_rows` 与 698 同源（导入同一模块）+ 698 既有输出回归 |

### `test/test_dlt645_test_tab_wiring.py`

注册表能力（仅 6）、tab 标题/顺序、切协议显隐、懒加载只建一次、串口注入、双击转单帧、
主题钩子、cleanup 不关串口。

## 6. 风险

- **写数据/清零是真实下发**：页面只负责组帧与发送，输入框默认为 0/空，`length_warning` 提示长度不符；
  不自动循环写。参数落盘但不含任何密码真实值以外的东西（用户自填）。
- **DI 表是生成物**：分类只做「按前缀分组 + 取表内名称」，不新增/改名任何 DI；
  若表更新，分类自动跟随（测试断言覆盖全部 DI）。
- **共享渲染抽取**不得改变 698 输出：`test_dlt698_testbench.py` 279 项是安全网。
