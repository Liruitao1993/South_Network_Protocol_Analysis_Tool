# -*- coding: utf-8 -*-
"""DL/T 698.45（协议 8）**协议测试页**的预置测试库与组帧逻辑 —— 纯逻辑层，禁止 import Qt。

与「协议组帧」页的分工：组帧页是**临时、任意**的，字段随手填；本模块是**预先做好**的
测试项库 —— 按协议的对象标识（OI）分配把 777 个对象分成「电能量 / 需量 / 变量 / 事件 /
参变量 / 冻结数据 / 采集 / 文件与应用 / 控制 / 厂家扩展」十类，每项都带可直接下发的
OAD，供现场按类挑选、批量下发、逐条看回复。

分层
----
- 本模块：分类库（`catalog`）+ 组帧（`build_*`）+ 响应判定（`evaluate_response`）
- ``dlt698_test_widget``：只做界面与串口，不含任何 698 字节细节
- 帧的 HCS/FCS/地址域一律交 `dl_t698_45_frame_gen.DLT69845FrameGenerator`（本项目唯一
  FCS 实现）；SA 编码复用 `dl_t698_45_upgrade.build_sa`（唯一实现）—— **禁止**在别处
  再拼一份 ``68 … 16``（AGENTS §8 陷阱 31 的漂移根因）。

⚠ 顶层 import `dl_t698_45_frame_gen` / `dl_t698_45_parser`（二者顶层 import 可选依赖
``crcmod``）⇒ **GUI / 串口 / 蓝牙页不得顶层 import 本模块**，必须在动作方法内惰性 import，
把 ImportError 兜成「请 pip install crcmod」的提示（AGENTS 惰性 import 铁律）。

协议口径（逐字节自证于 ``test/test_dlt698_testbench.py`` 的 golden 段）
------------------------------------------------------------------------
链路层：``68 | L(2B 小端，L 不含首尾字节 ⇒ 整帧 = L+2) | 控制域 | SA | CA | HCS | APDU |
FCS | 16``。APDU 内 A-XDR 数据域**多字节一律大端**；两层字节序不互套。

- 读一个属性   GET-Request Normal   `05 01 PIID OAD 00`
  文档附录 H.3.1：读通信地址 = `05 01 01 40 01 02 00 00`
- 读多个属性   GET-Request Normal-List  `05 02 PIID 个数 OAD×n 00`
  文档附录 H.3.2：`05 02 02 02 20 00 02 00 20 01 02 00 00`
- 读记录型属性 GET-Request Record   `05 03 PIID OAD RSD RCSD 00`
  文档附录 H.3.3：`05 03 03 50 04 02 00 01 20 21 02 00 1C 07 E0 01 14 00 00 00
  02 00 20 21 02 00 00 00 10 02 00 00`
- 设置一个属性 SET-Request Normal   `06 01 PIID OAD Data 00`
  文档附录 H.4.1：`06 01 02 40 00 02 00 1C 07 E0 01 14 10 1B 0B 00`
- 操作一个方法 ACTION-Request Normal  `07 01 PIID OMD Data 00`
  文档附录 H.5.1：`07 01 05 00 10 01 00 0F 00 00`
- 建立应用连接 CONNECT-Request      `02 PIID …`
  文档附录 H.2：`02 00 00 10 FF×8 FF×15 04 00 04 00 01 04 00 00 00 00 64 00 00`

PIID（§7.3.3 表6）：bit7 = 服务优先级（0 普通 / 1 高），bit6 = 保留，bit0~5 = 服务序号
（0~63）。响应里的 PIID-ACD 把 bit6 换成 ACD 标志。

``date_time_s``（类型 28）：``1C`` + 年(2B 大端) 月 日 时 分 秒 = tag + 7 字节，**无长度域**。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from dl_t698_45_frame_gen import DLT69845FrameGenerator
from dl_t698_45_oi_lookup import OILookup
from dl_t698_45_parser import DLT69845Parser
from dl_t698_45_upgrade import build_sa as _build_sa

# ─── 常用 OAD（协议文档附录 H 的实例）───────────────────────────────────────
OAD_ADDRESS = bytes.fromhex("40010200")      # OI 0x4001 通信地址 · 属性2 参数
OAD_DATETIME = bytes.fromhex("40000200")     # OI 0x4000 日期时间 · 属性2 参数
OAD_VERSION = bytes.fromhex("43000300")      # OI 0x4300 电气设备 · 属性3 版本信息

#: 广播地址（服务器地址特征字节 0xAA，1 字节，无地址体）
BROADCAST_SA = bytes([0xAA])
#: 通配地址：特征 0x45（单地址类型/逻辑0/长度6）+ AA×6
WILDCARD_SA = bytes.fromhex("45AAAAAAAAAAAA")

#: 各服务的 APDU 服务码（Client-APDU / Server-APDU 的 CHOICE 标签）
SERVICE_CONNECT_REQ = 0x02
SERVICE_CONNECT_RSP = 0x82
SERVICE_GET_REQ = 0x05
SERVICE_GET_RSP = 0x85
SERVICE_SET_REQ = 0x06
SERVICE_SET_RSP = 0x86
SERVICE_ACTION_REQ = 0x07
SERVICE_ACTION_RSP = 0x87
SERVICE_REPORT_RSP = 0x08
SERVICE_REPORT_NOTIFY = 0x88
SERVICE_ERROR_RSP = 0xEE

#: 帧尾「没有时间标签」字节（TimeTag OPTIONAL 的缺省编码，现场设备一律用这个）
TIME_TAG_NONE = b"\x00"

#: 结果枚举：信息表「结果」列的取值
RESULT_PENDING = "等待中"
RESULT_OK = "成功"
RESULT_FAIL = "失败"
RESULT_TIMEOUT = "超时"


# ═══════════════════════════════════════════════════════════════════════════
# 一、对象分类库（依据 OI 高字节分配 + 接口类，见协议文档附录 A）
# ═══════════════════════════════════════════════════════════════════════════

#: 顶层分类的展示顺序（与协议对象标识的分配顺序一致）
TOP_ORDER: Tuple[str, ...] = (
    "电能量", "需量", "变量", "事件", "参变量",
    "冻结数据", "采集", "文件与应用", "控制", "厂家扩展",
)

#: OI 高字节 → (顶层分类, 子分类名)。子分类名取自该类对象的实际语义
#: （逐条核对过 `OILookup.OI_NAME_MAP` 的成员，不是按命名猜的）：
#: 0x00~0x05 是电能量的 6 个分量、0x10/0x11 是需量的当前/冻结周期内、
#: 0x30~0x37 是事件的分项、0x40~0x49 是参变量的分组、0xF0~0xF4 是厂家扩展。
HBYTE_INFO: Dict[int, Tuple[str, str]] = {
    0x00: ("电能量", "总电能"),
    0x01: ("电能量", "基波电能"),
    0x02: ("电能量", "谐波电能"),
    0x03: ("电能量", "铜损补偿"),
    0x04: ("电能量", "铁损补偿"),
    0x05: ("电能量", "关联电能"),
    0x10: ("需量", "当前需量"),
    0x11: ("需量", "冻结周期内需量"),
    0x20: ("变量", "测量值"),
    0x21: ("变量", "统计值"),
    0x22: ("变量", "设备信息"),
    0x23: ("变量", "总加组"),
    0x24: ("变量", "脉冲计量"),
    0x25: ("变量", "水气热量"),
    0x26: ("变量", "状态量与环境量"),
    0x27: ("变量", "充电桩"),
    0x28: ("变量", "发电"),
    0x30: ("事件", "电能表事件"),
    0x31: ("事件", "终端事件"),
    0x32: ("事件", "功控电控记录"),
    0x33: ("事件", "事件单元"),
    0x34: ("事件", "充电事件"),
    0x35: ("事件", "遥信遥测事件"),
    0x36: ("事件", "系统监测事件"),
    0x37: ("事件", "锁具事件"),
    0x40: ("参变量", "通用参数"),
    0x41: ("参变量", "计量参数"),
    0x42: ("参变量", "校时"),
    0x43: ("参变量", "设备管理"),
    0x44: ("参变量", "应用连接与安全"),
    0x45: ("参变量", "通信模块"),
    0x46: ("参变量", "充电控制"),
    0x47: ("参变量", "台区与充电服务"),
    0x48: ("参变量", "电器设备数据"),
    0x49: ("参变量", "监控单元"),
    0x50: ("冻结数据", "冻结"),
    0x60: ("采集", "采集档案"),
    0x70: ("文件与应用", "文件与脚本"),
    0x71: ("文件与应用", "扩展变量"),
    0x72: ("文件与应用", "充电计划"),
    0x73: ("文件与应用", "应用与软件比对"),
    0x80: ("控制", "远程控制"),
    0x81: ("控制", "终端参数"),
    0x82: ("控制", "遥控"),
    0xF0: ("厂家扩展", "文件传输"),
    0xF1: ("厂家扩展", "安全与ESAM"),
    0xF2: ("厂家扩展", "输入输出设备"),
    0xF3: ("厂家扩展", "显示"),
    0xF4: ("厂家扩展", "应用与日志"),
}

#: 属性标识里「属性特征」高 3 位的说明（§7.3.5 OAD）
ATTR_FEATURE_TEXT: Dict[int, str] = {
    0: "属性",
    1: "记录型",
    2: "记录型（按时间）",
    3: "记录型（按上N次）",
    4: "数组元素",
}


@dataclass(frozen=True)
class OadItem:
    """一个可下发的测试对象（= OI + 该接口类的属性/方法表）。"""

    oi: int
    name: str
    class_id: int
    class_name: str
    attrs: Tuple[Tuple[int, str], ...]
    methods: Tuple[Tuple[int, str], ...]

    @property
    def default_attr(self) -> int:
        """默认属性号：优先 2（各类的「数值/数组/记录表」），没有就取第一个。"""
        ids = [a for a, _ in self.attrs]
        if 2 in ids:
            return 2
        return ids[0] if ids else 2

    @property
    def default_index(self) -> int:
        """默认元素索引：0 = 全部内容（§7.3.5）。"""
        return 0

    def oad(self, attr: Optional[int] = None, index: int = 0) -> bytes:
        return make_oad(self.oi, self.default_attr if attr is None else attr, index)

    def omd(self, method: int, mode: int = 0) -> bytes:
        return make_omd(self.oi, method, mode)

    def label(self) -> str:
        return f"{self.oi:04X}H {self.name}"

    def attr_name(self, attr: int) -> str:
        for aid, aname in self.attrs:
            if aid == attr:
                return aname
        return "未定义属性"

    def method_name(self, method: int) -> str:
        for mid, mname in self.methods:
            if mid == method:
                return mname
        return "未定义方法"

    def record_attrs(self) -> Tuple[Tuple[int, str], ...]:
        """可走 GET-Record 的属性（记录型）。

        判据：属性名含「表」/「记录」，或接口类本身就是记录型（事件 7/24、冻结 9、采集 10）。
        都没有 ⇒ **返回空**（该对象不进「读取记录」页）—— 早先的「兜底返回全部属性」会让
        记录页与属性页内容完全一样，用户分不出两页的差别。
        """
        out = []
        for aid, aname in self.attrs:
            if aid == 1:                       # 1 一律是逻辑名，不用于批量读表
                continue
            if ("表" in aname) or ("记录" in aname) or (self.class_id in (7, 9, 10, 24)):
                out.append((aid, aname))
        return tuple(out)


@dataclass(frozen=True)
class SubGroup:
    """子分类：一个 OI 高字节下的全部对象。"""

    name: str
    hbyte: int
    items: Tuple[OadItem, ...]


@dataclass(frozen=True)
class Category:
    """顶层分类（电能量 / 需量 / … / 厂家扩展）。"""

    name: str
    groups: Tuple[SubGroup, ...]

    def item_count(self) -> int:
        return sum(len(g.items) for g in self.groups)


def _item_from_oi(oi: int, name: str) -> OadItem:
    cls_id = int(OILookup.OI_TO_CLASS_ID.get(oi, 0) or 0)
    cls = OILookup.CLASS_ID_MAP.get(cls_id) or {}
    attrs = tuple(sorted((cls.get("attributes") or {}).items()))
    methods = tuple(sorted((cls.get("methods") or {}).items()))
    return OadItem(
        oi=oi,
        name=name,
        class_id=cls_id,
        class_name=str(cls.get("name") or "未知类"),
        attrs=attrs,
        methods=methods,
    )


@lru_cache(maxsize=1)
def catalog() -> Tuple[Category, ...]:
    """构建完整的测试对象分类树（进程内只建一次；777 项，约 10ms）。

    分类依据：OI 高字节（`HBYTE_INFO`）+ 接口类属性表（`OILookup.CLASS_ID_MAP`）。
    高字节未登记的 OI（协议后续新增）落到「厂家扩展 / 其它」，**不丢对象**。
    """
    buckets: Dict[Tuple[str, str], List[OadItem]] = {}
    for oi in sorted(OILookup.OI_NAME_MAP):
        name = str(OILookup.OI_NAME_MAP[oi])
        hb = (oi >> 8) & 0xFF
        top, sub = HBYTE_INFO.get(hb, ("厂家扩展", f"其它(0x{hb:02X}H)"))
        buckets.setdefault((top, sub), []).append(_item_from_oi(oi, name))

    out: List[Category] = []
    for top in TOP_ORDER:
        groups = []
        keys = [k for k in buckets if k[0] == top]

        def _hbyte_of(key) -> int:
            items = buckets[key]
            return (min(it.oi for it in items) >> 8) & 0xFF

        # 子类顺序 = OI 高字节顺序（0H→1H→…），不能按中文名排（Unicode 会把「关联」排到
        # 「总电能」前面，现场按 0H/1H 找项就对不上了）
        for _top, sub in sorted(keys, key=_hbyte_of):
            items = tuple(sorted(buckets[(top, sub)], key=lambda it: it.oi))
            groups.append(SubGroup(name=sub, hbyte=_hbyte_of((top, sub)), items=items))
        if groups:
            out.append(Category(name=top, groups=tuple(groups)))
    return tuple(out)


@lru_cache(maxsize=1)
def _by_oi() -> Dict[int, OadItem]:
    return {item.oi: item for cat in catalog() for g in cat.groups for item in g.items}


def find_item(oi: int) -> Optional[OadItem]:
    """按 OI 找测试对象；未登记的 OI 返回 None（调用方自行兜底显示）。"""
    return _by_oi().get(int(oi))


def all_items() -> Tuple[OadItem, ...]:
    """全部测试对象（按 OI 升序）。"""
    return tuple(_by_oi()[oi] for oi in sorted(_by_oi()))


def item_count() -> int:
    return len(_by_oi())


def oi_category(oi: int) -> Tuple[str, str]:
    """OI → (顶层分类, 子分类)；未登记高字节归「厂家扩展 / 其它」。"""
    hb = (int(oi) >> 8) & 0xFF
    return HBYTE_INFO.get(hb, ("厂家扩展", f"其它(0x{hb:02X}H)"))


# ─── 分类树的展示文案（与现场同类工具一致：顶层 4H、子层 3H、叶子给完整 OAD）───

def category_label(hbyte: int, name: str, count: int = -1) -> str:
    """顶层分类节点文案 `4H: 参变量`。

    顶层取 OI 高字节的**高 4 位**（0x40 ⇒ `4H`、0x30 ⇒ `3H`），子层取**低 4 位**
    （0x43 ⇒ `3H: 设备`）—— 与现场同类工具的树完全同形，现场照着念「4H 3H 设备」即可。
    """
    text = f"{(int(hbyte) >> 4) & 0x0F:X}H: {name}"
    return f"{text}（{count}）" if count >= 0 else text


def group_label(hbyte: int, name: str) -> str:
    """子分类节点文案 `3H: 设备`（第二层取该 OI 高字节的低 4 位）。"""
    return f"{int(hbyte) & 0x0F:X}H: {name}"


def leaf_label(oad: bytes, attr_name: str, index: int = 0, piid: int = 0) -> str:
    """叶子文案 `43000300_（版本信息）_(索引=0)_(优先级及序号=00)`。

    现场同类工具就是这个口径：OAD 全字节 + 属性名 + 元素索引 + 将要下发的 PIID，
    一眼能看出「点下去会发什么」，不必再回头查 OAD 表。
    """
    raw = bytes(oad or b"")
    # 索引照现场工具写数字（0 即「全部内容」，不再额外翻译成「全部」）
    return (f"{raw.hex().upper()}_（{attr_name}）_(索引={int(index)})"
            f"_(优先级及序号={int(piid) & 0xFF:02X})")


def oad_entries(item: OadItem) -> Tuple[Tuple[int, str, bytes], ...]:
    """把一个对象摊成**每个属性一条具体 OAD**：`(属性号, 属性名, OAD 字节)`。

    属性 1（逻辑名）也保留 —— 现场排查时常需要单独读逻辑名（参考工具的树里同样有
    `43000100_（设备描述符(逻辑名)）`）。
    """
    return tuple((aid, aname, item.oad(aid, 0)) for aid, aname in item.attrs)


#: 通用属性名 → 叶子名后缀。类属性表里的名字是**类级**的（「逻辑名」「换算及单位」），
#: 单看它不知道是哪个对象的什么量；拼上对象名才读得懂（`电压逻辑名` / `电压换算及单位`）。
#: 空串 = 该属性就是「值本体」，叶子名直接用对象名（`电压`、`电流`）。
_ATTR_SUFFIX = {
    1: "逻辑名",
    2: "",
    3: "换算及单位",
    31: "（带品质）",
}

#: 分相类（class 3 分相变量类）：属性 1/2/3/31 都是 A/B/C 三元素数组，
#: 按元素索引 01H/02H/03H 拆成「A相电压」这类具体项。
#: 顺序依据：`dl_t698_45_data_decode._decode_phase_array` 的 `labels = ["A相","B相","C相"]`
#: （仓库内唯一解码口径）+ §7.3.5「01H 指向对象属性的第一个元素」。
_PHASE_CLASS_IDS = (3,)
_PHASE_ATTRS = (1, 2, 3, 31)
_PHASES = ("A相", "B相", "C相")


def leaf_base_name(item: OadItem, attr: int, attr_name: str) -> str:
    """叶子名（不含相别）：`电压` / `电压逻辑名` / `电压换算及单位` / `设备描述符`。

    规则（只对**类级通用属性名**补对象名，具体属性名原样保留）：

    - `逻辑名` → `<对象>逻辑名`（`电压逻辑名`）
    - `…换算及单位` → `<对象><限定词>换算及单位`
    - `…数组` / `数值` / `参数` → `<对象><限定词>`（`电压`、`正向有功电能（扩展精度）`）
    - 其余（`设备描述符`、`版本信息`、`事件记录表`、`A相各次谐波数值数组` …）本身就是
      具体语义，**直接用**——早先把后缀映射无差别套上去，`43000200` 被叫成「电气设备」、
      `43000300` 被叫成「电气设备换算及单位」，把真正的「设备描述符 / 版本信息」盖掉了。

    限定词：`扩展精度2` / `扩展精度` / `尾数` / `带品质`，用来区分同一对象的兄弟数组属性
    （class 1 有 6 个电能量数组，全叫「正向有功电能」就分不清了）。
    """
    qual = ""
    if "扩展精度2" in attr_name:
        qual = "（扩展精度2）"
    elif "扩展精度" in attr_name:
        qual = "（扩展精度）"
    elif "尾数" in attr_name:
        qual = "（尾数）"
    if attr_name.startswith("带品质的"):
        qual = "（带品质）" + qual

    # 谐波变量类（class 5）的属性名自带相别与「各次谐波」，本身已具体 ⇒ 原样保留
    if item.class_id == 5:
        return qual and f"{item.name}{qual}" or attr_name

    if attr_name == "逻辑名":
        return f"{item.name}逻辑名"
    if attr_name.endswith("换算及单位"):
        return f"{item.name}{qual}换算及单位"
    if attr_name.endswith("数组") or attr_name in ("数值", "参数"):
        return f"{item.name}{qual}"
    return f"{attr_name}{qual}" if qual else attr_name


def record_leaf_name(item: OadItem, attr_name: str) -> str:
    """记录型叶子的名字：`电能表失压事件·事件记录表`。

    记录页的类属性名（「事件记录表」「冻结数据表」）在所有事件/冻结对象上都一样，
    不带上对象名就分不清是哪一条；已经包含对象名的（少见）则不重复拼。
    """
    if not attr_name or item.name in attr_name:
        return attr_name or item.name
    return f"{item.name}·{attr_name}"


def leaf_entries(item: OadItem) -> Tuple[Tuple[int, int, str, bytes], ...]:
    """把一个对象摊成**可下发的具体测试项**：`(元素索引, 属性号, 叶子名, OAD)`。

    比 `oad_entries` 多两件事，解决「叶子只写类级属性名、看不出具体是什么量」：

    1. **名字带对象语义**：`20000200` 显示为 `电压`，`20000100` 显示为 `电压逻辑名`
       （直接拿类属性名会得到「分相数值数组」，现场看不出是电压还是电流）。
    2. **分相类按相展开**：`20000201` → `A相电压`、`20000202` → `B相电压`、
       `20000203` → `C相电压`（§7.3.5：00H=整个属性，01H=第一个元素）。

    只对 class 3 展开 —— 它的属性名明确是「分相数值数组」。功率类（class 4）的
    「总及分相数值数组」在仓库内解码器里按 A/B/C 标注、与「总+三相」四元素说法不一致，
    证据不足 ⇒ **不猜**，只给整体项（`有功功率` 等）。
    """
    out: List[Tuple[int, int, str, bytes]] = []
    for attr, attr_name in item.attrs:
        base = leaf_base_name(item, attr, attr_name)
        out.append((0, attr, base, item.oad(attr, 0)))
        if item.class_id in _PHASE_CLASS_IDS and attr in _PHASE_ATTRS:
            for index, phase in enumerate(_PHASES, start=1):
                out.append((index, attr, f"{phase}{base}", item.oad(attr, index)))
    return tuple(out)


def record_entries(item: OadItem) -> Tuple[Tuple[int, str, bytes], ...]:
    """记录型对象摊成具体 OAD（只含记录表类属性，供「读取记录」页）。"""
    return tuple((aid, aname, item.oad(aid, 0)) for aid, aname in item.record_attrs())


def omd_entries(item: OadItem) -> Tuple[Tuple[int, str, bytes], ...]:
    """把一个对象摊成**每个方法一条具体 OMD**：`(方法号, 方法名, OMD 字节)`。"""
    return tuple((mid, mname, item.omd(mid)) for mid, mname in item.methods)


def omd_label(omd: bytes, method_name: str, piid: int = 0) -> str:
    """方法叶子文案 `00100100_（复位）_(优先级及序号=00)`（OMD 没有元素索引）。"""
    return (f"{bytes(omd or b'').hex().upper()}_（{method_name}）"
            f"_(优先级及序号={int(piid) & 0xFF:02X})")


# ═══════════════════════════════════════════════════════════════════════════
# 二、OAD / OMD / PIID 编码
# ═══════════════════════════════════════════════════════════════════════════

def make_oad(oi: int, attr: int = 2, index: int = 0) -> bytes:
    """OAD = OI(2B 大端) + 属性标识(1B) + 元素索引(1B)（§7.3.5）。

    属性标识低 5 位为属性号（1~31），高 3 位为属性特征（0 普通 / 1~3 记录型 / 4 数组元素）。
    """
    oi = int(oi)
    attr = int(attr)
    index = int(index)
    if not 0 <= oi <= 0xFFFF:
        raise ValueError(f"OI 越界: 0x{oi:X}（应为 0x0000~0xFFFF）")
    if not 0 <= attr <= 0xFF:
        raise ValueError(f"属性标识越界: {attr}（应为 0~255）")
    if not 0 <= index <= 0xFF:
        raise ValueError(f"元素索引越界: {index}（应为 0~255）")
    return oi.to_bytes(2, "big") + bytes([attr, index])


def make_omd(oi: int, method: int, mode: int = 0) -> bytes:
    """OMD = OI(2B 大端) + 方法标识(1B) + 操作模式(1B)（§7.3.6）。"""
    oi = int(oi)
    method = int(method)
    mode = int(mode)
    if not 0 <= oi <= 0xFFFF:
        raise ValueError(f"OI 越界: 0x{oi:X}")
    if not 0 <= method <= 0xFF:
        raise ValueError(f"方法标识越界: {method}")
    if not 0 <= mode <= 0xFF:
        raise ValueError(f"操作模式越界: {mode}")
    return oi.to_bytes(2, "big") + bytes([method, mode])


def parse_oad(raw: bytes) -> Dict[str, object]:
    """OAD 字节 → {oi, attr, attr_no, feature, index, name, cls_name}（不抛异常）。"""
    raw = bytes(raw or b"")
    out: Dict[str, object] = {"oi": 0, "attr": 0, "attr_no": 0, "feature": 0,
                              "index": 0, "name": "", "cls_name": "", "hex": raw.hex().upper()}
    if len(raw) < 4:
        return out
    oi = int.from_bytes(raw[0:2], "big")
    attr = raw[2]
    item = find_item(oi)
    out.update({
        "oi": oi,
        "attr": attr,
        "attr_no": attr & 0x1F,
        "feature": (attr >> 5) & 0x07,
        "index": raw[3],
        "name": item.name if item else f"未知对象(0x{oi:04X})",
        "cls_name": item.class_name if item else "未知类",
    })
    return out


def describe_oad(raw: bytes) -> str:
    """OAD → 「4001H 通信地址 - 参数(2) 索引0(全部)」这类单行人话。"""
    info = parse_oad(raw)
    if not info.get("name"):
        return "OAD 数据不足（需 4 字节）"
    idx = int(info["index"])
    idx_text = "全部内容" if idx == 0 else str(idx)
    return (f"{int(info['oi']):04X}H {info['name']} - {info['attr_no']}号属性"
            f"（索引{idx_text}）")


def build_piid(seq: int = 0, priority: int = 0) -> int:
    """PIID 字节：bit7 优先级 + bit6 保留(0) + bit0~5 服务序号（§7.3.3 表6）。

    注意响应用的 PIID-ACD 把 bit6 换成 ACD 标志 —— 那是服务器侧的事，本函数只编请求。
    """
    seq = int(seq)
    priority = int(priority)
    if not 0 <= seq <= 63:
        raise ValueError(f"服务序号越界: {seq}（应为 0~63）")
    if priority not in (0, 1):
        raise ValueError(f"服务优先级只有 0(普通)/1(高)，收到 {priority}")
    return ((priority & 0x01) << 7) | (seq & 0x3F)


def describe_piid(byte: int, acd: bool = False) -> str:
    """PIID / PIID-ACD → 「普通优先级 序号5」/「ACD=0 序号5」。"""
    b = int(byte) & 0xFF
    pri = (b >> 7) & 0x01
    seq = b & 0x3F
    if acd:
        return f"ACD={(b >> 6) & 0x01} 序号{seq}"
    return f"{'高' if pri else '普通'}优先级 序号{seq}"


# ═══════════════════════════════════════════════════════════════════════════
# 三、date_time_s 编解码（类型 28，tag 0x1C + 7 字节，无长度域）
# ═══════════════════════════════════════════════════════════════════════════

DATE_TIME_S_TAG = 0x1C


def encode_date_time_s(when: datetime) -> bytes:
    """datetime → `1C | 年(2B 大端) | 月 | 日 | 时 | 分 | 秒`（共 8 字节）。

    自证：文档 H.4.1 设置时钟 = `1C 07 E0 01 14 10 1B 0B` ⇒ 2016-01-20 16:27:11。
    """
    if not isinstance(when, datetime):
        raise TypeError(f"需要 datetime，收到 {type(when).__name__}")
    if not 0 <= when.year <= 0xFFFF:
        raise ValueError(f"年份越界: {when.year}")
    return (bytes([DATE_TIME_S_TAG])
            + struct.pack(">H", when.year)
            + bytes([when.month, when.day, when.hour, when.minute, when.second]))


def encode_date_time_s_body(when: datetime) -> bytes:
    """只要 7 字节本体（不带 0x1C tag），供 A-XDR 之外的裸时间域使用。"""
    return encode_date_time_s(when)[1:]


def decode_date_time_s(raw: bytes, offset: int = 0) -> Optional[datetime]:
    """解 `1C + 7` 或裸 7 字节；长度/取值不合法返回 None（绝不抛）。"""
    data = bytes(raw or b"")
    if offset < 0 or offset >= len(data):
        return None
    if data[offset] == DATE_TIME_S_TAG and offset + 8 <= len(data):
        offset += 1
    elif offset + 7 > len(data):
        return None
    body = data[offset:offset + 7]
    if len(body) < 7:
        return None
    try:
        year = int.from_bytes(body[0:2], "big")
        return datetime(year, body[2], body[3], body[4], body[5], body[6])
    except (ValueError, OverflowError):
        return None


def date_time_text(when: Optional[datetime]) -> str:
    return when.strftime("%Y-%m-%d %H:%M:%S") if when else ""


# ═══════════════════════════════════════════════════════════════════════════
# 四、SA 编码（复用 `dl_t698_45_upgrade.build_sa`，此处只做类型标注与再导出）
# ═══════════════════════════════════════════════════════════════════════════

def build_sa(addr_type: int = 1, logic_addr: int = 0, addr_len: int = 6,
             addr_bytes: bytes = b"") -> bytes:
    """组装 698.45 服务器地址 SA（唯一实现在 `dl_t698_45_upgrade.build_sa`）。

    类型：0 单地址 / 1 通配 / 2 组 / 3 广播（广播固定 1 字节 `AA`）；地址体按人书写顺序
    给出、线上逆序。例：单地址 `111111111111`（长度 6）⇒ `05 11 11 11 11 11 11`。
    """
    return _build_sa(addr_type, logic_addr, addr_len, addr_bytes)


def address_hex_to_bytes(text: str, addr_len: int = 6) -> bytes:
    """地址文本（可带空格/横线/0x）→ 定长地址体字节；非法抛 ValueError。

    不足 `addr_len` 前补 0，超出报错（截断会静默改掉用户要调的地址，现场查不出）。
    """
    cleaned = _clean_hex(text)
    if not cleaned:
        return b""
    if len(cleaned) % 2:
        raise ValueError(f"地址必须是整字节十六进制（当前 {len(cleaned)} 个字符）")
    data = bytes.fromhex(cleaned)
    if len(data) > addr_len:
        raise ValueError(
            f"地址 {text} 有 {len(data)} 字节，超过所选地址长度 {addr_len} 字节")
    return data.rjust(int(addr_len), b"\x00")


def sa_from_text(addr_type: int, logic_addr: int, addr_len: int, text: str) -> bytes:
    """界面口径的 SA 组装：地址文本 + 类型/逻辑/长度 → SA 字节。"""
    return build_sa(addr_type, logic_addr, addr_len,
                    address_hex_to_bytes(text, addr_len))


def sa_text(sa: bytes) -> str:
    """SA → 便于回显的文本（地址体按人书写顺序，与输入框同一个方向）。"""
    data = bytes(sa or b"")
    if len(data) <= 1:
        return data.hex().upper()
    return data[1:][::-1].hex().upper()


# ═══════════════════════════════════════════════════════════════════════════
# 五、RSD（记录行选择描述符，§7.3.15 表18）
# ═══════════════════════════════════════════════════════════════════════════

RSD_CHOICES: Tuple[Tuple[int, str], ...] = (
    (0, "不选择（全部记录）"),
    (1, "选择方法1：指定对象属性 = 指定值"),
    (2, "选择方法2：指定对象属性区间 + 间隔"),
    (9, "选择方法9：上第 n 次记录"),
    (10, "选择方法10：最新 n 条记录"),
)


def build_rsd(choice: int, *, oad: bytes = b"", value: bytes = b"",
              start: bytes = b"", end: bytes = b"", interval: bytes = b"",
              n: int = 1) -> bytes:
    """组装 RSD（`RSD::=CHOICE{ [0]不选择 NULL, [1]Selector1 … [10]Selector10 }`）。

    - 0：`00`（不选择）
    - 1：`01` + OAD + Data（指定值）—— 文档 H.3.3 用 `01` + 冻结时间 OAD + `date_time`
    - 2：`02` + OAD + 起始值 + 结束值 + 数据间隔（间隔为 `00` = NULL 表示区间内全部）
    - 9：`09` + 上第 n 次记录（unsigned，1B）
    - 10：`10` + 上 n 条记录（unsigned，1B）

    其余选择方法（3~8、11）结构未在本页用到，传入即抛 ValueError（不做「猜一个」的编排）。
    """
    choice = int(choice)
    if choice == 0:
        return b"\x00"
    if choice == 1:
        _require_oad(oad, "选择方法1")
        return b"\x01" + bytes(oad) + bytes(value or b"\x00")
    if choice == 2:
        _require_oad(oad, "选择方法2")
        if not (start and end):
            raise ValueError("选择方法2 需要同时给出起始值与结束值")
        return b"\x02" + bytes(oad) + bytes(start) + bytes(end) + bytes(interval or b"\x00")
    if choice == 9:
        return b"\x09" + bytes([int(n) & 0xFF])
    if choice == 10:
        return b"\x10" + bytes([int(n) & 0xFF])
    raise ValueError(f"未实现的选择方法 {choice}（仅支持 0/1/2/9/10）")


def _require_oad(oad: bytes, what: str) -> None:
    if len(bytes(oad or b"")) != 4:
        raise ValueError(f"{what} 需要 4 字节 OAD，收到 {len(bytes(oad or b''))} 字节")


def build_rcsd(oads: Sequence[bytes]) -> bytes:
    """RCSD（记录列选择描述符）= 个数(1B) + 每个 `00`(OAD 标签) + OAD（表19）。

    文档 H.3.3：`02 00 20 21 02 00 00 00 10 02 00` ⇒ 2 列，分别是两个 OAD。
    """
    items = [bytes(o) for o in oads]
    for o in items:
        if len(o) != 4:
            raise ValueError(f"RCSD 的每一项必须是 4 字节 OAD，收到 {len(o)} 字节")
    if not items:
        raise ValueError("RCSD 至少要选 1 列")
    if len(items) > 0xFF:
        raise ValueError(f"RCSD 列数过多: {len(items)}")
    out = bytes([len(items)])
    for o in items:
        out += b"\x00" + o
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 六、组帧（唯一的 FCS 实现由 DLT69845FrameGenerator 提供）
# ═══════════════════════════════════════════════════════════════════════════

def _gen() -> DLT69845FrameGenerator:
    return DLT69845FrameGenerator()


def build_connect(sa: bytes, ca: int = 0, piid: int = 0, **kwargs) -> bytes:
    """建立应用连接（CONNECT-Request）；参数见 `generate_connect_request`。"""
    return _gen().generate_connect_request(bytes(sa), int(ca), int(piid), **kwargs)


def build_get(sa: bytes, ca: int, piid: int, oad: bytes,
              time_tag_none: bool = True) -> bytes:
    """读一个对象属性（GET-Request Normal）。

    文档 H.3.1：SA=通配、CA=0、PIID=1、OAD=通信地址 ⇒
    `68 17 00 43 05 AA AA AA AA AA AA 00 <HCS> 05 01 01 40 01 02 00 00 <FCS> 16`。
    """
    _require_oad(oad, "读属性")
    return _gen().generate_get_request_normal(
        bytes(sa), int(ca), int(piid), bytes(oad), time_tag_none=bool(time_tag_none))


def build_get_list(sa: bytes, ca: int, piid: int,
                   oads: Sequence[bytes], time_tag_none: bool = True) -> bytes:
    """读多个对象属性（GET-Request Normal-List，子类型 2）。

    文档 H.3.2：`05 02 02 02 20 00 02 00 20 01 02 00 00`（PIID=2、2 个 OAD、无时间标签）。
    """
    items = [bytes(o) for o in oads]
    if not items:
        raise ValueError("列表读取至少要选 1 个 OAD")
    if len(items) > 0xFF:
        raise ValueError(f"一次列表读取最多 255 个 OAD，收到 {len(items)}")
    for o in items:
        if len(o) != 4:
            raise ValueError(f"OAD 必须是 4 字节，收到 {len(o)} 字节")
    apdu = (bytes([SERVICE_GET_REQ, 0x02, int(piid) & 0xFF, len(items)])
            + b"".join(items)
            + (TIME_TAG_NONE if time_tag_none else b""))
    return _gen().generate_apdu_frame(bytes(sa), int(ca), apdu, control=0x43)


def build_get_record(sa: bytes, ca: int, piid: int, oad: bytes,
                     rsd: bytes = b"\x00", rcsd: Optional[bytes] = None,
                     time_tag_none: bool = True) -> bytes:
    """读一个记录型对象属性（GET-Request Record，子类型 3）。

    APDU = `05 03 PIID OAD RSD RCSD 00`。文档 H.3.3（日冻结, RSD=选择方法1）：
    `05 03 03 50 04 02 00 01 20 21 02 00 1C 07 E0 01 14 00 00 00 02 00 20 21 02 00
   00 00 10 02 00 00`。
    `rcsd` 为空时不追加（部分设备允许省略列描述，由设备自行决定返回全部列）。
    """
    _require_oad(oad, "读记录")
    apdu = (bytes([SERVICE_GET_REQ, 0x03, int(piid) & 0xFF])
            + bytes(oad) + bytes(rsd or b"\x00"))
    if rcsd:
        apdu += bytes(rcsd)
    if time_tag_none:
        apdu += TIME_TAG_NONE
    return _gen().generate_apdu_frame(bytes(sa), int(ca), apdu, control=0x43)


def build_set(sa: bytes, ca: int, piid: int, oad: bytes,
              data: bytes, time_tag_none: bool = True) -> bytes:
    """设置一个对象属性（SET-Request Normal）。文档 H.4.1：
    `06 01 02 40 00 02 00 1C 07 E0 01 14 10 1B 0B 00`。

    `data` 是**已按 A-XDR 编好**的数据域（含类型 tag）；本函数不猜类型 —— 参数类型错了
    设备只会回 DAR，看不出是谁的错。
    """
    _require_oad(oad, "设置属性")
    apdu = (bytes([SERVICE_SET_REQ, 0x01, int(piid) & 0xFF])
            + bytes(oad) + bytes(data or b""))
    if time_tag_none:
        apdu += TIME_TAG_NONE
    return _gen().generate_apdu_frame(bytes(sa), int(ca), apdu, control=0x43)


def build_action(sa: bytes, ca: int, piid: int, omd: bytes,
                 data: bytes = b"", time_tag_none: bool = True) -> bytes:
    """操作一个对象方法（ACTION-Request Normal）。文档 H.5.1：
    `07 01 05 00 10 01 00 0F 00 00`（OMD=0010H 复位、Data=`0F 00`=integer 0、无时间标签）。
    """
    omd = bytes(omd or b"")
    if len(omd) != 4:
        raise ValueError(f"OMD 必须是 4 字节（OI+方法+模式），收到 {len(omd)} 字节")
    apdu = (bytes([SERVICE_ACTION_REQ, 0x01, int(piid) & 0xFF])
            + omd + bytes(data or b""))
    if time_tag_none:
        apdu += TIME_TAG_NONE
    return _gen().generate_apdu_frame(bytes(sa), int(ca), apdu, control=0x43)


def build_set_address(sa: bytes, ca: int, piid: int, new_address: bytes,
                      time_tag_none: bool = True) -> bytes:
    """写通信地址：SET-Request Normal OAD=`40010200`，Data = octet-string(新地址)。"""
    data = bytes(new_address or b"")
    if not data:
        raise ValueError("新地址不能为空")
    axdr = bytes([0x09]) + _ber_len(len(data)) + data      # octet-string
    return build_set(sa, ca, piid, OAD_ADDRESS, axdr, time_tag_none)


def build_set_datetime(sa: bytes, ca: int, piid: int, when: datetime,
                       time_tag_none: bool = True) -> bytes:
    """写日期时间：SET-Request Normal OAD=`40000200`，Data = date_time_s。"""
    return build_set(sa, ca, piid, OAD_DATETIME, encode_date_time_s(when), time_tag_none)


def _ber_len(length: int) -> bytes:
    """A-XDR/BER 长度域（单一定义在 `AXDRCoder._encode_length`，此处转调）。"""
    from dl_t698_45_axdr import AXDRCoder

    return AXDRCoder._encode_length(int(length))


def parse_hex(text: str) -> bytes:
    """宽松十六进制解析（去空格/逗号/0x 前缀）；非法抛 ValueError（带位置说明）。"""
    cleaned = _clean_hex(text)
    if not cleaned:
        return b""
    if len(cleaned) % 2:
        raise ValueError(f"十六进制字符数必须为偶数（当前 {len(cleaned)}）")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f"不是合法十六进制：{text.strip()[:60]}") from exc


def _clean_hex(text: str) -> str:
    out = []
    for tok in str(text or "").replace(",", " ").replace("-", " ").split():
        if tok.lower().startswith("0x"):
            tok = tok[2:]
        out.append(tok)
    joined = "".join(out)
    return "".join(ch for ch in joined if ch not in " \t\r\n")


def format_hex(data: bytes, limit: int = 0) -> str:
    """字节 → 空格分隔大写十六进制；`limit>0` 且超长时给「头 + … + 尾 + 总长」。"""
    raw = bytes(data or b"")
    if limit and len(raw) > limit:
        half = max(1, limit // 2)
        return (f"{raw[:half].hex(' ').upper()} … {raw[-half:].hex(' ').upper()}"
                f"（共 {len(raw)} 字节）")
    return raw.hex(" ").upper()


# ═══════════════════════════════════════════════════════════════════════════
# 七、响应判定（一律走 DLT69845Parser，不做字节比对）
# ═══════════════════════════════════════════════════════════════════════════

def parse_frame(frame: bytes) -> dict:
    """整帧 → 解析结果 dict（`DLT69845Parser.parse` 的薄包装；异常吞掉给错误串）。"""
    try:
        return DLT69845Parser().parse(bytes(frame or b""))
    except Exception as exc:                      # noqa: BLE001 —— 解析器任何异常都不能冒出界面
        return {"解析状态": "失败", "错误信息": f"{type(exc).__name__}: {exc}"}


def frame_apdu(frame: bytes) -> Tuple[Optional[dict], str]:
    """整帧 → (APDU dict, 错误原因)。校验不过 / 无 APDU 时 APDU 为 None。"""
    result = parse_frame(frame)
    if result.get("解析状态") != "成功":
        return None, f"帧解析失败：{result.get('错误信息', '未知原因')}"
    bad = [name for name, key in (("HCS", "帧头校验HCS"), ("FCS", "帧校验FCS"))
           if (result.get(key) or {}).get("校验结果") != "通过"]
    if bad:
        return None, "帧解析失败：" + "/".join(bad) + " 校验不通过"
    link = result.get("链路用户数据") or {}
    apdu = link.get("APDU")
    if not isinstance(apdu, dict):
        reason = link.get("APDU解析错误") or "响应帧里没有 APDU（可能是链路层报文）"
        return None, f"帧解析失败：{reason}"
    return apdu, ""


def evaluate_response(frame: bytes) -> Dict[str, object]:
    """把一帧响应翻成「结果 + 人话」，供信息表与日志直接用。

    Returns:
        dict(
          ok: True/False/None（None = 无法判定，例如 CONNECT-Response 未做字段级解析）,
          kind: "GET-Response" 等,
          title: 一行的结论（成功 / 失败（DAR=1 无权限））,
          reason: ok=False 时的原因,
          dar: DAR 值或 None,
          oad: "40010200" / ""，
          lines: [「名称: 值」...]（业务解码优先），
          raw: 整帧 hex，
        )

    **永不抛异常**：现场拿到半截帧/其它协议的帧时只应当记一条「不是 698 响应」。
    """
    out: Dict[str, object] = {
        "ok": None, "kind": "", "title": "", "reason": "", "dar": None,
        "oad": "", "omd": "", "lines": [], "raw": bytes(frame or b"").hex().upper(),
        "apdu_type": "",
    }
    apdu, err = frame_apdu(frame)
    if apdu is None:
        out["ok"] = False
        out["title"] = "帧无效"
        out["reason"] = err
        return out

    code = _service_code(apdu)
    out["apdu_type"] = str(apdu.get("APDU类型") or "")
    out["kind"] = out["apdu_type"] or f"服务码 0x{code:02X}"

    if code == SERVICE_CONNECT_RSP:
        out["ok"] = None                    # 结构未做字段级解析，不冒充判定
        out["title"] = "已收到建立应用连接响应（未做字段级解析）"
        out["lines"] = [f"APDU: {format_hex(bytes.fromhex(str(apdu.get('原始数据') or '')))}"]
        return out

    if code == SERVICE_ERROR_RSP:
        out["ok"] = False
        out["title"] = "异常响应（ERROR-Response）"
        out["lines"] = _apdu_lines(apdu)
        return out

    if code in (SERVICE_GET_RSP,):
        oad = (apdu.get("OAD") or {}).get("原始值", "")
        out["oad"] = str(oad)
        return _evaluate_get(apdu, out)

    if code in (SERVICE_SET_RSP,):
        return _evaluate_one_dar(apdu, out, "设置", "OAD")

    if code == SERVICE_ACTION_RSP:
        return _evaluate_one_dar(apdu, out, "操作", "OMD")

    if code == SERVICE_REPORT_NOTIFY:
        out["ok"] = None
        out["title"] = "上报通知（非本页请求的响应）"
        out["lines"] = _apdu_lines(apdu)
        return out

    out["ok"] = None
    out["title"] = f"未识别的服务码 0x{code:02X}"
    out["lines"] = _apdu_lines(apdu)
    return out


def _service_code(apdu: dict) -> int:
    raw = str(apdu.get("服务码") or "")
    try:
        return int(raw, 16)
    except ValueError:
        return -1


def _evaluate_get(apdu: dict, out: Dict[str, object]) -> Dict[str, object]:
    subtype = str(apdu.get("子类型") or "")
    out["kind"] = f"GET-Response（{subtype or '未知子类型'}）"

    if "列表" in apdu and isinstance(apdu.get("列表"), list):
        entries = apdu["列表"]
        lines: List[str] = []
        ok_any = False
        for item in entries:
            oad_hex = (item.get("OAD") or {}).get("原始值", "")
            info = parse_oad(bytes.fromhex(oad_hex)) if oad_hex else {}
            label = _oid_label(info) if info else (oad_hex or "?")
            dar = _dar_of(item)
            if dar is not None and dar != 0:
                lines.append(f"{label}: 失败 DAR={dar} {_dar_entry(item)[1]}".rstrip())
                continue
            ok_any = True
            for line in _data_lines(item):
                lines.append(f"{label}: {line}")
        out["ok"] = True if (ok_any or not entries) else False
        out["title"] = f"列表读取响应（{len(entries)} 项）"
        out["lines"] = lines or ["（响应未带数据）"]
        return out

    dar, dar_text = _dar_entry(apdu)
    out["dar"] = dar
    if dar is not None and dar != 0:
        out["ok"] = False
        out["title"] = f"失败（DAR={dar} {dar_text}）".replace(" ）", "）")
        out["reason"] = dar_text
        return out

    if "RCSD及响应数据" in apdu:
        out["ok"] = True
        out["title"] = "记录读取响应"
        out["lines"] = _record_lines(str(apdu.get("RCSD及响应数据") or ""))
        return out

    out["ok"] = True
    out["title"] = "成功"
    out["lines"] = _data_lines(apdu) or ["（响应未带数据）"]
    return out


def _evaluate_one_dar(apdu: dict, out: Dict[str, object], what: str,
                      key: str) -> Dict[str, object]:
    ref = str((apdu.get(key) or {}).get("原始值", ""))
    out["oad" if key == "OAD" else "omd"] = ref
    dar, dar_text = _dar_entry(apdu)
    out["dar"] = dar
    if dar is None:
        out["ok"] = None
        out["title"] = f"{what}响应未带 DAR"
        out["lines"] = _apdu_lines(apdu)
        return out
    if dar != 0:
        out["ok"] = False
        out["title"] = f"{what}失败（DAR={dar} {dar_text}）".replace(" ）", "）")
        out["reason"] = dar_text
        return out
    out["ok"] = True
    out["title"] = f"{what}成功"
    out["lines"] = _data_lines(apdu)
    return out


def _dar_entry(node: dict) -> Tuple[Optional[int], str]:
    """取 DAR 及其中文说明：GET 响应在「数据访问结果」，SET/ACTION 响应在「结果」。

    说明直接取解析器翻好的 `DAR说明`（无则 `说明`），不另建 DAR 码表 ——
    `dl_t698_45_apdu_parser._enrich_dar` 是那张表的单一来源。
    """
    for key in ("数据访问结果", "结果"):
        entry = node.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("解析值"), int):
            dar = int(entry["解析值"])
            text = str(entry.get("DAR说明") or entry.get("说明") or "").strip()
            return dar, (text or ("成功" if dar == 0 else ""))
    return None, ""


def _dar_of(node: dict) -> Optional[int]:
    return _dar_entry(node)[0]


def _dar_text_of(node: dict) -> str:
    dar, text = _dar_entry(node)
    if dar is None or dar == 0:
        return ""
    return text or ""


def _oid_label(info: dict) -> str:
    if not info or not info.get("name"):
        return str(info.get("hex") or "?")
    oi = int(info.get("oi") or 0)
    return f"{oi:04X}H {info['name']}(属性{info.get('attr_no')})"


def _data_lines(apdu: dict) -> List[str]:
    """把 APDU 里的数据域翻成若干行「名称: 值」；业务解码优先，退化为 A-XDR 值。"""
    lines: List[str] = []
    biz = apdu.get("数据业务")
    if isinstance(biz, dict) and biz:
        lines.extend(f"{k}: {v}" for k, v in biz.items())
        return lines
    for key in ("数据", "响应数据"):
        if key in apdu:
            text = _axdr_text(apdu[key])
            if text:
                lines.append(f"{key}: {text}")
    return lines


def _axdr_text(node) -> str:
    """A-XDR 解码结果 → 单行人话（不递归展开大数组，避免日志被冲爆）。"""
    if not isinstance(node, dict):
        return str(node)
    typ = str(node.get("类型") or "")
    val = node.get("解析值")
    if typ == "octet-string" and isinstance(val, str):
        return f"octet-string = {val.upper()}"
    if typ == "array" and isinstance(val, list):
        if len(val) <= 4:
            return "[" + ", ".join(_axdr_text(v) for v in val) + "]"
        head = ", ".join(_axdr_text(v) for v in val[:4])
        return f"[{head}, …共 {len(val)} 项]"
    if typ == "structure" and isinstance(val, (dict, list)):
        if isinstance(val, dict):
            return "{" + ", ".join(f"{k}={_axdr_text(v)}" for k, v in val.items()) + "}"
        return "{" + ", ".join(_axdr_text(v) for v in val) + "}"
    if isinstance(val, str) and typ:
        return f"{typ} = {val}"
    if val is None:
        return typ or "null"
    return f"{val}" if not typ else f"{typ} = {val}"


def _record_lines(rcsd_hex: str) -> List[str]:
    """RCSD 及响应数据 → 列清单 + 响应数据原文。

    记录型响应的数据体是「M 条记录 × N 列」的二维结构，逐列语义要靠列 OAD 的设备实现
    确定；本页只保证**列能对上**、数据原文完整给出（不臆造字段含义）。
    """
    try:
        raw = bytes.fromhex(str(rcsd_hex or ""))
    except ValueError:
        return ["响应数据（原始）: " + str(rcsd_hex or "")]
    if not raw:
        return ["（响应未带记录数据）"]
    count = raw[0]
    lines: List[str] = [f"记录列数: {count}"]
    pos = 1
    for i in range(count):
        if pos + 4 > len(raw):
            lines.append(f"第{i + 1}列: 数据不足（已到帧尾）")
            break
        item = parse_oad(raw[pos:pos + 4])
        lines.append(f"第{i + 1}列: {_oid_label(item)}")
        pos += 4
    rest = raw[pos:]
    lines.append(f"响应数据（原始）: {format_hex(rest, limit=160) if rest else '（无）'}")
    return lines


def _apdu_lines(apdu: dict) -> List[str]:
    """兜底行：把 APDU 里的标量字段平铺出来（供未识别服务/异常响应用）。"""
    lines: List[str] = []
    for key, value in apdu.items():
        if isinstance(value, dict):
            text = str(value.get("说明") or value.get("解析值") or "").strip()
            if text:
                lines.append(f"{key}: {text}")
        elif isinstance(value, (str, int, float)) and key not in ("原始数据", "解析状态"):
            lines.append(f"{key}: {value}")
    return lines


def extract_address(frame: bytes) -> str:
    """从「读通信地址」响应里取地址（octet-string，大写 hex）；取不到返回空串。"""
    apdu, _err = frame_apdu(frame)
    if not isinstance(apdu, dict):
        return ""
    nodes = []
    if isinstance(apdu.get("列表"), list):
        nodes = list(apdu["列表"])
    else:
        nodes = [apdu]
    for item in nodes:
        oad_hex = str((item.get("OAD") or {}).get("原始值", "")).upper()
        if oad_hex and oad_hex != OAD_ADDRESS.hex().upper():
            continue
        data = item.get("数据")
        if isinstance(data, dict):
            raw = str(data.get("原始值") or data.get("解析值") or "")
            if raw:
                return raw.upper()
    return ""


def extract_date_time(frame: bytes) -> Optional[datetime]:
    """从「读日期时间」响应里取时间（date_time_s）；取不到返回 None。"""
    apdu, _err = frame_apdu(frame)
    if not isinstance(apdu, dict):
        return None
    nodes = list(apdu["列表"]) if isinstance(apdu.get("列表"), list) else [apdu]
    for item in nodes:
        oad_hex = str((item.get("OAD") or {}).get("原始值", "")).upper()
        if oad_hex and oad_hex != OAD_DATETIME.hex().upper():
            continue
        data = item.get("数据")
        if isinstance(data, dict):
            encoding = str(data.get("原始编码") or "")
            if encoding:
                when = decode_date_time_s(bytes.fromhex(encoding))
                if when:
                    return when
            raw = str(data.get("原始值") or "")
            if raw:
                when = decode_date_time_s(bytes.fromhex(raw))
                if when:
                    return when
    return None


def response_summary(frame: bytes) -> str:
    """一帧响应的单行摘要（信息表「信息」列右侧追加用）；失败时带原因。"""
    info = evaluate_response(frame)
    title = str(info.get("title") or "")
    reason = str(info.get("reason") or "")
    if reason and reason not in title:
        return f"{title}｜{reason}" if title else reason
    return title


# ─── 逐字段解析输出（复用单帧解析页那张表，不自建第二套字段拆解）────────────

def parse_table(frame: bytes, verify: bool = True) -> list:
    """整帧 → `DLT69845Parser.parse_to_table` 的行列表（异常时返回空表）。

    这是**单帧解析页显示的那张表**，字段级拆解、偏移、说明全部由解析器负责 ——
    测试页只做展示，不另写一份字段拆解（AGENTS 陷阱 31 的漂移根因）。
    """
    try:
        return DLT69845Parser().parse_to_table(bytes(frame or b""), verify=verify)
    except Exception:                              # noqa: BLE001 —— 展示层绝不因解析崩掉
        return []


def _display_width(text: str) -> int:
    """字符串显示宽度：CJK/全角算 2 列，用于日志里对齐四列。"""
    import unicodedata

    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: str, width: int) -> str:
    """按显示宽度左对齐补空格（超宽则原样返回，不截断）。"""
    text = str(text)
    gap = width - _display_width(text)
    return text + (" " * gap if gap > 0 else "")


def _cell_text(value) -> str:
    """「解析值」单元格文本化：dict/list 打成 `k=v, …` / `[a, b]`，其余原样。"""
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if isinstance(val, (dict, list)):
                continue                     # 嵌套结构交给「说明」列，别把格子撑爆
            parts.append(f"{key}={val}")
        return ", ".join(parts)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_cell_text(v) for v in value) + "]"
    text = str(value)
    return "" if text in ("", "-", "None") else text


#: 四列的显示宽度（字段 / 原始值 / 解析值），说明列吃掉剩余
_COL_FIELD, _COL_RAW, _COL_PARSED = 22, 24, 30
#: 单元格最大显示宽度：超出截断并标「共 N 字符」（否则结构化数据一行能撑到屏幕外的几千列）
_CELL_MAX = 72


def _compact_hex_like(text: str, keep_chars: int = 32) -> str:
    """长 hex 串压成「前 N 个字符 …（共 M 字符）」，避免一行撑到屏幕外。

    只对**纯十六进制**下手（解析器把 A-XDR 数据的原始编码直接塞进原始值/解析值列）；
    文字说明不受影响。**不要求长度为偶数** —— 解析器偶尔给出被截断的奇数长度编码，
    早先按「偶数才是 hex」判定会整段漏压、一行撑到屏幕外。
    """
    text = str(text or "").strip()
    compact = text.replace(" ", "")
    if len(compact) < keep_chars + 16:
        return text
    if any(c not in "0123456789abcdefABCDEF" for c in compact):
        return text
    return f"{compact[:keep_chars].upper()} … （共 {len(compact)} 字符）"


def _clip(text: str, limit: int = _CELL_MAX) -> str:
    """按显示宽度截断（CJK 算 2 列），超出补 `…` 与原始长度。"""
    text = str(text)
    if _display_width(text) <= limit:
        return text
    kept, width = [], 0
    for ch in text:
        w = 2 if _display_width(ch) == 2 else 1
        if width + w > limit:
            break
        kept.append(ch)
        width += w
    return "".join(kept) + f"…（共 {len(text)} 字符）"


def format_table_rows(rows: Sequence[Sequence], header: str = "") -> List[str]:
    """解析行 → 对齐的四列文本（`字段 | 原始值 | 解析值 | 说明`）。

    字段名里的前导空格（解析器用它表示层级）保留，因此缩进层次照旧可读。
    """
    out: List[str] = []
    if header:
        out.append(header)
    for row in rows:
        if not row or len(row) < 4:
            continue
        field, raw, parsed, desc = row[0], row[1], row[2], row[3]
        raw = "" if str(raw) in ("", "-", "None") else str(raw)
        raw = _clip(_compact_hex_like(raw), _COL_RAW + 8)
        parsed = _cell_text(parsed)
        desc = "" if str(desc) in ("", "None") else str(desc)
        parsed = _clip(_compact_hex_like(parsed))
        desc = _clip(desc, 110)
        # 解析器对结构化字段（OAD/OMD）把解析值拼成 `{'OI': …}` 字符串；
        # 「说明」列已经是同一信息的人话版，两列都印等于刷屏 ⇒ 有说明时省略该串。
        if desc and parsed.startswith(("{'", "['")):
            parsed = ""
        line = (f"  {_pad(field, _COL_FIELD)} {_pad(raw, _COL_RAW)}"
                f" {_pad(parsed, _COL_PARSED)}")
        out.append((line + " " + desc).rstrip())
    return out


def detail_lines(frame: bytes, verify: bool = True,
                 title: str = "帧结构") -> List[str]:
    """整帧 → 逐字段明细（含「共 N 行」头），供收发日志直接写。

    解析器拆不动（半截帧/非 698 字节）时给一行可读提示，不抛、不静默。
    """
    rows = parse_table(frame, verify=verify)
    if not rows:
        return [f"（{title}：没有可解析的字段，可能不是完整的 698.45 帧）"]
    return format_table_rows(rows, header=f"{title}（{len(rows)} 行）")


# ═══════════════════════════════════════════════════════════════════════════
# 八、预置测试项（页面顶部的固定动作，全部来自协议文档附录 H）
# ═══════════════════════════════════════════════════════════════════════════

def quick_read_address(sa: bytes, ca: int = 0, piid: int = 1) -> bytes:
    """读通信地址（GET 40010200）—— 「获取设备地址」按钮的帧。"""
    return build_get(sa, ca, piid, OAD_ADDRESS)


def quick_write_address(sa: bytes, ca: int, piid: int, new_address: bytes) -> bytes:
    return build_set_address(sa, ca, piid, new_address)


def quick_read_datetime(sa: bytes, ca: int = 0, piid: int = 1) -> bytes:
    return build_get(sa, ca, piid, OAD_DATETIME)


def quick_write_datetime(sa: bytes, ca: int, piid: int, when: datetime) -> bytes:
    return build_set_datetime(sa, ca, piid, when)


def quick_read_version(sa: bytes, ca: int = 0, piid: int = 1) -> bytes:
    return build_get(sa, ca, piid, OAD_VERSION)


def quick_connect(sa: bytes, ca: int = 0, piid: int = 0) -> bytes:
    return build_connect(sa, ca, piid)


# ═══════════════════════════════════════════════════════════════════════════
# 九、筛选（页面上的搜索框；与界面无关，可单测）
# ═══════════════════════════════════════════════════════════════════════════

def filter_items(keyword: str, items: Iterable[OadItem] = None) -> Tuple[OadItem, ...]:
    """按名称 / OI 十六进制 / 接口类名筛选测试对象（空关键字返回全部）。

    关键字以 `0x`/纯十六进制的形式给出时**同时**匹配 OI 前缀（「2000」能命中 0x2000），
    现场按 OAD 前 4 位找项比记中文名快。
    """
    items = tuple(items if items is not None else all_items())
    kw = str(keyword or "").strip().lower()
    if not kw:
        return items
    bare = kw[2:] if kw.startswith("0x") else kw
    out = []
    for item in items:
        if (kw in item.name.lower()
                or kw in item.class_name.lower()
                or (bare and f"{item.oi:04x}".startswith(bare))):
            out.append(item)
    return tuple(out)
