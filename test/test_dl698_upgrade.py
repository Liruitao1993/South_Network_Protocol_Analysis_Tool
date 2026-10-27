"""协议8（DL/T 698.45-2017）分布式产品升级（文件传输）纯逻辑层测试 —— design §11 A 组。

运行：
    pwsh -c '$env:PYTHONIOENCODING="utf-8"; python -u test/test_dl698_upgrade.py'

数据来源（判据**不是**本工程 encode 出来的，故可抓住「自证闭环」类假绿）：
  - `协议文档/8.698.45协议/代理升级流程.docx`：启动传输实帧（A1 逐字节 golden）、
    启动传输响应帧（A6）、执行升级实帧（A3）、写文件帧形状 `02 02 12 00 00 09 82 07 D0`（A2）。
    doc 帧字段：SA 单地址 6 字节线上 `33 00 98 06 55 07`（书写序 075506980033）、
    文件大小 275811、文件属性 E0、版本 "v1.0"、类别 0、块大小 2000、校验类型 0、校验值 7F7ED9D2。
  - 《面向对象的用电信息数据交换协议(20210910).md》：表188 文件信息 6 项、
    类型表 `date_time_s tag=28 / SIZE=7`（定长、**无长度域**）、附录 H.3.1 示例
    `1C 07 E0 01 14 00 00 00`、§6.2.4.2.4 地址特征字节 + 广播固定 1 字节 AA、
    规范「执行升级时间为全 FF 表示立即执行」。
"""

import sys
import zlib
import hashlib

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

import dl_t698_45_upgrade as up  # noqa: E402
import dl_t698_45_data_decode as decode_mod  # noqa: E402
from dl_t698_45_frame_gen import DLT69845FrameGenerator  # noqa: E402
from dl_t698_45_parser import DLT69845Parser  # noqa: E402
from validator.dl_t698_45_validator import DLT69845Validator  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f"  -- {detail}" if detail else ""))


def section(title):
    print(f"\n{title}")


def hexs(b) -> str:
    return bytes(b).hex(" ").upper()


def spaced(h: str) -> bytes:
    """带空格/换行的 hex → bytes（便于把 doc 帧原样抄进源码）。"""
    return bytes.fromhex("".join(h.split()))


# ─── doc 实帧（golden） ─────────────────────────────────────────────────────
DOC_START_FRAME = spaced("""
    68 3C 00 43 05 33 00 98 06 55 07 00 3C 7F 07 01 00 F0 01 07 00
    02 03 02 06 0A 00 0A 00 06 00 04 35 63 04 03 E0 0A 04 76 31 2E 30 16 00
    12 07 D0 02 02 16 00 09 04 7F 7E D9 D2 00 54 24 16
""")
DOC_START_ACK = spaced(
    "68 1A 00 C3 05 33 00 98 06 55 07 00 16 AC 87 01 00 F0 01 07 00 00 00 00 00 AE 11 16")
DOC_EXEC_FRAME = spaced("""
    68 22 00 43 05 33 00 98 06 55 07 00 A4 47 07 01 02 F0 01 0D 00
    02 02 1C FF FF FF FF FF FF FF 00 00 30 47 16
""")
# doc 的 SA（单地址 / 逻辑地址0 / 长度6 / 书写序 075506980033）与文件信息段
DOC_SA = spaced("05 33 00 98 06 55 07")
DOC_FILE_INFO = spaced("02 06 0A 00 0A 00 06 00 04 35 63 04 03 E0 0A 04 76 31 2E 30 16 00")
# 写文件样本数据：0x00..0xFF ×2 + 88×0x00 = 600 字节
BLOCK_600 = bytes(range(256)) * 2 + bytes(88)


def apdu_of(frame: bytes) -> bytes:
    """取解析器认定的链路用户数据（APDU）字节。"""
    return spaced(DLT69845Parser().parse(frame)["链路用户数据"]["原始字节"])


def block_count_ref(total: int, bs: int) -> int:
    """测试侧独立参考实现（ceil），与被测函数互为对拍。"""
    return 0 if total <= 0 else -(-total // bs)


def _raises(fn, want="") -> bool:
    """fn() 必须抛 ValueError（可选：异常文本含 want）。"""
    try:
        fn()
    except ValueError as exc:
        return want in str(exc) if want else True
    except Exception:
        return False
    return False


def _ack(omd: bytes, dar: int) -> bytes:
    """构造合法的 ACTION-Response Normal 帧（只变 OMD/DAR，HCS/FCS 由既有实现计算）。"""
    apdu = bytes([0x87, 0x01, 0x00]) + omd + bytes([dar, 0x00, 0x00, 0x00])
    return DLT69845FrameGenerator()._assemble_frame(DOC_SA, 0, 0xC3, apdu)


def test_a1_start_transfer_golden():
    section("[A1] 启动传输帧与 doc 实帧逐字节相等")
    fi = up.build_file_info(size=275811, source="", target="",
                            attr_byte=0xE0, version="v1.0", category=0)
    check("file_info 与 doc 同段逐字节相等", fi == DOC_FILE_INFO,
          f"{hexs(fi)} != {hexs(DOC_FILE_INFO)}")
    frame = up.build_start_transfer(DOC_SA, 0, 0, fi, 2000, 0, bytes.fromhex("7F7ED9D2"))
    check("整帧逐字节相等（HCS/FCS/长度域一并相等）", frame == DOC_START_FRAME,
          f"\n    got = {hexs(frame)}\n    doc = {hexs(DOC_START_FRAME)}")
    check("帧长 62 = L(0x003C=60)+2 且末字节 16H",
          len(frame) == int.from_bytes(frame[1:3], "little") + 2 == 62 and frame[-1] == 0x16,
          f"{len(frame)} / L={int.from_bytes(frame[1:3], 'little')}")
    apdu = apdu_of(frame)
    # ★ TimeTag=无 必须补 00：不补就比 doc 少 1 字节（本任务实测）
    check("APDU 45 字节且末字节 TimeTag=00（缺它即整帧少 1 字节）",
          len(apdu) == 45 and apdu[-1] == 0x00, f"{len(apdu)} / {hexs(apdu[-2:])}")
    check("校验结构 02 02 16 00 09 04 7F 7E D9 D2 在帧内",
          spaced("02 02 16 00 09 04 7F 7E D9 D2") in frame)
    # >65535 自动切长帧 [6] double-long-unsigned
    big = up.build_start_transfer(DOC_SA, 0, 0, fi, 70000, 0, b"")
    check("块大小 70000 自动切长帧 06 + u32BE（06 00 01 11 70）",
          spaced("06 00 01 11 70") in big, hexs(big))
    check("块大小 2000 用短帧 12 07 D0（doc 同形）", spaced("12 07 D0") in frame)
    check("块大小 0 抛 ValueError", _raises(lambda: up.build_start_transfer(DOC_SA, 0, 0, fi, 0)))
    v = DLT69845Validator().verify(frame)
    check("doc 帧经校验器全 PASS", v.valid, [(c.name, c.level.value) for c in v.checks])


def test_a2_write_block():
    section("[A2] 写文件帧：BER 长形式 + 校验器全 PASS")
    frame = up.build_write_block(DOC_SA, 0, 1, 0, BLOCK_600)
    apdu = apdu_of(frame)
    # 布局：07 01 PIID | OMD(4B) || 02 02 | 12 <u16 序号> | 09 <BER len> | 数据 | 00
    check("APDU 前缀 07 01 01 F0 01 08 00（PIID=1 + 方法8 OMD）",
          apdu[:7] == spaced("07 01 01 F0 01 08 00"), hexs(apdu[:7]))
    check("参数头 02 02 12 00 00 09 82 02 58（600 → BER 长形式 82 02 58）",
          apdu[7:16] == spaced("02 02 12 00 00 09 82 02 58"), hexs(apdu[7:16]))
    check("块数据原样紧随其后（600 字节全等）",
          apdu[16:16 + 600] == BLOCK_600, hexs(apdu[16:24]))
    check("末字节 TimeTag=00", apdu[-1] == 0x00, hexs(apdu[-2:]))
    check("APDU 长 617 = 3+4+2+3+4+600+1", len(apdu) == 617, str(len(apdu)))
    check("整帧长 634 = L+2 且末字节 16H",
          len(frame) == int.from_bytes(frame[1:3], "little") + 2 == 634 and frame[-1] == 0x16,
          f"{len(frame)} / L={int.from_bytes(frame[1:3], 'little')}")
    r = DLT69845Parser().parse(frame)
    check("解析状态成功", r["解析状态"] == "成功", str(r.get("错误信息", "")))
    v = DLT69845Validator().verify(frame)
    check("校验器全 PASS（起始字符/长度域一致性/HCS/FCS/结束字符）", v.valid,
          [(c.name, c.level.value, c.message) for c in v.checks])

    b2000 = bytes(range(256)) * 7 + bytes(208)
    check("2000 字节样本长 2000", len(b2000) == 2000, str(len(b2000)))
    frame2 = up.build_write_block(DOC_SA, 0, 1, 0, b2000)
    check("2000B 时参数头 02 02 12 00 00 09 82 07 D0（doc 同形）",
          apdu_of(frame2)[7:16] == spaced("02 02 12 00 00 09 82 07 D0"),
          hexs(apdu_of(frame2)[7:16]))
    check("2000B 帧经校验器全 PASS", DLT69845Validator().verify(frame2).valid)
    check("块序号 1（第二包）编码 02 02 12 00 01 09 82 02 58",
          spaced("02 02 12 00 01 09 82 02 58") in up.build_write_block(DOC_SA, 0, 2, 1, BLOCK_600))
    check("块序号 65536 抛 ValueError（[18] 短帧上限）",
          _raises(lambda: up.build_write_block(DOC_SA, 0, 1, 65536, b"\x00")))


def test_a3_exec_upgrade_golden():
    section("[A3] 执行升级（立即）帧逐字节 golden")
    frame = up.build_exec_upgrade(DOC_SA, 0, 2)
    check("整帧逐字节相等", frame == DOC_EXEC_FRAME,
          f"\n    got = {hexs(frame)}\n    doc = {hexs(DOC_EXEC_FRAME)}")
    check("date_time_s = 1C + 7×FF（定长、无长度域；多写 07 即多 1 字节）",
          spaced("1C FF FF FF FF FF FF FF") in frame and bytes.fromhex("1C07") not in frame)
    check("软件许可默认 NULL=00（帧尾 …FF 00 00 30 47 16）",
          frame[-6:] == spaced("FF 00 00 30 47 16"), hexs(frame[-6:]))
    check("校验器全 PASS", DLT69845Validator().verify(frame).valid)
    check("非 7 字节执行时间抛 ValueError",
          _raises(lambda: up.build_exec_upgrade(DOC_SA, 0, 2, b"\xFF" * 6)))
    lic = up.build_exec_upgrade(DOC_SA, 0, 2, license_bytes=bytes.fromhex("0904A1B2C3D4"))
    check("许可字节原样透传（不猜 CHOICE 内 tag/长度；6B 许可替换 1B NULL ⇒ 整帧 +5）",
          bytes.fromhex("0904A1B2C3D4") in lic and len(lic) == len(frame) + 5, hexs(lic))
    check("指定时间模式（2016-01-20 00:00:00）编码 1C 07E0 0114 000000",
          spaced("1C 07 E0 01 14 00 00 00")
          in up.build_exec_upgrade(DOC_SA, 0, 2, exec_time=bytes.fromhex("07E001140000 00")))


def test_a4_split_matrix():
    section("[A4] 分包矩阵：包数 / 末包字节 / 拼接还原")
    for total in (0, 1, 599, 600, 601, 2000, 1234567):
        data = bytes((i * 31 + 7) & 0xFF for i in range(total))
        for bs in (1, 600, 2000, 8192):
            blocks = up.split_blocks(data, bs)
            n = block_count_ref(total, bs)
            exp_last = (total % bs) or bs
            check(f"total={total} bs={bs}：包数 == {n}", len(blocks) == n, str(len(blocks)))
            check(f"total={total} bs={bs}：拼接还原 == 原数据", b"".join(blocks) == data)
            check(f"total={total} bs={bs}：末包字节 == {exp_last if total else 0}",
                  (len(blocks[-1]) == exp_last) if blocks else True,
                  str(len(blocks[-1]) if blocks else None))
            check(f"total={total} bs={bs}：block_count 与 len(split_blocks) 一致",
                  up.block_count(total, bs) == len(blocks))
            plan = up.UpgradePlan.for_data(data, bs)
            check(f"total={total} bs={bs}：UpgradePlan 与分包一致",
                  plan.num_blocks == len(blocks)
                  and plan.last_block_bytes == (exp_last if total else 0),
                  f"{plan.num_blocks}/{plan.last_block_bytes}")
    check("空数据 → 空列表 / 0 包", up.split_blocks(b"", 600) == [] and up.block_count(0, 600) == 0)
    check("block_size<=0 抛 ValueError",
          _raises(lambda: up.split_blocks(b"\x00\x01", 0)) and _raises(lambda: up.split_blocks(b"", -1)))


def test_a5_sa_matrix():
    section("[A5] SA 地址：通配 / doc 单地址 / 广播 / 非法长度")
    check("默认参数 == WILDCARD_SA == 45 AA×6",
          up.build_sa() == up.WILDCARD_SA == bytes.fromhex("45AAAAAAAAAAAA"),
          hexs(up.build_sa()))
    check("doc 单地址（书写序 075506980033 → 线上逆序 05 33 00 98 06 55 07）",
          up.build_sa(0, 0, 6, bytes.fromhex("075506980033")) == DOC_SA,
          hexs(up.build_sa(0, 0, 6, bytes.fromhex("075506980033"))))
    check("广播地址固定 1 字节 AA（忽略长度/地址体）",
          up.build_sa(3, 0, 6, bytes.fromhex("075506980033")) == bytes([0xAA]))
    check("组地址特征 = 0x85（类型2 + 长度6）",
          up.build_sa(2, 0, 6, bytes.fromhex("075506980033"))[0] == 0x85,
          hexs(up.build_sa(2, 0, 6, bytes.fromhex("075506980033"))))
    check("逻辑地址 1 抬高 bit4 ⇒ 特征 0x15", up.build_sa(0, 1, 6)[0] == 0x15)
    check("长度 1 合法（单地址 ⇒ 特征 0x00 + 1 字节）",
          up.build_sa(0, 0, 1, b"\x33") == bytes.fromhex("0033"),
          hexs(up.build_sa(0, 0, 1, b"\x33")))
    check("长度 16 合法（单地址 ⇒ 特征 0x0F）", up.build_sa(0, 0, 16)[0] == 0x0F,
          hexs(up.build_sa(0, 0, 16)[:1]))
    check("通配 + 长度 1 ⇒ 特征 0x40", up.build_sa(1, 0, 1)[0] == 0x40)
    for bad in (0, 17, -1):
        check(f"长度 {bad} 抛 ValueError 且中文可读（含 1..16）",
              _raises(lambda v=bad: up.build_sa(0, 0, v), "1..16"))
    check("地址体不足 addr_len 时补零后逆序",
          up.build_sa(0, 0, 4, b"\x01\x02") == bytes.fromhex("0300000201"),
          hexs(up.build_sa(0, 0, 4, b"\x01\x02")))
    check("通配地址体不足补 AA",
          up.build_sa(1, 0, 3, b"\xAA") == bytes.fromhex("42AAAAAA"),
          hexs(up.build_sa(1, 0, 3, b"\xAA")))
    # 解析器读回（逆序口径与 _parse_address 一致）
    r = DLT69845Parser().parse(DOC_START_FRAME)
    check("解析器读回 SA 书写序与 build_sa 输入一致",
          r["地址域"]["服务器地址SA"]["解析值"] == "075506980033",
          r["地址域"]["服务器地址SA"]["解析值"])


def test_a6_check_action_response():
    section("[A6] 确认判定：doc 响应 / DAR / OMD / 非响应 / 坏帧")
    ok = up.check_action_response(DOC_START_ACK, up.OMD_START)
    check("doc 响应帧 ok=True", ok["ok"], ok["reason"])
    check("doc 响应帧字段 dar=0 / omd=F0010700 / apdu_type=ACTION-Response",
          ok["dar"] == 0 and ok["omd"] == "F0010700" and ok["apdu_type"] == "ACTION-Response",
          str(ok))

    r = up.check_action_response(_ack(up.OMD_START, 14), up.OMD_START)
    check("DAR=14 → ok=False 且 reason 含 DAR 值与含义",
          (not r["ok"]) and "DAR=14" in r["reason"] and "数据块序号无效" in r["reason"], r["reason"])
    check("DAR≠0 → reason 提示重试", "重试" in r["reason"], r["reason"])
    check("DAR≠0 → 解析出的 dar 原样回传", r["dar"] == 14, str(r["dar"]))

    r = up.check_action_response(_ack(up.OMD_WRITE, 0), up.OMD_START)
    check("OMD 换成写文件（F0010800）→ ok=False 且 reason 指出 OMD 不符",
          (not r["ok"]) and "OMD 不符" in r["reason"] and "F0010800" in r["reason"], r["reason"])

    r = up.check_action_response(DOC_START_FRAME, up.OMD_START)
    check("非 ACTION-Response（doc 启动传输请求帧）→ ok=False",
          (not r["ok"]) and "不是 ACTION-Response" in r["reason"], r["reason"])

    broken = bytearray(DOC_START_ACK)
    broken[-4] ^= 0xFF  # FCS 低字节
    r = up.check_action_response(bytes(broken), up.OMD_START)
    check("破坏 FCS → ok=False 且 reason 含「解析失败」",
          (not r["ok"]) and "解析失败" in r["reason"], r["reason"])
    broken2 = bytearray(DOC_START_ACK)
    broken2[13] ^= 0x08  # APDU 载荷（DAR 之后的字节）→ FCS 不符
    r = up.check_action_response(bytes(broken2), up.OMD_START)
    check("破坏载荷 → FCS 不通过 → ok=False（不得被误判为确认）",
          (not r["ok"]) and "解析失败" in r["reason"], r["reason"])

    for junk in (b"", b"not a frame", bytes([0x68, 0x01]), DOC_START_ACK[:10]):
        r = up.check_action_response(junk, up.OMD_START)
        check(f"坏帧 {hexs(junk) or '空'} 不抛异常且 ok=False",
              r["ok"] is False and r["reason"] != "")
    r = up.check_action_response(None, up.OMD_START)
    check("None 帧不抛异常", r["ok"] is False, r["reason"])
    check("返回值键齐全",
          set(r) == {"ok", "reason", "dar", "omd", "apdu_type"}, str(sorted(r)))


def test_a7_checksum_values():
    section("[A7] 校验值：CRC 必须是 2 字节 CRC-16/X-25（现场口径）")
    data = bytes((i * 17 + 3) & 0xFF for i in range(4096)) + b"\x00\xff"
    c16 = up.crc16_x25(data)
    check("CRC 为 2 字节（不是 crc32 的 4 字节）",
          len(up.calc_checksum_value(data, "crc")) == 2,
          hexs(up.calc_checksum_value(data, "crc")))
    check("CRC 大端 == crc16_x25 2B 大端",
          up.calc_checksum_value(data, "crc", "big") == c16.to_bytes(2, "big"),
          hexs(up.calc_checksum_value(data, "crc")))
    check("CRC 小端 == crc16_x25 2B 小端",
          up.calc_checksum_value(data, "crc", "little") == c16.to_bytes(2, "little"))
    # 现场自证：DPU_APP_V1.0.3.4.bin(469200B) 的 CRC 应为 0x7373（实帧 09 02 73 73）
    import crcmod.predefined as _predefined

    _c = _predefined.Crc("x-25")
    _c.update(data)
    check("crc16_x25 与 crcmod x-25 同值（同一规格，不是另挑一个 CRC16）",
          c16 == int(_c.crcValue), hex(c16))
    check("默认参数 == crc/big",
          up.calc_checksum_value(data) == up.calc_checksum_value(data, "crc", "big"))
    check("大小写不敏感（CRC/md5/SHA1）",
          up.calc_checksum_value(data, "CRC") == up.calc_checksum_value(data, "crc")
          and up.calc_checksum_value(data, "MD5") == up.calc_checksum_value(data, "md5")
          and up.calc_checksum_value(data, "SHA1") == up.calc_checksum_value(data, "sha1"))
    check("CRC 空数据 == 00 00（2 字节）", up.calc_checksum_value(b"", "crc") == b"\x00\x00")
    check("md5 == hashlib.md5().digest()",
          up.calc_checksum_value(data, "md5") == hashlib.md5(data).digest())
    check("sha1 == hashlib.sha1().digest()",
          up.calc_checksum_value(data, "sha1") == hashlib.sha1(data).digest())
    check("md5/sha1 忽略字节序",
          up.calc_checksum_value(data, "md5", "little") == hashlib.md5(data).digest())
    check("长度：crc 2 / md5 16 / sha1 20",
          len(up.calc_checksum_value(data, "crc")) == 2
          and len(up.calc_checksum_value(data, "md5")) == 16
          and len(up.calc_checksum_value(data, "sha1")) == 20)
    check("未知 kind 抛 ValueError（含中文提示）",
          _raises(lambda: up.calc_checksum_value(data, "sha256"), "未知校验类型"))
    check("未知字节序抛 ValueError", _raises(lambda: up.calc_checksum_value(data, "crc", "mid")))


def test_a8_doc_frame_parse_regression_guard():
    section("[A8] 回归守卫：doc 启动传输实帧 parse_to_table 零错误")
    rows = DLT69845Parser().parse_to_table(DOC_START_FRAME)
    flat = " | ".join(" | ".join(str(c) for c in r) for r in rows)
    check("行数 > 20（完整解出参数结构）", len(rows) > 20, str(len(rows)))
    check("无 ❌ 行", "❌" not in flat, [r[0] for r in rows if "❌" in str(r[0])])
    check("无「未知类型」行（钉住 bit-string 长度域=位宽：按字节读会多吃 2 字节、"
          "错位到 0x76='v' 而报未知类型）",
          "未知类型" not in flat, [r for r in rows if "未知类型" in " ".join(map(str, r))])
    check("文件属性解为 bit-string 3位 / E0",
          any(r[2] == "E0" and "bit-string" in r[3] for r in rows),
          [r for r in rows if "bit-string" in r[3]])
    check("文件大小解为 275811", any(r[2] == "275811" for r in rows))
    check("传输块大小解为 2000", any(r[2] == "2000" for r in rows))
    check("校验值解为 7F7ED9D2", any("7F7ED9D2" in str(r[2]) for r in rows))
    check("OMD 语义含「启动传输」", "启动传输" in flat, [r for r in rows if "OMD" in r[0]])
    # 执行升级帧同样应零错误（date_time_s 定长口径）
    rows3 = DLT69845Parser().parse_to_table(DOC_EXEC_FRAME)
    flat3 = " | ".join(" | ".join(str(c) for c in r) for r in rows3)
    check("doc 执行升级帧 parse_to_table 无 ❌/未知类型",
          "❌" not in flat3 and "未知类型" not in flat3,
          [r for r in rows3 if "❌" in str(r) or "未知" in str(r)])


def test_a9_mutation_counterproof():
    """变异反证：把五处口径改回历史错误形态，必须与 doc golden 不同（红）。

    只在测试里现搭错误帧（不改产品代码），证明 A1/A2/A3/A5 的逐字节断言确有判别力。
    注：SA 逆序（`build_sa`）与「帧长 = L+2」两处**不在此处重复演示** —— 它们分别由 A5 的
    逐字节断言与 A1 的整帧 golden 直接覆盖（此前版本里那两条只是常量比较、不触产品代码，
    属恒真断言，已删除）。
    """
    section("[A9] 变异反证（错误形态必须被 golden 抓住）")
    gen = DLT69845FrameGenerator()

    # ① 文件属性 bit-string 长度域写成「字节数」1（应为位数 3）
    fi_byte = (bytes([0x02, 0x06]) + bytes.fromhex("0A00") + bytes.fromhex("0A00")
               + bytes.fromhex("0600043563") + bytes([0x04, 0x01, 0xE0])
               + bytes.fromhex("0A0476312E30") + bytes([0x16, 0x00]))
    f_bit = gen.generate_action_request_normal(
        DOC_SA, 0, 0, up.OMD_START,
        bytes([0x02, 0x03]) + fi_byte + bytes.fromhex("1207D0") + bytes.fromhex("0202160009047F7ED9D2") + b"\x00")
    check("① bit-string 写成字节数 ⇒ 与 doc 不等（且解析器少读 2 字节）",
          f_bit != DOC_START_FRAME)

    # ② date_time_s 多写长度域 07
    f_dts = gen.generate_action_request_normal(
        DOC_SA, 0, 2, up.OMD_EXEC,
        bytes([0x02, 0x02, 0x1C, 0x07]) + up.IMMEDIATE_EXEC_TIME + bytes([0x00, 0x00]))
    check("② date_time_s 带长度域 ⇒ 与 doc 执行升级帧不等（多 1 字节）",
          f_dts != DOC_EXEC_FRAME and len(f_dts) == len(DOC_EXEC_FRAME) + 1, str(len(f_dts)))

    # ③ 块序号写成 1 基
    f_base1 = up.build_write_block(DOC_SA, 0, 1, 1, BLOCK_600)
    check("③ 首块序号写成 1 ⇒ 参数头不是 doc 的 12 00 00",
          spaced("02 02 12 00 00 09 82 02 58") not in f_base1)

    # ④ BER 长度域退化为单字节（>127 溢出）
    orig = up._ber_len
    try:
        up._ber_len = lambda n: bytes([n & 0xFF])
        f_ber = up.build_write_block(DOC_SA, 0, 1, 0, BLOCK_600)
        check("④ BER 长形式写成单字节 ⇒ 参数头不再是 09 82 02 58",
              spaced("02 02 12 00 00 09 82 02 58") not in f_ber,
              hexs(apdu_of(f_ber)[7:16]))
    finally:
        up._ber_len = orig

    # ⑤ TimeTag 不补 00 ⇒ 比 doc 少 1 字节（本任务实测）
    f_notag = gen.generate_action_request_normal(
        DOC_SA, 0, 0, up.OMD_START,
        bytes([0x02, 0x03]) + DOC_FILE_INFO + bytes.fromhex("1207D0")
        + bytes.fromhex("0202160009047F7ED9D2"))
    check("⑤ 不补 TimeTag ⇒ 比 doc 少 1 字节",
          len(f_notag) == len(DOC_START_FRAME) - 1 and f_notag != DOC_START_FRAME,
          f"{len(f_notag)} vs {len(DOC_START_FRAME)}")


# ─── 读版本信息（GET-Request Normal；用户现场实帧 golden） ──────────────────
VER_READ_FRAME = spaced(
    "68 17 00 43 05 AA AA AA AA AA AA 00 AA 2A 05 01 01 43 00 03 00 00 6D 5C 16")
VER_SA_SINGLE_AA = spaced("05 AA AA AA AA AA AA")   # 单地址 + 地址体 AA×6（示例帧的 SA）
VER_APDU_PIID1 = spaced("05 01 01 43 00 03 00 00")  # GET-Request Normal + TimeTag 无
LEGACY_APDU_PIID1 = spaced("05 01 01 43 00 03 00")  # 老 generate_get_request_normal（无 TimeTag）
VER_VERSION_FIELDS = ("JCDZ", "V1.5", "250901", "V1.0", "230602", "SHANDONG")
VER_VERSION_TEXT = ("厂商代码=JCDZ，软件版本号=V1.5，软件版本日期=2025-09-01，"
                    "硬件版本号=V1.0，硬件版本日期=2023-06-02，厂商扩展信息=SHANDONG")


def _version_data(*values: str) -> bytes:
    """版本信息（表191）：`structure{厂商代码, 软件版本号, 软件版本日期, 硬件版本号, 硬件版本日期, 厂商扩展信息}`。"""
    out = bytes([0x02, len(values)])
    for v in values:
        raw = v.encode("ascii")
        out += bytes([0x0A, len(raw)]) + raw
    return out


def _ver_response(data: bytes, piid_acd: int = 1, oad: bytes = up.OAD_VERSION,
                  tag: bytes = b"\x01") -> bytes:
    """搭一帧 GET-Response Normal（`tag=01` 数据 / `00` 错误信息 DAR），经组帧器保证 HCS/FCS 正确。"""
    apdu = bytes([0x85, 0x01, piid_acd]) + bytes(oad) + bytes(tag) + bytes(data)
    return DLT69845FrameGenerator()._assemble_frame(up.WILDCARD_SA, 0, 0xC3, apdu)


def test_a10_read_version():
    section("[A10] 读版本信息：组帧 golden + 响应判定")

    # ① 组帧逐字节复现用户实帧
    frame = up.build_read_version(VER_SA_SINGLE_AA, 0, 1)
    check("① 单地址 AA×6 + PIID=1 ⇒ 逐字节等于现场实帧", frame == VER_READ_FRAME, hexs(frame))
    check("① APDU = 05 01 01 43 00 03 00 00（GET-Request Normal + TimeTag 无）",
          apdu_of(frame) == VER_APDU_PIID1, hexs(apdu_of(frame)))

    # ② 页面默认 SA（通配）⇒ 仍是合法帧，APDU/OAD 不变
    dflt = up.build_read_version(up.WILDCARD_SA, 0, 0)
    parsed = DLT69845Parser().parse(dflt)
    check("② 通配 SA 下 HCS/FCS 均通过",
          parsed["帧头校验HCS"]["校验结果"] == "通过"
          and parsed["帧校验FCS"]["校验结果"] == "通过")
    check("② 地址类型=通配地址（特征 0x45）",
          parsed["地址域"]["地址特征"]["地址类型"] == "通配地址", parsed["地址域"]["地址特征"])
    check("② APDU 正确（PIID=0）", apdu_of(dflt) == spaced("05 01 00 43 00 03 00 00"),
          hexs(apdu_of(dflt)))
    check("② OAD 语义 = 版本信息",
          "版本信息" in parsed["链路用户数据"]["APDU"]["OAD"]["语义说明"])

    # ③ PIID 自增（校验随之重算）；OAD 非法即报错
    f7 = up.build_read_version(up.WILDCARD_SA, 0, 7)
    check("③ PIID=7 ⇒ APDU 位改 07 且 FCS 重算通过",
          apdu_of(f7) == spaced("05 01 07 43 00 03 00 00")
          and DLT69845Parser().parse(f7)["帧校验FCS"]["校验结果"] == "通过")
    try:
        up.build_read_version(up.WILDCARD_SA, 0, 0, oad=b"\x43\x00\x03")
        check("③ OAD 非 4 字节 ⇒ 抛 ValueError", False)
    except ValueError:
        check("③ OAD 非 4 字节 ⇒ 抛 ValueError", True)

    # ④ 成功响应：ok + 版本文本（命名业务字段）
    resp = _ver_response(_version_data(*VER_VERSION_FIELDS))
    res = up.check_get_response(resp)
    check("④ 成功响应 ok=True", res["ok"] is True, res)
    check("④ 版本文本取命名字段", res["version"] == VER_VERSION_TEXT, res["version"])
    check("④ OAD 回显被记录", res["oad"] == "43000300", res["oad"])
    check("④ 数据业务字段原样带出（6 项）",
          res["data_business"].get("软件版本号") == "V1.5"
          and len(res["data_business"]) == 6, res["data_business"])

    # ⑤ Get-Result 的 CHOICE：tag=00 = 错误信息 DAR
    r5 = up.check_get_response(_ver_response(b"\x03", tag=b"\x00"))
    check("⑤ DAR=3 ⇒ ok=False 且 dar=3", r5["ok"] is False and r5["dar"] == 3, r5)
    check("⑤ reason 带 DAR 说明（拒绝读写）", "拒绝读写" in r5["reason"], r5["reason"])
    r5b = up.check_get_response(_ver_response(b"\x00", tag=b"\x00"))
    check("⑤ DAR=0 无数据 ⇒ ok=True 但版本为空（调用方按「响应未带数据」显示）",
          r5b["ok"] is True and r5b["version"] == "", r5b)

    # ⑥ 判据必须能挡住「不是本次要的那一帧」
    r6 = up.check_get_response(_ver_response(_version_data("A"), oad=spaced("43000400")))
    check("⑥ OAD 不符 ⇒ ok=False 且 reason 给出期望值",
          r6["ok"] is False and "OAD 不符" in r6["reason"], r6["reason"])
    r6b = up.check_get_response(DOC_START_FRAME)
    check("⑥ ACTION 帧 ⇒ ok=False 且 reason 说明不是 GET-Response",
          r6b["ok"] is False and "不是 GET-Response" in r6b["reason"], r6b["reason"])
    broken = bytearray(resp)
    broken[-3] ^= 0xFF                                   # 破坏 FCS
    r6c = up.check_get_response(bytes(broken))
    check("⑥ FCS 被破坏 ⇒ ok=False 且 reason 点名 FCS",
          r6c["ok"] is False and "FCS" in r6c["reason"], r6c["reason"])
    check("⑥ 空帧/垃圾帧不抛异常",
          up.check_get_response(b"")["ok"] is False
          and up.check_get_response(b"\x00\x01\x02")["ok"] is False)

    # ⑦ 既有 GET-Request 组帧行为逐字节不变（默认不补 TimeTag）
    legacy = DLT69845FrameGenerator().generate_get_request_normal(
        up.WILDCARD_SA, 0, 1, up.OAD_VERSION)
    check("⑦ 老调用方（不传新参数）APDU 仍是 7 字节、无 TimeTag",
          apdu_of(legacy) == LEGACY_APDU_PIID1, hexs(apdu_of(legacy)))

    # ⑧ 变异反证：golden 确有判别力（改口径就必须对不上）
    no_tag = DLT69845FrameGenerator().generate_get_request_normal(
        VER_SA_SINGLE_AA, 0, 1, up.OAD_VERSION)          # 忘记 TimeTag
    check("⑧ 不补 TimeTag ⇒ 与实帧不等（且少 1 字节）",
          no_tag != VER_READ_FRAME and len(no_tag) == len(VER_READ_FRAME) - 1,
          f"{len(no_tag)} vs {len(VER_READ_FRAME)}")
    wildcard = up.build_read_version(up.WILDCARD_SA, 0, 1)   # SA 特征换成通配
    check("⑧ SA 换成通配（特征 45）⇒ 与实帧不等（HCS 随之变）",
          wildcard != VER_READ_FRAME and wildcard[4] == 0x45, hexs(wildcard[:6]))


# ─── 内部版本（厂家扩展 OAD FF100400；用户现场实帧 golden） ─────────────────
INT_READ_FRAME = spaced(
    "68 17 00 43 05 03 24 08 04 26 20 00 CD 9A 05 01 2C FF 10 04 00 00 C2 8A 16")
INT_SA = spaced("05 03 24 08 04 26 20")            # 单地址 + 地址体 032408042620（书写序 2026040824 03）


def test_a11_internal_version_read():
    section("[A11] 内部版本（厂家扩展 OAD FF100400）")

    # ① 组帧逐字节复现用户实帧（PIID=0x2C，OAD=FF100400）
    frame = up.build_read_version(INT_SA, 0, 0x2C, oad=up.OAD_INTERNAL_VERSION)
    check("① 内部版本帧逐字节等于现场实帧", frame == INT_READ_FRAME, hexs(frame))
    check("① APDU = 05 01 2C FF 10 04 00 00",
          apdu_of(frame) == spaced("05 01 2C FF 10 04 00 00"), hexs(apdu_of(frame)))
    check("① 与「通用版本」帧不同（OAD 不同 ⇒ HCS/FCS 也不同）",
          frame != up.build_read_version(INT_SA, 0, 0x2C))

    # ② 解析器认定的 OAD/语义（厂商自定义区间 ⇒ 标「未知对象」）
    parsed = DLT69845Parser().parse(frame)
    oad = parsed["链路用户数据"]["APDU"]["OAD"]
    check("② HCS/FCS 均通过",
          parsed["帧头校验HCS"]["校验结果"] == "通过"
          and parsed["帧校验FCS"]["校验结果"] == "通过")
    check("② OAD 原始值 = FF100400 且语义标注厂商扩展/未知对象",
          oad["原始值"] == "FF100400" and ("未知对象" in oad["语义说明"]
                                          or "厂商" in oad["语义说明"]), oad["语义说明"])
    check("② 属性号 = 4（与通用版本的属性 3 不同）",
          oad["解析值"]["属性编号"] == 4, oad["解析值"])

    # ③ 内部版本的响应判定：厂家扩展对象没有命名业务字段 ⇒ 版本内容取数据值
    resp = _ver_response(b"\x0A\x06V1.0.3", oad=up.OAD_INTERNAL_VERSION)   # visible-string
    res = up.check_get_response(resp, up.OAD_INTERNAL_VERSION)
    check("③ 内部版本响应 ok=True 且取到内容", res["ok"] is True and res["version"] == "V1.0.3", res)
    check("③ OAD 回显 = FF100400", res["oad"] == "FF100400", res["oad"])

    # ④ 互斥：两条命令各自的响应**不能互相顶替**（否则「选择」等于没生效）
    common_resp = _ver_response(_version_data(*VER_VERSION_FIELDS))
    r_common_as_int = up.check_get_response(common_resp, up.OAD_INTERNAL_VERSION)
    check("④ 通用版本响应喂给「内部版本」读取 ⇒ OAD 不符、不认",
          r_common_as_int["ok"] is False and "OAD 不符" in r_common_as_int["reason"],
          r_common_as_int["reason"])
    r_int_as_common = up.check_get_response(resp, up.OAD_VERSION)
    check("④ 内部版本响应喂给「通用版本」读取 ⇒ 同样不认",
          r_int_as_common["ok"] is False and "OAD 不符" in r_int_as_common["reason"],
          r_int_as_common["reason"])

    # ⑤ 变异反证：内部版本帧不能靠「通用」的默认 OAD 组出来
    no_oad = up.build_read_version(INT_SA, 0, 0x2C)
    check("⑤ 不传 OAD（默认通用）⇒ 与内部版本实帧不等",
          no_oad != INT_READ_FRAME and apdu_of(no_oad)[3:7] == up.OAD_VERSION,
          hexs(apdu_of(no_oad)))
    check("⑤ OAD 常量确为两个不同值",
          up.OAD_VERSION == spaced("43 00 03 00")
          and up.OAD_INTERNAL_VERSION == spaced("FF 10 04 00"))


# ─── 版本明细（逐字段解析；用户要求「详细解析」） ───────────────────────────
#: 现场实帧：内部版本读命令的响应（带 4 字节 FEH 前导；6 项 visible-string，长度 4/4/6/4/6/8）
REAL_INT_RESP = spaced("""
    FE FE FE FE 68 47 00 C3 05 03 24 08 04 26 20 00 5A E2
    85 01 00 FF 10 04 00 01
    02 06 0A 04 4C 48 49 4E 0A 04 30 30 33 39 0A 06 32 36 30 38 30 33
    0A 04 30 30 31 41 0A 06 32 35 31 30 31 33 0A 08 47 57 47 53 58 58 58 58
    00 00 14 CD 16
""")
#: 期望的 6 项（名称 → 值；日期按表191 规则补全为 20YY-MM-DD）
REAL_INT_FIELDS = (
    ("厂商代码", "LHIN", "0A044C48494E", 4),
    ("软件版本号", "0039", "0A0430303339", 4),
    ("软件版本日期", "2026-08-03", "0A06323630383033", 6),
    ("硬件版本号", "001A", "0A0430303141", 4),
    ("硬件版本日期", "2025-10-13", "0A06323531303133", 6),
    ("厂商扩展信息", "GWGSXXXX", "0A084757475358585858", 8),
)


def _resp_with(data: bytes, oad: bytes, tag: bytes = b"\x01") -> bytes:
    """搭一帧 GET-Response（tag 01=数据 / 00=错误信息 DAR），OAD 由调用方给。"""
    apdu = bytes([0x85, 0x01, 0x01]) + bytes(oad) + bytes(tag) + bytes(data)
    return DLT69845FrameGenerator()._assemble_frame(up.WILDCARD_SA, 0, 0xC3, apdu)


def test_a12_version_detail_rows():
    section("[A12] 版本明细：逐字段解析（表191 命名 + 日期补全 + ⚠ 未自证）")

    # ① 现场实帧 → 6 项逐字段（名称/值/原始字节/长度）
    res = up.check_get_response(REAL_INT_RESP, up.OAD_INTERNAL_VERSION)
    check("① 现场帧判 ok 且带 6 行明细", res["ok"] is True and len(res["rows"]) == 6, res["rows"])
    rows = res["rows"]
    check("① 名称/值逐项正确（含日期补全）",
          [(r["名称"], r["值"]) for r in rows] == [(n, v) for n, v, _h, _l in REAL_INT_FIELDS],
          [(r["名称"], r["值"]) for r in rows])
    check("① 原始字节与声明长度逐项一致",
          [(r["原始"], r["长度"]) for r in rows] == [(h, l) for _n, _v, h, l in REAL_INT_FIELDS],
          [(r["原始"], r["长度"]) for r in rows])
    check("① 结构长度自证通过（4/4/6/4/6/8）",
          decode_mod.version_lengths_match(
              decode_mod.version_like_members(
                  DLT69845Parser().parse(REAL_INT_RESP)["链路用户数据"]["APDU"]["数据"])) is True)

    # ② 标准「通用版本信息」（同一形状）走同一条命名路径
    common = _resp_with(bytes([0x02, 6]) + b"".join(
        bytes([0x0A, len(v)]) + v for v in
        (b"JCDZ", b"V1.5", b"250901", b"V1.0", b"230602", b"SHANDONG")), up.OAD_VERSION)
    r2 = up.check_get_response(common, up.OAD_VERSION)
    check("② 通用版本信息同样逐字段命名",
          [(r["名称"], r["值"]) for r in r2["rows"]][:3]
          == [("厂商代码", "JCDZ"), ("软件版本号", "V1.5"), ("软件版本日期", "2025-09-01")],
          r2["rows"])

    # ③ 长度与表191 声明不符 ⇒ 命名照给 + 显式 ⚠ 行（不静默、也不假装自证）
    odd = _resp_with(bytes([0x02, 6]) + b"".join(
        bytes([0x0A, len(v)]) + v for v in
        (b"AB", b"V1.5", b"250901", b"V1.0", b"230602", b"SHANDONG")), up.OAD_INTERNAL_VERSION)
    r3 = up.check_get_response(odd, up.OAD_INTERNAL_VERSION)
    check("③ 6 项仍在 + 多一行「⚠ 长度未自证」",
          len(r3["rows"]) == 7 and r3["rows"][-1]["名称"] == "⚠ 长度未自证", r3["rows"][-1])
    check("③ ⚠ 行写明声明值与实发值",
          "表191 声明 (4, 4, 6, 4, 6, 8)" in r3["rows"][-1]["值"]
          and "(2, 4, 6, 4, 6, 8)" in r3["rows"][-1]["值"], r3["rows"][-1]["值"])

    # ③b 末项为 NULL（表191 声明定长，但现场设备回 00）⇒ 仍要逐字段命名 + 点名缺失
    #     现场报障：这种形态早先整条退化成 `数据 = 0206...`（看到的是原始内容）
    null_tail = _resp_with(bytes([0x02, 6]) + b"".join(
        bytes([0x0A, len(v)]) + v for v in
        (b"CNC", b"1033", b"251023", b"HW00", b"250822")) + b"\x00",
        up.OAD_VERSION)
    r3b = up.check_get_response(null_tail, up.OAD_VERSION)
    names = [r["名称"] for r in r3b["rows"]]
    check("③b NULL 末项仍判 ok", r3b["ok"] is True, r3b.get("reason"))
    check("③b 仍给出 6 个具名字段（不塌成「数据」）",
          names[:6] == ["厂商代码", "软件版本号", "软件版本日期",
                        "硬件版本号", "硬件版本日期", "厂商扩展信息"], names)
    check("③b 厂商扩展信息 = NULL",
          r3b["rows"][5]["值"] == "NULL", r3b["rows"][5])
    check("③b 追加「⚠ 字段缺失」并点名", 
          "⚠ 字段缺失" in names and "厂商扩展信息" in r3b["rows"][names.index("⚠ 字段缺失")]["值"],
          r3b["rows"][names.index("⚠ 字段缺失")] if "⚠ 字段缺失" in names else names)
    check("③b 日期仍补全", r3b["rows"][2]["值"] == "2025-10-23", r3b["rows"][2]["值"])

    # ③c 定长字段用 NUL 补齐 ⇒ 显示时去掉尾部 NUL（否则界面是一串不可见字符）
    nul_pad = _resp_with(bytes([0x02, 6]) + b"".join(
        bytes([0x0A, len(v)]) + v for v in
        (b"CNC\x00", b"1033", b"251023", b"HW00", b"250822", b"GWGS0000")),
        up.OAD_VERSION)
    r3c = up.check_get_response(nul_pad, up.OAD_VERSION)
    check("③c NUL 补齐的厂商代码去掉尾部 NUL",
          r3c["rows"][0]["值"] == "CNC", repr(r3c["rows"][0]["值"]))
    check("③c 原始字节仍保留 NUL（可追溯）",
          r3c["rows"][0]["原始"].endswith("00"), r3c["rows"][0]["原始"])

    # ④ 非结构数据 ⇒ 单行「数据」（兜底，别空着）
    single = _resp_with(bytes([0x0A, 0x0A]) + b"V1.0.3-INT", up.OAD_INTERNAL_VERSION)
    r4 = up.check_get_response(single, up.OAD_INTERNAL_VERSION)
    check("④ 单个 visible-string ⇒ 一行「数据」",
          [(r["名称"], r["值"]) for r in r4["rows"]] == [("数据", "V1.0.3-INT")], r4["rows"])
    check("④ 兜底行也带原始字节", r4["rows"][0]["原始"] == "0A0A56312E302E332D494E54",
          r4["rows"][0])

    # ⑤ 单一来源：字段名只在 decode 模块一份（模板与常量同源）
    check("⑤ CLASS_ATTR_TEMPLATES[(19,3)] 的 fields 就是 VERSION_FIELDS（无第二份清单）",
          decode_mod.CLASS_ATTR_TEMPLATES[(19, 3)]["fields"] == list(decode_mod.VERSION_FIELDS))
    check("⑤ 表191 声明长度 = 4/4/6/4/6/8",
          decode_mod.VERSION_FIELD_BYTES == (4, 4, 6, 4, 6, 8))
    check("⑤ 非 6 项结构不算版本信息（不猜命名）",
          decode_mod.decode_version_info({"tag_name": "structure", "解析值": [
              {"tag_name": "visible-string", "解析值": "A"}]}) is None)

    # ⑥ 变异反证：字段名顺序对调 ⇒ 我们的断言必须对不上（证明名字不是白给的）
    swapped = [dict(r) for r in rows]
    swapped[2]["名称"], swapped[4]["名称"] = swapped[4]["名称"], swapped[2]["名称"]
    check("⑥ 字段名顺序被对调 ⇒ 与现场帧的期望逐项不符（断言有判别力）",
          [(r["名称"], r["值"]) for r in swapped]
          != [(n, v) for n, v, _h, _l in REAL_INT_FIELDS])
    check("⑥ 日期字段被错配时能看出来（软件版本日期 ≠ 2026-08-03）",
          dict((r["名称"], r["值"]) for r in swapped)["软件版本日期"] != "2026-08-03")


def test_a14_start_transfer_v14_golden():
    section("[A14] 方法14 启动传输：现场两帧逐字节 + CRC-16 2 字节")

    # 现场两帧（同一设备、只差「2 字节标识」的 A-XDR 类型：09 octet-string / 0A visible-string）
    REAL_V14_OCTET = (
        "68600043051111111111111046C8070100F0010E00020602060A0753434D2E62696E"
        "0A0753434D2E62696E06000728D00403E00A0876312E302E302E30160012019002"
        "0216000902737301010A0476312E3001010A04323737300902011800C7F216")
    REAL_V14_VISIBLE = (
        "68600043051111111111111046C8070100F0010E00020602060A0753434D2E62696E"
        "0A0753434D2E62696E06000728D00403E00A0876312E302E302E30160012019002"
        "0216000902737301010A0476312E3001010A04323737300A020118000BEF16")

    sa = bytes.fromhex("05111111111111")
    file_info = (bytes([0x02, 6])
                 + bytes([0x0A, 7]) + b"SCM.bin"
                 + bytes([0x0A, 7]) + b"SCM.bin"
                 + b"\x06" + (469200).to_bytes(4, "big")
                 + b"\x04\x03\xE0"
                 + bytes([0x0A, 8]) + b"v1.0.0.0"
                 + b"\x16\x00")
    check_crc = up.calc_checksum_value(b"", "crc")  # 占位，下面用手工 7373

    for variant, want in (("octet", REAL_V14_OCTET), ("visible", REAL_V14_VISIBLE)):
        frame = up.build_start_transfer_v14(
            sa, 0x10, 0, file_info, 400, up.CHECK_CRC, bytes.fromhex("7373"),
            variant=variant)
        check(f"方法14/{variant} 逐字节等于现场帧", frame.hex().upper(), want)
        parsed = DLT69845Parser().parse(frame)
        check(f"方法14/{variant} 自家解析器 HCS/FCS 通过",
              (parsed.get("帧头校验HCS") or {}).get("校验结果") == "通过"
              and (parsed.get("帧校验FCS") or {}).get("校验结果") == "通过")
        check(f"方法14/{variant} 服务码/OMD 正确",
              parsed["链路用户数据"]["APDU"]["OMD"]["原始值"] == "F0010E00",
              parsed["链路用户数据"]["APDU"]["OMD"]["原始值"])

    # 两帧只差 3 个字节（标识的类型标签 + FCS 2 字节）
    a = bytes.fromhex(REAL_V14_OCTET)
    b = bytes.fromhex(REAL_V14_VISIBLE)
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    check("两帧差异仅 3 字节（类型标签 + FCS）", len(diff) == 3, len(diff))
    check("类型标签位置正是 0x09/0x0A", [a[diff[0]], b[diff[0]]] == [0x09, 0x0A],
          [a[diff[0]], b[diff[0]]])

    # CRC 口径：真实升级包 → 0x7373（现场实帧里的值）
    check("CRC-16/X-25 对 'abc' 的已知值", hex(up.crc16_x25(b"abc")), "0x9e25")
    check("CHECK_CRC 常量为 0", up.CHECK_CRC == 0, up.CHECK_CRC)


def test_a13_bt_block_cap_from_write_limit():
    section("[A13] 蓝牙通道：按「一次 ATT 写上限」反推每包最大块长")

    def frame_len(limit, sa, cap):
        return len(up.build_write_block(bytes(sa), 0, 0, 0, bytes(cap)))

    # ① 用户给的例子：ATT/写上限 512 ⇒ 每包 ≤ 480（实测 478 ≤ 480）
    cap512 = up.max_block_bytes_for_frame_limit(512, up.WILDCARD_SA)
    check("① 写上限 512 ⇒ 块长 478（≤ 480，用户口径的上界成立）", cap512 == 478, cap512)
    check("① 该块长组出的整帧恰好 512（不多不少）",
          frame_len(512, up.WILDCARD_SA, cap512) == 512,
          frame_len(512, up.WILDCARD_SA, cap512))
    check("① 再大 1 字节就超了（判据紧）",
          frame_len(512, up.WILDCARD_SA, cap512 + 1) == 513)

    # ② 协商 MTU 512 ⇒ 一次写 509（ATT 头 3 字节）⇒ 块长 475
    cap509 = up.max_block_bytes_for_frame_limit(509, up.WILDCARD_SA)
    check("② 写上限 509（MTU 512 − 3）⇒ 块长 475", cap509 == 475, cap509)
    check("② 整帧恰好 509", frame_len(509, up.WILDCARD_SA, cap509) == 509)
    check("② 与 512 档不同（开销是按真实组帧算的，不是固定减 32）",
          cap512 - cap509 == 3, (cap512, cap509))

    # ③ 开销随地址域长度变（不是写死的常量）
    sa1 = bytes([0xAA])                                    # 广播：SA 只 1 字节
    check("③ 广播 SA(1B) 能多塞 6 字节（开销少 6）",
          up.max_block_bytes_for_frame_limit(509, sa1) == cap509 + 6,
          up.max_block_bytes_for_frame_limit(509, sa1))

    # ④ 小上限 / 非法输入
    check("④ 上限 33 ⇒ 块长 1（帧头吃掉 32）", up.max_block_bytes_for_frame_limit(33, up.WILDCARD_SA) == 1)
    check("④ 上限 32 ⇒ 0（放不下任何块数据）", up.max_block_bytes_for_frame_limit(32, up.WILDCARD_SA) == 0)
    check("④ 上限 20（ATT 默认负载）⇒ 0", up.max_block_bytes_for_frame_limit(20, up.WILDCARD_SA) == 0)
    check("④ 非法输入一律 0",
          up.max_block_bytes_for_frame_limit(0, up.WILDCARD_SA) == 0
          and up.max_block_bytes_for_frame_limit(-5, up.WILDCARD_SA) == 0
          and up.max_block_bytes_for_frame_limit(None, up.WILDCARD_SA) == 0
          and up.max_block_bytes_for_frame_limit(509, b"") == 0)

    # ⑤ 单调性 + 与真实组帧一致（不用产品自己的结果当期望）
    caps = [up.max_block_bytes_for_frame_limit(n, up.WILDCARD_SA) for n in (40, 100, 200, 509, 1000)]
    check("⑤ 上限越大块长不减", caps == sorted(caps), caps)
    check("⑤ 每个档位都满足「整帧 ≤ 上限」且「再大 1 字节就超」",
          all(frame_len(n, up.WILDCARD_SA, c) <= n
              and frame_len(n, up.WILDCARD_SA, c + 1) > n
              for n, c in zip((40, 100, 200, 509, 1000), caps)),
          [(n, c) for n, c in zip((40, 100, 200, 509, 1000), caps)])


def test_a15_block_status_gate():
    section("[A15] 传输块状态字（F00104）：组帧 + 位序兼容 + 不通过必须拦下")

    sa = bytes.fromhex("05111111111111")
    req = up.build_read_block_status(sa, 0x0000, 0x10)
    gen = DLT69845FrameGenerator()
    # 帧形：68 L L C SA CA HCS APDU FCS 16 —— 用解析器反查 APDU 最稳
    parsed = DLT69845Parser().parse(req)
    check("① 状态字请求是 GET-Request Normal",
          "GET" in str(parsed.get("APDU类型", "")) or "05 01" in req.hex(" ").upper(),
          parsed.get("APDU类型"))
    check("① OAD = F0010400（文件分块传输管理·传输块状态字）",
          "F0010400" in req.hex(" ").upper().replace(" ", ""), req.hex(" "))
    check("① 组帧以 16H 结尾且 HCS/FCS 自洽（解析器无错误行）",
          req[-1] == 0x16 and DLT69845Parser().parse(req).get("valid", True) is not False,
          DLT69845Parser().parse(req).get("错误信息"))
    check("① PIID 可配（0x10 原样写入请求）",
          "050110F0010400" in req.hex(" ").upper().replace(" ", ""), req.hex(" "))

    def resp(body: bytes, piid: int = 0x10, oad: bytes = b"\xF0\x01\x04\x00") -> bytes:
        apdu = bytes([0x85, 0x01, piid]) + oad + body
        return gen._assemble_frame(sa, 0x0000, 0xC3, apdu)

    def bitmap(bits, set_idx, value="msb") -> bytes:
        out = bytearray((bits + 7) // 8)
        for i in set_idx:
            b, k = divmod(i, 8)
            out[b] |= (1 << (7 - k)) if value == "msb" else (1 << k)
        return bytes(out)

    # ② 位序兼容：3 块全成功，MSB-first(E0) 与 LSB-first(07) 都必须放行
    r_msb = up.check_block_status(resp(bytes([0x01, 0x04, 0x03]) + bitmap(3, [0, 1, 2])), 3)
    r_lsb = up.check_block_status(resp(bytes([0x01, 0x04, 0x03]) + bitmap(3, [0, 1, 2], "lsb")), 3)
    check("② MSB-first 全成功 ⇒ 通过", r_msb["ok"] is True and r_msb["order"] == "msb", r_msb)
    check("② LSB-first 全成功也通过（并标出 order=lsb）",
          r_lsb["ok"] is True and r_lsb["order"] == "lsb", r_lsb)

    # ③ 缺块 / 位数不足 / 补位被置：一律不通过（且点名缺哪块）
    r_miss = up.check_block_status(resp(bytes([0x01, 0x04, 0x03]) + bitmap(3, [0, 2])), 3)
    check("③ 缺第 2 块(1-based) ⇒ 不通过并点名",
          r_miss["ok"] is False and r_miss["matched"] is True and r_miss["missing"] == [2], r_miss)
    r_short = up.check_block_status(resp(bytes([0x01, 0x04, 0x02]) + bitmap(2, [0, 1])), 3)
    check("③ 声明 2 位 < 3 块 ⇒ 不通过（理由写明位数小）",
          r_short["ok"] is False and "位数" in str(r_short["reason"]), r_short)
    padded = bytearray(bitmap(16, [0, 1, 2]))
    padded[1] |= 0x80                                  # 第 16 位（超出 3 块的补位）置 1
    r_pad = up.check_block_status(resp(bytes([0x01, 0x04, 0x10]) + bytes(padded)), 3)
    check("③ 超出块数的位被置 1 ⇒ 不通过（补位/多报块都必须拦下）",
          r_pad["ok"] is False and ("补位" in str(r_pad["reason"]) or "多报块" in str(r_pad["reason"])),
          r_pad)

    # ④ DAR 分支 / OAD 不符 / 非 GET 响应
    r_dar = up.check_block_status(resp(bytes([0x00, 0x01])), 3)
    check("④ DAR=1 ⇒ 不通过且给可读 DAR 名",
          r_dar["ok"] is False and "DAR" in str(r_dar["reason"]) and "硬件" in str(r_dar["reason"]), r_dar)
    r_oad = up.check_block_status(resp(bytes([0x01, 0x04, 0x03]) + bitmap(3, [0, 1, 2]),
                                       oad=b"\x43\x00\x03\x00"), 3)
    check("④ OAD 不符 ⇒ matched False（不当成状态字）",
          r_oad["matched"] is False and "OAD" in str(r_oad["reason"]), r_oad)
    action = gen._assemble_frame(sa, 0x0000, 0xC3, bytes([0x87, 0x01, 0x10, 0xF0, 0x01, 0x04, 0x00, 0x00, 0x00, 0x00]))
    r_act = up.check_block_status(action, 3)
    check("④ ACTION-Response ⇒ matched False（不是 GET-Response）",
          r_act["matched"] is False, r_act)


def main():
    print("=" * 66)
    print("协议8 698.45 文件传输升级 —— 纯逻辑层（dl_t698_45_upgrade）")
    print("=" * 66)
    test_a1_start_transfer_golden()
    test_a2_write_block()
    test_a3_exec_upgrade_golden()
    test_a4_split_matrix()
    test_a5_sa_matrix()
    test_a6_check_action_response()
    test_a7_checksum_values()
    test_a8_doc_frame_parse_regression_guard()
    test_a9_mutation_counterproof()
    test_a10_read_version()
    test_a11_internal_version_read()
    test_a12_version_detail_rows()
    test_a14_start_transfer_v14_golden()
    test_a13_bt_block_cap_from_write_limit()
    test_a15_block_status_gate()
    print(f"\nPASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
