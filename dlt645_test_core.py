# -*- coding: utf-8 -*-
"""DL/T 645-2007（协议 6）**协议测试页**的预置测试库与组帧逻辑 —— 纯逻辑，禁止 import Qt。

与「协议组帧」页的分工：组帧页是**临时、任意**的（字段随手填、命令自己选）；
本模块是**预先做好**的测试项库 ——

- 按协议大项把 1781 条数据标识（`dlt645_di.json` 1099 + 光伏扩展 682）分成
  「电能量 / 最大需量 / 电压电流 / 功率与谐波 / 参变量 / 结算日 / 记录 / 光伏扩展」等大类，
  每个叶子就是一个可直接下发的 DI；
- 另给一套**特殊命令库**（读/写通信地址、广播校时、冻结、改速率、改密码、三类清零、读后续），
  字段定义直接取 `dlt645_frame_schema.DLT645_CMD_SCHEMA`，界面只负责渲染；
- 响应判定（结构/校验 → 方向位 → 功能码 → 异常位 → DI 回显 → 取值）集中在这里，
  界面不写任何 645 字节细节。

分层
----
- 本模块：分类库 + 命令库 + 组帧 + 响应判定（纯逻辑）
- ``dlt645_test_widget``：只做界面与串口
- 帧封装**一律**交 :class:`dlt645_frame_gen.DLT645FrameGenerator`（地址线上低字节在前、
  数据域 +0x33、CS、``68…16`` 的唯一实现）；数据域编码走 ``dlt645_frame_schema.build_data``
  ⇒ **禁止**在别处再拼一份 645 帧（AGENTS §4.5 / §8 陷阱 48）。
- 解析一律交 ``DLT645Parser``（表格化再经 ``protocol_registry.DLT645GuiParser``，
  含前导 FEH 行与偏移位移）；本模块不重写任何字节偏移。

本模块无 Qt、无 crcmod 依赖 ⇒ 可被 GUI 顶层 import（与 698 页相反）；
但内核仍按需 import 组帧器以免拉高面板启动开销。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from dlt645_data_codec import FUNC_NAMES, decode_err, decode_value
from dlt645_frame_schema import REQ, build_di_fields, get_command
from dlt645_pv_wireless import WIRELESS_DI_MAP, parse_wireless_di as _parse_wireless_di
from dlt645_pv_wireless_frame import REQ_WITH_PAYLOAD_DI, wireless_di_info
from testpage_render import format_table_rows

#: 结果枚举（信息表「结果」列）
RESULT_PENDING = "等待中"
RESULT_OK = "成功"
RESULT_FAIL = "失败"
RESULT_TIMEOUT = "超时"
RESULT_NO_REPLY = "已发送"

#: 页面默认地址（12 位书写序）
DEFAULT_ADDR = "000000000000"
#: 广播地址（BCD 99×6）—— 广播校时
BROADCAST_99 = "999999999999"
#: 读/写通信地址命令的地址域（AA×6，DL/T645-2007 §7.4/§7.5）
BROADCAST_AA = "AAAAAAAAAAAA"

#: 结算日分桶大小（`05` 类有 254 个结算日 × 2 条，一桶 20 天）
SETTLE_BUCKET = 20


def _gen():
    """惰性取组帧器（唯一实现）。"""
    from dlt645_frame_gen import DLT645FrameGenerator

    return DLT645FrameGenerator()


# ═══════════════════════════════════════════════════════════════════════════
# 一、DI 分类库（数据全部来自 DI 表，不手写名称）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DiItem:
    """一条数据标识（叶子）。"""

    di: str            #: 8 位书写序（DI3DI2DI1DI0），如 "02010100"
    name: str
    unit: str = ""
    data_type: str = ""
    length: int = 0
    pv: bool = False        #: 光伏扩展 DI（`02E6/03E6/04E6`）
    wireless: bool = False  #: 无线模组接口手册 V1.6 的扩展 DI（`WIRELESS_DI_MAP`）
    note: str = ""          #: 手册备注（读页「当前项」展示方向/控制码/注意事项）


@dataclass(frozen=True)
class SubGroup:
    """子分类（同一 DI2 下的一组 DI）。"""

    name: str
    items: Tuple[DiItem, ...]


@dataclass(frozen=True)
class Category:
    """顶层分类（协议大项）。"""

    name: str
    subgroups: Tuple[SubGroup, ...]

    @property
    def item_count(self) -> int:
        return sum(len(s.items) for s in self.subgroups)


#: 顶层分类（DI3 高字节 → 名称）与显示顺序
_DI3_NAMES: Tuple[Tuple[str, str], ...] = (
    ("00", "电能量"),
    ("01", "最大需量"),
    ("02", "电压 / 电流"),
    ("03", "功率 / 功率因数 / 谐波"),
    ("04", "参变量"),
    ("05", "结算日电能"),
    ("06", "记录"),
    ("07", "冻结次数"),
    ("FF", "LME 自定义"),
)

#: 光伏扩展单独成一层（DI2 == E6），子类按 DI3 语义
_PV_CATEGORY = "光伏扩展"
#: 无线模组接口手册 V1.6（`dlt645_pv_wireless.WIRELESS_DI_MAP`）单独成一层
_WIRELESS_CATEGORY = "光伏无线扩展（V1.6）"
#: 读请求需要携带数据域的 DI（02EB0000 转发参数 / FF00DD01 LME 条目）
READ_PAYLOAD_DI = frozenset(REQ_WITH_PAYLOAD_DI) | {"FF00DD01"}
_PV_SUB_NAMES: Dict[str, str] = {"02": "光伏变量", "03": "光伏事件", "04": "光伏参数"}

#: （DI3, DI2）→ 子类名称；缺省回落「NN 类」
_SUB_NAMES: Dict[Tuple[str, str], str] = {
    ("00", "01"): "正向有功电能",
    ("00", "02"): "反向有功电能",
    ("00", "03"): "组合有功电能",
    ("00", "04"): "正向无功电能",
    ("00", "05"): "反向无功电能",
    ("00", "06"): "组合无功1电能",
    ("00", "07"): "组合无功2电能",
    ("00", "10"): "第2象限无功电能",
    ("00", "11"): "第3象限无功电能",
    ("00", "12"): "第4象限无功电能",
    ("00", "90"): "第1象限无功电能",
    ("00", "60"): "正向有功精确电能（含数据块）",
    ("00", "61"): "反向有功精确电能（含数据块）",
    ("01", "01"): "正向有功最大需量",
    ("01", "02"): "反向有功最大需量",
    ("02", "01"): "电压",
    ("02", "02"): "电流",
    ("03", "06"): "有功功率",
    ("03", "08"): "无功功率",
    ("03", "0A"): "视在功率",
    ("03", "0B"): "功率因数",
    ("03", "0C"): "相角",
    ("03", "10"): "电压谐波",
    ("03", "11"): "电流谐波",
    ("04", "00"): "基本参数（日期/时间/地址/状态字）",
    ("04", "FF"): "LME 详细信息",
    ("06", "00"): "事件与编程次数",
    ("06", "10"): "负荷曲线",
    ("07", "00"): "冻结次数",
    ("FF", "00"): "LME 自定义",
}


def _merged_di_map() -> Dict[str, dict]:
    """合并后的 DI 表（基础 1099 + 光伏扩展 682）；唯一来源（缓存）。"""
    return _load_merged()


def _di_table_candidates() -> Tuple[str, ...]:
    """DI 表候选路径：先数据目录（frozen = exe 目录），再模块目录（源码树 / _MEIPASS）。

    第二项是**只读资源兜底**：测试沙箱会把 `app_paths.data_path` 指到空目录，
    生产环境 exe 旁的 datas 缺失时也应能退回随包副本，而不是「页面打开但一条 DI 都没有」。
    """
    import pathlib

    import app_paths

    first = str(app_paths.data_path("dlt645_di.json"))
    second = str(pathlib.Path(__file__).resolve().parent / "dlt645_di.json")
    return (first,) if first == second else (first, second)


@lru_cache(maxsize=1)
def _load_merged() -> Dict[str, dict]:
    """加载并合并 DI 表（缓存）。基础表与扩展表都只经既有实现读取。"""
    import json

    import dlt645_pv_ext as pv

    base: Dict[str, dict] = {}
    for path in _di_table_candidates():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        di_map = data.get("di_map") if isinstance(data, dict) else None
        if isinstance(di_map, dict) and di_map:
            base = di_map
            break
    return pv.merge_pv_di_map(base)


def di_info(di: str) -> Dict[str, object]:
    """单条 DI 的信息（基础/扩展表查不到时回落无线手册表；未知 → 空 dict）。"""
    key = str(di or "").strip().upper()
    info = _load_merged().get(key)
    if info:
        return dict(info)
    winfo = wireless_di_info(key)
    return dict(winfo) if winfo else {}


#: 光伏扩展 DI 的识别：`02E6/03E6/04E6`（**不能只判 DI2=E6** ——
#: 结算日 DI2 也能取到 `E6`（第 230 个结算日），那是常规电能条目）
_PV_DI3 = frozenset({"02", "03", "04"})


def _is_pv_di(di: str) -> bool:
    return len(di) == 8 and di[2:4] == "E6" and di[:2] in _PV_DI3


def _item_from(di: str, info: dict) -> DiItem:
    return DiItem(
        di=di,
        name=str(info.get("name") or ""),
        unit=str(info.get("unit") or ""),
        data_type=str(info.get("data_type") or ""),
        length=int(info.get("length") or 0),
        pv=_is_pv_di(di),
    )


def _settle_bucket_label(di2: str) -> str:
    """结算日分桶标签：`05` 类 254 个结算日按 20 天一桶。"""
    try:
        day = int(di2, 16)
    except ValueError:
        return f"{di2} 类"
    start = ((day - 1) // SETTLE_BUCKET) * SETTLE_BUCKET + 1
    end = min(start + SETTLE_BUCKET - 1, 254)
    return f"结算日 {start}~{end}"


def _sub_name(di3: str, di2: str) -> str:
    if (di3, di2) in _SUB_NAMES:
        return _SUB_NAMES[(di3, di2)]
    if di3 == "04":
        try:
            month = int(di2, 16)
        except ValueError:
            month = 0
        if 1 <= month <= 12:
            return f"上{month}月电能"
    if di3 == "05":
        return _settle_bucket_label(di2)
    if di2 == "E6":
        return _PV_SUB_NAMES.get(di3, "光伏扩展")
    return f"{di2} 类"


#: DI 表里已知的 7 位残键（`dlt645_pv_ext` 生成「第1象限无功」时少写一位）：
#: 它们与标准条目 `0090xxxx` **同名**，不能当新 DI 下发 ⇒ 不进树；测试断言只可能是这些。
_MALFORMED_DI = frozenset({
    "0090000", "0090100", "0090200", "0090300", "0090400", "0090500", "0090600",
    "0090700", "0090800", "0090900", "0090A00", "0090B00", "0090C00", "0090D00",
    "0090E00", "0090F00",
})


def malformed_di_keys() -> Tuple[str, ...]:
    """DI 表里无法下发（非 8 位）的键，按字典序。"""
    return tuple(sorted(k for k in _load_merged() if len(k) != 8))


@lru_cache(maxsize=1)
def catalog() -> Tuple[Category, ...]:
    """按协议大项分类的 DI 树（顶层 → 子类 → 叶子），顺序固定、无重复。

    分组规则（全部由 DI 表前缀驱动）：
    - 常规：顶层 = DI3，子类 = DI2；
    - 结算日（DI3=05）：254 个结算日按 `SETTLE_BUCKET` 天分桶（否则 254 个子节点）；
    - 光伏扩展（DI2=E6）：独立顶层，子类按 DI3（02 变量 / 04 参数 / 03 事件）。
    """
    merged = _load_merged()
    buckets: Dict[Tuple[str, str], List[DiItem]] = {}
    labels: Dict[Tuple[str, str], str] = {}
    for di, info in merged.items():
        if len(di) != 8:
            continue                                  # 见表内残键（malformed_di_keys）
        if di in WIRELESS_DI_MAP:
            # 同一 DI 两边都有定义时**以无线手册为准**（04E60001：附件1 长度列 16 与文字
            # 描述不自洽；手册给 1+6×M 且实测帧自证）⇒ 只挂在「光伏无线扩展」下，避免重复叶子。
            continue
        di3, di2 = di[:2], di[2:4]
        if _is_pv_di(di):
            top, key = _PV_CATEGORY, f"PV{di3}"
            label = _PV_SUB_NAMES.get(di3, "光伏扩展")
        elif di3 == "05":
            try:
                day = int(di2, 16)
            except ValueError:
                continue
            top, key = di3, f"S{(day - 1) // SETTLE_BUCKET:03d}"
            label = _settle_bucket_label(di2)
        else:
            top, key = di3, di2
            label = _sub_name(di3, di2)
        buckets.setdefault((top, key), []).append(_item_from(di, info))
        labels[(top, key)] = label

    def _subs(top: str) -> Tuple[SubGroup, ...]:
        pairs = [(key, items) for (t, key), items in buckets.items() if t == top]
        pairs.sort(key=lambda kv: kv[0])
        return tuple(
            SubGroup(labels[(top, key)], tuple(sorted(items, key=lambda it: it.di)))
            for key, items in pairs
        )

    categories: List[Category] = []
    known = {d3 for d3, _ in _DI3_NAMES}
    for di3, name in _DI3_NAMES:
        subs = _subs(di3)
        if subs:
            categories.append(Category(name, subs))
    for top in sorted({t for (t, _k) in buckets if t not in known and t != _PV_CATEGORY}):
        categories.append(Category(f"其他（{top}H）", _subs(top)))
    pv_subs = _subs(_PV_CATEGORY)
    if pv_subs:
        categories.append(Category(_PV_CATEGORY, pv_subs))
    wireless = _wireless_category()
    if wireless is not None:
        categories.append(wireless)
    return tuple(categories)


def _wireless_category() -> Optional[Category]:
    """无线手册 V1.6 分类：子类 = 手册分组，叶子 = `WIRELESS_DI_MAP` 的 12 条 DI。"""
    groups: Dict[str, List[DiItem]] = {}
    order: List[str] = []
    for di, info in WIRELESS_DI_MAP.items():
        group = str(info.get("group") or "扩展")
        if group not in groups:
            groups[group] = []
            order.append(group)
        groups[group].append(DiItem(
            di=di,
            name=str(info.get("name") or ""),
            unit=str(info.get("unit") or ""),
            data_type=str(info.get("data_type") or ""),
            length=max(0, int(info.get("length") or 0)),
            wireless=True,
            note=str(info.get("note") or ""),
        ))
    if not groups:
        return None
    return Category(_WIRELESS_CATEGORY,
                    tuple(SubGroup(name, tuple(items)) for name, items in
                          ((g, groups[g]) for g in order)))


def all_items() -> Tuple[DiItem, ...]:
    """全部叶子（顺序同 `catalog`）。"""
    return tuple(it for cat in catalog() for sub in cat.subgroups for it in sub.items)


def item_count() -> int:
    return len(all_items())


@lru_cache(maxsize=512)
def find_di(di: str) -> Optional[DiItem]:
    """按 DI 查叶子（未知 → None）。"""
    key = str(di or "").strip().upper()
    for item in all_items():
        if item.di == key:
            return item
    return None


def filter_items(keyword: str) -> Tuple[DiItem, ...]:
    """按「名称 / DI 十六进制」筛选（空关键词 = 全部）。"""
    kw = str(keyword or "").strip().lower()
    if not kw:
        return all_items()
    return tuple(it for it in all_items()
                 if kw in it.name.lower() or kw in it.di.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 二、特殊命令库（字段定义直接取 schema，界面只渲染）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Command:
    """一条预置请求命令。"""

    func: int
    name: str
    hint: str
    fields: Tuple[dict, ...] = ()
    addr_default: str = DEFAULT_ADDR

    @property
    def addr_is_fixed(self) -> bool:
        """地址是否由协议规定（13H/15H = AA×6、08H = 99×6）。"""
        return self.addr_default not in (DEFAULT_ADDR, "")


@dataclass(frozen=True)
class CommandGroup:
    name: str
    commands: Tuple[Command, ...]


#: 命令分组（功能码 → 组名）；只列 schema 里真实存在的请求命令
_COMMAND_GROUPS: Tuple[Tuple[str, Tuple[int, ...]], ...] = (
    ("通信地址", (0x13, 0x15)),
    ("校时与冻结", (0x08, 0x16)),
    ("速率与密码", (0x17, 0x18)),
    ("清零（需编程键）", (0x19, 0x1A, 0x1B)),
    ("后续数据", (0x12,)),
    # 无线模组接口手册 V1.6 的扩展控制码（DL/T 645 标准里不存在，schema 已定义）
    ("无线扩展（V1.6）", (0x06, 0x1E)),
)


@lru_cache(maxsize=1)
def command_groups() -> Tuple[CommandGroup, ...]:
    """预置特殊命令（数据来自 `DLT645_CMD_SCHEMA` 的请求项）。"""
    groups: List[CommandGroup] = []
    for group_name, funcs in _COMMAND_GROUPS:
        commands: List[Command] = []
        for func in funcs:
            try:
                spec = get_command((REQ, func))
            except ValueError:
                continue
            commands.append(Command(
                func=int(func),
                name=str(spec.get("name") or FUNC_NAMES.get(func, f"命令{func:02X}")),
                hint=str(spec.get("hint") or ""),
                fields=tuple(spec.get("fields") or ()),
                addr_default=str(spec.get("addr_default") or DEFAULT_ADDR),
            ))
        if commands:
            groups.append(CommandGroup(group_name, tuple(commands)))
    return tuple(groups)


def all_commands() -> Tuple[Command, ...]:
    return tuple(c for g in command_groups() for c in g.commands)


def find_command(func: int) -> Optional[Command]:
    for cmd in all_commands():
        if cmd.func == int(func):
            return cmd
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 三、组帧（唯一实现 = DLT645FrameGenerator）
# ═══════════════════════════════════════════════════════════════════════════

def format_address(text: str) -> str:
    """地址归一化：12 位十六进制书写序（大写，去空格）；非法抛 ValueError。"""
    raw = str(text or "").strip().replace(" ", "")
    if raw[:2].lower() == "0x":
        raw = raw[2:]
    if not raw:
        raise ValueError("表地址不能为空（12 位十六进制，如 000000000001）")
    if len(raw) > 12:
        raise ValueError(f"表地址最多 12 位（当前 {len(raw)} 位）")
    try:
        int(raw, 16)
    except ValueError:
        raise ValueError(f"表地址含非法十六进制字符：{text!r}")
    return raw.rjust(12, "0").upper()


def address_from_frame(frame: bytes) -> str:
    """帧地址域 → 12 位书写序（低字节在前的线上序反转）。"""
    data = bytes(frame or b"")
    if len(data) < 7:
        return ""
    return data[1:7][::-1].hex().upper()


def build_read(di: str, addr: str = DEFAULT_ADDR,
               field_values: Optional[Dict[str, str]] = None) -> bytes:
    """读数据（11H）：数据域默认只有 DI；`02EB0000` / `FF00DD01` 需带请求参数。"""
    fv: Dict[str, object] = dict(field_values or {})
    fv["数据标识 DI"] = _di(di)
    return _gen().generate_frame((REQ, 0x11), fv, addr)


def read_request_fields(di: str) -> List[dict]:
    """读请求需要携带数据域时返回字段定义（否则空列表）。

    - `02EB0000` 光伏逆变器数据转发：DI + 波特率Z + 校验C + 超时T(BCD) + 转发数据；
    - `FF00DD01` LME 查询：DI + 条目列表。
    字段名/编码全部来自 `dlt645_frame_schema.build_di_fields`（与组帧页同源）。
    """
    key = _di(di)
    if key in READ_PAYLOAD_DI:
        return list(build_di_fields(key))
    return []


def build_read_next(di: str, addr: str = DEFAULT_ADDR, extra: bytes = b"") -> bytes:
    """读后续数据（12H）：DI + 可选附加数据。"""
    return _gen().generate_frame(
        (REQ, 0x12),
        {"数据标识 DI": _di(di), "附加数据": bytes(extra or b"").hex().upper()},
        addr,
    )


def build_write(di: str, field_values: Dict[str, object], addr: str = DEFAULT_ADDR) -> bytes:
    """写数据（14H）：DI + 密码组 + 操作者代码 + 数据；字段名与 schema 逐字一致。"""
    fv = dict(field_values or {})
    fv["数据标识 DI"] = _di(di)
    return _gen().generate_frame((REQ, 0x14), fv, addr)


def build_command(func: int, field_values: Dict[str, object],
                  addr: str = DEFAULT_ADDR) -> bytes:
    """特殊命令（13H/15H/08H/16H/17H/18H/19H/1AH/1BH/12H）。"""
    cmd = find_command(func)
    fv = dict(field_values or {})
    use_addr = command_effective_addr(cmd, addr) if cmd else addr
    return _gen().generate_frame((REQ, int(func)), fv, use_addr)


def command_effective_addr(cmd: Optional[Command], page_addr: str) -> str:
    """命令实际使用的地址：schema 规定固定地址时用它，否则用页面上的表地址。"""
    if cmd is not None and cmd.addr_is_fixed:
        return cmd.addr_default
    return page_addr


def quick_read_address() -> bytes:
    """读通信地址（13H）：地址域 AA×6，数据域为空。"""
    return build_command(0x13, {}, BROADCAST_AA)


def quick_write_address(new_addr: str) -> bytes:
    """写通信地址（15H）：地址域 AA×6，数据域 = 6 字节新地址。"""
    return build_command(0x15, {"新通信地址": format_address(new_addr)}, BROADCAST_AA)


def build_broadcast_time(when: Optional[datetime] = None) -> bytes:
    """广播校时（08H）：地址域 99×6，数据域 ss mm hh DD MM YY（留空 = 本机当前时间）。"""
    text = ""
    if when is not None:
        text = when.strftime("%Y-%m-%d %H:%M:%S")
    return build_command(0x08, {"校时时间": text}, BROADCAST_99)


def _di(di: str) -> str:
    """DI 归一化（8 位十六进制，大写）；非法抛可读 ValueError。"""
    raw = str(di or "").strip().replace(" ", "").upper()
    if len(raw) != 8:
        raise ValueError(f"数据标识 DI 应为 8 位十六进制（当前 {len(raw)} 位）：{di!r}")
    try:
        int(raw, 16)
    except ValueError:
        raise ValueError(f"数据标识 DI 含非法十六进制字符：{di!r}")
    return raw


def write_fields(di: str) -> List[dict]:
    """写数据页的动态字段（按 DI 的 data_type 掩码生成；与协议组帧页同源）。"""
    return list(build_di_fields(_di(di)))


def length_warning(di: str, field_values: Dict[str, object]) -> str:
    """写数据时的长度提示（不阻断；无提示返回空串）。"""
    from dlt645_frame_schema import length_warning as _lw

    fv = dict(field_values or {})
    fv["数据标识 DI"] = _di(di)
    return _lw((REQ, 0x14), fv)


# ═══════════════════════════════════════════════════════════════════════════
# 四、解析与响应判定
# ═══════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _parser():
    from dlt645_parser import DLT645Parser

    return DLT645Parser()


@lru_cache(maxsize=1)
def _gui_parser():
    from protocol_registry import DLT645GuiParser

    return DLT645GuiParser(_parser())


def parse_frame(frame: bytes) -> dict:
    """整帧 → `DLT645Parser.parse` 结果（异常时给最小 dict，不抛）。"""
    try:
        return _parser().parse(bytes(frame or b""))
    except Exception as exc:                       # noqa: BLE001 —— 展示层绝不崩
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}", "fields": []}


def parse_table(frame: bytes) -> list:
    """整帧 → 逐字段表格（`DLT645GuiParser.parse_to_table`，含前导 FEH 行）。"""
    try:
        return _gui_parser().parse_to_table(bytes(frame or b""))
    except Exception:                              # noqa: BLE001
        return []


def detail_lines(frame: bytes, title: str = "帧结构") -> List[str]:
    """整帧 → 对齐的四列明细（含「共 N 行」头）。"""
    rows = parse_table(frame)
    if not rows:
        return [f"（{title}：没有可解析的字段，可能不是完整的 DL/T645 帧）"]
    return format_table_rows(rows, header=f"{title}（{len(rows)} 行）")


def format_hex(data: bytes, limit: int = 0) -> str:
    """HEX 文本（`limit` > 0 时头尾各留一半，省略中间 —— 与升级页同一口径）。"""
    raw = bytes(data or b"")
    text = " ".join(f"{b:02X}" for b in raw)
    if limit and len(raw) > limit:
        head = limit // 2
        tail = limit - head
        text = (" ".join(f"{b:02X}" for b in raw[:head]) + " ... "
                + " ".join(f"{b:02X}" for b in raw[-tail:]) + f" (共 {len(raw)} 字节)")
    return text


def parse_hex(text: str) -> bytes:
    """宽松 HEX 解析（分隔符 / `0x` / 连续写法），非法抛可读 ValueError。"""
    from dlt645_data_codec import parse_hex as _parse

    return _parse(text)


def _wireless_value_text(parsed: dict) -> str:
    """无线手册 DI 的应答取值：用 `parse_wireless_di` 的行解码拼前 3 个字段。"""
    di = str(parsed.get("di_code") or "")
    data = parsed.get("data") or b""
    if not di or not data:
        return ""
    try:
        rows, _name = _parse_wireless_di(di, int(parsed.get("control") or 0), data)
    except Exception:                                  # noqa: BLE001 —— 解码失败回落 HEX
        return ""
    pairs: List[str] = []
    for row in rows or ():
        label = str(row[0]).strip(" └")
        if not label or "数据块" in label:
            continue
        value = str(row[2] or "").strip()
        if value:
            pairs.append(f"{label}={value}")
    return "；".join(pairs[:3])


def _read_value_text(parsed: dict) -> str:
    """读应答的取值文本：无线手册 DI 走无线解码，其余按 DI 的 data_type 解码。"""
    di = str(parsed.get("di_code") or "")
    if di and wireless_di_info(di):
        text = _wireless_value_text(parsed)
        if text:
            return text
    return _value_text(parsed)


def _value_text(parsed: dict) -> str:
    """按 DI 的 data_type 把数据域解成可读值（失败回落 HEX）。"""
    data = parsed.get("data") or b""
    di = str(parsed.get("di_code") or "")
    if not di or len(data) < 4:
        return ""
    body = data[4:]
    info = di_info(di)
    dtype = str(info.get("data_type") or "")
    unit = str(info.get("unit") or "")
    if dtype:
        try:
            text = decode_value(body, dtype, unit)
        except Exception:                          # noqa: BLE001 —— 解码失败不影响判定
            text = ""
        if text:
            return text
    return body.hex(" ").upper()


def evaluate_response(frame: bytes, expect: Dict[str, object]) -> Dict[str, object]:
    """应答判定 → ``{status, code, summary, lines, address, di, value_text}``。

    ``expect``: ``{"func": int, "di": str|None, "kind": "read|write|command|address",
    "no_reply": bool}``。任何一步不满足即「失败」+ 可读原因，但**仍返回明细行**；
    缺失证据时给「失败/无法判定」而不是冒充成功（AGENTS §8 陷阱 23 精神）。
    """
    out: Dict[str, object] = {
        "status": RESULT_FAIL,
        "code": "",
        "summary": "",
        "lines": detail_lines(frame),
        "address": "",
        "di": "",
        "value_text": "",
    }
    if expect.get("no_reply"):
        out["status"] = RESULT_NO_REPLY
        out["summary"] = "该命令无需应答（广播/校时类），已发送"
        return out

    parsed = parse_frame(frame)
    if parsed.get("error") and not parsed.get("fields"):
        out["summary"] = f"无法解析：{parsed.get('error')}"
        return out
    ctrl = int(parsed.get("control") or 0)
    out["code"] = f"C=0x{ctrl:02X} {FUNC_NAMES.get(ctrl & 0x1F, '')}".strip()
    if not parsed.get("structure_valid", False):
        out["summary"] = f"帧结构错误：{parsed.get('structure_error') or '结构不自洽'}"
        return out
    if not parsed.get("checksum_valid", False):
        out["summary"] = (f"校验和错误（帧内 0x{int(parsed.get('checksum') or 0):02X}，"
                          f"按帧内容应为 0x{int(parsed.get('checksum_expected') or 0):02X}）")
        return out
    if not ctrl & 0x80:
        out["summary"] = "不是从站应答（控制码 D7=0）"
        return out
    func = ctrl & 0x1F
    want = int(expect.get("func") or 0)
    if want and func != want:
        out["summary"] = f"应答功能码 0x{func:02X}，期望 0x{want:02X}"
        return out
    if ctrl & 0x40:
        err_text = decode_err(parsed.get("data") or b"") or "未知错误"
        out["summary"] = f"异常应答：{err_text}"
        return out

    kind = str(expect.get("kind") or "command")
    if kind == "address":
        addr = str(parsed.get("address_in_data") or "")
        if not addr:
            out["summary"] = "读通信地址应答里没有 6 字节地址"
            return out
        out.update(status=RESULT_OK, address=addr,
                   summary=f"读通信地址成功：{addr}")
        return out

    di = str(parsed.get("di_code") or "")
    out["di"] = di
    want_di = str(expect.get("di") or "").upper()
    if want_di:
        if not di:
            out["summary"] = "应答数据域缺少数据标识 DI"
            return out
        if di != want_di:
            out["summary"] = (f"应答 DI {di} 与请求 {want_di} 不一致"
                              f"（{parsed.get('di_desc') or '未知数据标识'}）")
            return out

    desc = str(parsed.get("di_desc") or "")
    if kind in ("read", "write"):
        value = _read_value_text(parsed) if kind == "read" else ""
        out["value_text"] = value
        if kind == "read":
            out["summary"] = (f"{di} {desc or '未知数据标识'}"
                              + (f" = {value}" if value else "（无数据值）"))
        else:
            out["summary"] = f"写数据成功：{di} {desc or '未知数据标识'}"
        out["status"] = RESULT_OK
        return out

    out["status"] = RESULT_OK
    out["summary"] = desc or f"应答成功（{out['code']}）"
    return out


__all__ = [
    "BROADCAST_99",
    "BROADCAST_AA",
    "Category",
    "Command",
    "CommandGroup",
    "DEFAULT_ADDR",
    "DiItem",
    "RESULT_FAIL",
    "RESULT_NO_REPLY",
    "RESULT_OK",
    "RESULT_PENDING",
    "RESULT_TIMEOUT",
    "SETTLE_BUCKET",
    "SubGroup",
    "address_from_frame",
    "all_commands",
    "all_items",
    "build_broadcast_time",
    "build_command",
    "build_read",
    "build_read_next",
    "build_write",
    "catalog",
    "command_effective_addr",
    "command_groups",
    "detail_lines",
    "di_info",
    "evaluate_response",
    "filter_items",
    "find_command",
    "find_di",
    "format_address",
    "format_hex",
    "item_count",
    "length_warning",
    "parse_frame",
    "parse_hex",
    "parse_table",
    "quick_read_address",
    "quick_write_address",
    "write_fields",
]
