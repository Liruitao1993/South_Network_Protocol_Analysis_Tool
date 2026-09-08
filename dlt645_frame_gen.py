# -*- coding: utf-8 -*-
"""DL/T 645-2007 帧生成器（组帧方向）

**本模块是全仓库 645 帧封装的唯一权威实现**：地址域字节序、控制码组装、
数据域 +0x33 加扰、长度 L、校验和 CS、`68…16` 包裹全部只在这里实现一次。
GUI（frame_gen_widget）、Web（reflex_web）与 EB 数据标识生成器都应调用本模块，
不得各自手写封装——此前 EB 645 生成器就是因为在 GUI/Web 各写一份且口径错误
（CS 漏算帧头、数据域未加扰），产出的帧真实设备不认、本工具也解析不了。

口径依据（均有实证，详见 .trellis/tasks/09-07-eb-645-standard-fix/research/）：

- DL/T645-2007 §7.6 广播校时帧格式表：线序 `68 99×6 68 08 06 ss mm hh DD MM YY CS 16`
- DL/T645-2007 §7.4/§7.5 读/写通信地址：地址域填 `AAH×6`（非 BCD，故地址按 hex 处理）
- 真实抓包 CCO-2-COM3-260628-124120 三帧内层 645 帧验算：
  CS = sum(帧首字节 … 数据域末字节) & 0xFF，数据域逐字节 +0x33
- 与本仓库既有正确实现一致：archive_widget._build_dlt645_read_energy_frame、
  test/test_dlt645_lme.build_frame
"""

from typing import Optional, Union

from dlt645_data_codec import FUNC_NAMES

AddrLike = Union[str, bytes, bytearray]


def encode_addr(addr: AddrLike, label: str = "地址域") -> bytes:
    """地址 → 线上 6 字节（**低字节在前**）。

    接受两种输入：

    - 12 位十六进制/BCD 字符串，按正常书写序（高位在前），如 `"260526000028"`
      → 线上 `28 00 00 26 05 26`；广播校时 `"999999999999"` → `99×6`；
      读/写通信地址 `"AAAAAAAAAAAA"` → `AA×6`（AA 非合法 BCD，故按 hex 处理）
    - 6 字节 bytes，视为**已是线上序**，原样返回

    645-2007 的地址域不加扰（+0x33 只作用于数据域）。
    """
    if isinstance(addr, (bytes, bytearray)):
        b = bytes(addr)
        if len(b) != 6:
            raise ValueError(f"{label}应为 6 字节，当前 {len(b)} 字节")
        return b
    s = (addr or "").strip().replace(" ", "")
    if s.lower().startswith("0x"):
        s = s[2:]
    if not s:
        raise ValueError(f"{label}不能为空")
    if len(s) > 12:
        raise ValueError(f"{label}最多 12 位（当前 {len(s)} 位）：{addr!r}")
    try:
        b = bytes.fromhex(s.rjust(12, "0"))
    except ValueError:
        raise ValueError(f"{label}含非法十六进制字符：{addr!r}")
    return b[::-1]


def encode_di(di: str, label: str = "数据标识") -> bytes:
    """DI 字符串（DI3DI2DI1DI0 书写序，如 "04FFAAF9"）→ 线上 4 字节（低字节在前）。

    例：`"04FFAAF9"` → `F9 AA FF 04`；`"00010000"` → `00 00 01 00`。
    """
    s = (di or "").strip().replace(" ", "").upper()
    if len(s) != 8:
        raise ValueError(f"{label}应为 8 位十六进制（当前 {len(s)} 位）：{di!r}")
    try:
        return bytes.fromhex(s)[::-1]
    except ValueError:
        raise ValueError(f"{label}含非法十六进制字符：{di!r}")


class DLT645FrameGenerator:
    """DL/T 645-2007 组帧器。

    典型用法::

        gen = DLT645FrameGenerator()
        frame = gen.build_frame("000000000033", gen.build_control(0x11),
                                encode_di("00010000"))
        # → 68 33 00 00 00 00 00 68 11 04 33 33 34 33 E5 16

    命令级组帧（按 schema 自动拼数据域）见 :meth:`generate_frame`。
    """

    START = 0x68
    END = 0x16
    SCRAMBLE = 0x33

    #: 广播校时等命令的地址域（BCD 99×6）
    BROADCAST_99 = "999999999999"
    #: 读/写通信地址命令的地址域（AA×6，文档 §7.4/§7.5，非合法 BCD）
    BROADCAST_AA = "AAAAAAAAAAAA"

    # 控制码位定义：D7=DIR 传输方向，D6=异常应答标志，D4~D0=功能码（5 位）
    # 口径与 dlt645_parser.py 一致（parser 用 ctrl & 0x1F 取功能码、ctrl >> 7 取 DIR）
    DIR_SLAVE = 0x80     # D7=1：从站→主站（应答/主动上报）
    ERR_FLAG = 0x40      # D6=1：异常应答
    FUNC_MASK = 0x1F

    @staticmethod
    def build_control(func_code: int, dir_bit: int = 0, err: bool = False) -> int:
        """组装控制码 C。

        func_code: 5 位功能码（D4~D0），如 0x11 读数据、0x08 广播校时
        dir_bit:   1 = 从站发出的应答/上报帧（D7 置位）
        err:       True = 异常应答（D6 置位），仅应答帧有意义

        例：读请求 0x11 / 读应答 0x91 / 读异常应答 0xD1。
        """
        func = int(func_code)
        if not 0 <= func <= DLT645FrameGenerator.FUNC_MASK:
            raise ValueError(
                f"功能码应在 00H~1FH（D4~D0 共 5 位），当前 0x{func:02X}")
        ctrl = func
        if dir_bit:
            ctrl |= DLT645FrameGenerator.DIR_SLAVE
        if err:
            ctrl |= DLT645FrameGenerator.ERR_FLAG
        return ctrl

    @classmethod
    def scramble(cls, data: bytes) -> bytes:
        """数据域逐字节 +0x33（DL/T645-2007 强制；地址域不加扰）。"""
        return bytes((b + cls.SCRAMBLE) & 0xFF for b in data)

    @classmethod
    def descramble(cls, data: bytes) -> bytes:
        """数据域逐字节 -0x33，:meth:`scramble` 的逆运算。"""
        return bytes((b - cls.SCRAMBLE) & 0xFF for b in data)

    def build_frame(self, addr: AddrLike, ctrl: int, data: bytes = b"",
                    scramble: bool = True) -> bytes:
        """封装完整 645 帧：`68 A0..A5 68 C L DATA(+0x33) CS 16`。

        addr:     见 :func:`encode_addr`
        ctrl:     控制码，通常由 :meth:`build_control` 生成
        data:     **未加扰**的逻辑数据域（DI + 值）
        scramble: True（默认）时对 data 逐字节 +0x33；False 仅用于测试对照，
                  UI 不应暴露该参数
        """
        addr_b = encode_addr(addr)
        payload = self.scramble(data) if scramble else bytes(data or b"")
        if len(payload) > 0xFF:
            raise ValueError(
                f"数据域长度 {len(payload)} 超出单帧上限 255 字节（L 仅 1 字节）")
        body = bytes([self.START]) + addr_b + bytes(
            [self.START, ctrl & 0xFF, len(payload)]) + payload
        cs = sum(body) & 0xFF          # CS 覆盖帧首至数据域末（含两个 68H 与地址域）
        return body + bytes([cs, self.END])

    def generate_frame(self, cmd_key, field_values: Optional[dict] = None,
                       addr: Optional[AddrLike] = None) -> bytes:
        """命令级组帧：按 schema 拼数据域与控制码，再封装成帧。

        cmd_key:      `(direction, func_code)`，direction ∈ {"req", "rsp"}，
                      见 dlt645_frame_schema.DLT645_CMD_SCHEMA
        field_values: 字段名 → 用户输入字符串
        addr:         表地址；None 时取该命令的 schema 默认地址
                      （广播校时 99×6、读/写通信地址 AA×6、其余 000000000000）
        """
        # 延迟导入避免 schema ↔ gen 循环依赖
        from dlt645_frame_schema import build_data, get_command

        spec = get_command(cmd_key)
        fv = dict(field_values or {})
        ctrl = self.build_control(spec["func"], dir_bit=spec["dir"],
                                  err=bool(spec.get("err")))
        data = build_data(cmd_key, fv)
        return self.build_frame(addr if addr is not None else spec["addr_default"],
                                ctrl, data)


def describe_control(ctrl: int) -> str:
    """控制码 → 中文说明（DIR / 异常 / 功能码），供 UI 只读展示。"""
    func = ctrl & DLT645FrameGenerator.FUNC_MASK
    dir_txt = "从站→主站" if ctrl & DLT645FrameGenerator.DIR_SLAVE else "主站→从站"
    err_txt = "异常应答" if ctrl & DLT645FrameGenerator.ERR_FLAG else ""
    name = FUNC_NAMES.get(func, f"功能码{func:02X}")
    parts = [f"C=0x{ctrl:02X}", dir_txt, name]
    if err_txt:
        parts.append(err_txt)
    return " | ".join(parts)
