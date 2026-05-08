"""基于 networkx 的拓扑关系存储器

与 topology_widget 配合使用，在收到拓扑响应后自动维护节点关系图。
提供层级查询、子树遍历、根路径搜索、JSON 导出等功能。
"""

import networkx as nx
from typing import Dict, List, Optional


class TopologyGraph:
    """基于 networkx.DiGraph 的电力线网络拓扑存储器

    节点属性:
        - address:  12位地址字符串
        - tei:      节点标识（同时也是图节点ID）
        - level:    层级 0=CCO
        - role:     CCO / PCO / STA
        - channel:  载波 / 无线 / -
        - phase:    A/B/C/... / -
        - module_type:   单载波 / 双模 / 无线 / -
        - signal_quality: 信号质量字符串 / -

    边属性:
        - relation: "proxy" (代理/父子关系)
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()

    def clear(self) -> None:
        """清空拓扑图"""
        self.graph.clear()

    def add_nodes(self, nodes: Dict[int, "TopoNode"]) -> None:
        """从 TopoNode 字典批量添加/更新节点"""
        for tei, node in nodes.items():
            self.graph.add_node(
                tei,
                address=node.address,
                tei=node.tei,
                level=node.level,
                role=node.role,
                channel=node.channel,
                phase=node.phase,
                module_type=node.module_type,
                signal_quality=node.signal_quality,
            )
            # 代理边：proxy_tei -> tei 表示代理关系
            if node.proxy_tei >= 0 and node.proxy_tei != tei:
                if node.proxy_tei in nodes:
                    self.graph.add_edge(node.proxy_tei, tei, relation="proxy")

    def add_raw_nodes(self, raw_nodes: List[dict]) -> None:
        """从原始字典列表添加节点（兼容解析输出）"""
        for n in raw_nodes:
            tei = n["tei"]
            self.graph.add_node(
                tei,
                address=n.get("addr", ""),
                tei=tei,
                level=n.get("level", 0),
                role=n.get("role", "STA"),
                channel=n.get("channel", "-"),
                phase=n.get("phase", "-"),
            )
            proxy = n.get("proxy_tei", -1)
            if proxy >= 0 and proxy != tei:
                self.graph.add_edge(proxy, tei, relation="proxy")

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def get_parent(self, tei: int) -> int:
        """获取父节点（代理节点）TEI，无则返回 -1"""
        preds = list(self.graph.predecessors(tei))
        return preds[0] if preds else -1

    def get_children(self, tei: int) -> List[int]:
        """获取子节点 TEI 列表"""
        return list(self.graph.successors(tei))

    def get_root(self) -> int:
        """获取根节点 TEI（无入边者），无则返回 -1"""
        for node in self.graph.nodes:
            if self.graph.in_degree(node) == 0:
                return node
        return -1

    def get_nodes_by_level(self, level: int) -> List[int]:
        """按层级筛选节点 TEI"""
        return [
            n for n, attr in self.graph.nodes(data=True)
            if attr.get("level") == level
        ]

    def get_nodes_by_role(self, role: str) -> List[int]:
        """按角色筛选节点 TEI"""
        return [
            n for n, attr in self.graph.nodes(data=True)
            if attr.get("role") == role
        ]

    def get_subtree_nodes(self, tei: int) -> List[int]:
        """获取某节点下所有子树节点（含自身）"""
        return list(nx.descendants(self.graph, tei)) + [tei]

    def get_path_to_root(self, tei: int) -> List[int]:
        """获取节点到根节点的路径（根在前，自身在后）"""
        root = self.get_root()
        if root == -1 or tei not in self.graph:
            return []
        try:
            return nx.shortest_path(self.graph, source=root, target=tei)
        except nx.NetworkXNoPath:
            return []

    def get_depth(self, tei: int) -> int:
        """获取节点深度（到根节点的跳数）"""
        path = self.get_path_to_root(tei)
        return len(path) - 1 if path else -1

    def get_max_level(self) -> int:
        """获取当前拓扑最大层级"""
        return max(
            (attr.get("level", 0) for _, attr in self.graph.nodes(data=True)),
            default=0,
        )

    # ------------------------------------------------------------------
    # 统计 / 导出
    # ------------------------------------------------------------------

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def export_dict(self) -> dict:
        """导出为 node-link 字典（可 JSON 序列化）"""
        return nx.node_link_data(self.graph, edges="links")

    def to_adjacency_list(self) -> Dict[int, List[int]]:
        """导出为邻接表 {parent: [children]}"""
        return {n: list(self.graph.successors(n)) for n in self.graph.nodes}

    def get_summary(self) -> str:
        """获取人类可读的拓扑摘要"""
        lines = [
            f"节点总数: {self.graph.number_of_nodes()}",
            f"连接总数: {self.graph.number_of_edges()}",
            f"根节点 TEI: {self.get_root()}",
        ]
        roles = {}
        for _, attr in self.graph.nodes(data=True):
            r = attr.get("role", "未知")
            roles[r] = roles.get(r, 0) + 1
        for r, c in sorted(roles.items()):
            lines.append(f"  {r}: {c}")
        max_level = self.get_max_level()
        lines.append(f"最大层级: {max_level}")
        return "\n".join(lines)
