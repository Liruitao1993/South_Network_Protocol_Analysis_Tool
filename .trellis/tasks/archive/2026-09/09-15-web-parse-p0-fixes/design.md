# 设计：Web 解析 P0 修复

## 1. 分层与职责（本次要建立的可测边界）

```
reflex_web/reflex_web/web_utils.py      ← 纯函数（无 Qt / 无 reflex）：本次新增 4 个
    hex_to_bytes_strict()
    apply_strip_once()
    batch_frame_status()
    parse_kwargs_for()
reflex_web/reflex_web/reflex_web.py     ← State：只做「取状态 → 调纯函数 → 赋值前端字段」
csg_new_gen_parser.py                   ← ED 包装自动识别 + 双布局（两端共享）
protocol_registry.py                    ← 校验器工厂（Web 直接复用，无 Qt）
```

原则：**判据进纯函数，State 里不留条件逻辑**。理由：Reflex `State` 无法在无 app 上下文时实例化，逻辑留在 State 就等于不可测；本仓已有范式 `web_utils`（纯逻辑）+ `test_web_frame_gen_utils.py`（脚本直测）。

## 2. 纯函数契约（`web_utils`）

```python
def hex_to_bytes_strict(text: str) -> bytes:
    """清洗 hex（复用 clean_hex_input 的 0x 前缀与分隔符容忍）→ bytes。
    空 → ValueError("报文为空")；奇数长度 → ValueError("输入长度为奇数，十六进制字符串必须是偶数长度！")"""
```

```python
def strip_frame_bytes(frame_bytes: bytes, head: int, tail: int) -> bytes:
    """头/尾剔除；head=tail=0 → 原样返回；head >= total-tail → ValueError（沿用现文案）。"""
```
- **不设缓存**：桌面用「回写输入框 + `_csg_last_stripped_hex`」保证幂等（`main_gui.py:5322-5346`）；
  Web 的实现天然幂等——每次 `parse_frame` 都从**未被修改的** `frame_hex` 重新清洗后剔除，
  同一输入恒定得到同一输出。实施中曾按原审计结论引入「缓存键跳过」，实测第二次解析会拿到
  **未剔除**的原始字节（真回归），已撤销。
- 取舍：不回写输入框（受控 textarea；Web 无字节高亮，无坐标一致需求）。

```python
def batch_frame_status(rows) -> tuple[str, str]:
    """(status, summary)。
    空表 → ("失败", "解析无结果（未产出字段）")
    存在 row[0] 以 "❌" 开头 → ("失败", row[3] or "解析失败")
    否则 → ("成功", "-")   # summary 由调用方另行计算，本函数只负责失败摘要覆盖
    """
```
- 返回值第 2 项仅在失败时有意义；成功返回 `"-"` 以免调用方误用。

```python
def parse_kwargs_for(protocol_index: int, parse_level: str = "auto",
                     pb_frame_type: str = "sof", gw_frame_type: int = 1,
                     channel: str = "plc") -> dict:
```
- 9 → `{"parse_level": parse_level, "channel": channel, "pb_frame_type": pb_frame_type}`（`pb_frame_type` 仅在 `mac_only`/`pb_only` 有意义，parser 内部按级别取值；始终下发与现有行为一致）。
- 10/11 → `{"parse_level": parse_level, "channel": channel}` + `pb_only` 时 `{"frame_type": gw_frame_type}`。
- 其余 → `{}`。

## 3. ED 包装：单源化与双布局（`csg_new_gen_parser.py`）

```python
_ED_PB_SIZES = (16, 40, 72, 136, 264, 520)

def detect_ed_wrapper(frame_bytes: bytes, fallback: str = "plc2") -> str: ...
```
- 打分算法逐条对齐 `main_gui._detect_ed_wrapper`（`main_gui.py:5037-5060`）：帧结构强校验先行（`ED` 起始、`frame_len` ∈ [4,4096]、`total ≤ n`、`frame_bytes[5] == 0xEF`、尾 `0xEE`），再对 `("plc2", 9, 7)` / `("gx", 8, 6)` 逐候选打分。
- 无业务域时分（控制/空数据报文）仅看 `pb_len` 是否属常用尺寸（与桌面一致）。

`_parse_ed_wrapper(frame_bytes, parse_level, pb_frame_type, channel, wrapper=None)`：
- `wrapper is None` → `detect_ed_wrapper(frame_bytes)`。
- 布局表（与 `main_gui.py:5172-5240` 逐字段对齐）：

| 字段 | plc2（9B 头） | gx（8B 头） |
|---|---|---|
| 时间戳 | `data[1:5]` LE | `data[0:4]` LE |
| 物理信道 | `data[0]` | `data[4]` |
| 物理块个数 | `data[5]` | `data[5]` |
| Payload CRC | `data[6]`（ctrl2=0x02 时 0=正确/1=错误） | 无此行 |
| 单个物理块长度 | `data[7:9]` LE | `data[6:8]` LE |
| 业务帧 | `data[9:]`（offset = data_start+9） | `data[8:]`（offset = data_start+8） |
| 标题行 | `── PLC2.0 监控包装头 ──` | `── 广西台体监控包装头 ──` |

- 触发条件不变：`ctrl1 == 0x00 and ctrl2 in (0x01,0x02,0x03) and data_len >= hdr_len`，`hdr_len = 8 if wrapper == "gx" else 9`。

`parse_to_table(..., ed_wrapper=None)` → 透传。

**桌面委托**：`main_gui._detect_ed_wrapper` 保留方法名与返回语义，内部：
```python
from csg_new_gen_parser import detect_ed_wrapper
mode = self._ed_wrapper_mode()                       # auto / plc2 / gx
fallback = "plc2" if mode == "auto" else mode
return detect_ed_wrapper(frame_bytes, fallback=fallback)
```
（`_ed_wrapper_for_frame` 与所有调用点保持不变。）

**摘要消费者**：改为「标题含 `监控包装头`」，并按标题含 `广西` 与否给出 `广西台体监控包装帧` / `PLC2.0监控包装帧`。

## 4. 校验链路

`_get_validator`：
```python
def _get_validator(self):
    import protocol_registry
    return protocol_registry.make_validator(self.current_protocol)
```
- `make_validator` 内部 `importlib` 惰性导入，异常语义与原实现一致（导入失败 → 向上抛，由 `verify_frame` 的 `except Exception` 兜底）。
- 删除原 12 项硬编码 dict 与局部 import（该 dict 与本任务无关地漂移过：`p` 未定义即是删改留下的伤口）。

`verify_frame` 预处理与 `parse_frame` 相同（R1）：清洗（严格）→ 剔除（幂等）。

## 5. 兼容性与取舍

- **不回写输入框**（与桌面不同）：Web `frame_hex` 是受控 textarea，解析时回写会打断编辑；Web 也尚无字节高亮，无坐标一致需求。取舍写在此处，避免后来者「修」回去。
- **空表 = 失败**：桌面原语义为「成功」，本次两侧统一为失败，理由是空表意味着解析器未产出任何字段（对用户等价于没解析成功）。ED 三分支自带 status，不受影响。
- **`frame_type` 取值域**：协议10 `pb_frame_type` 下拉与协议11 共用控件时取值集合不同（`gw_new_gen_parser` 与 `hdc10_parser` 分支不同），实现时以两端解析器 `frame_type` 分支为准，并把实测取值写进测试。
- **不引入新依赖**：`protocol_registry` 仅 `dataclass/importlib`，Web 侧直接 import 不增加打包负担（`reflex_web_exe.spec` 已含项目根模块白名单，实现时确认）。
