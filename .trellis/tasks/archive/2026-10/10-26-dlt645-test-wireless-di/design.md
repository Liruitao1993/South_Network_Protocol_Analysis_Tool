# 设计：645 测试页接入无线手册 V1.6 扩展 DI

> PRD 见 `prd.md`。核心：**数据源只有一个**（`dlt645_pv_wireless.WIRELESS_DI_MAP` +
> `dlt645_pv_wireless_frame` 的字段/编解码），本任务只把它们接进测试页的树与读请求，
> 不新增 DI 名称表、不改解析/组帧口径。

## 1. 改动点

| 文件 | 改动 |
|---|---|
| `dlt645_test_core.py` | 分类追加无线组；`DiItem + wireless/note`；`di_info` 回落；`read_request_fields`；`build_read(..., field_values)`；无线响应摘要；命令组补 06H/1EH |
| `dlt645_test_widget.py` | 读页「当前项」支持请求字段（02EB0000 / FF00DD01）+ 无线备注行；预览/队列传字段 |
| `test/test_dlt645_testbench.py` | 分类/组帧/判定/GUI/变异断言（R5） |
| 文档 | AGENTS §5.4、spec §7n、CHANGELOG（版本批次留工作区） |

## 2. 分类结构

```
光伏无线扩展（V1.6）              ← 顶层分类（追加在「光伏扩展」之后）
├── 数据转发       02EB0000
├── 无线参数       04E60001 04E60002
├── 拓扑           04900100
├── 升级           04900101 04900102 04900103 04900104 04900105 04900106
├── 版本           04900107
└── 在网状态       028100FF
```

- 子类名直接取 `info["group"]`（手册分组），顺序 = `WIRELESS_DI_MAP` 插入顺序（与手册表一致）；
- 叶子 `DiItem(name/unit/data_type/length, wireless=True, note=info["note"])`；
  `length = max(0, int(info["length"]))`（`-1` 不定长 → 0，与现有展示一致）；
- **不要**把这 12 条并进 `_load_merged()`：它们不是 `dlt645_di.json` 数据，并进去会与
  「叶子数 = 合并表 − 残键」的既有不变量打架；分类层单独追加更清晰。

## 3. 读请求字段

```python
# schema 已有：REQ_WITH_PAYLOAD_DI = ("02EB0000",)；build_di_fields 对无线 DI 优先分派
def read_request_fields(di: str) -> List[dict]:
    key = _di(di)
    if key in REQ_WITH_PAYLOAD_DI or key == "FF00DD01":
        return list(build_di_fields(key))
    return []

def build_read(di, addr=DEFAULT_ADDR, field_values=None):
    fv = dict(field_values or {})
    fv["数据标识 DI"] = _di(di)
    return _gen().generate_frame((REQ, 0x11), fv, addr)
```

- `02EB0000` 的字段：`波特率特征字 Z`（1 字节 hex）/`校验方式 C`/`超时 T（BCD）`/
  `转发数据（逆变器报文）`——由 `dlt645_pv_wireless_frame._fields_transfer()` 提供；
- `FF00DD01` 的字段：`条目列表`（LME）。
- **不传字段时与现状逐字节一致**（既有 11H 帧 golden 不变）。

## 4. 响应摘要（不重复解析实现）

`evaluate_response(kind="read")` 中，若 `di_info(di)` 来自无线表：

```python
rows, name = parse_wireless_di(di, ctrl, parsed["data"])   # data = 减 33H 后含 DI
pairs = [(r[0].strip(" └"), _cell_text(r[2])) for r in rows or ()
         if r[0].strip().startswith("└") and r[2] and "数据块" not in r[0]]
value_text = "；".join(f"{k}={v}" for k, v in pairs[:3]) or body.hex(" ")
```

- 摘要：`f"{di} {name} = {value_text}"`；`detail_lines` 仍由 `DLT645Parser` 提供（已含无线展开）。
- 标准 DI 分支保持现有 `decode_value` 不变。

## 5. 特殊命令

`_COMMAND_GROUPS` 末尾追加 `("无线扩展（V1.6）", (0x06, 0x1E))`；两条命令 schema 已存在，
`build_command` 走 `generate_frame`，地址用页面表地址（1EH 的模块地址由用户填）。
06H 的字段含「数据标识 DI」（`_di_field`），页面已支持 DI 输入（上一任务加的）。

## 6. 页面

- `_show_read_detail(di)`：构造 `信息行 + (可选)请求字段表单 + (可选)说明`；
  复用写页的字段渲染方式（`QFormLayout` + `textChanged → _refresh_preview`）。
- `state["fields"]` 同时供读页使用；`_build_preview("read")` 传 `_field_values("read")`；
  `_build_queue` 读条目同样传字段。
- 无线叶子在「当前项」追加一行备注（`item.note`，`wordWrap`），说明方向/控制码与注意事项。

## 7. 测试要点

- 逐字节 golden 用 `logical_data()`（既有 helper，减 33H）断言请求数据域；
  02EB0000 期望 `[DI reverse] + 08 02 10 68 11 00`；
- 响应构造直接用 `DLT645FrameGenerator.generate_frame(("rsp",0x11), fv)`，
  `fv` 取 `build_wireless_fields(di)` 的字段名（`build_data` 会走 `build_wireless_payload`）；
- 变异点：`read_request_fields` 恒空 / 无线摘要分支移除 / 分类不追加。
