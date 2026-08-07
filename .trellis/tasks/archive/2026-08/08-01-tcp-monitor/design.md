# TCP 流量监控器 - 设计文档

## 架构

```
main_gui.py
  └── TCPMonitorWidget (monitor/tcp_monitor.py)
        ├── 顶部工具栏：网卡选择 / 过滤 / 开始停止 / 清空
        ├── 上半部分：TCP 流列表 (QTableWidget)
        └── 下半部分 (QSplitter)
              ├── 左侧：应用层帧列表 (QTableWidget)
              └── 右侧：解析结果表 (QTableWidget) + hex 显示
```

## 核心模块

### 1. TCPMonitorWidget (QWidget)
主控件，负责 UI 布局和抓包控制。

### 2. PacketSniffer (QThread)
抓包线程，封装 scapy sniff：
- `start(iface, bpf_filter)` → 开始
- `stop()` → 停止
- 每个包通过 signal 发回主线程 `packet_received(tuple)`

### 3. TCPFlowReassembler
流重组器，纯逻辑类（非 UI）：
- `flows: dict[flow_key, FlowBuffer]` — 按四元组分流
- `process_packet(src_ip, src_port, dst_ip, dst_port, payload, timestamp)`
- `get_flow_list()` → 流摘要列表
- `get_frames(flow_key)` → 该流切分好的应用帧列表

### 4. FlowBuffer
单条流的双向缓冲区：
- `upstream_buf: bytearray` / `downstream_buf: bytearray`
- `deframe(方向)` → 从缓冲区切出完整帧（返回 list of (timestamp, direction, frame_bytes)）

## 帧切分算法

国网新一代 / 南网新一代都是以 0xC0 为 SOF 的类 HDLC 帧：

```
while buf 中能找到 0xC0:
    pos = buf.find(0xC0)
    读取帧头（前若干字节），解析长度字段
    if 缓冲区长度 < 帧长: break  # 等下一个 segment
    切出完整帧，送回调
    buf = buf[pos + 帧长:]
```

帧长字段位置和大小端：参考 `gw_new_gen_parser.py` 和 `csg_new_gen_parser.py` 的帧头解析逻辑。

## 协议自动识别

切出帧后，根据帧头特征判断：
- 优先尝试国网新一代解析（看 DT/NID 等字段）
- 再尝试南网新一代
- 解析不报错 → 判定为对应协议

## 线程安全

- scapy sniff 在 QThread 中运行
- 每个包通过 `Signal` 发到主线程
- 流重组器在主线程操作（信号槽保证）
- UI 更新做节流（比如每 100ms 批量刷新一次，避免卡死）

## 依赖

- `scapy` — 运行时动态 import，失败时禁用功能并提示
- `npcap` (Windows) / `libpcap` (Linux) — 系统级依赖

## 集成到主窗口

- main_gui.py 新增：
  - `from monitor.tcp_monitor import TCPMonitorWidget`
  - `create_tcp_monitor_tab()` 方法
  - 在 `tab_widget` 添加 "TCP监控" 标签
- 解析器复用现有 `self.gw_new_gen_parser` / `self.csg_new_gen_parser`
- 通过 `set_parsers(gw_parser, csg_parser)` 注入到 widget
