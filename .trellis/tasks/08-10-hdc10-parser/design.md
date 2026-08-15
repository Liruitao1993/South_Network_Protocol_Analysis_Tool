# HDC 1.0 解析器技术设计

## Architecture

基于现有 `gw_new_gen_parser.py` 的架构模式，但独立实现，不共享代码。理由：HDC 1.0 与 2.0 的字段定义、应用层报文结构差异很大，硬做继承反而增加耦合复杂度。

```
hdc10_parser.py              # 主解析器类 HDC10Parser
  ├── _parse_fc()            # FC 帧控制解析(16字节)
  ├── _parse_fc_vf_*()       # 各定界符类型的可变区域解析
  ├── _parse_pb_block()      # 物理块解析(PBH + 分片重组 + PBCS)
  ├── _parse_mac_header()    # MAC 帧头分发(标准/单跳)
  ├── _parse_mac_std_header()  # 标准帧 MAC 头
  ├── _parse_mac_singlehop_header()  # 单跳帧 MAC 头
  ├── _parse_msdu_payload()  # MSDU 解析(按类型分发)
  ├── _parse_application_layer()  # 应用层通用头 + 业务分派
  ├── _parse_cmd_payload()   # 业务报文数据深度解析
  └── _crc24 / _crc32        # 校验工具

hdc10_mme_parser.py          # 管理消息解析器(独立模块)
  └── parse_management_message()

validator/hdc10_validator.py # 校验器
  └── HDC10Validator(BaseValidator)
```

## Data Flow

```
输入 bytes
  → parse_to_table()
    ├─ 输入模式检测 (auto / fc_only / mac_only / pb_only / app / fc_pb / fc_mac)
    │
    ├─ [有 FC 前缀] → _parse_fc() → 判定定界符类型
    │     ├─ 信标帧 → 解析信标载荷 + BPCS + PBCS
    │     ├─ SOF 帧 → _parse_pb_block() → MAC帧重组 → _parse_mac_header()
    │     │                          → 按MSDU类型分发 → 应用层 / MME / IP
    │     ├─ SACK 帧 → 仅 FC(无载荷)
    │     └─ 网间协调帧 → 解析可变区域
    │
    ├─ [无 FC: mac_only / pb_only] → 直接解析 MAC / PB
    │
    └─ [app 模式] → 直接解析应用层报文
```

## Key Design Decisions

### 1. 字节序：小端为主

- 多字节整数（NID、TEI、序列号、报文 ID 等）一律小端
- MAC 地址：大端（文档明确说明）
- 与国网新一代解析器保持一致的约定

### 2. 跨字节位域：高位在前

TEI 等 12bit 跨字节字段，先出现的字节放高位。例如源 TEI = 字节 4（高 8 位）+ 字节 5 高 4 位（低 4 位）。

### 3. 应用层报文头长度单位为 4 字节块

文档定义"报文头长度"为 6bit，单位 = 4 字节块。解析时用 `hdr_len * 4` 计算 DATA 偏移。

### 4. CRC 算法复用

- CRC-24：`crcmod.mkCrcFun(0x1800063, initCrc=0, rev=True, xorOut=0)`，与国网新一代一致
- CRC-32：`zlib.crc32`，与国网新一代一致

### 5. 表格输出格式

与现有所有解析器一致的 7 元组：
```python
(field_name, raw_value, parsed_value, description, byte_start, byte_end, is_child)
```

## GUI 集成点

| 位置 | 修改内容 |
|------|---------|
| `main_gui.py:35` 附近 | import HDC10Parser |
| `main_gui.py:474` 附近 | self.hdc10_parser = HDC10Parser() |
| `main_gui.py:554` 协议下拉 | 新增第 11 项 "HDC 1.0 双模互联互通" |
| `main_gui.py:646-682` | 解析级别/PB帧类型/通道选择，索引 11 也显示 |
| `main_gui.py:1750` 占位文本 | 新增协议 11 的 placeholder |
| `main_gui.py:1820-1890` | 协议切换可见性逻辑 |
| `main_gui.py:2877` 批量解析 | 分派到 hdc10_parser |
| `main_gui.py:3467` 校验器 | 11: HDC10Validator() |
| `main_gui.py:2089` 查询页 | 新增 HDC 1.0 报文 ID 查询 |
| `main_gui.py:4374` 协议名映射 | 新增 "hdc10": 11 等 |
| `main_gui.py:4515-4544` 日志前缀剥离 | 可复用国网新一代的 96..16 逻辑 |
| `main_gui.py:4834` 摘要函数 | 新增 `_get_hdc10_summary` |
| `main_gui.py:6316` 深度解析对话框 | 协议 11 显示标题 |

## 风险与权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| HDC 1.0 与 2.0 代码重复度高 | 维护成本增加 | 结构对齐风格，CRC 工具可复用；但不强做继承 |
| 管理消息类型多，文档不全 | MME 解析覆盖率不足 | 先实现常见类型，未知类型回退到 hex 显示 |
| 应用层 DATA 域格式复杂 | 深度解析困难 | 抄表/升级/注册等核心报文做头部解析，DATA 透明显示 |
| 无线(HRF)通道测试样本少 | 无线解析可能有 bug | 先保证 PLC 通道正确，HRF 按文档实现，测试迭代 |

## 兼容性

- 不修改现有 11 个协议的任何解析逻辑
- 新增协议索引 11，现有配置文件 `config.json` 中协议索引不受影响
- 版本号：`APP_VERSION` 升级到 1.12.0（新增协议 = 次版本号升级）

## Rollback Plan

- 所有改动集中在：`hdc10_parser.py`（新）、`hdc10_mme_parser.py`（新）、`validator/hdc10_validator.py`（新）
- `main_gui.py` 仅做增量添加（import、实例化、下拉项、分支分派）
- 回滚：删除 3 个新文件 + 回退 main_gui.py 中新增的 11 号协议分支
