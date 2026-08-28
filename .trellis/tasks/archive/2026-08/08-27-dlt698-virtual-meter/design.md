# Design：协议8 虚拟表（698.45 从站模拟器）

## 架构总览

```
meter_sim/                          # 新建包（纯逻辑，无 Qt）
├── __init__.py                     #   导出 MeterSimEngine / load_archive / save_archive
├── archive.py                      #   档案数据模型：加载/保存 meter_sim_data.json、查 OAD、增删改
├── link_layer.py                   #   698 链路层：从字节流定位 68...16 帧、解析 C/SA/CA/HCS、组 SA
├── request_parser.py               #   请求 APDU 解析（复用 dl_t698_45_apdu_parser/AXDRCoder）
├── response_builder.py             #   响应 APDU 构造（Get-Response Normal/NormalList/Record、链接、安全封装）
├── dynamic_data.py                 #   动态数据：当前时间/通信地址/电能量递增/冻结时标/漏点
└── engine.py                       #   MeterSimEngine：handle_request(frame_bytes, options) -> resp_bytes|None
                                    #   纯函数式入口，无状态（状态：档案+选项 dataclass）

meter_sim_widget.py                 # 新建 GUI 组件（PySide6）：VirtualMeterWidget(QWidget)
meter_sim_data.json                 # 新建数据种子（从 config.ini 迁移 194 条，app_paths 定位）

main_gui.py                         # 集成：import + addTab + _on_protocol_changed 协议8 可见
南网协议解析工具.spec                # datas 增加 meter_sim_data.json
test/test_meter_sim.py              # 新建测试
```

## 核心契约

### archive.py（档案）

数据文件格式（`meter_sim_data.json`，经 app_paths.data_path 定位、ensure_data_file 种子自愈）：

```json
{
  "version": 1,
  "items": [
    {"key": "00100200", "oi": "0010", "attr": "02", "idx": "00",
     "name": "正向有功电能", "data": "0105060000000106..."},
    {"key": "50040200_20210200", "oi": "2021", "attr": "02", "idx": "00",
     "frozen": "5004", "name": "日冻结_A相电压", "data": "01011c07e3..."}
  ]
}
```

- `key` = OI(4hex)+属性(2)+索引(2)；冻结档案 key = `冻结OI(4)属性(2)索引(2)_<原key>`（对齐开源 `50040200_20210200` 命名）
- `data` = A-XDR 编码的属性值 hex（不含 Get-Result 的 00/01 选择标签与 OAD）
- 迁移：一次性读取开源 `Meter698-45Simulator-master/config.ini` 的 `[MeterData]`，按空格切分（名称 + 数据 hex），key 前 8 位含下划线的拆 frozen/oi；生成种子 JSON 提交到仓库（生成脚本 `scripts/gen_meter_sim_data.py`，一次性离线脚本不打包）
- API：`load_archive() -> Archive`、`Archive.lookup(oi, attr, idx, frozen=None) -> Item|None`、`add/update/remove`、`save()`

### link_layer.py（链路帧收发）

- `extract_frames(buf: bytes) -> (frames: list[bytes], consumed: int)`：在字节流中按 68 起始 + 长度域（L 小端 2 字节，帧长 = L+2）定位完整帧，尾字节 16 校验；支持 FE 前缀跳过、粘包/分片（未完整则保留剩余）；HCS/FCS 用 DLT69845FrameGenerator._calc_crc 校验（坏帧丢弃）
- `parse_header(frame) -> dict`：C 控制域（DIR/PRM/SEG/SC/func）、地址标志字节（地址类型 2bit：0单/1通配/2组/3广播、逻辑地址、地址长度 N = 低5bit+1）、SA bytes、CA；返回 sa_raw/sa_addr_type/sa_len
- 组响应帧复用 `DLT69845FrameGenerator._assemble_frame(sa, ca, control, apdu)`（control=0xC3 响应：DIR=1 PRM=1 func=3）；HCS/FCS 由它计算

### response_builder.py（响应 APDU）

全部 bytes 操作；A-XDR 数据项用 `AXDRCoder().encode(value, tag)` 编码，但档案数据已是编码后 hex（直接 bytes.fromhex 拼接），仅动态数据需要 encode。

- `build_get_response_normal(piid, oad_bytes, data_bytes|None, dar=None)` → `85 01 piid OAD [01 data | 00 dar]`
- `build_get_response_normal_list(piid, [(oad, data|dar)...])` → `85 02 piid count OAD×n GetResult×n`
- `build_get_response_record(piid, oad, rsd_time_info, rows: list[bytes])` → `85 03 piid OAD 0200 count [0101 + rowdata]... 0000`（记录型结构对齐开源：OAD + 0200 + 行数 + 每行 0101 数据 + 0000 尾）；Selector 09（无时间锚点）按系统时间生成行
- `build_link_response(...)`：81/82 链接响应（预连接/应用链接）
- `wrap_security(apdu, mac_enabled)`：`90 00 len apdu 01 00 04 0A0B0C0D`（len 按 >127 的 81/82 变长编码规则）
- 事件（OI 3xxx，如 3320）：按开源 Event() 结构 `85 03 00 OAD RCSD... 0101 + 事件数据`，事件数据查档案
- DAR 码：成功 00；对象不存在 09（未知 OI）；其他按 698 标准

### dynamic_data.py

- `current_time_item()`：4000 属性 02 → `1c` + 系统时间 date_time_s（年 2 字节大端）
- `comm_address(sa_raw, meter_no)`：4001/4002/202a → `55 07 05` + 12 位表号（通配模式按表序号递增；单播模式可用请求 SA）
- `increase_energy(base_hex, elapsed_sec)`：00100200 array 5 个 double-long-unsigned，按开源规则（总费率 ×2、其余 ×1，偏移秒数）递增
- `freeze_timestamp(rsd_dt_bytes|None)`：取请求 RSD 中的 date_time_s（Selector 01/02）；Selector 09 或无时间 → 系统日期 00:00:00
- `leak_check(from_min, to_min, dt)`：曲线冻结漏点时段判定（时间在区间内 → 返回空记录行）

### engine.py

```python
@dataclass
class SimOptions:
    meter_count: int = 3          # 通配多表数量
    blacklist: list[str] = ()     # SA hex（小端反转后的表地址串）
    whitelist: list[str] = ()
    energy_increase: bool = False
    auto_freeze_time: bool = True # 日/月/曲线冻结自动时标
    leak_window: tuple|None = None  # (from_min, to_min)
    mac_enabled: bool = True
    meter_no_base: str = "..."    # 通配表号起始（12 位 BCD）

class MeterSimEngine:
    def __init__(self, archive: Archive, options: SimOptions): ...
    def handle_frame(self, frame: bytes, now=None) -> list[bytes]:
        # 返回 0..n 个响应帧（通配地址返回多帧/或单帧按表序号；黑白名单命中返回 []）
```

流程：parse_header → 地址过滤（黑/白名单）→ 安全解封装（10 00）→ APDU 分派（05 01/02/03、01/02 链接；06/07 回成功 DAR；其他回错误/忽略）→ 逐 OAD 查档案（动态 OI 先走 dynamic_data）→ 组响应 APDU → 安全封装（可选）→ _assemble_frame 链路帧。
- 通配地址（SA=AA..AA 且地址类型=1）：按 meter_count 决定响应，SA 用 `05 + 递增表号(小端)`；单播回原 SA
- 解析异常/未知服务：不抛异常，返回错误响应帧或 []，日志记录原因

## GUI 设计（meter_sim_widget.py）

`VirtualMeterWidget(QWidget)`，构造签名对齐其他独立组件（`__init__(self, parent=None)`，main_gui 创建后由协议切换控制可见性）。

布局（QVBoxLayout 三段）：

1. **模式工具栏**（QHBoxLayout）：
   - 模式切换：离线模拟 / 串口从站（QTabWidget 或分段按钮）
   - 串口从站模式：端口/波特率/校验/停止位下拉（独立 QSerialPort 选择，不复用主串口——从站需长期独占，典型用法是虚拟串口对）、开始/停止按钮（set_btn_icon 媒体播放/停止图标）、状态灯
   - 离线模式：请求帧输入框（QPlainTextEdit，不自动折行）+「生成响应」按钮 +「送解析器回读」按钮
2. **主体 QTabWidget**：
   - 「运行」页：收发日志（ZoomableTableWidget 或 QPlainTextEdit 等宽字体：时间戳/方向/数据标识/hex）+ 响应帧表格（复用单帧解析表格风格，直接调 DLT69845Parser.parse_to_table 展示响应帧字段）
   - 「档案数据」页：ZoomableTableWidget（key/OI/属性/索引/名称/数据hex/解码预览），增/删/改按钮、导入/导出 JSON、数据 hex 单元格编辑后用 AXDRCoder.decode 刷新预览列；改动即时保存 JSON
   - 「模拟设置」页：多表数量、黑/白名单（QPlainTextEdit，`/` 分隔）、电能量递增、冻结自动时标、漏点时段（两个 QTimeEdit）、明文 MAC 开关
3. 串口监听线程：独立 QThread（参考 SerialWorker 模式），raw 字节 → link_layer.extract_frames → engine.handle_frame → send_frame；日志信号回主线程；停止时线程退出（连接关闭 + wait），遵守线程回收要求

## main_gui.py 集成点

- import：`from meter_sim_widget import VirtualMeterWidget`
- 创建（~L1060 区，与其他 tab 一致）：`self.virtual_meter_tab = VirtualMeterWidget()`
- addTab（~L1107 报文工具附近）：`self._virtual_meter_tab_index = self.tab_widget.addTab(self.virtual_meter_tab, "虚拟表")`
- `_on_protocol_changed`：协议 8 时显示虚拟表 tab，其余隐藏（参考组帧 tab 的 south/gdw/dlt698 可见性写法；虚拟表仅 dlt698）
- 不接入主 SerialWorker（独立串口）；无需协议下拉外的其他注册（校验器/批量解析/查询页均不涉及）

## 数据迁移

`scripts/gen_meter_sim_data.py`（离线一次性）：读 `Meter698-45Simulator-master/config.ini` → 解析 194 条 → 写 `meter_sim_data.json` 种子到项目根。规则：
- key 长度 8：oi=key[0:4], attr=key[4:6], idx=key[6:8]
- key 含 `_`：frozen=前 8 位的前 4 位，原 OAD 在下划线后
- 名称取 ini 值第一段，数据 hex 取第二段（去换行）
- 生成后人工抽查 5 条与 config.ini 一致

## 打包

`南网协议解析工具.spec`：datas 增加 `('meter_sim_data.json', '.')`；hiddenimports 无需新增（meter_sim 包静态 import）。

## 风险与权衡

- **记录型响应结构**：开源 Record 响应为手工拼字节（8503+OAD+0200+count+0101...+0000），标准文档结构需在实现时用真实主站帧/开源回帧双向核对；测试以"开源输入帧→重写引擎响应帧字节一致或经解析器回读字段一致"双判据
- **645 模拟**：Meter645_core 仅 5KB，功能有限；作为 engine 中非 68 起始帧的旁路（645 帧以 68 起但长度域/地址结构不同），识别失败则忽略；不阻塞主体验收
- **串口独占**：从站模式与主界面串口组帧不能同口；UI  tooltip 说明建议虚拟串口对（如 VSPD）
- **开源代码 bug 不继承**：全局变量乱序、hex 字符串拼接、HCS 2 字节补零 hack 等全部重写；以项目 AXDRCoder/FrameGenerator 为准
