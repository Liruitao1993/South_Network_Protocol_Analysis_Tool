# TCP 流量监控器 - 实施计划

## 步骤

### 1. 创建 monitor/tcp_monitor.py 骨架
- 导入依赖（scapy 用 try/except 包裹）
- TCPMonitorWidget 类骨架
- PacketSniffer(QThread) 类骨架
- TCPFlowReassembler 类骨架
- FlowBuffer 类骨架

### 2. 实现 PacketSniffer
- scapy sniff 封装
- BPF 过滤
- 包解析（IP/TCP/payload）
- signal: `packet_received` 发回元组

### 3. 实现 TCPFlowReassembler + FlowBuffer
- 流四元组 key: (src_ip, src_port, dst_ip, dst_port)，归一化为双向
- 方向判断（哪到哪算 upstream）
- 缓冲区按 SOF 0xC0 切帧
- 帧长从帧头读取（先硬编码通用逻辑，按国网新一代帧头格式：FC 16字节里有长度字段，先按 PB 帧头取长度）
- 切出完整帧回调

### 4. 实现 TCPMonitorWidget UI
- 顶部工具栏：网卡下拉 + 刷新 + 过滤输入 + 开始/停止 + 清空 + 协议选择
- 上半：流列表表格（6列：流ID / 源 / 目的 / 包数 / 字节 / 最新时间）
- 下半 Splitter：左帧列表 + 右解析结果表
- 表格都加 `_setup_table_copy_menu`（复制逻辑）

### 5. 集成抓包 → 重组 → 显示 流程
- 开始 → 启动 sniffer 线程
- 收到包 → 喂给 reassembler → 有新帧/新流 → 更新 UI
- 节流：100ms 定时器批量刷新
- 点击流 → 切换关注 → 刷新帧列表
- 点击帧 → 调用解析器 → 填充解析结果表

### 6. 集成到 main_gui.py
- 导入 TCPMonitorWidget
- `create_tcp_monitor_tab()` 方法
- 在 `__init__` 里调用，添加到 tab_widget
- 注入 gw_new_gen_parser 和 csg_new_gen_parser

### 7. 错误处理
- scapy 未安装 → 标签页显示提示文字 + 安装说明
- npcap 未安装 → 开始抓包时捕获异常，提示安装
- 解析失败 → 显示 "解析失败"，不崩溃

### 8. 测试验证
- 语法检查：python -c "import ast; ast.parse(...)"
- 启动测试：python main_gui.py 看标签页是否显示
- 功能验证（人工）：网卡列表、抓包、过滤、流列表、帧解析

## 风险点

- **帧长字段读取**：国网和南网新一代帧头长度字段位置和字节序可能不同。先按通用方式（SOF 后找长度字段），后续调优。
- **scapy 兼容性**：Windows 上 npcap 必须安装，否则抓不了。做好降级提示。
- **UI 卡顿**：抓包量大时直接逐包更新 UI 会卡。用 100ms 节流 + 批量刷新。
- **TCP 序列号处理**：MVP 版本不做乱序重排，按到达顺序拼缓冲，乱序时可能切帧失败。先按简单实现，遇到问题再优化。

## 验证命令

```bash
# 语法
python -c "import ast; ast.parse(open('monitor/tcp_monitor.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('main_gui.py', encoding='utf-8').read())"

# 启动
python main_gui.py
```

## 修改的文件

- 新建：`monitor/tcp_monitor.py`
- 修改：`main_gui.py`（加标签页 + 注入解析器）
