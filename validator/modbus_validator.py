# -*- coding: utf-8 -*-
"""Modbus（RTU / TCP）校验器。

判据与解析器**同一实现**：直接调用 ``modbus_core.split_frame`` /
``modbus_core.detect_transport`` 和功能码表，避免校验器与解析器各写一份判据
后逐渐漂移（同 ``validator/yw645_validator.py`` / ``validator/modular_iface_validator.py``）。

检查项：

1. 帧长度 ≥ 4 字节；
2. 传输类型识别（RTU / TCP），Modbus ASCII 明确报不支持；
3. 从站地址 / 单元标识（0 = 广播，1~247 常规，248~255 保留 → WARN）；
4. 功能码合法性（规范已定义，或最高位为 1 的异常响应）；
5. RTU：CRC16（Modbus 多项式 0xA001）逐字节校验；
6. TCP：MBAP 协议标识为 0 + 长度域与实收字节一致；
7. 数据长度自洽（按功能码核对字段长度，如 0x03 响应的字节数域）；
8. 从站异常响应：结构合法但业务被拒绝 → 记 WARN 并列出异常码含义。
"""

from __future__ import annotations

from typing import Optional

import modbus_core as mc
from validator.base import BaseValidator, CheckItem, CheckLevel, ValidationResult

PROTOCOL_NAME = mc.PROTOCOL_NAME


class ModbusValidator(BaseValidator):
    """Modbus RTU / TCP 帧校验器。"""

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        data = bytes(frame_bytes or b"")
        result = ValidationResult(protocol=f"{PROTOCOL_NAME}（RTU/TCP）", valid=True)

        result.checks.append(self._check_min_length(data, 4, PROTOCOL_NAME))
        if not data:
            result.valid = False
            result.errors.append("报文为空")
            return result

        # 1) 传输类型
        if mc.is_ascii_frame(data):
            result.checks.append(
                CheckItem(
                    name="传输类型",
                    level=CheckLevel.FAIL,
                    expected="Modbus RTU / Modbus TCP",
                    actual="疑似 Modbus ASCII（0x3A ':' 开头）",
                    message="本工具只支持二进制 RTU / TCP 帧，请提供去除 ASCII 编码后的十六进制内容",
                )
            )
            result.valid = False
            return result

        split = mc.split_frame(data)
        transport = split.get("transport")
        transport_label = "Modbus RTU" if transport == mc.TRANSPORT_RTU else "Modbus TCP"
        result.checks.append(
            CheckItem(
                name="传输类型",
                level=CheckLevel.PASS,
                expected="按帧结构自动识别",
                actual=transport_label,
                message=(
                    "检测到 MBAP 头（事务/协议/长度/单元标识）"
                    if transport == mc.TRANSPORT_TCP
                    else "检测到 从站地址 + PDU + CRC16 结构"
                ),
            )
        )

        # 2) 从站地址 / 单元标识
        slave = int(split.get("slave") or 0)
        slave_label = split.get("slave_label") or "从站地址"
        if slave == 0:
            slave_level, slave_note = CheckLevel.PASS, "广播地址：从站执行但不响应"
        elif 1 <= slave <= 247:
            slave_level, slave_note = CheckLevel.PASS, "常规从站地址范围（1~247）"
        elif 248 <= slave <= 255:
            slave_level, slave_note = CheckLevel.WARN, "248~255 为规范保留地址，通常只用于特殊场景"
        else:
            slave_level, slave_note = CheckLevel.FAIL, "地址超出 0~255"
        result.checks.append(
            CheckItem(
                name=slave_label,
                level=slave_level,
                expected="0~247（网关场景可为 0~255）",
                actual=f"{slave}（0x{slave:02X}）",
                message=slave_note,
            )
        )

        # 3) CRC16 / MBAP 长度域
        if transport == mc.TRANSPORT_RTU:
            crc_ok = bool(split.get("crc_ok"))
            wire = (data[-1] << 8) | data[-2] if len(data) >= 2 else 0
            calc = mc.crc16(data[:-2])
            result.checks.append(
                CheckItem(
                    name="CRC16",
                    level=CheckLevel.PASS if crc_ok else CheckLevel.FAIL,
                    expected=f"0x{calc:04X}（低字节先发）",
                    actual=f"0x{wire:04X}（线上 {data[-2]:02X} {data[-1]:02X}）",
                    message=(
                        "CRC16（初值 0xFFFF、多项式 0xA001）校验通过"
                        if crc_ok
                        else "CRC 不符：帧可能被截断、拼接，或含前导/尾随字节"
                    ),
                )
            )
            if not crc_ok:
                result.errors.append("CRC16 校验失败")
        else:
            declared = (data[4] << 8) | data[5] if len(data) >= 6 else 0
            protocol_id = (data[2] << 8) | data[3] if len(data) >= 4 else 0
            expected_total = declared + 6
            length_ok = bool(split.get("length_ok"))
            result.checks.append(
                CheckItem(
                    name="MBAP 协议标识",
                    level=CheckLevel.PASS if protocol_id == 0 else CheckLevel.WARN,
                    expected="0",
                    actual=f"{protocol_id}",
                    message="Modbus TCP 固定为 0" if protocol_id == 0 else "非 0 表示非标准 Modbus 封装",
                )
            )
            result.checks.append(
                CheckItem(
                    name="MBAP 长度域",
                    level=CheckLevel.PASS if length_ok else CheckLevel.FAIL,
                    expected=f"{expected_total} 字节整帧（长度域 {declared} = 单元标识 + PDU）",
                    actual=f"{len(data)} 字节",
                    message="长度域与实收字节一致" if length_ok else "长度域与实收字节不一致（帧被截断或多出字节）",
                )
            )
            if not length_ok:
                result.errors.append("MBAP 长度域与实收字节不一致")

        # 4) 功能码
        pdu = split.get("pdu") or b""
        func: Optional[int] = pdu[0] if pdu else None
        if func is None:
            result.checks.append(
                CheckItem(
                    name="功能码",
                    level=CheckLevel.FAIL,
                    expected="1 字节功能码",
                    actual="PDU 为空",
                    message="地址/长度域之后没有功能码字节",
                )
            )
            result.valid = False
            return result
        base_func = func & 0x7F
        known = base_func in mc.FUNC_NAMES
        result.checks.append(
            CheckItem(
                name="功能码",
                level=CheckLevel.PASS if known else CheckLevel.WARN,
                expected="Modbus 规范已定义的功能码（见 modbus_core.FUNC_NAMES）",
                actual=f"0x{func:02X}"
                + ("（异常响应）" if func & 0x80 else "")
                + (f" {mc.FUNC_NAMES[base_func][0]}" if known else " 未定义/厂商自定义"),
                message=(
                    "功能码在规范表内"
                    if known
                    else "规范未定义该功能码：仍会按原始数据展示，不判为帧错误"
                ),
            )
        )

        # 5) 异常响应
        if func & 0x80:
            code = pdu[1] if len(pdu) > 1 else None
            reason = mc.EXCEPTION_CODES.get(code or 0, "未定义异常码") if code is not None else "缺少异常码"
            result.checks.append(
                CheckItem(
                    name="异常响应",
                    level=CheckLevel.WARN if code is not None else CheckLevel.FAIL,
                    expected="异常码 1 字节",
                    actual=f"0x{code:02X} {reason}" if code is not None else "缺少异常码",
                    message="从站以异常响应拒绝请求（帧结构合法，业务未成功）",
                )
            )
            result.valid = result.fail_count == 0
            return result

        # 6) 数据长度自洽（按功能码核对字段长度）
        result.checks.append(self._check_pdu_shape(func, pdu))

        result.valid = result.fail_count == 0
        if result.valid and result.warn_count:
            result.warnings.extend(
                check.message for check in result.checks if check.level == CheckLevel.WARN
            )
        return result

    # ── 子检查 ──────────────────────────────────────────────────
    def _check_pdu_shape(self, func: int, pdu: bytes) -> CheckItem:
        """按功能码核对 PDU 长度（只做"是否为合法请求/响应形态"的粗判）。"""
        name = mc.FUNC_NAMES.get(func, ("未知功能码", ""))[0]
        length = len(pdu)
        ok = True
        detail = ""

        if func in (0x01, 0x02, 0x03, 0x04):
            is_response = length >= 3 and pdu[1] > 0 and 2 + pdu[1] == length
            is_request = length == 5
            if is_response:
                detail = f"响应形态：字节数 {pdu[1]} 与 PDU 长度自洽"
                if func in (0x03, 0x04) and pdu[1] % 2:
                    ok, detail = False, f"读寄存器响应的字节数 {pdu[1]} 应为偶数"
            elif is_request:
                detail = "请求形态：起始地址 + 数量，共 5 字节 PDU"
            else:
                ok, detail = False, f"PDU 长度 {length} 既不是请求（5）也不是合法响应（2+字节数）"
        elif func in (0x05, 0x06, 0x16):
            ok = length == 5
            detail = f"{name}的 PDU 固定 5 字节（功能码 + 4 字节数据）"
        elif func in (0x0F, 0x10):
            if length >= 7 and 6 + pdu[5] == length:
                detail = f"请求形态：字节数 {pdu[5]} 与 PDU 长度自洽"
            elif length == 5:
                detail = "响应形态：起始地址 + 数量，共 5 字节 PDU"
            else:
                ok, detail = False, f"PDU 长度 {length} 既不满足请求（6+字节数）也不满足响应（5）"
        elif func == 0x17:
            if length >= 10 and 10 + pdu[9] == length:
                detail = f"请求形态：写字节数 {pdu[9]} 与 PDU 长度自洽"
            elif length >= 3 and 2 + pdu[1] == length:
                detail = "响应形态：字节数 + 读回数据"
            else:
                ok, detail = False, f"读写多个寄存器的 PDU 长度 {length} 不自洽"
        elif func == 0x08:
            ok = length == 5
            detail = "诊断功能 PDU 固定 5 字节（子功能 2 + 数据 2）"
        else:
            detail = f"{name}未做字段级长度校验（按原始数据展示）"

        return CheckItem(
            name="数据长度自洽",
            level=CheckLevel.PASS if ok else CheckLevel.FAIL,
            expected="符合功能码定义的 PDU 长度",
            actual=f"{length} 字节",
            message=detail,
        )


__all__ = ["PROTOCOL_NAME", "ModbusValidator"]
