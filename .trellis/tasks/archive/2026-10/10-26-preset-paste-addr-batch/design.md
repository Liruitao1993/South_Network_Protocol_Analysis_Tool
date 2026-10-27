# 设计：预设页「粘贴报文添加」+「一键批量替换地址」

> PRD 见 `prd.md`。核心事实：**地址替换引擎已存在**（`frame_addr_fix.py` + `message_tool_widget.replace_frame_address`，
> 已被蓝牙单按钮/串口批量/蓝牙批量/报文工具四处复用），本任务只补**预设页这层的编排 + 入口**。

## 1. 边界

| 模块 | 角色 | 改动 |
|---|---|---|
| `preset_buttons.py` 模块头（纯逻辑段） | 协议映射 + 批量编排 | `+ protocol_registry` 导入、`preset_protocol_index`、`AddrBatchItem`、`batch_fix_presets` |
| `preset_buttons.py` `AddPresetDialog` | 可编辑报文模式 | `+ editable_frame: bool = False`、剪贴板粘贴按钮、HEX 校验/归一化 |
| `preset_buttons.py` `PresetButtonWidget` | 入口 + 地址区 + 写回 | `+ _on_add_clicked` / 地址区 `_sync_addr_group` / `_on_batch_addr_clicked` / 日志与汇总 |
| `frame_addr_fix.py` | **复用，不改** | — |
| `message_tool_widget.py` | **复用，不改** | —（`replace_frame_address` / `addr_field_errors` / `hex_text_to_bytes`） |
| `test/test_preset_paste_addr.py` | 新增 | 纯逻辑 + offscreen GUI |
| `release_check.py` | 门禁 | `CORE_TESTS` +1 行 |

不改：`main_gui.py`（页面已有 `set_protocol` 调用，新逻辑自包含）、协议解析/组帧、Web 端、配置 schema。

## 2. 契约

```python
# ── preset_buttons.py（纯逻辑，无 Qt）───────────────────────────────────
ADDR_STATUS_OK = "ok"
ADDR_STATUS_SKIPPED = "skipped"

@dataclass
class AddrBatchItem:
    index: int                      # 传入 commands 内的下标（调用方据此映射回原下标）
    name: str                       # button_name（日志/弹框用）
    status: str                     # ok / skipped
    frame_hex: str                  # ok = 新帧；skipped = 原值
    error: str = ""                 # skipped 原因（可直接展示）
    notes: List[str] = field(default_factory=list)   # ok 的「地址域…/校验和…」明细

def preset_protocol_index(preset_key: str) -> Optional[int]:
    """preset_mode(south/gdw/…) → 协议索引；未知 = None（来源 protocol_registry）"""

def batch_fix_presets(commands: Sequence[Mapping[str, Any]], protocol_index: int,
                      values: Mapping[str, str]) -> List[AddrBatchItem]:
    """逐条 replace_frame_address；不修改入参；单条异常→skipped，不中断"""
```

## 3. GUI 结构

```
预设命令页
├─ 说明 hint
├─ 行：[添加命令]  搜索: [____________]
├─ 统计 label
├─ QGroupBox「批量替换地址（<协议名>）」
│   ├─ _addr_form_host（每次 _sync_addr_group 重建 = 新的 QWidget + QFormLayout 字段行 + 按钮行）
│   │   ├─ 源地址：[____]   目的地址：[____]        （按 fields_for 动态）
│   │   └─ [一键替换地址]  …stretch
│   └─ 提示 label（写法说明 / 不支持协议的原因）
├─ 按钮滚动区（不变）
└─ 串口日志（不变）
```

- **重建方式**：`_sync_addr_group()` 每次都新建一个 `_addr_form_host` 并 `removeWidget(old)+deleteLater()`，
  **不用 `QFormLayout.removeRow`**（AGENTS 陷阱 69 已记录该 API 会连控件一起删，反查行号才安全；
  换整个 host 更简单且无双重删除风险）。
- **按协议暂存输入**：`self._addr_values_by_protocol[协议键][字段 key]`，切走前收集、切回后回填。
- `set_protocol()` → `load_buttons()` + `_sync_addr_group()`。

## 4. 一键替换的执行顺序

```text
index = preset_protocol_index(当前协议)      # None → 告知"不支持"并 return
values = 非空输入                             # 空 → 警告 "至少填一个地址" 并 return
errors = addr_field_errors(index, values)     # 写法级；非空 → 警告列出并 return
commands = load_commands(当前协议, _get_path())
scope = [i for i,c in enumerate(commands) if c.get("protocol", 当前协议) == 当前协议]
items = batch_fix_presets([commands[i] for i in scope], index, values)
ok = [it for it in items if it.status == ok]; skipped = 其余
若 not ok → 警告 "没有可替换的预设" + 跳过原因，**不写盘**
QMessageBox.question（成功/跳过计数 + 前 8 条原因）→ 否 → return
for it in ok: commands[scope[it.index]]["frame_hex"] = it.frame_hex
save_commands(...)   # 一次落盘；失败 → 警告"保存失败" + return
_log_batch_result(ok, skipped) → load_buttons() → 汇总 information
```

**作用范围 = 当前协议**（页面只显示该协议条目；同文件里其它协议的历史混入条目**保持原样**——
与 `load_buttons` 同一过滤判据，避免「看不见的条目被悄悄改掉」）。

## 5. AddPresetDialog 编辑模式

- `editable_frame=True`：`frame_preview.setReadOnly(False)`、`setMaximumHeight(110)`、Consolas 9、
  占位提示「在此粘贴报文（HEX，可直接 Ctrl+V）…」，下方「从剪贴板粘贴」按钮（`set_btn_icon(..., "copy")`）。
- 打开时若 `frame_hex` 为空：读剪贴板 → `hex_text_to_bytes` 成功才带入（归一化），失败**静默忽略**
  （剪贴板常是别的内容，不该弹框）。
- `_on_ok`：编辑模式必须先 `_normalize_frame_text()`（复用 `hex_text_to_bytes`）→ 失败
  `QMessageBox.warning` 并 return（**不 accept**）；成功存空格分隔大写 HEX。
- 非编辑模式完全走原路径（`_frame_hex` 原样存入），保证组帧页「添加到预设」零行为变化。

## 6. 失败/边界矩阵

| 条件 | 行为 |
|---|---|
| 协议不支持（modular / 12） | 地址区按钮 disabled + 提示「v1 支持 南网/645/国网/698.45/依瓦645/南网上行」 |
| 地址全空 | 警告「至少填写一个地址」，文件不变 |
| 地址写法非法（长度/字符/越界） | 列出 `addr_field_errors` 全部原因，文件不变 |
| 某条报文为空 / 结构不符 / 原帧校验不符 | 该条 `skipped`（原因可读），其余照常；确认框+汇总+日志三处可见 |
| 全部 `skipped` | 警告 + 原因，**不写盘**（避免「保存了一次什么都没变」） |
| `save_commands` 失败 | 警告「保存失败」；内存列表未被刷新（按钮仍是旧报文，状态自洽） |
| 剪贴板内容不是 HEX | 对话框打开时不带入；点「从剪贴板粘贴」时明确提示 |
| 编辑模式报文非法/为空 | 警告并停在对话框（不落盘） |

## 7. 测试计划（`test/test_preset_paste_addr.py`）

| 段 | 内容 |
|---|---|
| [1] | `preset_protocol_index` 7 个已知键 + 未知/空；与 `protocol_registry.preset_mode` 逐条对拍 |
| [2] | `batch_fix_presets`：南网真帧（src/dst 字节 + `NWValidator` 0 fail）、645 带 FE（前导保留 + `DLT645Validator` 0 fail）、空帧、坏帧、混合批次、**入参深比较不变** |
| [3] | `AddPresetDialog`：编辑模式可编辑、`6812004116`→`68 12 00 41 16`、`68 12 0G` 被拒、剪贴板带入、非编辑模式原样 |
| [4] | offscreen GUI：地址区按协议生成（south 2 字段 / modular 禁用+提示）、端到端一键替换（patch `question`/`information`/`warning`）、跳过项、空地址拦截 |
| [5] | offscreen GUI：添加命令端到端（patch `preset_buttons.AddPresetDialog` 替身）→ JSON 多一条 + 按钮出现 |
| [6] | 按钮不裁字：`add_btn` / `batch_addr_btn` 在 `show()` 后 `width >= sizeHint().width()` 且未设 `maximumWidth` |

**变异反证（实施阶段做，逐条变红后逐字节还原）**：
① 写回用相对下标（不映射回 `scope`）→ 应红（跨协议条目被改）；
② 全失败仍写盘 → 应红（文件字节变化）；
③ 编辑模式跳过 HEX 校验 → 应红（非法 HEX 落盘）。

## 8. 风险

- `message_tool_widget` 顶层 `import crcmod` ⇒ **只能函数内导入**；`preset_buttons` 模块级导入会让
  无 crcmod 的机器连预设页都打不开（`test/test_dlt698_preset.py` 会最先炸）。
- 预设文件是用户数据：写回必须**一次原子写**（`PresetButtonManager.save_commands` → `atomic_write_json`），
  且只改 `frame_hex` 一个键。
- 页面 `_get_path()` 对 dlt698/dlt645/modular/yw645/csg_uplink 返回 `None`（用模块默认路径）；
  测试必须重定向模块常量或只用 `south/gdw` 临时路径，**不得写真实预设文件**。
