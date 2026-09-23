"""模组化终端功能模块接口协议校验器（协议12）。

帧结构判据（起止符 / 长度域一致 / 保留位 / FCS / 控制域）**全部来自
`modular_iface_axdr.frame_layout`**（与解析器 `ModularIfaceParser.parse()` 同一实现），
避免校验器与解析器各写一份判据而逐渐漂移。

* FCS（§5.2.5 + 附录 A）：覆盖 `L + C + 数据域`，低字节在前；
* APDU 自证（`apdu_self_check`）：`axdr_tail != 0` ⇒ A-XDR 编码假设与真实帧不符
  （协议12 文档无示例帧，见 `modular_iface_axdr` 顶部说明）。
"""

from __future__ import annotations

from modular_iface_data import CTRL_CODE_NAMES, DIR_PRM_MEANINGS
from modular_iface_parser import apdu_self_check, frame_layout
from validator.base import BaseValidator, CheckItem, CheckLevel, ValidationResult


class ModularIfaceValidator(BaseValidator):
    """68H + L(2B, 小端) + C(2B) + 数据域 + FCS(2B) + 16H；FCS = CRC-16/PPP（x-25）。"""

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        data = bytes(frame_bytes or b"")
        result = ValidationResult(protocol="模组化接口", valid=True)

        if not data:
            result.checks.append(
                CheckItem(
                    name="起始字符",
                    level=CheckLevel.FAIL,
                    expected="68H",
                    actual="-",
                    message="空帧",
                )
            )
            result.valid = False
            return result

        layout = frame_layout(data)

        # 起始符
        result.checks.append(
            CheckItem(
                name="起始字符",
                level=CheckLevel.PASS if layout["start_ok"] else CheckLevel.FAIL,
                expected="68H",
                actual=f"{data[0]:02X}H",
                message="帧起始标志正确" if layout["start_ok"] else "帧起始标志错误",
            )
        )

        if not layout["start_ok"]:
            result.valid = False
            return result

        # 长度域：L 只占 12 位
        if layout["declared_l"] is None:
            result.checks.append(
                CheckItem(
                    name="长度域",
                    level=CheckLevel.FAIL,
                    expected="L(2B) + C(2B)",
                    actual=f"{len(data)}字节",
                    message="长度域/控制域未收全，无法判定",
                )
            )
            result.valid = False
            return result

        result.checks.append(
            CheckItem(
                name="长度域",
                level=CheckLevel.PASS,
                expected="bit0~11 = 数据域字节数",
                actual=f"{layout['declared_l']}字节",
                message=f"§5.2.2 图5；声明整帧 {layout['expected_total']} 字节（= L + 8）",
            )
        )

        if layout["reserved_bits_nonzero"]:
            result.checks.append(
                CheckItem(
                    name="长度域保留位",
                    level=CheckLevel.WARN,
                    expected="bit12~15 = 0",
                    actual=f"0x{data[1] | (data[2] << 8):04X}",
                    message="§5.2.2：bit12~15 保留，应为 0；非 0 时长度域含义不可信",
                )
            )

        # 帧长度
        result.checks.append(
            CheckItem(
                name="帧长度",
                level=CheckLevel.PASS if layout["length_ok"] else CheckLevel.FAIL,
                expected=f"{layout['expected_total']}字节",
                actual=f"{len(data)}字节",
                message=(
                    f"数据域{layout['declared_l']}字节，整帧{layout['expected_total']}字节"
                    if layout["length_ok"]
                    else "长度域声明与实际帧长不一致"
                ),
            )
        )

        # 结束符
        result.checks.append(
            CheckItem(
                name="结束字符",
                level=CheckLevel.PASS if layout["end_ok"] else CheckLevel.FAIL,
                expected="16H",
                actual=(
                    f"{data[layout['end_offset']]:02X}H"
                    if 0 <= layout["end_offset"] < len(data)
                    else "-"
                ),
                message="帧结束标志正确" if layout["end_ok"] else "帧结束标志错误",
            )
        )

        # FCS
        if layout["fcs_usable"]:
            wire = int.from_bytes(layout["fcs_field"], "little")
            expect = int.from_bytes(layout["fcs_calc"], "little")
            result.checks.append(
                CheckItem(
                    name="帧校验FCS",
                    level=CheckLevel.PASS if layout["fcs_ok"] else CheckLevel.FAIL,
                    expected=f"0x{expect:04X}",
                    actual=f"0x{wire:04X}",
                    message=(
                        "附录A CRC-16/PPP（fcstab，生成多项式0x8408），覆盖 L+C+数据域，低字节在前"
                        + (
                            ""
                            if layout["fcs_offset"] == 5 + layout["declared_l"]
                            else "（按实际帧尾定位：长度域声明的整帧长与实际不符）"
                        )
                    ),
                )
            )
        else:
            result.checks.append(
                CheckItem(
                    name="帧校验FCS",
                    level=CheckLevel.FAIL,
                    expected="可定位的 FCS 字段",
                    actual="-",
                    message="长度域声明整帧长度与实际帧长不符，按声明布局取不到 FCS",
                )
            )

        # 控制域
        control = layout["control"]
        code = control["code"]
        result.checks.append(
            CheckItem(
                name="控制码",
                level=CheckLevel.PASS if code in CTRL_CODE_NAMES else CheckLevel.WARN,
                expected="00H/01H/02H",
                actual=f"{code:02X}H",
                message=(
                    f"DIR={control['dir']} PRM={control['prm']} FID={control['fid']}；"
                    f"{DIR_PRM_MEANINGS.get((control['dir'], control['prm']), '')}；"
                    f"{CTRL_CODE_NAMES.get(code, '表2 未定义（保留）')}"
                ),
            )
        )

        # APDU 自证（仅信息帧）
        apdu_ok = True
        if code == 0x02 and layout["payload"]:
            check = apdu_self_check(layout["payload"])
            tail = check["axdr_tail"]
            apdu_ok = tail == 0 and not check["reason"]
            result.checks.append(
                CheckItem(
                    name="APDU解析",
                    level=CheckLevel.PASS if apdu_ok else CheckLevel.WARN,
                    expected="完整解析（剩余0字节）",
                    actual=f"{check['apdu_name'] or '未知'}"
                    f"，已解析{check['axdr_consumed']}字节，剩余{tail}字节",
                    message=(
                        "A-XDR 解析自洽"
                        if apdu_ok
                        else f"{check['reason'] or 'APDU 尾部/内部剩余字节'}"
                        "；协议12 无示例帧，编码假设集中在 modular_iface_axdr 的三个开关"
                    ),
                )
            )
        elif code == 0x01:
            size = len(layout["payload"])
            result.checks.append(
                CheckItem(
                    name="否认帧数据域",
                    level=CheckLevel.PASS if size == 2 else CheckLevel.FAIL,
                    expected="2字节（错误信息码 BIN）",
                    actual=f"{size}字节",
                    message="表3",
                )
            )
        elif code == 0x00 and layout["payload"]:
            result.checks.append(
                CheckItem(
                    name="确认帧数据域",
                    level=CheckLevel.FAIL,
                    expected="无数据域",
                    actual=f"{len(layout['payload'])}字节",
                    message="§5.2.4.1：确认帧无数据域",
                )
            )

        result.valid = bool(layout["ok"] and apdu_ok)
        return result
