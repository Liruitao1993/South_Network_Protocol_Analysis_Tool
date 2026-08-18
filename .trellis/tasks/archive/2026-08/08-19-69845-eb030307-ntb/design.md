# Design: 协议8 EB030307 过零NTB值上行数据解析

## 1. ACTION-Response NormalList 数据个数兼容

现状 `_parse_action_response` choice=0x02：
```python
for _ in range(count):
    item = {"OMD": self._parse_omd_raw(data, offset)}
    offset += 4
    if offset < len(data):
        dar_val = data[offset]; offset += 1
        item["结果"] = self._enrich_dar(...)
    if offset < len(data):
        resp, consumed = self.axdr.decode(data, offset)  # ← 01 被当 array tag
        ...
```

文档示例（EB030110 读取，无数据）`87 02 00 01 EB 03 01 10 00 09 03 01 00 05 00 00`：
- `00`=DAR, `09 03 01 00 05`=octet-string(3B), `00 00`=时间标签

用户帧（EB030307 有数据）：`00 01 09 81 81 26...`
- `00`=DAR, `01`=**数据个数=1**, `09 81 81 26...`=octet-string(129B)

**结构判定**：DAR 后字节含义需兼容两种：
- 文档示例：`00`(DAR) 后直接 A-XDR（`09`=octet-string tag）
- 用户帧：`00`(DAR) 后 `01`(数据个数) 再 A-XDR

**判定方法**：DAR 后读 1 字节 b：
- b == 0x00 或 b >= 0x80（A-XDR 长格式/超长）→ 视为无数据个数，直接按 A-XDR 解（文档示例路径）
- b 为合法 A-XDR 类型 tag（01/02/03/05/06/09/0A/0C/0F/12/1C 等）→ 可能是数据个数也可能是 array tag
  - **用 A-XDR tag 集合判定**：若 b ∈ 常见 A-XDR 类型 tag → 直接按数据解（文档路径）
  - 否则视为数据个数 N，解 N 个 A-XDR 项

更稳妥：**双路径尝试**：
1. 先按「数据个数 N + N×A-XDR」解（N 需 1~64 且后续能解出 N 项）
2. 失败则回退「直接 A-XDR 解 1 项」

实现：
```python
def _parse_axdr_items_or_single(self, data, offset):
    """兼容：数据个数前缀 或 直接单个 A-XDR"""
    try:
        n = data[offset]
        if 1 <= n <= 64 and offset + 1 < len(data):
            o = offset + 1
            items = []
            for _ in range(n):
                d, c = self.axdr.decode(data, o)
                items.append(d); o += c
            if o <= len(data):
                return items, o
    except Exception:
        pass
    d, c = self.axdr.decode(data, offset)
    return [d], offset + c
```

注意：文档示例 `09`（octet-string tag）若被当 N=9 会解 9 项失败 → 回退单 A-XDR ✓
用户帧 `01` 当 N=1 → 解 1 项 octet-string ✓

## 2. EB030307 字段 schema（gdw_eb_di_fields.py）

```python
"EB030307": {
    "名称": "通信模块最近1个整分整秒过零时刻NTB值",
    "fields": [
        {"name": "数据开始时间", "type": "bcd_time", "length": 6},
        {"name": "边沿类型", "type": "enum",
         "enum_map": {0: "保留", 1: "下降沿", 2: "上升沿"}},
        {"name": "数据周期_分钟", "type": "uint8"},
        {"name": "数据点数M", "type": "uint8"},
        {"name": "NTB值数组", "type": "list",
         "item_fields": [
             {"name": "相线1 NTB值", "type": "uint32"},
             {"name": "相线2 NTB值", "type": "uint32"},
             {"name": "相线3 NTB值", "type": "uint32"},
         ]},
    ],
},
```

bcd_time 当前显示 `26 08 14 14 42 00` 拼接，改进为 `2026-08-14 14:42:00` 可读格式。

## 3. 表格展示

现有 `_add_eb_business_fields` 已支持 list 递归展开（类型+长度）：
```
数据点数M | 10 | 类型=uint8, 长度=1字节
NTB值数组 | [10项] | 类型=list, 长度=120字节
  相线1 NTB值 | 1803910282 | 类型=uint32, 长度=4字节
  相线2 NTB值 | 0 | 类型=uint32, 长度=4字节
  ...
```
无需改表格逻辑（uint32 大端已由 1.14.2 修正）。

## 4. 兼容性

- 文档示例（无数据个数）走单 A-XDR 回退路径 ✓
- 现有 SET/ACTION Request List 不受影响
- `_decode_eb_data_content` 无 schema 分支不受影响（EB030307 现在有 schema 了）

## 5. 风险

- `_parse_axdr_items_or_single` 对 N 的判定可能误判：A-XDR tag 0x01~0x0F 均可能是合法 tag 或数据个数。用「解 N 项成功且不越界」做条件，失败回退，双路径兜底安全。
- bcd_time 显示格式改动可能影响其他 EB 项（EB030501 时钟等）——统一改进为可读格式，测试确认。
