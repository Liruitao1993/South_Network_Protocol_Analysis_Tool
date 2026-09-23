"""模组化终端功能模块接口协议解析器（协议12 / Q/GDW 模组化终端功能模块接口协议）。

协议文档（唯一权威）：`协议文档/12.模组化功能协议/模组化终端功能模块接口协议.md`

链路层（§5.2，**小端**）：
    68H | 长度域L(2B, LE, bit0~11=数据域字节数，bit12~15 保留) | 控制域C(2B, LE)
    | 数据域(L) | FCS(2B, LE) | 16H
    整帧长度 = L + 8；FCS 覆盖 L+C+数据域（§5.2.5，算法见附录 A）。

控制域（图6）：
    低字节 = DIR(bit7) | PRM(bit6) | 控制码(bit5~0)；高字节 = 帧序号 FID。
    表1 的 DIR/PRM 组合意义 4 种；表2 控制码 00H 确认 / 01H 否认 / 02H 信息。

应用层（§6，**大端 A-XDR**）：8 类 APDU（表13）与 25 类 Data（表5）的编解码
**一律走 `modular_iface_axdr` 单源**，静态表名走 `modular_iface_data` 单源。

容错契约（AGENTS.md §8 陷阱 23）：长度不符 / FCS 不符 / 截断 / A-XDR 解不动时，
**仍输出已能解析的字段**并插入醒目的 `⚠` 行，同时告诉用户正确值；**绝不返回空表**。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from modular_iface_axdr import (  # noqa: F401  (F401: 供 validator / GUI / 测试 import)
    APDU_BY_TAG,
    APDU_TAGS,
    FRAME_END,
    FRAME_START,
    HEADER_LEN,
    AxdrError,
    AxdrNode,
    apdu_self_check,
    calc_fcs,
    decode_apdu,
    describe_value,
    frame_layout,
    verify_frame,
    weekday_name,
)
from modular_iface_data import (
    APDU_NAMES,
    APDU_SHORT_NAMES,
    ARRAY_FIELDS,
    CTRL_CODE_NAMES,
    DAR_NAMES,
    DIR_PRM_MEANINGS,
    DTA1_NAMES,
    DTA2_NAMES,
    DT_DEFINITIONS,
    DT_ENUM_NAMES,
    DT_NAMES,
    IFACE_TYPE_NAMES,
    LINK_RESPONSE_FUNC_CONFIG,
    STRUCTURE_FIELDS,
    decode_dt,
    dt_name,
    unit_text,
)

# ── 常量（兼容既有调用方的别名，实体在 modular_iface_axdr / modular_iface_data）─

#: 兼容别名（main_gui 查询页 / 既有测试按这些名字 import）
CTRL_FUNC_NAMES = CTRL_CODE_NAMES
DTA1_MODULE_NAMES = DTA1_NAMES
DTA2_RW = DTA2_NAMES
MODULE_INFO_FIELDS = tuple(STRUCTURE_FIELDS[0x0000])
#: 兼容视图：键为 (DTA2, DTB)（main_gui 查询页按此迭代 DTA1=0 的通用信息类）
GENERIC_DT_NAMES: Dict[Tuple[int, int], str] = {
    ((dt >> 8) & 0x0F, dt & 0xFF): name
    for dt, name in DT_NAMES.items()
    if (dt >> 12) == 0
}


def data_total_len(data_bytes: bytes) -> int:
    """从长度域推算整帧长度（L=数据域字节数 → 整帧 = L+8）；不可信返回 0。"""
    if len(data_bytes) < 3:
        return 0
    if data_bytes[0] != FRAME_START:
        return 0
    l_val = data_bytes[1] | (data_bytes[2] << 8)
    data_len = l_val & 0x0FFF
    total = data_len + 8
    if total < 8 or total > 8192:
        return 0
    return total


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def is_frame(data: bytes) -> bool:
    """严格判定：68H 起头、16H 结尾、且整帧长 = L + 8。"""
    data = bytes(data or b"")
    if len(data) < 8 or data[0] != FRAME_START or data[-1] != FRAME_END:
        return False
    need = data_total_len(data)
    return need > 0 and len(data) == need


class ModularIfaceParser:
    """解析结果 = 行列表，每行 ``(行名, 原始值, 解析值, 说明, 起始偏移, 结束偏移)``。

    最近一次解析的元信息放在 ``self.last_meta``：
    ``{"valid", "fcs_ok", "structure_ok", "length_ok", "reserved_bits_nonzero",
       "apdu", "axdr_tail", "errors"}``
    """

    name = "模组化接口"

    def __init__(self) -> None:
        self.last_meta: Dict[str, Any] = {}
        #: 本次解析当前 APDU 的信息类标识（供 structure/array 的说明取文档定义）
        self._current_dt: Optional[int] = None

    # ── 入口 ──────────────────────────────────────────────────────────

    def parse(self, frame: bytes) -> List[tuple]:
        rows: List[tuple] = []
        data = bytes(frame or b"")
        meta: Dict[str, Any] = {
            "valid": False,
            "fcs_ok": False,
            "structure_ok": False,
            "length_ok": False,
            "reserved_bits_nonzero": False,
            "apdu": None,
            "apdu_ok": True,
            "axdr_tail": None,
            "errors": [],
        }
        self.last_meta = meta
        self._current_dt = None

        if not data:
            meta["errors"].append("空帧")
            return self._rows([("⚠ 空帧", "-", "-", "未收到任何字节", 0, 0)], meta)

        if data[0] != FRAME_START:
            meta["errors"].append("起始符错误")
            rows.append(("起始字符", f"{data[0]:02X}", "非68H", "帧必须以 68H 起头", 0, 0))
            rows.append(
                (
                    "⚠ 帧结构错误",
                    f"{data[0]:02X}",
                    "起始符错误",
                    "首字节不是 68H，无法按协议12 解析",
                    0,
                    0,
                )
            )
            return self._rows(rows, meta)

        rows.append(("起始字符", "68", "68H", "帧起始标志", 0, 0))

        if len(data) < 5:
            meta["errors"].append("长度域/控制域未收全")
            rows.append(
                (
                    "⚠ 帧不完整",
                    str(len(data)),
                    "至少5字节",
                    "长度域(2B)+控制域(2B)尚未收全，无法继续",
                    0,
                    len(data) - 1,
                )
            )
            return self._rows(rows, meta)

        # 帧结构判据（与校验器 `ModularIfaceValidator` 同源的单一实现）
        layout = frame_layout(data)
        data_len = int(layout["declared_l"] or 0)
        total = int(layout["expected_total"] or 0)
        l_raw = data[1] | (data[2] << 8)
        reserved_nz = bool(layout["reserved_bits_nonzero"])
        length_ok = bool(layout["length_ok"])
        meta["reserved_bits_nonzero"] = reserved_nz
        meta["length_ok"] = length_ok
        l_note = f"bit0~11=数据域{data_len}字节（整帧={total}），低字节在前"
        if reserved_nz:
            l_note += f"；⚠ bit12~15 保留位非 0（0x{l_raw:04X}）"
        rows.append(("长度域", f"{data[1]:02X} {data[2]:02X}", str(data_len), l_note, 1, 2))

        # 控制域（小端：低字节 DIR|PRM|控制码，高字节 FID）
        c0, c1 = data[3], data[4]
        dir_bit = (c0 >> 7) & 1
        prm_bit = (c0 >> 6) & 1
        func = c0 & 0x3F
        fid = c1
        meaning = DIR_PRM_MEANINGS.get((dir_bit, prm_bit), "")
        ctrl_name = CTRL_CODE_NAMES.get(func, f"保留({func:02X}H)")
        rows.append(
            (
                "控制域",
                f"{c0:02X} {c1:02X}",
                f"DIR={dir_bit} PRM={prm_bit} 控制码={func:02X}H FID={fid}",
                f"{meaning}；{ctrl_name}（表1/表2）",
                3,
                4,
            )
        )
        rows.append(("  传输方向(DIR)", f"0x{c0:02X}", str(dir_bit), "0=终端发出，1=功能模块发出", 3, 3))
        rows.append(("  启动标志(PRM)", f"0x{c0:02X}", str(prm_bit), "0=模块发起，1=终端发起", 3, 3))
        rows.append(
            ("  控制码", f"0x{func:02X}", ctrl_name, "00H确认 01H否认 02H信息（表2）", 3, 3)
        )
        rows.append(("  帧序号(FID)", f"0x{c1:02X}", str(fid), "循环0~255，响应与请求一致", 4, 4))

        # 长度不符时的提示（仍按声明布局尽力解析）
        if not length_ok:
            meta["errors"].append(f"帧长度 {len(data)} ≠ 长度域声明 {total}")
            rows.append(
                (
                    "⚠ 帧长度与长度域不符",
                    f"{len(data)}字节",
                    f"期望{total}字节",
                    f"长度域声明数据域{data_len}字节（整帧{total}），实际收到{len(data)}字节；"
                    "以下按声明布局尽力解析",
                    0,
                    len(data) - 1,
                )
            )

        # 数据域 + FCS + 结束符（判据来自 frame_layout）
        payload = layout["payload"]
        fcs_off = 5 + data_len
        fcs_ok = bool(layout["fcs_ok"])
        if layout["fcs_usable"]:
            off = int(layout["fcs_offset"])
            wire = int.from_bytes(layout["fcs_field"], "little")
            expect = int.from_bytes(layout["fcs_calc"], "little")
            where = (
                "（附录A CRC-16/PPP，覆盖 L+C+数据域；低字节在前）"
                if off == fcs_off
                else f"（按实际帧尾定位：长度域声明整帧 {total} 字节、实际 {len(data)} 字节）"
            )
            rows.append(
                (
                    "帧校验(FCS)",
                    _hex(layout["fcs_field"]),
                    f"0x{wire:04X}",
                    f"期望0x{expect:04X} {'校验正确' if fcs_ok else '校验错误'}{where}",
                    off,
                    off + 1,
                )
            )
        else:
            meta["errors"].append("取不到 FCS 字段")
            rows.append(
                (
                    "帧校验(FCS)",
                    "-",
                    "不可用",
                    f"长度域声明整帧 {total} 字节、实际 {len(data)} 字节，按声明布局取不到 FCS 字段",
                    min(fcs_off, len(data) - 1),
                    len(data) - 1,
                )
            )
        meta["fcs_ok"] = fcs_ok

        end_off = int(layout["end_offset"])
        end_byte = data[end_off] if 0 <= end_off < len(data) else None
        end_ok = bool(layout["end_ok"])
        rows.append(
            (
                "结束字符",
                f"{end_byte:02X}" if end_byte is not None else "-",
                "16H" if end_ok else "非16H",
                "帧结束标志" if length_ok else "（按实际末字节）",
                end_off,
                end_off,
            )
        )
        if not end_ok:
            meta["errors"].append("结束符不是 16H")

        rows.append(
            (
                "数据域",
                _hex(payload) if payload else "-",
                f"{data_len}字节" if length_ok else f"{len(payload)}/{data_len}字节",
                "",
                5,
                5 + len(payload) - 1 if payload else 5,
            )
        )

        # 按控制码分派数据域
        if func == 0x00:
            if payload:
                rows.append(
                    (
                        "⚠ 确认帧不应有数据域",
                        _hex(payload),
                        f"{len(payload)}字节",
                        "表2/§5.2.4.1：确认帧无数据域",
                        5,
                        5 + len(payload) - 1,
                    )
                )
        elif func == 0x01:
            if len(payload) >= 2:
                err = payload[0] | (payload[1] << 8)
                rows.append(
                    (
                        "错误信息码",
                        f"{payload[0]:02X} {payload[1]:02X}",
                        f"0x{err:04X}",
                        "BIN 2字节（表3）；低字节在前",
                        5,
                        6,
                    )
                )
            else:
                rows.append(
                    (
                        "⚠ 否认帧数据域不完整",
                        _hex(payload) if payload else "-",
                        f"{len(payload)}/2字节",
                        "表3：否认帧数据域 = 错误信息码 BIN 2 字节",
                        5,
                        5 + max(0, len(payload) - 1),
                    )
                )
        elif func == 0x02:
            if not payload:
                rows.append(
                    (
                        "⚠ 信息帧缺少 APDU",
                        "-",
                        "0字节",
                        "§5.2.4.3：信息帧的数据域应包含一个完整 APDU",
                        5,
                        5,
                    )
                )
            else:
                rows.extend(self._parse_apdu(payload, 5, meta))
        else:
            rows.append(("控制码", f"0x{func:02X}", "保留", "表2：非确认/否认/信息码", 3, 3))

        structure_ok = length_ok and end_ok
        meta["structure_ok"] = bool(layout["structure_ok"]) and structure_ok
        meta["valid"] = bool(
            layout["ok"] and meta["apdu_ok"] and not meta["errors"]
        )
        return self._rows(rows, meta)

    def parse_to_table(self, frame: bytes) -> List[tuple]:
        """GUI / 串口工具兼容入口。"""
        return self.parse(frame)

    def _rows(self, rows: List[tuple], meta: Optional[Dict[str, Any]] = None) -> List[tuple]:
        if meta is not None:
            self.last_meta = meta
        return rows

    # ── APDU ─────────────────────────────────────────────────────────

    def _parse_apdu(self, payload: bytes, base: int, meta: Dict[str, Any]) -> List[tuple]:
        rows: List[tuple] = []
        tag = payload[0]
        meta["apdu"] = tag
        rows.append(
            (
                "应用层数据单元(APDU)",
                f"0x{tag:02X}",
                APDU_NAMES.get(tag, f"未知APDU(0x{tag:02X})"),
                "A-XDR CHOICE 标签（表13）",
                base,
                base,
            )
        )
        try:
            nodes, consumed = decode_apdu(payload, 0)
        except AxdrError as exc:
            consumed = min(exc.consumed, len(payload))
            meta["axdr_tail"] = len(payload) - consumed
            meta["apdu_ok"] = False
            meta["errors"].append(exc.message)
            rows.extend(self._render_nodes(getattr(exc, "partial", []) or [], base))
            rows.append(
                (
                    "⚠ APDU 字段未解完",
                    _hex(payload[consumed:]),
                    f"已解析{consumed}/{len(payload)}字节",
                    f"{exc.message}；以上字段仍有效（A-XDR 编码假设见 modular_iface_axdr "
                    "的 AXDR_TAG_IN_SEQUENCE / AXDR_LEN_FOR_FIXED_IN_CHOICE / AXDR_VAR_LENGTH_BYTES）",
                    base + consumed,
                    base + len(payload) - 1,
                )
            )
            return rows

        rows.extend(self._render_nodes(nodes, base))
        tail = len(payload) - consumed
        meta["axdr_tail"] = tail
        if tail:
            meta["apdu_ok"] = False
            meta["errors"].append(f"APDU 尾部多余 {tail} 字节")
            rows.append(
                (
                    "⚠ APDU 尾部多余字节",
                    _hex(payload[consumed:]),
                    f"{tail}字节",
                    "A-XDR 解析结束后仍有未消费字节 —— 编码假设可能与实机不符"
                    "（用 verify_frame()['axdr_tail'] 判定，见 modular_iface_axdr 开关 ①/②/③）",
                    base + consumed,
                    base + len(payload) - 1,
                )
            )
        return rows

    # ── 节点 → 表格行 ────────────────────────────────────────────────

    def _render_nodes(self, nodes: Sequence[AxdrNode], base: int) -> List[tuple]:
        names = None
        self._current_dt = None
        for node in nodes:
            if node.name == "信息类标识(DT)" and isinstance(node.value, int):
                self._current_dt = node.value
                names = STRUCTURE_FIELDS.get(node.value) or ARRAY_FIELDS.get(node.value)
        rows: List[tuple] = []
        for node in nodes:
            rows.extend(self._render_node(node, base, 1, names))
        return rows

    def _render_node(
        self,
        node: AxdrNode,
        base: int,
        depth: int,
        names: Optional[Sequence[str]] = None,
    ) -> List[tuple]:
        start = base + node.offset
        end = start + max(0, len(node.raw) - 1)
        rows: List[tuple] = [
            (
                f"{'    ' * depth}{node.name}",
                _hex(node.raw),
                self._node_text(node),
                self._node_note(node),
                start,
                end,
            )
        ]
        children = node.children or []
        if not children:
            return rows
        if node.type_name == "structure":
            for i, child in enumerate(children):
                child.name = (
                    names[i] if names and i < len(names) else f"成员{i + 1}"
                )
                rows.extend(self._render_node(child, base, depth + 1))
        elif node.type_name == "array":
            for i, child in enumerate(children):
                child.name = f"元素{i + 1}"
                # 数组元素常为 structure（附录 G.3/J.3/K.3）：把成员名继续传下去
                rows.extend(self._render_node(child, base, depth + 1, names))
        else:
            for child in children:
                rows.extend(self._render_node(child, base, depth + 1))
        return rows

    def _node_text(self, node: AxdrNode) -> str:
        t = node.type_name
        v = node.value
        if t == "apdu-tag":
            return APDU_NAMES.get(
                APDU_TAGS.get(str(v), -1), str(v)
            )
        if t == "DAR":
            return DAR_NAMES.get(int(v), f"未定义({v})") if isinstance(v, int) else str(v)
        if t == "DT":
            return f"0x{int(v):04X}" if isinstance(v, int) else str(v)
        if t == "Scaler_Unit" and isinstance(v, dict):
            return f"换算=10^{v.get('scaler')}，单位={unit_text(v.get('unit'))}"
        if t == "channel" and isinstance(v, dict):
            iface_code = v.get("iface")
            config_code = v.get("config")
            iface = IFACE_TYPE_NAMES.get(
                iface_code if isinstance(iface_code, int) else -1, f"保留({iface_code})"
            )
            func = LINK_RESPONSE_FUNC_CONFIG.get(
                config_code if isinstance(config_code, int) else -1,
                f"保留({config_code})",
            )
            return f"接口类型={iface}，功能配置={func}"
        if t == "channel-list":
            return f"{len(v)}个虚拟通道"
        if t == "structure":
            return f"{len(v)}个成员"
        if t == "enum" and isinstance(v, int):
            names = DT_ENUM_NAMES.get(self._current_dt if self._current_dt is not None else -1)
            if names and v in names:
                return f"{v}（{names[v]}）"
        return describe_value(v, t)

    def _node_note(self, node: AxdrNode) -> str:
        t = node.type_name
        v = node.value
        if t == "apdu-tag":
            short = APDU_SHORT_NAMES.get(APDU_TAGS.get(str(v), -1), "")
            return f"A-XDR CHOICE 标签（表13）{short}"
        if t == "DT" and isinstance(v, int):
            return decode_dt(int(v).to_bytes(2, "big")).get("text", "")
        if t == "DAR":
            return "表11：0成功 / 1拒绝读写 / 2信息类未定义 / 255其它"
        if t in ("date_time", "date_time_s", "date", "time") and isinstance(v, dict):
            week = weekday_name(v.get("day_of_week")) if t in ("date_time", "date") else ""
            field_tables = {"date_time": "6", "date_time_s": "7", "date": "8", "time": "9"}
            base_note = f"{t}（表{field_tables[t]}；无效字段显示 --）"
            return f"{base_note}，{week}" if week else base_note
        if t == "Scaler_Unit":
            return "表12：换算 = 以 10 为底的指数（integer），单位查附录 M"
        if t == "bit-string":
            return "表4：位串（内容 = 位宽1B + 位组）"
        if t == "channel":
            return "表18 虚拟通道工作模式（接口类型 enum + 功能配置 unsigned）"
        if t == "channel-list":
            return "表18：SEQUENCE OF {接口类型, 功能配置}"
        if t == "structure":
            definition = DT_DEFINITIONS.get(self._current_dt if self._current_dt is not None else -1)
            return definition or "structure（SEQUENCE OF Data）"
        if t == "array":
            definition = DT_DEFINITIONS.get(self._current_dt if self._current_dt is not None else -1)
            return definition or "array（SEQUENCE OF Data）"
        return t

    # ── 摘要 ─────────────────────────────────────────────────────────

    def get_summary(self, frame: bytes) -> str:
        """批量/单帧摘要：``方向 | 控制码 | FID=n | 信息类:… | APDU 名``。"""
        data = bytes(frame or b"")
        if len(data) < 8 or data[0] != FRAME_START:
            return "无效帧"
        data_len = (data[1] | (data[2] << 8)) & 0x0FFF
        c0 = data[3]
        dir_bit = (c0 >> 7) & 1
        func = c0 & 0x3F
        fid = data[4]
        direction = "模块→终端" if dir_bit else "终端→模块"
        ctrl = CTRL_CODE_NAMES.get(func, f"控制码{func:02X}H")
        parts = [direction, ctrl, f"FID={fid}"]
        payload = data[5 : 5 + data_len]
        if func == 0x02 and payload:
            nodes: List[AxdrNode] = []
            try:
                nodes, _consumed = decode_apdu(payload, 0)
            except AxdrError as exc:
                nodes = getattr(exc, "partial", []) or []
            dt_value = next(
                (n.value for n in nodes if n.name == "信息类标识(DT)" and isinstance(n.value, int)),
                None,
            )
            if dt_value is not None:
                parts.append(f"信息类:{dt_name(dt_value)}")
            parts.append(APDU_NAMES.get(payload[0], f"APDU[{payload[0]}]"))
        elif func == 0x01 and len(payload) >= 2:
            parts.append(f"错误码=0x{payload[0] | (payload[1] << 8):04X}")
        elif func == 0x00:
            parts.append("ACK")
        return " | ".join(parts)

    # ── 工具 ─────────────────────────────────────────────────────────

    @staticmethod
    def is_frame(data: bytes) -> bool:
        """兼容入口（等价模块级 `is_frame`）。"""
        return is_frame(data)
