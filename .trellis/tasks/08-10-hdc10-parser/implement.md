# HDC 1.0 解析器实现计划

## 实现顺序

### Phase 1：骨架 + FC 解析

- [ ] 新建 `hdc10_parser.py`，定义 `HDC10Parser` 类
- [ ] 实现 CRC-24 / CRC-32 工具方法
- [ ] 实现 `parse_to_table` 主入口 + 输入模式路由
- [ ] 实现 `_parse_fc`：FC 帧控制 16 字节通用字段解析
- [ ] 实现载波 SOF 帧可变区域解析
- [ ] 实现载波信标 / SACK / 网间协调帧可变区域
- [ ] 实现无线 SOF / SACK / 信标帧可变区域
- [ ] FCCS 校验显示

### Phase 2：PB + MAC 帧头解析

- [ ] 实现 `_parse_pb_block`：单 PB / 多 PB 聚合解析
- [ ] 实现 PBH 解析（序列号、帧起始/结束标志）
- [ ] 实现 PBCS 显示
- [ ] 实现 MAC 帧分片重组（跨多 PB 的 MAC 帧拼接）
- [ ] 实现 `_parse_mac_header` 分发（标准 / 单跳）
- [ ] 实现标准帧 MAC 头解析（16 字节全部字段 + 可选 MAC 地址扩展）
- [ ] 实现单跳帧 MAC 头解析（4 字节）
- [ ] ICV（CRC-32）定位与显示

### Phase 3：MSDU + 应用层解析

- [ ] 实现 `_parse_msdu_payload`：按 MSDU 类型分发
- [ ] 实现应用层通用头解析（端口号 + 报文 ID + 控制字）
- [ ] 实现抄表类报文解析（0x001/0x002/0x003）上下行
- [ ] 实现确认/否认（0x020）
- [ ] 实现校时（0x004）
- [ ] 实现事件上报（0x008）
- [ ] 实现从节点注册系列（0x011/0x012/0x013）
- [ ] 实现升级系列（0x030~0x036）
- [ ] 实现台区户变关系识别（0x0A1）
- [ ] 实现查询 ID 信息（0x0A2）
- [ ] 实现精准校时（0x0A3）
- [ ] 实现通信测试（0x006）
- [ ] 实现抄控器报文（0x040/0x041）
- [ ] 未知报文 ID 回退到 hex 透明显示

### Phase 4：管理消息（MME）

- [ ] 新建 `hdc10_mme_parser.py`
- [ ] 实现管理消息头解析（MMTYPE 2B + 保留 1B）
- [ ] 实现关联请求/确认
- [ ] 实现心跳检测
- [ ] 实现发现列表消息
- [ ] 实现离线指示
- [ ] 未知 MME 类型回退

### Phase 5：GUI 集成

- [ ] main_gui.py import + 实例化
- [ ] 协议下拉框新增第 11 项
- [ ] 解析级别 / PB 帧类型 / 通道选择 UI 对索引 11 可见
- [ ] 单帧解析分派
- [ ] 批量解析分派
- [ ] 日志前缀剥离（复用 96..16 模式）
- [ ] 查询页：报文 ID 数据
- [ ] 校验器集成
- [ ] 摘要函数
- [ ] 深度解析对话框标题
- [ ] APP_VERSION 升级到 1.12.0

### Phase 6：校验器

- [ ] 新建 `validator/hdc10_validator.py`
- [ ] FCCS 校验
- [ ] PBCS 校验
- [ ] ICV 校验
- [ ] 长度 / 字段合法性检查

## 验证命令

```bash
# 基础导入测试
python -c "from hdc10_parser import HDC10Parser; p = HDC10Parser(); print('OK')"

# FC 解析测试 - 用一个已知报文
python test_hdc10.py

# GUI 启动测试
python main_gui.py --minimized

# 打包测试
pyinstaller 南网协议解析工具.spec --noconfirm
```

## 高风险点

1. **标准 MAC 帧头长度**：文档写 16 字节，但实际设备可能输出 15 字节（参考国网新一代的经验）。需用 ICV 回标验证来动态判定。
2. **管理消息头保留字段长度**：文档可能写 2 字节，实测可能为 1 字节（参考国网新一代的经验）。
3. **应用层报文头长度字段单位**：6bit，单位 4 字节块，容易搞错。
4. **TEI 跨字节的高低位排列**：必须严格对照文档各表，不能凭直觉。

## 文件清单

新增文件：
- `hdc10_parser.py`
- `hdc10_mme_parser.py`
- `validator/hdc10_validator.py`

修改文件：
- `main_gui.py`（集成点约 10 处）
- `config.json`（版本号）
