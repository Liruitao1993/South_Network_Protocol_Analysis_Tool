# Design — 协议6 校验和/长度/结构不符时仍继续解析并提示正确值

## 1. 改动边界

| 文件 | 改动性质 |
| --- | --- |
| `dlt645_parser.py` | 拆结构与校验判据；`parse()` 去掉提前 return；新增提示行与结果字段（**唯一的产品代码改动**） |
| `test/test_dlt645_tolerant_parse.py`（**新增**） | 覆盖 A1~A9 与变异反证 |
| `release_check.py` | 登记新套件进 `CORE_TESTS` |
| `main_gui.py` / `README.md` / 两个 `.iss` | 仅版本号与 CHANGELOG |
| `AGENTS.md` | §5.4/§8 说明与陷阱条目 |

不改：`validator/dlt645_validator.py`（**现状已正确**：`校验和错误，期望0xXX`）、`protocol_registry.py`（GUI 映射按字段名子串，自动适配）、`dlt645_sim/`、其他协议解析器。

## 2. 现状与断点

```python
# dlt645_parser.py（现状）
@staticmethod
def check_frame(data: bytes) -> bool:
    if len(data) < 12: return False                        # ← 结构
    if data[0] != 0x68 or data[7] != 0x68 or data[-1] != 0x16: return False   # ← 结构
    return (sum(data[0:-2]) & 0xFF) == data[-2]            # ← 校验

def parse(data):
    if not DLT645Parser.check_frame(data):      # ← 断点：三者混判 + 提前 return
        result['error'] = '无效的DLT645帧格式'
        return result                            # fields 为空 → GUI 空白
```

**结构与校验是两类不同性质的判据**：结构不符 → 字段定位不可靠（但长度 ≥12 仍可尝试）；校验不符 → 内容可正常解析，只是完整性存疑。混判导致后者的完整信息被丢弃。

## 3. 设计决策

### D1 判据拆分（保持向后兼容）

```python
@staticmethod
def check_structure(data: bytes) -> Tuple[bool, str]:
    """结构判据（不含 CS）：长度 / 双 68H / 结束 16H。返回 (ok, 中文原因)"""
    if len(data) < 12:
        return False, f"帧长不足 12 字节（实际 {len(data)}）"
    if data[0] != 0x68 or data[7] != 0x68:
        return False, (f"帧起始符错误：第1字节应 68H（实际 {data[0]:02X}H）、"
                       f"第8字节应 68H（实际 {data[7]:02X}H）")
    if data[-1] != 0x16:
        return False, f"帧结束符错误：末字节应 16H（实际 {data[-1]:02X}H）"
    return True, ""

@staticmethod
def calc_checksum(data: bytes) -> int:
    """正确的校验和 = 起始符 68H 到数据域最后 1 字节的算术和 & 0xFF"""
    return sum(data[0:-2]) & 0xFF

@staticmethod
def check_frame(data: bytes) -> bool:
    """结构 + 校验全部通过（保留给既有调用方/外部）"""
    ok, _ = DLT645Parser.check_structure(data)
    return bool(ok) and DLT645Parser.calc_checksum(data) == data[-2]
```

**为什么保留 `check_frame`**：它是既有公开静态方法（测试与外部可能调用）；语义不变（结构+校验），只是内部复用新函数。

### D2 `parse()` 去掉提前 return，分级降级

```python
struct_ok, struct_err = DLT645Parser.check_structure(data)
if len(data) < 12:                       # 连长度都不够：无法定位字段（R4 降级）
    result['valid'] = False
    result['error'] = f"帧长度不足（{len(data)} 字节，最短 12 字节），无法定位完整字段"
    result['fields'] = [
        ('❌ 帧长度不足', f"{len(data)} 字节",
         'DL/T645-2007 最短帧：68H + 地址6B + 68H + 控制码 + 数据长度 + CS + 16H = 12B'),
        ('原始数据', data.hex().upper(), f"{len(data)} 字节"),
    ]
    return result
# —— 长度 ≥12：无论结构与校验是否通过，一律继续解析（R1/R2/R3）——
cs_actual = data[-2]
cs_expected = DLT645Parser.calc_checksum(data)
cs_ok = cs_actual == cs_expected
```

随后沿用既有解析流水线（地址/控制码/数据域减 0x33/DI 查表/深度解析），只在三处增强：

1. **结果字段**（供 GUI/摘要/测试）：
   ```python
   result['structure_valid'] = struct_ok
   result['structure_error'] = struct_err      # 仅 structure_valid 为 False 时非空
   result['checksum'] = cs_actual
   result['checksum_expected'] = cs_expected   # 新增：正确值
   result['checksum_valid'] = cs_ok
   ```
2. **`valid` 语义保持不变（R5，关键）**：
   ```python
   result['valid'] = struct_ok and cs_ok and not result['data_length_mismatch']
   ```
   即「结构 OK + 校验 OK + 长度相符」才为 True —— `dlt645_sim/engine.py:115` 与 `dlt645_meter_sim_widget.py:544` 都用 `parsed.get("valid", True)` 拒收坏帧，语义必须不变，否则虚拟表开始接受坏帧（A8 钉住）。
3. **提示行**（插在既有 `数据长度错误` 行之后、`数据标识 DI` 行之前）：
   ```python
   if not struct_ok:
       result['fields'].append((
           '❌ 帧结构错误', '', struct_err,
           '按帧内假定位置继续解析；结构不符时字段归属可能不准，请核对原始报文'))
   if not cs_ok:
       result['fields'].append((
           '⚠ 校验和错误', f"帧内 {cs_actual:02X}H", f"应为 {cs_expected:02X}H",
           f"CS = 起始符 68H 到数据域最后 1 字节的算术和 & 0xFF = 0x{cs_expected:02X}；"
           '帧内值不符，以下字段仍按帧内实际内容解析'))
   ```
   **行名必须含「校验和」**（R7）：`protocol_registry.DLT645GuiParser` 的偏移映射用字段名子串匹配（`elif "校验和" in field: byte_start = total_len - 2`）→ 自动高亮到 CS 字节，无需改 GUI。
   **文案对齐南网先例**（`protocol_parser.py:878` 的「期望 0xXX，实际 0xYY」措辞），并额外给出**计算规则**（用户明确要求"把校验和计算好，提示正确校验是什么"）。
4. **既有行的信息增强**：
   - `数据长度错误` 行补「应声明 {实际} 字节」（R2）
   - `校验和` 行：通过时显示 `CS校验通过`；不通过时显示 `应为 {cs_expected:02X}H（帧内值错误）`（与 `⚠` 行互补，作为字段级的自然位置）
   - `帧结束符` 行：非 `16H` 时显示实际值 + 提示

### D4 长度不符行的增强（R2）

现状 `('⚠ 数据长度错误', f"声明{X}B / 实际{Y}B", '…')` → 补「应声明 Y 字节」。

### D5 与 GUI/Web/批处理的关系

- `DLT645GuiParser.parse_to_table`（`protocol_registry.py:359`）：只遍历 `fields` → 自动显示新行 ✓（`校验和` 相关行映射到 CS 字节，结构错误行落到默认 0 字节）
- 深解析弹窗路径（`main_gui.py:10680`）以「长度≥12 且 68/68/16」为**路由**条件：仅用于把默认协议路由到 645 深解析；协议6 主显示路径不依赖它（按协议索引走 `DLT645GuiParser`）→ 结构坏帧仍能解析 ✓
- Web（`reflex_web.py:516` 用同款逻辑补字节范围）→ 同源 `fields` ✓
- 批处理：按行渲染 `fields`，此前坏 CS 帧得到空表、现在得到完整行 ✓ 改善（需在回归中确认无断言依赖旧的空表行为）

## 4. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| R-1 改变 `valid` 语义会让虚拟表接受坏帧 | **不改 `valid` 语义**（D2-2）+ A8 断言 + `test_dlt645_sim*.py` 全绿 |
| R-2 结构坏帧按假定位置解析产生误导性字段 | 插入「❌ 帧结构错误」行明确标注「字段归属可能不准」+ 保留原始 hex |
| R-3 既有测试断言了「坏 CS → 空 fields」 | 先全局检索此类断言；若有，属**预期行为变更**，按新行为更新并在 implement.md 记录理由 |
| R-4 批处理/摘要依赖旧空表语义 | 回归 `test_web_parse_fixes.py` 与桌面批处理用例；必要时同步 |
| R-5 新行名影响 GUI 偏移映射 | 行名含「校验和」→ 命中既有映射分支（R7），A9 钉住 |

## 5. 回滚

单文件产品改动（`dlt645_parser.py`）+ 新测试；无数据迁移、无接口破坏（新增字段只增不改）。回滚 = `git revert <commit>`。
