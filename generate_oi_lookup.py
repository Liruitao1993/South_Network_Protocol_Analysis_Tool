"""
Generate updated dl_t698_45_oi_lookup.py with complete CLASS_ID_MAP and OI_TO_CLASS_ID.
"""
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

with open('extracted_classes.json', 'r', encoding='utf-8') as f:
    extracted = json.load(f)

with open('oi_to_class.json', 'r', encoding='utf-8') as f:
    oi_to_class_raw = json.load(f)

# Convert string keys back to int
oi_to_class = {int(k, 16): v for k, v in oi_to_class_raw.items()}

# Build CLASS_ID_MAP with manual fixes for corrupted/missing data
CLASS_ID_MAP = {}

# Helper to convert extracted dict (string keys) to proper format
def load_extracted(class_id):
    s = str(class_id)
    if s in extracted:
        info = extracted[s]
        return {
            'name': info['name'],
            'attributes': {int(k): v for k, v in info['attributes'].items()},
            'methods': {int(k): v for k, v in info['methods'].items()},
        }
    return None

# Classes 1-11, 13-20: use extracted data where available
for cid in list(range(1, 12)) + list(range(13, 21)):
    data = load_extracted(cid)
    if data:
        CLASS_ID_MAP[cid] = data

# Fix class 1 (corrupted attributes 6-9)
CLASS_ID_MAP[1] = {
    'name': '电能量类',
    'attributes': {
        1: '逻辑名',
        2: '总及费率电能量数组',
        3: '换算及单位',
        4: '扩展精度总及费率电能量数组',
        5: '扩展精度换算及单位',
        6: '总及费率电能量尾数数组',
        7: '总及费率电能量尾数换算及单位',
        8: '扩展精度2总及费率电能量数组',
        9: '扩展精度2总及费率电能量换算及单位',
        30: '带品质的总及费率电能量数组',
        31: '带品质的扩展精度总及费率电能量数组',
    },
    'methods': {1: '复位', 2: '执行'},
}

# Fix class 12 (脉冲计量类)
CLASS_ID_MAP[12] = {
    'name': '脉冲计量类',
    'attributes': {
        1: '逻辑名',
        2: '通信地址',
        3: '互感器倍率',
        4: '脉冲配置',
        5: '有功功率',
        6: '无功功率',
        7: '当日正向有功电量',
        8: '当月正向有功电量',
        9: '当日反向有功电量',
        10: '当月反向有功电量',
        11: '当日正向无功电量',
        12: '当月正向无功电量',
        13: '当日反向无功电量',
        14: '当月反向无功电量',
        15: '正向有功电能示值',
        16: '正向无功电能示值',
        17: '反向有功电能示值',
        18: '反向无功电能示值',
        19: '换算及单位',
    },
    'methods': {1: '复位', 2: '执行', 3: '添加脉冲输入单元', 4: '删除脉冲输入单元'},
}

# Class 21 (ESAM接口类)
CLASS_ID_MAP[21] = {
    'name': 'ESAM接口类',
    'attributes': {
        1: '逻辑名',
        2: 'ESAM序列号',
        3: 'ESAM版本号',
        4: '对称密钥版本',
        5: '会话时效门限',
        6: '会话时效剩余时间',
        7: '当前计数器',
        8: '证书版本',
        9: '终端证书序列号',
        10: '终端证书',
        11: '主站证书序列号',
        12: '主站证书',
        13: 'ESAM安全存储对象列表',
        14: '红外认证时效门限',
        15: '红外认证剩余时间',
    },
    'methods': {
        1: '复位', 2: '执行', 3: 'ESAM数据读取', 4: '数据更新',
        5: '协商失效', 6: '钱包操作', 7: '密钥更新', 8: '证书更新',
        9: '参数设置', 10: '钱包初始化', 11: '红外认证请求',
        12: '红外认证指令', 13: '内部认证', 14: '外部认证',
    },
}

# Class 22 (输入输出设备类)
CLASS_ID_MAP[22] = {
    'name': '输入输出设备类',
    'attributes': {
        1: '逻辑名',
        2: '设备对象列表',
        3: '设备对象数量',
        4: '配置参数',
        5: '端口授权状态',
    },
    'methods': {1: '复位', 2: '执行', 3: '端口授权开启'},
}

# Class 23 (总加组类)
CLASS_ID_MAP[23] = {
    'name': '总加组类',
    'attributes': {
        1: '逻辑名',
        2: '总加组配置表',
        3: '总加组有功功率',
        4: '总加组无功功率',
        5: '总加组滑差时间内平均有功功率',
        6: '总加组滑差时间内平均无功功率',
        7: '总加组日有功电量',
        8: '总加组日无功电量',
        9: '总加组月有功电量',
        10: '总加组月无功电量',
        11: '总加组剩余电量（费）',
        12: '当前功率下浮控控后总加组有功功率冻结值',
        13: '总加组滑差时间周期',
        14: '总加组功控轮次配置',
        15: '总加组电控轮次配置',
        16: '总加组控制设置状态',
        17: '总加组当前控制状态',
        18: '换算及单位',
    },
    'methods': {
        1: '清空总加组配置单元', 2: '执行',
        3: '添加一个总加组配置单元', 4: '批量添加总加组配置单元',
        5: '删除一个总加组配置单元',
    },
}

# Class 24 (分项事件对象类) - use extracted but fix
CLASS_ID_MAP[24] = {
    'name': '分项事件对象类',
    'attributes': {
        1: '逻辑名',
        2: '关联对象属性表',
        3: '当前记录数',
        4: '最大记录数',
        5: '配置参数',
        6: '事件记录表1',
        7: '事件记录表2',
        8: '事件记录表3',
        9: '事件记录表4',
        10: '当前值记录表',
        11: '上报标识',
        12: '有效标识',
        14: '时间状态记录表',
        15: '上报方式',
    },
    'methods': {1: '复位', 2: '执行', 4: '添加一个事件关联对象属性', 5: '删除一个事件关联对象属性'},
}

# Class 25 (无线公网/专网通信接口类)
CLASS_ID_MAP[25] = {
    'name': '无线公网/专网通信接口类',
    'attributes': {
        1: '逻辑名',
        2: '通信配置',
        3: '主站通信参数表',
        4: '短信通信参数',
        5: '版本信息',
        6: '支持规约列表',
        7: 'SIM卡ICCID',
        8: 'IMSI',
        9: '信号强度',
        10: 'SIM卡号码',
        11: '终端IP',
        12: '设备描述符',
        13: '运营商及网络制式',
        14: '多网络配置',
    },
    'methods': {1: '复位'},
}

# Class 26 (以太网通信接口类)
CLASS_ID_MAP[26] = {
    'name': '以太网通信接口类',
    'attributes': {
        1: '逻辑名',
        2: '通信配置',
        3: '主站通信参数表',
        4: '终端IP',
        5: 'MAC地址',
    },
    'methods': {1: '复位'},
}

# Class 27 (监控单元接口类)
CLASS_ID_MAP[27] = {
    'name': '监控单元接口类',
    'attributes': {
        1: '逻辑名',
        2: '死区配置集合',
        3: '遥信配置集合',
        4: '遥测越限配置',
    },
    'methods': {
        1: '复位', 2: '执行',
        3: '添加死区配置单元', 4: '添加遥信配置单元',
        5: '添加遥测越限单元', 6: '清空死区配置集合',
        7: '清空遥信配置集合', 8: '清空遥测越限集合',
    },
}

# Class 28 (电器设备类)
CLASS_ID_MAP[28] = {
    'name': '电器设备类',
    'attributes': {
        1: '逻辑名',
        2: '设备描述符',
        3: '厂商版本信息',
        4: '开关机状态',
    },
    'methods': {1: '复位', 2: '执行', 3: '开机', 4: '关机', 5: '透明转发'},
}

# Class 29 (自描述类)
CLASS_ID_MAP[29] = {
    'name': '自描述类',
    'attributes': {
        1: '逻辑名',
        2: '属性描述符',
        3: '方法描述符',
    },
    'methods': {1: '复位', 2: '执行'},
}

print(f"Built CLASS_ID_MAP with {len(CLASS_ID_MAP)} classes")
for cid in sorted(CLASS_ID_MAP.keys()):
    info = CLASS_ID_MAP[cid]
    print(f"  class_id={cid}: {info['name']} - {len(info['attributes'])} attrs, {len(info['methods'])} methods")

# Now generate the output file
output_lines = ['"""DL/T 698.45 OI 查询模块"""', '', 'from typing import Dict, Any, Optional', '', '', 'class OILookup:', '    """对象标识查询"""', '']

# Write OI_NAME_MAP (existing data)
# We need to read it from the original file to preserve exactly
with open('dl_t698_45_oi_lookup.py', 'r', encoding='utf-8') as f:
    original = f.read()

# Extract OI_NAME_MAP from original
start = original.find('    OI_NAME_MAP = {')
end = original.find('\n    }', start) + 6
oi_name_map_block = original[start:end]

output_lines.append(oi_name_map_block)
output_lines.append('')
output_lines.append('    # 接口类映射 (class_id -> {name, attributes, methods})')
output_lines.append('    CLASS_ID_MAP = {')

for cid in sorted(CLASS_ID_MAP.keys()):
    info = CLASS_ID_MAP[cid]
    output_lines.append(f'        {cid}: {{')
    output_lines.append(f'            "name": "{info["name"]}",')
    # attributes
    attrs = info['attributes']
    if attrs:
        attr_items = ', '.join(f'{k}: "{v}"' for k, v in sorted(attrs.items()))
        output_lines.append(f'            "attributes": {{{attr_items}}},')
    else:
        output_lines.append(f'            "attributes": {{}},')
    # methods
    methods = info['methods']
    if methods:
        method_items = ', '.join(f'{k}: "{v}"' for k, v in sorted(methods.items()))
        output_lines.append(f'            "methods": {{{method_items}}},')
    else:
        output_lines.append(f'            "methods": {{}},')
    output_lines.append('        },')

output_lines.append('    }')
output_lines.append('')

# Write OI_TO_CLASS_ID
output_lines.append('    # OI 到 class_id 的映射（从协议文档附录A提取）')
output_lines.append('    OI_TO_CLASS_ID = {')
# Write in chunks for readability
chunk_size = 8
items = sorted(oi_to_class.items())
for i in range(0, len(items), chunk_size):
    chunk = items[i:i+chunk_size]
    line = '        ' + ', '.join(f'0x{oi:04X}: {cid}' for oi, cid in chunk) + ','
    output_lines.append(line)
output_lines.append('    }')
output_lines.append('')

# Write methods
output_lines.extend([
    '    def get_class_name(self, class_id: int) -> Optional[str]:',
    '        info = self.CLASS_ID_MAP.get(class_id)',
    '        if info:',
    '            return info["name"]',
    '        return None',
    '',
    '    def get_attribute_name(self, oi: int, attr_id: int) -> Optional[str]:',
    '        class_id = self.OI_TO_CLASS_ID.get(oi)',
    '        if class_id is None:',
    '            return None',
    '        info = self.CLASS_ID_MAP.get(class_id)',
    '        if info and "attributes" in info:',
    '            return info["attributes"].get(attr_id)',
    '        return None',
    '',
    '    def get_method_name(self, oi: int, method_id: int) -> Optional[str]:',
    '        class_id = self.OI_TO_CLASS_ID.get(oi)',
    '        if class_id is None:',
    '            return None',
    '        info = self.CLASS_ID_MAP.get(class_id)',
    '        if info and "methods" in info:',
    '            return info["methods"].get(method_id)',
    '        return None',
    '',
    '    def get_oad_description(self, oi: int, attr_id: int, index: int) -> str:',
    '        oi_name = self.OI_NAME_MAP.get(oi) or f"未知对象(0x{oi:04X})"',
    '        class_id = self.OI_TO_CLASS_ID.get(oi)',
    '        if class_id is not None:',
    '            class_name = self.CLASS_ID_MAP.get(class_id, {}).get("name", "")',
    '            if class_name:',
    '                oi_name = f"{oi_name} ({class_name})"',
    '        attr_name = self.get_attribute_name(oi, attr_id) or f"属性{attr_id}"',
    '        if index == 0:',
    '            index_desc = "全部内容"',
    '        else:',
    '            index_desc = f"第{index}个元素"',
    '        return f"{oi_name} - {attr_name} ({index_desc})"',
    '',
    '    def get_omd_description(self, oi: int, method_id: int) -> str:',
    '        oi_name = self.OI_NAME_MAP.get(oi) or f"未知对象(0x{oi:04X})"',
    '        class_id = self.OI_TO_CLASS_ID.get(oi)',
    '        if class_id is not None:',
    '            class_name = self.CLASS_ID_MAP.get(class_id, {}).get("name", "")',
    '            if class_name:',
    '                oi_name = f"{oi_name} ({class_name})"',
    '        method_name = self.get_method_name(oi, method_id) or f"方法{method_id}"',
    '        return f"{oi_name} - {method_name}"',
])

with open('dl_t698_45_oi_lookup.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines) + '\n')

print("\nGenerated dl_t698_45_oi_lookup.py")
