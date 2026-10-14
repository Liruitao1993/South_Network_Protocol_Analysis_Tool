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
    section("[A7] 校验值与 zlib/hashlib 对拍")
    data = bytes((i * 17 + 3) & 0xFF for i in range(4096)) + b"\x00\xff"
    crc = zlib.crc32(data) & 0xFFFFFFFF
    check("crc 大端 == crc32 4B 大端",
          up.calc_checksum_value(data, "crc", "big") == crc.to_bytes(4, "big"),
          hexs(up.calc_checksum_value(data, "crc")))
    check("crc 小端 == crc32 4B 小端",
          up.calc_checksum_value(data, "crc", "little") == crc.to_bytes(4, "little"))
    check("默认参数 == crc/big",
          up.calc_checksum_value(data) == up.calc_checksum_value(data, "crc", "big"))
    check("大小写不敏感（CRC/md5/SHA1）",
          up.calc_checksum_value(data, "CRC") == up.calc_checksum_value(data, "crc")
          and up.calc_checksum_value(data, "MD5") == up.calc_checksum_value(data, "md5")
          and up.calc_checksum_value(data, "SHA1") == up.calc_checksum_value(data, "sha1"))
    check("CRC 空数据 == 00 00 00 00", up.calc_checksum_value(b"", "crc") == b"\x00\x00\x00\x00")
    check("md5 == hashlib.md5().digest()",
          up.calc_checksum_value(data, "md5") == hashlib.md5(data).digest())
    check("sha1 == hashlib.sha1().digest()",
          up.calc_checksum_value(data, "sha1") == hashlib.sha1(data).digest())
    check("md5/sha1 忽略字节序",
          up.calc_checksum_value(data, "md5", "little") == hashlib.md5(data).digest())
    check("长度：crc 4 / md5 16 / sha1 20",
          len(up.calc_checksum_value(data, "crc")) == 4
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
    print(f"\nPASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
