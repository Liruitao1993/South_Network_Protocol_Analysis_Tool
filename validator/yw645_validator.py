# -*- coding: utf-8 -*-
"""依瓦定制645协议（协议13）校验器。

判据来源与解析器**同一实现**：本校验器直接调用 ``YW645Parser.parse()`` 并读取其
``last_meta``（``length_ok`` / ``cs_ok`` / ``cs_expected`` / ``items_form`` …），
避免校验器与解析器各写一份判据而逐渐漂移（同 ``validator/modular_iface_validator.py`` 的做法）。

检查项（prd R8.2）：帧长度 / 起始字符 68H / 地址域定界符 68H / 结束符 16H /
校验和 CS / 数据域长度一致性 / 模式合法性 / 数据域切分自洽性。

* 长度不符 / CS 不符 → 对应项 ``FAIL``，但**解析器仍完整输出**（见 ``yw645_parser`` 容错铁律）。
* 模式合法性：文档只定义 0x10/0x20/0x30/0x40；**写模式无命令码（缺陷 D1）** ⇒ 未知模式记 ``WARN``
  而非 ``FAIL``（不得把「文档未定义」判成「帧错误」）。
"""

from __future__ import annotations

from validator.base import BaseValidator, CheckItem, CheckLevel, ValidationResult
from yw645_parser import PROTOCOL_NAME, YW645Parser
from yw645_wire import (
    FORM_MALFORMED,
    FRAME_END,
    FRAME_START,
    MIN_FRAME_LEN,
    MODE_NAMES,
)


class YW645Validator(BaseValidator):
    """依瓦定制645（协议13）：``68H + 6B地址 + 68H + COMMAND + L + DATA + CS + 16H``。"""

    def verify(self, frame_bytes: bytes) -> ValidationResult:
        data = bytes(frame_bytes or b"")
        result = ValidationResult(protocol=PROTOCOL_NAME, valid=True)

        if not data:
            result.checks.append(
                CheckItem(
                    name="帧长度",
                    level=CheckLevel.FAIL,
                    expected=f">={MIN_FRAME_LEN}字节",
                    actual="0字节",
                    message="空帧",
                )
            )
            result.valid = False
            return result

        parser = YW645Parser()
        parser.parse(data)
        meta = parser.last_meta

        # 1. 帧长度
        result.checks.append(self._check_min_length(data, MIN_FRAME_LEN, PROTOCOL_NAME))

        # 2. 起始字符 / 3. 地址域定界符 / 4. 结束字符
        result.checks.append(self._check_start_char(data, FRAME_START, 0))
        if len(data) > 7:
            delim = data[7]
            result.checks.append(
                CheckItem(
                    name="地址域定界符",
                    level=CheckLevel.PASS if delim == FRAME_START else CheckLevel.FAIL,
                    expected="68H",
                    actual=f"0x{delim:02X}",
                    message=(
                        "地址域之后的第二帧起始符正确"
                        if delim == FRAME_START
                        else "地址域之后必须是第二个 68H（与其它 68 家族协议的互斥自证）"
                    ),
                )
            )
        else:
            result.checks.append(
                CheckItem(
                    name="地址域定界符",
                    level=CheckLevel.FAIL,
                    expected="68H",
                    actual="数据不足",
                    message=f"帧长 {len(data)} < 8，无法读取地址域定界符",
                )
            )
        result.checks.append(self._check_end_char(data, FRAME_END))

        # 5. 数据域长度一致性
        declared = meta.get("declared_len")
        expected_total = (declared + MIN_FRAME_LEN) if isinstance(declared, int) else None
        result.checks.append(
            CheckItem(
                name="数据域长度",
                level=CheckLevel.PASS if meta.get("length_ok") else CheckLevel.FAIL,
                expected=(
                    f"{expected_total}字节（数据域{declared}）" if expected_total else "可计算的长度域"
                ),
                actual=f"{len(data)}字节",
                message=(
                    f"((COMMAND & 0x0F) << 8) | L = {declared}；整帧 = 数据域 + 12"
                    if meta.get("length_ok")
                    else "长度域声明的整帧长与实际帧长不一致（解析器仍按实际帧长尽力解析）"
                ),
            )
        )

        # 6. 校验和 CS
        cs_pos = len(data) - 2
        cs_wire = data[cs_pos] if 0 <= cs_pos < len(data) else None
        expected_cs = meta.get("cs_expected")
        result.checks.append(
            CheckItem(
                name="校验和",
                level=CheckLevel.PASS if meta.get("cs_ok") else CheckLevel.FAIL,
                expected=f"0x{expected_cs:02X}" if isinstance(expected_cs, int) else "-",
                actual=f"0x{cs_wire:02X}" if cs_wire is not None else "-",
                message=(
                    "CS = 从第一个 68H 起、到 CS 之前所有字节模 256 累加和"
                    "（含数据域原样字节，不含 CS/16H）"
                ),
            )
        )

        # 7. 模式合法性（文档 D1：写模式无命令码 ⇒ 未知模式记 WARN，不判错）
        cmd = data[8] if len(data) > 8 else None
        mode = (cmd & 0xF0) if cmd is not None else None
        if mode is None:
            result.checks.append(
                CheckItem(
                    name="模式",
                    level=CheckLevel.FAIL,
                    expected="0x10/0x20/0x30/0x40",
                    actual="数据不足",
                    message=f"帧长 {len(data)} < 9，无法读取 COMMAND",
                )
            )
        elif mode in MODE_NAMES:
            result.checks.append(
                CheckItem(
                    name="模式",
                    level=CheckLevel.PASS,
                    expected="0x10/0x20/0x30/0x40",
                    actual=f"0x{cmd:02X}（{MODE_NAMES[mode]}）",
                    message="文档定义的读模式/透传模式",
                )
            )
        else:
            result.checks.append(
                CheckItem(
                    name="模式",
                    level=CheckLevel.WARN,
                    expected="0x10/0x20/0x30/0x40",
                    actual=f"0x{cmd:02X}",
                    message=(
                        "文档只定义读模式(0x10/0x20)与透传模式(0x30/0x40)；"
                        "写模式无命令码（文档缺陷 D1），未知模式不判定为帧错误"
                    ),
                )
            )

        # 8. 数据域切分自洽性
        form = meta.get("items_form")
        split_ok = form is not None and form != FORM_MALFORMED
        result.checks.append(
            CheckItem(
                name="数据域切分",
                level=CheckLevel.PASS if split_ok else CheckLevel.FAIL,
                expected="ID(+FL+数据) 可完整消费数据域",
                actual=str(form),
                message=(
                    "数据项序列自洽（文档 L120：请求不带 FL、回复带 FL）"
                    if split_ok
                    else "两种切分形态均无法完整消费数据域（解析器已按原始字节兜底输出）"
                ),
            )
        )

        result.valid = all(c.level != CheckLevel.FAIL for c in result.checks)
        result.errors = list(meta.get("errors") or [])
        return result
