# -*- coding: utf-8 -*-
"""按协议分帧 / 判「已开始未收全」的**纯逻辑**族。

自 ``serial_tool_widget.py`` **原样搬出**（判据一字未改），搬到本模块的动机：
升级页（协议8 文件传输升级）要复用同一套分帧判据，而 ``serial_tool_widget`` 是
Qt 模块 ⇒ 纯逻辑必须先落地到这里，由 ``serial_tool_widget`` **保留同名 re-export**
（既有测试锚点 ``stw.frame_length_for`` / ``stw.declared_frame_len`` /
``stw._wakeup_base`` / ``stw.hdlc_frame_len`` / ``SerialToolWidget._declared_frame_len``
一字不变，且指向同一函数对象）。

口径（与搬出前完全一致，AGENTS.md §8 陷阱 59/75）：
  - 每种策略都要求**自证**，任一条件不满足就返回 0，交回调用方既有的
    「帧结构优先 + 时间聚合」路径 —— 错切帧比不切更糟。
  - 68 家族帧可带帧首连续 ``0xFE`` 前导码 ⇒ 判定一律复用 :mod:`wakeup_prefix`
    （**单一来源**，本层不得另写 FE 扫描），且长度返回值**含前导字节数**
    （调用方仍按 ``buf[need-1] == 0x16`` 自证）。

本模块**纯逻辑**：零 Qt、零 GUI、零解析器依赖（只依赖 stdlib 与本仓库 ``wakeup_prefix``），
可被串口页 / 蓝牙页 / 升级页以及无 GUI 的脚本安全引用。
"""

from typing import Optional

import wakeup_prefix

# ── 整帧长度合理区间 ───────────────────────────────────────────────────
# 「按帧结构分帧」的整帧长度合理区间（字节）。长度域算出该区间外的值视为不可信，
# 退回时间聚合，避免把任意以 68H 开头的数据当成帧。
RAW_MIN_FRAME_LEN = 8
RAW_MAX_FRAME_LEN = 8192

# HDLC 帧最小长度（字节）：7EH + 地址 + 控制 + FCS(2) + 7EH
HDLC_MIN_FRAME_LEN = 6


# ── 纯函数：按协议分帧 ────────────────────────────────────────────────
#
# 命令表带「协议」字段后，RX 不必再靠时间窗口猜帧边界，而是用**协议自身的
# 长度域/定界符**切帧。每种策略都要求自证，任一条件不满足就返回 0（交回
# 既有「帧结构优先 + 时间聚合」路径）—— 错切帧比不切更糟。

# 协议索引 → 分帧策略。未列出的协议（1/5/9/10/11）没有自证的长度域/定界符。
STRATEGY_BY_PROTOCOL = {
    0: "ft12_68",        # 南网：68H + L(2B 小端)，整帧 = L
    7: "ft12_68",        # 国网：同上（gdw10376_parser.py:333）
    6: "dlt645",         # 645：68H + A(6) + 68H + C + L(1B@9) + …，整帧 = L + 12
    8: "dlt698_45",      # 698.45：68H + L(2B 小端) + C + …，整帧 = L + 2（无第二个 68H）
    2: "hdlc_7e",        # HDLC/国网DLMS：7EH 定界（7DH 转义）
    3: "hdlc_7e",        # DLMS-APDU(国网)：同上（国网 DLMS 走 HDLC 7E 定界）
    4: "dlms_wrapper",   # DLMS Wrapper：版本 0001 + … + L(2B 大端@6)，整帧 = 8 + L
}

STRATEGY_NAMES = {
    "ft12_68": "68H+长度域(2B 小端)",
    "dlt645": "645 结构(68 A6 68)",
    "dlt698_45": "698.45 结构(68 L L C…)",
    "hdlc_7e": "HDLC 7EH 定界",
    "dlms_wrapper": "DLMS Wrapper 长度头",
}

# 以 16H 结尾的策略（长度域只给出长度，末字节 16H 才是自证）；HDLC 由 7EH 定界、
# DLMS Wrapper 由版本 + 长度域自证，都不需要额外的末字节校验。
END_CHAR_STRATEGIES = frozenset({"ft12_68", "dlt645", "dlt698_45"})

# 68 家族的分帧要认**前导 FEH 唤醒字节**（规范依据见 AGENTS §8 陷阱 75：
# DL/T 698.45-2017 §6.3.1 b)、DL/T 645-2007 §5.3.1）——判定复用 wakeup_prefix
# **单一来源**，不要在分帧层另写一份 FE 扫描。
# 现场报障（2026-10-13）：`FE FE FE FE 68 21 00 … 38 16`（39B，698.45）因首字节是 FE
# 被判「判不出长度」→ 走 10ms 静默窗口 → 一帧被切成两条 [RX]。
# HDLC（7EH 定界）与 DLMS Wrapper（00 01 版本头）**不**加前导容忍：它们首字节另有
# 语义（定界符/版本号），加容忍只会掩盖错帧。
FE_WAKEUP_STRATEGIES = frozenset({"ft12_68", "dlt645", "dlt698_45"})


def _wakeup_base(strategy: Optional[str], buf) -> int:
    """分帧前要跳过的前导 FE 字节数（非 68 家族恒为 0）。

    ``strategy is None`` = 未指定协议的启发式路径（它只处理 68 家族结构）⇒ 同样跳过。
    """
    if strategy is not None and strategy not in FE_WAKEUP_STRATEGIES:
        return 0
    return wakeup_prefix.wakeup_prefix_len(buf)


def _sane_frame_len(n: int) -> int:
    """整帧长度合理区间过滤：区间外视为不可信（返回 0）。"""
    return n if RAW_MIN_FRAME_LEN <= n <= RAW_MAX_FRAME_LEN else 0


def declared_frame_len(buf) -> int:
    """**未指定协议时**的启发式：推算缓冲起始处 68 帧的整帧长度；不可信返回 0。

    三种「68H + 长度域」结构（均以 16H 结尾）：

      - DLT645-2007：``68H + 地址(6B) + 68H + 控制码 + 数据长度 L(1B@9) + … + CS + 16H``，
        特征 = **第 8 字节是第二个起始符 68H**；整帧 = ``L + 12``。
      - 南网 / 国网：``68H + 长度域 L(2B 小端) + 控制域 + … + CS + 16H``，
        **L 就是整帧字节数**（`protocol_parser.py:72`、`gdw10376_parser.py:333`）。
      - 698.45：``68H + 长度域 L(2B 小端) + 控制域 + … + FCS + 16H`` —— **没有第二个
        68H**；L = 传输帧中**不含起始/结束字符**的数据长度（协议文档 6.2.2 a，L 本身
        含两个长度域字节）⇒ **整帧 = L + 2**（标准附录 H.1.1 示例：32 字节、L=30）。

    ⚠ 南网/国网 与 698.45 的**前 3 字节形态完全相同**（都是 ``68 L L``，第 4 字节是
    控制域而非定界符），故**不能**靠头部签名区分，只能用**末字节自证**：南网/国网的
    末字节恒为 16H，所以「按 L 到齐却不是 16H」即否定南网/国网口径，改按 698.45 的
    ``L + 2`` 判。历史上曾按「第 4 字节 = 68H」判定 698.45 —— 真实 698.45 帧没有这
    个字节（1.23.60 修正），该判据恒不命中，导致 698 帧被按南网口径算出 L（比真实
    整帧小 2）而永远切不开。

    长度域不可信时返回 0，交由时间聚合处理 —— 错切帧比不切更糟。

    **前导 FEH**（1.23.78）：68 家族帧可带帧首连续 `0xFE`（规范依据见 §8 陷阱 75），
    故先按 :func:`_wakeup_base` 跳过前导再判定三种结构，且返回值**含前导字节数**
    （调用方仍按 ``buf[need-1] == 0x16`` 自证）。
    """
    base = _wakeup_base(None, buf)
    if len(buf) - base < 8 or buf[base] != 0x68:
        return 0                      # 不足 8 字节还分不清三种结构
    lv = buf[base + 1] | (buf[base + 2] << 8)
    n68 = _sane_frame_len(lv)                                  # 南网/国网：L 即整帧
    data_len = lv & 0x3FFF
    unit = (lv >> 14) & 0x01
    n698 = _sane_frame_len((data_len * 1024 if unit else data_len) + 2)
    n645 = (_sane_frame_len(buf[base + 9] + 12)
            if (buf[base + 7] == 0x68 and len(buf) - base >= 10) else 0)
    # ① 末字节自证：已到齐且以 16H 收尾的那个口径就是它（南网/国网与 698 只能这样区分）
    for n in (n68, n645, n698):
        if n and len(buf) - base >= n and buf[base + n - 1] == 0x16:
            return base + n           # 含前导
    # ② 南网/国网口径已被末字节否定（按 L 已到齐却不是 16H）→ 只可能是 698.45
    if n68 and len(buf) - base >= n68:
        return base + n698 if n698 else 0
    # ③ 都还没收全：按头部分辨（645 特征 = 第 8 字节是第二个起始符 68H）
    n = n645 or n68
    return base + n if n else 0


def frame_length_for(strategy: str, buf) -> int:
    """按协议分帧策略推算**整帧长度**；不可信返回 0。

    协议已知时 ``ft12_68`` **只要长度域收齐（3 字节）** 就按南网/国网口径取长度
    —— 不再等满 8 字节才开工（策略本身已是选择，等满 8 字节会在首片过短时误走
    短静默窗口把整帧切碎，1.23.57 现场报障）。

    **结构排除改为末字节自证**：南网/国网的 L 就是整帧、末字节恒为 16H，故「按 L
    到齐却不是 16H」即否定本结构（典型：把 698.45 帧按本口径切 —— 其 L 比整帧小
    2），返回 0 交回回退路径；645 另有「第 8 字节起始符 + 末字节」双重自证。历史上
    的「第 4 字节 = 68H」判据基于**错误的** 698.45 帧格式（真实 698.45 帧没有第二个
    68H），恒不命中且会误导排查，已于 1.23.60 删除。详见 `declared_frame_len`。

    **前导 FEH**（1.23.78）：68 家族帧可带帧首连续 `0xFE`（规范依据见 §8 陷阱 75），
    故 68 家族三种策略先按 :func:`_wakeup_base` 跳过前导，下标一律偏移 ``base``，
    返回值**含前导字节数**；HDLC / DLMS Wrapper 不加前导容忍。
    """
    if not strategy or not buf:
        return 0
    base = 0
    if strategy == "hdlc_7e":
        return hdlc_frame_len(buf)
    if strategy == "dlms_wrapper":
        if len(buf) < 8 or buf[0] != 0x00 or buf[1] != 0x01:
            return 0
        wlen = int.from_bytes(bytes(buf[6:8]), "big")
        if wlen < 1:                  # 0 长度 APDU 非法
            return 0
        need = 8 + wlen
    else:
        # ── 68 家族：先跳过前导 FEH，其后所有下标偏移 base ──
        base = _wakeup_base(strategy, buf)
        if len(buf) - base < 3 or buf[base] != 0x68:
            return 0
        if strategy == "ft12_68":
            # 协议已知：长度域在第 1~2 字节即可算整帧长；末字节 16H 由调用方自证。
            need = buf[base + 1] | (buf[base + 2] << 8)
            # 字节够判时排除「不是南网/国网结构」的输入（AGENTS.md §8 陷阱 59 的自证版）
            if len(buf) - base >= 8 and buf[base + 7] == 0x68 and len(buf) - base >= 10:
                n645 = buf[base + 9] + 12
                if len(buf) - base >= n645 and buf[base + n645 - 1] == 0x16:
                    return 0              # ① 645 结构（起始符 + 末字节双自证）
            if len(buf) - base >= need and buf[base + need - 1] != 0x16:
                return 0                  # ② 按南网口径到齐却非 16H → 不是本结构
        elif strategy == "dlt645":
            if len(buf) - base < 10 or buf[base + 7] != 0x68:
                return 0
            need = buf[base + 9] + 12
        elif strategy == "dlt698_45":
            # 真实 698.45 链路帧**没有第二个 68H**（68 | L(2B) | C | … | FCS | 16）；
            # L 是不含首尾定界符的数据长度 ⇒ 整帧 = L + 2（6.2.2 a + 附录 H.1.1 自证）
            lv = buf[base + 1] | (buf[base + 2] << 8)
            n68 = lv                      # 南网/国网口径：L 即整帧
            if len(buf) - base >= n68 and buf[base + n68 - 1] == 0x16:
                return 0                  # 末字节自证是南网/国网帧，不是 698.45
            data_len = lv & 0x3FFF
            need = (data_len * 1024 if (lv >> 14) & 0x01 else data_len) + 2
        else:
            return 0                      # 其余策略没有自证的长度域/定界符
    if need < RAW_MIN_FRAME_LEN or need > RAW_MAX_FRAME_LEN:
        return 0
    return base + need                    # 含前导（调用方按 buf[need-1] 自证）


def hdlc_frame_len(buf) -> int:
    """HDLC 7EH 定界的整帧长度（**含首尾 7EH**）；未收全/不成立返回 0。

    帧内的 ``7EH``/``7DH`` 由发送方转义为 ``7DH 5EH``/``7DH 5DH``，所以 ``7EH``
    只可能是标志位 —— 定界本身即自证，不需要 FCS。输出含首尾标志，与
    `main_gui._extract_hdlc_frames` 同口径（`HDLCParser.parse` 正要求首字节 7EH）。

    连续 ``7E 7E``（共享标志位）不产生空帧：本函数消耗到**尾标志**（含），
    下一轮从尾标志之后重新找头，于是第二个 7EH 成为下一帧的头。
    """
    if len(buf) < 2 or buf[0] != 0x7E:
        return 0
    end = buf.find(0x7E, 1)
    if end < 0:
        return 0                      # 尾标志未到 → 等（受 FRAME_IDLE/HOLD 约束）
    need = end + 1
    if need < HDLC_MIN_FRAME_LEN or need > RAW_MAX_FRAME_LEN:
        return 0
    return need


# 设计文档（design.md §2）把 645 / DLMS Wrapper 两支记作独立函数名；现网实现里它们是
# frame_length_for 的两个分支（判据依赖 ``base`` 偏移，拆开会改动逻辑）⇒ 这里只做
# **同口径入口别名**，不复制判据：行为与 frame_length_for("<strategy>", buf) 完全一致。
def dlt645_frame_len(buf) -> int:
    """645（``dlt645`` 策略）整帧长度；实现见 :func:`frame_length_for`。"""
    return frame_length_for("dlt645", buf)


def dlms_wrapper_frame_len(buf) -> int:
    """DLMS Wrapper（``dlms_wrapper`` 策略）整帧长度；见 :func:`frame_length_for`。"""
    return frame_length_for("dlms_wrapper", buf)


def frame_incomplete(strategy: Optional[str], buf) -> bool:
    """缓冲里是否有一段**已开始但未收全**的协议帧（→ 应继续等，而非按静默刷出）。

    实测串口驱动的交付块间隔可大于 10ms 静默窗口，靠静默判定会把一帧切成多行；
    只要能算出还差多少字节（或 HDLC 已见到头标志），就按结构等到收全为止
    （受「断帧设置」里的**协议帧等待静默 / 协议帧等待上限**约束，两者现场可调）。

    **头标志已出现、但长度域还没收够字节时也算未收全**（1.23.43 实测报障）：
    首片只有 1~2 字节的 ``68`` 时读不出长度；若当「非协议帧」走 10ms 静默窗口，
    首片会被单独刷出，缓冲从下一片起不再以 68 开头 → 整帧被切成多行
    （实测国网 F112 响应拆成 4 条 ``[RX]``）。

    **前导 FE 也算「帧已开始」**（1.23.78 现场报障）：68 家族帧可带帧首连续 ``0xFE``
    （规范依据见 §8 陷阱 75），故先跳过前导再判长度 —— 否则首字节 0xFE 会让
    ``frame_length_for`` 判 0，一帧被 10ms 静默切成两行。

    ``buf`` = 调用方的接收缓冲（原 ``SerialToolWidget._raw_buffer``）；本函数**只读**，
    不消费字节 —— 任何情况下不得丢字节，纯 FE 噪声由「协议帧等待上限」兜底刷出。
    """
    if not buf:
        return False
    if strategy == "hdlc_7e":
        return buf[0] == 0x7E and buf.find(0x7E, 1) < 0
    if strategy == "dlms_wrapper":
        if len(buf) < 8:
            return True
        need = frame_length_for(strategy, buf)
        return bool(need) and len(buf) < need
    # 68 家族（含未指定协议的启发式）：先跳过前导 FEH
    base = _wakeup_base(strategy, buf)
    if base >= len(buf):
        return True          # 只见到前导 FE（还没见到帧头）→ 继续等（有等待上限兜底）
    rest = len(buf) - base
    # 长度域/第二起始符签名还没收够 → 继续等（勿按短静默切开）
    min_hdr = {
        "ft12_68": 3,       # 长度域在第 1~2 字节
        "dlt698_45": 3,     # 长度域在第 1~2 字节（真实 698.45 帧无第二个起始符）
        "dlt645": 10,       # 第二起始符在第 7，数据长度在第 9
    }.get(strategy or "")
    if buf[base] == 0x68 and min_hdr and rest < min_hdr:
        return True
    if not strategy and buf[base] == 0x68 and rest < 8:
        # 启发式：还不够区分 698/645/南网国网三种结构
        return True
    if strategy:
        need = frame_length_for(strategy, buf)
    else:
        need = declared_frame_len(buf)
    return bool(need) and len(buf) < need
