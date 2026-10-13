"""串行前导码（FEH）单一来源。

依据（两者都在仓库内，改前先复核）：

- DL/T 698.45-2017 §6.3.1 字节规则 b)：
  「在有效数据帧前加 4 个 FEH 作为前导码；」
  （``协议文档/8.698.45协议/面向对象的用电信息数据交换协议(20210910).md:509``）
  同节 c)：「数据链路层帧的字节之间无线路空闲间隔；两帧之间的线路空闲间隔至少 33 位。」
- DL/T 645-2007 §5.3.1 前导字节：
  「在主站发送帧信息之前，建议先发送 4 个字节 FEH，以唤醒接收方。」（``DLT645-2007.md:486``）

即 **68 家族链路帧允许（协议8 是要求）在帧前带 FEH 前导码**，前导码不属于帧内容。
本模块是全仓唯一的前导判定实现（协议8 解析器/校验器、协议6 解析器/校验器均引用），
禁止在调用点或 Web 侧另写一份（AGENTS.md §8 陷阱 31/75）。

口径：**只跳过帧首连续的 ``0xFE``**（0~N 个，不假定恰好 4 个，不猜测其它字节）。
68 家族帧的首字节恒为 ``0x68``，``0xFE`` 不可能是合法首字节 ⇒ 该剥离零误伤。

纯逻辑：零依赖、无 Qt、不 import 任何 parser（可被解析器/校验器/表格构建方安全引用）。
"""

from typing import List, Tuple

WAKEUP_BYTE = 0xFE

# 表格行名（协议8 与协议6 共用，避免两端写出两个名字导致消费方（摘要/查询页）漏匹配）
WAKEUP_FIELD_NAME = "唤醒前导字节"


def wakeup_prefix_len(data: bytes) -> int:
    """返回帧首连续 ``0xFE`` 的字节数（无前导返回 0）。"""
    if not data:
        return 0
    n = 0
    while n < len(data) and data[n] == WAKEUP_BYTE:
        n += 1
    return n


def strip_wakeup_prefix(data: bytes) -> Tuple[bytes, int]:
    """剥离帧首连续 ``0xFE`` 前导码，返回 ``(帧字节, 跳过字节数)``。

    无前导时原样返回（**恒等操作**）：既有「无 FE 帧行为逐行不变」的硬约束依赖这一点。
    """
    skipped = wakeup_prefix_len(data)
    if not skipped:
        return data, 0
    return data[skipped:], skipped


def wakeup_display(skipped: int) -> str:
    """把跳过字节数渲染成 ``FE FE FE FE`` 形式（表格「原始值」列用）。"""
    return " ".join(["FE"] * max(0, int(skipped)))


def make_wakeup_row(skipped: int, note: str) -> tuple:
    """构造表格首行的前导码行：``(行名, 原始值, 解析值, 说明, 0, skipped-1)``。"""
    n = max(1, int(skipped))
    return (
        WAKEUP_FIELD_NAME,
        wakeup_display(skipped),
        "-",
        note,
        0,
        n - 1,
    )


def shift_row_offsets(rows: List[tuple], delta: int) -> List[tuple]:
    """把表格行的字节偏移（第 5、第 6 列）整体 ``+delta``。

    只有两列**同时是 int** 的行才位移；``None``（APDU 子行、提示行等）原样保留 —— 与
    ``main_gui.parse_single`` 的 ED 头部偏移修正同一口径。``delta == 0`` 时原样返回。
    """
    step = int(delta)
    if not step:
        return list(rows)
    shifted: List[tuple] = []
    for row in rows:
        if len(row) >= 6 and isinstance(row[4], int) and isinstance(row[5], int):
            row = (row[0], row[1], row[2], row[3], row[4] + step, row[5] + step)
        shifted.append(row)
    return shifted
