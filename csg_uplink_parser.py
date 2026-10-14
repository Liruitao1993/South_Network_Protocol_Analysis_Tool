# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14，Q/CSG 11109004-2013）解析器（纯逻辑，零 Qt）。

协议文档（唯一权威）：``协议文档/14.南网上行通信规约/中国南方电网有限责任公司计量自动化终端上行通信规约(条文解释).md``

帧结构（5.1.1 图2 / 6.2.x 图11~15）::

    68H | L(2B 小端) | L(同上，重复一次) | 68H | C(1B) | A(7B) | 链路用户数据(应用层) | CS | 16H
    L = 控制域 + 地址域 + 链路用户数据 = 8 + len(应用层) ⇒ 长度域线上 4 字节，整帧 = L + 8
    CS = (控制域 + 地址域 + 链路用户数据) 模 256 和

    长度域 4 字节的证据链（5.1.2 + 图2/图3 + 条文解释 + 5.2.1「L+8」）见 ``csg_uplink_wire`` 头注释；
    解析/切帧兼容历史异形形态（单个 2 字节 L / FT1.2 双同值），**规范形态优先**。

应用层（6.1 图5）::

    AFN(1B) | SEQ(1B) | 信息体1 | 信息体2 | … | [PW(16B)] | [Tp(5B)]
    信息体 = 信息点标识DA(2B) + 数据标识编码DI(4B) + 数据标识内容(变长)
    ⚠ DI 线上**低字节在前**（表 E1 00 60 12 → 线上 12 60 00 E1）；本模块按表序查索引/展示，
      原始值列给出线上顺序（换算见 ``csg_uplink_di.to_semantic_di``）。

网管（深化应用）扩展（文档第 4 章，AFN=0A/0C/04/13 的 15 个扩展 DI）由 ``csg_uplink_nm``
提供结构化解码，解析表按字段展开成子行（``    ↳ 字段``）。

线格式（地址/长度/CS/切帧）全部在 ``csg_uplink_wire``；DI 索引在 ``csg_uplink_di`` —— 本模块
不重复实现任何一份（项目既有约定，见 AGENTS.md 陷阱 48/55/61）。

行元组契约（GUI / 批量 / 串口三个调用方共同依赖）::

    (行名, 原始值, 解析值, 说明, 起始偏移, 结束偏移)     # 结束偏移为**闭区间**

容错铁律（AGENTS.md §8 陷阱 23/49）：帧长不足才降级；长度够就**一律继续完整解析**，CS 错 /
长度域不符 / 末字节非 16H / 起始符非 68H 时仍输出全部已解析字段 + 醒目 ``⚠`` 行，
``last_meta["valid"]=False``，**绝不返回空表**。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import csg_uplink_di as DI
import csg_uplink_wire as W

__all__ = ["CSGUplinkParser", "is_frame", "extract_frames"]

Row = Tuple[str, str, str, str, int, int]


def _hex(raw: bytes) -> str:
    return raw.hex(" ").upper()


def is_frame(data: bytes) -> bool:
    """是否为可自洽切帧的南网上行帧（起始 68 68、末字节 16H、CS 自洽）。"""
    return W.looks_like_csg_uplink(bytes(data))


def extract_frames(data: bytes) -> List[bytes]:
    """按帧首 68H + 长度域（规范 4 字节 / 兼容 2 字节）定长切帧（唯一实现在 ``csg_uplink_wire``）。"""
    return W.extract_csg_uplink_frames(bytes(data))


def _decode_da(raw: bytes) -> Tuple[int, int, List[int]]:
    """DA(2B, 线上 DA1 在前) → ``(DA2 信息点组, DA1 信息点元, 测量点号列表)``。

    ``pn = (DA2-1)*8 + bit + 1``（6.1.3）；DA1 每一位对应一个测量点，bit0→p1。
    """
    da1 = raw[0] if len(raw) > 0 else 0
    da2 = raw[1] if len(raw) > 1 else 0
    pns = [(da2 - 1) * 8 + bit + 1 for bit in range(8) if (da1 >> bit) & 1] if da2 else []
    return da2, da1, pns


class CSGUplinkParser:
    """Q/CSG 11109004-2013 南网上行通信规约报文解析器。"""

    name = "南网上行通信规约"
    short_name = "南网上行"

    def __init__(self) -> None:
        self.last_meta: Dict[str, object] = {}

    # ── 对外入口 ─────────────────────────────────────────────────

    def parse(self, frame: bytes, **kwargs) -> List[Row]:
        return self.parse_to_table(frame, **kwargs)

    def parse_to_table(self, frame: bytes, **kwargs) -> List[Row]:
        data = bytes(frame)
        rows: List[Row] = []
        meta: Dict[str, object] = {"valid": False, "protocol": "csg_uplink"}

        if len(data) < W.MIN_FRAME_LEN_ANY:
            rows.append(("帧长不足", _hex(data), "",
                         f"少于最短帧 {W.MIN_FRAME_LEN_ANY} 字节（规范形态最短 {W.MIN_FRAME_LEN}）",
                         0, max(0, len(data) - 1)))
            self.last_meta = meta
            return rows

        # 固定头（长度域形态自适应：规范 4 字节优先，兼容 2 字节）
        layout = W.force_layout(data)
        rows.append(("起始字符", f"{data[0]:02X}", "68H", "帧起始符", 0, 0))
        rows.append(("长度L", _hex(layout.length_raw), str(layout.value),
                     "控制域+地址域+链路用户数据的字节总数（2 字节小端）。"
                     + W.FORM_NAMES[layout.form], 1, layout.len_field))
        if layout.is_canonical:
            first, second = _hex(data[1:3]), _hex(data[3:5])
            same = data[1:3] == data[3:5]
            rows.append(("  长度L重复段", f"{first} | {second}", first if same else f"{first} ≠ {second}",
                         "条文解释：两个重复的长度 L 必需完全一致，否则此帧为无效帧"
                         + ("" if same else "  ⚠ 两段不一致"), 1, 4))
        rows.append(("起始字符2", f"{data[layout.start2_index]:02X}", "68H", "第二个起始字符",
                     layout.start2_index, layout.start2_index))

        # 控制域 C
        ci = layout.c_index
        c = data[ci]
        ctl = W.decode_control(c)
        rows.append(("控制域C", f"{c:02X}",
                     f"DIR={ctl['DIR']} PRM={ctl['PRM']} 功能码={ctl['功能码']}",
                     f"{ctl['传输方向']} / {ctl['启动标志']} / {ctl['功能码名称']}", ci, ci))
        rows.append(("  DIR传输方向位", f"{(c >> 7) & 1}", str(ctl["DIR"]), str(ctl["传输方向"]), ci, ci))
        rows.append(("  PRM启动标志位", f"{(c >> 6) & 1}", str(ctl["PRM"]), str(ctl["启动标志"]), ci, ci))
        if ctl["PRM"]:
            rows.append(("  FCB帧计数位", f"{(c >> 5) & 1}", str(ctl["FCB"]), "帧计数位（PRM=1）", ci, ci))
            rows.append(("  FCV帧计数有效位", f"{(c >> 4) & 1}", str(ctl["FCV"]), "帧计数有效位（PRM=1）", ci, ci))
        else:
            rows.append(("  ACD要求访问位", f"{(c >> 5) & 1}", str(ctl["ACD"]), "要求访问位（PRM=0，上行）", ci, ci))
        rows.append(("  功能码", f"{ctl['功能码']}", str(ctl["功能码"]), str(ctl["功能码名称"]), ci, ci))

        # 地址域 A
        ai = layout.addr_index
        try:
            addr = W.parse_addr(data[ai:ai + W.ADDR_LEN])
        except ValueError:
            addr = None
        if addr is not None:
            rows.append(("地址域A", _hex(data[ai:ai + W.ADDR_LEN]), W.format_addr(addr),
                         "A1省地市区县码(BCD) + A2终端地址(BIN) + A3主站地址(BIN)", ai, ai + W.ADDR_LEN - 1))
            rows.append(("  A1省地市区县码", _hex(bytes(reversed(data[ai:ai + 3]))), addr.bcd_code,
                         "3 字节 BCD，线上低字节（区县码）在前", ai, ai + 2))
            rows.append(("  A2终端地址", _hex(data[ai + 3:ai + 6]), str(addr.a2),
                         "3 字节 BIN，小端；FFFFFFH 为系统广播", ai + 3, ai + 5))
            rows.append(("  A3主站地址", f"{data[ai + 6]:02X}", str(addr.a3), "MSA，主站启动非零",
                         ai + 6, ai + 6))

        app_start = layout.apdu_offset
        app_end = len(data) - 2
        apdu = data[app_start:app_end]
        frame_cs = data[-2]
        cs_calc = W.calc_cs(data[ci:-2])

        # 应用层
        self._parse_apdu(rows, apdu, app_start)

        # 帧尾
        rows.append(("校验和CS", f"{frame_cs:02X}", f"{cs_calc:02X}",
                     "正确" if frame_cs == cs_calc else "⚠ 校验和不符（帧内 vs 复算）", app_end, app_end))
        rows.append(("结束字符", f"{data[-1]:02X}", "16H",
                     "" if data[-1] == 0x16 else "⚠ 结束字符应为 16H", len(data) - 1, len(data) - 1))

        # 全局自洽性
        expect_total = layout.total
        repeat_ok = (data[1:3] == data[3:5]) if layout.is_canonical else True
        if data[0] != W.FRAME_START or data[layout.start2_index] != W.FRAME_START:
            rows.append(("⚠ 帧头异常", f"{data[0]:02X} .. {data[layout.start2_index]:02X}", "68H 68H",
                         "固定报文头应为 68H + 长度域 + 68H", 0, layout.start2_index))
        if not repeat_ok:
            rows.append(("⚠ 长度L重复不符", _hex(layout.length_raw), "两段应完全一致",
                         "条文解释：两个重复的长度 L 必需完全一致，否则此帧为无效帧", 1, 4))
        if expect_total != len(data):
            rows.append(("⚠ 长度L不符", str(layout.value), f"期望整帧 {expect_total} 字节",
                         f"实际 {len(data)} 字节（L 应为 整帧-{layout.fixed_len}，"
                         f"当前形态 {layout.form}）", 1, layout.len_field))

        meta["valid"] = (frame_cs == cs_calc and data[-1] == 0x16
                         and data[0] == W.FRAME_START and data[layout.start2_index] == W.FRAME_START
                         and repeat_ok and expect_total == len(data))
        meta["afn"] = apdu[0] if apdu else None
        meta["cs_ok"] = frame_cs == cs_calc
        meta["len_form"] = layout.form
        self.last_meta = meta
        return rows

    # ── 应用层 ───────────────────────────────────────────────────

    def _parse_apdu(self, rows: List[Row], apdu: bytes, base: int) -> None:
        if len(apdu) < 2:
            rows.append(("应用层", _hex(apdu), "", "应用层不足 2 字节（AFN+SEQ）", base,
                         base + max(0, len(apdu) - 1)))
            return
        afn = apdu[0]
        rows.append(("应用功能码AFN", f"{afn:02X}",
                     DI.AFN_NAMES.get(afn, "备用/未知"),
                     f"应用层功能：{DI.AFN_NAMES.get(afn, '未定义')}", base, base))

        seq = apdu[1]
        tpv, fir, fin, con, seqno = (seq >> 7) & 1, (seq >> 6) & 1, (seq >> 5) & 1, (seq >> 4) & 1, seq & 0x0F
        if afn == 0x00 or (afn in (0x04, 0x06, 0x0A, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x12, 0x13, 0x14, 0x15) and con):
            seq_label = f"RSEQ={seqno}"
        else:
            seq_label = f"PSEQ={seqno}"
        rows.append(("帧序列域SEQ", f"{seq:02X}",
                     f"TpV={tpv} FIR={fir} FIN={fin} CON={con} {seq_label}",
                     "TpV时间标签有效/FIR首帧/FIN末帧/CON请求确认/序号0~15", base + 1, base + 1))
        rows.append(("  TpV时间标签有效位", f"{tpv}", str(tpv), "1=带时间标签Tp", base + 1, base + 1))
        rows.append(("  FIR首帧标志", f"{fir}", str(fir), "", base + 1, base + 1))
        rows.append(("  FIN末帧标志", f"{fin}", str(fin), "", base + 1, base + 1))
        rows.append(("  CON请求确认标志", f"{con}", str(con), "1=需要对该帧确认", base + 1, base + 1))
        rows.append(("  PSEQ/RSEQ序号", f"{seqno}", str(seqno), "0~15 循环", base + 1, base + 1))

        self._parse_infobodies(rows, apdu, base, afn)

    def _parse_infobodies(self, rows: List[Row], apdu: bytes, base: int, afn: int) -> None:
        pos = 2
        idx = 0
        total = len(apdu)
        while pos + 6 <= total:
            da_raw = apdu[pos:pos + 2]
            di_raw = apdu[pos + 2:pos + 6]
            # 线上 DI 低字节在前 → 表序 DI（DI3 DI2 DI1 DI0）用于索引/展示
            di = DI.to_semantic_di(di_raw.hex())
            name, unit, fmt = DI.value_name_unit(di)
            da2, da1, pns = _decode_da(da_raw)
            idx += 1
            pn_txt = "、".join(f"p{p}" for p in pns) if pns else "（无测量点，DA1=00H）"
            rows.append((f"信息体{idx} · 信息点标识DA", _hex(da_raw), f"DA2={da2:02X} DA1={da1:02X}",
                         f"测量点：{pn_txt}", base + pos, base + pos + 1))
            rows.append((f"信息体{idx} · 数据标识DI", _hex(di_raw), di,
                         (name or "未收录 DI（原始字节展示）")
                         + "（原始值=线上顺序低字节在前，解析值=表序）",
                         base + pos + 2, base + pos + 5))
            cstart = pos + 6
            rest = apdu[cstart:]
            clen = DI.content_length(di, rest)
            if clen is None or cstart + clen > total:
                content = rest
                note = ("⚠ 该 DI 内容长度未知（变长），按剩余字节整体展示" if clen is None
                        else f"⚠ 截断：期望 {clen} 字节，实得 {len(rest)} 字节")
                rows.append((f"信息体{idx} · 数据标识内容", _hex(content), "",
                             note, base + cstart, base + total - 1))
                self._append_content_decode(rows, di, content, base + cstart)
                pos = total
                break
            content = apdu[cstart:cstart + clen]
            dec = DI.decode_di_value(di, content)
            rows.append((f"信息体{idx} · 数据标识内容", _hex(content), str(dec.get("解析值", "")),
                         str(dec.get("说明", "")), base + cstart, base + cstart + clen - 1))
            self._append_content_decode(rows, di, content, base + cstart, dec)
            pos = cstart + clen

        if pos < total:
            rows.append(("应用层剩余字节", _hex(apdu[pos:]), "",
                         "未能归入任何信息体（可能为 PW 消息认证码或 Tp 时间标签，本版未细分）",
                         base + pos, base + total - 1))

    def _append_content_decode(self, rows: List[Row], di: str, content: bytes, base_off: int,
                               dec: Optional[dict] = None) -> None:
        """网管（深化应用）扩展 DI：把内容按字段逐条展开成缩进行（如台账 14 项、拓扑 n×13B）。"""
        if dec is None:
            dec = DI.decode_di_value(di, content)
        for sub in dec.get("子项", []) or []:
            off = base_off + int(sub.get("偏移", 0) or 0)
            ln = int(sub.get("长度", 0) or 0)
            rows.append((f"    ↳ {sub.get('名称', '')}", str(sub.get("原始值", "")),
                         str(sub.get("解析值", "")), str(sub.get("说明", "")),
                         off, off + max(0, ln - 1)))

    # ── 摘要 ─────────────────────────────────────────────────────

    def get_summary(self, frame: bytes) -> str:
        """单行摘要：``AFN名 | 控制域功能码 | CS``。"""
        data = bytes(frame)
        if len(data) < W.MIN_FRAME_LEN_ANY:
            return "帧长不足"
        layout = W.force_layout(data)
        ctl = W.decode_control(data[layout.c_index])
        apdu_off = layout.apdu_offset
        afn = data[apdu_off] if len(data) > apdu_off else 0
        cs_ok = W.check_cs(data, layout)
        return (f"{DI.AFN_NAMES.get(afn, '未知')} | {ctl['功能码名称']} | "
                f"{ctl['传输方向']} | CS{'✓' if cs_ok else '✗'}")
