"""DL/T 698.45 分布式产品升级（文件传输）报文构建 —— 纯逻辑层，禁止 import Qt。

三步命令（《面向对象的用电信息数据交换协议》类18「文件信息」实例方法，
OI=0xF001；协议文档/8.698.45协议/代理升级流程.docx 给出实帧）：

    启动传输  ACTION-Request Normal  OMD=F0 01 07 00   方法7
    写文件    ACTION-Request Normal  OMD=F0 01 08 00   方法8（每包一帧）
    执行升级  ACTION-Request Normal  OMD=F0 01 0D 00   方法13

链路层（L/HCS/FCS/地址域）小端、APDU 内 A-XDR 大端，两层不互套；链路层一律
交由 `DLT69845FrameGenerator.generate_action_request_normal` 组装（本项目唯一
FCS 实现），本模块只负责 A-XDR 参数与 SA 编码。

⚠ 本模块顶层 import `dl_t698_45_frame_gen` / `dl_t698_45_parser`（二者顶层
`import crcmod.predefined`，可选依赖）⇒ **GUI/蓝牙/串口页不得顶层 import 本模块**，
必须在动作方法内惰性 import，并把 ImportError 兜成「请 pip install crcmod」的提示
（AGENTS 惰性 import 铁律）。

三帧的逐字节 golden 见 test/test_dl698_upgrade.py（A1/A2/A3 与 doc 实帧完全相等）。
"""

import hashlib
import zlib
from dataclasses import dataclass
from typing import List, Optional

from dl_t698_45_frame_gen import DLT69845FrameGenerator
from dl_t698_45_axdr import AXDRCoder
from dl_t698_45_parser import DLT69845Parser
from dl_t698_45_data_decode import (
    VERSION_FIELDS,
    VERSION_FIELD_BYTES,
    decode_version_info,
    version_lengths_match,
    version_like_members,
)

# ─── 协议常量 ───────────────────────────────────────────────────────────────
OMD_START = bytes.fromhex("F0010700")   # 方法7 启动传输（进入接收升级包状态）
OMD_WRITE = bytes.fromhex("F0010800")   # 方法8 写文件（传输一个数据块）
OMD_EXEC = bytes.fromhex("F0010D00")    # 方法13 执行升级

#: 读版本信息的 OAD：`OI=0x4300`（电气设备/设备管理类）、属性 3 = 版本信息、索引 0 = 全部内容。
#: 解析器对该 OAD 的语义说明即为「电气设备 (设备管理类) - 版本信息 (全部内容)」。
OAD_VERSION = bytes.fromhex("43000300")

#: **厂家扩展**的内部版本 OAD：`OI=0xFF10`（0xFF00 起为厂商自定义区间，解析器标「未知对象」）、
#: 属性 4、索引 0。实帧 golden（用户提供，HCS/FCS 实测通过、本模块可逐字节复现）：
#: `68 17 00 43 05 03 24 08 04 26 20 00 CD 9A 05 01 2C FF 10 04 00 00 C2 8A 16`。
OAD_INTERNAL_VERSION = bytes.fromhex("FF100400")

DEFAULT_BLOCK_SIZE = 600               # 默认每包字节数（串口缓冲与 698 帧长经验值）
IMMEDIATE_EXEC_TIME = b"\xFF" * 7      # 执行升级时间 = date_time_s 全 FF ⇒ 立即执行
WILDCARD_SA = bytes.fromhex("45AAAAAAAAAAAA")  # 通配地址：特征0x45 + AA×6

APDU_TIME_TAG_NONE = b"\x00"           # ACTION-Request 尾部 OPTIONAL TimeTag，00=无

# A-XDR 标签（dl_t698_45_axdr.AXDR_TAG 的子集，本模块直接使用数值以免受文案改动影响）
_TAG_NULL = 0x00
_TAG_STRUCTURE = 0x02
_TAG_BIT_STRING = 0x04
_TAG_DOUBLE_LONG_UNSIGNED = 0x06       # [6] double-long-unsigned（长帧传输块尺寸）
_TAG_OCTET_STRING = 0x09
_TAG_VISIBLE_STRING = 0x0A
_TAG_LONG_UNSIGNED = 0x12              # [18] long-unsigned（短帧传输块尺寸）
_TAG_ENUM = 0x16
_TAG_DATE_TIME_S = 0x1C                # 定长 7 字节、**无长度域**

_MAX_SHORT_BLOCK_SIZE = 0xFFFF         # 超过则传输块尺寸改用长帧 [6]


# ─── A-XDR 长度域（BER） ────────────────────────────────────────────────────
def _ber_len(length: int) -> bytes:
    """A-XDR/BER 长度域：<128 短形式；≥128 为 `0x80|n` + n 字节大端长度。

    长度口径**单一来源** = `AXDRCoder._encode_length`（DL/T 790.6-2010 A-XDR），
    本模块只做非负校验后转调，避免第二份实现漂移。
    实测：4 → `04`（doc 校验值长度、短形式）、600 → `82 02 58`、2000 → `82 07 D0`。
    """
    if length < 0:
        raise ValueError(f"长度不能为负: {length}")
    return AXDRCoder._encode_length(length)


def _visible_string(text: str) -> bytes:
    """visible-string：`0A <BER长度> <ASCII 字节>`。

    供「文件信息」的源/目标文件名与文件版本使用；非 ASCII 字符按 replace 兜底。
    """
    data = (text or "").encode("ascii", errors="replace")
    return bytes([_TAG_VISIBLE_STRING]) + _ber_len(len(data)) + data


# ─── SA 地址 ────────────────────────────────────────────────────────────────
def build_sa(addr_type: int = 1, logic_addr: int = 0, addr_len: int = 6,
             addr_bytes: bytes = b"") -> bytes:
    """组装 698.45 服务器地址 SA（地址特征字节 + 地址体）。

    规范 §6.2.4.2.4：特征 = `(类型&3)<<6 | (逻辑地址&3)<<4 | (长度-1)&0x0F`；
    类型 0 单地址 / 1 通配 / 2 组 / 3 广播（广播固定 1 字节 `AA`，无地址体）。
    `addr_bytes` 按**大端正序**（人书写顺序）给出，线上**逆序**拼在特征字节后
    （与 `frame_gen_widget._get_dlt698_sa` / `build_dlt698_sa` 同一口径）；地址体
    不足 `addr_len` 时补零（通配补 `AA`），超出则截断。长度不在 1..16 抛 ValueError。
    例：单地址 `075506980033` ⇒ `05 33 00 98 06 55 07`（doc 实帧）；默认参数 ⇒ `45 AA×6`。
    """
    addr_type = int(addr_type or 0)
    logic_addr = int(logic_addr or 0)
    addr_len = int(addr_len or 0)

    if not 1 <= addr_len <= 16:
        raise ValueError(
            f"地址长度非法: {addr_len}（698.45 地址特征字节 D3-D0 表示 1~16 字节，"
            "请在 1..16 之间选择）"
        )

    if addr_type == 3:                      # 广播地址：固定 1 字节 AA，忽略长度/逻辑地址
        return bytes([0xAA])

    feature = ((addr_type & 0x03) << 6) | ((logic_addr & 0x03) << 4) | ((addr_len - 1) & 0x0F)

    body = bytes(addr_bytes or b"")
    if len(body) < addr_len:
        # 通配地址的地址体规范规定全 AA；其余类型按补零处理
        body += bytes([0xAA if addr_type == 1 else 0x00]) * (addr_len - len(body))
    elif len(body) > addr_len:
        body = body[:addr_len]

    return bytes([feature]) + body[::-1]    # 书写序大端 → 线上逆序


# ─── 分包 ───────────────────────────────────────────────────────────────────
def split_blocks(data: bytes, block_size: int) -> List[bytes]:
    """按 `block_size` 把升级包切成数据块列表（写文件方法8 每帧携带一块）。

    块序号 0 基（doc 首块 = `12 00 00`）；末包为余数，长度可小于 `block_size`。
    空数据返回空列表；`block_size <= 0` 抛 ValueError（避免死循环/除零）。
    """
    data = bytes(data or b"")
    block_size = int(block_size)
    if block_size <= 0:
        raise ValueError(f"每包字节数必须为正整数: {block_size}")
    return [data[i:i + block_size] for i in range(0, len(data), block_size)]


def block_count(total: int, block_size: int) -> int:
    """总字节数 `total` 按 `block_size` 分包的包数（等价 ceil；0 ⇒ 0 包）。

    与 `split_blocks` 判据一致（升级包为空 ⇒ 零块 ⇒ 不发写文件帧），
    `block_size <= 0` 同 `split_blocks` 抛 ValueError。
    """
    total = int(total)
    block_size = int(block_size)
    if block_size <= 0:
        raise ValueError(f"每包字节数必须为正整数: {block_size}")
    if total <= 0:
        return 0
    return (total + block_size - 1) // block_size


@dataclass(frozen=True)
class UpgradePlan:
    """分包计划（design §2）：总字节数 / 每包字节数 ⇒ 总包数 / 末包字节数。

    仅做算术封装，供 UI 显示「第 x/N 包」与进度分母；不含任何 Qt 依赖。
    """

    total_bytes: int
    block_size: int

    @classmethod
    def for_data(cls, data: bytes, block_size: int = DEFAULT_BLOCK_SIZE) -> "UpgradePlan":
        """由升级包字节构造计划。"""
        return cls(total_bytes=len(bytes(data or b"")), block_size=int(block_size))

    @property
    def num_blocks(self) -> int:
        """总包数（空文件为 0 包）。"""
        return block_count(self.total_bytes, self.block_size)

    @property
    def last_block_bytes(self) -> int:
        """末包字节数（= 余数，整除时等于 block_size；无包时为 0）。"""
        if self.num_blocks == 0:
            return 0
        rem = self.total_bytes % self.block_size
        return rem if rem else self.block_size


# ─── 文件信息（表188 属性2） ────────────────────────────────────────────────
def build_file_info(size: int, source: str = "", target: str = "",
                    attr_byte: int = 0xE0, version: str = "v1.0",
                    category: int = 0) -> bytes:
    """编码「文件信息」结构（启动传输方法7 的第 1 个参数）。

    表188 属性2 ::= structure{源文件名 visible-string, 目标文件名 visible-string,
    文件大小 double-long-unsigned, 文件属性 bit-string(SIZE(3)), 文件版本
    visible-string, 文件类别 enum{当前设备文件(0)/其他设备文件(1)}}
    ⇒ `02 06 | 0A<len>源 | 0A<len>目标 | 06<u32BE 大小> | 04 03<属性字节> | 0A<len>版本 | 16<类别>`。
    `文件属性` 直接拼 `04 03 <字节>`（长度域写**位数** 3 = SIZE(3)），不走
    `AXDRCoder._encode_bit_string`，从而绕开位序解释分歧（design §13 开放问题2）。
    """
    size = int(size)
    if size < 0:
        raise ValueError(f"文件大小不能为负: {size}")
    out = bytearray([_TAG_STRUCTURE, 6])
    out += _visible_string(source)
    out += _visible_string(target)
    out += bytes([_TAG_DOUBLE_LONG_UNSIGNED]) + (size & 0xFFFFFFFF).to_bytes(4, "big")
    out += bytes([_TAG_BIT_STRING, 3, int(attr_byte) & 0xFF])
    out += _visible_string(version)
    out += bytes([_TAG_ENUM, int(category) & 0xFF])
    return bytes(out)


# ─── 三帧构建 ───────────────────────────────────────────────────────────────
def build_start_transfer(sa: bytes, ca: int, piid: int, file_info: bytes,
                         block_size: int, check_type: int = 0,
                         check_value: bytes = b"") -> bytes:
    """组「启动传输」整帧（方法7，OMD=F0010700）。

    参数 ::= `02 03 | 文件信息 | 传输块大小 | 校验 | TimeTag(00)`，
    校验 ::= `02 02 | 16<校验类型> | 09<BER长度><校验值>`（doc `02 02 16 00 09 04 7F 7E D9 D2`）。
    传输块大小的 CHOICE `[18]/[6]` 恰与 A-XDR 同值标签：≤65535 用短帧 `12<u16BE>`
    （doc 2000 ⇒ `12 07 D0`），更大自动切长帧 `06<u32BE>`；备选内容为**裸值**（不带自身
    tag/长度，依据 doc 实帧与既有 Get-Result 口径）。链路层交 `generate_action_request_normal`。
    """
    block_size = int(block_size)
    if block_size <= 0:
        raise ValueError(f"传输块大小必须为正整数: {block_size}")

    if block_size > _MAX_SHORT_BLOCK_SIZE:
        block_field = bytes([_TAG_DOUBLE_LONG_UNSIGNED]) + block_size.to_bytes(4, "big")
    else:
        block_field = bytes([_TAG_LONG_UNSIGNED]) + block_size.to_bytes(2, "big")

    value = bytes(check_value or b"")
    check_field = (bytes([_TAG_STRUCTURE, 2])
                   + bytes([_TAG_ENUM, int(check_type) & 0xFF])
                   + bytes([_TAG_OCTET_STRING]) + _ber_len(len(value)) + value)

    param = (bytes([_TAG_STRUCTURE, 3])
             + bytes(file_info)
             + block_field
             + check_field
             + APDU_TIME_TAG_NONE)
    return DLT69845FrameGenerator().generate_action_request_normal(
        sa, int(ca), int(piid), OMD_START, param)


def build_write_block(sa: bytes, ca: int, piid: int, block_index: int,
                      block_data: bytes) -> bytes:
    """组「写文件」整帧（方法8，OMD=F0010800；每包一帧）。

    参数 ::= `02 02 | 12<u16BE 块序号> | 09<BER长度><块数据> | TimeTag(00)`。
    块序号 0 基（doc 首块 `12 00 00`）；PIID 每帧自增（doc：启动传输 0、首块 1）。
    块数据 BER 长形式自动：600 ⇒ `09 82 02 58`、2000 ⇒ `09 82 07 D0`（与 doc 同形）。
    序号 >65535 无法用 `[18]` 短帧表达 ⇒ 抛 ValueError。
    """
    block_index = int(block_index)
    if block_index < 0:
        raise ValueError(f"块序号不能为负: {block_index}")
    if block_index > _MAX_SHORT_BLOCK_SIZE:
        raise ValueError(
            f"块序号超出 [18] 短帧传输块序号上限 65535: {block_index}"
            "（请增大每包字节数或减小文件大小）"
        )

    data = bytes(block_data or b"")
    param = (bytes([_TAG_STRUCTURE, 2])
             + bytes([_TAG_LONG_UNSIGNED]) + block_index.to_bytes(2, "big")
             + bytes([_TAG_OCTET_STRING]) + _ber_len(len(data)) + data
             + APDU_TIME_TAG_NONE)
    return DLT69845FrameGenerator().generate_action_request_normal(
        sa, int(ca), int(piid), OMD_WRITE, param)


def build_exec_upgrade(sa: bytes, ca: int, piid: int, exec_time: Optional[bytes] = None,
                       license_bytes: bytes = b"") -> bytes:
    """组「执行升级」整帧（方法13，OMD=F0010D00）。

    参数 ::= `02 02 | 1C<7B 执行升级时间> | 软件许可 CHOICE | TimeTag(00)`。
    执行升级时间 = `date_time_s` ≡ `octet-string(SIZE(7))`：**tag + 定长 7 字节、无长度域**
    （规范类型表 tag=28/SIZE=7 + 附录示例 `1C 07 E0 01 14 00 00 00`；本仓既有编码器多写
    长度域，故此处不依赖它，design §6.3）。默认全 FF = 立即执行（规范明文）。
    软件许可默认 NULL=`00`；给了许可字节则**原样透传**（不猜 CHOICE 内 tag/长度，design §13-3）。
    """
    when = bytes(IMMEDIATE_EXEC_TIME if exec_time is None else exec_time)
    if len(when) != 7:
        raise ValueError(f"执行升级时间(date_time_s)必须为 7 字节: 收到 {len(when)} 字节")

    lic = bytes(license_bytes or b"")
    param = (bytes([_TAG_STRUCTURE, 2])
             + bytes([_TAG_DATE_TIME_S]) + when
             + (lic if lic else bytes([_TAG_NULL]))
             + APDU_TIME_TAG_NONE)
    return DLT69845FrameGenerator().generate_action_request_normal(
        sa, int(ca), int(piid), OMD_EXEC, param)


# ─── 读版本信息（GET-Request Normal） ──────────────────────────────────────
def build_read_version(sa: bytes, ca: int, piid: int,
                       oad: bytes = OAD_VERSION) -> bytes:
    """组「读版本信息」整帧（GET-Request Normal，OAD 默认 `43 00 03 00`）。

    APDU = `05 01 <PIID> <OAD> 00`（末尾 `00` = TimeTag 无时间标签）；SA/CA 由调用方
    给（本页取与升级传输**同一份** SA/CA 配置）。实帧口径已自证：SA=单地址 + `AA×6`、
    CA=0、PIID=1 时**逐字节等于**现场实帧
    `68 17 00 43 05 AA AA AA AA AA AA 00 AA 2A 05 01 01 43 00 03 00 00 6D 5C 16`
    （含 HCS/FCS）。
    """
    oad = bytes(oad)
    if len(oad) != 4:
        raise ValueError(f"OAD 必须是 4 字节（例 43000300），收到 {len(oad)} 字节")
    return DLT69845FrameGenerator().generate_get_request_normal(
        sa, int(ca), int(piid), oad, time_tag_none=True)


# ─── 校验值 ─────────────────────────────────────────────────────────────────
def calc_checksum_value(data: bytes, kind: str = "crc", endian: str = "big") -> bytes:
    """计算「启动传输」参数里的校验值字节（文件内容摘要，供从站校验整包）。

    kind：`crc`/`CRC` → `zlib.crc32`（X.25 多项式族，非 CRC16）得 32 位整数，按 `endian`
    （`big` 默认 / `little`）输出 4 字节；`md5`/`MD5` → 16 字节；`sha1`/`SHA1` → 20 字节
    （摘要为字节串，忽略 `endian`）。未知 kind / 未知字节序抛 ValueError。
    ⚠ doc 只给校验值 `7F 7E D9 D2`、未给对应文件 ⇒ **不宣称**与现场设备一致，UI 允许手工覆盖。
    """
    data = bytes(data or b"")
    k = (kind or "").strip().lower()
    if k == "crc":
        val = zlib.crc32(data) & 0xFFFFFFFF
        e = (endian or "big").strip().lower()
        if e not in ("big", "little"):
            raise ValueError(f"CRC 字节序只支持 big/little: {endian}")
        return val.to_bytes(4, e)
    if k == "md5":
        return hashlib.md5(data).digest()
    if k == "sha1":
        return hashlib.sha1(data).digest()
    raise ValueError(f"未知校验类型: {kind}（支持 crc / md5 / sha1）")


# ─── 确认判定 ───────────────────────────────────────────────────────────────
def check_action_response(frame: bytes, expect_omd: bytes) -> dict:
    """判定一帧接收报文是否为**本步**的 ACTION-Response Normal 成功确认。

    判据一律走 `DLT69845Parser` 的解析结果（design 不变量4：不做字符串/字节比对）：
    解析状态=="成功" ∧ HCS/FCS 均"通过" ∧ APDU 服务码 0x87 ∧ 子类型=="ActionResponseNormal"
    ∧ OMD 原始值==`expect_omd` ∧ DAR(结果)==0 ⇒ ok=True。DAR≠0 的 reason 带 `DAR说明`
    与「需重试」（重试用尽由调用方停止）。任何坏帧/异常都被吞掉 ⇒ **永不抛异常**。
    Returns: {"ok": bool, "reason": str, "dar": int|None, "omd": str, "apdu_type": str}
    """
    out = {"ok": False, "reason": "", "dar": None, "omd": "", "apdu_type": ""}
    try:
        result = DLT69845Parser().parse(bytes(frame or b""))
        if result.get("解析状态") != "成功":
            out["reason"] = f"帧解析失败：{result.get('错误信息', '未知原因')}"
            return out

        # HCS/FCS：解析器只把不符写进「校验结果」、解析状态仍是"成功" ⇒ 载荷被破坏的
        #        坏帧必须在此拦下，否则会被误判为确认（变异反证见测试 A6）。
        bad = [name for name, key in (("HCS", "帧头校验HCS"), ("FCS", "帧校验FCS"))
               if (result.get(key) or {}).get("校验结果") != "通过"]
        if bad:
            out["reason"] = "帧解析失败：" + "/".join(bad) + " 校验不通过"
            return out

        link = result.get("链路用户数据") or {}
        apdu = link.get("APDU")
        if not isinstance(apdu, dict):
            out["reason"] = "帧解析失败：无 APDU 内容" + (
                f"（{link.get('APDU解析错误')}）" if link.get("APDU解析错误") else "")
            return out

        out["apdu_type"] = str(apdu.get("APDU类型", ""))
        if apdu.get("解析状态") != "成功" or str(apdu.get("服务码", "")) != "0x87":
            out["reason"] = f"不是 ACTION-Response（APDU 类型={out['apdu_type'] or '未知'}）"
            return out
        if apdu.get("子类型") != "ActionResponseNormal":
            out["reason"] = f"不是 ACTION-Response Normal（子类型={apdu.get('子类型', '-')}）"
            return out

        omd = (apdu.get("OMD") or {}).get("原始值", "")
        out["omd"] = str(omd)
        expect = bytes(expect_omd).hex().upper()
        if str(omd).upper() != expect:
            out["reason"] = f"OMD 不符：收到 {omd or '-'}，期望 {expect}"
            return out

        dar = (apdu.get("结果") or {}).get("解析值", None)
        out["dar"] = dar if isinstance(dar, int) else None
        if not isinstance(dar, int):
            out["reason"] = "响应缺少 DAR 结果字节"
            return out
        if dar != 0:
            desc = (apdu.get("结果") or {}).get("DAR说明", "")
            out["reason"] = f"DAR={dar} {desc}（需重试）"
            return out

        out["ok"] = True
        out["reason"] = "确认成功"
        return out
    except Exception as exc:                     # 坏帧不得抛异常（调用方在串口回调线程）
        out["reason"] = f"帧解析失败：{exc}"
        return out


#: 「数据业务」/「数据」子树里最多取多少个字段与多少字符进日志（防一屏全是版本内容）
_VERSION_TEXT_MAX_FIELDS = 8
_VERSION_TEXT_MAX_CHARS = 160


def _version_text(apdu: dict) -> str:
    """从 GET-Response 的解析结果取**可读版本内容**（尽量给命名字段，否则给数据值串）。

    优先级：① 解析器已按 OAD 业务解码出的「数据业务」（如 厂商代码/软件版本号/…）；
    ② 「数据」子树里各成员的 解析值；③ 都没有则空串（调用方按「响应未带数据」处理）。
    长度上界 `_VERSION_TEXT_MAX_CHARS` 字符（超长截断并加省略号），避免刷屏日志。
    """
    def _clip(text: str) -> str:
        return text if len(text) <= _VERSION_TEXT_MAX_CHARS else \
            text[:_VERSION_TEXT_MAX_CHARS] + "…"

    biz = apdu.get("数据业务")
    if isinstance(biz, dict) and biz:
        items = [f"{k}={v}" for k, v in list(biz.items())[:_VERSION_TEXT_MAX_FIELDS]]
        if len(biz) > _VERSION_TEXT_MAX_FIELDS:
            items.append(f"…（共 {len(biz)} 项）")
        return _clip("，".join(items))

    data = apdu.get("数据")
    values = data.get("解析值") if isinstance(data, dict) else None
    if isinstance(values, list):
        cells = []
        for item in values[:_VERSION_TEXT_MAX_FIELDS]:
            if isinstance(item, dict):
                cells.append(str(item.get("解析值", item.get("原始值", ""))))
            else:
                cells.append(str(item))
        if len(values) > _VERSION_TEXT_MAX_FIELDS:
            cells.append(f"…（共 {len(values)} 项）")
        return _clip(" ".join(c for c in cells if c))
    if isinstance(data, dict):
        return _clip(str(data.get("解析值", data.get("原始值", ""))))
    return ""


def version_rows(apdu: dict) -> List[dict]:
    """GET-Response 的**逐字段明细**：`[{"名称", "值", "原始", "长度"}]`（详细解析用）。

    - 标准/厂家扩展的「版本信息形状」结构（6×visible-string）⇒ 按表191 逐项命名
      （`厂商代码/软件版本号/软件版本日期/硬件版本号/硬件版本日期/厂商扩展信息`，日期补全为
      `20YY-MM-DD`）；**长度与表191 声明不一致时追加一行 ⚠ 说明**（命名照给 —— 值与原文字节
      一起展示，是否采信由现场判断）；
    - 其他（单个 visible-string / octet-string / 数组…）⇒ 一条 `数据` 行（值 = 解析值，原始 = 编码字节）。
    命名与日期规则一律来自 :mod:`dl_t698_45_data_decode`（**不在此处再写一份字段名**）。
    """
    rows: List[dict] = []
    data = apdu.get("数据") if isinstance(apdu, dict) else None
    members = version_like_members(data)
    if members is not None:
        named = decode_version_info(data) or {}
        for i, member in enumerate(members):
            name = VERSION_FIELDS[i] if i < len(VERSION_FIELDS) else f"字段{i + 1}"
            rows.append({
                "名称": name,
                "值": str(named.get(name, member.get("解析值", ""))),
                "原始": str(member.get("原始编码", "")).upper(),
                "长度": len(str(member.get("原始值", ""))) // 2,
            })
        if not version_lengths_match(members):
            actual = tuple(r["长度"] for r in rows)
            rows.append({
                "名称": "⚠ 长度未自证",
                "值": f"表191 声明 {VERSION_FIELD_BYTES}，本次实发 {actual}",
                "原始": "", "长度": 0,
            })
        return rows

    if isinstance(data, dict):
        value = data.get("解析值", data.get("原始值", ""))
        if isinstance(value, (list, dict)):
            value = data.get("原始值", "")
        rows.append({
            "名称": "数据",
            "值": str(value),
            "原始": str(data.get("原始编码", "")).upper(),
            "长度": len(str(data.get("原始值", ""))) // 2,
        })
    return rows


def check_get_response(frame: bytes, expect_oad: bytes = OAD_VERSION) -> dict:
    """判定一帧接收报文是否为「读版本信息」的 GET-Response Normal 成功响应。

    判据同样一律走 `DLT69845Parser`（不做字符串/字节比对）：解析状态=="成功" ∧ HCS/FCS
    均"通过" ∧ 服务码 0x85 ∧ 子类型=="GetResponseNormal" ∧ OAD 原始值==`expect_oad`；
    然后按 Get-Result 的 CHOICE（表54：`错误信息[0] DAR` / `数据[1] Data`）分流：
    - 解析结果里有 `数据访问结果` ⇒ 是错误信息：DAR≠0 → ok=False（reason 带 DAR 说明，调用方按重试处理）；
      DAR==0 → ok=True 但 `version` 为空（响应未带数据）；
    - 有 `数据` ⇒ ok=True，`version` 取 `_version_text()`（命名业务字段优先）。
    任何坏帧/异常都被吞掉 ⇒ **永不抛异常**。
    Returns: {"ok", "reason", "dar", "oad", "apdu_type", "version", "data_business"}
    """
    out = {"ok": False, "reason": "", "dar": None, "oad": "", "apdu_type": "",
           "version": "", "data_business": {}, "rows": []}
    try:
        result = DLT69845Parser().parse(bytes(frame or b""))
        if result.get("解析状态") != "成功":
            out["reason"] = f"帧解析失败：{result.get('错误信息', '未知原因')}"
            return out

        bad = [name for name, key in (("HCS", "帧头校验HCS"), ("FCS", "帧校验FCS"))
               if (result.get(key) or {}).get("校验结果") != "通过"]
        if bad:
            out["reason"] = "帧解析失败：" + "/".join(bad) + " 校验不通过"
            return out

        link = result.get("链路用户数据") or {}
        apdu = link.get("APDU")
        if not isinstance(apdu, dict):
            out["reason"] = "帧解析失败：无 APDU 内容" + (
                f"（{link.get('APDU解析错误')}）" if link.get("APDU解析错误") else "")
            return out

        out["apdu_type"] = str(apdu.get("APDU类型", ""))
        if apdu.get("解析状态") != "成功" or str(apdu.get("服务码", "")) != "0x85":
            out["reason"] = f"不是 GET-Response（APDU 类型={out['apdu_type'] or '未知'}）"
            return out
        if apdu.get("子类型") != "GetResponseNormal":
            out["reason"] = f"不是 GET-Response Normal（子类型={apdu.get('子类型', '-')}）"
            return out

        oad = (apdu.get("OAD") or {}).get("原始值", "")
        out["oad"] = str(oad)
        expect = bytes(expect_oad).hex().upper()
        if str(oad).upper() != expect:
            out["reason"] = f"OAD 不符：收到 {oad or '-'}，期望 {expect}"
            return out

        if "数据访问结果" in apdu:                 # Get-Result = 错误信息[0] DAR
            dar = (apdu.get("数据访问结果") or {}).get("解析值", None)
            out["dar"] = dar if isinstance(dar, int) else None
            if not isinstance(dar, int):
                out["reason"] = "响应缺少 DAR 结果字节"
                return out
            if dar != 0:
                desc = (apdu.get("数据访问结果") or {}).get("说明", "")
                out["reason"] = f"DAR={dar} {desc}（需重试）"
                return out
            out["ok"] = True
            out["reason"] = "响应 DAR=0 但未带数据"
            return out

        if not isinstance(apdu.get("数据"), dict):
            out["reason"] = "响应里既没有数据也没有数据访问结果"
            return out
        out["ok"] = True
        out["reason"] = "读取成功"
        biz = apdu.get("数据业务")
        out["data_business"] = dict(biz) if isinstance(biz, dict) else {}
        out["version"] = _version_text(apdu)
        out["rows"] = version_rows(apdu)          # 逐字段明细（详细解析）
        return out
    except Exception as exc:                     # 坏帧不得抛异常（调用方在串口回调线程）
        out["reason"] = f"帧解析失败：{exc}"
        return out


__all__ = [
    "OMD_START", "OMD_WRITE", "OMD_EXEC", "OAD_VERSION", "OAD_INTERNAL_VERSION",
    "DEFAULT_BLOCK_SIZE", "IMMEDIATE_EXEC_TIME", "WILDCARD_SA",
    "build_sa", "split_blocks", "block_count", "UpgradePlan",
    "build_file_info", "build_start_transfer", "build_write_block",
    "build_exec_upgrade", "build_read_version", "calc_checksum_value",
    "check_action_response", "check_get_response", "version_rows",
]
