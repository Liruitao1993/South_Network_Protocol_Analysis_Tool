# Design — HDC 1.0 应用层未识别内容收口

## 1. 改动边界

| 文件 | 改动性质 |
| --- | --- |
| `hdc10_parser.py` | 主战场：类型值域常量、`_parse_msdu_payload` 分派、`_parse_app_only` 收口、`_parse_app_payload` fallback 呈现、`_parse_application_layer` 安全模式提示 |
| `main_gui.py` | `_GW_APP_META_FIELDS` 补新提示行（防挤占摘要关键字段）+ `CHANGELOG` + 版本号 |
| `reflex_web/reflex_web/web_utils.py` | 同上黑名单，与桌面逐字一致 |
| `test/test_hdc10_app_dispatch.py` | 新增测试套件 |
| `release_check.py` | 新增套件登记进 `CORE_TESTS` |
| `AGENTS.md` / `README.md` / 两个 `.iss` | 文档与版本同步 |

不改：`hdc10_mme_parser.py`（MME 内部）、抄表 DATA 内嵌解析、`validator/`。

## 2. 现状数据流与断点

```
MPDU ──_parse_pb_block──> PB 体 ──_parse_mac_frame──> MAC 头 ──> msdu_type(标准头byte7/单跳头byte1)
                                                        │
                                                        └─> _parse_msdu_payload(msdu_body, ..., msdu_type)
                                                              ├─ msdu_type==0 ──> MME 解析          ✅
                                                              ├─ first in (0x11,0x12,0x1A) ──> 应用层 ✅（但判据错）
                                                              └─ 其余 ──> 「未定义(厂商扩展)」      ❌ 断点3

app 级别入口: _parse_app_only(data)
    ├─ data[0] in (0x11,0x12,0x1A) ──> _parse_application_layer   ✅
    ├─ _detect_fc(data) ──> 完整帧解析                            ✅
    └─ 其余 ──> 「未识别格式的应用层数据」                        ❌ 断点2

_parse_application_layer(data)   ← 对任意端口都能解析通用头（自身无缺陷）
    └─ _parse_app_payload(payload, ..., biz_id, port)
          ├─ 0x001..0x0A3 命中 ──> 各业务解析器                    ✅
          └─ 其余 ──> 「未识别的业务数据(0xXXX)」                  ❌ 断点1
```

**三个断点，对应 P1-3 / P1-4 / P0**：判据用错字段（断点3）、白名单挡在通用头之前（断点2）、fallback 不查名字表（断点1）。

## 3. 设计决策

### D1 类型值域单一来源（R5）

靠近现有 `MSDU_TYPES`(:115) / `SINGLEHOP_MSG_TYPES`(:128) 新增：

```python
# 应用层报文的类型值：表10 标准MAC头=48(0x30)，表13 单跳帧头=128(0x80)
APP_MSDU_TYPES = frozenset({48, 128})
# IPv4 报文的类型值：表10=49(0x31)，表13=129(0x81)
IPV4_MSDU_TYPES = frozenset({49, 129})
```

**理由**：两套表的值域不同（48 vs 128），散落在各判断点必然漂移；集中成两份 frozenset 后，分派与测试共用同一来源。

### D2 `_parse_msdu_payload` 分派顺序（R3，断点3）

```python
if msdu_type == 0:                       # 表10/表13 的 0 → MME（保持不变）
    ...MME...
elif msdu_type in APP_MSDU_TYPES:        # 新增：MAC 头已声明是应用层 → 直接按应用层解析
    ..._parse_application_layer...
elif msdu_type in IPV4_MSDU_TYPES:       # 新增：明确提示（本次不实现 IPv4 载荷解析）
    ...「IPv4报文」提示行 + 原始数据...
elif msdu_type is None:                  # 回退：无头上下文时才用首字节启发式
    ...现状：first==0x00→MME；first in (0x11,0x12,0x1A)→应用层...
else:                                    # 其余：现状「未定义」分支（文案补上声明类型）
    ...
```

**关键权衡**：把 `msdu_type in APP_MSDU_TYPES` 提到启发式之前，会让「MAC 头声明应用层、但内容是填充/随机数据」的帧也进入应用层解析。评估后可接受：
- `_parse_application_layer` 有完整长度守卫，且 fuzz 已证 936 组合零崩溃（A9 复检）；
- 语义上这是**正确**行为（以 MAC 头声明为准），且对新增端口/biz_id 的呈现比「未定义(厂商扩展)」更有信息量。

**为什么顺序是 MME → app → IPv4 → None → 其他**：`msdu_type == 0` 在两张表里都是 MME 语义（表10「网络管理消息」/表13「发现列表消息」，后者经 MMTYPE=0x0008 也在 MME 树内解析），保持首位以最小化回归面。

### D3 `_parse_app_only` 收口（R2，断点2）

`app` 级别是用户**显式声明输入就是应用层**，不应再由端口值二次否决。判据改为「像不像通用头」：

```python
def _parse_app_only(self, data):
    if len(data) < 4:
        return [("❌ 应用层报文", "", "", "长度不足4字节(端口+报文ID+控制字)", ...)] + 原始数据行
    has_fc = self._detect_fc(data)
    if data[0] in APP_PORTS or (data[3] == 0 and not has_fc):
        return self._parse_application_layer(data, 0)
    if has_fc and len(data) > 16:                  # 误粘整帧的既有兜底，保留
        return self.parse_to_table(data, parse_level="auto")
    return self._parse_application_layer(data, 0)  # 新增兜底：按应用层解释并注明推测
```

**权衡**：`data[3] == 0` 作为弱校验（规范 §5.2.4「报文控制字默认设置为 0」）。它把「非白名单端口但控制字合规」的帧收进应用层解析（修掉 A3），同时保留「误粘完整 MPDU」走 FC 的既有体验（A6）。

**实现期修正（已实测，留档）**：字面按 D3 写（弱校验先于 FC 检测）会让**合法完整 MPDU** 被错位按应用层解析 —— FC 的 `byte3` 是**网络标识(NID)高字节**，取 0 的概率约 1/256，并非「控制字」。故弱校验收紧为 `data[3] == 0 and not has_fc`，并新增断言 A6d（NID 高字节=0 的完整 MPDU 仍走 FC 路径）钉住。**变异 7.5**（去掉 `and not has_fc`）已实际观察到 A6d 变红，属于真实的判据回退防护。

### D4 fallback 升级为「已命名但格式未定义」（R1，断点1；覆盖 P0-1/P0-2）

**不新增 0x0A0/0x0A4 专用分支**，而是改造 fallback 本身：

```python
else:
    name = MSG_ID_NAMES.get(msg_id)          # 单一来源；biz_id 与表 key 同口径
    if name:
        行1: f"  {name}"       说明=f"业务ID 0x{msg_id:03X}：{name}"
        行2: "    ⚠ 格式未定义" 说明="本规范（第4-3部分 表2）未给出该报文的字段格式，以下为原始数据"
        行3: 原始数据 hex 行
    else:
        现状「未识别的业务数据(0x{msg_id:03X})」+ 补「未在本规范报文ID表中定义」
```

**理由**：0x00A0/0x00A4 的名字本就已在 `MSG_ID_NAMES`(:159)，查表即自动受益；将来规范新增命名也自动跟随（避免第二次遗漏）。**这正是 P0 缺陷的根因**——名字表与分派链是两份手写清单，只有让 fallback 查表才能消除漂移。

### D5 安全模式提示（R4，P1-5）

在 `_parse_application_layer` 的「安全模式」行之后插入（仅 `sec_mode != 0`）：

```python
table.append(("  ⚠ 安全保护", f"0x{sec_mode:X}", SECURITY_MODES.get(sec_mode, f"保留({sec_mode})"),
              "数据域受信道安全机制保护，以下按明文解析的字段可能无效",
              base_offset + 1, base_offset + 2))
```

**为什么不直接跳过业务解析**：按 AGENTS.md 陷阱 23，用户点解析就必须看到内容——保留解析 + 醒目提示，比只报「加密无法解析」信息量更大（字段结构/长度仍可参考）。

**摘要影响（陷阱 44 必须处理）**：该行位于 `── 应用层报文 ──` 区、且在 `── 业务数据 ──` 区**之前**，按 `_gw_app_biz_summary` 的窗口规则（起点=业务数据区头 +1）**本就在扫描窗口外**；但为防将来窗口扩展，仍把「⚠ 安全保护」加入两端的 `_GW_APP_META_FIELDS` 黑名单（`startswith` 方向注意：黑名单是前缀匹配，故用 `"⚠ 安全保护"` 完整前缀）。

### D6 兼容与不变式

- `_parse_app_payload(biz_id, port)` 的调用语义不变；`sec_mode` 只影响新增提示行，不参与分派（A7 对拍）。
- 已知业务的字段值/行序/偏移一律不动（R6）——用「改动前后同帧逐行对拍」验证（见 implement 步骤 0）。
- 新逻辑全部为**纯函数式分支**，不引入实例状态（R8 陷阱 41）。

## 4. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| R-1 改 MSDU 判据后，真实帧解析结果与现状不同（填充帧进入应用层解析） | 步骤 0 先对拍：记录 60 帧在改动前后的完整表格差异，逐帧确认差异都是「更明确」而非「错位」 |
| R-2 新增提示行挤占摘要关键业务字段（陷阱 44） | 黑名单两端同步 + `test_gw_app_summary_detail.py` 回归 + 新增断言 |
| R-3 端口收口后，误粘完整 MPDU 的体验回归 | A6 显式覆盖：`_detect_fc` 路径保留，且放在应用层弱校验之后 |
| R-4 桌面/Web 摘要漂移（陷阱 31/44） | 两份实现逐字同改 + 对拍断言 |
| R-5 测试误把填充帧的「未定义」当缺陷 | A8 只用 `key[1] != '-'` 的真实业务帧做断言；填充帧只断言「不抛异常」 |

## 5. 回滚

单提交、无数据迁移、无接口变更。回滚 = `git revert <commit>`。新增测试与常量可整体移除，不影响其它协议。
