"""
DLT645-2007 数据标识(DI)查询模块
"""

import json
import os
from typing import List, Tuple, Optional


class DLT645DILookup:
    """DLT645-2007 DI标识查询器"""

    def __init__(self):
        self._di_map: dict = {}  # DI标识 -> DI信息
        self._data: List[Tuple[str, str, str, str, str, bool]] = []  # (di_code, di_name, unit, data_type, desc, is_custom)
        self._custom_file = os.path.join(os.path.dirname(__file__), 'dlt645_di_custom.json')
        self._load_di_map()

    def _load_di_map(self):
        """从JSON文件加载DI映射表"""
        json_path = os.path.join(os.path.dirname(__file__), 'dlt645_di.json')

        # 加载标准DI定义
        standard_dis = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    standard_dis = data.get('di_map', {})
            except Exception as e:
                print(f"加载DLT645 DI文件失败: {e}")

        # 加载自定义DI
        custom_dis = self._load_custom_di()

        # 合并标准DI和自定义DI
        self._di_map = {**standard_dis, **custom_dis}

        # 准备查询数据
        self._rebuild_data_list()

    def _load_custom_di(self) -> dict:
        """加载自定义DI列表"""
        if not os.path.exists(self._custom_file):
            return {}
        try:
            with open(self._custom_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 将列表转换为字典
                result = {}
                for item in data:
                    di_code = item.get('di_code', '').upper()
                    if di_code:
                        result[di_code] = {
                            'name': item.get('name', ''),
                            'unit': item.get('unit', ''),
                            'data_type': item.get('data_type', ''),
                            'length': item.get('length', 4)
                        }
                return result
        except Exception as e:
            print(f"加载自定义DI失败: {e}")
            return {}

    def _rebuild_data_list(self):
        """重建数据列表"""
        self._data = []
        custom_codes = set()

        # 首先收集自定义DI代码
        if os.path.exists(self._custom_file):
            try:
                with open(self._custom_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        custom_codes.add(item.get('di_code', '').upper())
            except:
                pass

        # 构建数据列表
        for di_code, info in self._di_map.items():
            di_code = di_code.upper()
            is_custom = di_code in custom_codes

            di_name = info.get('name', '')
            unit = info.get('unit', '')
            data_type = info.get('data_type', '')
            length = info.get('length', 4)

            desc = f"数据类型: {data_type}, 长度: {length}字节"
            if unit:
                desc += f", 单位: {unit}"

            self._data.append((di_code, di_name, unit, data_type, desc, is_custom))

    def search(self, keyword: str) -> List[Tuple[str, str, str, str, str, bool]]:
        """搜索DI标识"""
        keyword = keyword.strip().upper()
        results = []

        for item in self._data:
            di_code, di_name, unit, data_type, desc, is_custom = item
            # 搜索DI代码、名称、数据类型
            search_text = f"{di_code} {di_name} {data_type}".upper()
            if keyword in search_text:
                results.append(item)

        return results

    def get_di_info(self, di_code: str) -> Optional[dict]:
        """获取指定DI的详细信息"""
        return self._di_map.get(di_code.upper())

    @property
    def data(self) -> List[Tuple[str, str, str, str, str, bool]]:
        """获取所有DI数据"""
        return self._data.copy()

    def add_custom_di(self, di_code: str, name: str, unit: str = "", data_type: str = "", length: int = 4) -> bool:
        """添加自定义DI"""
        di_code = di_code.upper().strip()
        if not di_code or len(di_code) != 8:
            return False

        # 验证DI代码格式（必须是8位十六进制）
        try:
            int(di_code, 16)
        except ValueError:
            return False

        # 添加到自定义列表
        custom_list = []
        if os.path.exists(self._custom_file):
            try:
                with open(self._custom_file, 'r', encoding='utf-8') as f:
                    custom_list = json.load(f)
            except:
                pass

        # 检查是否已存在
        for item in custom_list:
            if item.get('di_code', '').upper() == di_code:
                # 更新
                item['name'] = name
                item['unit'] = unit
                item['data_type'] = data_type
                item['length'] = length
                break
        else:
            # 新增
            custom_list.append({
                'di_code': di_code,
                'name': name,
                'unit': unit,
                'data_type': data_type,
                'length': length
            })

        # 保存
        try:
            with open(self._custom_file, 'w', encoding='utf-8') as f:
                json.dump(custom_list, f, ensure_ascii=False, indent=2)
            # 重新加载
            self._load_di_map()
            return True
        except Exception as e:
            print(f"保存自定义DI失败: {e}")
            return False

    def delete_custom_di(self, di_code: str) -> bool:
        """删除自定义DI"""
        di_code = di_code.upper().strip()

        if not os.path.exists(self._custom_file):
            return False

        try:
            with open(self._custom_file, 'r', encoding='utf-8') as f:
                custom_list = json.load(f)

            # 过滤掉要删除的
            original_len = len(custom_list)
            custom_list = [item for item in custom_list if item.get('di_code', '').upper() != di_code]

            if len(custom_list) == original_len:
                return False  # 没找到

            # 保存
            with open(self._custom_file, 'w', encoding='utf-8') as f:
                json.dump(custom_list, f, ensure_ascii=False, indent=2)

            # 重新加载
            self._load_di_map()
            return True

        except Exception as e:
            print(f"删除自定义DI失败: {e}")
            return False


# 全局查询器实例
_dlt645_di_lookup = None


def get_dlt645_di_lookup() -> DLT645DILookup:
    """获取DLT645 DI查询器单例"""
    global _dlt645_di_lookup
    if _dlt645_di_lookup is None:
        _dlt645_di_lookup = DLT645DILookup()
    return _dlt645_di_lookup