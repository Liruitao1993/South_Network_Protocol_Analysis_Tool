"""DL/T 698.45 帧生成器 - APDU 字段元数据 Schema

定义 698.45 常用的下行 APDU 命令（请求帧）的字段结构。
所有多字节整数默认采用小端序（698.45 协议规范）。
"""

from typing import Dict, Any, Tuple

# ==================== APDU 类型枚举 ====================

APDU_TYPE_LIST = [
    (0x01, "LINK-Request", "预连接请求"),
    (0x02, "CONNECT-Request", "建立应用连接请求"),
    (0x03, "RELEASE-Request", "断开应用连接请求"),
    (0x05, "GET-Request", "读取请求"),
    (0x06, "SET-Request", "设置请求"),
    (0x07, "ACTION-Request", "操作请求"),
    (0x09, "PROXY-Request", "代理请求"),
    (0x45, "COMPACT-GET-Request", "紧凑读取请求"),
    (0x46, "COMPACT-SET-Request", "紧凑设置请求"),
    (0x49, "COMPACT-PROXY-Request", "紧凑代理请求"),
    (0x10, "SECURITY-Request", "安全请求"),
]

# GET-Request Normal 子类型
GET_REQUEST_LIST = [
    ("get_normal", "读取一个对象属性 (Normal)"),
    ("get_normal_list", "读取若干个对象属性 (NormalList)"),
    ("get_record", "读取一个记录型对象属性 (Record)"),
    ("get_record_list", "读取若干个记录型对象属性 (RecordList)"),
    ("get_next", "读取后续记录型对象属性 (Next)"),
]

# SET-Request Normal 子类型
SET_REQUEST_LIST = [
    ("set_normal", "设置一个对象属性 (Normal)"),
    ("set_normal_list", "设置若干个对象属性 (NormalList)"),
]

# ACTION-Request Normal 子类型
ACTION_REQUEST_LIST = [
    ("action_normal", "操作一个对象方法 (Normal)"),
    ("action_normal_list", "操作若干个对象方法 (NormalList)"),
]

# ==================== APDU 字段 Schema ====================

# key = (apdu_type, sub_type) 例如 ("GET-Request", "get_normal")
DLT69845_FIELD_SCHEMA: Dict[Tuple[str, str], Dict[str, Any]] = {
    # ─────────── LINK-Request ───────────
    ("LINK-Request", "link_request"): {
        "name": "预连接请求 (LINK-Request)",
        "doc": (
            "<b>APDU类型</b>：LINK-Request (0x01)<br>"
            "<b>说明</b>：预连接请求，用于建立链路层连接<br><br>"
            "<b>时序</b>：客户机 → 服务器<br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=1 (链路管理)"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "请求类型", "type": "uint8", "length": 1, "default": 0, "desc": "0=登录, 1=心跳, 2=退出登录"},
            {"name": "心跳周期", "type": "uint16", "length": 2, "endian": "little", "default": 0, "desc": "心跳周期(秒)"},
        ],
    },

    # ─────────── CONNECT-Request ───────────
    ("CONNECT-Request", "connect_request"): {
        "name": "建立应用连接请求 (CONNECT-Request)",
        "doc": (
            "<b>APDU类型</b>：CONNECT-Request (0x02)<br>"
            "<b>说明</b>：建立应用层连接请求<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "期望安全参数", "type": "uint8", "length": 1, "default": 0, "desc": "0=明文, 1=密文, 2=密文+MAC"},
            {"name": "客户机APDU最大长度", "type": "uint16", "length": 2, "endian": "little", "default": 1024, "desc": "宣告自身APDU最大长度"},
            {"name": "期望帧最大窗口尺寸", "type": "uint8", "length": 1, "default": 1, "desc": "收发双方一次允许不确认的帧总数"},
            {"name": "期望帧最大帧长", "type": "uint16", "length": 2, "endian": "little", "default": 1024, "desc": "期望的帧最大帧长"},
            {"name": "期望超时时间", "type": "uint16", "length": 2, "endian": "little", "default": 60, "desc": "期望的应用连接超时时间(s)"},
        ],
    },

    # ─────────── RELEASE-Request ───────────
    ("RELEASE-Request", "release_request"): {
        "name": "断开应用连接请求 (RELEASE-Request)",
        "doc": (
            "<b>APDU类型</b>：RELEASE-Request (0x03)<br>"
            "<b>说明</b>：断开应用层连接请求<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "断开原因", "type": "uint8", "length": 1, "default": 0, "desc": "0=正常断开, 1=异常断开"},
        ],
    },

    # ─────────── GET-Request Normal ───────────
    ("GET-Request", "get_normal"): {
        "name": "读取一个对象属性 (GET-Request Normal)",
        "doc": (
            "<b>APDU类型</b>：GET-Request Normal (0x05 01)<br>"
            "<b>说明</b>：读取指定对象的一个属性值<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)<br><br>"
            "<b>OI (对象标识)</b>：2字节，标识要读取的对象<br>"
            "<b>属性标识</b>：1字节，指定对象属性<br>"
            "<b>OAD</b> = OI[2B] + 属性标识[1B] = 含标识及属性的对象属性描述符"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "OI", "type": "oi", "length": 2, "default": 0x0000, "desc": "对象标识 (2字节小端序)"},
            {"name": "属性标识", "type": "uint8", "length": 1, "default": 2, "desc": "对象属性标识"},
        ],
    },

    # ─────────── GET-Request NormalList ───────────
    ("GET-Request", "get_normal_list"): {
        "name": "读取若干个对象属性 (GET-Request NormalList)",
        "doc": (
            "<b>APDU类型</b>：GET-Request NormalList<br>"
            "<b>说明</b>：一次读取多个对象的属性<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)<br><br>"
            "格式：05 02 [PIID] [Count] [[OI][属性标识]]..."
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "OAD项数", "type": "uint8", "length": 1, "default": 1, "desc": "OAD数量（自动根据下方列表计算）"},
            {"name": "OAD列表", "type": "oad_list", "length": 1, "default": "00000000", "desc": "多个OAD，每个4字节(OI2B+属性标识1B+索引1B)，十六进制空格分隔"},
        ],
    },

    # ─────────── SET-Request Normal ───────────
    ("SET-Request", "set_normal"): {
        "name": "设置一个对象属性 (SET-Request Normal)",
        "doc": (
            "<b>APDU类型</b>：SET-Request Normal (0x06 01)<br>"
            "<b>说明</b>：设置指定对象的一个属性值<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)<br><br>"
            "格式：06 01 [PIID] [OAD] [数据内容]"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "OI", "type": "oi", "length": 2, "default": 0x0000, "desc": "对象标识 (2字节小端序)"},
            {"name": "属性标识", "type": "uint8", "length": 1, "default": 2, "desc": "对象属性标识"},
            {"name": "数据内容", "type": "bytes", "length": 1, "default": "", "desc": "要设置的数据值 (十六进制)"},
        ],
    },

    # ─────────── ACTION-Request Normal ───────────
    ("ACTION-Request", "action_normal"): {
        "name": "操作一个对象方法 (ACTION-Request Normal)",
        "doc": (
            "<b>APDU类型</b>：ACTION-Request Normal (0x07 01)<br>"
            "<b>说明</b>：操作指定对象的一个方法<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)<br><br>"
            "格式：07 01 [PIID] [OMD] [参数(可选)]"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "OI", "type": "oi", "length": 2, "default": 0x0000, "desc": "对象标识 (2字节小端序)"},
            {"name": "方法标识", "type": "uint8", "length": 1, "default": 1, "desc": "对象方法标识"},
            {"name": "参数", "type": "bytes", "length": 1, "default": "", "desc": "方法参数 (十六进制, 可选)"},
        ],
    },

    # ─────────── PROXY-Request ───────────
    ("PROXY-Request", "proxy_request"): {
        "name": "代理请求 (PROXY-Request)",
        "doc": (
            "<b>APDU类型</b>：PROXY-Request (0x09)<br>"
            "<b>说明</b>：通过当前服务器代理访问其他服务器<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "代理服务器地址(SA)", "type": "bytes", "length": 1, "default": "0100000000", "desc": "目标服务器地址 (含地址特征字节)"},
            {"name": "代理客户机地址(CA)", "type": "uint8", "length": 1, "default": 0, "desc": "代理客户机地址"},
            {"name": "代理APDU", "type": "bytes", "length": 1, "default": "0501", "desc": "代理转发的APDU (十六进制)"},
        ],
    },

    # ─────────── SECURITY-Request ───────────
    ("SECURITY-Request", "security_request"): {
        "name": "安全请求 (SECURITY-Request)",
        "doc": (
            "<b>APDU类型</b>：SECURITY-Request (0x10)<br>"
            "<b>说明</b>：安全传输请求，包含安全认证数据<br><br>"
            "<b>控制域</b>：DIR=0, PRM=1, 功能码=3 (用户数据)"
        ),
        "fields": [
            {"name": "PIID", "type": "uint8", "length": 1, "default": 1, "desc": "服务序号"},
            {"name": "安全参数", "type": "bytes", "length": 1, "default": "", "desc": "安全认证参数 (十六进制)"},
        ],
    },
}


# ==================== OI 常用对象列表（用于下拉选择） ====================

OI_PRESET_LIST = [
    # 电能类
    (0x0000, "组合有功电能"),
    (0x0010, "正向有功电能"),
    (0x0020, "反向有功电能"),
    (0x0030, "组合无功1电能"),
    (0x0040, "组合无功2电能"),
    (0x0050, "第一象限无功电能"),
    (0x0060, "第二象限无功电能"),
    (0x0070, "第三象限无功电能"),
    (0x0080, "第四象限无功电能"),
    # 变量类
    (0x0201, "电压"),
    (0x0202, "A相电压"),
    (0x0203, "B相电压"),
    (0x0204, "C相电压"),
    (0x0206, "电流"),
    (0x0207, "A相电流"),
    (0x0208, "B相电流"),
    (0x0209, "C相电流"),
    (0x020B, "有功功率"),
    (0x020C, "A相有功功率"),
    (0x020D, "B相有功功率"),
    (0x020E, "C相有功功率"),
    (0x020F, "无功功率"),
    (0x0210, "A相无功功率"),
    (0x0211, "B相无功功率"),
    (0x0212, "C相无功功率"),
    (0x0213, "视在功率"),
    (0x0214, "A相视在功率"),
    (0x0215, "B相视在功率"),
    (0x0216, "C相视在功率"),
    (0x0217, "功率因数"),
    (0x0218, "A相功率因数"),
    (0x0219, "B相功率因数"),
    (0x021A, "C相功率因数"),
    (0x0280, "频率"),
    # 参数类 (接口类1)
    (0x0400, "电表通信地址"),
    (0x0401, "终端通信地址"),
    (0x0402, "CT变比"),
    (0x0403, "PT变比"),
    (0x0405, "电表常数"),
    (0x0500, "日期时间"),
    (0x0501, "通信速率"),
    (0x0502, "冻结间隔"),
    # 最大需量类
    (0x0600, "正向有功最大需量"),
    (0x0601, "反向有功最大需量"),
    # 事件类
    (0x0100, "电表运行状态字"),
    (0x0101, "电网异常事件"),
    (0x0102, "电表异常事件"),
    (0x0103, "终端异常事件"),
]
