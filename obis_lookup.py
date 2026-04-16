"""
OBIS 查询模块
用于 HDLC/DLMS/Wrapper/APDU 协议的 OBIS 码查询
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class OBISLookup:
    """OBIS 查询管理器"""

    # 标准 OBIS 码定义 (A.B.C.D.E.F -> 名称, 说明)
    STANDARD_OBIS = {
        # 通用对象 (0.x.x.x.x.255)
        (0, 0, 96, 1, 0, 255): ("设备逻辑名称", "设备的逻辑名称标识"),
        (0, 0, 96, 1, 1, 255): ("制造商", "设备制造商名称"),
        (0, 0, 96, 1, 2, 255): ("产品名称", "产品型号或名称"),
        (0, 0, 96, 1, 3, 255): ("固件版本", "当前固件版本号"),
        (0, 0, 96, 1, 4, 255): ("硬件版本", "当前硬件版本号"),

        # 电能相关对象 (1.x.x.x.x.255)
        (1, 0, 1, 8, 0, 255): ("正向有功总电能", "累计正向有功总电能"),
        (1, 0, 2, 8, 0, 255): ("反向有功总电能", "累计反向有功总电能"),
        (1, 0, 3, 8, 0, 255): ("正向无功总电能", "累计正向无功总电能"),
        (1, 0, 4, 8, 0, 255): ("反向无功总电能", "累计反向无功总电能"),
        (1, 0, 15, 8, 0, 255): ("绝对值有功总电能", "累计绝对值有功总电能"),

        # 需量相关对象 (1.x.x.x.x.255)
        (1, 0, 1, 6, 0, 255): ("正向有功最大需量", "正向有功最大需量及发生时间"),
        (1, 0, 2, 6, 0, 255): ("反向有功最大需量", "反向有功最大需量及发生时间"),

        # 时钟相关 (0.x.x.x.x.255)
        (0, 0, 1, 0, 0, 255): ("时钟", "当前日期和时间"),
        (0, 0, 1, 1, 0, 255): ("时区", "本地时区偏移"),
        (0, 0, 1, 2, 0, 255): ("夏令时", "夏令时状态"),

        # 关联对象 (0.x.x.x.x.255)
        (0, 0, 41, 0, 0, 255): ("当前关联", "当前活动关联"),
        (0, 0, 41, 0, 1, 255): ("关联状态", "当前关联状态"),

        # 安全对象 (0.x.x.x.x.255)
        (0, 0, 43, 1, 0, 255): ("当前用户", "当前活动用户"),
        (0, 0, 43, 1, 1, 255): ("用户列表", "已配置用户列表"),
        (0, 0, 43, 2, 0, 255): ("当前角色", "当前活动角色"),

        # 活动日历 (0.x.x.x.x.255)
        (0, 0, 13, 0, 0, 255): ("活动日历", "当前活动日历"),
        (0, 0, 13, 1, 0, 255): ("日表", "活动日表"),
        (0, 0, 13, 2, 0, 255): ("周表", "活动周表"),
        (0, 0, 13, 3, 0, 255): ("年表", "活动年表"),

        # 寄存器对象 (1.x.x.x.x.255)
        (1, 0, 1, 0, 0, 255): ("正向有功瞬时功率", "当前正向有功瞬时功率"),
        (1, 0, 2, 0, 0, 255): ("反向有功瞬时功率", "当前反向有功瞬时功率"),
        (1, 0, 3, 0, 0, 255): ("正向无功瞬时功率", "当前正向无功瞬时功率"),
        (1, 0, 4, 0, 0, 255): ("反向无功瞬时功率", "当前反向无功瞬时功率"),
        (1, 0, 15, 0, 0, 255): ("总功率因数", "当前总功率因数"),

        # 电压电流 (1.x.x.x.x.255)
        (1, 0, 32, 7, 0, 255): ("L1电压", "A相电压"),
        (1, 0, 52, 7, 0, 255): ("L2电压", "B相电压"),
        (1, 0, 72, 7, 0, 255): ("L3电压", "C相电压"),
        (1, 0, 31, 7, 0, 255): ("L1电流", "A相电流"),
        (1, 0, 51, 7, 0, 255): ("L2电流", "B相电流"),
        (1, 0, 71, 7, 0, 255): ("L3电流", "C相电流"),

        # 谐波 (1.x.x.x.x.255)
        (1, 0, 32, 127, 0, 255): ("L1电压THD", "A相电压总谐波失真"),
        (1, 0, 31, 127, 0, 255): ("L1电流THD", "A相电流总谐波失真"),

        # 需量寄存器 (1.x.x.x.x.255)
        (1, 0, 1, 4, 0, 255): ("正向有功需量", "当前正向有功需量"),
        (1, 0, 2, 4, 0, 255): ("反向有功需量", "当前反向有功需量"),

        # 质量指标 (1.x.x.x.x.255)
        (1, 0, 32, 24, 0, 255): ("L1电压中断次数", "A相电压中断次数"),
        (1, 0, 32, 26, 0, 255): ("L1电压中断累计时间", "A相电压中断累计时间"),

        # 错误寄存器对象 (0.x.x.x.x.255)
        (0, 0, 97, 97, 0, 255): ("错误寄存器", "通用错误寄存器"),
        (0, 0, 97, 97, 1, 255): ("报警寄存器1", "报警寄存器1"),
        (0, 0, 97, 97, 2, 255): ("报警寄存器2", "报警寄存器2"),
        (0, 0, 97, 97, 3, 255): ("报警寄存器3", "报警寄存器3"),

        # 断开控制对象 (0.x.x.x.x.255)
        (0, 0, 96, 3, 10, 255): ("断开控制状态", "断开控制状态"),
        (0, 0, 96, 3, 11, 255): ("断开控制模式", "断开控制模式"),

        # 限电阈值对象 (1.x.x.x.x.255)
        (1, 0, 94, 96, 19, 255): ("限电阈值", "限电阈值"),
    }

    def __init__(self, custom_obis_file: Optional[str] = None):
        """
        初始化 OBIS 查询器

        Args:
            custom_obis_file: 自定义 OBIS 定义文件路径（JSON格式）
        """
        self.custom_obis: Dict[Tuple, Tuple[str, str]] = {}
        self._data: List[Tuple] = []  # 用于表格显示的数据

        # 加载自定义 OBIS
        if custom_obis_file:
            self._load_custom_obis(custom_obis_file)
        else:
            # 默认保存位置
            default_path = Path(__file__).parent / "custom_obis.json"
            if default_path.exists():
                self._load_custom_obis(str(default_path))

        # 构建数据列表
        self._build_data_list()

    def _load_custom_obis(self, filepath: str):
        """从 JSON 文件加载自定义 OBIS"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data:
                obis = tuple(item['obis'])
                self.custom_obis[obis] = (item['name'], item['desc'])
        except Exception as e:
            print(f"加载自定义 OBIS 失败: {e}")

    def save_custom_obis(self, filepath: Optional[str] = None):
        """保存自定义 OBIS 到 JSON 文件"""
        if filepath is None:
            filepath = str(Path(__file__).parent / "custom_obis.json")

        data = []
        for obis, (name, desc) in self.custom_obis.items():
            data.append({
                'obis': list(obis),
                'name': name,
                'desc': desc
            })

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存自定义 OBIS 失败: {e}")
            return False

    def _build_data_list(self):
        """构建用于显示的数据列表"""
        self._data = []

        # 标准 OBIS
        for obis, (name, desc) in self.STANDARD_OBIS.items():
            self._data.append((obis, name, desc, False))  # False = 非自定义

        # 自定义 OBIS（覆盖或追加）
        for obis, (name, desc) in self.custom_obis.items():
            # 检查是否已存在
            found = False
            for i, (o, n, d, is_custom) in enumerate(self._data):
                if o == obis:
                    self._data[i] = (obis, name, desc, True)
                    found = True
                    break
            if not found:
                self._data.append((obis, name, desc, True))

        # 按 OBIS 排序
        self._data.sort(key=lambda x: x[0])

    def search(self, keyword: str) -> List[Tuple]:
        """
        搜索 OBIS

        Args:
            keyword: 搜索关键词（OBIS码或名称）

        Returns:
            匹配的 OBIS 列表
        """
        if not keyword:
            return self._data

        keyword = keyword.strip().upper()
        results = []

        for obis, name, desc, is_custom in self._data:
            # 构建 OBIS 字符串表示
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"

            # 匹配 OBIS 码或名称
            if keyword in obis_str or keyword in name.upper() or keyword in desc.upper():
                results.append((obis, name, desc, is_custom))

        return results

    def get_by_obis(self, obis: Tuple[int, ...]) -> Optional[Tuple[str, str]]:
        """根据 OBIS 码获取名称和描述"""
        # 先查自定义
        if obis in self.custom_obis:
            return self.custom_obis[obis]
        # 再查标准
        if obis in self.STANDARD_OBIS:
            return self.STANDARD_OBIS[obis]
        return None

    def add_custom(self, obis: Tuple[int, ...], name: str, desc: str) -> bool:
        """添加自定义 OBIS"""
        self.custom_obis[obis] = (name, desc)
        self._build_data_list()
        return self.save_custom_obis()

    def delete_custom(self, obis: Tuple[int, ...]) -> bool:
        """删除自定义 OBIS"""
        if obis in self.custom_obis:
            del self.custom_obis[obis]
            self._build_data_list()
            return self.save_custom_obis()
        return False


# 便捷函数
def get_obis_lookup() -> OBISLookup:
    """获取 OBIS 查询器实例"""
    return OBISLookup()


if __name__ == "__main__":
    # 测试
    lookup = get_obis_lookup()
    print(f"总计 OBIS 数量: {len(lookup._data)}")

    # 搜索测试
    results = lookup.search("1.0.1.8")
    print(f"\n搜索 '1.0.1.8' 结果:")
    for obis, name, desc, is_custom in results[:5]:
        print(f"  {obis}: {name} - {desc}")