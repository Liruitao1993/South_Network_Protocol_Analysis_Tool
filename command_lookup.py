"""
PLC RF 协议命令字查询模块
用于万胜 PLC RF 协议的命令字查询
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class CommandLookup:
    """命令字查询管理器"""

    # 标准命令字定义 (Command Code -> 中文含义, 详细描述)
    STANDARD_COMMANDS = {
        0x1001: ("模块通用信息", "模块通用信息查询/设置"),
        0x1101: ("启动升级命令（初始化）", "开始固件升级流程，初始化升级环境"),
        0x1102: ("发送升级包数据", "传输固件升级包的分片数据"),
        0x1103: ("激活模块固件", "激活新固件，完成升级流程"),
        0x1201: ("数据推送（DataNotification）", "模块向电表推送数据通知"),
        0x1202: ("事件推送（EventNotification）", "模块向电表推送事件通知"),
        0x1301: ("DLMS数据帧封装", "通过DLMS协议封装的数据帧传输"),
        0x2001: ("模块获取电表表号", "查询电表的表号信息"),
        0x2002: ("心跳机制", "模块与电表之间的心跳保活"),
        0x2003: ("模块将自身信息传输至电表", "上报模块自身的配置和状态信息"),
        0x2004: ("获取电表信息", "查询电表的详细信息"),
        0x2101: ("从电表获取G3-PLC信息", "查询G3-PLC网络相关信息"),
        0x2102: ("模块将G3-PLC信息传输至电表", "上报G3-PLC网络状态信息"),
    }

    def __init__(self, custom_commands_file: Optional[str] = None):
        """
        初始化命令字查询器

        Args:
            custom_commands_file: 自定义命令字定义文件路径（JSON格式）
        """
        self.custom_commands: Dict[int, Tuple[str, str]] = {}
        self._data: List[Tuple] = []  # 用于表格显示的数据

        # 加载自定义命令字
        if custom_commands_file:
            self._load_custom_commands(custom_commands_file)
        else:
            # 默认保存位置
            default_path = Path(__file__).parent / "custom_commands.json"
            if default_path.exists():
                self._load_custom_commands(str(default_path))

        # 构建数据列表
        self._build_data_list()

    def _load_custom_commands(self, filepath: str):
        """从 JSON 文件加载自定义命令字"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data:
                code = int(item['code'], 16) if isinstance(item['code'], str) else item['code']
                self.custom_commands[code] = (item['name'], item['desc'])
        except Exception as e:
            print(f"加载自定义命令字失败: {e}")

    def save_custom_commands(self, filepath: Optional[str] = None) -> bool:
        """保存自定义命令字到 JSON 文件"""
        if filepath is None:
            filepath = str(Path(__file__).parent / "custom_commands.json")

        data = []
        for code, (name, desc) in self.custom_commands.items():
            data.append({
                'code': f"0x{code:04X}",
                'name': name,
                'desc': desc
            })

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存自定义命令字失败: {e}")
            return False

    def _build_data_list(self):
        """构建用于显示的数据列表"""
        self._data = []

        # 标准命令字
        for code, (name, desc) in self.STANDARD_COMMANDS.items():
            self._data.append((code, name, desc, False))  # False = 非自定义

        # 自定义命令字（覆盖或追加）
        for code, (name, desc) in self.custom_commands.items():
            # 检查是否已存在
            found = False
            for i, (c, n, d, is_custom) in enumerate(self._data):
                if c == code:
                    self._data[i] = (code, name, desc, True)
                    found = True
                    break
            if not found:
                self._data.append((code, name, desc, True))

        # 按命令字排序
        self._data.sort(key=lambda x: x[0])

    def search(self, keyword: str) -> List[Tuple]:
        """
        搜索命令字

        Args:
            keyword: 搜索关键词（命令字编码或名称）

        Returns:
            匹配的命令字列表
        """
        if not keyword:
            return self._data

        keyword = keyword.strip().upper()
        results = []

        for code, name, desc, is_custom in self._data:
            # 匹配命令字编码（支持 0x1101 或 1101 或 4353）
            code_hex = f"0x{code:04X}"
            code_dec = str(code)

            if keyword in code_hex or keyword in code_dec or keyword == name.upper() or keyword in desc.upper():
                results.append((code, name, desc, is_custom))

        return results

    def get_by_code(self, code: int) -> Optional[Tuple[str, str]]:
        """根据命令字编码获取名称和描述"""
        # 先查自定义
        if code in self.custom_commands:
            return self.custom_commands[code]
        # 再查标准
        if code in self.STANDARD_COMMANDS:
            return self.STANDARD_COMMANDS[code]
        return None

    def add_custom(self, code: int, name: str, desc: str) -> bool:
        """添加自定义命令字"""
        self.custom_commands[code] = (name, desc)
        self._build_data_list()
        return self.save_custom_commands()

    def delete_custom(self, code: int) -> bool:
        """删除自定义命令字"""
        if code in self.custom_commands:
            del self.custom_commands[code]
            self._build_data_list()
            return self.save_custom_commands()
        return False


# 便捷函数
def get_command_lookup() -> CommandLookup:
    """获取命令字查询器实例"""
    return CommandLookup()


if __name__ == "__main__":
    # 测试
    lookup = get_command_lookup()
    print(f"总计命令字数量: {len(lookup._data)}")

    # 搜索测试
    results = lookup.search("1101")
    print(f"\n搜索 '1101' 结果:")
    for code, name, desc, is_custom in results[:5]:
        print(f"  0x{code:04X}: {name} - {desc}")