# -*- coding: utf-8 -*-
"""
协议9（通感一体化）多物理块帧 PB 大小推断 + PBCS CRC-24 三态校验回归测试
直接运行: python test/test_csg_pb_size_pbcs.py

覆盖（参见 .trellis/tasks/09-08-csg-pb-size-pbcs-crc24/）:
- T1 真实 4-PB 抓包帧（CMT=1→映射136，帧长 2096=16+4×520）：按 520 切片，
     PBH 序列号 0/1/2/3，出现「PB大小推断」提示行，4 行 PBCS 为置零告警
- T2 合成 4×136 PB 帧（CMT=4→映射136 与帧长自洽）：无推断行，4 行 PBCS 校验通过
- T3 篡改 PB[2] 的 PBCS 为非零错误值：该行显示「校验失败(计算值=...)」
- T4 截掉末 PB 尾部 4 字节：不抛异常，末 PB 显示「PBCS缺失(帧截断)」
- T5 展示顺序：逐块交错「PBH→块体→PBCS」；噪声载荷块体按原始报文展示且
     抑制 MAC/MSDU 伪解析行（出现「MAC重组解析=无法解析」标记行）
- T6 合法 MAC 帧体：块体行之后仍有 MAC/MSDU 解析行（抑制不误伤合法帧）
"""

import _path_setup  # noqa: E402

import crcmod
from csg_new_gen_parser import CSGNewGenParser

# CRC-24 参数与解析器 _crc24 一致：poly=0x1800063, init=0, rev=True, xorOut=0
_crc24_func = crcmod.mkCrcFun(0x1800063, initCrc=0x000000, rev=True, xorOut=0x000000)
# CRC-32 (IEEE 802.3)：与解析器 MAC 帧完整性校验一致，用于构造合法 MAC 帧
_crc32_func = crcmod.mkCrcFun(0x104C11DB7, initCrc=0x000000, rev=True, xorOut=0xFFFFFFFF)

# 真实抓包帧（2096 字节 = FC 16 + 4×520 PB），来源 _tmp_test/probe_frame.hex，
# 内嵌于此以便测试不依赖 _tmp_test 目录
REAL_FRAME_HEX = (
    "09 01 F0 FF 01 00 00 14 DE 05 20 80 10 D8 F2 95 00 00 00 00 2C 27 5A 1F"
    "4C 05 0D 0E 58 05 4C 55 5A 36 29 61 72 48 17 46 0F 3F 1D 6D 7B 56 61 7E"
    "33 0A 57 01 08 25 7A 6B 41 4B 38 25 6E 38 61 6A 4F 79 5B 08 4D 61 65 2D"
    "50 64 42 07 5C 51 47 72 49 4A 76 59 2C 42 10 5D 1A 7A 6A 56 0C 2C 78 5E"
    "1C 71 31 31 4B 70 48 0F 1C 6C 53 0F 1D 61 47 72 4B 1A 2C 3B 46 3E 1C 0B"
    "03 5E 71 5F 36 12 53 4F 0D 1E 66 6F 6F 64 30 25 7A 7C 0D 46 10 23 57 7D"
    "2F 72 35 2D 61 0C 27 72 78 2E 56 58 56 34 7A 4F 4B 0A 2B 3F 22 53 00 06"
    "24 4C 4F 71 1B 0C 08 55 2F 55 7B 0A 63 6B 12 02 58 2F 22 13 01 12 63 26"
    "43 3E 59 39 6B 3D 67 6A 24 44 6D 65 2D 7D 57 16 37 77 02 76 5F 68 40 35"
    "76 5E 73 6E 62 71 51 4D 5C 3B 58 4B 3E 5F 41 46 34 30 55 29 02 75 6A 21"
    "44 1C 77 65 17 13 70 29 06 47 1F 52 2E 44 22 5D 52 3C 4A 28 76 58 2C 5A"
    "79 57 7A 5C 7A 21 49 1F 04 4F 63 04 58 1F 7C 45 7C 58 24 15 31 76 5B 32"
    "6C 00 69 38 66 60 3F 0B 74 19 21 32 49 10 00 52 68 50 7C 3D 00 3C 3C 55"
    "58 6C 25 14 63 14 27 01 41 5E 3A 3E 1E 49 6E 43 4D 72 5C 30 2B 45 4F 06"
    "7D 5D 05 18 56 5B 4B 3D 54 50 3E 33 21 5E 0D 24 65 65 60 04 3A 15 09 17"
    "5B 18 7D 06 7C 6E 3A 42 33 34 66 35 22 25 03 17 01 00 59 0F 60 2B 1C 5A"
    "2B 3D 4F 39 70 60 6F 69 0F 5F 31 1F 57 76 22 29 66 69 4E 2C 04 5C 49 77"
    "52 58 5F 10 11 3F 50 3F 3C 13 1A 56 27 56 5A 57 00 52 04 54 0B 3A 3D 18"
    "5E 76 7E 7B 0A 79 15 11 0C 0A 6C 3A 73 6A 6A 2F 51 52 25 36 43 75 62 2B"
    "75 08 1F 5F 1F 1F 26 63 0F 2F 2B 61 1D 32 50 00 23 7A 5C 5B 22 2B 02 6A"
    "46 5E 70 33 04 6B 0F 0D 09 22 6E 59 31 46 3C 68 48 53 07 46 0B 2C 60 78"
    "7D 66 5C 6B 0C 05 07 23 43 21 48 75 1A 3B 2E 41 3E 23 78 0D 5E 26 21 30"
    "2E 1A 60 09 01 00 00 00 01 00 00 00 2D 1E 1C 31 75 53 5D 1E 64 09 46 42"
    "0F 08 4E 44 76 30 24 40 54 1E 50 04 40 03 68 1D 58 6B 6A 1B 6C 66 30 0C"
    "0B 56 15 6B 3C 5E 37 31 08 4B 3B 2F 46 4B 2B 0C 0D 0F 2C 0D 36 0A 73 56"
    "17 14 4C 5F 61 1D 7B 30 10 63 49 78 23 1A 3D 6C 34 2F 7B 54 06 26 2B 44"
    "0E 2B 0F 1C 07 14 48 1B 4D 0F 18 58 3C 52 06 72 6F 3B 1F 02 39 62 69 56"
    "2C 7C 4F 1D 2B 46 29 6C 33 14 4E 3B 1E 04 67 0A 09 63 77 0D 4E 4B 00 46"
    "15 79 22 74 03 11 30 43 2B 68 42 0D 42 0B 62 58 48 25 35 65 19 73 2A 75"
    "38 3C 33 25 29 37 0C 73 18 43 6F 56 0C 38 75 08 07 3D 25 23 3A 62 67 77"
    "27 29 5B 28 54 6E 1E 71 60 29 65 69 26 46 2B 56 6C 45 50 65 0B 6C 4D 5E"
    "35 14 0F 4D 3C 17 71 58 79 6C 0A 06 2D 0C 3C 5F 7E 32 50 68 24 66 16 6C"
    "40 3D 7D 22 41 7E 35 62 12 7A 17 0E 5F 54 41 10 4E 0C 72 03 19 1C 2E 32"
    "4D 56 0A 7A 34 6E 2C 68 57 4E 4F 15 5D 6C 7B 71 37 2F 07 32 5E 37 3E 4A"
    "4C 2B 6A 6B 60 2D 6D 2D 32 54 4C 6D 75 65 57 13 22 71 1A 01 21 45 20 19"
    "16 3F 4E 3F 27 28 22 49 35 5C 77 43 3C 25 77 60 19 72 19 12 64 37 08 33"
    "43 23 77 48 00 4D 69 68 19 41 74 6C 79 38 5D 0D 0A 73 68 76 0E 35 4B 1B"
    "6F 79 05 64 57 0C 1C 4A 5C 29 42 47 09 0F 6B 5D 15 6F 42 56 54 41 0D 64"
    "7E 0B 35 27 7E 5E 0E 1A 14 3C 53 23 6C 08 69 49 45 2B 71 5E 46 26 44 25"
    "3D 60 64 3C 75 19 28 2C 14 76 76 47 3C 54 72 33 63 56 38 7E 2A 35 29 22"
    "03 4B 2A 72 66 03 4B 77 5C 1C 59 77 27 78 3E 74 76 61 20 4B 16 6D 40 38"
    "33 66 6F 31 0E 4A 0C 5B 36 1D 3D 1A 5E 62 7D 59 22 54 4B 02 21 7C 6F 53"
    "0C 5F 49 28 38 71 2C 55 75 11 78 34 4D 21 32 6C 41 21 4F 40 53 3B 50 67"
    "2C 78 30 31 38 5E 70 20 42 2C 43 6A 4E 7A 41 28 40 76 26 5D 03 00 00 00"
    "02 00 00 00 10 46 2B 68 10 69 7D 7D 63 46 0C 20 65 60 7C 1E 3A 52 5A 0F"
    "52 42 1A 40 2E 26 57 07 6F 4D 1C 16 66 7B 79 27 3A 40 5D 52 2E 6C 3D 09"
    "77 73 07 77 1C 44 00 30 0A 43 36 50 0A 6D 5D 2F 44 56 17 03 5A 38 0D 03"
    "2D 5A 58 28 39 17 2E 42 3B 0D 1F 74 0D 2F 7E 1A 01 0F 7E 5C 0C 47 50 5B"
    "22 64 71 65 0E 16 6E 11 6F 73 40 23 3A 0C 00 25 78 6B 16 4E 72 3C 25 2C"
    "50 01 54 00 6C 37 68 15 15 58 6C 68 08 18 16 78 04 3B 61 1C 7D 63 60 46"
    "64 7B 06 3F 65 39 2D 0C 67 5A 66 50 32 2C 7A 1F 36 76 32 64 4A 36 42 2F"
    "02 4B 15 47 58 5D 3C 72 27 18 62 5C 5D 69 39 4E 1C 66 79 03 57 29 30 39"
    "61 61 7B 79 56 1A 65 24 78 09 02 61 57 6B 4B 3C 05 52 10 78 59 2E 78 41"
    "2B 25 79 2C 4E 3D 3A 05 23 39 5E 51 51 34 54 31 60 2F 56 17 60 2D 36 4B"
    "6A 73 36 56 53 29 3C 0B 73 48 25 64 15 16 40 51 2B 0F 7C 51 11 02 0B 7B"
    "5D 46 31 70 0F 27 1E 3C 10 79 19 6F 36 27 2A 5C 0E 39 05 06 1F 64 43 16"
    "77 7B 54 01 54 29 2A 10 0B 4C 7E 7C 7D 65 33 40 01 55 31 08 22 0E 6B 08"
    "1D 6C 7B 54 5C 57 45 50 03 11 76 61 56 4A 14 72 20 44 03 7D 52 5A 2E 4B"
    "3B 1A 4C 52 2D 0F 72 23 0E 42 26 42 11 69 5F 0E 2B 63 57 6F 19 27 43 73"
    "14 75 5E 52 36 2F 65 08 35 76 6A 6D 74 60 3F 0A 00 32 47 10 46 40 1F 5C"
    "22 75 0D 1E 02 76 34 6A 1E 14 40 66 0C 46 33 54 7B 24 20 60 2B 36 3C 7B"
    "1F 04 16 14 0D 67 52 64 0C 41 28 7A 31 19 18 3E 40 1C 0B 5C 18 35 00 0A"
    "33 11 3C 79 73 45 11 08 30 56 0D 5F 5F 1B 18 69 2D 13 6F 44 31 77 0F 50"
    "19 12 30 3C 61 73 23 47 32 0A 6C 35 42 06 1C 18 04 2E 16 04 52 66 62 73"
    "4B 10 47 37 54 3C 31 35 4F 74 77 62 09 7D 5E 0B 02 21 29 71 01 00 56 58"
    "1E 59 4A 3B 5F 59 3A 65 10 0E 6B 3F 73 00 00 00 03 00 00 00 3D 20 54 44"
    "17 7D 6D 52 29 35 51 70 0D 20 3C 3E 55 63 2E 4B 54 7A 2C 05 12 79 37 2E"
    "0D 59 68 59 3F 61 4B 59 2D 25 6C 2F 70 57 7C 16 4A 63 69 1E 58 09 0A 5E"
    "07 54 11 7B 58 42 16 7C 0A 17 30 0D 63 47 44 7E 42 36 11 71 76 77 43 5F"
    "33 1C 3E 55 5E 53 5A 68 04 54 05 49 12 6D 37 5B 71 1E 17 4B 79 20 07 55"
    "54 76 1E 03 75 25 69 0E 58 79 68 69 1E 24 4B 13 1B 4E 26 5C 49 39 07 0B"
    "6D 26 16 5E 77 70 03 1E 6C 6F 55 44 6A 15 05 44 55 2A 0E 77 4E 6A 26 6F"
    "78 42 5E 10 05 68 0B 4B 4D 16 4B 25 4E 7E 0E 37 51 28 2F 73 33 77 02 02"
    "60 15 24 40 4B 49 04 75 09 4A 16 33 3A 28 25 75 4F 54 15 74 6C 5D 22 67"
    "33 0E 07 3C 5D 2E 38 2B 56 12 5C 3E 7D 5D 22 6D 75 56 6E 77 13 67 00 53"
    "02 3F 5D 2B 21 49 4D 38 01 5B 0C 3E 6F 1E 47 00 05 69 60 7E 4B 7E 01 08"
    "60 7E 7B 6B 3F 6D 6C 79 02 7C 5A 28 21 0F 1E 1E 27 22 3B 55 61 56 75 28"
    "70 53 22 00 44 1F 2B 67 39 25 05 50 2A 68 5B 5A 5A 78 75 61 76 3A 44 33"
    "7A 52 0B 4E 10 58 5E 20 55 39 72 5E 5D 15 47 56 53 28 34 04 36 35 46 58"
    "39 3F 2B 6C 0F 51 31 38 19 71 21 54 59 34 26 44 2A 7D 34 7C 6A 19 4C 6E"
    "13 6F 60 43 56 28 42 1F 47 7B 1A 24 30 58 69 2D 67 41 49 56 3B 43 76 3B"
    "53 7E 58 7C 1A 24 07 68 5D 02 3B 00 36 08 76 6D 58 58 01 37 16 62 53 31"
    "0C 1B 66 22 1F 3D 04 00 65 27 6D 35 3F 7B 3C 61 1D 72 1F 13 39 0C 3E 2D"
    "38 03 6C 61 68 6B 39 73 05 3E 29 74 18 65 5A 42 12 31 7E 75 14 2F 27 49"
    "0B 60 37 7C 10 0A 33 78 5A 0F 58 07 68 3C 4C 78 3E 53 45 45 5B 15 36 77"
    "19 02 03 52 4C 30 03 42 0D 4A 53 04 1F 28 60 6C 18 03 00 73 6D 1B 58 61"
    "40 59 68 01 2C 5C 1D 35 79 2F 1D 29 20 68 7B 30 59 6F 15 65 7A 47 5C 71"
    "5C 3F 19 0C 18 00 00 00"
)


def _crc24(data: bytes) -> int:
    return _crc24_func(data)


def rows_named(table, name):
    """按字段名精确取行（忽略解析器表示层级用的行首缩进）"""
    return [row for row in table if str(row[0]).strip() == name]


def _bplc_sof_fc(pb_count=4, cmt_index=4, std_version=1) -> bytes:
    """构造 BPLC SOF 帧 FC（表20 可变区域 + CRC-24 FCS 小端）

    byte0=0x09：SNID低4位=0 | 接入指示=1(bit3) | 定界符类型=1(SOF)
    byte7：物理块个数(bit0-3) + 载波映射表索引(bit4-7)
    byte12：标准版本号(bit4-7)=1(BPLC) + 扩展载波映射表索引(bit0-3)
    """
    fc = bytearray(16)
    fc[0] = 0x09
    fc[7] = ((cmt_index & 0x0F) << 4) | (pb_count & 0x0F)
    fc[12] = (std_version & 0x0F) << 4
    fc[13:16] = _crc24(bytes(fc[:13])).to_bytes(3, 'little')
    return bytes(fc)


def _pb(seq: int, pb_total: int, body: bytes = b'') -> bytes:
    """构造一个物理块：PB头4B(序号2B小端+聚合标志+保留) + PB体 + 保留1B + PBCS 3B

    PBCS = CRC-24(物理块头 + 物理块体 + 保留) 小端 3 字节（表49）
    """
    pb_hdr = seq.to_bytes(2, 'little') + bytes([0x00, 0x00])
    body_size = pb_total - 4 - 1 - 3
    pb_body = (body + b'\x00' * body_size)[:body_size]
    reserved = b'\x00'
    pbcs = _crc24(pb_hdr + pb_body + reserved).to_bytes(3, 'little')
    return pb_hdr + pb_body + reserved + pbcs


def _synthetic_frame(pb_count=4, pb_total=136, cmt_index=4) -> bytes:
    """合成多物理块 MPDU 帧：帧长 = FC(16) + pb_count × pb_total"""
    frame = _bplc_sof_fc(pb_count=pb_count, cmt_index=cmt_index)
    for i in range(pb_count):
        frame += _pb(i, pb_total)
    return frame


def _index_of(table, name):
    """返回字段名首次出现的行下标（不存在返回 -1）"""
    for idx, row in enumerate(table):
        if str(row[0]).strip() == name:
            return idx
    return -1


def _valid_mac_frame() -> bytes:
    """构造合法 MAC 帧：版本1 短头(12B) + MSDU短头(VLAN=0,类型=0x01) + 应用层 + CRC-32"""
    msdu = bytes([0x00, 0x01, 0x11, 0x01, 0x01, 0x00, 0x00, 0x00])
    mac_hdr = bytearray(12)
    mac_hdr[0] = 0x03  # 帧头类型=1(短头) | 版本=1(bit1)
    mac_hdr[2:4] = len(msdu).to_bytes(2, 'little')
    crc = _crc32_func(msdu).to_bytes(4, 'little')
    return bytes(mac_hdr) + msdu + crc


def test_real_4pb_520_slice_and_zero_pbcs():
    """T1: 真实 4-PB 帧按帧长一致性推断为 520 字节切片，PBCS 全零 → 置零告警"""
    frame = bytes.fromhex("".join(REAL_FRAME_HEX.split()))
    assert len(frame) == 2096, f"真实帧应为 2096 字节(16+4×520)，实际 {len(frame)}"

    table = CSGNewGenParser().parse_to_table(frame, parse_level="fc_pb")

    # 切片正确：4 个物理块头，序列号 0/1/2/3（按 136 切片时会读到 PB 体中的载荷）
    for i in range(4):
        assert rows_named(table, f"物理块头[{i}]"), f"缺少 物理块头[{i}] 行（切片错误）"
        seq = rows_named(table, f"序列号[{i}]")
        assert seq and seq[0][2] == str(i), f"物理块[{i}] 序列号错误: {seq[:1]}"

    # CMT 映射 136 与帧长不符 → 显式推断提示行（原始值=映射值，解析值=推断值）
    infer = rows_named(table, "PB大小推断")
    assert infer, "缺少「PB大小推断」提示行"
    assert infer[0][1] == "136", f"推断行原始值应为 CMT 映射值 136: {infer[0]}"
    assert infer[0][2] == "520", f"推断行解析值应为 520: {infer[0]}"
    assert "帧长" in infer[0][3], f"推断依据说明应含帧长等式: {infer[0]}"

    # 4 行 PBCS：存储值全零而计算值非零 → 置零/采集接口未提供（不判校验失败）
    for i in range(4):
        rows = rows_named(table, f"物理块检查序列[{i}]")
        assert rows, f"缺少 物理块检查序列[{i}] 行"
        row = rows[0]
        assert "置零" in row[2], f"PBCS[{i}] 解析值应标记置零: {row}"
        assert "未提供" in row[3], f"PBCS[{i}] 说明应为采集接口未提供: {row}"
        assert "校验失败(计算值=" not in row[3], f"PBCS[{i}] 置零不应判为校验失败: {row}"
        # 保留字节单独成行，便于核对 CRC-24 计算范围
        assert rows_named(table, f"保留[{i}](PB尾)"), f"缺少 保留[{i}](PB尾) 行"
    print("[OK] T1 真实4PB帧520切片+PBCS置零告警测试通过")


def test_synthetic_4pb_136_pbcs_pass():
    """T2: CMT 映射与帧长自洽（4×136）→ 无推断行，4 行 PBCS 校验通过"""
    frame = _synthetic_frame(pb_count=4, pb_total=136, cmt_index=4)
    assert len(frame) == 16 + 4 * 136, f"合成帧长度错误: {len(frame)}"

    table = CSGNewGenParser().parse_to_table(frame, parse_level="fc_pb")

    assert rows_named(table, "PB大小推断") == [], "帧长自洽时不应出现推断提示行"
    for i in range(4):
        rows = rows_named(table, f"物理块检查序列[{i}]")
        assert rows, f"缺少 物理块检查序列[{i}] 行"
        assert "校验通过" in rows[0][2], f"PBCS[{i}] 应校验通过: {rows[0]}"
        seq = rows_named(table, f"序列号[{i}]")
        assert seq and seq[0][2] == str(i), f"物理块[{i}] 序列号错误: {seq[:1]}"
    print("[OK] T2 合成4×136帧PBCS校验通过测试通过")


def test_synthetic_pbcs_mismatch():
    """T3: 篡改 PB[2] 的 PBCS 为非零错误值 → 校验失败(计算值=...)"""
    frame = bytearray(_synthetic_frame(pb_count=4, pb_total=136, cmt_index=4))
    pbcs_off = 16 + 2 * 136 + 136 - 3   # PB[2] 的 PBCS 起始偏移（保留1B 之后）
    frame[pbcs_off:pbcs_off + 3] = (0x123456).to_bytes(3, 'little')

    table = CSGNewGenParser().parse_to_table(bytes(frame), parse_level="fc_pb")

    rows = rows_named(table, "物理块检查序列[2]")
    assert rows, "缺少 物理块检查序列[2] 行"
    row = rows[0]
    assert row[2] == "0x123456", f"PBCS[2] 解析值应为存储值: {row}"
    assert "校验失败(计算值=" in row[3], f"PBCS[2] 说明应含校验失败与计算值: {row}"
    # 其余物理块不受影响
    for i in (0, 1, 3):
        others = rows_named(table, f"物理块检查序列[{i}]")
        assert others and "校验通过" in others[0][2], f"PBCS[{i}] 应仍校验通过: {others[:1]}"
    print("[OK] T3 PBCS校验失败测试通过")


def test_truncated_pbcs_missing():
    """T4: 截掉末 PB 尾部 4 字节（保留1+PBCS3）→ 不抛异常，显示 PBCS缺失(帧截断)"""
    frame = _synthetic_frame(pb_count=4, pb_total=136, cmt_index=4)[:-4]
    assert len(frame) == 16 + 4 * 136 - 4, f"截断帧长度错误: {len(frame)}"

    table = CSGNewGenParser().parse_to_table(frame, parse_level="fc_pb")

    rows = rows_named(table, "物理块检查序列[3]")
    assert rows, "截断帧末 PB 仍应有 物理块检查序列[3] 行"
    assert rows[0][2] == "PBCS缺失(帧截断)", f"末 PB 应显示 PBCS 缺失: {rows[0]}"
    assert "无法校验" in rows[0][3], f"末 PB 说明应解释无法校验: {rows[0]}"
    # 帧长等式无解 → 回退 CMT 映射值，不改判（R3）
    assert rows_named(table, "PB大小推断") == [], "截断帧等式无解时不应推断改判"
    # 前 3 个完整物理块仍正常校验
    for i in range(3):
        rows_i = rows_named(table, f"物理块检查序列[{i}]")
        assert rows_i and "校验通过" in rows_i[0][2], f"PBCS[{i}] 应校验通过: {rows_i[:1]}"
    print("[OK] T4 截断帧PBCS缺失测试通过")


def test_interleaved_order_and_noise_suppression():
    """T5: 逐块交错展示 PBH→块体→PBCS；噪声载荷抑制 MAC/MSDU 伪解析行"""
    frame = bytes.fromhex("".join(REAL_FRAME_HEX.split()))
    table = CSGNewGenParser().parse_to_table(frame, parse_level="fc_pb")

    # 交错顺序：物理块头[i] → 物理块体[i] → 物理块检查序列[i] → 物理块头[i+1]
    for i in range(4):
        i_head = _index_of(table, f"物理块头[{i}]")
        i_body = _index_of(table, f"物理块体[{i}]")
        i_pbcs = _index_of(table, f"物理块检查序列[{i}]")
        assert i_head >= 0 and i_body >= 0 and i_pbcs >= 0, \
            f"物理块[{i}] 缺少 PBH/块体/PBCS 行: {i_head},{i_body},{i_pbcs}"
        assert i_head < i_body < i_pbcs, \
            f"物理块[{i}] 行顺序应为 PBH→块体→PBCS: {i_head},{i_body},{i_pbcs}"
        if i < 3:
            i_next = _index_of(table, f"物理块头[{i + 1}]")
            assert i_pbcs < i_next, f"物理块[{i}] 的 PBCS 应在下一个 PBH 之前: {i_pbcs},{i_next}"

    # 噪声载荷：块体按原始报文展示，不再堆一行合并的「物理块体」
    assert rows_named(table, "物理块体") == [], "多PB帧不应再出现合并的「物理块体」行"
    for i in range(4):
        body = rows_named(table, f"物理块体[{i}]")
        assert body and "无法按MAC帧解析" in body[0][3], f"物理块体[{i}] 应标为原始报文展示: {body}"
        assert body[0][2] == "512字节", f"物理块体[{i}] 应为 512 字节: {body}"

    # 伪解析行抑制：无 MAC/MSDU 行，仅一条「MAC重组解析=无法解析」标记
    assert rows_named(table, "帧头类型") == [], "噪声载荷不应输出 MAC 帧头类型行"
    assert rows_named(table, "MSDU类型") == [], "噪声载荷不应输出 MSDU 类型行"
    marker = rows_named(table, "MAC重组解析")
    assert marker and marker[0][2] == "无法解析", f"应有 MAC重组解析=无法解析 标记行: {marker}"
    print("[OK] T5 交错展示+噪声抑制测试通过")


def test_valid_mac_body_still_parsed():
    """T6: 单PB 携带合法 MAC 帧 → 块体行之后仍有 MAC/MSDU 解析行（抑制不误伤）"""
    frame = _bplc_sof_fc(pb_count=1, cmt_index=4) + _pb(0, 136, body=_valid_mac_frame())
    table = CSGNewGenParser().parse_to_table(frame, parse_level="fc_pb")

    body = rows_named(table, "物理块体")
    assert body, "单PB 帧应有「物理块体」行"
    assert "承载MAC帧数据" in body[0][3], f"合法 MAC 帧体说明错误: {body}"
    i_body = _index_of(table, "物理块体")
    i_mac = _index_of(table, "帧头类型")
    i_msdu = _index_of(table, "MSDU类型")
    assert i_mac > i_body > 0, f"MAC 解析行应在块体行之后: {i_body},{i_mac}"
    assert i_msdu > i_mac, f"MSDU 类型行应在 MAC 行之后: {i_mac},{i_msdu}"
    assert rows_named(table, "MAC重组解析") == [], "合法 MAC 帧不应出现无法解析标记"
    print("[OK] T6 合法MAC帧体仍解析测试通过")


if __name__ == "__main__":
    test_real_4pb_520_slice_and_zero_pbcs()
    test_synthetic_4pb_136_pbcs_pass()
    test_synthetic_pbcs_mismatch()
    test_truncated_pbcs_missing()
    test_interleaved_order_and_noise_suppression()
    test_valid_mac_body_still_parsed()
    print("=" * 50)
    print("[OK] 全部测试通过")
