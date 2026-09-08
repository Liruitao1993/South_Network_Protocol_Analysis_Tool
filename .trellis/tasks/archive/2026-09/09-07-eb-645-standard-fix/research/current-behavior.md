# Research: EB 645 帧生成器现状（代码定位 + 实测复现）

- **Query**: 复核并补全 GUI / Web 两处 EB 645 构帧代码的 file:line，确认 CS 计算范围、+0x33 加扰、DI 传输序三项口径，并实测其产物在本工具解析器/校验器下的判定结果
- **Scope**: internal
- **Date**: 2026-09-07
- **Task**: `.trellis/tasks/09-07-eb-645-standard-fix`（parent: `09-07-dlt645-frame-gen`，status: planning）

---

## 1. 结论速览

当前生成器与 DL/T645-2007 相比存在 **3 处**偏差，而不是任务描述中的 2 处：

| # | 偏差项 | 现状 | DL/T645-2007 要求 | 是否在本任务 PRD 范围内 |
|---|---|---|---|---|
| 1 | CS 计算范围 | `sum(body)`，`body = C + L + DATA`，**不含帧头 `68 A0..A5 68`** | §5.2.6：**从第一个帧起始符（68H）开始**到校验码之前所有字节的模 256 和 | ✅ 在范围内 |
| 2 | 数据域加扰 | **未 +0x33**，DI 与数据原样上线 | §5.2.5：发送方按字节 **加 33H**，接收方按字节减 33H | ✅ 在范围内 |
| 3 | **DI 传输序** | `bytes.fromhex(di)`，即 `EB030002 → EB 03 00 02`（**DI3 在前 / 高字节先传**） | §5.3.2：所有数据项**先传送低位字节**，即 `EB030002 → 02 00 03 EB`（DI0 在前） | ❌ **PRD 未提及，需用户决策** |

> 偏差 #3 是本次研究的新发现，直接影响「修正后能否被本工具 645 解析页正确识别 DI」。详见 `doc-requirements.md` §3 与 `impact-and-tests.md` §5。

另有 1 处**非缺陷**的确认项：地址域 A0~A5 直接按用户输入 hex 顺序上线（不反转），与 GUI 标签「地址域A0~A5(hex)」/ tooltip「12位hex（6字节）」语义一致，符合 645「A0 为低字节、低字节先传」的规定，**无需改动**。

---

## 2. GUI 侧代码定位（`frame_gen_widget.py`）

### 2.1 核心构帧函数 `_build_eb_645_frame`

`frame_gen_widget.py:961-975`

```python
961	    def _build_eb_645_frame(self) -> bytes:
962	        """生成 EB 数据标识 645 帧: 68 A0..A5 68 C L DI3 DI2 DI1 DI0 DATA CS 16"""
963	        di = self._eb_current_di
964	        if not di or not di.startswith("EB") or len(di) != 8:
965	            raise ValueError("请先选择 EB 数据标识（如 EB030002）")
966	        ctrl = int(self.eb_ctrl_combo.currentData(), 16)
967	        data = bytes.fromhex(self.eb_data_edit.text().replace(" ", "")) if self.eb_data_edit.text().strip() else b""
968	        addr = bytes.fromhex(self.eb_addr_edit.text().replace(" ", ""))
969	        if len(addr) != 6:
970	            addr = addr[:6].ljust(6, b'\x00')
971	        di_bytes = bytes.fromhex(di)                     # ← 偏差 #3：未反转 DI
972	        data_len = len(di_bytes) + len(data)
973	        body = bytes([ctrl, data_len]) + di_bytes + data  # ← 偏差 #2：payload 未 +0x33
974	        cs = sum(body) & 0xFF                            # ← 偏差 #1：CS 不含帧头
975	        return bytes([0x68]) + addr + bytes([0x68]) + body + bytes([cs, 0x16])
```

- `:962` docstring 自述帧结构为 `DI3 DI2 DI1 DI0`，与 `:971` 的 `bytes.fromhex(di)` 一致（字符串首字节 `EB` 被当成先传的 DI3），即**明确采用高字节先传**。
- `:974` 的 `body` 从控制码开始，**没有把 `:975` 拼接的 `bytes([0x68]) + addr + bytes([0x68])` 计入**。

### 2.2 相关上下文

| 位置 | 说明 |
|---|---|
| `frame_gen_widget.py:677` | 注释：「EB 数据标识 645/698 帧生成器（协议7 国网 52H-F1/56H-F2 报文内容辅助）」 |
| `frame_gen_widget.py:679-686` | `EB_CTRL_OPTIONS`：91/11/14/94/81/01，默认第一项 `91` |
| `frame_gen_widget.py:716` | 承载格式下拉项文案：**「645 帧（68 封装）」**（任务中提到的「68 封装」即此处） |
| `frame_gen_widget.py:740-744` | `地址域A0~A5(hex)` 标签 + `QLineEdit("000000000000")` + tooltip「12位hex（6字节）」 |
| `frame_gen_widget.py:746-749` | `数据内容(hex)` 输入框，placeholder「可留空，如 01 01 112233445566」 |
| `frame_gen_widget.py:904-906` | 字段表单仅在 `fmt == "698"` 时启用；**645 分支没有字段表单编码**，只吃裸 hex |
| `frame_gen_widget.py:977-1017` | `_build_eb_698_frame`（委托 `reflex_web/frame_gen_utils.build_eb_698_frame`） |
| `frame_gen_widget.py:1019-1035` | **`_gen_eb_frame` 分发器**：`fmt == "698"` → `_build_eb_698_frame()`，否则 → `_build_eb_645_frame()` |
| `frame_gen_widget.py:1037-1065` | `_apply_eb_to_content`：把 `self.eb_gen_frame` 写入国网命令 schema 中名为「报文内容」的字段（找不到则退回第一个 `type == "bytes"` 字段） |
| `frame_gen_widget.py:1072-1077` | `reset_eb_generator` |

> **GUI 侧的 645/698 职责已经是分离的**：`_gen_eb_frame`（分发）→ `_build_eb_645_frame` / `_build_eb_698_frame`（纯 645 / 纯 698）。改 `_build_eb_645_frame` **不会**波及 698 分支。

---

## 3. Web 侧代码定位（`reflex_web/reflex_web/reflex_web.py`）

### 3.1 核心构帧函数 `gen_eb_645_frame`

`reflex_web/reflex_web/reflex_web.py:1550-1598`

```python
1550	    def gen_eb_645_frame(self):
1551	        """生成 EB 数据标识 645 帧: 68 A0..A5 68 C L DI3 DI2 DI1 DI0 DATA CS 16
1552	
1553	        645 数据标识为 4 字节小端（DI3 DI2 DI1 DI0 = EB XX XX XX），
1554	        EB 数据标识字符串如 "EB030002" → 帧内字节 EB 03 00 02。
1555	        """
1556	        if self.gen_eb_format == "698":
1557	            return self._gen_eb_698_frame()          # ← Q5：函数名与职责不一致
...
1564	        di = self.gen_eb_di.strip()
1565	        if not di or not di.startswith("EB") or len(di) != 8:  # 校验
...
1570	            ctrl = int(self.gen_eb_ctrl, 16)
1571-1575	        data_bytes = bytes.fromhex(...) or b""
1576-1578	        addr_bytes = bytes.fromhex(self.gen_eb_addr...); 补齐/截断到 6 字节
...
1583	        # DI 字节: "EB030002" → EB 03 00 02
1585	            di_bytes = bytes.fromhex(di)              # ← 偏差 #3
...
1590	        data_len = len(di_bytes) + len(data_bytes)
1591	        body = bytes([ctrl, data_len]) + di_bytes + data_bytes   # ← 偏差 #2
1592	        cs = sum(body) & 0xFF                                   # ← 偏差 #1
1593	        frame = bytes([0x68]) + addr_bytes + bytes([0x68]) + body + bytes([cs, 0x16])
1594	        self.gen_eb_frame = frame.hex()
1595-1598	        # 查名称 + 设置成功提示「点击「填入报文内容」写入透明转发字段」
```

- `:1553` docstring 自称「4 字节**小端**」，但 `:1554` 举例 `EB030002 → EB 03 00 02` 实为**大端**（字符串顺序直译）。注释本身自相矛盾，属于既有文档缺陷。
- 与 GUI `:971-975` 逐行等价（同样的 4 步），是**复制粘贴的第二份实现**。

### 3.2 相关上下文

| 位置 | 说明 |
|---|---|
| `reflex_web.py:167` | 注释：「EB 数据标识 645 帧生成器（协议7 透明转发/事件上报报文内容辅助）」 |
| `reflex_web.py:171-176` | 状态字段：`gen_eb_ctrl="91"`、`gen_eb_addr="000000000000"`、`gen_eb_data=""`、`gen_eb_frame=""`、`gen_eb_msg`、`gen_eb_msg_type` |
| `reflex_web.py:178` | `gen_eb_format: str = "645"`（645 / 698 开关） |
| `reflex_web.py:1463-1473` | `set_eb_ctrl` / `set_eb_addr` / `set_eb_data` |
| `reflex_web.py:1475-1487` | `set_eb_format` |
| `reflex_web.py:1600-1670` | `_gen_eb_698_frame`（698 分支实体） |
| `reflex_web.py:1672+` | `apply_eb_frame_to_content`：写入第一个 bytes 类型字段（「报文内容」） |
| `reflex_web.py:5647-5653` | UI「生成帧」按钮 `on_click=State.gen_eb_645_frame` — **645 与 698 共用同一入口** |
| `reflex_web.py:5654-5659` | UI「填入报文内容字段」按钮 `on_click=State.apply_eb_frame_to_content` |

> **Web 侧 645/698 职责未分离**：`gen_eb_645_frame` 在 `:1556-1557` 直接转调 `_gen_eb_698_frame`。详见 §6。

### 3.3 是否存在第三处共享实现？

**不存在。** 全仓搜索结果：

| 文件 | 是否含 645 构帧 | 备注 |
|---|---|---|
| `frame_gen_widget.py:961-975` | ✅ 产品代码 | GUI 实现 |
| `reflex_web/reflex_web/reflex_web.py:1550-1598` | ✅ 产品代码 | Web 实现（与 GUI 重复） |
| `reflex_web/frame_gen_utils.py` | ❌ **无 645 构帧** | 全文只有 698：`build_dlt698_sa(:256)`、`build_dlt698_axdr_apdu(:324)`、`build_eb_698_apdu(:474)`、`build_eb_698_frame(:560)`。模块 docstring `:1-19` 明确定位为「协议组帧纯逻辑模块（Reflex Web 版）…不依赖 Reflex / Qt…可被独立测试脚本断言字节与 GUI 生成器一致」 |
| `gdw_send_frame_lib.py` / `send_frame_lib.py` | ❌ | 全仓 `bytes([0x68])` 搜索无命中 |
| `dl_t698_45_frame_gen.py:47` | ❌ | 698 链路层 |
| `test/test_gdw_fujian.py:47-51`、`:364-374` | ⚠️ **测试内 2 份副本** | `make_645_frame`、`_build_eb_645_frame_logic`，同样是非标准口径 |
| `test/test_dlt645_lme.py:31-43` | ✅ **标准口径参考实现** | `build_frame` / `build_frame_raw`：`enc = (b+0x33)`、`body = 68 + addr + 68 + ctrl + len + enc`、`cs = sum(body)`（**含帧头**）——这是仓内唯一符合标准的 645 构帧助手 |
| `test/test_nw_lcmi.py:41-44` | ❌ | 南网 376.2 外层帧，无关 |

**架构建议线索**（供 implement 参考，非本研究结论）：`reflex_web/frame_gen_utils.py` 已经是 GUI 与 Web 共享的纯逻辑模块（GUI `_build_eb_698_frame:996` 就是 `from frame_gen_utils import build_eb_698_frame`）。把 645 构帧抽成 `frame_gen_utils.build_eb_645_frame()` 可一次性消除 GUI/Web/test 三份副本，且天然可被 `test_web_frame_gen_utils.py` 直接断言。

---

## 4. 打包/构建残留副本（**可忽略，但需标注**）

| 路径 | 命中 | 性质 |
|---|---|---|
| `dist/reflex_web_embedded/frame_gen_widget.py:974` | `cs = sum(body) & 0xFF` | PyInstaller/Reflex 打包产物 |
| `dist/reflex_web_offline/frame_gen_widget.py:993` | 同上 | 打包产物 |
| `dist/reflex_web_embedded/reflex_web/reflex_web/reflex_web.py` | 含 `gen_eb_645_frame` | 打包产物 |
| `dist/reflex_web_offline/reflex_web/reflex_web/reflex_web.py` | 同上 | 打包产物 |
| `dist/reflex_web_embedded.zip` / `.rar`、`dist/reflex_web_embedded_win64.zip` | — | 归档产物 |
| `_tmp_test/_MEI632282/`（110 项） | **搜索 `_build_eb_645_frame` / `gen_eb_645_frame` 0 命中** | PyInstaller 运行时解包残留，无源码副本 |
| `_tmp_test/_MEI16802/`、`_MEI177442/`、`_MEI48642/` | 空目录 | 残留 |
| `repomix-output.md`（23MB，L299246 / L299563 / L327867 / L342853） | 全仓快照 | 生成物，非源码 |

**结论**：以上全部为构建/快照产物，**不应手工修改**，改完源码后由打包流程重新生成。

---

## 5. 实测复现（真实运行结果，非推演）

运行方式：`python -B`（禁用 bytecode 写入），直接 import 本仓 `DLT645Parser` / `DLT645Validator` / `GDW10376Parser`。

固定输入：`DI="EB030002"`、`ctrl=0x81`、`addr="000000000000"`、`data="01 01 11 22 33 44 55 66"`（与 `test_gdw_fujian.py:379` / `test_web_frame_gen_utils.py:343-345` 完全一致）

| 变体 | 帧 hex | `DLT645Parser.parse().valid` | 解析出的 `di_code` | `DLT645Validator.verify().valid` |
|---|---|---|---|---|
| **A = 当前生成器**（无加扰 / CS 不含帧头 / DI 高字节先） | `6800000000000068810CEB0300020101112233445566E416` | **False** | —（提前返回） | **False** |
| **B = PRD 口径**（+0x33 / CS 含帧头 / DI 顺序不动） | `6800000000000068810C1E36333534344455667788991816` | **True** | **`020003EB`（未知数据标识）** | **True** |
| **C = 完整标准**（+0x33 / CS 含帧头 / DI 低字节先） | `6800000000000068810C3533361E34344455667788991816` | **True** | **`EB030002`** ✅ | **True** |

- 变体 A 的 hex 与任务描述中给出的实测帧**逐字节一致**，现状复核通过。
- 变体 A 的失败原因：`dlt645_parser.py:39` `cs = sum(data[0:-2]) & 0xFF` 覆盖整帧头 → 与帧内 `E4` 不符 → `check_frame` 返回 False → `:63-65` 直接返回 `valid=False, error='无效的DLT645帧格式'`。`validator/dlt645_validator.py:43-64` 同理（`:46` `cs_data = frame_bytes[0:cs_pos]`）判「校验和错误」。
- **变体 B 的关键副作用**：`valid=True` 但 `di_code = "020003EB"`。原因见 `dlt645_parser.py:105`：

```python
105	            di_val = int.from_bytes(result['data'][0:4], byteorder='little')
106	            di_code_str = f"{di_val:08X}"
```

  减 33H 后得到 `EB 03 00 02`，按小端合成 = `0x020003EB`。也就是说**只做 PRD 的两项修正，645 解析页仍会把 DI 显示为「未知数据标识」**，达不到「口径修正为标准 DL/T645-2007」的验收直觉。

---

## 6. Q5 核实：`gen_eb_645_frame` 名实不符

**确认成立。**

```python
# reflex_web/reflex_web/reflex_web.py
1550	    def gen_eb_645_frame(self):
1556	        if self.gen_eb_format == "698":
1557	            return self._gen_eb_698_frame()
```

调用方共 3 处，其中 2 处走的是 698 分支：

| 调用点 | 实际分支 |
|---|---|
| `reflex_web.py:5650` UI「生成帧」按钮 `on_click=State.gen_eb_645_frame` | 取决于 `gen_eb_format` 运行时值（645 或 698） |
| `test/test_web_frame_gen_utils.py:346`（`test_eb_645_generator`） | **645** |
| `test/test_web_frame_gen_utils.py:410`（`test_eb_698_full_frame`，`:405` 先 `set_eb_format('698')`） | **698** |
| `test/test_web_frame_gen_utils.py:475`（`test_eb_698_full_frame` 字段表单段，`:467` 先 `set_eb_format('698')`） | **698** |

**是否需要拆分以免误改 698 分支？**

- **技术上不必须**：645 逻辑位于 `:1558-1598`，698 逻辑在 `:1556-1557` 提前 return 后完全隔离；只改 `:1583-1593` 不会触碰 698。
- **但强烈建议拆分**，理由：
  1. `:1551-1554` 的 docstring 描述的是 645 帧结构，却被 698 路径复用，改 645 docstring 时容易连带误导；
  2. 若后续要加「不加扰」开关（见 `impact-and-tests.md` §6 待决策项），开关只应作用于 645，混在一起易泄漏到 698；
  3. GUI 侧已经是 `_gen_eb_frame`(分发) + `_build_eb_645_frame`(纯 645) 的干净结构（`frame_gen_widget.py:1019-1035`），Web 侧对齐后两端可读性一致；
  4. 拆分若改函数名，**必须同步 3 处调用点**：`reflex_web.py:5650`、`test_web_frame_gen_utils.py:346`、`:410`、`:475`（共 4 处引用）。
- **最小侵入替代方案**：保留 `gen_eb_645_frame` 作为分发入口（不改名、不动 UI 绑定），把 `:1558-1598` 的实体抽为 `_gen_eb_645_frame_body()` 或直接抽到 `frame_gen_utils.build_eb_645_frame()`。这样 0 处调用点需要改。

---

## Caveats / Not Found

1. **仓内无真实抓包的 EB 内层 645 帧可对照**。`CCO-2-COM3-260628-124120 - 复制.log`（32MB）用 `Select-String` 搜索 `EB 03 00 02` / `EB 04 02` / `1E 36 33`（加扰 MSB-first）/ `35 33 36`（加扰 LSB-first）**全部 0 命中**。因此「真实设备到底发不发 +0x33」只能靠文档口径推断（见 `doc-requirements.md`），无法用抓包交叉验证。
2. 变体 B/C 的 `di_code` 结论依赖 `dlt645_parser.py:105` 的小端合成，已用实际运行验证，非静态推断。
3. 本研究**未修改任何产品代码或测试代码**；所有实测均通过 `python -B -c` 内联脚本完成（`-B` + `PYTHONDONTWRITEBYTECODE` 避免产生 `__pycache__`）。
