"""国网协议组帧字段Schema定义 (Q/GDW 10376.2-2024)

严格按照协议文档定义，覆盖所有下行命令的数据单元。
"""

from typing import Dict, Any, Tuple

GDW_AFNFN_SCHEMA: Dict[Tuple[int, int], Dict[str, Any]] = {

    # =========================================================================
    # AFN=00H 确认/否认 (上行响应，无下行数据单元)
    # =========================================================================
    (0x00, 1): {"name": "确认", "direction": "up", "fields": [],
                "doc": "<b>AFN=00H F1 确认</b><br>上行响应帧，无下行数据单元。"},
    (0x00, 2): {"name": "否认", "direction": "up", "fields": [],
                "doc": "<b>AFN=00H F2 否认</b><br>上行响应帧，无下行数据单元。"},

    # =========================================================================
    # AFN=01H 初始化
    # =========================================================================
    (0x01, 1): {"name": "硬件初始化", "direction": "down", "fields": [],
                "doc": "<b>AFN=01H F1 硬件初始化</b><br>无数据单元。"},
    (0x01, 2): {"name": "参数区初始化", "direction": "down", "fields": [],
                "doc": "<b>AFN=01H F2 参数区初始化</b><br>无数据单元。"},
    (0x01, 3): {"name": "数据区初始化", "direction": "down", "fields": [],
                "doc": "<b>AFN=01H F3 数据区初始化</b><br>无数据单元。"},

    # =========================================================================
    # AFN=02H 数据转发
    # =========================================================================
    (0x02, 1): {
        "name": "转发通信协议数据帧",
        "direction": "down",
        "fields": [
            {"name": "通信协议类型", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "报文长度", "type": "uint8", "default": 0},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=02H F1 转发通信协议数据帧</b><br>数据单元：通信协议类型(1B)+报文长度(1B)+报文内容(NB)"
    },

    # =========================================================================
    # AFN=03H 查询数据
    # =========================================================================
    (0x03, 1):  {"name": "厂商代码和版本信息", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F1</b><br>无下行数据单元。"},
    (0x03, 2):  {"name": "噪声值", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F2</b><br>无下行数据单元。"},
    (0x03, 3):  {
        "name": "从节点侦听信息",
        "direction": "down",
        "fields": [
            {"name": "开始节点指针", "type": "uint8", "default": 0,
             "description": "节点侦听列表中的指针位置，0为第一个指针"},
            {"name": "读取节点数量", "type": "uint8", "default": 1,
             "description": "N<=16"},
        ],
        "doc": "<b>AFN=03H F3 从节点侦听信息</b><br>数据单元：开始节点指针(1B)+读取节点数量(1B)"
    },
    (0x03, 4):  {"name": "主节点地址", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F4</b><br>无下行数据单元。"},
    (0x03, 5):  {"name": "主节点状态字和通信速率", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F5</b><br>无下行数据单元。"},
    (0x03, 6):  {
        "name": "主节点干扰状态",
        "direction": "down",
        "fields": [
            {"name": "持续时间", "type": "uint8", "default": 0,
             "description": "等待查询执行的时间，单位min，0表示立即停止"},
        ],
        "doc": "<b>AFN=03H F6 主节点干扰状态</b><br>数据单元：持续时间(1B)"
    },
    (0x03, 7):  {"name": "从节点监控最大超时时间", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F7</b><br>无下行数据单元。"},
    (0x03, 8):  {"name": "无线通信参数", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F8</b><br>无下行数据单元。"},
    (0x03, 9):  {
        "name": "通信延时相关广播通信时长",
        "direction": "down",
        "fields": [
            {"name": "通信协议类型", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "报文长度", "type": "uint8", "default": 0},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=03H F9</b><br>数据单元：通信协议类型(1B)+报文长度(1B)+报文内容(NB)"
    },
    (0x03, 10): {"name": "本地通信模块运行模式信息", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F10</b><br>无下行数据单元。"},
    (0x03, 11): {
        "name": "本地通信模块AFN索引",
        "direction": "down",
        "fields": [
            {"name": "AFN功能码", "type": "uint8", "default": 0},
        ],
        "doc": "<b>AFN=03H F11</b><br>数据单元：AFN功能码(1B)"
    },
    (0x03, 12): {"name": "查询CCO模块ID", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F12</b><br>无下行数据单元。"},
    (0x03, 16): {"name": "查询宽带载波通信参数", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F16</b><br>无下行数据单元。"},
    (0x03, 17): {"name": "查询无线频段", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F17</b><br>无下行数据单元。"},
    (0x03, 18): {"name": "查询本地通信信道加密参数", "direction": "down", "fields": [],
                 "doc": "<b>AFN=03H F18</b><br>无下行数据单元。"},
    (0x03, 100): {"name": "查询场强门限", "direction": "down", "fields": [],
                  "doc": "<b>AFN=03H F100</b><br>无下行数据单元。"},

    # =========================================================================
    # AFN=04H 链路接口检测
    # =========================================================================
    (0x04, 1): {
        "name": "发送测试",
        "direction": "down",
        "fields": [
            {"name": "持续时间", "type": "uint8", "default": 0,
             "description": "单位s，0表示停止发送"},
        ],
        "doc": "<b>AFN=04H F1</b><br>数据单元：持续时间(1B)"
    },
    (0x04, 2): {"name": "从节点点名", "direction": "down", "fields": [],
                "doc": "<b>AFN=04H F2</b><br>无数据单元。"},
    (0x04, 3): {
        "name": "本地通信模块报文通信测试",
        "direction": "down",
        "fields": [
            {"name": "测试通信速率", "type": "uint8", "default": 0,
             "description": "0表示默认通信速率"},
            {"name": "目标地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "通信协议类型", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "报文长度", "type": "uint8", "default": 0},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=04H F3</b><br>数据单元：测试通信速率(1B)+目标地址(6B)+通信协议类型(1B)+报文长度(1B)+报文内容(NB)"
    },

    # =========================================================================
    # AFN=05H 控制命令
    # =========================================================================
    (0x05, 1): {
        "name": "设置主节点地址",
        "direction": "down",
        "fields": [
            {"name": "主节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
        ],
        "doc": "<b>AFN=05H F1</b><br>数据单元：主节点地址(6B)"
    },
    (0x05, 2): {
        "name": "允许/禁止从节点上报",
        "direction": "down",
        "fields": [
            {"name": "事件上报状态标志", "type": "enum", "default": 1,
             "enum_map": {0: "禁止", 1: "允许"}},
        ],
        "doc": "<b>AFN=05H F2</b><br>数据单元：事件上报状态标志(1B)，0=禁止，1=允许"
    },
    (0x05, 3): {
        "name": "启动广播",
        "direction": "down",
        "fields": [
            {"name": "控制字", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "相位识别"}},
            {"name": "报文长度", "type": "uint8", "default": 0},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=05H F3</b><br>数据单元：控制字(1B)+报文长度(1B)+报文内容(NB)"
    },
    (0x05, 4): {
        "name": "设置从节点监控最大超时时间",
        "direction": "down",
        "fields": [
            {"name": "最大超时时间", "type": "uint8", "default": 60,
             "description": "单位s"},
        ],
        "doc": "<b>AFN=05H F4</b><br>数据单元：最大超时时间(1B)"
    },
    (0x05, 5): {
        "name": "设置无线通信参数",
        "direction": "down",
        "fields": [
            {"name": "无线信道组", "type": "uint8", "default": 0,
             "description": "0~63对应0~63组，254=自动选择，255=保持不变"},
            {"name": "无线主节点发射功率", "type": "enum", "default": 0,
             "enum_map": {0: "最高", 1: "次高", 2: "次低", 3: "最低", 255: "保持不变"}},
        ],
        "doc": "<b>AFN=05H F5</b><br>数据单元：无线信道组(1B)+发射功率(1B)"
    },
    (0x05, 6): {
        "name": "允许/禁止台区识别",
        "direction": "down",
        "fields": [
            {"name": "台区识别使能标志", "type": "enum", "default": 1,
             "enum_map": {0: "禁止", 1: "允许"}},
        ],
        "doc": "<b>AFN=05H F6</b><br>数据单元：台区识别使能标志(1B)"
    },
    (0x05, 10): {
        "name": "串口速率配置",
        "direction": "down",
        "fields": [
            {"name": "通信速率值", "type": "enum", "default": 4,
             "enum_map": {0: "9600bps", 1: "19200bps", 2: "38400bps", 3: "57600bps", 4: "115200bps"}},
        ],
        "doc": "<b>AFN=05H F10</b><br>数据单元：通信速率值(1B)，0=9600,1=19200,2=38400,3=57600,4=115200"
    },
    (0x05, 16): {
        "name": "设置宽带载波通信参数",
        "direction": "down",
        "fields": [
            {"name": "宽带载波频段", "type": "enum", "default": 0,
             "enum_map": {0: "1.953~11.96MHz", 1: "2.441~5.615MHz", 2: "0.781~2.930MHz", 3: "1.758~2.930MHz"}},
        ],
        "doc": "<b>AFN=05H F16</b><br>数据单元：宽带载波频段(1B)"
    },
    (0x05, 17): {
        "name": "设置无线频段",
        "direction": "down",
        "fields": [
            {"name": "无线调制方式", "type": "enum", "default": 2,
             "enum_map": {2: "500kHz", 3: "200kHz"}},
            {"name": "无线信道编号", "type": "uint8", "default": 1},
            {"name": "信道协商使能", "type": "enum", "default": 1,
             "enum_map": {0: "禁止", 1: "允许"}},
        ],
        "doc": "<b>AFN=05H F17</b><br>数据单元：调制方式(1B)+信道编号(1B)+协商使能(1B)"
    },
    (0x05, 18): {
        "name": "允许/禁止本地通信信道加密",
        "direction": "down",
        "fields": [
            {"name": "加密使能标识", "type": "enum", "default": 0,
             "enum_map": {0: "禁止加密", 1: "允许加密"}},
            {"name": "加密模式", "type": "enum", "default": 0,
             "enum_map": {0: "兼容模式", 1: "强制模式"}},
            {"name": "加密算法类型", "type": "enum", "default": 0,
             "enum_map": {0: "国密算法", 1: "国际算法CBC", 2: "国际算法GCM"}},
            {"name": "密钥更新周期", "type": "uint16", "endian": "little", "default": 0,
             "description": "单位10s，0=使用缺省配置"},
        ],
        "doc": "<b>AFN=05H F18</b><br>数据单元：使能(1B)+模式(1B)+算法(1B)+周期(2B)"
    },
    (0x05, 20): {
        "name": "广播透传命令",
        "direction": "down",
        "fields": [
            {"name": "控制字", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "报文长度", "type": "uint16", "endian": "little", "default": 0,
             "length_field": "报文内容"},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=05H F20</b><br>数据单元：控制字(1B)+报文长度(2B)+报文内容(NB)"
    },
    (0x05, 100): {
        "name": "设置场强门限",
        "direction": "down",
        "fields": [
            {"name": "场强门限", "type": "uint8", "default": 96,
             "description": "取值50~120，默认96"},
        ],
        "doc": "<b>AFN=05H F100</b><br>数据单元：场强门限(1B)"
    },
    (0x05, 101): {
        "name": "设置中心节点时间",
        "direction": "down",
        "fields": [
            {"name": "秒", "type": "bcd", "length": 1, "default": "00"},
            {"name": "分", "type": "bcd", "length": 1, "default": "00"},
            {"name": "时", "type": "bcd", "length": 1, "default": "00"},
            {"name": "日", "type": "bcd", "length": 1, "default": "01"},
            {"name": "月", "type": "bcd", "length": 1, "default": "01"},
            {"name": "年", "type": "bcd", "length": 1, "default": "25"},
        ],
        "doc": "<b>AFN=05H F101</b><br>数据单元：秒(1B BCD)+分(1B)+时(1B)+日(1B)+月(1B)+年(1B)"
    },
    (0x05, 200): {
        "name": "控制拒绝节点上报",
        "direction": "down",
        "fields": [
            {"name": "从节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
        ],
        "doc": "<b>AFN=05H F200</b><br>数据单元：从节点地址(6B)"
    },

    # =========================================================================
    # AFN=06H 主动上报 (上行，无下行)
    # =========================================================================
    (0x06, 1): {"name": "上报从节点信息", "direction": "up", "fields": [],
                "doc": "<b>AFN=06H F1</b><br>上行主动上报。"},
    (0x06, 2): {"name": "上报抄读数据", "direction": "up", "fields": [],
                "doc": "<b>AFN=06H F2</b><br>上行主动上报。"},
    (0x06, 3): {"name": "上报路由工况变动信息", "direction": "up", "fields": [],
                "doc": "<b>AFN=06H F3</b><br>上行主动上报。"},
    (0x06, 4): {"name": "上报从节点信息及设备类型", "direction": "up", "fields": [],
                "doc": "<b>AFN=06H F4</b><br>上行主动上报。"},
    (0x06, 5): {"name": "上报从节点事件", "direction": "up", "fields": [],
                "doc": "<b>AFN=06H F5</b><br>上行主动上报。"},

    # =========================================================================
    # AFN=10H 路由查询
    # =========================================================================
    (0x10, 1):  {"name": "查询从节点数量", "direction": "down", "fields": [],
                 "doc": "<b>AFN=10H F1</b><br>无下行数据单元。"},
    (0x10, 2):  {
        "name": "查询从节点信息",
        "direction": "down",
        "fields": [
            {"name": "从节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "从节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F2</b><br>数据单元：从节点起始序号(2B)+从节点数量(1B)"
    },
    (0x10, 3):  {
        "name": "查询指定从节点的上一级中继路由信息",
        "direction": "down",
        "fields": [
            {"name": "从节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
        ],
        "doc": "<b>AFN=10H F3</b><br>数据单元：从节点地址(6B)"
    },
    (0x10, 4):  {"name": "查询路由运行状态", "direction": "down", "fields": [],
                 "doc": "<b>AFN=10H F4</b><br>无下行数据单元。"},
    (0x10, 5):  {
        "name": "查询未抄读成功的从节点信息",
        "direction": "down",
        "fields": [
            {"name": "从节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "从节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F5</b><br>数据单元：从节点起始序号(2B)+从节点数量(1B)"
    },
    (0x10, 6):  {
        "name": "查询主动注册的从节点信息",
        "direction": "down",
        "fields": [
            {"name": "从节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "从节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F6</b><br>数据单元：从节点起始序号(2B)+从节点数量(1B)"
    },
    (0x10, 7):  {
        "name": "查询从节点模块ID信息",
        "direction": "down",
        "fields": [
            {"name": "从节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "从节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F7</b><br>数据单元：从节点起始序号(2B)+从节点数量(1B)"
    },
    (0x10, 9):  {"name": "查询网络规模", "direction": "down", "fields": [],
                 "doc": "<b>AFN=10H F9</b><br>无下行数据单元。"},
    (0x10, 20): {
        "name": "查询双模网络拓扑信息",
        "direction": "down",
        "fields": [
            {"name": "节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F20</b><br>数据单元：节点起始序号(2B)+节点数量(1B)，首帧必须从1开始，1为主节点"
    },
    (0x10, 21): {
        "name": "查询网络拓扑信息",
        "direction": "down",
        "fields": [
            {"name": "节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F21</b><br>数据单元：节点起始序号(2B)+节点数量(1B)"
    },
    (0x10, 31): {
        "name": "查询相线信息",
        "direction": "down",
        "fields": [
            {"name": "节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F31</b><br>数据单元：节点起始序号(2B)+节点数量(1B)"
    },
    (0x10, 40): {
        "name": "流水线查询ID信息",
        "direction": "down",
        "fields": [
            {"name": "设备类型", "type": "enum", "default": 1,
             "enum_map": {1: "抄控器", 2: "CCO", 3: "电能表通信单元", 4: "中继器", 5: "II型采集器", 6: "I型采集器", 7: "三相表通信单元"}},
            {"name": "节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "ID类型", "type": "enum", "default": 1,
             "enum_map": {1: "芯片ID", 2: "模块ID"}},
        ],
        "doc": "<b>AFN=10H F40</b><br>数据单元：设备类型(1B)+节点地址(6B)+ID类型(1B)"
    },
    (0x10, 100): {"name": "查询微功率无线网络规模", "direction": "down", "fields": [],
                  "doc": "<b>AFN=10H F100</b><br>无下行数据单元。"},
    (0x10, 101): {
        "name": "查询微功率无线从节点信息",
        "direction": "down",
        "fields": [
            {"name": "从节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "从节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F101</b><br>数据单元：从节点起始序号(2B)+从节点数量(1B)"
    },
    (0x10, 104): {"name": "查询升级后模块版本信息", "direction": "down", "fields": [],
                  "doc": "<b>AFN=10H F104</b><br>无下行数据单元。"},
    (0x10, 111): {"name": "查询网络信息", "direction": "down", "fields": [],
                  "doc": "<b>AFN=10H F111</b><br>无下行数据单元。"},
    (0x10, 112): {
        "name": "查询宽带载波芯片信息",
        "direction": "down",
        "fields": [
            {"name": "节点起始序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "节点数量", "type": "uint8", "default": 1},
        ],
        "doc": "<b>AFN=10H F112</b><br>数据单元：节点起始序号(2B)+节点数量(1B)"
    },

    # =========================================================================
    # AFN=11H 路由设置
    # =========================================================================
    (0x11, 1): {
        "name": "添加从节点",
        "direction": "down",
        "fields": [
            {"name": "从节点数量", "type": "uint8", "default": 1},
            {"name": "从节点列表", "type": "list",
             "count_field": "从节点数量",
             "item_fields": [
                 {"name": "从节点地址", "type": "bytes", "length": 6,
                        "reverse": True, "default": "000000000000"},
                 {"name": "通信协议类型", "type": "enum", "default": 0,
                  "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
             ]},
        ],
        "doc": "<b>AFN=11H F1</b><br>数据单元：数量(1B)+[地址(6B)+协议类型(1B)]*n"
    },
    (0x11, 2): {
        "name": "删除从节点",
        "direction": "down",
        "fields": [
            {"name": "从节点数量", "type": "uint8", "default": 1},
            {"name": "从节点列表", "type": "list",
             "count_field": "从节点数量",
             "item_fields": [
                 {"name": "从节点地址", "type": "bytes", "length": 6,
                        "reverse": True, "default": "000000000000"},
             ]},
        ],
        "doc": "<b>AFN=11H F2</b><br>数据单元：数量(1B)+[地址(6B)]*n"
    },
    (0x11, 3): {
        "name": "设置从节点固定中继路径",
        "direction": "down",
        "fields": [
            {"name": "从节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "中继级别", "type": "uint8", "default": 0},
            {"name": "中继路径", "type": "list",
             "count_field": "中继级别",
             "item_fields": [
                 {"name": "中继节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
             ]},
        ],
        "doc": "<b>AFN=11H F3</b><br>数据单元：目的地址(6B)+中继级别(1B)+[中继地址(6B)]*n"
    },
    (0x11, 4): {
        "name": "设置路由工作模式",
        "direction": "down",
        "fields": [
            {"name": "工作模式", "type": "uint8", "default": 0,
             "description": "D0=工作状态(0抄表1学习), D1=注册允许状态"},
            {"name": "速率单位标识", "type": "enum", "default": 0,
             "enum_map": {0: "bit/s", 1: "kbit/s"}},
            {"name": "通信速率1", "type": "uint16", "endian": "little", "default": 0,
             "description": "0表示默认通信速率"},
        ],
        "doc": "<b>AFN=11H F4</b><br>数据单元：工作模式(1B)+速率单位标识(1B)+通信速率1(2B)"
    },
    (0x11, 5): {
        "name": "激活从节点主动注册",
        "direction": "down",
        "fields": [
            {"name": "开始时间", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "持续时间", "type": "uint16", "endian": "little", "default": 10,
             "description": "单位min"},
            {"name": "从节点重发次数", "type": "uint8", "default": 3},
            {"name": "随机等待时间片个数", "type": "uint8", "default": 10,
             "description": "时间片指150ms"},
        ],
        "doc": "<b>AFN=11H F5</b><br>数据单元：开始时间(6B BCD)+持续时间(2B)+重发次数(1B)+随机等待时间片个数(1B)"
    },
    (0x11, 6): {"name": "终止从节点主动注册", "direction": "down", "fields": [],
                "doc": "<b>AFN=11H F6</b><br>无数据单元。"},
    (0x11, 100): {
        "name": "设置网络规模",
        "direction": "down",
        "fields": [
            {"name": "网络规模", "type": "uint16", "endian": "little", "default": 1000},
        ],
        "doc": "<b>AFN=11H F100</b><br>数据单元：网络规模(2B)"
    },
    (0x11, 101): {"name": "启动网络维护进程", "direction": "down", "fields": [],
                  "doc": "<b>AFN=11H F101</b><br>无数据单元。"},
    (0x11, 102): {"name": "启动组网", "direction": "down", "fields": [],
                  "doc": "<b>AFN=11H F102</b><br>无数据单元。"},

    # =========================================================================
    # AFN=12H 路由控制
    # =========================================================================
    (0x12, 1): {"name": "重启", "direction": "down", "fields": [],
                "doc": "<b>AFN=12H F1</b><br>无数据单元。"},
    (0x12, 2): {"name": "暂停", "direction": "down", "fields": [],
                "doc": "<b>AFN=12H F2</b><br>无数据单元。"},
    (0x12, 3): {"name": "恢复", "direction": "down", "fields": [],
                "doc": "<b>AFN=12H F3</b><br>无数据单元。"},

    # =========================================================================
    # AFN=13H 路由数据转发
    # =========================================================================
    (0x13, 1): {
        "name": "监控从节点",
        "direction": "down",
        "fields": [
            {"name": "通信协议类型", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "通信延时相关性标志", "type": "enum", "default": 0,
             "enum_map": {0: "无关", 1: "相关"}},
            {"name": "从节点附属节点数量", "type": "uint8", "default": 0},
            {"name": "从节点附属节点列表", "type": "list",
             "count_field": "从节点附属节点数量",
             "item_fields": [
                 {"name": "从节点附属节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
             ]},
            {"name": "报文长度", "type": "uint8", "default": 0},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=13H F1</b><br>数据单元：协议类型(1B)+延时标志(1B)+附属节点数量(1B)+[地址(6B)]*n+报文长度(1B)+报文内容"
    },
    (0x13, 2): {
        "name": "扩展监控从节点",
        "direction": "down",
        "fields": [
            {"name": "通信协议类型", "type": "enum", "default": 0,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "通信延时相关性标志", "type": "enum", "default": 0,
             "enum_map": {0: "无关", 1: "相关"}},
            {"name": "从节点附属节点数量", "type": "uint8", "default": 0},
            {"name": "从节点附属节点列表", "type": "list",
             "count_field": "从节点附属节点数量",
             "item_fields": [
                 {"name": "从节点附属节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
             ]},
            {"name": "报文长度", "type": "uint16", "endian": "little", "default": 0,
             "length_field": "报文内容"},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>AFN=13H F2</b><br>数据单元：协议类型(1B)+延时标志(1B)+附属节点数量(1B)+[地址(6B)]*n+报文长度(2B)+报文内容"
    },

    # =========================================================================
    # AFN=14H 路由数据抄读 (下行)
    # =========================================================================
    (0x14, 1): {
        "name": "路由请求抄读内容",
        "direction": "down",
        "fields": [
            {"name": "抄读标志", "type": "enum", "default": 2,
             "enum_map": {0: "抄读失败", 1: "抄读成功", 2: "可以抄读"}},
            {"name": "通信延时相关性标志", "type": "enum", "default": 0,
             "enum_map": {0: "无关", 1: "相关"}},
            {"name": "路由请求数据长度", "type": "uint8", "default": 0},
            {"name": "路由请求数据内容", "type": "bytes", "default": ""},
            {"name": "从节点附属节点数量", "type": "uint8", "default": 0},
            {"name": "从节点附属节点列表", "type": "list",
             "count_field": "从节点附属节点数量",
             "item_fields": [
                 {"name": "从节点附属节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
             ]},
        ],
        "doc": "<b>AFN=14H F1</b><br>数据单元：抄读标志(1B)+延时标志(1B)+数据长度(1B)+数据内容+附属节点数量(1B)+[地址(6B)]*n"
    },
    (0x14, 2): {"name": "路由请求集中器时钟", "direction": "down", "fields": [],
                "doc": "<b>AFN=14H F2</b><br>无下行数据单元。"},
    (0x14, 3): {"name": "请求依通信延时修正通信数据", "direction": "down", "fields": [],
                "doc": "<b>AFN=14H F3</b><br>无下行数据单元。"},
    (0x14, 4): {"name": "路由请求交采信息", "direction": "down", "fields": [],
                "doc": "<b>AFN=14H F4</b><br>无下行数据单元。"},

    # =========================================================================
    # AFN=15H 文件传输
    # =========================================================================
    (0x15, 1): {
        "name": "文件传输方式1",
        "direction": "down",
        "fields": [
            {"name": "传输阶段标识", "type": "enum", "default": 1,
             "enum_map": {1: "文件传输请求", 2: "文件内容传输", 3: "文件传输结束"}},
            {"name": "文件类型", "type": "uint8", "default": 0,
             "description": "0=保留,1=CCO程序,2=CCO参数,3=从节点程序,4=从节点参数"},
            {"name": "文件标识", "type": "uint8", "default": 0},
        ],
        "doc": "<b>AFN=15H F1</b><br>数据单元：传输阶段标识(1B)+文件类型(1B)+文件标识(1B)"
    },

    # =========================================================================
    # AFN=F0H 内部调试 / LME扩展
    # =========================================================================
    (0xF0, 62): {
        "name": "LME扩展 查询双模主详细信息",
        "direction": "down",
        "fields": [
            {"name": "保留", "type": "uint16", "endian": "little", "default": 0,
             "description": "固定为0x0000"},
        ],
        "doc": "<b>AFN=F0H F62 LME扩展 查询双模主详细信息</b><br>数据单元：保留(2B)，固定为0x0000"
    },

    # =========================================================================
    # AFN=F1H 并发抄表
    # =========================================================================
    (0xF1, 1): {
        "name": "集中器主动并发抄表",
        "direction": "down",
        "fields": [
            {"name": "从节点数量", "type": "uint8", "default": 1},
            {"name": "从节点列表", "type": "list",
             "count_field": "从节点数量",
             "item_fields": [
                 {"name": "从节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
                 {"name": "通信协议类型", "type": "enum", "default": 0,
                  "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
                 {"name": "报文长度", "type": "uint8", "default": 0},
                 {"name": "报文内容", "type": "bytes", "default": ""},
             ]},
        ],
        "doc": "<b>AFN=F1H F1</b><br>数据单元：数量(1B)+[地址(6B)+协议类型(1B)+报文长度(1B)+报文内容]*n"
    },
    (0xF1, 2): {"name": "集中器确认主动上报", "direction": "down", "fields": [],
                "doc": "<b>AFN=F1H F2</b><br>无数据单元。"},

    # =========================================================================
    # 福建增补规约（附件3：1376.2集中器本地通信模块接口协议【福建增补】V1.4）
    # =========================================================================
    (0x50, 1): {"name": "确认", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=50H F1 确认</b><br>上行响应帧，无下行数据单元。"},
    (0x50, 2): {"name": "否认", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=50H F2 否认</b><br>上行响应帧，数据单元：错误状态字(1B)。"},
    (0x50, 3): {"name": "确认且还有后续任务", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=50H F3</b><br>上行响应帧，无数据单元。"},

    (0x51, 1): {"name": "硬件初始化", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=51H F1 硬件初始化</b><br>无数据单元。"},
    (0x51, 2): {"name": "参数区初始化", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=51H F2 参数区初始化</b><br>无数据单元。"},
    (0x51, 3): {"name": "数据区初始化", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=51H F3 数据区初始化</b><br>无数据单元。"},

    (0x52, 1): {
        "name": "转发通信协议数据帧",
        "direction": "down",
        "fields": [
            {"name": "通信对象类型", "type": "enum", "default": 1,
             "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块", 4: "路由模块", 5: "信号处理模块"}},
            {"name": "通信对象地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "透明转发通信控制字", "type": "uint8", "default": 0,
             "description": "BS8"},
            {"name": "接收等待报文超时时间", "type": "uint8", "default": 1,
             "description": "10ms或1s"},
            {"name": "接收等待字节超时时间", "type": "uint8", "default": 10,
             "description": "10ms"},
            {"name": "报文长度", "type": "uint16", "endian": "little", "default": 0,
             "length_field": "报文内容"},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>福建增补 AFN=52H F1 透明转发通信协议数据帧</b><br>数据单元：通信对象类型(1B)+通信对象地址(6B)+控制字(1B)+等待报文超时(1B)+等待字节超时(1B)+报文长度(2B)+报文内容(NB)"
    },
    (0x52, 2): {
        "name": "CCO任务队列_智能补采",
        "direction": "down",
        "fields": [
            {"name": "任务方案号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "具体任务序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "通信对象类型", "type": "enum", "default": 1,
             "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
            {"name": "通信对象地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "规约类型", "type": "enum", "default": 2,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "保留", "type": "uint8", "default": 0},
            {"name": "报文长度", "type": "uint16", "endian": "little", "default": 0,
             "length_field": "报文内容"},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>福建增补 AFN=52H F2 CCO任务队列_智能补采</b><br>数据单元：方案号(2B)+序号(2B)+对象类型(1B)+对象地址(6B)+规约类型(1B)+保留(1B)+报文长度(2B)+报文内容(NB)"
    },
    (0x52, 3): {
        "name": "CCO任务队列_本地定时",
        "direction": "down",
        "fields": [
            {"name": "任务方案号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "具体任务序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "通信对象类型", "type": "enum", "default": 1,
             "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
            {"name": "通信对象地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "规约类型", "type": "enum", "default": 2,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "保留", "type": "uint8", "default": 0},
            {"name": "报文长度", "type": "uint16", "endian": "little", "default": 0,
             "length_field": "报文内容"},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>福建增补 AFN=52H F3 CCO任务队列_本地定时</b><br>数据单元：同F2格式"
    },
    (0x52, 11): {
        "name": "CCO并发抄表_福建",
        "direction": "down",
        "fields": [
            {"name": "任务方案号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "具体任务序号", "type": "uint16", "endian": "little", "default": 1},
            {"name": "通信对象类型", "type": "enum", "default": 1,
             "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
            {"name": "通信对象地址", "type": "bcd", "length": 6, "default": "000000000000"},
            {"name": "规约类型", "type": "enum", "default": 2,
             "enum_map": {0: "透明传输", 1: "DL/T 645-1997", 2: "DL/T 645-2007", 3: "DL/T 698.45"}},
            {"name": "保留", "type": "uint8", "default": 0},
            {"name": "报文长度", "type": "uint16", "endian": "little", "default": 0,
             "length_field": "报文内容"},
            {"name": "报文内容", "type": "bytes", "default": ""},
        ],
        "doc": "<b>福建增补 AFN=52H F11 CCO并发抄表_福建</b><br>数据单元：同F2格式"
    },
    (0x52, 12): {"name": "清空CCO并发抄表队列", "direction": "down", "fields": [],
                 "doc": "<b>福建增补 AFN=52H F12</b><br>无数据单元。"},

    (0x53, 1): {"name": "本地模块参数配置请求", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=53H F1</b><br>无下行数据单元。"},
    (0x53, 2): {"name": "主节点地址", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=53H F2</b><br>无下行数据单元。"},
    (0x53, 4): {"name": "厂商代码和版本信息", "direction": "down", "fields": [
        {"name": "通信对象类型", "type": "enum", "default": 1,
         "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
        {"name": "通信对象地址", "type": "bcd", "length": 6, "default": "000000000000"},
    ], "doc": "<b>福建增补 AFN=53H F4</b><br>下行：通信对象类型(1B)+通信对象地址(6B)"},
    (0x53, 5): {"name": "通信信道信息", "direction": "down", "fields": [
        {"name": "通信对象类型", "type": "enum", "default": 1,
         "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
        {"name": "通信对象地址", "type": "bcd", "length": 6, "default": "000000000000"},
    ], "doc": "<b>福建增补 AFN=53H F5</b><br>下行：通信对象类型(1B)+通信对象地址(6B)"},
    (0x53, 6): {"name": "本地通信模块串口当前通信参数", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=53H F6</b><br>无下行数据单元。"},
    (0x53, 10): {"name": "模块通信协议模式切换", "direction": "down", "fields": [
        {"name": "模块运行模式", "type": "enum", "default": 2,
         "enum_map": {1: "国网协议", 2: "福建增补协议", 0: "无效", 3: "无效"}},
    ], "doc": "<b>福建增补 AFN=53H F10</b><br>数据单元：D0~D1模式(1B) 1=国网,2=福建增补"},

    (0x55, 1): {"name": "设置主节点地址", "direction": "down", "fields": [
        {"name": "主节点地址", "type": "bcd", "length": 6, "default": "000000000000"},
    ], "doc": "<b>福建增补 AFN=55H F1</b><br>数据单元：主节点地址(6B)"},
    (0x55, 2): {"name": "允许、禁止从节点上报", "direction": "down", "fields": [
        {"name": "本次设置的对象数量", "type": "uint8", "default": 1},
        {"name": "对象列表", "type": "list",
         "count_field": "本次设置的对象数量",
         "item_fields": [
             {"name": "通信对象类型", "type": "enum", "default": 1,
              "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
             {"name": "任务对象通信地址", "type": "bcd", "length": 6, "default": "000000000000"},
             {"name": "事件上报状态标志", "type": "enum", "default": 1,
              "enum_map": {0: "禁止", 1: "允许"}},
         ]},
    ], "doc": "<b>福建增补 AFN=55H F2</b><br>数据单元：数量(1B)+n×[对象类型(1B)+地址(6B)+上报标志(1B)]"},
    (0x55, 3): {"name": "启动广播命令（不修正时标）", "direction": "down", "fields": [
        {"name": "通信对象类型", "type": "enum", "default": 1,
         "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
        {"name": "广播时长", "type": "uint8", "default": 1, "description": "单位分钟"},
        {"name": "广播报文长度", "type": "uint8", "default": 0},
        {"name": "广播请求内容", "type": "bytes", "default": ""},
    ], "doc": "<b>福建增补 AFN=55H F3</b><br>数据单元：对象类型(1B)+广播时长(1B)+报文长度(1B)+报文内容(NB)"},
    (0x55, 4): {"name": "启动广播命令（修正时标）", "direction": "down", "fields": [
        {"name": "通信对象类型", "type": "enum", "default": 1,
         "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
        {"name": "广播时长", "type": "uint8", "default": 1, "description": "单位分钟"},
    ], "doc": "<b>福建增补 AFN=55H F4</b><br>数据单元：对象类型(1B)+广播时长(1B)"},
    (0x55, 6): {"name": "启动从节点主动注册", "direction": "down", "fields": [
        {"name": "允许执行时间", "type": "uint16", "endian": "little", "default": 10,
         "description": "单位分钟"},
    ], "doc": "<b>福建增补 AFN=55H F6</b><br>数据单元：允许执行时间(2B)"},
    (0x55, 7): {"name": "结束当前任务", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=55H F7</b><br>无数据单元。"},
    (0x55, 8): {"name": "启动预告任务执行", "direction": "down", "fields": [],
                "doc": "<b>福建增补 AFN=55H F8</b><br>无数据单元。"},
    (0x55, 9): {"name": "预告抄读对象", "direction": "down", "fields": [
        {"name": "本次预告对象数量", "type": "uint16", "endian": "little", "default": 1},
        {"name": "通信延时修正标志", "type": "enum", "default": 0,
         "enum_map": {0: "不需要修正", 1: "需要修正"}},
        {"name": "预告对象列表", "type": "list",
         "count_field": "本次预告对象数量",
         "item_fields": [
             {"name": "预告对象序号", "type": "uint16", "endian": "little", "default": 1},
             {"name": "通信对象类型", "type": "enum", "default": 1,
              "enum_map": {0: "主节点模块", 1: "电能表通信模块", 2: "I型采集器通信模块", 3: "II型采集器通信模块"}},
             {"name": "任务对象通信地址", "type": "bcd", "length": 6, "default": "000000000000"},
         ]},
    ], "doc": "<b>福建增补 AFN=55H F9</b><br>数据单元：对象数量(2B)+延时修正标志(1B)+n×[序号(2B)+对象类型(1B)+地址(6B)]"},
    (0x55, 10): {"name": "模块通信协议模式切换", "direction": "down", "fields": [
        {"name": "模块运行模式", "type": "enum", "default": 2,
         "enum_map": {1: "国网协议", 2: "福建增补协议", 0: "无效", 3: "无效"}},
    ], "doc": "<b>福建增补 AFN=55H F10</b><br>数据单元：D0~D1模式(1B)"},
    (0x55, 11): {"name": "串口通信速率协商", "direction": "down", "fields": [
        {"name": "协商通信速率", "type": "enum", "default": 6,
         "enum_map": {0: "300bps", 1: "600bps", 2: "1200bps", 3: "2400bps", 4: "4800bps", 5: "7200bps", 6: "9600bps", 7: "19200bps", 8: "38400bps", 9: "57600bps", 10: "115200bps"}},
    ], "doc": "<b>福建增补 AFN=55H F11</b><br>数据单元：速率枚举(1B)"},
    (0x55, 12): {"name": "自动恢复默认通信速率时长", "direction": "down", "fields": [
        {"name": "自动恢复时长", "type": "uint16", "endian": "little", "default": 120,
         "description": "单位分钟，16~1400"},
    ], "doc": "<b>福建增补 AFN=55H F12</b><br>数据单元：恢复时长(2B)"},
    (0x55, 13): {"name": "允许协商最高通信速率设置", "direction": "down", "fields": [
        {"name": "允许协商最高速率", "type": "enum", "default": 10,
         "enum_map": {0: "300bps", 1: "600bps", 2: "1200bps", 3: "2400bps", 4: "4800bps", 5: "7200bps", 6: "9600bps", 7: "19200bps", 8: "38400bps", 9: "57600bps", 10: "115200bps"}},
    ], "doc": "<b>福建增补 AFN=55H F13</b><br>数据单元：速率枚举(1B)"},
    (0x55, 18): {"name": "启动预告任务执行（2字节报文长度模式）", "direction": "down", "fields": [],
                 "doc": "<b>福建增补 AFN=55H F18</b><br>无数据单元。"},

    (0x56, 1): {"name": "主动注册的从节点信息", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=56H F1</b><br>上行主动上报，下行为确认。"},
    (0x56, 2): {"name": "从节点主动上报事件内容", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=56H F2</b><br>上行主动上报，下行为确认。"},
    (0x56, 3): {"name": "通信对象具体抄读内容请求", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=56H F3</b><br>上行主动上报。"},
    (0x56, 4): {"name": "预告的通信对象响应报文", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=56H F4</b><br>上行主动上报。"},
    (0x56, 5): {"name": "信道延时信息报文", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=56H F5</b><br>上行主动上报。"},
    (0x56, 6): {"name": "广播任务完成", "direction": "up", "fields": [],
                "doc": "<b>福建增补 AFN=56H F6</b><br>上行主动上报。"},
    (0x56, 13): {"name": "通信对象具体抄读内容请求（2B长度模式）", "direction": "up", "fields": [],
                 "doc": "<b>福建增补 AFN=56H F13</b><br>上行主动上报。"},
    (0x56, 14): {"name": "预告的通信对象响应报文（2B长度模式）", "direction": "up", "fields": [],
                 "doc": "<b>福建增补 AFN=56H F14</b><br>上行主动上报。"},
    (0x56, 15): {"name": "带任务信息的事件上报", "direction": "up", "fields": [],
                 "doc": "<b>福建增补 AFN=56H F15</b><br>上行主动上报。"},
}
