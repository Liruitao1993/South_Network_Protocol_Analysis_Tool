# -*- coding: utf-8 -*-
"""国网协议（Q/GDW 10376.2—2024）「协议测试」页纯逻辑层。

职责（**禁止 import Qt**）：
- 分类树：按功能域 → AFN → Fn 组织 `GDW_AFNFN_SCHEMA` 的 122 条命令（含福建增补 50H~56H、F0/F1 扩展）；
- EB 扩展：附件1 的 75 条 EB 数据标识，按前缀分组；构造 645 帧（DI 低字节在前、数据域 +0x33 加扰）；
- 组帧：一律委托 `GDWFrameGenerator`（唯一实现，不手拼国网帧）；
- 判定：只读 `GDW10376Parser.parse_to_table` 的行 + `verify`，**不新增协议判据**；
- 文本/地址/hex 工具：GUI 与测试共用。

单一来源约束见任务 design.md §1；改这里前先确认对应数据源没有第二份副本。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from gdw_frame_generator_schema import GDW_AFNFN_SCHEMA
from gdw_send_frame_lib import GDWFrameGenerator
from gdw10376_parser import GDW10376Parser

# ── 页面 ────────────────────────────────────────────────────────────────
PAGE_READ = "read"
PAGE_WRITE = "write"
PAGE_REPORT = "report"
PAGE_EB = "eb"
PAGE_CUSTOM = "custom"

PAGES: Tuple[Tuple[str, str], ...] = (
    (PAGE_READ, "读取数据"),
    (PAGE_WRITE, "设置控制"),
    (PAGE_REPORT, "主动上报"),
    (PAGE_EB, "EB 扩展"),
    (PAGE_CUSTOM, "自定义"),
)
PAGE_LABELS: Dict[str, str] = dict(PAGES)

#: AFN → 页面（**必须恰好覆盖 `AFN_MAP` 全部 AFN，且互斥**；测试有断言）
AFN_PAGE: Dict[int, str] = {
    0x03: PAGE_READ, 0x04: PAGE_READ, 0x10: PAGE_READ, 0x14: PAGE_READ,
    0x53: PAGE_READ, 0xF0: PAGE_READ,
    0x01: PAGE_WRITE, 0x02: PAGE_WRITE, 0x05: PAGE_WRITE, 0x11: PAGE_WRITE,
    0x12: PAGE_WRITE, 0x13: PAGE_WRITE, 0x15: PAGE_WRITE, 0x51: PAGE_WRITE,
    0x52: PAGE_WRITE, 0x55: PAGE_WRITE, 0xF1: PAGE_WRITE,
    0x00: PAGE_REPORT, 0x06: PAGE_REPORT, 0x50: PAGE_REPORT, 0x56: PAGE_REPORT,
}

#: 功能域（三级树的第一级）：AFN → 域
AFN_DOMAIN: Dict[int, str] = {}
for _afn in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06):
    AFN_DOMAIN[_afn] = "基础功能"
for _afn in (0x10, 0x11, 0x12, 0x13, 0x14, 0x15):
    AFN_DOMAIN[_afn] = "路由与数据"
for _afn in (0x50, 0x51, 0x52, 0x53, 0x55, 0x56):
    AFN_DOMAIN[_afn] = "福建增补"
AFN_DOMAIN[0xF0] = "扩展命令"
AFN_DOMAIN[0xF1] = "扩展命令"

DOMAIN_ORDER = ("基础功能", "路由与数据", "福建增补", "扩展命令", "EB 扩展", "用户自定义")

#: EB 分组（DI 第 3 字节）
EB_GROUP_NAMES: Dict[str, str] = {
    "EB03": "事件与状态",
    "EB04": "参数与统计",
    "EB55": "功能映射",
    "EBE0": "任务配置",
    "EBEE": "多数据项",
}
EB_GROUP_ORDER = ("EB03", "EB04", "EBE0", "EB55", "EBEE")

#: 国网默认信息域（下行、启动站）
DEFAULT_INFO: Dict[str, int] = {
    "路由标识": 0, "附属节点标识": 0, "通信模块标识": 1, "冲突检测": 0,
    "中继级别": 0, "纠错编码标识": 0, "信道标识": 0, "预计应答字节数": 0,
    "通信速率": 0, "速率单位标识": 0, "报文序列号": 1,
    "dir": 0, "prm": 1, "通信方式": 0,
}

FUJIAN_AFNS = frozenset({0x50, 0x51, 0x52, 0x53, 0x55, 0x56})


class FrameBuildError(ValueError):
    """组帧前的输入错误（中文可读原因，直接展示给用户）。"""


# ── 数据模型 ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GdwCommand:
    afn: int
    fn: int
    name: str
    direction: str                      # "down" / "up"
    fields: Tuple[Dict[str, Any], ...] = ()
    doc: str = ""
    source: str = "标准"

    @property
    def key(self) -> str:
        """命令键（`AFN-Fn`，如 `03-1`；避免 `F1`/`F10` 拼成同一串）。"""
        return f"{self.afn:02X}-{self.fn}"

    @property
    def label(self) -> str:
        arrow = "下行" if self.direction == "down" else "上行"
        return f"{self.afn:02X}H F{self.fn} {self.name}（{arrow}）"


@dataclass(frozen=True)
class EbItem:
    di: str
    name: str
    fmt: str
    length: int
    usage: str
    fields: Tuple[Dict[str, Any], ...] = ()

    @property
    def key(self) -> str:
        return self.di

    @property
    def label(self) -> str:
        ln = f"{self.length}B" if self.length else "不定长"
        return f"{self.di} {self.name}（{self.fmt}/{ln}）"


@dataclass(frozen=True)
class SubGroup:
    key: str
    name: str
    items: Tuple[Any, ...] = ()


@dataclass(frozen=True)
class Category:
    name: str
    groups: Tuple[SubGroup, ...] = ()


# ── 单一来源读取 ────────────────────────────────────────────────────────
def afn_name(afn: int) -> str:
    return GDW10376Parser.AFN_MAP.get(afn, f"AFN {afn:02X}H")


def fn_name(afn: int, fn: int) -> str:
    return GDW10376Parser.FN_MAP.get(afn, {}).get(fn, f"F{fn}")


def command_source(afn: int) -> str:
    if afn in FUJIAN_AFNS:
        return "福建增补"
    if afn >= 0xF0:
        return "扩展"
    return "标准"


def _command(afn: int, fn: int, entry: Mapping[str, Any],
             source: Optional[str] = None) -> GdwCommand:
    return GdwCommand(
        afn=afn, fn=fn,
        name=str(entry.get("name") or fn_name(afn, fn)),
        direction=str(entry.get("direction") or "down"),
        fields=tuple(entry.get("fields") or ()),
        doc=str(entry.get("doc") or ""),
        source=source or command_source(afn),
    )


def all_commands() -> List[GdwCommand]:
    """全部 (AFN, Fn) 命令（按 AFN、Fn 升序）。"""
    return [_command(a, f, e) for (a, f), e in sorted(GDW_AFNFN_SCHEMA.items())]


def commands_for_page(page: str) -> List[GdwCommand]:
    return [c for c in all_commands() if AFN_PAGE.get(c.afn) == page]


def find_command(afn: int, fn: int) -> Optional[GdwCommand]:
    e = GDW_AFNFN_SCHEMA.get((afn, fn))
    return _command(afn, fn, e) if e else None


def custom_commands() -> List[GdwCommand]:
    """用户自定义 AFN+Fn（`gdw_custom_afn.json`，解析器的唯一读取入口）。"""
    out: List[GdwCommand] = []
    try:
        entries = GDW10376Parser().get_custom_entries()
    except Exception:
        return out
    for afn, fns in (entries or {}).items():
        try:
            a = int(afn)
        except (TypeError, ValueError):
            continue
        for fn, name in (fns or {}).items():
            try:
                f = int(fn)
            except (TypeError, ValueError):
                continue
            schema = GDW_AFNFN_SCHEMA.get((a, f), {})
            out.append(GdwCommand(
                afn=a, fn=f, name=str(name or schema.get("name") or f"F{f}"),
                direction=str(schema.get("direction") or "down"),
                fields=tuple(schema.get("fields") or ()),
                doc=str(schema.get("doc") or "用户自定义 AFN+Fn（gdw_custom_afn.json）"),
                source="自定义",
            ))
    return out


def eb_items() -> List[EbItem]:
    from gdw_eb_di_lookup import get_eb_di_lookup
    from gdw_eb_di_fields import EB_DI_FIELDS

    lookup = get_eb_di_lookup()
    out: List[EbItem] = []
    for di, info in sorted((lookup.EB_DI_MAP or {}).items()):
        defined = EB_DI_FIELDS.get(di) or {}
        out.append(EbItem(
            di=di,
            name=str(info.get("名称") or di),
            fmt=str(info.get("格式") or "XX"),
            length=int(info.get("长度") or 0),
            usage=str(info.get("功能") or ""),
            fields=tuple(defined.get("fields") or ()),
        ))
    return out


def eb_groups() -> List[Tuple[str, str, List[EbItem]]]:
    grouped: Dict[str, List[EbItem]] = {}
    for item in eb_items():
        prefix = item.di[:4]
        grouped.setdefault(prefix, []).append(item)
    order = [p for p in EB_GROUP_ORDER if p in grouped]
    order += [p for p in sorted(grouped) if p not in order]
    return [(p, EB_GROUP_NAMES.get(p, p), grouped[p]) for p in order]


def catalog(page: str) -> List[Category]:
    """按页面生成三级分类树。未知 page 返回空表。"""
    if page == PAGE_EB:
        groups = tuple(SubGroup(key=p, name=f"{p} {name}", items=tuple(items))
                       for p, name, items in eb_groups())
        return [Category("EB 扩展", groups)] if groups else []
    if page == PAGE_CUSTOM:
        items = tuple(custom_commands())
        return [Category("用户自定义", (SubGroup("CUSTOM", "自定义 AFN+Fn", items),))] if items else []
    cmds = commands_for_page(page)
    if not cmds:
        return []
    by_domain: Dict[str, List[GdwCommand]] = {}
    for c in cmds:
        by_domain.setdefault(AFN_DOMAIN.get(c.afn, "其他"), []).append(c)
    cats: List[Category] = []
    for domain in DOMAIN_ORDER:
        if domain not in by_domain:
            continue
        by_afn: Dict[int, List[GdwCommand]] = {}
        for c in by_domain[domain]:
            by_afn.setdefault(c.afn, []).append(c)
        groups = tuple(
            SubGroup(key=f"{a:02X}", name=f"{a:02X}H {afn_name(a)}", items=tuple(items))
            for a, items in sorted(by_afn.items())
        )
        cats.append(Category(domain, groups))
    return cats


def leaf_count(page: Optional[str] = None) -> int:
    if page == PAGE_EB:
        return len(eb_items())
    if page == PAGE_CUSTOM:
        return len(custom_commands())
    if page:
        return len(commands_for_page(page))
    return len(all_commands())


def item_count() -> int:
    return len(all_commands())


# ── hex / 地址工具 ──────────────────────────────────────────────────────
_SEPARATORS = " ,;\t\r\n，；、/|-－_"


def parse_hex(text: str) -> bytes:
    """宽松解析 hex（分隔符/0x/连续写法），奇数位或非法字符抛 FrameBuildError。"""
    raw = (text or "").strip()
    if not raw:
        return b""
    cleaned = raw.replace("0x", "").replace("0X", "")
    for ch in _SEPARATORS:
        cleaned = cleaned.replace(ch, "")
    if not cleaned:
        return b""
    bad = sorted({c for c in cleaned if c not in "0123456789abcdefABCDEF"})
    if bad:
        raise FrameBuildError(f"含非 HEX 字符：{' '.join(bad)}")
    if len(cleaned) % 2:
        raise FrameBuildError(f"HEX 位数必须成对（当前 {len(cleaned)} 位）")
    return bytes.fromhex(cleaned)


def format_hex(data: bytes, sep: str = " ") -> str:
    return sep.join(f"{b:02X}" for b in data)


def addr_ok(text: str) -> bool:
    t = (text or "").strip()
    return len(t) == 12 and t.isdigit()


def normalize_addr(text: str, default: str = "000000000000") -> str:
    t = (text or "").strip().replace(" ", "")
    return t if addr_ok(t) else default


# ── 组帧 ────────────────────────────────────────────────────────────────
def _enum_value(fld: Mapping[str, Any], value: Any) -> Any:
    """把界面上的显示文本/键名归一化成整数（enum_map 的键是字符串）。"""
    emap = fld.get("enum_map") or {}
    if value in emap:                     # 已经给的是键
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    for k, label in emap.items():
        if str(label) == str(value):
            try:
                return int(k)
            except (TypeError, ValueError):
                break
    try:
        return int(value)
    except (TypeError, ValueError):
        raise FrameBuildError(f"字段「{fld.get('name')}」需要枚举值：{value!r}")


def normalize_values(fields: Sequence[Mapping[str, Any]],
                     values: Mapping[str, Any]) -> Dict[str, Any]:
    """按 schema 把界面值转成生成器要的形态（enum→int、bytes→hex 串、list→list[dict]）。"""
    out: Dict[str, Any] = {}
    for fld in fields:
        name = fld.get("name")
        val = values.get(name, fld.get("default"))
        ftype = fld.get("type")
        if ftype == "enum":
            out[name] = _enum_value(fld, val)
        elif ftype == "bytes":
            if isinstance(val, (bytes, bytearray)):
                out[name] = bytes(val).hex().upper()
            else:
                out[name] = ("" if val is None else str(val))
        elif ftype == "list":
            rows = val if isinstance(val, list) else []
            fixed: List[Dict[str, Any]] = []
            for row in rows:
                item: Dict[str, Any] = {}
                for sub in fld.get("item_fields") or ():
                    sub_name = sub.get("name")
                    sub_val = (row or {}).get(sub_name, sub.get("default"))
                    if sub.get("type") == "enum":
                        sub_val = _enum_value(sub, sub_val)
                    item[sub_name] = sub_val
                fixed.append(item)
            out[name] = fixed
        elif ftype == "uint8":
            out[name] = _to_int(val, name, 0, 255)
        elif ftype == "uint16":
            out[name] = _to_int(val, name, 0, 0xFFFF)
        elif ftype == "uint32":
            out[name] = _to_int(val, name, 0, 0xFFFFFFFF)
        else:
            out[name] = val
    return out


def _to_int(value: Any, name: Any, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise FrameBuildError(f"字段「{name}」需要整数：{value!r}")
    if not (low <= n <= high):
        raise FrameBuildError(f"字段「{name}」超出范围 {low}~{high}：{n}")
    return n


def validate_values(cmd: GdwCommand, values: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """返回 [(字段名, 可读原因)]；空列表表示可以组帧。"""
    errors: List[Tuple[str, str]] = []
    try:
        normalized = normalize_values(cmd.fields, values)
    except FrameBuildError as exc:
        return [("-", str(exc))]
    for fld in cmd.fields:
        name = fld.get("name")
        ftype = fld.get("type")
        val = normalized.get(name)
        if ftype == "bytes" and val:
            try:
                parse_hex(str(val))
            except FrameBuildError as exc:
                errors.append((str(name), str(exc)))
        if ftype == "bcd":
            text = ("" if val is None else str(val)).replace(" ", "")
            if text and any(c not in "0123456789abcdefABCDEF" for c in text):
                errors.append((str(name), "BCD 字段只接受十六进制字符"))
    return errors


def build_frame(cmd: GdwCommand, values: Mapping[str, Any], *,
                src: str = "000000000000", dst: str = "000000000000",
                relay: Sequence[str] = (),
                info: Optional[Mapping[str, Any]] = None,
                auto_lengths: bool = True,
                raw_data: bytes = b"") -> bytes:
    """组帧（唯一实现：`GDWFrameGenerator.generate_frame`）。

    `auto_lengths=True` 时自动补 `报文长度`/`从节点附属节点数量`/`从节点数量` 这类
    由内容派生的字段，避免用户手填出错（生成器本身不推导）。

    `raw_data` 非空时**追加在数据单元之后**（上行应答命令在 schema 里没有字段，
    页面用「数据单元(HEX)」交给它；下行命令不要用）。
    """
    if not addr_ok(src) or not addr_ok(dst):
        raise FrameBuildError("源/目的地址必须是 12 位十进制数字")
    for r in relay:
        if not addr_ok(r):
            raise FrameBuildError(f"中继地址必须是 12 位十进制数字：{r}")
    merged_info = dict(DEFAULT_INFO)
    if info:
        merged_info.update({k: v for k, v in info.items() if v is not None})
    normalized = normalize_values(cmd.fields, values)
    if auto_lengths:
        _apply_derived_lengths(cmd.fields, normalized)
    try:
        return GDWFrameGenerator().generate_frame(
            cmd.afn, cmd.fn, normalized, merged_info,
            src, dst, list(relay), extra_data=bytes(raw_data or b""),
        )
    except FrameBuildError:
        raise
    except Exception as exc:                      # 生成器的 ValueError 等 → 可读原因
        raise FrameBuildError(f"组帧失败：{type(exc).__name__}: {exc}") from exc


def _apply_derived_lengths(fields: Sequence[Mapping[str, Any]],
                           values: Dict[str, Any]) -> None:
    """按 schema 的 `count_field`/`length_field` 回填派生字段（内容长度优先）。"""
    for fld in fields:
        if fld.get("type") != "bytes":
            continue
        target = fld.get("length_field")
        if not target or target not in values:
            continue
        try:
            n = len(parse_hex(str(values.get(fld.get("name")) or "")))
        except FrameBuildError:
            continue
        values[target] = n if 0 <= n <= 0xFF else values.get(target)
    for fld in fields:
        if fld.get("type") != "list":
            continue
        target = fld.get("count_field")
        if target and target in values:
            values[target] = len(values.get(fld.get("name")) or [])


def default_values(cmd: GdwCommand) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for fld in cmd.fields:
        ftype = fld.get("type")
        name = fld.get("name")
        if ftype == "list":
            out[name] = []
        elif ftype == "enum":
            d = fld.get("default", 0)
            out[name] = d
        else:
            out[name] = fld.get("default", "" if ftype in ("bytes", "ascii") else 0)
    return out


# ── EB 扩展（645 帧） ───────────────────────────────────────────────────
def _bcd645(text: str) -> bytes:
    """12 位十进制 → 6 字节 BCD（低字节在前）。"""
    t = (text or "").strip()
    if not addr_ok(t):
        raise FrameBuildError("645 地址必须是 12 位十进制数字")
    out = bytearray()
    for i in range(10, -1, -2):
        out.append(int(t[i:i + 2], 16))       # 每两个数字 → 1 BCD 字节
    return bytes(out)


def _scramble(data: bytes) -> bytes:
    return bytes((b + 0x33) & 0xFF for b in data)


def _di_wire(di: str) -> bytes:
    """DI 线上序：低字节在前（EB030001 → 01 00 03 EB）。"""
    t = (di or "").strip().upper().replace(" ", "")
    if len(t) != 8 or any(c not in "0123456789ABCDEF" for c in t):
        raise FrameBuildError(f"EB 数据标识格式不对：{di!r}（需 8 位十六进制）")
    return bytes.fromhex(t)[::-1]


def build_eb_645(di: str, *, addr: str, ctrl: int = 0x11,
                 data: bytes = b"") -> bytes:
    """构造读写 EB 数据标识的 645 帧（数据域逐字节 +0x33）。"""
    if ctrl not in (0x11, 0x13, 0x14):
        raise FrameBuildError(f"EB 命令控制码只支持 11H 读 / 14H 写 / 13H 读后续：0x{ctrl:02X}")
    payload = _di_wire(di) + bytes(data or b"")
    scrambled = _scramble(payload)
    head = b"\x68" + _bcd645(addr) + b"\x68" + bytes([ctrl, len(scrambled)]) + scrambled
    cs = sum(head) & 0xFF
    return head + bytes([cs, 0x16])


def encode_eb_data(di: str, values: Mapping[str, Any]) -> bytes:
    from gdw_eb_di_fields import encode_eb_di_data
    try:
        return encode_eb_di_data(di, dict(values))
    except Exception as exc:
        raise FrameBuildError(f"EB 数据内容编码失败：{type(exc).__name__}: {exc}") from exc


def build_eb_frame(di: str, *, addr: str, ctrl: int = 0x11,
                   data: bytes = b"", wrap: bool = True,
                   src: str = "000000000000", dst: str = "000000000000",
                   info: Optional[Mapping[str, Any]] = None) -> bytes:
    """EB 命令帧：`wrap=True` 时作为 `AFN=02H F1` 转发帧的报文内容下发。"""
    inner = build_eb_645(di, addr=addr, ctrl=ctrl, data=data)
    if not wrap:
        return inner
    cmd = find_command(0x02, 1)
    if cmd is None:
        raise FrameBuildError("缺少 AFN=02H F1 转发命令定义")
    return build_frame(cmd, {
        "通信协议类型": 2,                     # DL/T 645-2007
        "报文长度": len(inner),
        "报文内容": format_hex(inner),
    }, src=src, dst=dst, info=info)


# ── 解析 / 判定 ─────────────────────────────────────────────────────────
def _row_value(rows: Sequence[Tuple], name: str) -> Optional[Tuple]:
    for row in rows or ():
        if len(row) >= 4 and str(row[0]).strip() == name:
            return row
    return None


def _row_int(row: Optional[Tuple]) -> Optional[int]:
    if not row:
        return None
    try:
        return int(row[2])
    except (TypeError, ValueError):
        try:
            return int(str(row[1]).replace("0x", ""), 16)
        except (TypeError, ValueError):
            return None


def _row_fn(row: Optional[Tuple]) -> Optional[int]:
    if not row:
        return None
    text = f"{row[2]} {row[3]}"
    import re
    m = re.search(r"F(\d+)\s*=", text)
    return int(m.group(1)) if m else None


def parse_table(frame: bytes) -> List[Tuple]:
    """国网解析表格（GUI 与判定共用；解析器唯一入口）。"""
    try:
        return list(GDW10376Parser().parse_to_table(bytes(frame or b"")))
    except Exception:
        return []


def verify_frame(frame: bytes):
    try:
        return GDW10376Parser().verify(bytes(frame or b""))
    except Exception:
        return None


def evaluate_response(cmd: GdwCommand, frame: bytes) -> Dict[str, Any]:
    """判定一帧是否为 `cmd` 的响应以及是否成功。

    返回 `{ok, matched, reason, rows}`：`ok=None` 表示「是这条命令的响应，但没有可自证的
    成功/失败字段」，**不得由调用方当成成功**。
    """
    rows = parse_table(frame)
    out: Dict[str, Any] = {"ok": None, "matched": False, "reason": "", "rows": rows}
    if not rows:
        out["ok"] = False
        out["reason"] = "无法解析（帧长不足或结构不认识）"
        return out

    # 1) 结构/校验：只看失败项，避免把「⚠ 长度域」这类提示判成坏帧
    result = verify_frame(frame)
    if result is not None:
        for item in getattr(result, "checks", ()) or ():
            level = str(getattr(item, "level", "")).lower()
            if "fail" in level:
                out["ok"] = False
                out["reason"] = f"{item.name}未通过：{item.message}"
                return out
    start = _row_value(rows, "结束字符")
    if start is None:
        out["ok"] = False
        out["reason"] = "缺少结束字符 16H（截断或非国网帧）"
        return out
    cs = _row_value(rows, "校验和(CS)")
    if cs is None or not str(cs[3] or "").startswith("校验正确"):
        out["ok"] = False
        out["reason"] = "校验和未通过"
        return out

    # 2) AFN / Fn 回显
    afn_val = _row_int(_row_value(rows, "应用功能码(AFN)"))
    if afn_val is None:
        out["ok"] = False
        out["reason"] = "缺少应用功能码(AFN)行"
        return out
    if afn_val != cmd.afn:
        out["reason"] = f"AFN 不符：收到 {afn_val:02X}H，期望 {cmd.afn:02X}H"
        return out
    fn_val = _row_fn(_row_value(rows, "数据单元标识(DT)"))
    if fn_val is not None and fn_val != cmd.fn:
        out["reason"] = f"Fn 不符：收到 F{fn_val}，期望 F{cmd.fn}"
        return out
    out["matched"] = True

    # 3) 语义判定（只用解析器已经给出的字段，不新增协议判据）
    err = _row_int(_row_value(rows, "错误代码"))
    if err is None:
        err = _row_int(_row_value(rows, "错误状态字"))
    if err is not None:
        desc = ""
        for name in ("错误代码", "错误状态字"):
            row = _row_value(rows, name)
            if row:
                desc = str(row[3] or "")
                break
        out["ok"] = err == 0
        out["reason"] = f"错误{'代码' if _row_value(rows, '错误代码') else '状态字'}=0x{err:02X}" + (
            f"（{desc}）" if desc else "")
        return out

    if cmd.afn in (0x00, 0x50):
        if cmd.fn in (1, 3):
            out["ok"] = True
            out["reason"] = "确认" + ("（还有后续任务）" if cmd.fn == 3 else "")
            return out
        if cmd.fn == 2:
            out["ok"] = False
            out["reason"] = "否认（设备拒绝执行）"
            return out

    confirm = _row_value(rows, "确认/否认")
    if confirm is not None:
        text = f"{confirm[2]} {confirm[3]}"
        out["ok"] = "确认" in str(confirm[2]) or "确认" in text
        out["reason"] = text.strip() or "确认/否认"
        return out

    out["reason"] = "已收到同命令响应，未做字段级判定"
    return out


def response_summary(rows: Sequence[Tuple]) -> str:
    if not rows:
        return ""
    afn = _row_value(rows, "应用功能码(AFN)")
    dt = _row_value(rows, "数据单元标识(DT)")
    parts: List[str] = []
    if afn:
        parts.append(str(afn[3] or afn[2]))
    if dt:
        parts.append(str(dt[3] or dt[2]))
    for row in rows:
        name = str(row[0]).strip()
        if not name or name.startswith(("起始", "长度域", "控制域", "D", "信息域", "地址域",
                                        "应用功能码", "数据单元标识", "校验和", "结束字符",
                                        "源地址", "目的地址", "报文序列号", "预计应答", "通信速率")):
            continue
        val = str(row[2] or row[3] or "").strip()
        if val:
            parts.append(f"{name}={val}")
        if len(parts) >= 4:
            break
    return " | ".join(parts)


def detail_lines(rows: Sequence[Tuple], max_lines: int = 0) -> List[str]:
    from testpage_render import format_table_rows
    lines = list(format_table_rows(rows) or [])
    if max_lines and max_lines > 0 and len(lines) > max_lines:
        lines = lines[:max_lines] + [f"…（已省略 {len(lines) - max_lines} 行）"]
    return lines


__all__ = [
    "PAGE_READ", "PAGE_WRITE", "PAGE_REPORT", "PAGE_EB", "PAGE_CUSTOM",
    "PAGES", "PAGE_LABELS", "AFN_PAGE", "AFN_DOMAIN", "EB_GROUP_NAMES",
    "DEFAULT_INFO", "FrameBuildError",
    "GdwCommand", "EbItem", "SubGroup", "Category",
    "afn_name", "fn_name", "command_source", "all_commands", "commands_for_page",
    "find_command", "custom_commands", "eb_items", "eb_groups", "catalog",
    "leaf_count", "item_count",
    "parse_hex", "format_hex", "addr_ok", "normalize_addr",
    "normalize_values", "validate_values", "build_frame", "default_values",
    "build_eb_645", "encode_eb_data", "build_eb_frame", "_di_wire", "_bcd645",
    "parse_table", "verify_frame", "evaluate_response", "response_summary", "detail_lines",
]
