"""
国网协议 AFN+Fn 查询模块
用于 Q/GDW 10376.2—2024 集中器本地通信模块接口协议
"""

from typing import List, Optional, Tuple


class GDWAFNLookup:
    """国网协议 AFN+Fn 组合查询管理器"""

    def __init__(self):
        self._parser = None
        self._data: List[Tuple] = []
        self._build_data_list()

    @property
    def parser(self):
        if self._parser is None:
            from parser_registry import get_parser
            self._parser = get_parser("gdw")
        return self._parser

    def _build_data_list(self):
        """构建用于显示的数据列表"""
        self._data = []
        for afn, afn_name, fn, fn_name in self.parser.get_afn_fn_list():
            self._data.append((afn, afn_name, fn, fn_name))

    def search(self, keyword: str) -> List[Tuple]:
        """根据关键词搜索 AFN+Fn 组合"""
        return self.parser.search_afn_fn(keyword)

    def refresh(self) -> None:
        """重建缓存数据（自定义 AFN+Fn 增删后必须调用，否则查询页仍是旧表）。

        `_data` 在构造时一次性构建，而自定义条目是运行时改的（同一进程内
        `parser_registry.get_parser("gdw")` 单例已被就地修改），不重建就读不到。
        """
        self._build_data_list()

    @property
    def data(self) -> List[Tuple]:
        """获取所有 AFN+Fn 数据"""
        return self._data


def get_gdw_afn_lookup() -> GDWAFNLookup:
    """获取国网协议 AFN 查询器实例"""
    global _LOOKUP_INSTANCE
    if _LOOKUP_INSTANCE is None:
        _LOOKUP_INSTANCE = GDWAFNLookup()
    return _LOOKUP_INSTANCE


_LOOKUP_INSTANCE: Optional[GDWAFNLookup] = None
