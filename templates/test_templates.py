"""测试用例模板库

提供预置的测试用例模板，测试工程师可一键导入使用。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import json


@dataclass
class TestTemplate:
    """测试用例模板"""
    name: str                    # 模板名称
    description: str             # 描述
    protocol: str                # 协议类型（south/gdw/hdlc/plc_rf/dlt645）
    category: str                # 分类（组网/档案/任务/时间/查询等）
    items: List[Dict[str, Any]]  # 测试项列表


# 预置模板：组网完整流程
TEMPLATE_NETWORKING = TestTemplate(
    name="组网完整流程",
    description="复位 → 查询 → 初始化档案 → 添加从节点 → 等待组网 → 查询拓扑",
    protocol="south",
    category="组网",
    items=[
        {
            "name": "复位硬件",
            "frame_hex": "680C00000100010102E8ED16",
            "match_rule": "682A00C80300020300E8029808000202129078563412FC0301000F00010817484C3039XXXXXXXXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 5000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "680E00880000010001E800007216",
            "persistent": False
        },
        {
            "name": "回复集中器时间",
            "frame_hex": "",
            "match_rule": "680C00C806XX010606E8XX16",
            "match_mode": "HEX",
            "timeout_ms": 600000,
            "send_enabled": False,
            "match_enabled": True,
            "response_frame": "681200000606010606E8【\"time\",6,Y-M-D-h-m-s,\"little\"】【\"CS\",1,3:-2,\"little\"】16",
            "persistent": True
        },
        {
            "name": "查询最大网络规模",
            "frame_hex": "680C000003006A0300E85816",
            "match_rule": "68 0E 00 88 03 00 6A 03 00 E8 F7 03 DA 16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询多网络信息",
            "frame_hex": "680C00000300910300E87F16",
            "match_rule": "68 14 00 88 03 00 91 03 00 E8 00 01 12 90 78 56 34 12 BE 16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询并发数",
            "frame_hex": "680C00000300950300E88316",
            "match_rule": "68 0D 00 88 03 00 95 03 00 E8 14 1F 16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询宽带载波频段",
            "frame_hex": "680C00000300900300E87E16",
            "match_rule": "68 0D 00 88 03 00 90 03 00 E8 XX XX 16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询主节点运行信息",
            "frame_hex": "680C000003006F0300E85D16",
            "match_rule": "6825008803006F0300E8XXXXXXXXFFFFFFFFFFFFFFFFFFFFFFXXXXXXXXXXXXXX000000XX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询台区组网成功率",
            "frame_hex": "680C00000300970300E88516",
            "match_rule": "680E00880300970300E8XXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "初始化档案",
            "frame_hex": "680C00000100020102E8EE16",
            "match_rule": "680E00880000010001E8XXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "添加从节点",
            "frame_hex": "681300000400020402E8012200000000001716",
            "match_rule": "680E00880000010001E800007216",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询从节点数量",
            "frame_hex": "680C00000300050300E8F316",
            "match_rule": "680E00880300050300E801007C16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "等待组网",
            "frame_hex": "",
            "match_rule": "",
            "match_mode": "HEX",
            "timeout_ms": 60000,
            "send_enabled": False,
            "match_enabled": False,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询网络拓扑信息",
            "frame_hex": "680F00000300650303E80000025816",
            "match_rule": "683700880300650304E8020000000212907856341201000000XXXXXXXXXXXX00004022000000000002100100XXXXXXXXXXXX0000XXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        }
    ]
)

# 预置模板：任务管理流程
TEMPLATE_TASK_MANAGEMENT = TestTemplate(
    name="任务管理流程",
    description="初始化任务 → 启动任务 → 添加任务 → 等待数据上报",
    protocol="south",
    category="任务",
    items=[
        {
            "name": "初始化任务",
            "frame_hex": "680C00000100030102E8EF16",
            "match_rule": "680E00880000010001E800007216",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "启动任务",
            "frame_hex": "681800200000000000002200000000000200080202E83816",
            "match_rule": "680E00880000010001E800007216",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "添加任务",
            "frame_hex": "682600200000000000002200000000000200010202E80000801E00070001020304050607F216",
            "match_rule": "680E00880000010001E800007216",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "延时等待任务数据上报",
            "frame_hex": "",
            "match_rule": "681500C80500050505E8000022000000000001E716",
            "match_mode": "HEX",
            "timeout_ms": 25000,
            "send_enabled": False,
            "match_enabled": True,
            "response_frame": "680E00880000010001E800007216",
            "persistent": False
        }
    ]
)

# 预置模板：档案管理流程
TEMPLATE_ARCHIVE_MANAGEMENT = TestTemplate(
    name="档案管理流程",
    description="初始化档案 → 添加从节点 → 查询从节点 → 删除从节点",
    protocol="south",
    category="档案",
    items=[
        {
            "name": "初始化档案",
            "frame_hex": "680C00000100020102E8EE16",
            "match_rule": "680E00880000010001E8XXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "添加从节点1",
            "frame_hex": "681300000400020402E8012200000000001716",
            "match_rule": "680E00880000010001E800007216",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询从节点数量",
            "frame_hex": "680C00000300050300E8F316",
            "match_rule": "680E00880300050300E801007C16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        }
    ]
)

# 预置模板：常见查询命令
TEMPLATE_COMMON_QUERIES = TestTemplate(
    name="常见查询命令",
    description="查询厂商代码、查询版本、查询运行状态等常用查询",
    protocol="south",
    category="查询",
    items=[
        {
            "name": "查询厂商代码",
            "frame_hex": "680C00000300010300E8EF16",
            "match_rule": "68XX00880300010300E8XXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询硬件版本",
            "frame_hex": "680C00000300020300E8F016",
            "match_rule": "68XX00880300020300E8XXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        },
        {
            "name": "查询软件版本",
            "frame_hex": "680C00000300030300E8F116",
            "match_rule": "68XX00880300030300E8XXXXXX16",
            "match_mode": "HEX",
            "timeout_ms": 2000,
            "send_enabled": True,
            "match_enabled": True,
            "response_frame": "",
            "persistent": False
        }
    ]
)

# 所有预置模板
ALL_TEMPLATES = [
    TEMPLATE_NETWORKING,
    TEMPLATE_TASK_MANAGEMENT,
    TEMPLATE_ARCHIVE_MANAGEMENT,
    TEMPLATE_COMMON_QUERIES,
]


def get_templates() -> List[TestTemplate]:
    """获取所有模板"""
    return ALL_TEMPLATES


def get_templates_by_protocol(protocol: str) -> List[TestTemplate]:
    """按协议筛选模板"""
    return [t for t in ALL_TEMPLATES if t.protocol == protocol]


def get_templates_by_category(category: str) -> List[TestTemplate]:
    """按分类筛选模板"""
    return [t for t in ALL_TEMPLATES if t.category == category]


def get_template_names() -> List[str]:
    """获取所有模板名称"""
    return [t.name for t in ALL_TEMPLATES]


def get_template_by_name(name: str) -> Optional[TestTemplate]:
    """根据名称获取模板"""
    for t in ALL_TEMPLATES:
        if t.name == name:
            return t
    return None


def load_template_from_json(file_path: str) -> Optional[TestTemplate]:
    """从 JSON 文件加载模板"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            # 兼容 test_plan.json 格式
            return TestTemplate(
                name=Path(file_path).stem,
                description=f"从 {Path(file_path).name} 加载",
                protocol="south",
                category="自定义",
                items=data
            )
        elif isinstance(data, dict):
            return TestTemplate(
                name=data.get('name', Path(file_path).stem),
                description=data.get('description', ''),
                protocol=data.get('protocol', 'south'),
                category=data.get('category', '自定义'),
                items=data.get('items', [])
            )
    except Exception as e:
        print(f"加载模板失败: {e}")
    return None
