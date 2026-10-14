# -*- coding: utf-8 -*-
"""南网上行通信规约（协议14，Q/CSG 11109004-2013）帧校验器。

校验项（对应文档 5.1.1~5.1.5、6.1.1）：
起始字符 68H ×2、长度域（规范形态 = 2 字节小端 L 重复一次，共 4 字节；两段须一致）、
控制域 C、地址域 A、应用功能码 AFN、帧校验和 CS、结束字符 16H。
"""

from __future__ import annotations

from .base import BaseValidator, CheckItem, CheckLevel, ValidationResult

import csg_uplink_di as DI
import csg_uplink_wire as W

__all__ = ["CSGUplinkValidator"]


class CSGUplinkValidator(BaseValidator):
    """Q/CSG 11109004-2013 南网上行通信规约校验器。"""

    protocol = "南网上行通信规约"

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        data = bytes(frame_bytes)
        result = ValidationResult(protocol=self.protocol, valid=True)
        checks = result.checks

        # 帧长
        checks.append(self._check_min_length(data, W.MIN_FRAME_LEN_ANY, self.protocol))
        if len(data) < W.MIN_FRAME_LEN_ANY:
            result.valid = False
            result.errors.append(f"帧长不足 {W.MIN_FRAME_LEN_ANY} 字节")
            return result

        layout = W.force_layout(data)

        # 起始字符 ×2（第二个 68H 的位置随长度域形态变化）
        checks.append(self._check_start_char(data, W.FRAME_START, 0))
        if data[layout.start2_index] == W.FRAME_START:
            checks.append(CheckItem("第二个起始字符", CheckLevel.PASS, "0x68",
                                    f"0x{data[layout.start2_index]:02X}",
                                    f"第二个起始字符正确（偏移 {layout.start2_index}）"))
        else:
            checks.append(CheckItem("第二个起始字符", CheckLevel.FAIL, "0x68",
                                    f"0x{data[layout.start2_index]:02X}",
                                    "固定报文头的第二个起始字符应为 0x68"))
        if not layout.is_canonical:
            checks.append(CheckItem(
                "长度域形态", CheckLevel.WARN, "4字节（L 2字节小端 + 重复一次）",
                f"{layout.len_field}字节（{layout.form}）",
                W.FORM_NAMES[layout.form]))

        # 长度 L：规范形态两段必须完全一致（5.1.2 条文解释），且声明整帧 = 实际
        expect = layout.total
        if layout.is_canonical and data[1:3] != data[3:5]:
            checks.append(CheckItem("长度L", CheckLevel.FAIL, "两段 L 完全一致",
                                    f"{data[1:3].hex().upper()} ≠ {data[3:5].hex().upper()}",
                                    "条文解释：两个重复的长度 L 必需完全一致，否则此帧为无效帧"))
        elif expect == len(data):
            checks.append(CheckItem("长度L", CheckLevel.PASS, f"{expect}字节",
                                    f"{len(data)}字节",
                                    f"长度域与整帧自洽（L+{layout.fixed_len}）"))
        else:
            checks.append(CheckItem("长度L", CheckLevel.FAIL, f"{expect}字节",
                                    f"{len(data)}字节",
                                    f"长度域 L 与整帧长度不符（L+{layout.fixed_len}）"))

        # 控制域
        ci = layout.c_index
        ctl = W.decode_control(data[ci])
        checks.append(CheckItem("控制域C", CheckLevel.PASS, "0x00~0xFF",
                                f"0x{data[ci]:02X}",
                                f"{ctl['传输方向']} / {ctl['启动标志']} / 功能码 {ctl['功能码']}（{ctl['功能码名称']}）"))

        # 地址域
        ai = layout.addr_index
        try:
            addr = W.parse_addr(data[ai:ai + W.ADDR_LEN])
            msg = W.format_addr(addr)
            if addr.a2 == 0:
                checks.append(CheckItem("地址域A", CheckLevel.WARN, "A2≠0", "A2=0",
                                        "终端地址 A2=000000H 为无效地址（5.1.4.3）"))
            else:
                checks.append(CheckItem("地址域A", CheckLevel.PASS, "7字节", msg, msg))
        except ValueError as exc:
            checks.append(CheckItem("地址域A", CheckLevel.FAIL, "7字节", "不足", str(exc)))

        # 应用功能码 AFN
        afn_off = layout.apdu_offset
        if afn_off < len(data):
            afn = data[afn_off]
            afn_valid = afn in DI.AFN_NAMES
            checks.append(CheckItem(
                "应用功能码AFN", CheckLevel.PASS if afn_valid else CheckLevel.WARN,
                "已定义 AFN", f"0x{afn:02X}",
                DI.AFN_NAMES.get(afn, "未定义（备用）AFN")))
        else:
            checks.append(CheckItem("应用功能码AFN", CheckLevel.FAIL, "1字节", "越界",
                                    "帧长不足以容纳应用功能码"))

        # 帧校验和
        cs_in = data[-2]
        cs_calc = W.calc_cs(data[ci:-2])
        if cs_in == cs_calc:
            checks.append(CheckItem("帧校验和CS", CheckLevel.PASS, f"0x{cs_calc:02X}",
                                    f"0x{cs_in:02X}", "校验和正确"))
        else:
            checks.append(CheckItem("帧校验和CS", CheckLevel.FAIL, f"0x{cs_calc:02X}",
                                    f"0x{cs_in:02X}", "校验和错误（帧内值 vs 复算值）"))

        # 结束字符
        checks.append(self._check_end_char(data, W.FRAME_END))

        result.valid = all(c.level != CheckLevel.FAIL for c in checks)
        for c in checks:
            if c.level == CheckLevel.FAIL:
                result.errors.append(c.message)
            elif c.level == CheckLevel.WARN:
                result.warnings.append(c.message)
        return result
