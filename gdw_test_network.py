# -*- coding: utf-8 -*-
"""国网协议测试页（协议7）—— **组网参数 / 字段语义绑定 / 从节点展开**（纯逻辑，零 Qt）。

设计要点
--------
用户要用「1 个 CCO + 2 个虚拟从节点」组成 1 对 2 网络做 AFN 遍历测试，因此：

1. **组网参数是一等公民**：:class:`NetworkConfig` 持有 1~2 个 :class:`SlaveNode`（地址 + 协议类型）
   以及 CCO 地址、载波频段、无线调制/信道/协商。全部随存档落盘，供每条命令复用。
2. **绑定按字段名语义，不按命令硬编码**：同一个「通信对象地址」出现在 52H F1 / 52H F11 /
   13H F1 等命令里，字段名一致就自动吃到同一个值 —— 新增命令无需改本模块。
   ``BIND_RULES`` 是唯一事实来源，测试按它逐条反证。
3. **手改优先**：调用方把「用户显式改过的字段名」传进 :func:`apply_binding`，这些字段一律不覆盖，
   避免自动填充把临时调试值冲掉（用户口径：手改优先）。
4. **节点展开只认「单节点地址」字段**：命令里只有单个「通信对象地址 / 从节点地址」时，
   1 对 2 就得按节点各发一帧（:func:`is_node_scoped`）；而「从节点列表」这类列表字段
   （11H F1 添加从节点）是一条帧里放两个节点，**不展开**。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import re

# ── 协议类型（与 11H F1 的「通信协议类型」枚举逐字对齐，单一来源）─────────
PROTO_TRANSPARENT = 0
PROTO_645_1997 = 1
PROTO_645_2007 = 2
PROTO_698_45 = 3

PROTO_LABELS: Dict[int, str] = {
    PROTO_TRANSPARENT: "透明传输",
    PROTO_645_1997: "DL/T 645-1997",
    PROTO_645_2007: "DL/T 645-2007",
    PROTO_698_45: "DL/T 698.45",
}

#: 载波频段（与 05H F16「宽带载波频段」枚举逐字对齐）
CARRIER_BANDS: Dict[int, str] = {
    0: "1.953~11.96MHz",
    1: "2.441~5.615MHz",
    2: "0.781~2.930MHz",
    3: "1.758~2.930MHz",
}
#: 无线调制方式（与 05H F17「无线调制方式」枚举对齐）
RADIO_MODS: Dict[int, str] = {2: "500kHz", 3: "200kHz"}

MAX_SLAVES = 2
ADDR_LEN = 12

# ── 字段语义 → 数据源 ──────────────────────────────────────────────────
# 键是「字段名精确匹配」，值是数据源代号；变量：node（当前展开的节点）。
# 只用精确名而不是包含匹配 —— 例如「从节点数量」不能被当成地址字段。
FIELD_NODE_ADDR = "通信对象地址"
FIELD_TARGET_ADDR = "目标地址"
FIELD_SLAVE_ADDR = "从节点地址"
FIELD_NODE_LIST = "从节点列表"
FIELD_SUB_LIST = "从节点附属节点列表"
FIELD_CCO = "主节点地址"
FIELD_BAND = "宽带载波频段"
FIELD_RADIO_MOD = "无线调制方式"
FIELD_RADIO_CH = "无线信道编号"
FIELD_RADIO_NEG = "信道协商使能"
FIELD_PROTO = "通信协议类型"
FIELD_PROTO_SHORT = "规约类型"

#: 单节点地址字段 —— 命中即「按节点展开」。
SINGLE_NODE_FIELDS = (FIELD_NODE_ADDR, FIELD_SLAVE_ADDR, FIELD_TARGET_ADDR)

#: 绑定规则：(字段名, 数据源, 目标类型)
#: 数据源：``node_addr`` / ``node_proto`` / ``cco`` / ``band`` / ``radio_mod`` /
#: ``radio_ch`` / ``radio_neg`` / ``node_list`` / ``node_list_addr_only`` / ``sub_list``
BIND_RULES: Tuple[Tuple[str, str], ...] = (
    (FIELD_NODE_ADDR, "node_addr"),
    (FIELD_TARGET_ADDR, "node_addr"),
    (FIELD_SLAVE_ADDR, "node_addr"),
    (FIELD_NODE_LIST, "node_list"),
    (FIELD_SUB_LIST, "sub_list"),
    (FIELD_CCO, "cco"),
    (FIELD_BAND, "band"),
    (FIELD_RADIO_MOD, "radio_mod"),
    (FIELD_RADIO_CH, "radio_ch"),
    (FIELD_RADIO_NEG, "radio_neg"),
    (FIELD_PROTO, "node_proto"),
    (FIELD_PROTO_SHORT, "node_proto"),
)


def proto_label(proto: int) -> str:
    return PROTO_LABELS.get(int(proto), f"协议{proto}")


def addr_ok(text: str) -> bool:
    t = (text or "").strip()
    return len(t) == ADDR_LEN and t.isdigit()


def normalize_addr(text: str) -> str:
    """12 位十进制地址；不足左补 0，非数字返回空串（不猜）。"""
    t = "".join(ch for ch in (text or "").strip() if not ch.isspace())
    if not t:
        return ""
    if not t.isdigit() or len(t) > ADDR_LEN:
        return ""
    return t.rjust(ADDR_LEN, "0")


@dataclass
class SlaveNode:
    """一个被测从节点（虚拟表）。"""

    addr: str = ""
    proto: int = PROTO_645_2007
    enabled: bool = True

    def normalized(self) -> "SlaveNode":
        return replace(self, addr=normalize_addr(self.addr), proto=int(self.proto or 0))

    def valid(self) -> bool:
        return addr_ok(self.addr)

    def label(self) -> str:
        if not self.addr:
            return "（未填地址）"
        return f"{self.addr}（{proto_label(self.proto)}）"

    def as_dict(self) -> Dict[str, Any]:
        return {"addr": self.addr, "proto": int(self.proto), "enabled": bool(self.enabled)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlaveNode":
        try:
            proto = int(data.get("proto") or 0)
        except (TypeError, ValueError):
            proto = PROTO_645_2007
        if proto not in PROTO_LABELS:
            proto = PROTO_645_2007
        return cls(addr=str(data.get("addr") or ""), proto=proto,
                   enabled=bool(data.get("enabled", True)))


@dataclass
class NetworkConfig:
    """组网参数：1~2 个从节点 + CCO / 载波 / 无线。"""

    slaves: List[SlaveNode] = field(default_factory=lambda: [SlaveNode(), SlaveNode()])
    cco_addr: str = ""
    carrier_band: int = 0
    radio_mod: int = 2
    radio_channel: int = 1
    radio_negotiate: int = 1
    #: 组帧时把组网参数填进未手改的字段
    auto_fill: bool = True
    #: 单节点地址类命令按启用的从节点各发一帧
    fanout: bool = True

    # ── 节点 ──────────────────────────────────────────────────────────
    def active_slaves(self) -> List[SlaveNode]:
        """启用且地址合法的从节点（组帧只能用这些）。"""
        return [n for n in self.slaves if n.enabled and n.valid()]

    def all_slaves(self) -> List[SlaveNode]:
        return [n for n in self.slaves if n.valid()]

    def nodes_or_placeholder(self) -> List[SlaveNode]:
        """统计用：启用但地址没填也占一行，便于看出「配了但没测」。"""
        out = [n for n in self.slaves if n.enabled]
        return out

    def find_slave(self, addr: str) -> Optional[SlaveNode]:
        for node in self.slaves:
            if node.addr and node.addr == addr:
                return node
        return None

    # ── 序列化 ────────────────────────────────────────────────────────
    def as_dict(self) -> Dict[str, Any]:
        return {
            "slaves": [n.as_dict() for n in self.slaves],
            "cco_addr": self.cco_addr,
            "carrier_band": int(self.carrier_band),
            "radio_mod": int(self.radio_mod),
            "radio_channel": int(self.radio_channel),
            "radio_negotiate": int(self.radio_negotiate),
            "auto_fill": bool(self.auto_fill),
            "fanout": bool(self.fanout),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NetworkConfig":
        raw_slaves = data.get("slaves")
        slaves: List[SlaveNode] = []
        if isinstance(raw_slaves, list):
            for item in raw_slaves[:MAX_SLAVES]:
                if isinstance(item, Mapping):
                    slaves.append(SlaveNode.from_dict(item))
        while len(slaves) < MAX_SLAVES:
            slaves.append(SlaveNode())
        net = cls(slaves=slaves)
        net.cco_addr = str(data.get("cco_addr") or "")
        for name, table in (("carrier_band", CARRIER_BANDS), ("radio_mod", RADIO_MODS)):
            try:
                value = int(data.get(name, 0))
            except (TypeError, ValueError):
                value = 0
            setattr(net, name, value if value in table else next(iter(table)))
        for name in ("radio_channel", "radio_negotiate"):
            try:
                setattr(net, name, int(data.get(name, 1)))
            except (TypeError, ValueError):
                setattr(net, name, 1)
        net.auto_fill = bool(data.get("auto_fill", True))
        net.fanout = bool(data.get("fanout", True))
        return net


# ── 字段判定 ────────────────────────────────────────────────────────────
def _field_name(fld: Mapping[str, Any]) -> str:
    return str(fld.get("name") or "")


def bind_source(field_name: str) -> Optional[str]:
    """字段名 → 绑定数据源代号（无绑定返回 None）。"""
    for name, source in BIND_RULES:
        if field_name == name:
            return source
    return None


def is_node_scoped(cmd: Any) -> bool:
    """命令是否需要按从节点逐帧发送（含单个节点地址字段）。"""
    for fld in getattr(cmd, "fields", ()) or ():
        if _field_name(fld) in SINGLE_NODE_FIELDS:
            return True
    return False


def bound_fields(cmd: Any) -> List[str]:
    return [str(f.get("name")) for f in (getattr(cmd, "fields", ()) or ())
            if bind_source(str(f.get("name")))]


# ── 绑定取值 ────────────────────────────────────────────────────────────
def _list_rows(nodes: Sequence[SlaveNode], with_proto: bool,
               item_names: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """节点集合 → 列表字段的行。

    行的键**必须**取该列表字段的 `item_fields` 名（`14H F1` 是「从节点附属节点地址」、
    `11H F1` 是「从节点地址」），否则生成器按 item 名取不到值会静默回落到默认地址，
    帧里的地址全成 0（已踩过）。地址类 item 一律吃节点地址，协议类 item 吃节点协议。
    """
    names = [str(n) for n in (item_names or ())]
    if not names:
        names = [FIELD_SLAVE_ADDR] + ([FIELD_PROTO] if with_proto else [])
    rows: List[Dict[str, Any]] = []
    for node in nodes:
        row: Dict[str, Any] = {}
        for iname in names:
            if iname in (FIELD_PROTO, FIELD_PROTO_SHORT):
                row[iname] = node.proto
            elif iname.endswith("地址"):
                row[iname] = node.addr
        rows.append(row)
    return rows


def _value_for(source: str, net: NetworkConfig, node: Optional[SlaveNode],
               field_name: str, with_proto: bool,
               item_names: Sequence[str] = ()) -> Any:
    if source == "node_addr":
        return node.addr if node is not None else ""
    if source == "node_proto":
        return node.proto if node is not None else net.slaves[0].proto
    if source == "cco":
        return net.cco_addr
    if source == "band":
        return int(net.carrier_band)
    if source == "radio_mod":
        return int(net.radio_mod)
    if source == "radio_ch":
        return int(net.radio_channel)
    if source == "radio_neg":
        return int(net.radio_negotiate)
    if source == "node_list":
        return _list_rows(net.active_slaves(), with_proto=True, item_names=item_names)
    if source == "sub_list":
        return _list_rows(net.active_slaves(), with_proto=False, item_names=item_names)
    return None


def apply_binding(values: Mapping[str, Any], cmd: Any, net: NetworkConfig,
                  node: Optional[SlaveNode] = None,
                  dirty: Iterable[str] = ()) -> Tuple[Dict[str, Any], List[str]]:
    """把组网参数填进命令字段。

    - 只在 ``net.auto_fill`` 打开时生效；
    - ``dirty`` 里的字段名视为用户手改，**不覆盖**（手改优先）；
    - 只填命令 schema 里真实存在的字段，避免把值塞进不认识的键；
    - 返回 ``(新 values, 实际填充的字段名列表)``，便于界面标注「自动」。
    """
    out = dict(values or {})
    applied: List[str] = []
    if not net.auto_fill:
        return out, applied
    names = [_field_name(f) for f in (getattr(cmd, "fields", ()) or ())]
    dirty_set = set(dirty or ())
    for fld in getattr(cmd, "fields", ()) or ():
        name = _field_name(fld)
        source = bind_source(name)
        if source is None or name in dirty_set:
            continue
        # 列表字段的 item_fields 决定要不要带协议类型
        item_names = [str(i.get("name")) for i in (fld.get("item_fields") or ())]
        with_proto = FIELD_PROTO in item_names
        value = _value_for(source, net, node, name, with_proto, item_names)
        if value is None:
            continue
        # 单节点地址字段：没有节点可填就跳过（不写空值）
        if source == "node_addr" and not value:
            continue
        if source == "cco" and not value:
            continue
        if source in ("node_list", "sub_list") and not value:
            continue
        if name not in names:
            continue
        out[name] = value
        applied.append(name)
    return out, applied


def is_uplink(cmd: Any) -> bool:
    """上行帧（只接收、不下发）：显式 direction=up 才算。"""
    return str(getattr(cmd, "direction", "") or "").strip().lower() == "up"


def plan_targets(keys: Iterable[Tuple[str, str]], find_cmd, net: NetworkConfig
                 ) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """把勾选清单展开成发送计划。

    返回 ``(plan, skipped)``：

    - ``plan`` = ``(page, key, node_addr)``：真正要下发的帧；
    - ``skipped`` = ``(page, key)``：勾选里混进来的**上行命令**（确认/否认应答、主动上报），
      由被测设备自己发出，测试系统只接收 —— 不下发、不给支持结论（下发属测试方法错误）。

    - ``net.fanout`` 关闭时一律单发（``node_addr=""``）；
    - 命中单节点地址字段的下行命令，按启用的从节点各一条；
    - 没有可用从节点时退化为单发，避免一条都发不出去。
    """
    nodes = net.active_slaves() if net.fanout else []
    plan: List[Tuple[str, str, str]] = []
    skipped: List[Tuple[str, str]] = []
    for page, key in keys:
        cmd = find_cmd(key) if find_cmd is not None else None
        if cmd is not None and is_uplink(cmd):
            skipped.append((page, key))
            continue
        if nodes and cmd is not None and is_node_scoped(cmd):
            plan.extend((page, key, node.addr) for node in nodes)
        else:
            plan.append((page, key, ""))
    return plan, skipped


def summary_env(net: NetworkConfig) -> List[Tuple[str, str]]:
    """报告/界面用的组网摘要（键值对，顺序稳定）。"""
    rows: List[Tuple[str, str]] = [("CCO 地址", net.cco_addr or "（未设置）")]
    for idx, node in enumerate(net.slaves, start=1):
        state = "" if node.enabled else "（未启用）"
        rows.append((f"从节点 {idx}", (node.label() if node.addr else "（未填写）") + state))
    rows.append(("载波频段", f"{net.carrier_band} {CARRIER_BANDS.get(net.carrier_band, '')}"))
    rows.append(("无线调制方式", f"{net.radio_mod} {RADIO_MODS.get(net.radio_mod, '')}"))
    rows.append(("无线信道编号", str(net.radio_channel)))
    rows.append(("信道协商使能", "允许" if net.radio_negotiate else "禁止"))
    return rows


# ── 前置流程：初始化 → 建档 → 核对档案 → 查拓扑判入网 ──────────────────
#: 前置流程用到的命令（key 与 ``core.GdwCommand.key`` 一致）
PREFLIGHT_INIT = "01-2"            # 01H F2 参数区初始化（清掉旧档案，否则 11H F1 回「表号重复」）
PREFLIGHT_ADD_NODES = "11-1"      # 11H F1 添加从节点（给被测 CCO 建档）
PREFLIGHT_NODE_COUNT = "10-1"      # 10H F1 从节点数量（模块档案总数）
PREFLIGHT_NODE_INFO = "10-2"       # 10H F2 从节点信息（只用来核对档案是否加对）
PREFLIGHT_TOPOLOGY = "10-20"       # 10H F20 查询双模网络拓扑信息（**入网判据**）

#: 前置流程默认查询的从节点数量上限（10H F2 一帧最多 64）
PREFLIGHT_QUERY_MAX = 64


def _field_names(cmd: Optional[Any]) -> List[str]:
    return [str(getattr(f, "name", "")) if not isinstance(f, Mapping) else str(f.get("name", ""))
            for f in (getattr(cmd, "fields", ()) or ())]


def _range_overrides(key: str, start: int, count: int,
                     find_cmd: Optional[Any], default_start: str, default_count: str
                     ) -> Dict[str, Any]:
    """按 schema 实际字段名生成「起始序号 + 数量」覆盖值。

    字段名不能硬编码：`10H F2` 是「从节点起始序号/从节点数量」，而 `10H F20` 是
    「节点起始序号/节点数量」，写死会覆盖不到、帧里数量恒为默认 1。
    """
    names: List[str] = []
    if find_cmd is not None:
        try:
            names = _field_names(find_cmd(key))
        except Exception:
            names = []
    start_name = next((n for n in names if "起始序号" in n), default_start)
    count_name = next((n for n in names if n.endswith("数量")), default_count)
    return {start_name: start, count_name: count}


def _preflight_add_nodes_overrides(archive: Sequence[SlaveNode]) -> Dict[str, Any]:
    """建档（`11H F1 添加从节点`）的显式覆盖值。

    **必须显式给**（1.26.8 修）：此前建档帧的从节点列表只靠界面「按组网参数自动填充」
    开关兜底 —— 开关被关掉（或存档里存的是关闭态）时，会发出「数量=0、没有地址」
    的空档案帧，被测 CCO 一遍空跑，现场表现为「建档成功但一块表都没进去」。

    字段名照 schema：`从节点数量` + `从节点列表[{从节点地址, 通信协议类型}]`；
    地址 6 字节低字节在前，协议类型取该从节点在组网参数里选的协议。
    """
    items = [{"从节点地址": node.addr, "通信协议类型": int(node.proto)}
             for node in archive if node.addr]
    if not items:
        return {}
    return {"从节点数量": len(items), "从节点列表": items}


def _preflight_query_overrides(archive: Sequence[SlaveNode], find_cmd: Optional[Any] = None
                               ) -> Dict[str, Dict[str, Any]]:
    """前置流程的覆盖值。

    - `11H F1`：建档内容（数量 + 地址/协议列表），**不依赖自动填充开关**；
    - `10H F2`：从节点起始序号 1、数量 = 档案个数（核对档案）；
    - `10H F20`：节点起始序号 **1**（拓扑里 1 = 主节点/CCO）、数量 = 1 + 档案个数（判入网）。
    """
    count = max(1, min(len(archive), PREFLIGHT_QUERY_MAX))
    topo_count = max(1, min(len(archive) + 1, PREFLIGHT_QUERY_MAX))
    overrides = {
        PREFLIGHT_NODE_INFO: _range_overrides(
            PREFLIGHT_NODE_INFO, 1, count, find_cmd, "从节点起始序号", "从节点数量"),
        PREFLIGHT_TOPOLOGY: _range_overrides(
            PREFLIGHT_TOPOLOGY, 1, topo_count, find_cmd, "节点起始序号", "节点数量"),
    }
    add_nodes = _preflight_add_nodes_overrides(archive)
    if add_nodes:
        overrides[PREFLIGHT_ADD_NODES] = add_nodes
    return overrides


def build_preflight(net: NetworkConfig, find_cmd: Optional[Any] = None
                    ) -> Tuple[List[Tuple[str, str, str]], Dict[str, Dict[str, Any]], List[str]]:
    """前置流程的发送计划。

    返回 ``(targets, overrides, notes)``：

    - ``targets``：依次 **参数区初始化** → 添加从节点（建档）→ 查从节点信息（**只核对档案**）
      → 查双模拓扑（**判入网**）；
    - ``overrides``：按 key 覆盖查询范围（F2 用「从节点…」字段名，F20 用「节点…」字段名）；
    - ``notes``：给日志/界面用的人话说明。

    **必须先初始化**（用户口径）：参数区初始化会清掉模块里已有的表档案，否则随后
    `11H F1 添加从节点` 会因为表号已在档案里而回「否认（错误状态字=6 表号重复）」。
    入网结论只看 `10H F20`：模块档案里有某表 ≠ 该表已入网。
    没有可用从节点档案时返回空计划 —— 建档命令本身就没东西可发。
    """
    archive = net.active_slaves()
    if not archive:
        return [], {}, ["组网参数里没有启用的从节点（12 位地址），无法建档"]
    count = max(1, min(len(archive), PREFLIGHT_QUERY_MAX))
    topo_count = max(1, min(len(archive) + 1, PREFLIGHT_QUERY_MAX))
    targets: List[Tuple[str, str, str]] = [
        ("cmd", PREFLIGHT_INIT, ""),        # 参数区初始化：清旧档案，避免「表号重复」
        ("cmd", PREFLIGHT_ADD_NODES, ""),   # 建档：列表/数量由组网参数自动填
        ("cmd", PREFLIGHT_NODE_COUNT, ""),  # 查模块档案总数
        ("cmd", PREFLIGHT_NODE_INFO, ""),   # 核对档案明细（含表地址）
        ("cmd", PREFLIGHT_TOPOLOGY, ""),    # 查拓扑：入网判据
    ]
    overrides = _preflight_query_overrides(archive, find_cmd)
    notes = [
        "① 01H F2 参数区初始化：会清掉模块里已有的表档案（及参数区），"
        "这样 11H F1 才不会回「表号重复」",
        f"② 建档 {len(archive)} 个：" + "、".join(n.addr for n in archive),
        f"③ 查从节点信息（核对档案）：起始序号 1，数量 {count}",
        f"④ 查双模拓扑（判入网）：起始序号 1（1=CCO），数量 {topo_count}",
    ]
    return targets, overrides, notes


def topology_addrs_from_rows(rows: Sequence[Tuple]) -> List[str]:
    """从 10H F20 上行解析行里取「节点N地址」，只保留角色有效的节点。

    `10H F20` 上行为「节点总数量(2B) + 节点起始序号(2B) + 本次应答数量(1B) +
    n×[节点地址(6B) + 网络拓扑信息(5B)]」；拓扑里角色=无效 的条目不算入网。

    注意字段名与 `10H F2` 不同（这里是「节点N…」，F2 是「从节点N…」）。
    """
    addrs: Dict[str, str] = {}
    roles: Dict[str, str] = {}
    for row in rows or ():
        if not row:
            continue
        name = str(row[0]).strip()
        m = re.match(r"^节点(\d+)地址$", name)
        if m:
            text = str(row[2] or row[1] or "").strip().upper()
            if len(text) == ADDR_LEN and text.isdigit():
                addrs[m.group(1)] = text
            continue
        m = re.match(r"^节点(\d+)节点角色$", name)
        if m:
            roles[m.group(1)] = str(row[2] or "").strip()

    joined: List[str] = []
    for idx, addr in addrs.items():
        role = roles.get(idx, "")
        if "无效" in role:            # 拓扑里有条目但角色无效 ⇒ 没真正入网
            continue
        if addr not in joined:
            joined.append(addr)
    return joined


def topology_detail(rows: Sequence[Tuple]) -> Dict[str, Dict[str, str]]:
    """10H F20 上行 → {地址: {角色, 层级, 信道}}，用于日志里给出入网证据。"""
    detail: Dict[str, Dict[str, str]] = {}
    order: Dict[str, str] = {}
    for row in rows or ():
        if not row:
            continue
        name = str(row[0]).strip()
        m = re.match(r"^节点(\d+)(地址|节点角色|节点层级|网络信道)$", name)
        if not m:
            continue
        idx, kind = m.group(1), m.group(2)
        value = str(row[2] or "").strip()
        if kind == "地址":
            order[idx] = value.upper()
            detail.setdefault(value.upper(), {})
        elif idx in order:
            key = {"节点角色": "角色", "节点层级": "层级", "网络信道": "信道"}[kind]
            detail[order[idx]][key] = value
    return detail


def archive_report(archive: Sequence[SlaveNode], seen: Sequence[str]) -> Dict[str, Any]:
    """档案核对（`10H F2` 上报的档案地址 vs 组网参数）。

    只说明「档案加没加对」，**不代表入网** —— 入网看 `10H F20` 拓扑。
    """
    wanted = [n.addr for n in archive if n.addr]
    seen_set = {str(a).strip().upper() for a in seen if a}
    in_archive = [a for a in wanted if a.upper() in seen_set]
    return {
        "archive": len(wanted),
        "matched": in_archive,
        "missing": [a for a in wanted if a.upper() not in seen_set],
        "extra": [a for a in seen_set if a.upper() not in {w.upper() for w in wanted}],
        "all_matched": bool(wanted) and len(in_archive) == len(wanted),
    }


def slave_addrs_from_rows(rows: Sequence[Tuple]) -> List[str]:
    """从 10H F2/F5/F6 上行解析行里取「从节点N地址」。

    解析器的行是 ``(字段名, 原始值, 解析值, 说明, 起, 止)``，地址解析值已按
    低字节在前还原成 12 位字符串（见 ``GDWFrameParser._format_addr``）。
    """
    found: List[str] = []
    for row in rows or ():
        if not row:
            continue
        name = str(row[0]).strip()
        if "地址" not in name or "从节点" not in name:
            continue
        for value in (row[2], row[1]):
            text = str(value or "").strip().upper()
            if len(text) == ADDR_LEN and all(ch in "0123456789" for ch in text):
                if text not in found:
                    found.append(text)
                break
    return found


def join_report(archive: Sequence[SlaveNode], seen: Sequence[str]) -> Dict[str, Any]:
    """档案 vs **10H F20 拓扑里的节点地址** → 入网判定。

    ``seen`` 必须来自拓扑（:func:`topology_addrs_from_rows`），不能来自 `10H F2`：
    F2 报的是模块里下装的档案，档案有 ≠ 该表已入网（用户口径）。

    ``joined`` 同时出现在档案与拓扑里；``missing`` 是档案有、拓扑没出现的（未入网）；
    ``extra`` 是拓扑里有、档案里没有的（现场残留节点）。
    """
    wanted = [n.addr for n in archive if n.addr]
    seen_set = {str(a).strip().upper() for a in seen if a}
    joined = [a for a in wanted if a.upper() in seen_set]
    missing = [a for a in wanted if a.upper() not in seen_set]
    extra = [a for a in seen_set if a.upper() not in {w.upper() for w in wanted}]
    return {
        "archive": len(wanted),
        "joined": joined,
        "missing": missing,
        "extra": extra,
        "all_joined": bool(wanted) and not missing,
    }

