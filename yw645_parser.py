# -*- coding: utf-8 -*-
"""依瓦定制645协议（协议13）解析器（纯逻辑，零 Qt）。

协议文档（唯一权威）：``协议文档/13.依瓦定制645协议/依瓦定制645协议.md``
（依瓦定制645协议 V1.0，2026-06-24 陈工）。逐字节证据见
``.trellis/tasks/10-09-yiwa-645-protocol/research/yiwa-645-protocol-facts.md``。

帧结构（图1 / 数据帧结构表）::

    偏移  0       1..6        7       8         9        10..10+n-1   10+n   11+n
         68H    A0..A5(6B)   68H   COMMAND      L       DATA(n)       CS     16H
                               bit7-4 = 模式
                               bit3-0 = 数据域长度高 4 位
    n = ((COMMAND & 0x0F) << 8) | L            （12 bit，0x000 ~ 0xFFF）
    整帧长度 = n + 12

线格式（地址高字节在前 / 长度拼接 / CS / ±0x33 / 数据项序列）**全部走 ``yw645_wire``**，
数据项表走 ``yw645_di``——本模块不重复实现任何一份（项目既有约定，见 AGENTS.md 陷阱 48/55/61）。

行元组契约（GUI / 批量 / 串口三个调用方共同依赖）::

    (行名, 原始值, 解析值, 说明, 起始偏移, 结束偏移)     # 结束偏移为**闭区间**

容错铁律（AGENTS.md §8 陷阱 23/49）
=================================
``parse`` 只在 ``len(data) < 12`` 时降级（返回「帧长不足」+ 原始 hex）；长度够就**一律继续完整解析**。
CS 错 / 长度域不符 / 截断 / 末字节非 ``16H`` / 起始符非 ``68H`` 时：
**仍输出全部已能解析的字段** + 插醒目 ``⚠`` 行（给出帧内值与正确值），``last_meta["valid"]=False``，
**绝不返回空表**。提示行行名含「校验和」子串（偏移映射按字段名子串匹配）。

文档缺陷处置
============
* **D1 写模式命令码缺失**：``mode_name`` 对未知高 4 位输出「未知模式(0xN0)」并给 ``⚠`` 行，
  **绝不臆造**命令码。
* **D2 DI 字节序歧义**：``di_lookup`` 字面优先 + 字节交换备选，命中方式写入输出与 ``last_meta``。
* **D3 ±0x33 文档自相矛盾**：默认自动判别（``resolve_mask``），并输出判别依据；
  另提供 ``assume_masked`` 显式覆盖（``None`` = 自动）。
* **D4 长度上限**：12 bit，上限 ``0xFFF``（文档「4096」按 4095 实现）。
* **D5 附录A 仅 2 项**：未知 ID 走兜底（原始 hex + ``⚠``），不拒解析。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import yw645_wire as W
from yw645_di import di_exists, di_lookup, di_payload_note

__all__ = ["YW645Parser", "PROTOCOL_NAME", "is_frame", "calc_checksum"]

PROTOCOL_NAME = "依瓦定制645"

#: 透传模式（数据域为不透明转发载荷，模块不做解包 —— 文档 L168/L174）
_PASS_MODES = frozenset({W.MODE_PASS_REQUEST, W.MODE_PASS_RESPONSE})
#: 读模式（数据域 = 数据项序列 ID(+FL+数据)）
_READ_MODES = frozenset({W.MODE_READ_REQUEST, W.MODE_READ_RESPONSE})

_FORM_LABELS = {
    W.FORM_REQUEST: "主站请求（无 FL）",
    W.FORM_REPLY: "模块回复（带 FL）",
    W.FORM_AMBIGUOUS: "歧义（按回复呈现）",
    W.FORM_MALFORMED: "无法切分",
}

_MASK_LABELS = {
    "raw": "按原样（未减 0x33）",
    "unmasked": "已减 0x33 还原",
    "unknown": "未判定",
}

_CS_NOTE = "规则：从第一个 68H 起、到 CS 之前所有字节模 256 累加和（含数据域原样字节，不含 CS/16H）"


def _hex(raw: bytes) -> str:
    return " ".join(f"{b:02X}" for b in raw)


def is_frame(data: bytes) -> bool:
    """结构自证（等价 ``yw645_wire.is_frame``）：长度够 + 双 68H + 末字节 16H + 长度域自洽。

    不含 CS 校验（CS 由解析器/校验器单独判定，两者正交）。
    """
    return W.is_frame(bytes(data or b""))


def calc_checksum(data: bytes) -> int:
    """整帧 CS 计算值。

    ``body`` = 帧头 … 数据域末字节 = 实际帧去掉尾部 ``CS + 16H`` 两个字节（见 ``yw645_wire.calc_cs``）。
    """
    d = bytes(data or b"")
    if len(d) < 2:
        return 0
    return W.calc_cs(d[:-2])


class YW645Parser:
    """解析结果 = 行列表；最近一次解析的元信息在 ``self.last_meta``。

    ``last_meta`` 键（全部必存在）::

        valid / cs_ok / cs_expected / structure_ok / structure_error /
        length_ok / declared_len / actual_len / items_form / mask_mode /
        di_lookup_mode / mode_name / addr / is_broadcast / errors
    """

    name = PROTOCOL_NAME

    def __init__(self) -> None:
        self.last_meta: Dict[str, Any] = {}

    # ── 入口 ─────────────────────────────────────────────────────────

    def parse(self, frame: bytes, *, assume_masked: Optional[bool] = None) -> List[tuple]:
        """解析一帧。

        ``assume_masked``：数据域混淆形态显式覆盖 —— ``None`` = 自动判别（``resolve_mask``），
        ``True`` = 强制「线上已混淆（减 0x33）」，``False`` = 强制「按原样（未混淆）」。
        覆盖用于「两种形态数学上不可判别」的透传载荷（如 ``37 14`` ↔ ``04 E1``）。
        """
        data = bytes(frame or b"")
        meta: Dict[str, Any] = {
            "valid": False,
            "cs_ok": False,
            "cs_expected": None,
            "structure_ok": False,
            "structure_error": "",
            "length_ok": False,
            "declared_len": None,
            "actual_len": max(0, len(data) - W.MIN_FRAME_LEN),
            "items_form": None,
            "mask_mode": None,
            "di_lookup_mode": "unknown",
            "mode_name": "",
            "addr": "",
            "is_broadcast": False,
            "errors": [],
        }
        self.last_meta = meta
        rows: List[tuple] = []
        last = max(0, len(data) - 1)

        # ── 降级：帧长不足（唯一允许「不完整解析」的分支）──────────────
        if len(data) < W.MIN_FRAME_LEN:
            meta["structure_error"] = f"帧长不足（{len(data)} < {W.MIN_FRAME_LEN}）"
            meta["errors"].append(meta["structure_error"])
            rows.append(
                (
                    "⚠ 帧长不足",
                    f"{len(data)}字节",
                    f"至少{W.MIN_FRAME_LEN}字节",
                    "依瓦定制645 最短帧 = 68H+6B地址+68H+COMMAND+L+CS+16H 共 12 字节",
                    0,
                    last,
                )
            )
            if data:
                rows.append(
                    ("原始字节", _hex(data), f"{len(data)}字节", "帧长不足，未做结构解析", 0, last)
                )
            return rows

        # ── 结构判据（偏移固定，故起始符错误也尽力继续解析）────────────
        start_ok = data[0] == W.FRAME_START
        delim_ok = data[7] == W.FRAME_START
        end_ok = data[-1] == W.FRAME_END
        cmd = data[8]
        low = data[9]
        declared = W.len_from_cmd(cmd, low)
        length_ok = len(data) == declared + W.MIN_FRAME_LEN
        meta["declared_len"] = declared
        meta["length_ok"] = length_ok
        meta["mode_name"] = W.mode_name(cmd)

        rows.append(
            (
                "起始字符",
                f"{data[0]:02X}",
                "68H" if start_ok else "非68H",
                "帧起始标志（第一定界符）",
                0,
                0,
            )
        )
        if not start_ok:
            meta["errors"].append(f"起始符错误：0x{data[0]:02X} ≠ 68H")
            rows.append(
                (
                    "⚠ 起始符错误",
                    f"{data[0]:02X}",
                    "68H",
                    "首字节不是 68H，无法按协议13 定位结构；以下按固定偏移尽力解析",
                    0,
                    0,
                )
            )

        addr_raw = data[1:7]
        try:
            addr_text = W.decode_addr12(addr_raw)
        except ValueError:
            addr_text = ""
        is_broadcast = W.is_broadcast_addr(addr_raw)
        meta["addr"] = addr_text
        meta["is_broadcast"] = is_broadcast
        rows.append(
            (
                "地址域",
                _hex(addr_raw),
                "广播地址(AA×6)" if is_broadcast else addr_text,
                "A0~A5 通讯目标地址，高字节在前，BCD；与 DL/T 645-2007（低字节在前）相反（文档 L57）",
                1,
                6,
            )
        )
        rows.append(
            (
                "  表号",
                _hex(addr_raw),
                addr_text,
                "按高字节在前拼成 12 位数字串（去前导 0）；>12 位取低 12 位，<12 位高位补 0（文档 L65/L67）",
                1,
                6,
            )
        )
        rows.append(
            (
                "  地址定界符",
                f"{data[7]:02X}",
                "68H" if delim_ok else "非68H",
                "地址域之后的第二帧起始符",
                7,
                7,
            )
        )
        if not delim_ok:
            meta["errors"].append(f"地址定界符错误：data[7]=0x{data[7]:02X} ≠ 68H")
            rows.append(
                (
                    "⚠ 地址定界符错误",
                    f"{data[7]:02X}",
                    "68H",
                    "地址域之后必须是第二个 68H（依瓦定制645 与南网/国网/698.45 的互斥自证之一）",
                    7,
                    7,
                )
            )

        # ── COMMAND / 长度域 ───────────────────────────────────────────
        rows.append(
            (
                "控制码(COMMAND)",
                f"{cmd:02X}",
                W.mode_name(cmd),
                "bit7~bit4 = 模式；bit3~bit0 = 数据域长度高 4 位（图-COMMAND位定义）",
                8,
                8,
            )
        )
        rows.append(("  模式", f"0x{cmd & 0xF0:02X}", W.mode_name(cmd), "读模式/透传模式的请求与返回", 8, 8))
        rows.append(
            (
                "  长度高位",
                f"0x{cmd & 0x0F:02X}",
                str(cmd & 0x0F),
                "COMMAND 低 4 位，与 L 拼成 12 bit 数据域长度",
                8,
                8,
            )
        )
        rows.append(("数据长度域(L)", f"{low:02X}", str(low), "数据域长度低 8 位", 9, 9))
        rows.append(
            (
                "数据域长度",
                f"{cmd:02X} {low:02X}",
                str(declared),
                f"((COMMAND & 0x0F) << 8) | L = 0x{declared:03X}（12 bit，上限 0xFFF）；"
                f"声明整帧 {declared + W.MIN_FRAME_LEN} 字节",
                8,
                9,
            )
        )

        mode = cmd & 0xF0
        if mode not in W.MODE_NAMES:
            meta["errors"].append(f"未知模式：0x{mode:02X}")
            rows.append(
                (
                    "⚠ 未知模式",
                    f"0x{cmd:02X}",
                    W.mode_name(cmd),
                    "文档只定义读模式(0x10/0x20)与透传模式(0x30/0x40)；"
                    "写模式无命令码（缺陷 D1），未知模式按尽力解析",
                    8,
                    8,
                )
            )

        if not length_ok:
            meta["errors"].append(f"帧长度 {len(data)} ≠ 长度域声明 {declared + W.MIN_FRAME_LEN}")
            rows.append(
                (
                    "⚠ 帧长度与长度域不符",
                    f"{len(data)}字节",
                    f"期望{declared + W.MIN_FRAME_LEN}字节",
                    f"长度域声明数据域 {declared} 字节（整帧 {declared + W.MIN_FRAME_LEN}），"
                    f"实际收到 {len(data)} 字节；以下按实际帧长尽力解析",
                    0,
                    last,
                )
            )

        # ── 数据域（按声明长度取值，尾部保留 CS+16H）────────────────────
        avail = max(0, len(data) - W.MIN_FRAME_LEN)
        take = min(declared, avail)
        payload = data[W.HEADER_LEN : W.HEADER_LEN + take]
        payload_end = W.HEADER_LEN + len(payload) - 1 if payload else W.HEADER_LEN
        leftover = data[W.HEADER_LEN + take : len(data) - 2]

        rows.append(
            (
                "数据域",
                _hex(payload) if payload else "-",
                f"{len(payload)}字节",
                "原始字节（减 0x33 之前；CS 与混淆判别正交）",
                W.HEADER_LEN,
                payload_end,
            )
        )
        if leftover:
            meta["errors"].append(f"数据域声明之外还有 {len(leftover)} 字节")
            rows.append(
                (
                    "⚠ 数据域多余字节",
                    _hex(leftover),
                    f"{len(leftover)}字节",
                    "长度域声明的数据域之外仍有未计入字节（长度域偏小）",
                    W.HEADER_LEN + take,
                    len(data) - 3,
                )
            )

        resolution = self._resolve_mask(payload, assume_masked)
        meta["mask_mode"] = resolution.mode
        meta["items_form"] = resolution.form
        rows.append(
            (
                "数据域混淆",
                f"原样得分={resolution.raw_score} 减0x33得分={resolution.unmasked_score}",
                _MASK_LABELS.get(resolution.mode, resolution.mode),
                resolution.detail,
                W.HEADER_LEN,
                payload_end,
            )
        )
        if resolution.payload:
            rows.append(
                (
                    "  数据域(还原后)",
                    _hex(resolution.payload),
                    f"{len(resolution.payload)}字节",
                    "减 0x33 判别后的数据域字节",
                    W.HEADER_LEN,
                    payload_end,
                )
            )
        if mode not in _PASS_MODES:
            # 透传模式(0x30/0x40) 的数据域是转发载荷、模块不做解包（文档「透传模式（用于CIU）」），
            # 按「ID(+FL+数据)」判定形态无意义，且会把 0x40 返回帧标成「主站请求」自相矛盾
            # ⇒ 该行只对读模式输出；meta['items_form'] 仍照算（元数据不丢）。
            rows.append(
                (
                    "数据域形态",
                    resolution.form,
                    _FORM_LABELS.get(resolution.form, resolution.form),
                    "按 ID(2B)+FL(1B)+数据 能否完整消费数据域判定（文档 L120：请求不带 FL、回复带 FL）",
                    W.HEADER_LEN,
                    payload_end,
                )
            )

        if resolution.items:
            _di, meta["di_lookup_mode"] = di_lookup(resolution.items[0].id)
        elif payload and len(payload) >= 2:
            _di, meta["di_lookup_mode"] = di_lookup(payload[:2])

        if mode in _PASS_MODES:
            # 透传模式：数据域是转发载荷，模块不做解包（文档 L168/L174）→ 按不透明字节呈现
            rows.append(
                (
                    "透传载荷（不透明）",
                    _hex(resolution.payload) if resolution.payload else "-",
                    f"{len(resolution.payload)}字节",
                    "透传模式(0x30/0x40)：数据域为转发载荷，模块无须解包直接转发；"
                    "此处按不透明字节呈现，不做数据项切分（文档「透传模式（用于CIU）」）",
                    W.HEADER_LEN,
                    payload_end,
                )
            )
        elif resolution.form == W.FORM_MALFORMED:
            meta["errors"].append("数据域无法按 ID(+FL+数据) 切分")
            rows.append(
                (
                    "⚠ 数据域无法切分",
                    _hex(resolution.payload) if resolution.payload else "-",
                    "无法切分",
                    "按「请求（无 FL）」与「回复（带 FL）」两种形态均无法完整消费数据域；"
                    "保留原始字节（属兜底路径，不拒解析）",
                    W.HEADER_LEN,
                    payload_end,
                )
            )
        else:
            if resolution.form == W.FORM_AMBIGUOUS:
                alt_items, _alt = W.decode_items(resolution.payload, with_fl=False)
                alt = ",".join(it.id_hex for it in alt_items)
                meta["errors"].append("数据域形态歧义（请求/回复同分）")
                rows.append(
                    (
                        "⚠ 数据域形态歧义",
                        _hex(resolution.payload),
                        "回复/请求两解同分",
                        "两种切分都自洽且同分：按「回复（带 FL）」呈现；"
                        f"若按「请求（无 FL）」则 ID 序列为 {alt or '（空）'}",
                        W.HEADER_LEN,
                        payload_end,
                    )
                )
            rows.extend(self._render_items(resolution.items, W.HEADER_LEN))

        # ── 校验和（按实际帧长定位 CS：len-2）───────────────────────────
        cs_pos = len(data) - 2
        cs_wire = data[cs_pos] if 0 <= cs_pos < len(data) else None
        cs_expected = W.calc_cs(data[:cs_pos]) if cs_pos >= 0 else 0
        cs_ok = cs_wire is not None and cs_wire == cs_expected
        meta["cs_expected"] = cs_expected
        meta["cs_ok"] = cs_ok
        rows.append(
            (
                "校验和(CS)",
                f"{cs_wire:02X}" if cs_wire is not None else "-",
                f"0x{cs_expected:02X}",
                f"帧内值 0x{cs_wire:02X}，计算值 0x{cs_expected:02X}，"
                f"{'校验正确' if cs_ok else '校验错误'}；{_CS_NOTE}",
                cs_pos,
                cs_pos,
            )
        )
        if not cs_ok:
            meta["errors"].append(
                f"校验和错误：帧内 0x{cs_wire:02X}，正确值 0x{cs_expected:02X}"
                if cs_wire is not None
                else "校验和字段缺失"
            )
            rows.append(
                (
                    "⚠ 校验和错误",
                    f"{cs_wire:02X}" if cs_wire is not None else "-",
                    f"应为 0x{cs_expected:02X}",
                    f"帧内值 0x{cs_wire:02X}，正确值 0x{cs_expected:02X}；{_CS_NOTE}",
                    cs_pos,
                    cs_pos,
                )
            )

        rows.append(
            (
                "结束字符",
                f"{data[-1]:02X}",
                "16H" if end_ok else "非16H",
                "帧结束标志（不得作为切帧定界：数据域已 +0x33，0x16 可为合法数据字节）",
                last,
                last,
            )
        )
        if not end_ok:
            meta["errors"].append(f"结束符错误：0x{data[-1]:02X} ≠ 16H")
            rows.append(
                (
                    "⚠ 结束符错误",
                    f"{data[-1]:02X}",
                    "16H",
                    "帧结束符不是 16H（截断帧或定界错位）",
                    last,
                    last,
                )
            )

        meta["structure_ok"] = bool(start_ok and delim_ok and end_ok)
        if not meta["structure_ok"]:
            meta["structure_error"] = "；".join(
                s for s in (
                    "" if start_ok else "起始符错误",
                    "" if delim_ok else "地址定界符错误",
                    "" if end_ok else "结束符错误",
                ) if s
            )
        meta["valid"] = bool(meta["structure_ok"] and length_ok and cs_ok)
        return rows

    def parse_to_table(self, frame: bytes, *, assume_masked: Optional[bool] = None, **kwargs) -> List[tuple]:
        """GUI / 串口 / Web 兼容入口（多余关键字参数忽略，便于协议参数统一下发）。"""
        return self.parse(frame, assume_masked=assume_masked)

    # ── 混淆判别 ─────────────────────────────────────────────────────

    @staticmethod
    def _resolve_mask(payload: bytes, assume_masked: Optional[bool]) -> W.MaskResolution:
        """数据域 ±0x33 形态判别；空数据域直接按「请求」呈现且不出歧义提示。"""
        if not payload:
            return W.MaskResolution(
                payload=b"",
                mode="raw",
                detail="数据域为空（无混淆与切分问题）",
                raw_score=0,
                unmasked_score=0,
                items=[],
                form=W.FORM_REQUEST,
            )
        raw_score = W.best_items_score(payload, id_exists=di_exists)
        unmasked = W.apply_mask(payload, invert=False)
        unmasked_score = W.best_items_score(unmasked, id_exists=di_exists)
        if assume_masked is not None:
            # 三态显式覆盖：True = 按线上已混淆（减 0x33）；False = 按原样（未混淆）
            if assume_masked:
                restored = unmasked
                mode = "unmasked"
                detail = "显式指定 assume_masked=True：按线上已混淆（逐字节减 0x33）解析"
            else:
                restored = bytes(payload)
                mode = "raw"
                detail = "显式指定 assume_masked=False：按原样（未减 0x33）解析"
            items, form = W.decode_items(restored, id_exists=di_exists)
            return W.MaskResolution(
                payload=restored,
                mode=mode,
                detail=detail,
                raw_score=raw_score,
                unmasked_score=unmasked_score,
                items=items,
                form=form,
            )
        return W.resolve_mask(payload, id_exists=di_exists)

    # ── 数据项渲染 ───────────────────────────────────────────────────

    @staticmethod
    def _render_items(items: Sequence[W.DataItem], base: int) -> List[tuple]:
        rows: List[tuple] = []
        for i, it in enumerate(items, 1):
            start = base + it.offset
            di, hit = di_lookup(it.id)
            if di is not None:
                rows.append(
                    (
                        f"数据项{i}",
                        it.id_hex,
                        di.get("name", "?"),
                        f"ID={it.id_hex}（{'字面命中' if hit == 'literal' else '字节交换命中'}）；"
                        f"长度={di.get('length', '-')}，类型={di.get('dtype', '-')}，读写={di.get('rw', '-')}；"
                        f"{di.get('note', '')}",
                        start,
                        start + 1,
                    )
                )
            else:
                rows.append(
                    (
                        f"⚠ 数据项{i}(未知ID)",
                        it.id_hex,
                        "未定义",
                        f"ID={it.id_hex}；附录A 未定义该数据项"
                        "（缺陷 D5：附录A 仅 0010/0020），按原始字节呈现",
                        start,
                        start + 1,
                    )
                )
            if it.fl is None:
                continue
            rows.append(
                (
                    "  长度(FL)",
                    f"0x{it.fl:02X}",
                    str(it.fl),
                    "数据项内容字节数（标志长度 FL）",
                    start + 2,
                    start + 2,
                )
            )
            if it.data:
                biz = di_payload_note(di, it.data) if di is not None else ""
                rows.append(
                    (
                        "  数据项值",
                        it.data_hex,
                        biz or it.data_hex,
                        biz or "原始字节（数据类型见附录A：BCD/变长）",
                        start + 3,
                        start + 2 + len(it.data),
                    )
                )
            else:
                rows.append(
                    ("  数据项值", "-", "空", "FL=0：数据项内容为空", start + 2, start + 2)
                )
        return rows

    # ── 摘要 ─────────────────────────────────────────────────────────

    def get_summary(self, frame: bytes) -> str:
        """批量/单帧摘要：``广播|表号 | 模式 | 数据域n字节 | 数据项名… | CS✓``（异常不抛错）。"""
        data = bytes(frame or b"")
        if len(data) < W.MIN_FRAME_LEN:
            return "无效帧（长度不足）"
        if data[0] != W.FRAME_START or data[7] != W.FRAME_START:
            return "帧结构错误（缺少 68H 定界符）"
        addr_raw = data[1:7]
        cmd, low = data[8], data[9]
        declared = W.len_from_cmd(cmd, low)
        mname = W.mode_name(cmd)
        parts = [
            "广播" if W.is_broadcast_addr(addr_raw) else f"表号:{W.decode_addr12(addr_raw)}",
            f"{mname}(0x{cmd:02X})" if not mname.startswith("未知模式") else f"未知模式(0x{cmd:02X})",
            f"数据域:{declared}字节",
        ]
        avail = max(0, len(data) - W.MIN_FRAME_LEN)
        payload = data[W.HEADER_LEN : W.HEADER_LEN + min(declared, avail)]
        mode = cmd & 0xF0
        if payload and mode in _READ_MODES:
            items, _form = W.decode_items(
                W.resolve_mask(payload, id_exists=di_exists).payload, id_exists=di_exists
            )
            if items:
                names = []
                for it in items:
                    di, _hit = di_lookup(it.id)
                    names.append(di.get("name", it.id_hex) if di else it.id_hex)
                parts.append(",".join(names))
        cs_pos = len(data) - 2
        cs_ok = cs_pos >= 0 and W.calc_cs(data[:cs_pos]) == data[cs_pos]
        parts.append("CS✓" if cs_ok else "CS✗")
        return " | ".join(parts)

    # ── 工具（类静态方法，兼容既有调用方）────────────────────────────

    @staticmethod
    def is_frame(data: bytes) -> bool:
        """兼容入口（等价模块级 :func:`is_frame`）。"""
        return is_frame(data)

    @staticmethod
    def calc_checksum(data: bytes) -> int:
        """兼容入口（等价模块级 :func:`calc_checksum`）。"""
        return calc_checksum(data)
