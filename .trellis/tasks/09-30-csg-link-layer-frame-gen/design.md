# 协议9 链路层组帧 —— 技术设计

对应 `prd.md`。字段依据见 `research/01`、`research/02`；与解析器的位级契约见 `research/03`（**实现时以它为准**）。

---

## 1. 边界与模块划分

```
新增 csg_link_frame_gen.py        纯逻辑无 Qt：FC / PBH / MAC 头组帧 + 位打包工具
新增 collapsible_section.py       可复用折叠区组件（全仓现无此类组件，已确认）
改造 csg_test_frame_gen_widget.py 五层折叠表单 + 分层预览
改   frame_gen_widget.py          两处接线：预览行构造、层次选项联动
```

**为什么单独建 `csg_link_frame_gen.py` 而不塞进 `csg_new_gen_frame_gen.py`**：
后者已 812 行、覆盖应用层 24 模式；链路层（FC/PB/MAC）与应用的字段体系完全不同，混在一起会让两个测试文件都难以定位。新模块互相引用：`csg_link_frame_gen` 只依赖 `csg_new_gen_frame_gen`（复用 `build_app_frame` / `build_ed_frame` / `pack_bits` / `FrameBuildError`），反向不依赖 —— 保持既有模块的可测性。

**不做什么**（与 PRD 的 Out of Scope 一致）：不动 `csg_new_gen_parser.py` 的 11 个 `_parse_mpdu_*`（不改成声明式字段表驱动）。理由：那会改变已由 60 帧真实夹具锚定的解析行为，风险与收益不成比例；组帧是纯新增，用「回读对拍」即可保证一致。

---

## 2. 关键契约（实现必须遵守，逐条来自 research/03）

| # | 契约 | 违反后果 |
| --- | --- | --- |
| C1 | FC 字节0 **bit3（接入指示）= 1** | 解析器 `is_mpdu` 判否 → auto 完全不走 MPDU 路径 |
| C2 | FCCS = CRC-24(FC 字节 **0-12**)，小端 3B | 回读 FCCS 显示「校验失败」 |
| C3 | MAC 完整性校验 = CRC-32(**MSDU 载荷**)，小端 4B，不含 MAC 头 | 同上 |
| C4 | PBCS = CRC-24(PBH + 块体 + 保留1B)，小端 3B | 同上 |
| C5 | MSDU 头长由 MAC 帧头类型决定：0→18B / 1→2B | MSDU 头被当业务数据，整棵解析树错位 |
| C6 | MSDU 长度字段 = 实际 MSDU 字节数 | 回读 MSDU 长度不符，MAC 树错位 |
| C7 | TEI 12bit 按「低字节在前，低位在前」（`23 61 45` oracle） | 源/目的TEI 错位（协议11 曾整批踩过，陷阱 54） |
| C8 | PB 块体长 = PB总大小 − 8；不足零填充 | PBCS 计算范围错、回读 MP 长度不符 |
| C9 | 应用层帧 = 端口(1B) + 报文标识(2B,LE) + 保留(1B) + 业务报文 | 复用 `build_app_frame`，勿重写 |

---

## 3. 数据流（组装顺序，自内向外）

```
① MSDU 载荷        来源：测试模式 BDU→业务报文→应用层帧（复用 build_app_frame）
                   或：手工 HEX（优先）
② MSDU 头          VLAN + MSDU类型（长度随 MAC 帧头类型：18B / 2B）
③ MSDU             = ② + ①                      ← msdu_len = len(③)
④ MAC 帧头         按帧头类型组 32B / 12B；msdu_len 填入字节 2-3（小端）
⑤ MAC 帧           = ④ + ③ + CRC32(③)[小端4B]
⑥ PB 体            ⑤ 按块体大小切分并零填充（多 PB 时顺序切分）
⑦ PB               = PBH(4B) + 体 + 保留(1B) + CRC24(PBH+体+保留)[小端3B]
⑧ FC               = 固定部分 + 可变区域 + CRC24(FC[0:13])[小端3B]
⑨ MPDU             SOF：⑧ + Σ⑦ ｜ 信标：⑧ + 载荷 ｜ SACK：⑧
⑩（可选）ED 封装    复用 build_ed_frame(⑨ 或 应用层帧)
```

**每一步的关键点**
- ③ 的 `msdu_len` 必须在 ④ 之前确定 → **先生成 MSDU 再生成 MAC 头**（顺序不可颠倒）。
- ⑥ 块体大小不是 2 的幂也能切（136−8=128 / 520−8=512 / 264−8=256 / 72−8=64 / 16−8=8），**块体大小天然整除**：MAC 帧通常不足一块则单块 + 补零。
- ⑨ 的形态随定界符类型变化：**信标无 PBH、SACK 无 PB/MAC/MSDU**（research/03 §7）。

---

## 4. 位打包：新增与解析侧严格互逆的 `put_bits_le`

解析侧已有两个位提取器：
- `csg_new_gen_parser.CSGNewGenParser._extract_bits(data, start_bit, width)`（L2334，**绝对位偏移，LSB 优先**，逐位取）
- `csg_new_gen_cmd_payloads._bits(data, offset, bit_start, bit_width)`（L1009，小端整数字节容器 + 内偏移）

现有组帧侧 `pack_bits(total_bits, fields)` 是「整数字节容器」风格，**无法直接表达跨字节且不按 8 位对齐的字段**（如 FC 字节1-3 的 12bit 源TEI/目的TEI 交错：`源TEI = b1 | (b2&0x0F)<<8`）。硬凑会让代码充满特例，正是出错的来源。

**设计决策：新增 `put_bits_le(buf: bytearray, start_bit: int, width: int, value: int)`**，语义 = `_extract_bits` 的严格逆：

```python
def put_bits_le(buf, start_bit, width, value):
    """把 value 的 width 位写入 buf 的 [start_bit, start_bit+width) 位区间（LSB 优先）。
    与 CSGNewGenParser._extract_bits 严格互逆。"""
```

- 契约：对任意 `start_bit / width / value`，`_extract_bits(bytes(buf), start_bit, width) == value`
- 测试**双向钉住**：`put → extract == value`，并对 FC 全部跨字节字段做断言
- FC/PB/MAC 的所有跨字节字段一律经它写入 → 消除「首字节=高位」这类错位（陷阱 54 的整类风险）
- 保留 `pack_bits` 不动（应用层既有代码与测试依赖它）

**验证方式（可执行）**：`test_csg_link_frame_gen.py` 里对 `_extract_bits` × `put_bits_le` 做交叉断言，
并对 TEI 用文档自带 oracle：`put 目的TEI=0x123 → 字节4=0x23`、`put 源TEI=0x456 @bit12 → 字节5 高半字节=0x6、字节6=0x45`。

---

## 5. FC 组帧的结构（4 个变体）

按「固定部分 + 变体可变区域」两段装配，变体差异**只体现在字节 1-12 低 4 位**：

```python
def build_fc(*, delimiter_type, access_indicator, snid, std_version,
             variant: dict) -> bytes:
    fc = bytearray(13)                      # 字节 0-12，13-15 待填 FCCS
    put_bits_le(fc, 0, 3, delimiter_type)   # 字节0 bit0-2
    put_bits_le(fc, 3, 1, access_indicator) # 字节0 bit3   ← C1 契约，默认 1
    put_bits_le(fc, 4, 4, snid & 0x0F)      # 字节0 bit4-7
    _fill_variant(fc, delimiter_type, std_version, variant)   # 字节 1-12 低4位
    put_bits_le(fc, 100, 4, std_version)    # 字节12 高4位 = 标准版本号
    return bytes(fc) + crc24_le(fc)         # + FCCS（C2）
```

变体装配（第一期 4 个，字段名与 research/01 表号一一对应）：

| 变体 | 关键字段落位（bit 偏移） |
| --- | --- |
| SOF-BPLC（表20） | 源TEI@8(12) / 目的TEI@20(12) / 链路标识符@32(8) / SNID高位@40(1) / 保留@41(15) / 物理块个数@56(4) / 载波映射表索引@60(4) / 帧长@64(12) / 保留@76(9) / TEI过滤@85(1) / 重传@86(1) / 符号数@87(9) / 扩展载波映射表索引@96(4) |
| SOF-ISAC 数据帧（表23） | 源TEI@8(12) / 目的TEI@20(12) / 多站点帧标识@32(1) / 训练帧标识@33(1) / 物理块个数@34(4) / 流数@38(2) / TF符号数@40(3) / PL频段@43(3) / TF扩展频段@46(1) / 保留@47(1) / Bitloading标识@48(1) / TMI或PB大小码@49(5) / 保留@54(2) / 保留@56(8) / 帧长@64(12) / 保留@76(4) / 保留@80(16) / SNID高位@96(1) / 保留@97(3) |
| 信标帧（表18） | 信标时间戳@8(32) / 信标周期计数@40(32) / 源TEI@72(12) / 载波映射表索引@84(4) / 符号数@88(9) / SNID高位@97(1) / 相线@98(2) |
| SACK（表30） | 接收结果@8(4) / 接收状态@12(4) / 目的TEI@16(12) / 接收物理块个数@28(4) / SNID高位@32(1) / SNR类型@33(2) / 保留@35(5) / SNR评估信息@40(30) / 保留@70(2) / 保留@72(24) / 扩展帧类型@96(4) |

> 说明：表中 bit 偏移 = `(字节号−1)*8 + 字节内比特位`，即 byte1 的 bit0 = 整体 bit8。
> **实现时按 research/01 逐字段核对**，并在测试中用「回读解析值 == 输入值」逐字段断言（这是最强的位序验证）。
> SACK 的 30bit SNR 字段**跨字节非对齐**（字节5-7 + 字节8 bit0-5）——必须走 `put_bits_le`，不能当 32bit 整型写。

**PB 大小与 cmt_index 的自洽**：以「PB 总大小」为 UI 主输入，按 `_get_pb_size` 的映射**反查** cmt_index/TMI：
- BPLC：PB=136 → cmt=4（≤0x7 区间任一）；PB=520 → cmt=8
- ISAC：PB=520 → TMI 0-8；264 → 9-15；136 → 16-20；72 → 21-25；16 → 26-27
- Bitloading=1 时改填「物理块大小码」`ISAC_BL_PB_SIZE_MAP`(0:136/1:520/2:72/3:264)，**与 PB 大小联动**

---

## 6. UI 设计：五层折叠

### 6.1 新增可复用组件 `collapsible_section.py`

```python
class CollapsibleSection(QWidget):
    """标题栏（可点击折叠）+ 内容区；状态可持久化、可程序化展开/收起。"""
    def __init__(self, title, parent=None, expanded=True, key=None)
    def content_layout(self) -> QLayout
    def set_expanded(self, expanded: bool)
    def is_expanded(self) -> bool
    def set_title_suffix(self, text)   # 用于显示「N 字节 / HEX 缩略」
    toggled = Signal(bool)
```

- 标题栏用 `QToolButton`（`setCheckable` + 箭头指示），内容区放 `QWidget` + 布局
- 提供 `expand_all()` / `collapse_all()`（巨型表单的操作便利）
- **独立文件**（AGENTS §4.1：新 UI 组件必须拆到独立文件）

### 6.2 页面结构

```
┌ 协议组帧 · 协议9 ──────────────────────────────────────────┐
│ 帧类型: [定界符类型 ▾]  通道: [PLC/HRF ▾]  版本: [BPLC/ISAC ▾] │ ← 顶层选择器，驱动下面所有区
│ 输出层次: [整帧MPDU/ED封装/应用层帧/仅BDU ▾]   [展开全部][收起全部]│
├──────────────────────────────────────────────────────────┤
│ ▼ ① FC 帧控制（16 字节）            [FC HEX 缩略]            │
│     定界符/接入指示/SNID/标准版本号 + 变体字段（按 6.3 联动）  │
│ ▼ ② 物理块 PBH（4×N 字节）+ PBCS     [PBH HEX 缩略]          │
│     物理块个数/序列号/聚合标志/PB总大小/PBCS(自动·只读)       │
│ ▼ ③ MAC 帧头（32 或 12 字节）         [MAC HEX 缩略]          │
│     帧头类型/版本/SNID/发送序号/MSDU长度(自动·只读)/TEI/跳数/  │
│     广播方向/发送类型/发送次数/MSDU序列号/[目的MAC(长头)]      │
│     完整性校验(CRC-32)(自动·只读，显示计算值)                  │
│ ▼ ④ MSDU（头 18/2 字节 + 载荷）       [MSDU HEX 缩略]        │
│     头: VLAN/MSDU类型/[源MAC/目的MAC(长头)]                   │
│     载荷来源: (•)测试模式  ( )手工HEX                         │
│       └ 测试模式时显示：现有 24 模式下拉 + 模式参数表单        │
│       └ 手工HEX时显示：多行输入框                             │
│ ▼ ⑤ ED..EE 封装（可选）              [ED HEX 缩略]           │
│     启用/包装格式(plc2,gx)/CS/物理信道/时间戳/物理块个数·长度   │
└──────────────────────────────────────────────────────────┘
预览区： 【分层概览】+【整帧逐字段回读】
```

### 6.3 联动规则（决定字段可见性，测试要逐条覆盖）

| 触发 | 效果 |
| --- | --- |
| 定界符类型 = SOF | ① 变体 = SOF-BPLC 或 SOF-ISAC 数据帧（按标准版本号）；②③④ 全部启用 |
| 定界符类型 = 信标 | **②③ 隐藏**（信标无 PBH/MAC）；④ 变为「信标载荷（手工 HEX）」 |
| 定界符类型 = SACK | **②③④ 隐藏**；① 变体 = SACK（SNR类型联动 SNR评估信息是否可编辑） |
| 标准版本号 = BPLC | ① 变体 = SOF-BPLC；② PB 候选 {136, 520} |
| 标准版本号 = ISAC-PLC | ① 变体 = SOF-ISAC 数据帧；② 候选 {520,264,136,72,16} + Bitloading 开关 |
| 通道 = HRF | 本期提示「HRF 变体二期支持」，并退回 PLC 变体（不静默给错布局） |
| MAC 帧头类型 = 0 (32B) | ③ 出现目的MAC/保留；④ MSDU 头变 18B（出现源/目的MAC） |
| MAC 帧头类型 = 1 (12B) | ③ 隐藏目的MAC；④ MSDU 头变 2B |
| MAC 版本 = 2 | 提示「单跳头二期支持」，并退回版本 1 |
| 输出层次 = 仅BDU/应用层帧 | ①②③（及对应自动计算）不参与，④ 之前的部分按原逻辑 |
| ④ 载荷来源 = 手工HEX | 隐藏模式下拉与参数表单（手工优先） |

### 6.4 预览（改造 `parse_rows`）

```
【分层概览】
  ① FC 帧控制        16 字节   <hex>
  ② 物理块 PBH       N 字节    <hex>
  ③ MAC 帧头         32/12 字节 <hex>
  ④ MSDU             N 字节    <hex>
  ⑤ ED..EE 封装      M 字节    <hex>
【ED 封装头字段】       （启用 ED 时，沿用现有 build_ed_header_rows）
【整帧逐字段回读】       CSGNewGenParser().parse_to_table(整帧, parse_level="auto")
```

- `output_layer()` 新增 `"mpdu"`；`output_bytes()` 分支扩展
- **`parse_rows` 的回读对象从「应用层帧」改为「按输出层次选定的字节」**，这样 FC/PB/MAC 的字段才会出现在预览里（否则用户看不到自己填的 FC）
- `extension`/`reserved` 等既有渲染保持不动，旧 144+117 项测试以此为准

---

## 7. 兼容性

| 项 | 处理 |
| --- | --- |
| `layer_combo` 旧三档 `ed/app/bdu` | **原样保留**（默认 `ed`），仅在其后追加 `mpdu`；旧测试按 data 值断言仍通过 |
| `CsgTestFrameGenWidget` 对外接口 | `build()` / `output_bytes()` / `parse_rows()` / `output_layer()` / `changed` 信号**签名不变**；`FrameBuildResult` 由新模块的 `LinkFrameBuildResult` 承载新层（或在 `FrameBuildResult` 上加可选字段，二选一在实现时定，倾向**新增 dataclass 不侵入既有**） |
| `frame_gen_widget.py` 接线 | `_do_realtime_update_csg` / `_generate_csg_frame` / `_csg_parse_to_table` 三处；后者的 `parse_to_table(payload)` 需按输出层次传参（整帧时 `auto`；仅 ED 时先剥 ED） |
| 配置持久化 | 折叠状态存 `config.json`；**测试必须沙箱 `main_gui.data_path` 与 `app_paths.data_path`**（AGENTS 陷阱 42） |
| 既有回归 | `test_csg_new_gen_frame_gen.py`(144) / `test_csg_frame_gen_gui.py`(117) / `test_protocol_registry.py` 必须全绿 |

---

## 8. 权衡记录

| 决策 | 备选 | 理由 |
| --- | --- | --- |
| 新增组帧模块 + 回读对拍（B 方案） | 把 11 个 `_parse_mpdu_*` 改成声明式表驱动，两侧共用（A 方案） | A 会改变已由 60 帧真实夹具锚定的解析行为、评审面巨大；B 纯新增、回归面为零，且 1.23.64 已确立「组帧与解析同源对拍」的路子。A 作为独立任务留待后续 |
| 新增 `put_bits_le` 而非复用 `pack_bits` | 扩展 `pack_bits` 支持任意 bit 偏移 | `pack_bits` 是「整数容器」语义，被应用层 24 模式与 144 项测试依赖；改语义有回归风险。新增互逆函数更小更清晰 |
| MSDU 头长度**不给用户单独设** | 让用户自选 18B/2B | 两者必须与 MAC 帧头类型一致（C5），给用户设等于允许造出解析器认不出的帧 |
| 以「PB 总大小」为主动输入，反推 cmt_index | 让用户直接填 cmt_index | 用户关心的是块大小；且解析器会按帧长校验 PB 大小，反推能保证自洽 |
| 整帧回读用 `parse_level="auto"` | 逐层分别回读 | auto 最接近用户实际粘贴解析的场景，能一次暴露层间错位 |

---

## 9. Rollout / Rollback

- **Rollout**：纯新增 + 一个页面的结构性改造；无数据格式变更、无迁移。改动集中在 2 个新文件 + 2 个既有文件。
- **Rollback**：`git revert` 单个提交即可（新增文件删除 + 既有文件回退），不影响数据文件与配置。
- **风险最小化顺序**：先加纯逻辑模块与测试（可独立验证，不碰 UI）→ 再加折叠组件 → 最后改造页面。每一步都可单独提交/回退。
