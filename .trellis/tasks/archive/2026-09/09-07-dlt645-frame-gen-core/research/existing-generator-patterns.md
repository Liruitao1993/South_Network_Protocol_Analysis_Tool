# Research: 现有三套 generator/schema 模式对齐

- **Query**: 三套 generator + schema 的类名、`generate_frame` 签名、schema dict 字段约定、字段类型集合、CS/校验位置；总结 dlt645 版最小公共契约
- **Scope**: internal
- **Date**: 2026-09-07
- **来源**: `send_frame_lib.py`(547) + `frame_generator_schema.py`；`gdw_send_frame_lib.py`(376) + `gdw_frame_generator_schema.py`；`dl_t698_45_frame_gen.py`(286) + `dl_t698_45_frame_schema.py`(257)

---

## 1. 三套对照总表

| 维度 | 南网（推荐范本） | 国网 | 698.45 |
|---|---|---|---|
| generator 文件 | `send_frame_lib.py` | `gdw_send_frame_lib.py` | `dl_t698_45_frame_gen.py` |
| 类名 | `ProtocolFrameGenerator`(`:6`) | `GDWFrameGenerator`(`:16`) | `DLT69845FrameGenerator`(`:9`) |
| schema 文件 | `frame_generator_schema.py` | `gdw_frame_generator_schema.py` | `dl_t698_45_frame_schema.py` |
| schema 顶层变量 | `DI_FIELD_SCHEMA` | `GDW_AFNFN_SCHEMA` | `DLT69845_FIELD_SCHEMA`(`:49`) |
| schema 键 | `Tuple[int,int,int,int]`（DI 四元组 di3,di2,di1,di0） | `Tuple[int,int]`（afn,fn） | `Tuple[str,str]`（apdu_type,sub_type） |
| 打包引擎 | **通用** `generate_data`(`:285`) 五遍 + `_pack_field`(`:431`) | **通用** `_pack_fields`(`:201`)+`_pack_field`(`:236`) | **硬编码** if name==... (`:154+`) |
| 底层封帧 | `protocol_tool.Frame/ControlField`(`:3,19`) | 自建 body + CS | `_assemble_frame`(`:20`) crcmod x-25 |
| 校验和位置 | `Frame.frame_pack()` 内部 | generator 内 `sum(body)&0xFF` | HCS/FCS（crc16 x-25, `struct.pack('<H')`） |

---

## 2. `generate_frame` 签名（三套）

### 南网 `ProtocolFrameGenerator.generate_frame`（`send_frame_lib.py:390-412`）
```python
def generate_frame(self, di_key: Tuple[int,int,int,int], field_values: Dict[str,Any],
                   src_addr: bytes = b'\x00'*6, dst_addr: bytes = b'\x00'*6,
                   dir_flag: int = 0, prm: int = 1, add_flag: int = 0) -> bytes:
    data = self.generate_data(di_key, field_values)   # 五遍打包
    di3, di2, di1, di0 = di_key
    return self._build_frame(di3, di2, di1, di0, src_addr=..., dst_addr=...,
                             data=data, dir_flag=..., prm=..., add_flag=...)
```
- `_build_frame`(`:19-28`)：用 `ControlField(dir,prm,add,ver,reserved)` + `Frame(...)`，`frame.frame_pack()` 内部算 CS。
- 另有硬编码快捷方法 `create_afnXX_diXX`（`:30+`）+ `afn_handlers` 字典（`:8-17`），但通用路径是 `generate_frame`。

### 国网 `GDWFrameGenerator.generate_frame`（`gdw_send_frame_lib.py:22-29`）
```python
def generate_frame(self, afn: int, fn: int, field_values: Dict[str,Any],
                   info_config: Dict[str,Any],
                   src_addr: str = "000000000000", dst_addr: str = "000000000000",
                   relay_addrs: List[str] = None) -> bytes:
```
- `info_config`：信息域 R 各位（路由标识/通信模块标识/中继级别/报文序列号…）字典（`:36-47` 文档）。
- 地址是 **12 位十进制字符串**，`_bcd_encode(addr_str,length)`(`:152`) 转 BCD 并**逆序**（`:177` result[::-1]）。
- 福建增补帧特判（`:63` afn ∈ {0x50..0x56}）。

### 698.45 `DLT69845FrameGenerator.generate_frame`（`dl_t698_45_frame_gen.py:125-130`）
```python
def generate_frame(self, apdu_type: str, sub_type: str, field_values: Dict[str,Any],
                   sa: bytes = None, ca: int = 0,
                   dir_bit=0, prm_bit=1, seg_bit=0, sc_bit=0, func_code=3) -> bytes:
```
- `build_control`(`:104-122`)：位域组装（dir<<7 | prm<<6 | seg<<5 | sc<<3 | func_code）。
- **⚠️ 反面教材**：`generate_frame` 内 `for name,val in field_values.items(): if name=="PIID"... elif name=="OI"...`（`:154+`）**硬编码字段名**，非通用打包。dlt645 不应学此模式。

---

## 3. schema dict 字段约定（实际用到的键）

### 顶层值结构（三套一致）
```python
命令键: {
    "name":  str,          # 命令中文名（下拉展示）
    "direction": "down"/"up"/"both",   # 南网/国网有；698.45 无（用 doc 描述）
    "doc":   str(HTML),    # 帮助文本（<b>/<table> 富文本）
    "fields": [ field, ... ]
}
```
- 南网样例 `frame_generator_schema.py:23-25`：`{"name":'查询未完成任务数', "direction":"down", "doc":'<b>DI编码</b>：E8 00 02 03...'}`。
- 698.45 样例 `dl_t698_45_frame_schema.py:51-63`：`{"name":..., "doc":..., "fields":[...]}`。
- 国网 `get_supported_afn_fn`(`gdw_send_frame_lib.py:331`) 只返回 direction ∈ {down, both}。

### field dict 键全集（实测）
| 键 | 用途 | 出现处 |
|---|---|---|
| `name` | 字段名（field_values 的键） | 全部 |
| `type` | 字段类型（见第 4 节） | 全部 |
| `length` | 字节长度（bytes/bcd/ascii 填充/截断） | `_pack_field:456,467,476` |
| `default` | 默认值 | `generate_data:311` |
| `desc` | 字段说明（UI 提示） | 698.45 schema |
| `endian` | `"little"`/`"big"`（uint16/32） | `_pack_field:442,447`；698 schema `:62` |
| `reverse` | bool，bytes 打包前逆序 | `_pack_field:454` |
| `required` | bool，缺值抛错 | `generate_data:313` |
| `optional` | bool，值为 None 时跳过 | `generate_data:384` |
| `enum_map` | 枚举值→文本映射（UI 下拉） | schema |
| `sub_fields` | 位域子字段列表（合并为父值） | `generate_data:318,332-366` |
| ↳ `bit_offset`/`bit_width` | 子字段位偏移/宽度 | `generate_data:343-346` |
| ↳ `condition` | 条件打包 `{field,value,eval}` | `_check_condition:416` |
| `item_fields` | list 类型的行内字段定义 | `_pack_field:485` |
| `count_field` | 引用另一字段名，回填 list 长度 | `generate_data:326-329` |
| `count_type` | list 自带数量前缀类型 uint8/uint16 | `_pack_field:489-494` |
| `length_field` | 引用另一字段名，回填本字段字节长度 | `generate_data:371-377` |
| `length_offset` | length_field 附加偏移 | `generate_data:376` |

---

## 4. 支持的字段类型集合（`_pack_field`）

南网 `_pack_field`(`:431-509`) 与国网 `_pack_field`(`:236-300`) **类型集完全一致**：
```
uint8, enum      → struct.pack("B", int(v))
uint16           → struct.pack("<H"/">H")  按 endian
uint32           → struct.pack("<I"/">I")  按 endian
bytes            → fromhex + (reverse) + length 填充/截断
ascii            → encode + length ljust
bcd              → fromhex(视为已编码hex) + length 填充/截断
list             → count_type 前缀 + 遍历 item_fields 递归 _pack_field
其他             → raise ValueError(f"不支持的字段类型: {ftype}")
```
698.45 schema 另用 `piid`/`oi` 类型（`dl_t698_45_frame_schema.py:60`），但由硬编码分支处理，非通用引擎。

### ⚠️ 关键缺口：三套的 `bcd` 类型都不是「十进制数值 → BCD 数字编码」
- `send_frame_lib.py:471-482` / `gdw_send_frame_lib.py:271-282`：`bcd` 类型把 value 当 **hex 字符串** `bytes.fromhex()`，只做长度填充，**不做十进制→BCD 转换、不处理小数点、不逆序**。
- 唯一真正的 BCD 编码是 `gdw_send_frame_lib.py:152 _bcd_encode`，但**仅用于地址域**（十进制串→BCD→逆序），不接受小数点。

**dlt645 组帧影响**：DL/T645 数据域大量是 `XXXXXX.XX` 带小数点的 BCD 计量值，且**低字节在前**（见 protocol-rules.md §7、parser-codec-encode-gaps.md E1）。三套现有 `bcd` 类型**无法直接复用**，dlt645 版**必须新写一个「数值/十进制串 → BCD 字节（含小数点定位 + 逆序）」的字段类型**（如新增 `type:"bcd645"` 或在 generator 内特化）。这是 dlt645 与三套范本的**最大差异点**。

---

## 5. dlt645 版应对齐的最小公共契约（结论）

**范本选择**：仿 **南网/国网的通用 schema 驱动引擎**（`generate_data` 多遍 + `_pack_field` 分派），**不要**学 698.45 的硬编码 if-name 分支。

**建议契约**：
1. 类名：`DLT645FrameGenerator`（新文件 `dlt645_send_frame_lib.py`）。
2. schema：`DLT645_FIELD_SCHEMA: Dict[命令键, Dict]`，命令键建议用**功能码 int**（如 `0x11`）或 `(func, sub)` 元组；值含 `name`/`direction`/`doc`/`fields`。
3. 签名对齐南网：
   ```python
   def generate_frame(self, func_code:int, field_values:Dict[str,Any],
                      addr:bytes/str, dir_flag=0, err_flag=0, more_frame=0) -> bytes
   ```
   内部控制码 = `(dir<<7)|(err<<6)|(more<<5)|(func&0x1F)`（见 protocol-rules.md §3）。
4. 字段类型：复用 uint8/uint16/uint32/enum/bytes/ascii/list + **新增 645 专用 BCD 类型**（带 data_type 小数点 + 低字节在前）。
5. 封帧：generator 内部完成 地址逆序 + DI 逆序 + 数据域 +0x33 + CS(`sum&0xFF`) + 68/68/16 包裹（参照 `test_dlt645_lme.py:31-43` `build_frame` 权威口径）。
6. 命令下拉数据源：功能码名复用 `dlt645_data_codec.FUNC_NAMES`；DI 选择复用 `dlt645_di_lookup.get_dlt645_di_lookup()`（见 di-schema-source.md）。

---

## Caveats

- 南网封帧依赖 `protocol_tool.Frame/ControlField`（`:3`），其 CS/字段布局是南网 1376.1 专用，**dlt645 不能直接复用 `_build_frame`**，须自写 645 封帧（12 字节固定开销 + 加扰 + CS）。
- 国网 `_bcd_encode`(`:152`) 可作 645 地址域编码参考，但 645 地址是 hex 语义（含 0xAA/0x99 通配），非纯十进制，需调整。
- schema 命令键的粒度（按功能码 vs 按 DI）需用户决定：读/写数据 11H/14H 的数据域随 DI 的 data_type 变化，纯功能码 schema 不足以描述写入值格式，可能需要「功能码 schema + DI data_type 驱动动态字段」的混合方案。
