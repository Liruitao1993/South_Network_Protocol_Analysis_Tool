"""拓扑帧解析与 networkx 节点关系存储演示

输出内容：
1. 拓扑查询原始帧（南网 / 国网）
2. 拓扑响应原始帧（含示例节点数据）
3. 解析后的节点信息
4. networkx 有向图存储与导出
"""

import sys
import struct
import networkx as nx
from typing import Dict, List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from protocol_tool import Frame, ControlField
from gdw_send_frame_lib import GDWFrameGenerator
from gdw10376_tool import GDWFrame, GDWControlField


# ========================================================================
# 1. 南网拓扑帧构建与解析
# ========================================================================

def build_south_frame(di3: int, di2: int, di1: int, di0: int,
                      data: bytes = b'',
                      src_addr: bytes = b'\x00' * 6,
                      dst_addr: bytes = b'\x00' * 6,
                      dir_flag: int = 0, prm: int = 1, add_flag: int = 0) -> bytes:
    """使用 protocol_tool.Frame 构建南网协议帧"""
    control = ControlField(dir=dir_flag, prm=prm, add=add_flag, ver=0, reserved=0)
    di = (di3 << 24) | (di2 << 16) | (di1 << 8) | di0
    frame = Frame(control=control, src_addr=src_addr, dst_addr=dst_addr,
                  afn=di1, seq=0, di=di, data=data)
    return frame.frame_pack()


def extract_south_data_area(frame: bytes) -> bytes:
    """从南网帧中提取纯数据区（跳过控制域、AFN、SEQ、DI）"""
    if len(frame) < 10 or frame[0] != 0x68:
        return b""
    length = int.from_bytes(frame[1:3], 'little')
    user_data_len = length - 6
    user_data = frame[4:4 + user_data_len]
    add = (frame[3] >> 5) & 0x01
    pos = 0
    if add:
        pos += 12
    pos += 1 + 1 + 4  # 跳过 AFN + SEQ + DI
    return user_data[pos:]


def parse_south_topology(data_area: bytes) -> List[dict]:
    """解析南网 E8 04 03 65 网络拓扑响应的纯数据区"""
    if len(data_area) < 5:
        return []
    total = int.from_bytes(data_area[0:2], 'little')
    start = int.from_bytes(data_area[2:4], 'little')
    count = data_area[4]
    nodes = []
    offset = 5
    for i in range(count):
        if offset + 19 > len(data_area):
            break
        addr = data_area[offset:offset + 6][::-1].hex().upper()
        tei = int.from_bytes(data_area[offset + 6:offset + 8], 'little')
        proxy_tei = int.from_bytes(data_area[offset + 8:offset + 10], 'little')
        info_byte = data_area[offset + 18]
        level = info_byte & 0x0F
        role_val = (info_byte >> 4) & 0x07
        role = {1: "STA", 2: "PCO", 4: "CCO"}.get(role_val, "未知")
        channel = "无线" if (info_byte >> 7) & 0x01 else "载波"
        nodes.append({
            'addr': addr, 'tei': tei, 'proxy_tei': proxy_tei,
            'level': level, 'role': role, 'channel': channel
        })
        offset += 19
    return nodes


# ========================================================================
# 2. 国网拓扑帧构建与解析
# ========================================================================

def build_gdw_query_frame(fn: int, start_seq: int, query_count: int) -> bytes:
    """使用 GDWFrameGenerator 构建国网拓扑查询帧 (AFN=10)"""
    generator = GDWFrameGenerator()
    info_config = {
        "dir": 0, "prm": 1, "报文序列号": 0,
        "通信模块标识": 0, "中继级别": 0,
        "路由标识": 0, "附属节点标识": 0,
        "冲突检测": 0, "纠错编码标识": 0,
        "信道标识": 0, "预计应答字节数": 0,
        "通信速率": 0, "速率单位标识": 0,
    }
    return generator.generate_frame(
        afn=0x10, fn=fn,
        field_values={"节点起始序号": start_seq, "节点数量": query_count},
        info_config=info_config,
        src_addr="000000000000", dst_addr="000000000000"
    )


def build_gdw_response_frame(fn: int, nodes: List[dict]) -> bytes:
    """使用 GDWFrame 手动构建国网拓扑响应帧"""
    total = len(nodes)
    start = 1
    count = len(nodes)

    data = struct.pack('<H', total)
    data += struct.pack('<H', start)
    data += struct.pack('B', count)
    for node in nodes:
        data += bytes.fromhex(node['addr'])
        data += struct.pack('<H', node['tei'])
        data += struct.pack('<H', node['proxy_tei'])
        info = (node['level'] & 0x0F)
        role_map = {'STA': 1, 'PCO': 2, 'CCO': 4}
        info |= (role_map.get(node['role'], 1) << 4)
        data += struct.pack('B', info)

    control = GDWControlField(comm_type=0, prm=0, dir=1)
    # 6字节信息域（上行）
    info_domain = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    dt = _fn_to_dt(fn)

    frame = GDWFrame(
        control=control,
        info_domain=info_domain,
        address=b'',
        afn=0x10,
        dt=dt,
        data=data,
    )
    return frame.frame_pack()


def _fn_to_dt(fn: int) -> bytes:
    """FN 转 DT (2字节): dt1 的 bit(fn-1)%8=1, dt2=(fn-1)//8"""
    dt1 = 1 << ((fn - 1) % 8)
    dt2 = (fn - 1) // 8
    return bytes([dt1, dt2])


def extract_gdw_data_unit(frame: bytes) -> bytes:
    """从国网帧中提取纯数据单元（跳过控制域、信息域、地址域、AFN、DT）"""
    if len(frame) < 18 or frame[0] != 0x68:
        return b""
    length = int.from_bytes(frame[1:3], 'little')
    # 信息域在 frame[4:10] (6字节)
    comm_module_flag = (frame[4] >> 2) & 0x01
    relay_level = (frame[4] >> 4) & 0x0F
    addr_len = 12 + 6 * relay_level if comm_module_flag else 0
    # frame[4] 是信息域起始(6B), 然后 addr_len, 然后 AFN(1B), DT(2B)
    data_start = 4 + 6 + addr_len + 1 + 2
    # L = 用户数据区长度 + 6; 用户数据区从 frame[4] 开始
    # CS 在 frame[L-2], 16H 在 frame[L-1]
    data_end = length - 2
    if data_start >= data_end or data_end > len(frame):
        return b""
    return frame[data_start:data_end]


def parse_gdw_topology(data_unit: bytes) -> List[dict]:
    """解析国网 AFN=10 F20/F21 网络拓扑响应的纯数据单元"""
    if len(data_unit) < 5:
        return []
    total = int.from_bytes(data_unit[0:2], 'little')
    start = int.from_bytes(data_unit[2:4], 'little')
    count = data_unit[4]
    nodes = []
    offset = 5
    for i in range(count):
        if offset + 11 > len(data_unit):
            break
        addr = data_unit[offset:offset + 6].hex().upper()
        tei = int.from_bytes(data_unit[offset + 6:offset + 8], 'little')
        proxy_tei = int.from_bytes(data_unit[offset + 8:offset + 10], 'little')
        info_byte = data_unit[offset + 10]
        level = info_byte & 0x0F
        role_val = (info_byte >> 4) & 0x07
        role = {1: "STA", 2: "PCO", 4: "CCO"}.get(role_val, "未知")
        nodes.append({
            'addr': addr, 'tei': tei, 'proxy_tei': proxy_tei,
            'level': level, 'role': role
        })
        offset += 11
    return nodes


# ========================================================================
# 3. NetworkX 拓扑图存储
# ========================================================================

class TopologyGraph:
    """基于 networkx 的拓扑关系存储器

    节点属性:
        - address:  12位地址字符串
        - tei:      节点标识
        - level:    层级
        - role:     CCO/PCO/STA
        - channel:  载波/无线（南网）

    边属性:
        - relation: "proxy" (代理/父子关系)
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    def add_nodes_from_raw(self, raw_nodes: List[dict]) -> None:
        """从原始字典列表添加节点（兼容 parse_*_topology 输出）"""
        for n in raw_nodes:
            tei = n['tei']
            self.graph.add_node(
                tei,
                address=n.get('addr', ''),
                tei=tei,
                level=n.get('level', 0),
                role=n.get('role', 'STA'),
                channel=n.get('channel', '-'),
                phase=n.get('phase', '-'),
            )
            proxy = n.get('proxy_tei', -1)
            if proxy >= 0 and proxy != tei:
                self.graph.add_edge(proxy, tei, relation='proxy')

    def get_parent(self, tei: int) -> int:
        """获取指定节点的父节点（代理节点）"""
        preds = list(self.graph.predecessors(tei))
        return preds[0] if preds else -1

    def get_children(self, tei: int) -> List[int]:
        """获取指定节点的子节点列表"""
        return list(self.graph.successors(tei))

    def get_root(self) -> int:
        """获取根节点（无入边的节点）"""
        for node in self.graph.nodes:
            if self.graph.in_degree(node) == 0:
                return node
        return -1

    def get_nodes_by_level(self, level: int) -> List[int]:
        """按层级筛选节点"""
        return [
            n for n, attr in self.graph.nodes(data=True)
            if attr.get('level') == level
        ]

    def get_subtree_nodes(self, tei: int) -> List[int]:
        """获取某节点下的所有子树节点（含自身）"""
        return list(nx.descendants(self.graph, tei)) + [tei]

    def get_path_to_root(self, tei: int) -> List[int]:
        """获取节点到根节点的路径"""
        root = self.get_root()
        if root == -1 or tei not in self.graph:
            return []
        try:
            return nx.shortest_path(self.graph, source=root, target=tei)
        except nx.NetworkXNoPath:
            return []

    def export_dict(self) -> dict:
        """导出为 node-link 字典（可 JSON 序列化）"""
        return nx.node_link_data(self.graph, edges="links")

    def get_summary(self) -> str:
        """获取拓扑摘要"""
        lines = [
            f"节点总数: {self.graph.number_of_nodes()}",
            f"连接总数: {self.graph.number_of_edges()}",
            f"根节点 TEI: {self.get_root()}",
        ]
        roles = {}
        for _, attr in self.graph.nodes(data=True):
            r = attr.get('role', '未知')
            roles[r] = roles.get(r, 0) + 1
        for r, c in sorted(roles.items()):
            lines.append(f"  {r}: {c}")
        max_level = max((attr.get('level', 0) for _, attr in self.graph.nodes(data=True)), default=0)
        lines.append(f"最大层级: {max_level}")
        return "\n".join(lines)


# ========================================================================
# 4. 演示输出
# ========================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("【南网拓扑】")
    print("=" * 70)

    # --- 查询帧 ---
    south_query_data = struct.pack('<H', 0) + struct.pack('B', 50)
    south_query = build_south_frame(0xE8, 0x03, 0x03, 0x65, data=south_query_data)
    print(f"\n1. 南网拓扑查询原始帧 (DI=E8 03 03 65, start=0, count=50):")
    print(f"   HEX: {south_query.hex().upper()}")
    print(f"   长度: {len(south_query)} 字节")
    print(f"   帧结构: 68 | L(2B) | C(40) | AFN(E8) | SEQ(00) | DI(65 03 03 E8) | 数据区(00 00 32) | CS | 16")
    print(f"   说明: DIR=0(下行), PRM=1(启动站), ADD=0(无地址域)")

    # --- 模拟响应节点 ---
    south_demo_nodes = [
        {'addr': '000000000001', 'tei': 1, 'proxy_tei': 1, 'level': 0, 'role': 'CCO', 'channel': '载波'},
        {'addr': '000000000002', 'tei': 2, 'proxy_tei': 1, 'level': 1, 'role': 'PCO', 'channel': '载波'},
        {'addr': '000000000003', 'tei': 3, 'proxy_tei': 1, 'level': 1, 'role': 'STA', 'channel': '无线'},
        {'addr': '000000000004', 'tei': 4, 'proxy_tei': 2, 'level': 2, 'role': 'STA', 'channel': '载波'},
        {'addr': '000000000005', 'tei': 5, 'proxy_tei': 2, 'level': 2, 'role': 'STA', 'channel': '载波'},
    ]

    south_resp_data = struct.pack('<H', len(south_demo_nodes))
    south_resp_data += struct.pack('<H', 0)
    south_resp_data += struct.pack('B', len(south_demo_nodes))
    for node in south_demo_nodes:
        south_resp_data += bytes.fromhex(node['addr'])[::-1]
        south_resp_data += struct.pack('<H', node['tei'])
        south_resp_data += struct.pack('<H', node['proxy_tei'])
        south_resp_data += b'\x00' * 8
        info = (node['level'] & 0x0F)
        role_map = {'STA': 1, 'PCO': 2, 'CCO': 4}
        info |= (role_map.get(node['role'], 1) << 4)
        if node.get('channel') == '无线':
            info |= 0x80
        south_resp_data += struct.pack('B', info)

    south_resp = build_south_frame(0xE8, 0x04, 0x03, 0x65,
                                   data=south_resp_data, dir_flag=1, prm=0)
    print(f"\n2. 南网拓扑响应原始帧 (DI=E8 04 03 65, 含 {len(south_demo_nodes)} 个节点):")
    print(f"   HEX: {south_resp.hex().upper()}")
    print(f"   长度: {len(south_resp)} 字节")
    print(f"   帧结构: 68 | L(2B) | C(C0) | AFN(E8) | SEQ(00) | DI(65 03 04 E8) | 数据区({len(south_resp_data)}B) | CS | 16")
    print(f"   说明: DIR=1(上行), PRM=0(从动站)")

    south_data_area = extract_south_data_area(south_resp)
    parsed_south = parse_south_topology(south_data_area)
    print(f"\n3. 解析后的节点内容:")
    for n in parsed_south:
        print(f"   TEI={n['tei']:2d} | 地址={n['addr']} | 代理={n['proxy_tei']:2d} | "
              f"层级={n['level']} | 角色={n['role']:3s} | 信道={n['channel']}")

    print("\n" + "=" * 70)
    print("【国网拓扑】")
    print("=" * 70)

    # --- 查询帧 ---
    gdw_query = build_gdw_query_frame(fn=21, start_seq=1, query_count=50)
    print(f"\n1. 国网拓扑查询原始帧 (AFN=10, F21, start=1, count=50):")
    print(f"   HEX: {gdw_query.hex().upper()}")
    print(f"   长度: {len(gdw_query)} 字节")
    print(f"   帧结构: 68 | L(2B) | C | INFO(6B) | AFN(10) | DT(20 02) | 数据区 | CS | 16")
    print(f"   说明: 信息域6字节，通信模块标识=0(无地址域)")

    gdw_demo_nodes = [
        {'addr': '000000000001', 'tei': 1, 'proxy_tei': 1, 'level': 0, 'role': 'CCO'},
        {'addr': '000000000002', 'tei': 2, 'proxy_tei': 1, 'level': 1, 'role': 'PCO'},
        {'addr': '000000000003', 'tei': 3, 'proxy_tei': 1, 'level': 1, 'role': 'STA'},
        {'addr': '000000000004', 'tei': 4, 'proxy_tei': 2, 'level': 2, 'role': 'STA'},
    ]

    gdw_resp = build_gdw_response_frame(fn=21, nodes=gdw_demo_nodes)
    print(f"\n2. 国网拓扑响应原始帧 (AFN=10, F21, 含 {len(gdw_demo_nodes)} 个节点):")
    print(f"   HEX: {gdw_resp.hex().upper()}")
    print(f"   长度: {len(gdw_resp)} 字节")

    gdw_data_unit = extract_gdw_data_unit(gdw_resp)
    parsed_gdw = parse_gdw_topology(gdw_data_unit)
    print(f"\n3. 解析后的节点内容:")
    for n in parsed_gdw:
        print(f"   TEI={n['tei']:2d} | 地址={n['addr']} | 代理={n['proxy_tei']:2d} | "
              f"层级={n['level']} | 角色={n['role']:3s}")

    print("\n" + "=" * 70)
    print("【NetworkX 拓扑图存储】")
    print("=" * 70)

    # 使用南网数据构建 networkx 图
    topo = TopologyGraph()
    topo.add_nodes_from_raw(parsed_south)

    print(f"\n1. 拓扑摘要:")
    print(topo.get_summary())

    print(f"\n2. 节点到根节点的路径:")
    root = topo.get_root()
    for tei in sorted(topo.graph.nodes):
        path = topo.get_path_to_root(tei)
        path_str = " -> ".join(str(x) for x in path)
        print(f"   TEI {tei}: {path_str}")

    print(f"\n3. 层级分布:")
    for lv in range(3):
        ns = topo.get_nodes_by_level(lv)
        if ns:
            print(f"   第 {lv} 层: TEI={sorted(ns)}")

    print(f"\n4. 子树查询 (TEI={root} 的子树):")
    subtree = topo.get_subtree_nodes(root)
    print(f"   包含节点: TEI={sorted(subtree)}")

    print(f"\n5. 导出为 node-link 数据 (JSON 可序列化):")
    data = topo.export_dict()
    print(f"   nodes: {len(data['nodes'])}, links: {len(data['links'])}")
    for link in data['links']:
        print(f"   边: {link['source']} -> {link['target']} (relation={link.get('relation')})")

    print(f"\n6. 父子关系查询:")
    for tei in sorted(topo.graph.nodes):
        parent = topo.get_parent(tei)
        children = topo.get_children(tei)
        parent_str = f"父={parent}" if parent >= 0 else "父=无(根节点)"
        children_str = f"子={children}" if children else "子=无(叶子)"
        print(f"   TEI {tei}: {parent_str} | {children_str}")
