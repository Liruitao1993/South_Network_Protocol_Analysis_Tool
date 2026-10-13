# 研究：复用 `frame_addr_fix` 与串口侧批量编排的关键事实

> 目的：把「可直接复用什么 / 有什么现成 oracle / 哪几处必须自己处理」写成一份短的、可供子代理消费的上下文，
> 避免每次都去读 63KB 的 `component-guidelines.md`（超过注入上限会被截断）。

## 1. 现成引擎（`frame_addr_fix.py`，515 行，纯逻辑无 Qt，**本任务不改它**）

```python
SUPPORTED_PROTOCOLS = (0, 6, 7, 8, 13, 14)

@dataclass(frozen=True)
class AddrField: key; label; hint; kind; length        # length=0 → 由帧决定（698 SA）
@dataclass
class FixResult: ok; frame: bytes; notes: List[str]; error: str

fields_for(protocol_index) -> Tuple[AddrField, ...]     # 不支持的协议 → ()
parse_address(text, addr_field, on_wire_length=0) -> (bytes, err)
apply(frame, protocol_index, values: Mapping[str,str]) -> FixResult
protocol_label(protocol_index) -> str
supported_choices() -> List[(显示名, 协议索引)]
```

字段键（`values` 的 key）：`0/7` = `src`/`dst`；`6/13` = `addr`；`8` = `sa`/`ca`；`14` = `a2`。

- `apply` 第一步是**结构 + 原帧校验自证**（`68…16`、长度域自洽、原校验正确），失败即 `ok=False`
  ⇒ 「能自证才替换」这条口径由引擎天然保证，本任务不用另写判据。
- `notes` 形如 `地址域 表地址 33 00 … → 32 00 …`、`校验和 0xE5 → 0x1A`（699 还有 HCS/FCS 两项）。
- 每个 applier 都是**先自证 → 定位 → 替换 → 复用该协议既有组帧/校验实现**（645 走 `DLT645FrameGenerator.build_frame`、
  698 走 `DLT69845FrameGenerator._assemble_frame`、依瓦走 `yw645_wire.encode_frame`、
  南网上行走 `csg_uplink_wire.encode_frame`、南网/国网走字节拼接 + `Frame/GDWFrame.calculate_checksum`）。
- 协议模块**按需导入**（`dl_t698_45_frame_gen` 顶层 `import crcmod`，crcmod 是可选依赖）
  ⇒ 串口页只 `import frame_addr_fix` 是安全的，**不要把 `dl_t698_45_frame_gen` 提到模块级**。
- 限制：**同长度替换**（改长度就动 L/HCS/FCS）；协议 9/10/11/12 与 1/2/3/4/5 → 可读「暂不支持」。

## 2. 必须由本任务处理的三件事

| 事 | 为什么不能指望引擎 | 做法 |
|---|---|---|
| **前导 FEH** | 引擎按 `frame[0] == 0x68` 自证；带 `FE FE FE FE` 的合法帧会直接失败 | 协议 **6/8** 先 `wakeup_prefix.strip_wakeup_prefix` 剥离，成功后按原字节数**原样恢复**前导；其余协议不剥（规范无依据，AGENTS §8 陷阱 75） |
| **协议列** | 引擎只处理帧字节，不知道命令记录结构 | `batch_fix_commands(..., write_protocol=True)` 把协议写进 `cmd["protocol"]`（「加载报文文件」导入的报文是 `protocol=None`，写进去 RX 才能按协议解析） |
| **预期响应** | 匹配方式有 7 种，只有 4 种是纯 HEX | `HEX_MATCH_TYPES = ("contains","equals","starts_with","ends_with")` 白名单；通配/正则/不匹配保持原样 + 说明 |

## 3. 现成的测试 oracle（不要自造帧）

- `test/test_bluetooth_addr_fix.py`（96 项）：六协议真帧 + 「替换后该协议校验器 0 fail」的判据、
  错误矩阵（结构不符 / 无地址域 / 长度不符 / hex 写错 / 协议不支持）、反例自检。
  **本任务的 `test/test_serial_addr_fix.py` 直接复用它的帧样本与校验器口径**。
- 前导 FE 的现成样本：`test/test_wakeup_fe_prefix.py`（`FE4` 常量、协议 8 报障帧、协议 6 合法帧）。
- 串口工具页面范式：`test/test_serial_tool_widget.py`（分段 `[1]…[34]`，新段接 `[35]`）——
  沙箱必须 `import _config_sandbox; _config_sandbox.install()`（重定向 `app_paths.data_path`）。
- 校验器用法：`validator/__init__.py` 导出；`protocol_registry.make_validator(index)` 可取对应校验器。

## 4. 本项目实测过、必须遵守的坑

- 改源码做变异反证：用 `path.write_bytes(...)`（`write_text` 会把 CRLF 翻译坏掉续行 → `SyntaxError`），
  还原后比 `md5`；锚点用 ASCII（命令行/heredoc 传中文会被本机编码搞坏）。
- 长驻内核会缓存 `sys.modules` ⇒ GUI 冒烟一律起**子进程**。
- 按钮宽度：判据是 `btn.width() >= btn.sizeHint().width()`，**必须在 `show()` 之后量**；
  只设 `minimumWidth`（`maximumWidth` 应保持 `QWIDGETSIZE_MAX`）—— 写死宽度在可配置字号下必裁字。
- 日志/弹框不要逐条刷：明细上限 20 行 + 「另有 N 条」（同 AGENTS §8 陷阱 58 的 burst 精神）。
