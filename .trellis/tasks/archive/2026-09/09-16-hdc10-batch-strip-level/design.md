# 设计：HDC 1.0（协议11）批量解析前缀剥离的级别来源与 app 端口判据

## 1. 缺陷链（现状）

```
用户粘贴日志行 → _prepare_batch_input (main_gui.py:7356)
  └─ current_protocol == 11
      └─ _strip_gw_new_gen_prefix(text)                     ← main_gui.py:7383
          └─ parse_level = getattr(self, "_gw_parse_level") ← 4781  ← 读到协议10 的值（缺陷 A）
              └─ if parse_level == "app":
                  └─ 只认 hex "11" 的偶字节位置             ← 4853  ← 丢弃端口 0x12 帧（缺陷 B）
                      └─ 全部丢弃 → 返回 ""
                          └─ _clean_hex_input("") == ""
                              └─ 弹「预处理后未保留有效报文内容！」(main_gui.py:7449)
```

协议11 界面上「解析级别」下拉显示的是 `_hdc10_parse_level`（`main_gui.py:3330`），所以用户看到「自动识别」而系统按 app 过滤——**界面值与生效值分裂**。

同时发现：即便用户在协议11 下真的选「应用层报文(app)」，因缺陷 A，strip 读到的仍是协议10 的值 → **协议11 的级别对批量前缀剥离完全无效**（双向分裂）。

## 2. 设计决策

### D1 级别来源：函数内自取，与解析侧同源（消除分裂）

`_strip_gw_new_gen_prefix` 增加 `parse_level` 形参，默认 `None` 表示「按当前协议自取」：

```python
def _strip_gw_new_gen_prefix(self, text: str, parse_level: Optional[str] = None) -> str:
    ...
    if parse_level is None:
        # 与真正用于解析的级别同源（协议11 → _hdc10_parse_level，协议10 → _gw_parse_level）
        parse_level = self._current_parse_params().get("parse_level") or "auto"
```

- 复用 `_current_parse_params()`（`main_gui.py:4616-4655`）作为**唯一分派点**——它已按 `spec.parse_level_family` 正确取 `hdc10` / `gw` 族级别，避免在 strip 里再写第二份 `if current_protocol == 11` 分派。
- 保留显式形参：供测试与未来调用方覆盖，签名与 Web 侧 `strip_gw_new_gen_prefix(text, parse_level="auto")` 语义对齐（Web 侧无「自取」概念，必须显式传）。
- 调用点（`7383`、`7410`）**不传参**，行为随协议自动正确；`_current_parse_params()` 是纯读（不建 parser、不碰控件写），可在主线程安全调用。

### D2 app 端口判据：集合取自解析器端口表（不新增第三份硬编码）

现状「只认 `11`」是三处重复口径（桌面 strip、Web strip、解析器端口表）中的两处错误副本。改为**从解析器端口表派生**，使权威只有一处：

```python
# HDC 1.0 / 国网新一代应用层端口（hex 串）
# 依据：第4-3部分 应用层通信协议 §5.2.2「升级业务取值为 0x12，其他业务取值为 0x11」
# 权威来源：hdc10_parser.APP_PORTS / gw_new_gen_parser.PORT_NAMES（解析器表）
_GW_APP_PORT_PREFIXES_FALLBACK = ("11", "12", "1A")

def _gw_app_port_prefixes(protocol_index: int) -> tuple:
    try:
        if protocol_index == 11:
            import hdc10_parser
            ports = hdc10_parser.APP_PORTS
        else:
            import gw_new_gen_parser
            ports = gw_new_gen_parser.PORT_NAMES
        return tuple(f"{p:02X}" for p in ports)
    except Exception:
        return _GW_APP_PORT_PREFIXES_FALLBACK
```

判定处由 `hex_clean[i:i+2] == "11"` 改为 `hex_clean[i:i+2] in app_prefixes`（`app_prefixes` 在函数入口按 `self.current_protocol` 算一次，避免循环内重复 import）。

- 惰性 import：`main_gui` 顶层不新增依赖；`hdc10_parser` / `gw_new_gen_parser` 均为纯逻辑模块（无 PySide6），Web 侧 `web_utils` 同样可 import（其已把项目根加入 `sys.path`）。
- 兜底常量仅用于 import 失败路径（异常不该让 GUI 崩），主路径由测试对拍钉住「集合 == 解析器表」。
- **保持不变的语义**：偶数位置扫描、命中位置起剩余 ≥ 8 hex 字符、以命中位置截断。仅把「单值相等」换成「集合成员」。

### D3 两端同步：同一判据、同一来源、对拍钉住

- Web `reflex_web/reflex_web/web_utils.py::strip_gw_new_gen_prefix(text, parse_level="auto")`：app 分支同样改为集合成员判定，集合来源同 D2（按 `protocol_index` 细化需新增形参或在调用点传入端口集合）。
  - 方案取舍：Web 侧调用点在 `reflex_web.py:874-878` 已按协议分派。最小侵入做法是**给 Web 函数加 `protocol_index: int = 10` 形参**（默认 10 = 国网新一代），调用点分别传 `10` / `11`；不改变既有默认行为。
  - 备选（不采用）：把两端共用的端口集合提到新的共享模块——会新增跨端依赖文件，超出本次修复的必要范围（AGENTS §8 陷阱 31 的共享核心属 `09-15-web-shared-parse-core` 任务）。
- 对拍测试：同一输入 + 同级别下，桌面 `MainWindow._strip_gw_new_gen_prefix`（未绑定方法，Host 复用）与 Web `strip_gw_new_gen_prefix` 输出必须逐字符相等。

### D4 明确不动的部分（控制改动面）

| 不动项 | 理由 |
| --- | --- |
| 协议9 `_strip_csg_new_gen_frame_prefix` 的 app 判据（`main_gui.py:4972`、`web_utils.py:306`） | 南网新一代应用层端口定义与依据文档不同，需单独核对，属独立任务 |
| `_prepare_batch_input` 中清洗前后的**重复剥离**（7383 + 7410） | 去重属行为变更（行映射覆盖语义），本任务保持现状 |
| `_current_parse_params` / 解析器 / 摘要逻辑 | 已正确，改动会扩大回归面 |
| `gw_parse_level_combo` 的共用控件设计 | 协议10/11 共用一处下拉是既有 UI 设计；本任务只保证「取值分派正确」，不要求拆控件 |

## 3. 接口契约（改动前后）

| 位置 | 改动前 | 改动后 |
| --- | --- | --- |
| `MainWindow._strip_gw_new_gen_prefix` | `(self, text: str) -> str`，级别硬读 `_gw_parse_level` | `(self, text: str, parse_level: Optional[str] = None) -> str`；`None` → `_current_parse_params()["parse_level"] or "auto"` |
| `web_utils.strip_gw_new_gen_prefix` | `(text, parse_level="auto")`，app 只认 `11` | `(text, parse_level="auto", protocol_index=10)`，app 判据用端口集合 |
| `reflex_web.py` 调用点 | `strip_gw_new_gen_prefix(input_text, self.gw_parse_level)` / `(…, self.hdc10_parse_level)` | 追加 `protocol_index=10` / `11` |
| app 判据 | `hex_clean[i:i+2] == "11"` | `hex_clean[i:i+2] in ("11","12","1A")`（取自解析器表） |

**兼容性**：默认参数保证既有调用方（含测试里 `main_gui.py` 的 `7383/7410`、Web 既有调用）行为不变，只有「协议11 + 非 auto 级别」与「app 级别的 12/1A 帧」两处**从错误变正确**。

## 4. 数据流（修复后）

```
粘贴日志行
  → _strip_gw_new_gen_prefix(text, None)
      → parse_level = _current_parse_params()["parse_level"]   # 协议11 → auto（界面显示值）
      → 普通行：取最后一个冒号后的 hex（≥4 字符）
      → app 级别时：偶字节扫描端口集合 {11,12,1A} → 命中即截断
  → _clean_hex_input(keep_newlines=True)
  → _extract_frames_for_protocol（协议11 = line 策略：每行一帧）
  → BatchParseWorker → parse_one_frame → HDC10Parser.parse_to_table(parse_level=auto)
  → 摘要 [11]…（协议10/11 摘要走 _get_gw_new_gen_summary）
```

## 5. 验证策略

| 层级 | 手段 | 判据 |
| --- | --- | --- |
| 纯函数 | `test/test_hdc10_batch_strip_level.py` 直接调 `_strip_gw_new_gen_prefix(text, level)` | 各级别输出矩阵；app 下 `11/12/1A` 保留、其他起始丢弃 |
| 级别来源 | 同上（Host 复用 `MainWindow` 未绑定方法 + 极简宿主属性） | `_gw_parse_level="app"` 与 `"auto"` 在协议11 下输出相同；协议10 下仍按 `_gw_parse_level` 生效 |
| 端到端 | offscreen `MainWindow` + `parse_batch()` + `wait_batch(win)`（AGENTS §8 陷阱 40） | 20 行样本 → 20 帧、状态全「成功」、摘要含 `报文:0x0030` |
| 两端对拍 | 桌面 vs `web_utils.strip_gw_new_gen_prefix` | 同输入同级别输出逐字符相等 |
| 回归 | `test_gw_batch_parse.py` / `test_hdc10.py` / `test_web_parse_fixes.py` / `release_check.py` | 全绿、无 FAIL/WARN |
| 变异反证 | 临时把端口集合改回 `("11",)`、把级别来源改回 `_gw_parse_level` | 对应断言变红后还原（AGENTS §8 陷阱 38 要求） |
| 现场帧 | 用户 20 行真实日志行硬编码进测试 | 修复前该用例失败（已用 offscreen 脚本验证过失败路径） |

## 6. 回滚

改动集中在 3 个文件（`main_gui.py`、`reflex_web/reflex_web/web_utils.py`、`reflex_web/reflex_web/reflex_web.py`）+ 1 个新测试文件 + 文档。回滚 = `git revert` 该提交；无数据迁移、无持久化格式变化、无版本号以外的兼容影响。

## 7. 已知残余风险

- app 级别扫描仍是「全串偶字节扫描」，若数据域中恰好出现 `11/12/1A` 会被误截断——放宽端口集合使该理论风险略增（新增 `12`/`1A` 两个值）。缓解：app 级别只在用户**显式**选择时生效（默认 auto 不做任何截断）；若要彻底消除，应改为「按帧结构定位应用层起始」，属独立任务（拟记入 AGENTS 待办）。
- 端口集合依赖解析器端口表，若文档修订新增端口而解析器表未更新，两端会同时「保守」（不识别新端口）——比两端不一致更安全。
