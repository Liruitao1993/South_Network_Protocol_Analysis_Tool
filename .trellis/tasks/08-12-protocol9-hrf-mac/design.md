# 设计：协议9 无线单跳MAC帧解析

## 现状（已审核）

- `parse_to_table(..., channel)` 已支持 plc/hrf（`self._channel`），HRF FC 可变区域（`_parse_mpdu_sof_hrf`/`_parse_mpdu_beacon_hrf`/`_parse_mpdu_sack_hrf`）与文档表42/45/46 逐字段一致，HRF 单 PB（`_pb_count=1`）。
- **缺口**：MAC 帧层所有路径按 header_type 定长度（`_parse_mac_frame` L2208 `header_size = 12 if header_type == 1 else 32`；`parse_to_table` L440；`_parse_pb_block` L872-884）。版本2（单跳帧协议，表5/表6 仅无线支持）帧被错位解析。
- `_parse_msdu_payload` 假设 MSDU 载荷自带 VLAN+类型前缀（PLC 布局），无线单跳帧 MSDU 类型在 MAC 头内、载荷为裸业务数据。

## 改动点（全部在 `csg_new_gen_parser.py`）

### 1. `_parse_mac_frame`：version==2 → 单跳MAC头（表12，4B）

```python
version = (first_byte >> 1) & 0x03
if version == 2:
    header_size = 4
else:
    header_size = 12 if header_type == 1 else 32
if frame_len < header_size + 4:  # 单跳最小 8B
    ...
```

version==2 分支（在 `header_type == 0` 长头分支之后并列）：
- 字节0：帧头类型(1b)/版本(2b)/保留(5b) 三行
- 字节1：MSDU类型 → `MSDU_TYPE_MAP`（表13 已有 0x01/0x02/0x80）
- 字节2-3：MSDU长度（小端）
- 载荷 `frame_bytes[4:4+msdu_len]` **内联分派**（不等主流程兜底）：
  - 1 → `_parse_application_message(payload, base_offset+4)`
  - 2 → `_parse_rf_discover_node_list`（新增，见 §4）
  - 128 → IPV4 行（复用现有 0x80 分支样式）
  - 其他 → 原始 hex 行
- 尾部 CRC-32 校验收尾（复用现有逻辑，`msdu_end = 4 + msdu_len`）

### 2. `parse_to_table` 步骤3（L434-448）

```python
is_mac_frame = (header_type in (0, 1) and version in (1, 2)
                and frame_len >= (4 if version == 2 else 12))
if is_mac_frame:
    mac_header_size = 4 if version == 2 else (12 if header_type == 1 else 32)
    offset, mac_table = self._parse_mac_frame(frame_bytes, offset)
    table_data.extend(mac_table)
    if version == 2:
        msdu_payload = b""   # 单跳帧载荷已在 _parse_mac_frame 内联解析
    else:
        msdu_len = ...; msdu_payload = frame_bytes[mac_header_size:...]
```
`_parse_msdu_payload(b"")` 走 `elif len(msdu_payload) > 0` False → 不变返回，无重复行。

### 3. `_parse_pb_block` 尾段（L872-888）

```python
if mac_data and ((mac_data[0] >> 1) & 0x03) == 2:
    mac_hdr_len = 4
    msdu_payload = b""      # 单跳帧载荷已由 _parse_mac_frame（L855 单MAC分支）内联解析
elif mac_data and (mac_data[0] & 0x01) == 0:
    mac_hdr_len = 32
else:
    mac_hdr_len = 12
```
（仅改长度取值与 v2 的 msdu_payload；`offset += pb_hdr_len + mac_hdr_len` 自然适配。）

### 4. 新增 `_parse_rf_discover_node_list`（表139/140/142/143）

```
站点MAC地址(6B 冒号分隔) + 统计序号(1B) + 信息单元 TLV 链:
  头1B: 类型(bit0-6) | 长度类型(bit7: 0=1B长度 1=2B长度)
  长度: 1或2B（小端）; 内容: L 字节
  类型0 站点属性: 按表142 展开 14B（CCO MAC 6B / 代理TEI 12b+角色 4b / 层级4b+RF跳数4b / 代理上行/下行接收率 / 链路最小接收率 / 无线发现列表周期 / 无线接收率老化周期个数）
  类型1/2/3: 原始 hex 行
```
返回 `list`，键名遵循 §4.2。越界容错：TLV 链读取不超过 payload 长度，异常时跳出并显示剩余原始。

### 5. 测试（`test_csg_new_gen.py` 追加或新文件 `test_csg_hrf_mac.py`）

- T1 单跳MAC帧直入（version==2）：构造 `06 01 00 05 | 应用层(0x11 01 01 ...) | CRC32`，断言 帧头类型/版本(单跳帧协议)/MSDU类型(应用层报文)/MSDU长度/应用层字段。
- T2 完整无线 MPDU（`channel='hrf'` + `parse_level='fc_pb'`）：HRF SOF FC(16B) + PB头 + 单跳MAC帧，断言链路贯通无"解析失败"。
- T3 无线发现列表（MSDU类型2）：构造 MAC+Seq+TLV(类型0 站点属性14B)，断言字段展开。
- T4 回归：现有 `python test_csg_new_gen.py` 全绿（PLC 路径不受影响）。

## 兼容性 / 风险

- version==2 判定只依赖字节0 bit1-2，与 header_type 无关（表5 帧头类型无意义）。
- 主流程 v2 载荷内联解析 + `msdu_payload=b""` 防重复；`_parse_pb_block` 单MAC分支（L855）已调用 `_parse_mac_frame`，天然覆盖。
- 级联路径（`parse_msdu_app=True`）v2 帧同样内联，无额外改动。
- 不触碰 HRF FC 可变区域、GUI、配置、监控器。

## 回滚

单文件改动；`git checkout -- csg_new_gen_parser.py` 即回退到改动前（HRF FC 可变区域为未提交工作区内容，回滚会一并丢弃——如需保留先行 `git stash`）。