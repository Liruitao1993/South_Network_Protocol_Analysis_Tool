# Design：协议7「协议测试」页

> 参考实现：`dlt698_test_core.py` / `dlt698_test_widget.py`（协议8 页）+ `dlt645_test_core.py`（第二套协议测试页）。
> 本页与两套既有页同构，但**数据源与判定全部换成国网**，且**不新增任何国网协议判据/组帧逻辑**。

## 1. 单一来源（禁止另建表）

| 用途 | 来源 |
|---|---|
| AFN 名称 / Fn 名称（含福建增补、F0/F1） | `gdw10376_parser.GDW10376Parser.AFN_MAP` / `FN_MAP` |
| 命令清单 + 字段 schema + 说明 | `gdw_frame_generator_schema.GDW_AFNFN_SCHEMA`（122 条，含 0x50~0x56 与 0xF0/0xF1） |
| 组帧 | `gdw_send_frame_lib.GDWFrameGenerator.generate_frame(...)` |
| 解析 / 表格 | `gdw10376_parser.GDW10376Parser.parse_to_table` / `verify` |
| EB 数据标识 + 分组 | `gdw_eb_di_lookup.get_eb_di_lookup().EB_DI_MAP`（75 条） |
| EB 数据内容字段与编码 | `gdw_eb_di_fields.EB_DI_FIELDS`（56 条有结构）+ `encode_eb_di_data` |
| 自定义 AFN/Fn | `GDW10376Parser.get_custom_entries()`（`gdw_custom_afn.json`） |
| 通道 | `channel_link.ChannelController` |
| 分帧 | `frame_deframe.frame_length_for("ft12_68", buf)`（国网 L = 整帧长、末字节 16H） |
| 四列文本 | `testpage_render.format_table_rows`（不写第二份） |

## 2. 纯逻辑层 `gdw_test_core.py`

### 2.1 页面与 AFN 归属

```python
PAGE_READ   = "read"    # 03 查询 / 04 链路检测 / 10 路由查询 / 14 路由抄读 / 53 福建查询 / F0 内部调试
PAGE_WRITE  = "write"   # 01 初始化 / 02 数据转发 / 05 控制 / 11 路由设置 / 12 重启暂停恢复 /
                        # 13 路由转发 / 15 文件传输 / 51 52 55 福建 / F1 并发抄表
PAGE_REPORT = "report"  # 00 确认否认 / 06 主动上报 / 50 福建确认否认 / 56 福建主动上报
PAGE_EB     = "eb"      # EB 扩展（645 帧）
PAGE_CUSTOM = "custom"  # 用户自定义 AFN+Fn
```

`AFN_PAGE: dict[int,str]` 必须**恰好覆盖** `AFN_MAP` 的全部 21 个 AFN，且每个只出现一次；
测试断言「并集 == AFN_MAP.keys()」「无重复」「每页 catalog 非空」。

### 2.2 数据模型

```python
@dataclass(frozen=True) class GdwCommand:
    afn: int; fn: int; name: str; direction: str        # "down"/"up"
    fields: tuple[dict,...]; doc: str; source: str      # "标准"/"福建增补"/"扩展"/"自定义"

@dataclass(frozen=True) class EbItem:
    di: str; name: str; fmt: str; length: int; usage: str
    fields: tuple[dict,...]                             # 来自 EB_DI_FIELDS，缺失则 ()

@dataclass(frozen=True) class SubGroup:   # AFN（或 EB 分组）
    key: str; name: str; items: tuple

@dataclass(frozen=True) class Category:   # 功能域（基础 / 路由 / 福建增补 / 扩展 / EB 分组）
    name: str; groups: tuple
```

`source` 判定：`afn in {0x50..0x56}` → 福建增补；`afn >= 0xF0` → 扩展；否则标准。

树的层级：`Category(功能域)` → `SubGroup(AFN 或 EB 前缀)` → 叶子（命令 / EB 项）。
命令叶子文案：`03H F1 厂商代码和版本信息`；EB 叶子：`EB030001 从节点模块事件引脚状态变位（BS8/1B）`。

### 2.3 组帧

```python
DEFAULT_INFO = {"路由标识":0,"附属节点标识":0,"通信模块标识":1,"冲突检测":0,"中继级别":0,
                "纠错编码标识":0,"信道标识":0,"预计应答字节数":0,"通信速率":0,
                "速率单位标识":0,"报文序列号":1,"dir":0,"prm":1,"通信方式":0}

def build_frame(cmd: GdwCommand, values: Mapping[str, Any], *,
                src: str, dst: str, relay: Sequence[str] = (),
                info: Mapping[str, int] | None = None) -> bytes
```
- 一律 `GDWFrameGenerator().generate_frame(afn, fn, dict(values), info, src, dst, list(relay))`。
- 值预处理：`enum` 传 int；`bytes` 传去分隔符 hex 字符串；`list` 传 `list[dict]`；
  `uint16` 按其 `endian`（生成器负责）；`bcd` 传十进制串。
- 校验失败（值非法）抛 `FrameBuildError(中文原因)`，页面捕获后外显、**不发帧**。

### 2.4 EB 组帧

```python
def build_eb_read(di, *, addr: str, ctrl: int = 0x11) -> bytes       # 645 帧
def build_eb_write(di, values, *, addr: str, ctrl: int = 0x14) -> bytes
def wrap_forward(payload: bytes, *, proto: int = 2) -> bytes        # AFN=02H F1 外层
```
- 645 帧：`68 | A(6B，BCD 低字节在前) | 68 | ctrl | L | 数据域 | CS | 16`；
  数据域 = `DI 线上序（低字节在前，如 EB030001 → 01 00 03 EB）` + 数据内容，**逐字节 +0x33 加扰**；
  CS = `sum(帧首..数据域末) & 0xFF`。写入数据 = `encode_eb_di_data(di, values)`；读请求无数据。
- `wrap_forward` 用 `build_frame` 组 `AFN=02H F1`：`通信协议类型=2(DL/T645-2007)`、`报文长度=len(645 帧)`、
  `报文内容=<645 帧 hex>`（生成器按 `bytes` 字段打包，长度字段要由调用方给正确值）。
- 页面提供「外层：转发帧 / 裸 645 帧」二选一（默认转发帧，与现场 CCO 交互一致）。

### 2.5 响应判定 `evaluate_response(cmd, frame) -> dict`

`parse_to_table(frame)` 取行；返回 `{ok: True/False/None, matched: bool, reason: str, rows: [...]}`：

1. 结构：`verify(frame)` 的 `帧长度/起始/结束/校验和` 任一 FAIL → `ok=False, matched=False`（截断/坏帧）。
2. AFN：行 `应用功能码(AFN)` 的解析值 → 与 `cmd.afn` 比对；不符 → `matched=False`。
3. Fn：行 `数据单元标识(DT)` 说明 `F<n>=...` → 与 `cmd.fn` 比对（DT2 非 0 视为厂商扩展，`matched=False`）。
4. 语义：
   - `AFN=00H`：`F1` 且含 `命令状态` → 成功；`F2` 且含 `错误状态字` → 失败（带状态字说明）。
   - `AFN=50H`：`F1/F3` 无数据单元 → 成功；`F2` + `错误状态字` → 失败。
   - 任意行含 `错误代码` → `err==0 ? 成功 : 失败(说明)`。
   - `AFN=56H` 的 `确认/否认` 行 → 按文案判。
   - 其余：`ok=None, matched=True, reason="已收到同命令响应，未做字段级判定"`（**不冒充成功**）。

### 2.6 其它工具

- `parse_hex(text)` / `format_hex(bytes)`（复用 698 页同名实现思路，容忍分隔符与 `0x`，奇数位报错）。
- `parse_table(frame)` → 行列表；`detail_lines(rows, max_lines=0)` → 文本行（走 `testpage_render`）。
- `response_summary(rows)` → 单行摘要（AFN/Fn + 第一个业务字段）。
- 地址工具：`addr_ok(text)`（12 位十进制）、`normalize_addr`。
- `default_values(cmd)`：按 schema `default` 生成初始值。
- `validate_values(cmd, values) -> list[(字段名, 原因)]`。

## 3. GUI 层 `gdw_test_widget.py`

布局（与 698 页同构）：

```
┌ 顶部：协议测试 | 发送通道[串口▾] 状态: … | 源地址 目的地址 模块标识 中继级别 序列号 | 超时 重试 ┐
├ 左：搜索 + 树(AFN/Fn) + 全选/全不选/勾选数 + 备注(命令说明)      ├ 中：命令信息 + 动态参数表单      ┤
│                                                                  │    + 预览 HEX + 发送/停止        │
├ 底：日志（彩色，分 TX/RX/信息/失败）                             ├ 下：tabs[信息表 | 报文表]         ┘
```

- 页签：读取数据 / 设置控制 / 主动上报 / EB 扩展 / 自定义；切换页签重建树与参数区（当前勾选按页保存到内存）。
- 动态字段控件按 schema 类型生成：`enum→QComboBox`、`uint8/16→QSpinBox`、`bcd→QLineEdit(掩码提示)`、
  `bytes→QLineEdit`、`list→子表(增删行)`；`length_field`/`count_field` 由生成器自动补，**界面不重复暴露**。
- EB 页：左树（EB 分组），中区 = 645 地址 / 控制码(读·写) / 外层(转发·裸帧) + 数据内容字段（有 `EB_DI_FIELDS` 时）
  或裸 HEX 输入（无定义时，明确提示「该 DI 无字段定义，按 HEX 下发」）。
- 发送队列：勾选叶子（未勾选 = 当前选中）→ 逐条组帧 `write_raw` → 等应答（单发 QTimer）→ 判定 → 下一条；
  `_awaiting` 守卫 + `_send_generation` 代次校验（防上一轮遗留定时器提前发下一条）。
- RX：`controller.rx` 字节 → `frame_deframe.frame_length_for("ft12_68", buf)` + 末字节 `16H` 自证；
  前导 `FE` 需后随 `68`；噪声重同步「找下一个 68/FE」。
- 报文表双击 → `frame_to_single_parse` 信号（与监控器/698 页共用注入点）。
- 落盘 `gdw_testbench.json`（`app_paths.data_path` 属性访问）：地址/信息域/超时/重试/通道/页签/分栏/书签(afn,fn,di)；原子写、坏值回落。
- 主题：`restyle_for_theme(dark)`；`cleanup()` 停队列/刷日志/落盘/断信号（不关串口、不断蓝牙）。
- 几何：树 `minimumHeight=160`、日志 `minimumHeight=120`、底部 tabs `maximumHeight=200`（照 698 页实测预算）。

## 4. 接线

1. `protocol_registry`：`ProtocolSpec` 增 `has_gdw_test: bool = False`，协议7 置 True；
   新增 `protocols_with_gdw_test()`；`protocol_names` 等既有字段不变。
2. `main_gui`：新增 `_ensure_gdw_test_tab()`（懒加载、`set_serial_worker` / `set_bluetooth_provider` /
   `set_send_to_single_handler` 注入、创建后 `restyle_for_theme(self._is_dark_theme())`）、
   `_on_protocol_changed` 里 `setTabVisible(...)`、`_shutdown_threads` 里 `cleanup()`。
3. tab 文案「协议测试」，排在「协议测试」（协议8）/「645协议测试」（协议6）之后 —— 三者互斥可见。

## 5. 测试

- `test/test_gdw_testbench.py`
  - [1] 单一来源对拍：catalog 叶子数 == schema 命令数（122）；AFN 归属无遗漏/重复；名称与 `AFN_MAP/FN_MAP` 逐条一致。
  - [2] 组帧：对每条命令用 `default_values` 组帧 → `parse_to_table` 回读，AFN/Fn/字段值一致；
          `03H F1`、`05H F1`、`10H F2`、`55H F1`、`F1H F1` 逐字节 golden。
  - [3] EB：读/写帧逐字节（DI 线序、+0x33、CS）、转发外层长度自洽、`EB_DI_FIELDS` 覆盖 56 条字段表单。
  - [4] 判定矩阵：00H F1/F2、50H F1/F2/F3、错误代码、AFN 不符、Fn 不符、CS 错、截断。
  - [5] offscreen GUI：五页切换/树筛选/动态表单类型/勾选顺序下发/超时重试/停止/落盘重开/主题/cleanup/几何与按钮宽度。
- `test/test_gdw_test_tab_wiring.py`：能力位仅协议7、tab 文案与位置、懒加载、注入（串口/蓝牙/单帧解析）、
  收尾不关串口、主题钩子。
- 变异反证：AFN/Fn 回显判定、EB +0x33、`_awaiting` 守卫、前导 FE 重同步各 1 条。

## 6. 风险与取舍

- **不新增国网判据**：AFN/Fn 回显不靠解析器新增方法，全部从既有表格行读取 → 跑真实帧语料等价性由 [4] 覆盖。
- **字段表单只覆盖 schema 的 8 种类型**；未来新增类型时 `_build_field_widget` 给「不支持（按 HEX）」并外显，不静默。
- **EB 645 帧加扰方向**：按解析器 `_try_parse_embedded_eb` 的既有口径（数据域 +0x33、DI 低字节在前）反向构造，
  组帧后立即用解析器回读自证（测试 [3]）。
- 协议8/6 既有页不动；`has_test` / `has_dlt645_test` 语义保持。
