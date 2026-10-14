# 解析器交叉核对与组帧契约（oracle 的唯一来源）

**核对对象**：`csg_new_gen_parser.py`（6884 行，已随 1.23.64 上线并通过 60 帧真实夹具回归）。
**原则**：`csg_new_gen_parser` 的位运算已由真实帧验证，**组帧必须与它逐位对称**。字段表有疑问时以本节为准。

> 行号为 2026-09-30 实测值，AGENTS 陷阱 45 警告行号会漂移 → 实现时按**符号名/代码文本**检索。

---

## 1. 关键契约：FC 必须置「接入指示=1」，否则 auto 完全不走 MPDU 路径

`parse_to_table` 的 MPDU 检测（L811-813）：

```python
delimiter_type = first_byte & 0x07        # bits 0-2
access_indicator = (first_byte >> 3) & 1  # bit 3
is_mpdu = (access_indicator == 1 and delimiter_type <= 3 and frame_len >= 16)
```

→ **组帧 FC 字节0 必须含 bit3=1**（表16：1=MPDU 在宽带载波通信接入网络中传输）。
→ 否则解析器会把整帧当 MAC/MSDU/APP 猜，e2e 测试必挂。**这是最容易漏的一条**。

## 2. 关键契约：MSDU 头长度由 MAC 帧头类型决定（文档表1/表2 的实际落地）

`_parse_msdu_payload`（L1081-1083）：

```python
msdu_hdr_len = 2                      # 默认短头
if mac_data and (mac_data[0] & 0x01) == 0:
    msdu_hdr_len = 18                 # 长头
```

`mac_data[0] & 0x01` = **帧头类型**（表4：0=32B长帧头 / 1=12B短帧头）

| 帧头类型 | MAC 头长 | MSDU 头长 | MSDU 头内容（表1/表2） |
| --- | --- | --- | --- |
| 0 | 32B | **18B** | 原始目的MAC(6) + 原始源MAC(6) + VLAN(4,LE) + MSDU类型(2,LE) |
| 1 | 12B | **2B** | VLAN(1) + MSDU类型(1) |

→ 组帧第 ④ 层必须**同时产出对应长度的 MSDU 头**，不能只有业务数据。

## 3. 关键契约：MSDU 头取值必须落在解析器的合法集合内

长 MSDU 头（L1097-1100）：
```python
is_msdu = (0 <= vlan_tag <= 3 and msdu_type in (0x01, 0x02, 0x80)) \
          or (vlan_tag == 0x8100 and msdu_type == 0x88E1)
```
短 MSDU 头（L1127-1130）：
```python
is_msdu = (0 <= vlan_tag <= 3 and msdu_type in (0x01, 0x02, 0x80)) \
          or (vlan_tag == 0x81 and msdu_type == 0x00)
```

→ 默认组帧取 **VLAN=0 / MSDU类型=0x01（应用层报文）** → 命中第一分支 → 分派 `_parse_application_message`。
→ 组帧 UI 的 VLAN 与 MSDU类型 下拉**取值必须限定**在上表集合内（或给出「非标准值将不被识别」的告警）。

## 4. 关键契约：应用层帧格式 = 端口号(1B) + 报文标识符(2B,LE) + 保留(1B) + 业务报文

`_parse_application_message`（L5474-5523）读 `app_data[0]`=端口号、`[1:3]`=报文标识符（**小端**）、`[3]`=保留。
现有组帧器 `build_app_frame`（`csg_new_gen_frame_gen.py` L487-501）产出**完全相同**的布局 ✅
→ **第 ④ 层的「应用层帧」直接复用 `build_app_frame`，不要再写一份。**

另注：`_parse_msdu_payload` 有直通启发式（L1071-1074）`port ∈ (0x11,0x13) and id==0x0101 → is_direct_app`，
即「无 MSDU 头」也能解析。**但组帧应带上 MSDU 头**（更贴合协议，且能验证 MSDU 头路径）。

## 5. MAC 帧的三处自证（组帧必须自动算准）

| 项 | 解析器出处 | 覆盖范围 | 字节序 |
| --- | --- | --- | --- |
| FCCS | L1992 `_crc24(frame_bytes[base:base+13])` | FC 字节 0-12 | 小端 3B（L1989） |
| PBCS | L1581 `_crc24(frame_bytes[pb_off:pbcs_off+1])` | PBH + 块体 + 保留(1B) | 小端 3B（L1578） |
| MAC 完整性校验 | L3438 `_crc32_ieee(frame_bytes[new_offset:msdu_end])` | **MSDU 载荷**（不含 MAC 头） | 小端 4B（L3435） |

解析器对 PBCS=0 有专门宽容（L1587「置零/采集接口未提供，非校验失败」）→ 组帧**照实算**，不要置零。

## 6. 物理块（PB）尺寸映射 —— 组帧的 cmt_index/TMI 必须与 PB 大小自洽

`_get_pb_body_size(pb_total) = pb_total - 8`（L1323）
`_get_pb_size(tmi, version)`（L1308-1318）：
- `version == 2`（ISAC-PLC）→ `ISAC_PB_MAP`（L1272-1278）：TMI 0-8→520；9-15→264；16-20→136；21-25→72；26-27→16
- 否则（BPLC）→ TMI ≤0x7 或 ==0xE → **136**；TMI ∈ {8,9,A,B,C,F} → **520**

解析器容错：`_infer_pb_size`（L1325）按 `PB起始偏移 + pb_count×PB大小 == 帧长` 唯一解覆盖映射值，覆盖时多打一行「PB大小推断」。
→ **组帧设计：以「PB 总大小」为主输入，自动反推 cmt_index**；若用户手动改 cmt_index 与所选大小冲突，给出告警（可组，但解析会多一行推断提示）。
→ `ISAC_BL_PB_SIZE_MAP`（L1280-1281）仅 Bitloading 分支使用：0:136 1:520 2:72 3:264。

## 7. 各定界符类型在 auto 下的路径（决定「帧尾放什么」）

| 定界符 | auto 路径 | 组帧帧尾 |
| --- | --- | --- |
| 0 信标帧 | FC → `_parse_mpdu_beacon` → 信标载荷（**无 PBH**，L935 注释） | FC(16) + 信标载荷 |
| 1 SOF帧 | FC →（可选 eFC）→ `_parse_pb_block` → MAC → MSDU | FC(16) [+eFC] + ΣPB |
| 2 SACK | FC 后无 PB/MSDU（L832-837 明示「无物理块，不适合 PB-only」） | FC(16) 单独 |
| 3 网间协调 | 同 SACK（第一期不做） | — |

→ 第一期 SOF/SACK/信标三种帧尾形态各不相同，**UI 的层可见性要随之联动**（SACK 隐藏 PB/MAC/MSDU 折叠区）。

## 8. auto 路径下 `_pb_count` 来自 FC，不要被 pb_only/mac_only 的硬编码误导

- `pb_only` / `mac_only` 强制 `_pb_count = 1`、`_cmt_index = 4`、`_std_version = 1`（L820-822、L844-846）
- **e2e 测试一律用 `parse_level="auto"`**（完整 MPDU），或分别用 `fc_only` / `pb_only` / `mac_only` 做**分层验证**（这正好是可以逐层断言组帧输出的手段）。

## 9. e2e oracle 设计（可执行断言）

`CSGNewGenParser.parse_to_table(frame_bytes, parse_level=..., channel=..., pb_frame_type=...)` 返回解析行列表，
每行形如 `(字段名, 原始值, 解析值, 说明, byte_start, byte_end)`。
→ **组帧 → 回读 → 断言「字段名 → 解析值」** 即强 oracle。

建议的三级 oracle：
1. **逐层**：`fc_only` 断言 FC 字段；`pb_only` 断言 PBH/PBCS；`mac_only` 断言 MAC 头 + MSDU 头。
2. **整帧**：`auto` 断言「定界符类型 / 源TEI / 目的TEI / 物理块个数 / MSDU长度 / 完整性校验(CRC-32) 校验通过」。
3. **字段等值**：对 FC 的全部字段值与表单输入逐一比对（`解析值` 列 == 输入值），这是最能抓位序错误的断言。

**TEI 位序的文档自带 oracle**（research/02 §2）：目的TEI=0x123、源TEI=0x456 → 第4/5/6 字节 = `23 61 45`。
这组数应直接进测试作为位序断言。

## 10. 复用清单（禁止重写）

| 功能 | 复用对象 |
| --- | --- |
| 应用层帧（端口/报文标识/保留/业务报文头） | `csg_new_gen_frame_gen.build_app_frame` / `build_business_message` |
| ED..EE 封装 | `csg_new_gen_frame_gen.build_ed_frame` |
| CRC-24 / CRC-32 | `csg_new_gen_parser.CSGNewGenParser._crc24` / `_crc32_ieee`（**静态/实例方法**，组帧侧需确认可调用形式，必要时提取为模块函数并两侧共用） |
| 位打包 | `csg_new_gen_frame_gen.pack_bits`（已与解析侧 `_bits` 对称，注释已声明） |
| 十六进制文本解析 | `csg_new_gen_frame_gen.hex_to_bytes` |
| 参数越界错误 | `csg_new_gen_frame_gen.FrameBuildError` / `_clip_count` |
| 解析器常量表 | `DELIMITER_TYPE_MAP`(L1265) / `MPDU_VERSION_MAP`(L216) / `MAC_HEADER_TYPE_MAP`(L202) / `MAC_VERSION_MAP`(L208) / `MSDU_TYPE_MAP`(L193) / `SEND_TYPE_MAP`(L219) / `BROADCAST_DIR_MAP`(L228) / `BEACON_PHASE_MAP`(L2476) / `SACK_SNR_TYPE_MAP`(L2842) / `ISAC_PB_MAP`(L1272) / `ISAC_BL_PB_SIZE_MAP`(L1281) |

> ⚠ **不要新建第二份常量清单**：下拉项应从上述解析器常量派生（协议9 的既有纪律：同一知识只有一个来源）。
> 组帧侧可新增的是「哪些字段可编辑、默认值、UI 分组」这类**表单元数据**，不是协议取值表。

## 11. 待实现时确认的 3 个开放点

1. `_crc24` / `_crc32_ieee` 当前是 `CSGNewGenParser` 的方法（`_crc32_ieee` 标注为 `@staticmethod`，L725；`_crc24` 为静态方法 L730）→ 组帧可直接 `CSGNewGenParser._crc24(...)`；若要彻底解耦，可提取到模块级并让两侧共用（新增导出，不改解析行为）。
2. 信标载荷（第 ④ 层在信标帧下的形态）：表51/表73 两个布局（精简/标准），第一期**只做「手工 HEX 填载荷」**，表结构组帧留二期。
3. MSDU 长头的「原始目的MAC/原始源MAC」默认值：建议默认 `FF:FF:FF:FF:FF:FF`（广播，L205 文档明示）+ 可编辑。
