"""
国网协议 AFN+Fn 查询模块
用于 Q/GDW 10376.2—2024 集中器本地通信模块接口协议
"""

from typing import List, Tuple
from gdw10376_parser import GDW10376Parser


class GDWAFNLookup:
    """国网协议 AFN+Fn 组合查询管理器"""

    def __init__(self):
        self.parser = GDW10376Parser()
        self._data: List[Tuple] = []
        self._build_data_list()

    def _build_data_list(self):
        """构建用于显示的数据列表"""
        self._data = []
        for afn, afn_name, fn, fn_name in self.parser.get_afn_fn_list():
            self._data.append((afn, afn_name, fn, fn_name))

    def search(self, keyword: str) -> List[Tuple]:
        """根据关键词搜索 AFN+Fn 组合"""
        return self.parser.search_afn_fn(keyword)

    @property
    def data(self) -> List[Tuple]:
        """获取所有 AFN+Fn 数据"""
        return self._data


def get_gdw_afn_lookup() -> GDWAFNLookup:
    """获取国网协议 AFN 查询器实例"""
    return GDWAFNLookup()
