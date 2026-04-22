"""南网协议帧生成器 - DI字段元数据Schema

定义所有集中器->模块下行命令的用户数据区字段结构。
所有多字节整数默认采用大端序，除非显式指定 endian="little"。
地址类字段 reverse=True 表示用户以正常顺序输入，组帧时自动反转。
"""

from typing import Dict, Any, Tuple

PROVINCE_ENUM_MAP = {1: '北京', 2: '天津', 3: '河北', 4: '山西', 5: '内蒙古', 6: '辽宁', 7: '吉林', 8: '黑龙江', 9: '上海', 10: '江苏', 11: '浙江', 12: '安徽', 13: '福建', 14: '江西', 15: '山东', 16: '河南', 17: '湖北', 18: '湖南', 19: '广东', 20: '广西', 21: '海南', 22: '重庆', 23: '四川', 24: '贵州', 25: '云南', 26: '西藏', 27: '陕西', 28: '甘肃', 29: '青海', 30: '宁夏', 31: '新疆', 32: '台湾', 33: '香港', 34: '澳门'}

WHITELIST_SWITCH_MAP = {0: '关闭', 1: '打开'}

WHITELIST_RANGE_MAP = {0: '表档案', 1: '厂家自定义', 2: '表档案和厂家自定义的合集'}

EVENT_REPORT_MAP = {0: '禁止上报', 1: '允许上报'}

# ==================== DI 字段 Schema ====================

DI_FIELD_SCHEMA: Dict[Tuple[int, int, int, int], Dict[str, Any]] = {
    # 查询未完成任务数 (E8 00 02 03)
    (0xE8, 0x00, 0x02, 0x03): {
        "name": '查询未完成任务数',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 02 03<br>\n<b>命令名称</b>：查询未完成任务数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。用于查询模块中尚未执行完毕的任务数。\n',
        "fields": []
    },

    # 查询剩余可分配任务数 (E8 00 02 06)
    (0xE8, 0x00, 0x02, 0x06): {
        "name": '查询剩余可分配任务数',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 02 06<br>\n<b>命令名称</b>：查询剩余可分配任务数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 20 查询剩余可分配任务数数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>剩余可分配任务数</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\n模块上电进行模块识别时，集中器可读取模块剩余可分配任务数作为参考，进行任务管理初始化，在分配任务时也可作为参考。\n\n一个典型任务的大小为 24 字节，模块结合自身可用存储空间的大小，计算剩余可分配的任务数。模块至少能缓存 100 个典型任务。\n\n剩余可分配任务数仅为集中器管理任务提供参考，当集中器添加任务的长度超过模块剩余存储空间时，模块回复否认。\n',
        "fields": []
    },

    # 查询厂商代码和版本信息 (E8 00 03 01)
    (0xE8, 0x00, 0x03, 0x01): {
        "name": '查询厂商代码和版本信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 01<br>\n<b>命令名称</b>：查询厂商代码和版本信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 40 厂商代码和版本信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>厂商代码</td><td style=\'text-align: center; word-wrap: break-word;\'>ASCII</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>芯片代码</td><td style=\'text-align: center; word-wrap: break-word;\'>ASCII</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>版本时间</td><td style=\'text-align: center; word-wrap: break-word;\'>YYMMDD</td><td style=\'text-align: center; word-wrap: break-word;\'>3</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>版本</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n',
        "fields": []
    },

    # 查询本地通信模块运行模式信息 (E8 00 03 02)
    (0xE8, 0x00, 0x03, 0x02): {
        "name": '查询本地通信模块运行模式信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 02<br>\n<b>命令名称</b>：查询本地通信模块运行模式信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 41 本地通信模块运行模式信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td colspan="7">数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td colspan="7">本地通信模式字</td><td style=\'text-align: center; word-wrap: break-word;\'>BS</td><td rowspan="3">1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>D7</td><td style=\'text-align: center; word-wrap: break-word;\'>D6</td><td style=\'text-align: center; word-wrap: break-word;\'>D5</td><td style=\'text-align: center; word-wrap: break-word;\'>D4</td><td style=\'text-align: center; word-wrap: break-word;\'>D3</td><td style=\'text-align: center; word-wrap: break-word;\'>D2</td><td style=\'text-align: center; word-wrap: break-word;\'>D1</td><td style=\'text-align: center; word-wrap: break-word;\'>D0</td></tr><tr><td colspan="4">保留</td><td colspan="4">通信方式</td></tr></table>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>最大支持的协议报文长度</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件传输支持的最大单包长度</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>升级操作等待时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>主节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>支持的最大从节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前从节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>支持单次读写从节点信息的最大数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>通信模块接口协议发布日期</td><td style=\'text-align: center; word-wrap: break-word;\'>YYMMDD</td><td style=\'text-align: center; word-wrap: break-word;\'>3</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>厂商代码和版本信息</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>9</td></tr></table>\n\na）通信方式：1表示“窄带电力线载波通信”，2表示“宽带电力线载波通信”，3表示“微功率无线通信”，4表示“窄带+微功率无线”，5表示“宽带+微功率无线”，其他取值保留。\n\nb) 最大支持的协议报文长度：可以正确接收的协议报文最大长度。\n\nc）文件传输支持的最大单个数据包长度：在AFN07H“传输文件”中支持的最大“文件段长度”大小。最大长度的值应在64、128、256、512、1024中选择。\n\nd) 升级操作等待时间：终端发送完最后一个升级数据包且文件已经生效之后，需要等待模块完成升级的时间长度。单位为分钟。\n\ne) 主节点地址：本地通信模块的主节点地址。\n\nf) 支持的最大从节点数量：主节点模块支持的最大从节点下装数量。\n\ng) 当前从节点数量：主节点模块当前下装的从节点数量。\n\nh) 单次读写从节点信息的最大数量：添加/删除/查询从节点等读写从节点信息时，一次支持最大的从节点数量。\n\ni）通信模块接口协议发布日期：BCD编码，YYMMDD日期格式。本标准发布日期为XXXXXX（具体待定）。本次协议新增设备在线、网络拓扑、节点运行时长、从节点入网被拒信息、节点自检结果、应用层报文信息、宽带载波频段、多网络信息、并发数、台区组网成功率、节点信道信息别等内容。\n\nj）通信模块厂商代码及版本信息：与 AFN=03H-DI=E8 00 03 01 查询“厂商代码及版本信息”返回内容相同。\n',
        "fields": []
    },

    # 查询主节点地址 (E8 00 03 03)
    (0xE8, 0x00, 0x03, 0x03): {
        "name": '查询主节点地址',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 03<br>\n<b>命令名称</b>：查询主节点地址<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 42 主节点地址数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>主节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": []
    },

    # 查询从节点数量 (E8 00 03 05)
    (0xE8, 0x00, 0x03, 0x05): {
        "name": '查询从节点数量',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 05<br>\n<b>命令名称</b>：查询从节点数量<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 44 查询从节点数量数据单元格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点总数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n',
        "fields": []
    },

    # 查询从节点主动注册进度 (E8 00 03 07)
    (0xE8, 0x00, 0x03, 0x07): {
        "name": '查询从节点主动注册进度',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 07<br>\n<b>命令名称</b>：查询从节点主动注册进度<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n<div style="text-align: center;"><div style="text-align: center;">表 46 查询从节点主动注册数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点主动注册工作标识</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n从节点主动注册工作标示：0 为从节点停止主动注册，1 为从节点正在主动注册。\n',
        "fields": []
    },

    # 查询映射表从节点数量 (E8 00 03 09)
    (0xE8, 0x00, 0x03, 0x09): {
        "name": '查询映射表从节点数量',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 09<br>\n<b>命令名称</b>：查询映射表从节点数量<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。查询主模块记录的从节点数量。仅限于查询通过“添加从节点通信地址映射表”命令下发的从节点数量。\n',
        "fields": []
    },

    # 查询任务建议超时时间 (E8 00 03 0B)
    (0xE8, 0x00, 0x03, 0x0B): {
        "name": '查询任务建议超时时间',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 0B<br>\n<b>命令名称</b>：查询任务建议超时时间<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表6-39 任务建议超时时间数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>优先级0的任务建议超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>优先级1的任务建议超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>优先级2的任务建议超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>优先级3的任务建议超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\na） 超时时间：单位 s，最长为 65535s，约 18 小时。\n\nb）建议集中器每下发20个任务，至少查询一次模块的建议超时时间。两次查询之间的时间间隔不得超过20分钟。集中器根据模块的建议超时时间动态调整抄表策略，提高抄表效率。\n\nc）模块需根据当前通信网络状态、未执行任务数量等信息，向集中器提供后续任务的建议超时时间。由于集中器每下发20个任务均需查询一次建议超时时间，因此模块可在执行20个任务的假设下，计算建议超时时间。\n',
        "fields": []
    },

    # 查询最大网络规模 (E8 00 03 6A)
    (0xE8, 0x00, 0x03, 0x6A): {
        "name": '查询最大网络规模',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 6A<br>\n<b>命令名称</b>：查询最大网络规模<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 68 返回最大网络规模数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>最大网络规模</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n',
        "fields": []
    },

    # 查询最大网络级数 (E8 00 03 6B)
    (0xE8, 0x00, 0x03, 0x6B): {
        "name": '查询最大网络级数',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 6B<br>\n<b>命令名称</b>：查询最大网络级数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 69 返回最大网络级数数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>最大网络级数</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": []
    },

    # 查询允许/禁止拒绝从节点信息上报 (E8 00 03 6C)
    (0xE8, 0x00, 0x03, 0x6C): {
        "name": '查询允许/禁止拒绝从节点信息上报',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 00 03 6C<br>\n<b>命令名称</b>：查询允许/禁止拒绝从节点信息上报<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>拒绝从节点信息上报使能</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n\na） 拒绝从节点信息上报使能：0：禁止；1：允许；\n",
        "fields": []
    },

    # 查询无线参数 (E8 00 03 6D)
    (0xE8, 0x00, 0x03, 0x6D): {
        "name": '查询无线参数',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 6D<br>\n<b>命令名称</b>：查询无线参数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 70 返回并发数数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>OPTION</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>CHANNEL</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": []
    },

    # 查询主节点运行信息 (E8 00 03 6F)
    (0xE8, 0x00, 0x03, 0x6F): {
        "name": '查询主节点运行信息',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 00 03 6F<br>\n<b>命令名称</b>：查询主节点运行信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>字节数</td><td style='text-align: center; word-wrap: break-word;'>说明</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>累计运行时间</td><td style='text-align: center; word-wrap: break-word;'>4</td><td style='text-align: center; word-wrap: break-word;'>节点从上电运行到现在的时间，单位：秒。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点模块ID</td><td style='text-align: center; word-wrap: break-word;'>11</td><td style='text-align: center; word-wrap: break-word;'>默认全0xff</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>发现站点数最大的站点</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>见心跳消息同字段定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大的发现站点数</td><td style='text-align: center; word-wrap: break-word;'>2</td><td style='text-align: center; word-wrap: break-word;'>见心跳消息同字段定义</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>系统启动原因</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>0：正常启动；1：断电重启；2：看门狗复位；3：程序异常复位。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>本地邻居网络个数</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>主站点可以监听到的邻居网络个数。</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1#邻居网络标识号</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>邻居网络标识号SNID</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1#邻居网络CCO地址</td><td style='text-align: center; word-wrap: break-word;'>6</td><td style='text-align: center; word-wrap: break-word;'>邻居网络主站点地址</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>1#邻居网络HPLC通道通信质量</td><td style='text-align: center; word-wrap: break-word;'>1</td><td style='text-align: center; word-wrap: break-word;'>HPLC通道RSSI</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>............</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>\n\na）累计运行时间：节点从上电运行到现在的时间，单位：秒。\n\nb) 节点模块 ID: 默认全 0xff。\n\nc） 发现站点数最大的站点：见心跳消息同字段定义。\n\nd) 最大的发现站点数：见心跳消息同字段定义。\n\ne）系统启动原因：0：正常启动；1：断电重启；2：看门狗复位；3：程序异常复位。\n\nf) 本地邻居网络个数：主站点可以监听到的邻居网络个数。\n\ng) 邻居网络标识号：邻居网络标识号 SNID。\n\nh) 邻居网络 CCO 地址：邻居网络主站点地址。\n\ni) 邻居网络 HPLC 通道通信质量：HPLC 通道 RSSI。\n",
        "fields": []
    },

    # 查询踢出后不允许入网时间 (E8 00 03 72)
    (0xE8, 0x00, 0x03, 0x72): {
        "name": '查询踢出后不允许入网时间',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 00 03 72<br>\n<b>命令名称</b>：查询踢出后不允许入网时间<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>踢出不允许入网时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>\n\na) 单位：秒；\n",
        "fields": []
    },

    # 查询宽带载波频段 (E8 00 03 90)
    (0xE8, 0x00, 0x03, 0x90): {
        "name": '查询宽带载波频段',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 90<br>\n<b>命令名称</b>：查询宽带载波频段<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 72 返回宽带载波频段数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>宽带载波频段</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n频段：0:1.953～11.96MHz；1：2.441～5.615 MHz；2：0.781～2.930 MHz；3～255表示保留\n',
        "fields": []
    },

    # 查询多网络信息 (E8 00 03 91)
    (0xE8, 0x00, 0x03, 0x91): {
        "name": '查询多网络信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 91<br>\n<b>命令名称</b>：查询多网络信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 73 返回多网络信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>多网络节点总数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>本节点网络标识号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>本节点主节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>邻居网络 1 标识号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>邻居网络 1 主节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>网间 SNR</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>......</td><td style=\'text-align: center; word-wrap: break-word;\'>......</td><td style=\'text-align: center; word-wrap: break-word;\'>......</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>邻居节点 n 网络标识号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>邻居网络 n 主节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>网间 SNR</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na) 网间 SNR：节点与周边其他网络主节点 m 之间的信噪比，单位为 dB，取值范围（符号数）：-20~80；\n',
        "fields": []
    },

    # 查询白名单生效信息 (E8 00 03 93)
    (0xE8, 0x00, 0x03, 0x93): {
        "name": '查询白名单生效信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 93<br>\n<b>命令名称</b>：查询白名单生效信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n上行数据内容如下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 74 返回查询白名单生效信息</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>白名单开关</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>白名单生效范围</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na） 白名单开关：0：关闭；1：打开；\n\nb) 白名单生效范围：0：表档案；1：厂家自定义；2：表档案和厂家自定义的合集；3～255：保留。\n\n数据标识内容格式见下表。\n',
        "fields": [{'name': '白名单开关', 'type': 'enum', 'length': 1, 'required': True, 'enum_map': {0: '关闭', 1: '打开'}, 'default': 1, 'description': '0=关闭，1=打开'}, {'name': '白名单生效范围', 'type': 'enum', 'length': 1, 'required': True, 'enum_map': {0: '表档案', 1: '厂家自定义', 2: '表档案和厂家自定义的合集'}, 'default': 0, 'description': '0=表档案，1=厂家自定义，2=合集'}]
    },

    # 查询并发数 (E8 00 03 95)
    (0xE8, 0x00, 0x03, 0x95): {
        "name": '查询并发数',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 95<br>\n<b>命令名称</b>：查询并发数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n<div style="text-align: center;"><div style="text-align: center;">表 75 返回并发数数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>并发数</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": []
    },

    # 查询台区组网成功率 (E8 00 03 97)
    (0xE8, 0x00, 0x03, 0x97): {
        "name": '查询台区组网成功率',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 03 97<br>\n<b>命令名称</b>：查询台区组网成功率<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 77 返回台区组网成功率数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>台区组网成功率</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\n注：模块上报扩大100倍，如组网成功率为100%，上报信息为10000。\n',
        "fields": []
    },

    # 查询文件信息 (E8 00 07 03)
    (0xE8, 0x00, 0x07, 0x03): {
        "name": '查询文件信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 07 03<br>\n<b>命令名称</b>：查询文件信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 102 查询文件信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件性质</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>目的地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件总段数 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件大小</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>4</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件总校验</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>已成功接收文件段数 m</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\na) 文件性质:\n\n1) 00H: 清除下装文件;\n\n2）01H：本地通信模块文件；\n\n3）02H：从节点模块文件；\n\nb) 文件 ID：用来区分不同的文件。\n\nc) 目的地址：文件传输的目的地址，99 99 99 99 99 99 为广播地址。\n\nd) 文件总段数 n：文件传输内容的总帧数。\n\ne) 文件大小：文件的总长度，单位字节。\n\nf）文件总校验：文件所有内容的 CRC16 校验和。\n\ng）成功接收文件段数：文件接收方已经成功接收到的文件段数，范围为1~n。n为文件总段数。如果为0表示尚未开始传输，为n表示传输已完成，为m表示段号0~m-1的帧已传输完成，可以从段号为m的帧开始续传。\n',
        "fields": []
    },

    # 查询文件处理进度 (E8 00 07 04)
    (0xE8, 0x00, 0x07, 0x04): {
        "name": '查询文件处理进度',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 07 04<br>\n<b>命令名称</b>：查询文件处理进度<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 103 查询文件处理进度数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件处理进度</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>处理未完成的文件 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>失败的节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\na）文件处理进度：0 全部成功，可以接收新文件；1 正在处理，不能接收新文件；2 未全部成功，存在失败节点。\n\nb) 处理未完成的文件 ID：当文件处理进度为 1—正在处理或 2—未全部成功时有效，表示当前处理未完成的文件 ID。\n\nc） 失败的节点数量：当文件处理进度为 2-处理未全部成功时有效，表示失败的节点数量。\n',
        "fields": []
    },

    # 查询采集任务号 (E8 00 08 03)
    (0xE8, 0x00, 0x08, 0x03): {
        "name": '查询采集任务号',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 08 03<br>\n<b>命令名称</b>：查询采集任务号<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n暂无该命令的详细文档定义。\n',
        "fields": []
    },

    # 查询宽带应用省份 (E8 00 F0 DF)
    (0xE8, 0x00, 0xF0, 0xDF): {
        "name": '查询宽带应用省份',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 00 F0 DF<br>\n<b>命令名称</b>：查询宽带应用省份<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n暂无该命令的详细文档定义。\n',
        "fields": [{'name': '宽带应用省份', 'type': 'enum', 'length': 1, 'required': True, 'enum_map': {1: '北京', 2: '天津', 3: '河北', 4: '山西', 5: '内蒙古', 6: '辽宁', 7: '吉林', 8: '黑龙江', 9: '上海', 10: '江苏', 11: '浙江', 12: '安徽', 13: '福建', 14: '江西', 15: '山东', 16: '河南', 17: '湖北', 18: '湖南', 19: '广东', 20: '广西', 21: '海南', 22: '重庆', 23: '四川', 24: '贵州', 25: '云南', 26: '西藏', 27: '陕西', 28: '甘肃', 29: '青海', 30: '宁夏', 31: '新疆', 32: '台湾', 33: '香港', 34: '澳门'}, 'default': 19, 'description': '省份代码（如0x13=广东）'}]
    },

    # 确认 (E8 01 00 01)
    (0xE8, 0x01, 0x00, 0x01): {
        "name": '确认',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 01 00 01<br>\n<b>命令名称</b>：确认<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n等待时间：该确认帧对应的命令的执行时间，单位为秒。\n\n<div style="text-align: center;"><div style="text-align: center;">表 7 确认数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>等待时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n',
        "fields": [{'name': '等待时间', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '等待确认时间（秒）'}]
    },

    # 否认 (E8 01 00 02)
    (0xE8, 0x01, 0x00, 0x02): {
        "name": '否认',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 01 00 02<br>\n<b>命令名称</b>：否认<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 8 否认数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>错误状态字</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n错误状态字：0 为通信超时，1 为无效数据标识内容，2 为长度错误，3 为校验错误，4 为数据标识编码不存在，5 为格式错误，6 为表号重复，7 为表号不存在，8 为电表应用层无应答，9 为主节点忙，10 主节点不支持此命令，11 为从节点不应答，12 为从节点不在网内，13 为添加任务时剩余可分配任务数不足，14 为上报任务数据时任务不存在，15 为任务 ID 重复，16 为查询任务时模块没有此任务，17 为任务 ID 不存在，FFH 其他。\n',
        "fields": [{'name': '错误状态字', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '错误状态代码'}]
    },

    # 复位硬件 (E8 02 01 01)
    (0xE8, 0x02, 0x01, 0x01): {
        "name": '复位硬件',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 01 01<br>\n<b>命令名称</b>：复位硬件<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n',
        "fields": []
    },

    # 初始化档案 (E8 02 01 02)
    (0xE8, 0x02, 0x01, 0x02): {
        "name": '初始化档案',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 01 02<br>\n<b>命令名称</b>：初始化档案<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n\n清除模块保存的档案信息。\n\n清除模块保存的从节点通信地址映射表。\n',
        "fields": []
    },

    # 初始化任务 (E8 02 01 03)
    (0xE8, 0x02, 0x01, 0x03): {
        "name": '初始化任务',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 01 03<br>\n<b>命令名称</b>：初始化任务<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n\n清除模块保存的任务信息。\n\n#### 上行报文\n\n初始化模块的上行报文为确认 / 否认报文，详见 “确认/否认” 报文格式。模块正确接收到初始化模块报文后立即回复确认帧，确认帧中的等待时间为模块完成初始化所需时间。\n\n模块执行完初始化模块命令后，处于暂停任务状态。\n',
        "fields": []
    },

    # 添加任务 (E8 02 02 01)
    (0xE8, 0x02, 0x02, 0x01): {
        "name": '添加任务',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 02 01<br>\n<b>命令名称</b>：添加任务<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 11 添加任务数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td colspan="8">数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td colspan="8">任务 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">任务模式字</td><td rowspan="2"></td><td rowspan="2"></td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>D7</td><td style=\'text-align: center; word-wrap: break-word;\'>D6</td><td style=\'text-align: center; word-wrap: break-word;\'>D5</td><td style=\'text-align: center; word-wrap: break-word;\'>D4</td><td style=\'text-align: center; word-wrap: break-word;\'>D3</td><td style=\'text-align: center; word-wrap: break-word;\'>D2</td><td style=\'text-align: center; word-wrap: break-word;\'>D1</td><td style=\'text-align: center; word-wrap: break-word;\'>D0</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>任务响应标识</td><td style=\'text-align: center; word-wrap: break-word;\'>转发标识</td><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td colspan="4">任务优先级</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td colspan="8">超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">报文长度</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">报文内容</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>L</td></tr></table>\n\na）任务 ID：区分不同任务的任务标识。本标准的任务 ID 取值范围为 0x0000-0xEFFF，其他取值保留。任务 ID 号必须在取值范围内循环使用，同一个任务 ID 号不能连续用在不同的任务中。\n\nb) 任务优先级：0~3，0 表示最高优先级，3 表示最低优先级。由集中器指定任务的优先级，模块保证高优先级的任务得到优先执行。\n\nc) 任务响应标识：该任务是否需要返回数据，0－不需要数据返回，1－需要数据返回。由集中器指定，广播校时等任务为 0，抄表任务为 1。若任务响应标识为 0，则模块只向集中器上报任务状态，不上报任务数据。\n\nd) 转发标识：默认为 0，若该任务需要下达给通信模块，将该位置为 1。\n\ne）超时时间：集中器指定任务执行的超时时间，单位为秒。超时时间从模块正确接收完集中器下发任务时开始计时，超时时间结束，集中器删除自己保存的任务，再按需决定是否重新下发；模块在超时时间结束时，若未完成任务，应上报任务状态不成功。\n\nf) 报文长度：原始报文数据总长度。\n\ng）报文内容：当转发标识为1时，报文第一位为“业务代码”，如下表所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 12 报文内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td colspan="2">数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td rowspan="2">报文内容</td><td style=\'text-align: center; word-wrap: break-word;\'>业务代码</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>报文有效内容</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>L-1</td></tr></table>\n\nh）业务代码：00H-透传报文；01H-精准对时；02-DLMS报文；其他一保留。\n\n当业务代码为01H时，报文内容为校时报文，具体格式见A.7；\n',
        "fields": [{'name': '任务ID', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '任务标识号'}, {'name': '任务模式字', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': 'D7=响应标识,D6=转发标识,D2~0=优先级'}, {'name': '超时时间', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 30, 'description': '任务超时时间（秒）'}, {'name': '报文长度', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '报文内容长度（字节）'}, {'name': '报文内容', 'type': 'bytes', 'required': False, 'default': '', 'description': '报文内容（hex字符串）'}]
    },

    # 删除任务 (E8 02 02 02)
    (0xE8, 0x02, 0x02, 0x02): {
        "name": '删除任务',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 02 02<br>\n<b>命令名称</b>：删除任务<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 13 删除任务数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>任务 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\n任务 ID：区分不同任务的任务标识。本标准的任务 ID 取值范围为 0x0000-0xEFFF，其他取值保留。\n',
        "fields": [{'name': '任务ID', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '要删除的任务标识号'}]
    },

    # 添加多播任务 (E8 02 02 07)
    (0xE8, 0x02, 0x02, 0x07): {
        "name": '添加多播任务',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 02 07<br>\n<b>命令名称</b>：添加多播任务<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 16 添加多播任务数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td colspan="8">数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td colspan="8">任务 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">任务模式字</td><td rowspan="2">BS</td><td rowspan="2">1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>D7</td><td style=\'text-align: center; word-wrap: break-word;\'>D6</td><td style=\'text-align: center; word-wrap: break-word;\'>D5</td><td style=\'text-align: center; word-wrap: break-word;\'>D4</td><td style=\'text-align: center; word-wrap: break-word;\'>D3</td><td style=\'text-align: center; word-wrap: break-word;\'>D2</td><td style=\'text-align: center; word-wrap: break-word;\'>D1</td><td style=\'text-align: center; word-wrap: break-word;\'>DO</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>任务响应标识</td><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td colspan="4">任务优先级</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'></td></tr><tr><td colspan="8">从节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">从节点地址 1</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td colspan="8">……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td></tr><tr><td colspan="8">从节点地址 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td colspan="8">超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">报文长度 L</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td colspan="8">报文内容</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>L</td></tr></table>\n\na）任务ID：区分不同任务的任务标识。\n\nb) 任务优先级：0~3,0 表示最高优先级，3 表示最低优先级。由集中器来指定任务的优先级，模块保证高优先级的任务得到优先执行。\n\nc）任务响应标识：该任务是否需要返回数据，0－不需要数据返回，1－数据返回。由集中器指定，广播校时等任务为0，抄表任务为1。若任务响应标识为0，则模块只向集中器上报任务状态，不上报任务数据。\n\nd) 超时时间：集中器指定任务执行的超时时间，单位为秒。超时时间从模块正确接收完集中器下发任务时开始计时，超时时间结束，集中器删除自己保存的任务，再按需决定是否重新下发；模块在超时时间结束时，若未完成任务，应上报任务状态不成功。\n\ne) 从节点数量：多播抄表的数量。数量 0xFFFF 表示向所有从模块传输任务报文。\n\nf) 从节点地址：多播抄表的地址。从节点数量为 n 时，表示多播同时抄读 n 个地址的某个数据项。若节点数量为 0xFFFF，则无从节点地址域。\n\ng）报文长度：原始报文数据总长度。\n\nh）报文内容：原始报文数据。\n\ni）多播任务需要数据返回，则按照单播任务上报任务数据的格式上报集中器。\n',
        "fields": [{'name': '任务ID', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '任务标识号'}, {'name': '任务模式字', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': 'D7=响应标识,D6=转发标识,D2~0=优先级'}, {'name': '从节点数量', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '0xFFFF=全部从节点'}, {'name': '从节点地址列表', 'type': 'list', 'count_field': '从节点数量', 'required': False, 'item_fields': [{'name': '从节点地址', 'type': 'bytes', 'length': 6, 'reverse': True, 'description': '6字节地址'}], 'description': '从节点地址列表（数量由上一字段决定）'}, {'name': '超时时间', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 30, 'description': '任务超时时间（秒）'}, {'name': '报文长度', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '报文内容长度'}, {'name': '报文内容', 'type': 'bytes', 'required': False, 'default': '', 'description': '报文内容（hex字符串）'}]
    },

    # 启动任务 (E8 02 02 08)
    (0xE8, 0x02, 0x02, 0x08): {
        "name": '启动任务',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 02 08<br>\n<b>命令名称</b>：启动任务<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n\n模块上电后，默认处于任务暂停状态，需要集中器下发启动任务。\n',
        "fields": [{'name': '任务ID', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '要启动的任务标识号'}]
    },

    # 暂停任务 (E8 02 02 09)
    (0xE8, 0x02, 0x02, 0x09): {
        "name": '暂停任务',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 02 09<br>\n<b>命令名称</b>：暂停任务<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n\n需要插入立即执行的任务时，可以先 “暂停任务”，然后通过 “添加任务” 增加高优先级的任务，再 “启动任务”。\n\n### 上行报文\n\n### 数据标识内容定义\n',
        "fields": [{'name': '任务ID', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '要暂停的任务标识号'}]
    },

    # 设置主节点地址 (E8 02 04 01)
    (0xE8, 0x02, 0x04, 0x01): {
        "name": '设置主节点地址',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 01<br>\n<b>命令名称</b>：设置主节点地址<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 80 设置主节点地址数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>主节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": [{'name': '主节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True, 'default': '000000000000', 'description': '6字节地址，低字节在前存储'}]
    },

    # 添加从节点 (E8 02 04 02)
    (0xE8, 0x02, 0x04, 0x02): {
        "name": '添加从节点',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 02<br>\n<b>命令名称</b>：添加从节点<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式下表。\n\n该命令只用于添加表地址为 6 字节的电能表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 81 添加从节点数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点的数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 1 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 n 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": [{'name': '从节点数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '要添加的从节点数量（自动计算，无需手动填写）'}, {'name': '从节点地址列表', 'type': 'list', 'count_field': '从节点数量', 'required': True, 'item_fields': [{'name': '从节点地址', 'type': 'bytes', 'length': 6, 'reverse': True, 'description': '6字节地址，低字节在前存储'}], 'description': '从节点地址列表，数量由上一字段决定'}]
    },

    # 删除从节点 (E8 02 04 03)
    (0xE8, 0x02, 0x04, 0x03): {
        "name": '删除从节点',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 03<br>\n<b>命令名称</b>：删除从节点<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 82 删除从节点数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点的数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 1 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'></td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 n 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": [{'name': '从节点数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '要删除的从节点数量（自动计算，无需手动填写）'}, {'name': '从节点地址列表', 'type': 'list', 'count_field': '从节点数量', 'required': True, 'item_fields': [{'name': '从节点地址', 'type': 'bytes', 'length': 6, 'reverse': True, 'description': '6字节地址，低字节在前存储'}], 'description': '从节点地址列表，数量由上一字段决定'}]
    },

    # 允许/禁止从节点上报 (E8 02 04 04)
    (0xE8, 0x02, 0x04, 0x04): {
        "name": '允许/禁止从节点上报',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 04<br>\n<b>命令名称</b>：允许/禁止从节点上报<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 83 允许/禁止上报从节点事件数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>事件上报状态标志</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n事件上报状态标志：0 禁止，1 允许。该标识含义为是否允许从节点事件上报，上电后默认为允许，禁止后，电能表端的事件不再上报给集中器，且在下次下发允许或初始化前一直保持在禁止状态。\n',
        "fields": [{'name': '事件上报状态标志', 'type': 'enum', 'length': 1, 'required': True, 'enum_map': {0: '禁止上报', 1: '允许上报'}, 'default': 1, 'description': '0x00=禁止上报，0x01=允许上报'}]
    },

    # 激活从节点主动注册 (E8 02 04 05)
    (0xE8, 0x02, 0x04, 0x05): {
        "name": '激活从节点主动注册',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 05<br>\n<b>命令名称</b>：激活从节点主动注册<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。集中器激活从节点主动注册，要求主模块收集从模块下接电能表信息并上报集中器。主模块使用 E8 05 05 03 上报从节点信息。\n',
        "fields": []
    },

    # 终止从节点主动注册 (E8 02 04 06)
    (0xE8, 0x02, 0x04, 0x06): {
        "name": '终止从节点主动注册',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 06<br>\n<b>命令名称</b>：终止从节点主动注册<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n',
        "fields": []
    },

    # 添加从节点通信地址映射表 (E8 02 04 07)
    (0xE8, 0x02, 0x04, 0x07): {
        "name": '添加从节点通信地址映射表',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 07<br>\n<b>命令名称</b>：添加从节点通信地址映射表<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 84 添加从节点通信地址映射表数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>本次添加从节点数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 1 通信地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 1 表计地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>12</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 n 通信地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 n 表计地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>12</td></tr></table>\n\n注：每个从节点通信映射地址（18 字节）组成：通信地址（6 字节）+00 00 00 00 00 00H（6 字节）+表地址（6 字节）。\n',
        "fields": [{'name': '本次添加从节点数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '本次添加的映射记录数量（自动计算，无需手动填写）'}, {'name': '映射表', 'type': 'list', 'count_field': '本次添加从节点数量', 'required': True, 'item_fields': [{'name': '从节点通信地址', 'type': 'bytes', 'length': 6, 'reverse': True, 'description': '6字节通信地址，低字节在前存储'}, {'name': '从节点表计地址', 'type': 'bytes', 'length': 12, 'reverse': True, 'description': '12字节表计地址，低字节在前存储'}], 'description': '映射表记录列表'}]
    },

    # 设置最大网络规模 (E8 02 04 6A)
    (0xE8, 0x02, 0x04, 0x6A): {
        "name": '设置最大网络规模',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 02 04 6A<br>\n<b>命令名称</b>：设置最大网络规模<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大网络规模</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>\n\na) 最大网络规模： $ \\leq 1000 $；缺省配置：1000；\n",
        "fields": [{'name': '最大网络规模', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 1000, 'description': '网络最大节点数量'}]
    },

    # 设置最大网络级数 (E8 02 04 6B)
    (0xE8, 0x02, 0x04, 0x6B): {
        "name": '设置最大网络级数',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 02 04 6B<br>\n<b>命令名称</b>：设置最大网络级数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>最大网络级数</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>\n\na) 最大网络级数： $ \\leq 15 $；缺省配置：15；\n",
        "fields": [{'name': '最大网络级数', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 10, 'description': '网络最大层级数'}]
    },

    # 允许/禁止拒绝从节点信息上报 (E8 02 04 6C)
    (0xE8, 0x02, 0x04, 0x6C): {
        "name": '允许/禁止拒绝从节点信息上报',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 02 04 6C<br>\n<b>命令名称</b>：允许/禁止拒绝从节点信息上报<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n设置格式[狼3]：缩进: 左 2.01 字符, 首行缩进: 0 字符, 编号 + 级别: 1 + 编号样式: a, b, c, ... + 起始编号: 1 + 对齐方式: 左侧 + 对齐位置: 7.4 毫米 + 缩进位置: 14.8 毫米\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>拒绝从节点信息上报使能</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n\n设置格式[狼 3]: 项目符号和编号\n\na） 拒绝从节点信息上报：0：禁止；1：允许；缺省配置：1；\n\n 规模\n",
        "fields": [{'name': '上报状态', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '0=禁止,1=允许拒绝上报'}]
    },

    # 设置无线参数 (E8 02 04 6D)
    (0xE8, 0x02, 0x04, 0x6D): {
        "name": '设置无线参数',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 02 04 6D<br>\n<b>命令名称</b>：设置无线参数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>OPTION</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>CHANNEL</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n\na) OPTION: 0: OPTION1; 1: OPTION2; 2: OPTION3;\n",
        "fields": [{'name': '数据内容', 'type': 'bytes', 'required': False, 'default': '', 'description': '无线参数数据（hex字符串）'}]
    },

    # 配置踢出后不允许入网时间 (E8 02 04 72)
    (0xE8, 0x02, 0x04, 0x72): {
        "name": '配置踢出后不允许入网时间',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 02 04 72<br>\n<b>命令名称</b>：配置踢出后不允许入网时间<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>踢出不允许入网时间</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr></table>\n\na) 单位：秒；缺省配置：CCO 自动动态控制；\n",
        "fields": [{'name': '禁止入网时间', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '踢出后禁止入网时间（分钟）'}]
    },

    # 配置运行参数 (E8 02 04 74)
    (0xE8, 0x02, 0x04, 0x74): {
        "name": '配置运行参数',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 74<br>\n<b>命令名称</b>：配置运行参数<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>站点 MAC 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>配置参数总数 m</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 1ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 1 配置数据长度</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 1 数据</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>见运行参数列表</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 2ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 2 配置数据长度</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 2 数据</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>见运行参数列表</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>...</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'></td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 mID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 m 配置数据长度</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>1 字节</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>参数 m 数据</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>见运行参数列表</td></tr></table>\n\n<div style="text-align: center;"><div style="text-align: center;">运行参数列表</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>运行参数 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td><td style=\'text-align: center; word-wrap: break-word;\'>说明</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x01</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>从节点RF发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x02</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>从节点PLC发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x03</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>异常离网锁定时间，单位：分钟，默认30分钟</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x04</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>RF通道控制开关：0：关闭；1：开启；默认开启</td></tr></table>\n',
        "fields": [{'name': '数据内容', 'type': 'bytes', 'required': False, 'default': '', 'description': '运行参数数据（hex字符串）'}]
    },

    # 启动台区识别 (E8 02 04 80)
    (0xE8, 0x02, 0x04, 0x80): {
        "name": '启动台区识别',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 80<br>\n<b>命令名称</b>：启动台区识别<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式如表18所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 85 启动台区识别数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>台区特征发送时长</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）台区特征发送时长，表示 CCO 发送台区特征允许的最大时长，单位为分钟（最大不超过 1440 分钟）。0 代表 1440 分钟；超时时间到期后，台区识别自动结束。\n\n注：若集中器未给 CCO 设置主节点地址，启动台区识别时，CCO 应答否认帧，否认原因码扩展为 EOH，主节点地址不存在。\n',
        "fields": [{'name': '台区识别模式', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '台区识别工作模式'}]
    },

    # 停止台区识别 (E8 02 04 81)
    (0xE8, 0x02, 0x04, 0x81): {
        "name": '停止台区识别',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 81<br>\n<b>命令名称</b>：停止台区识别<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n',
        "fields": []
    },

    # 设置宽带载波频段 (E8 02 04 90)
    (0xE8, 0x02, 0x04, 0x90): {
        "name": '设置宽带载波频段',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 90<br>\n<b>命令名称</b>：设置宽带载波频段<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 86 设置宽带载波频段数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>宽带载波频段</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na) 宽带载波频段：0:1.953～11.96MHz；1：2.441～5.615 MHz；2：0.781～2.930 MHz；3～255 表示保留。 $ \\underline{\\text{缺省配置：2；}} $\n\nb）只能集中器使用，抄控器不能使用该命令。\n',
        "fields": [{'name': '载波频段', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '宽带载波频段代码'}]
    },

    # 允许/禁止白名单功能 (E8 02 04 93)
    (0xE8, 0x02, 0x04, 0x93): {
        "name": '允许/禁止白名单功能',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 02 04 93<br>\n<b>命令名称</b>：允许/禁止白名单功能<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单开关</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>白名单生效范围</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n\na) 白名单开关：0：关闭；1：打开；缺省配置：1；\n\nb) 白名单生效范围：0：表档案；1：厂家自定义；2：表档案和厂家自定义的合集；3～255：保留。\n",
        "fields": [{'name': 'enable', 'type': 'uint8', 'length': 1, 'required': True}, {'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 重启节点 (E8 02 04 F0)
    (0xE8, 0x02, 0x04, 0xF0): {
        "name": '重启节点',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 04 F0<br>\n<b>命令名称</b>：重启节点<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 87 重启节点数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>等待时长</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\na) 节点地址：CCO 可填全 0。\n\nb）等待时长：节点重启前的等待时长，设置范围为 5~300，单位为秒。上行报文\n\n写参数上行报文为确认/否认报文，详见“确认/否认”报文格式。\n',
        "fields": [{'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 启动文件传输 (E8 02 07 01)
    (0xE8, 0x02, 0x07, 0x01): {
        "name": '启动文件传输',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 07 01<br>\n<b>命令名称</b>：启动文件传输<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 99 启动文件传输数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件性质</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>目的地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件总段数 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件大小</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>4</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件总校验</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>文件传输超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na) 文件性质；\n\n1）00H：清除下装文件；文件 ID 为 FFH 时，表示清除模块所有已接收且可以被清除的文件。文件 ID 不为 FFH 时，表示清除指定文件 ID 的文件，且该文件可以被清除。\n\n2）01H：集中器本地通信模块文件；\n\n3）02H：从节点模块文件；\n\nb) 文件 ID：用来区分不同的文件。\n\nc)\n\nd) 文件总段数 n：文件传输内容的总段数。\n\ne) 文件大小：文件的总长度，单位字节。\n\nf）文件总校验：文件所有内容的 CRC16 校验和。CRC16 校验生成多项式采用 CRC16-CCITT（0x1021）， $ x_{16} + x_{12} + x_{5} + 1 $。\n\ng) 文件传输超时时间：模块如果无法在超时时间内完成文件传输，则不再向从模块传输文件。集中器查询文件处理进度时，模块返回未全部成功，存在失败节点。单位为分钟。\n\nh) 文件传输采用串行方式，不允许并行传输文件。模块可根据自身存储容量存储多个文件。模块在未接收完文件时，若该文件不存在或者可以清除，则回复确认；若无法删除则回复否认。\n',
        "fields": [{'name': '文件类型', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '文件类型代码（如0x00=固件升级）'}, {'name': '文件ID', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '文件标识号'}, {'name': '目的地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True, 'default': '999999999999', 'description': '6字节目的地址，低字节在前存储'}, {'name': '总段数', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '文件总分段数量'}, {'name': '文件大小', 'type': 'uint32', 'length': 4, 'required': True, 'endian': 'big', 'default': 0, 'description': '文件总大小（字节）'}, {'name': '文件校验和', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '文件总校验和（如CRC-16）'}, {'name': '超时时间', 'type': 'uint8', 'length': 1, 'required': True, 'default': 30, 'description': '单段传输超时时间（秒）'}]
    },

    # 传输文件内容 (E8 02 07 02)
    (0xE8, 0x02, 0x07, 0x02): {
        "name": '传输文件内容',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 07 02<br>\n<b>命令名称</b>：传输文件内容<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 100 传输文件内容数据标识内容格式</div> </div>\n\n<table border="1" style="margin: auto; word-wrap: break-word;"><tr><td style="text-align: center; word-wrap: break-word;">数据标识内容</td><td style="text-align: center; word-wrap: break-word;">数据格式</td><td style="text-align: center; word-wrap: break-word;">字节数</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段号</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段长度 L</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段内容</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">L</td></tr><tr><td style="text-align: center; word-wrap: break-word;">文件段校验</td><td style="text-align: center; word-wrap: break-word;">BIN</td><td style="text-align: center; word-wrap: break-word;">2</td></tr></table>\n\na） 文件段号：文件内容的传输帧序号，取值范围 0 至 n-1（n 为文件总段数）\n\nb) 文件段长度 L：该帧文件内容长度；文件段长度不大于模块所支持的最大长度，长度值应在 64、128、256、512、1024 中选择。除了最后一个文件段，其他文件段的长度必须相同。\n\nc) 文件段内容：该帧传输的文件内容，长度为 L 字节。\n\nd）文件段校验：该帧文件内容的 CRC16 校验和。CRC16 校验生成多项式采用 CRC16-CCITT  $ (0x1021) $， $ x^{16} + x^{12} + x^{5} + 1 $。\n',
        "fields": [{'name': '段序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '当前传输段序号（从0开始）'}, {'name': '段长度', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '本段数据长度（字节）'}, {'name': '段数据', 'type': 'bytes', 'length_field': '段长度', 'required': True, 'default': '', 'description': '段原始数据（hex字符串输入）'}, {'name': '段校验和', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '本段数据校验和'}]
    },

    # 触发指定节点网络维护 (E8 02 10 14)
    (0xE8, 0x02, 0x10, 0x14): {
        "name": '触发指定节点网络维护',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 10 14<br>\n<b>命令名称</b>：触发指定节点网络维护<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n本命令用于触发指定节点探测与邻居节点的链路信号质量。主节点接收到此命令之后，对指定的从节点逐一发起网络维护。\n\n数据标识编码定义见下表\n\n<div style="text-align: center;"><div style="text-align: center;">表6-99 触发指定节点网络维护数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>探测方案</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>通信信道</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>超时时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点数量n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点1地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>...</td><td style=\'text-align: center; word-wrap: break-word;\'>...</td><td style=\'text-align: center; word-wrap: break-word;\'>...</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点n地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n\na） 探测方案：0 表示在当前主路径上探测与父节点的通信链路质量；\n\n1 表示中心节点寻找可与从节点通信的邻居节点，再探测该从节点与各邻居节点的通信链路质量，最后更新从节点的邻居表；\n\nb）通信信道：0 表示默认；1 表示在公共信道低频点上探测；2 表示在公共信道高频点上探测；3 表示在私有信道低频点上探测；4 表示在私有信道高频点上探测。\n\n2 表示暂停指定节点网络维护。\n\nc） 超时时间：探测所有从节点的持续时间，单位：秒；默认时间为  $ \\Sigma t1 \\times $ 从节点 n 邻居节点从节点数量：取值范围 1~16，其它值无效。\n',
        "fields": []
    },

    # 恢复通信速率和信道 (E8 02 10 16)
    (0xE8, 0x02, 0x10, 0x16): {
        "name": '恢复通信速率和信道',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 02 10 16<br>\n<b>命令名称</b>：恢复通信速率和信道<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据内容\n',
        "fields": []
    },

    # 查询未完成任务列表 (E8 03 02 04)
    (0xE8, 0x03, 0x02, 0x04): {
        "name": '查询未完成任务列表',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 02 04<br>\n<b>命令名称</b>：查询未完成任务列表<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 14 查询未完成任务列表数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>起始任务序号 m</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>本次查询的任务数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）起始任务序号 m：任务的起始序号，表示在任务列表中的第 m 个任务，序号从 0 开始。\n\nb) 本次查询的任务数量 n：本次查询的任务个数，起始序号为 m，任务数量为 n，表示查询任务列表中的第 m, m+1，……，m+n-1 个任务，n≥1。\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询任务数量'}]
    },

    # 查询未完成任务详细信息 (E8 03 02 05)
    (0xE8, 0x03, 0x02, 0x05): {
        "name": '查询未完成任务详细信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 02 05<br>\n<b>命令名称</b>：查询未完成任务详细信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 15 查询未完成任务详细信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>任务 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\n任务 ID: 区分不同任务的任务标识。\n',
        "fields": [{'name': '任务ID', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'little', 'default': 0, 'description': '要查询的任务标识号'}]
    },

    # 查询通信延时时长 (E8 03 03 04)
    (0xE8, 0x03, 0x03, 0x04): {
        "name": '查询通信延时时长',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 04<br>\n<b>命令名称</b>：查询通信延时时长<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>通信目的地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>报文长度 L</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\n<div style="text-align: center;"><div style="text-align: center;">表 22 查询通信延时时长数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>通信目的地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>报文长度 L</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\na）通信目的地址，其中，99 99 99 99 99 99 表示广播地址。\n\nb) 报文长度 L：需要计算通信下行延时的报文长度。\n',
        "fields": [{'name': '目的地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True, 'default': '000000000000', 'description': '6字节目的地址，低字节在前存储'}, {'name': '报文长度', 'type': 'uint16', 'length': 2, 'endian': 'little', 'optional': True, 'default': 0, 'description': 'PLUZ扩展字段，可选，报文长度（小端序）'}]
    },

    # 查询从节点信息 (E8 03 03 06)
    (0xE8, 0x03, 0x03, 0x06): {
        "name": '查询从节点信息',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 03 03 06<br>\n<b>命令名称</b>：查询从节点信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n### 表 23 查询从节点信息数据标识内容格式\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n\na）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。\n\nb) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1, ..., m+n-1 个从节点，n≥1。\n",
        "fields": [{'name': '从节点序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '从节点序号'}]
    },

    # 查询从节点的父节点 (E8 03 03 08)
    (0xE8, 0x03, 0x03, 0x08): {
        "name": '查询从节点的父节点',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 08<br>\n<b>命令名称</b>：查询从节点的父节点<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 24 查询从节点的父节点数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": [{'name': '从节点序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '从节点序号'}]
    },

    # 查询从节点通信地址映射表 (E8 03 03 0A)
    (0xE8, 0x03, 0x03, 0x0A): {
        "name": '查询从节点通信地址映射表',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 0A<br>\n<b>命令名称</b>：查询从节点通信地址映射表<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表6-24 查询从节点通信地址映射表数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>映射表记录起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>查询的映射表数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）映射表记录起始序号 m：表示在从节点通信地址映射记录在列表中的第 m 个从节点，序号从 0 开始。\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询记录数量'}]
    },

    # 查询从节点相位信息 (E8 03 03 0C)
    (0xE8, 0x03, 0x03, 0x0C): {
        "name": '查询从节点相位信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 0C<br>\n<b>命令名称</b>：查询从节点相位信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 26 查询从节点相位信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>本次查询从节点数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 1 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'>……</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点 n 地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n\na) 从节点数量 n 需满足： $ 0 < n \\leq 16 $。\n',
        "fields": [{'name': '数据内容', 'type': 'bytes', 'required': False, 'default': '', 'description': '查询从节点相位信息的自定义数据内容（hex字符串）'}]
    },

    # 批量查询从节点相位信息 (E8 03 03 0D)
    (0xE8, 0x03, 0x03, 0x0D): {
        "name": '批量查询从节点相位信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 0D<br>\n<b>命令名称</b>：批量查询从节点相位信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表6–26 批量查询从节点相位信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。\n\nb)从节点数量 n: 从节点起始序号为 m, 从节点数量为 n, 表示查询从节点列表中的第  $ m, m+1, \\ldots, m+n-1 $ 个从节点,  $ n \\geqslant 1 $。\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询节点数量'}]
    },

    # 查询表档案的台区识别结果 (E8 03 03 0E)
    (0xE8, 0x03, 0x03, 0x0E): {
        "name": '查询表档案的台区识别结果',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 0E<br>\n<b>命令名称</b>：查询表档案的台区识别结果<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 28 查询表档案的台区识别结果数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。\n\nb) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第  $ m, m+1, \\ldots, m+n-1 $ 个从节点， $ n \\geq 1 $。\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询数量'}]
    },

    # 查询多余节点的台区识别结果 (E8 03 03 0F)
    (0xE8, 0x03, 0x03, 0x0F): {
        "name": '查询多余节点的台区识别结果',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 0F<br>\n<b>命令名称</b>：查询多余节点的台区识别结果<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 29 查询多余节点的台区识别结果数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始。\n\nb) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1, ..., m+n-1 个从节点，n≥1。\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询数量'}]
    },

    # 查询台区识别状态 (E8 03 03 10)
    (0xE8, 0x03, 0x03, 0x10): {
        "name": '查询台区识别状态',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 10<br>\n<b>命令名称</b>：查询台区识别状态<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n',
        "fields": []
    },

    # 批量查询厂商代码和版本信息 (E8 03 03 12)
    (0xE8, 0x03, 0x03, 0x12): {
        "name": '批量查询厂商代码和版本信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 12<br>\n<b>命令名称</b>：批量查询厂商代码和版本信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式如下表所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 30 批量查询厂商代码和版本信息</div> </div>\n\n\n\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点起始序号m</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点数量n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始，0 表示 CCO，1 表示第 1 个从节点，2 表示第 2 个从节点，以此类推。每次查询的节点数量建议不超过 15 个。\n\n从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1，……，m+n-1 个从节点，n≥1。\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询数量'}]
    },

    # 查询模块资产信息 (E8 03 03 13)
    (0xE8, 0x03, 0x03, 0x13): {
        "name": '查询模块资产信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 13<br>\n<b>命令名称</b>：查询模块资产信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式如下表所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 31 查询模块资产信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>信息列表元素数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>信息元素 ID1</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'>……</td><td style=\'text-align: center; word-wrap: break-word;\'></td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>信息元素 IDn</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）节点地址：填写主节点地址时表示查询 CCO 的资产信息；填写节点入网地址时表示查询相应 STA 的资产信息；\n\nb) 信息列表元素数量 n：本次查询信息元素总数量；\n\nc) 信息元素 ID：信息元素 ID 如下表所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 32 信息元素 ID</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>信息元素 ID 取值</td><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td><td style=\'text-align: center; word-wrap: break-word;\'>字母或数字</td><td style=\'text-align: center; word-wrap: break-word;\'>示例</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x00</td><td style=\'text-align: center; word-wrap: break-word;\'>厂商代码</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XX(ASCII)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“南方电网”代号可为“NW”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x01</td><td style=\'text-align: center; word-wrap: break-word;\'>软件版本号（模块）</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XXXX(BCD)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“0001”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x02</td><td style=\'text-align: center; word-wrap: break-word;\'>Bootloader 版本号</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>XX(BIN)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“01”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x05</td><td style=\'text-align: center; word-wrap: break-word;\'>芯片厂商代码</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XX(ASCII)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“南方电网”代号可为“NW”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x06</td><td style=\'text-align: center; word-wrap: break-word;\'>软件发布日期（模块）</td><td style=\'text-align: center; word-wrap: break-word;\'>3</td><td style=\'text-align: center; word-wrap: break-word;\'>YYMMDD(BIN)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“210425”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x08</td><td style=\'text-align: center; word-wrap: break-word;\'>模块出厂通信地址</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td><td style=\'text-align: center; word-wrap: break-word;\'>XXXXXX(BIN)</td><td style=\'text-align: center; word-wrap: break-word;\'>当通信模块不支持模块出厂通信地址或者读取错误时，填写全FF。</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x09</td><td style=\'text-align: center; word-wrap: break-word;\'>硬件版本号（模块）</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XXXX(BCD)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“0001”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x0A</td><td style=\'text-align: center; word-wrap: break-word;\'>硬件发布日期（模块）</td><td style=\'text-align: center; word-wrap: break-word;\'>3</td><td style=\'text-align: center; word-wrap: break-word;\'>YYMMDD(BIN)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“210425”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x0B</td><td style=\'text-align: center; word-wrap: break-word;\'>软件版本号（芯片）</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XXXX(BCD)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“0001”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x0C</td><td style=\'text-align: center; word-wrap: break-word;\'>软件发布日期（芯片）</td><td style=\'text-align: center; word-wrap: break-word;\'>3</td><td style=\'text-align: center; word-wrap: break-word;\'>YYMMDD(BIN)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“210425”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x0D</td><td style=\'text-align: center; word-wrap: break-word;\'>硬件版本号（芯片）</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XXXX(BCD)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“0001”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x0E</td><td style=\'text-align: center; word-wrap: break-word;\'>硬件发布日期（芯片）</td><td style=\'text-align: center; word-wrap: break-word;\'>3</td><td style=\'text-align: center; word-wrap: break-word;\'>YYMMDD(BIN)</td><td style=\'text-align: center; word-wrap: break-word;\'>如“210425”</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x0F</td><td style=\'text-align: center; word-wrap: break-word;\'>应用程序版本号</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>XXXX(BCD)</td><td style=\'text-align: center; word-wrap: break-word;\'>填写“0001”</td></tr></table>\n\n注：资产信息数据应符合低字节在前高字节在后的字节序（小端）。\n',
        "fields": [{'name': '节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True, 'default': '000000000000', 'description': '6字节节点地址'}, {'name': '信息元素数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 0, 'description': '请求的信息元素数量'}, {'name': '信息元素ID列表', 'type': 'list', 'count_field': '信息元素数量', 'required': True, 'item_fields': [{'name': '信息元素ID', 'type': 'uint8', 'length': 1, 'description': '信息元素标识号'}], 'description': '信息元素ID列表'}]
    },

    # 批量查询模块资产信息 (E8 03 03 14)
    (0xE8, 0x03, 0x03, 0x14): {
        "name": '批量查询模块资产信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 14<br>\n<b>命令名称</b>：批量查询模块资产信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式如表72所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 33 查询模块资产信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点起始序号 m</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>信息元素 ID</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na）从节点起始序号 m：表示在从节点列表中的第 m 个从节点，序号从 0 开始，0 表示 CCO，1 表示第 1 个从节点，2 表示第 2 个从节点，以此类推。\n\nb) 从节点数量 n：从节点起始序号为 m，从节点数量为 n，表示查询从节点列表中的第 m, m+1，……，m+n-1 个从节点，n≥1。\n\nc) 信息元素 ID：一次查询一个信息元素。\n',
        "fields": [{'name': '字段_0_2', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big'}]
    },

    # 查询当前工作频段 (E8 03 03 20)
    (0xE8, 0x03, 0x03, 0x20): {
        "name": '查询当前工作频段',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 20<br>\n<b>命令名称</b>：查询当前工作频段<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n暂无该命令的详细文档定义。\n',
        "fields": []
    },

    # 查询从节点实时信息 (E8 03 03 61)
    (0xE8, 0x03, 0x03, 0x61): {
        "name": '查询从节点实时信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 61<br>\n<b>命令名称</b>：查询从节点实时信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 34 查询从节点实时信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": [{'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}, {'name': '从节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询设备在线状态 (E8 03 03 64)
    (0xE8, 0x03, 0x03, 0x64): {
        "name": '查询设备在线状态',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 64<br>\n<b>命令名称</b>：查询设备在线状态<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 35 查询设备在线状态数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": [{'name': 'req_type', 'type': 'uint8', 'length': 1, 'required': True}, {'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询网络拓扑信息 (E8 03 03 65)
    (0xE8, 0x03, 0x03, 0x65): {
        "name": '查询网络拓扑信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 65<br>\n<b>命令名称</b>：查询网络拓扑信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 36 查询网络拓扑信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点数量 n</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na） 节点序号从 0 开始，数量 n 取值少于支持单次读写从节点信息的最大数量。\n',
        "fields": [{'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询节点运行时长 (E8 03 03 66)
    (0xE8, 0x03, 0x03, 0x66): {
        "name": '查询节点运行时长',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 66<br>\n<b>命令名称</b>：查询节点运行时长<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 37 查询节点运行时长数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n',
        "fields": [{'name': '从节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询指定从节点信息 (E8 03 03 6E)
    (0xE8, 0x03, 0x03, 0x6E): {
        "name": '查询指定从节点信息',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 03 03 6E<br>\n<b>命令名称</b>：查询指定从节点信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>从节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr></table>\n",
        "fields": [{'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}, {'name': '从节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询节点自检结果 (E8 03 03 70)
    (0xE8, 0x03, 0x03, 0x70): {
        "name": '查询节点自检结果',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 70<br>\n<b>命令名称</b>：查询节点自检结果<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 38 查询节点自检结果数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr></table>\n\n节点地址：节点的MAC地址\n',
        "fields": [{'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询运行参数信息 (E8 03 03 74)
    (0xE8, 0x03, 0x03, 0x74): {
        "name": '查询运行参数信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 03 74<br>\n<b>命令名称</b>：查询运行参数信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n<div style="text-align: center;"><div style="text-align: center;">表 39 查询运行参数信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>运行参数总数</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>运行参数ID1</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>运行参数ID2</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>...。</td><td style=\'text-align: center; word-wrap: break-word;\'></td><td style=\'text-align: center; word-wrap: break-word;\'></td></tr></table>\n\n运行参数ID取值如下：\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>运行参数ID</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td><td style=\'text-align: center; word-wrap: break-word;\'>说明</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x01</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>从节点RF发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x02</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>从节点PLC发送功率，范围：0：自动；1-4：数字越大，功率越大；</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x03</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td><td style=\'text-align: center; word-wrap: break-word;\'>异常离网锁定时间，单位：分钟，默认30分钟</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>0x04</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td><td style=\'text-align: center; word-wrap: break-word;\'>RF通道控制开关：0：关闭；1：开启；默认开启</td></tr></table>\n',
        "fields": [{'name': '数量', 'type': 'uint8', 'length': 1, 'required': True}, {'name': '地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True}]
    },

    # 查询设备类型 (E8 03 03 96)
    (0xE8, 0x03, 0x03, 0x96): {
        "name": '查询设备类型',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 03 03 96<br>\n<b>命令名称</b>：查询设备类型<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点数量n</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n",
        "fields": [{'name': '节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True, 'default': '000000000000', 'description': '6字节节点地址'}]
    },

    # 查询节点信道信息 (E8 03 03 98)
    (0xE8, 0x03, 0x03, 0x98): {
        "name": '查询节点信道信息',
        "direction": "down",
        "doc": "<b>DI编码</b>：E8 03 03 98<br>\n<b>命令名称</b>：查询节点信道信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>数据内容</td><td style='text-align: center; word-wrap: break-word;'>数据格式</td><td style='text-align: center; word-wrap: break-word;'>字节数</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>节点地址</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>6</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点起始序号</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>2</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>周边节点数量</td><td style='text-align: center; word-wrap: break-word;'>BIN</td><td style='text-align: center; word-wrap: break-word;'>1</td></tr></table>\n\na）节点地址：表地址。STA 是入网 MAC 地址\n\nb) 周边节点起始序号 m：表示在周边节点列表中的第 m 个从节点，序号从 0 开始。\n\nc) 周边节点数量 n ： 周边节点起始序号为 m ， 节点数量为 n ， 表示查询周边节点列表中的第 m, m+1 ， 。 。 ， m+n-1 个从节点， 每一次查询 6 个（6≥n≥1）。\n\n上行报文\n\n#### 数据标识内容定义\n",
        "fields": [{'name': '节点地址', 'type': 'bytes', 'length': 6, 'required': True, 'reverse': True, 'default': '000000000000', 'description': '6字节节点地址'}]
    },

    # 请求交采数据 (E8 03 06 02)
    (0xE8, 0x03, 0x06, 0x02): {
        "name": '请求交采数据',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 06 02<br>\n<b>命令名称</b>：请求交采数据<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式如表 21 所示。\n\n<div style="text-align: center;"><div style="text-align: center;">表 21 请求交采数据数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据项类型</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>交采数据项标识</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>4</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>采集周期</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>采集数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\na） 数据项类型：1 代表 DL/T645-2007 数据项标识定义；其它取值保留。\n\nb） 数据项标识：若数据项类型为 1 则遵循 DL/T645-2007 中的定义；数据项类型其它取值时，数据项标识定义保留。\n\nc）采集周期：交采数据时间间隔，单位为秒，只每隔该时间采集一次数据。\n\nd）采集数量：连续采集交采数据的数量。\n',
        "fields": [{'name': 'data_type', 'type': 'uint8', 'length': 1, 'required': True}]
    },

    # 查询文件传输失败节点 (E8 03 07 05)
    (0xE8, 0x03, 0x07, 0x05): {
        "name": '查询文件传输失败节点',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 07 05<br>\n<b>命令名称</b>：查询文件传输失败节点<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 101 查询文件传输失败节点数据单元格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>本次查询的节点数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n起始序号从 0 开始。\n\n#### 上行报文\n\n#### 数据标识内容定义\n',
        "fields": [{'name': '起始序号', 'type': 'uint16', 'length': 2, 'required': True, 'endian': 'big', 'default': 0, 'description': '查询起始序号'}, {'name': '查询数量', 'type': 'uint8', 'length': 1, 'required': True, 'default': 1, 'description': '查询节点数量'}]
    },

    # 查询从节点邻居表 (E8 03 10 10)
    (0xE8, 0x03, 0x10, 0x10): {
        "name": '查询从节点邻居表',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 10 10<br>\n<b>命令名称</b>：查询从节点邻居表<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表6-96 查询从节点邻居表数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>从节点地址</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>6</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>开始邻居节点指针</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>读取邻居节点数量（≤16）</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n\n开始邻居节点指针：指从节点邻居表中的指针位置，0 为第一个指针。\n',
        "fields": []
    },

    # 查询主节点状态 (E8 03 10 11)
    (0xE8, 0x03, 0x10, 0x11): {
        "name": '查询主节点状态',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 10 11<br>\n<b>命令名称</b>：查询主节点状态<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据内容\n',
        "fields": []
    },

    # 读取入网节点信息 (E8 03 10 12)
    (0xE8, 0x03, 0x10, 0x12): {
        "name": '读取入网节点信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 10 12<br>\n<b>命令名称</b>：读取入网节点信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表6-97 读取入网节点信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>查询起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>查询数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": []
    },

    # 读取未入网节点信息 (E8 03 10 13)
    (0xE8, 0x03, 0x10, 0x13): {
        "name": '读取未入网节点信息',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 10 13<br>\n<b>命令名称</b>：读取未入网节点信息<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表6-98 读取未入网节点信息数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>读取节点起始序号</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>查询数量</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": []
    },

    # 请求切换通信速率和信道 (E8 03 10 15)
    (0xE8, 0x03, 0x10, 0x15): {
        "name": '请求切换通信速率和信道',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 03 10 15<br>\n<b>命令名称</b>：请求切换通信速率和信道<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n本命令用于掌机向主节点请求切换通信速率和通信信道。掌机在公共信道上发送此命令。\n\n<div style="text-align: center;"><div style="text-align: center;">表6-100 请求切换通信速率和信道数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>通信速率</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>通信信道</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>维护信道空闲恢复时间</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>保留</td><td style=\'text-align: center; word-wrap: break-word;\'>BIN</td><td style=\'text-align: center; word-wrap: break-word;\'>2</td></tr></table>\n\na）通信速率：0:10kbps；1:50kbps；2：100kbps。\n\nb）通信信道：0：主节点模块当前使用的私有信道组；33为维护信道组组；其他值保留。\n\nc）维护信道空闲恢复时间：恢复时间超时之后，自行恢复到原有的工作信道与通信速率。单位为分，默认值为10。范围为1~10。如果通信信道为0，则恢复时间填充0。\n',
        "fields": []
    },

    # 请求集中器时间 (E8 06 06 01)
    (0xE8, 0x06, 0x06, 0x01): {
        "name": '请求集中器时间',
        "direction": "down",
        "doc": '<b>DI编码</b>：E8 06 06 01<br>\n<b>命令名称</b>：请求集中器时间<br>\n<b>传输方向</b>：下行（集中器 → 模块）<br><br>\n无数据标识内容。\n\n下行报文\n\n数据标识内容定义\n\nE8 06 06 01：请求集中器时间\n\n数据标识内容格式见下表。\n\n<div style="text-align: center;"><div style="text-align: center;">表 97 请求集中器时间数据标识内容格式</div> </div>\n\n<table border=1 style=\'margin: auto; word-wrap: break-word;\'><tr><td style=\'text-align: center; word-wrap: break-word;\'>数据标识内容</td><td style=\'text-align: center; word-wrap: break-word;\'>数据格式</td><td style=\'text-align: center; word-wrap: break-word;\'>字节数</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前时间—秒</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前时间—分</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前时间—时</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前时间—日</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前时间—月</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr><tr><td style=\'text-align: center; word-wrap: break-word;\'>当前时间—年（低字节）</td><td style=\'text-align: center; word-wrap: break-word;\'>BCD</td><td style=\'text-align: center; word-wrap: break-word;\'>1</td></tr></table>\n',
        "fields": []
    },

}
