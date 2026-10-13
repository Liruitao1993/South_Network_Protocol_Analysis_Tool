# 布局探针：六协议的地址域 / 校验定位（实现前的实证）

> 目的：在写 `frame_addr_fix.py` 之前，用**仓库自身的解析器/校验器/组帧器**确认「地址域在哪、多长、校验覆盖到哪」，
> 避免凭记忆写偏移。做法：遍历各协议预设库里的**全部**帧 + 用仓库组帧器造国网带地址域帧，逐条核对。

## 探针命令（一次性脚本，未入库）

- `probe_addr.py`：遍历 `NW_command.json` / `DLT645_command.json` / `GW_command.json` + `commands.json` /
  `DLT698_command.json` / `YW645_command.json` / `CSG_UPLINK_command.json` 的全部帧；
  对每帧打印：我的布局推导（地址 span / 长度域 / 控制位）＋ 原帧校验自洽性 ＋ 该协议校验器 `fail` 数
  ＋ 解析器里名称含「地址/校验/HCS/FCS/CS」的行（偏移、值）。
- `probe_gdw.py`：国网预设里几乎没有带地址域的帧（`通信模块标识=0`），故用 `GDWFrameGenerator.generate_frame`
  造 `comm=1 relay=0/1` 与 `comm=0` 三类帧，再核对布局与校验。

## 实测结论（写进 `frame_addr_fix.py`）

| 协议 | 帧结构 | 地址域 | 校验 |
|---|---|---|---|
| 0 南网 | `68 L(2 小端) C 用户数据 CS 16`（**无第二个 68H**；L = 整帧长） | 仅当控制域 **D5=0x20**；`[4,16)` = 源 6B + 目的 6B，**每 6B 上线逆序**（`Frame.address = src[::-1]+dst[::-1]`） | `sum(frame[3:-2]) & 0xFF` → `[-2]`（`Frame.calculate_checksum`） |
| 6 645 | `68 A(6B) 68 C L DATA(+0x33) CS 16` | 固定 `[1,7)`，**低字节在前**（`dlt645_frame_gen.encode_addr`） | 由 `DLT645FrameGenerator.build_frame(..., scramble=False)` 整帧重建（CS 单一来源） |
| 7 国网 | `68 L(2 小端) C 信息域(6B) [地址域] AFN DT DATA CS 16`（L = 整帧长） | 当且仅当信息域 byte0 **bit2(0x04)=1**；长度 = **12 + 6×（byte0 高 4 位中继级别）**；`[10,10+len)` = 源 6B + 中继 6B×n + 目的 6B，均 BCD **逆序** | `sum(frame[3:-2]) & 0xFF` → `[-2]`（`GDWFrame.calculate_checksum`） |
| 8 698.45 | `68 L(2 小端) C 地址特征 SA CA HCS(2) APDU FCS(2) 16`（帧长 = L+2） | `SA 总长 = 2 + (地址特征字节 & 0x0F)`（特征 1B + SA 本体 `1+低4位`），`CA` 紧随 1B | `DLT69845FrameGenerator._assemble_frame` 重建 → `HCS = crc16(x-25)(L+C+SA+CA)`、`FCS = crc16(…+HCS+APDU)` |
| 13 依瓦645 | `68 A(6B) 68 COMMAND L DATA(+0x33) CS 16` | 固定 `[1,7)`，**高字节在前**（`yw645_wire.encode_addr12`，仅十进制数字） | `yw645_wire.encode_frame(addr, mode, unmask_data(frame[10:-2]))` 整帧重建 |
| 14 南网上行 | `68 L L 68 C A(7B) 用户数据 CS 16`（三种长度域形态，`resolve_layout` 判定） | `[addr_index, +7)` = A1 3B（低字节在前）+ A2 3B（小端）+ A3 1B | `csg_uplink_wire.encode_frame(c, addr, apdu, form)`：CS = 控制域+地址域+用户数据（**不含长度域**） |

### 实测证据要点

- **南网**：预设 `68 28 00 20 00 00 00 00 00 00 22 00 00 00 00 00 …85 16` 推导地址 span `(4,16)`、CS `sum[3:-2]` 命中；
  `D5=0` 的帧（如 `68 0C 00 00 02 00 …EF 16`）确认**无地址域**，解析器也只报「D5 地址域标识=0」。
- **国网**：生成帧 `68 1B 00 40 04 00 00 00 00 00 | 01 00 00 00 00 00 02 00 00 00 00 00 | 01 01 00 49 16`
  校验器 0 fail，地址 span `(10,22)`，解析器行 `源地址(A1) off=10` / `目的地址(A3) off=16`（其第 5 列是**闭区间末偏移**，
  故实现**不用解析器行偏移**，用上表的算术）；`relay=2` 帧地址域 24B，中继 `[16,28)` 保持不动。
- **国网福建增补**：`GW_command.json` 里两条「福建冻结 / 111111111111」帧自身长度域就不自洽（声明 31、实际 33），
  解析器也报 fail=1 ⇒ 实现按「长度域不符 / AFN∈0x50~0x56」双重拒绝。
- **698**：`04 33 00 00 00 00 00 0C …` 中 `地址特征=0x04 → SA 本体 5B`，解析器行 `SA off=5..9`、`CA off=10`、
  `HCS off=11..12`、`FCS off=30..31` 与推导一致；`0x05` 帧 → SA 本体 6B，同样一致（两例互证）。
- **依瓦**：`68 04 50 00 00 00 13 68 30 02 37 14 B4 16`（表号 `045000000013`）地址 = `04 50 00 00 00 13`
  ⇒ 十进制 12 位 → 高字节在前 BCD 成立。
- **南网上行**：`68 10 00 10 00 68 4B 00 00 00 01 00 00 00 0C … BB 16` 地址 = `00 00 00 | 01 00 00 | 00`
  （A2 小端 = 1）；`resolve_layout.form = l16x2` ⇒ 重建必须保留原形态。
- **crcmod 可缺**：`dl_t698_45_frame_gen` 顶层 `import crcmod` ⇒ `frame_addr_fix` 里协议模块一律**按需导入**；
  实测把 crcmod 屏蔽后 `import frame_addr_fix` 正常，协议8 的 `apply` 返回
  `地址替换失败：ImportError: blocked crcmod`（可读错误，不影响蓝牙页打开）。

## 对实现的影响

1. 六个协议的地址定位都用上表算术（**不用解析器表格偏移**，避免各协议「偏移/长度 vs 末偏移」口径差异）。
2. 校验重算能整帧重建的一律重建（6/8/13/14），南网/国网做字节拼接 + 复用各自 `calculate_checksum`。
3. 一律**先自证**（结构 + 原帧校验）再改；长度必须一致；福建增补与无地址域帧给可读拒绝理由。
