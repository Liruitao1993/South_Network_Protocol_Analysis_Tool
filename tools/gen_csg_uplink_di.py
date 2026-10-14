# -*- coding: utf-8 -*-
"""从协议14（Q/CSG 11109004-2013）条文解释 PDF 抽取**数据标识（DI）索引表**与错误码表。

依据 AGENTS.md 陷阱「位表必须以 pdfplumber 按单元格重取为准」：附录 A/B/D/E 的 DI 索引表
采用 pdfplumber ``extract_tables`` 逐单元格抽取，避免 markitdown 串行/并表。

各附录表列式不同，逐附录映射：
- 附 A/B：``DI3 DI2 DI1 DI0 | 数据格式 | 字节数 | 单位 | 读 | 写 | 数据标识名称``（DI 在第 0~3 列）
- 附 D/E：``序号 | DI3 DI2 DI1 DI0 | 事件名称 | 字节数 | 说明``（DI 在第 1~4 列）
- 附 F  ：``ERR | 说明``

输出 ``csg_uplink_di_data.py``（纯数据模块）。

⚠ 本脚本只负责 **2013 版附 A/B/D/E/F**。**网管（深化应用）扩展**（文档
``新一代计量自动化主站通信网络管理技术要求`` 第 4 章，16 条 DI + 结构化解码）在
``csg_uplink_nm.py`` 内手工维护，由 ``csg_uplink_di.py`` 在导入时合并 —— 重跑本脚本
**不会**丢失扩展条目，反之亦然。

用法::

    python tools/gen_csg_uplink_di.py
"""

from __future__ import annotations

import os
import re
import sys

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(
    ROOT, "协议文档", "14.南网上行通信规约",
    "中国南方电网有限责任公司计量自动化终端上行通信规约(条文解释).pdf",
)
OUT = os.path.join(ROOT, "csg_uplink_di_data.py")

#: (物理页起, 物理页止闭, 附录字母, 附录名, DI 起始列, 名称列)
SECTIONS = [
    (50, 68, "A", "终端参数", 0, 9),
    (69, 72, "B", "测量点参数", 0, 9),
    (112, 119, "D", "告警数据", 1, 5),
    (120, 120, "E", "事件记录", 1, 5),
]
ERR_PAGES = (123, 124)
_SEC = re.compile(r"^([A-J])\.(\d+(?:\.\d+)*)\s+(.*)$")
_CAP = re.compile(r"表\s*([A-J])\.(\d+(?:\.\d+)*)")
_HEX2 = re.compile(r"^[0-9A-Fa-f]{2}$")


def _norm(row):
    """压掉 None/空串单元格，返回去空白后的字符串列表。"""
    out = []
    for c in row:
        if c is None:
            continue
        s = str(c).replace("\n", " ").strip()
        out.append(s)
    return out


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _is_hex2(s):
    return bool(_HEX2.match(s or ""))


def _page_captions(page):
    """返回该页 (top, "X.n 标题") 列表（按 y 升序）。"""
    caps = []
    for w in page.extract_words():
        m = _CAP.match(w["text"]) or _CAP.match(w["text"] + " ")
        if m:
            caps.append((w["top"], f"{m.group(1)}.{m.group(2)}"))
    return sorted(caps)


def main():
    entries, seen = [], set()
    errs, err_seen = [], set()
    with pdfplumber.open(PDF) as pdf:
        for lo, hi, appx, appname, di_col, name_col in SECTIONS:
            for p in range(lo, min(hi, len(pdf.pages) - 1) + 1):
                page = pdf.pages[p]
                caps = _page_captions(page)
                try:
                    tables = page.find_tables()
                except Exception:
                    tables = []
                raw = page.extract_tables() or []
                for ti, table in enumerate(raw):
                    group = f"{appx}"
                    if ti < len(tables):
                        top = tables[ti].bbox[1]
                        cand = [c for c in caps if c[0] <= top + 2]
                        if cand:
                            group = cand[-1][1]
                    for row in table:
                        cells = _norm(row)
                        need = di_col + 4
                        if len(cells) < need:
                            continue
                        quartet = cells[di_col:need]
                        if not all(_is_hex2(x) for x in quartet):
                            continue
                        di = "".join(quartet).upper()
                        if di in seen:
                            continue
                        seen.add(di)
                        nm = _clean(cells[name_col]) if name_col < len(cells) else ""
                        if di_col == 0:
                            fmt = _clean(cells[4]) if len(cells) > 4 else ""
                            nb = _clean(cells[5]) if len(cells) > 5 else ""
                            unit = _clean(cells[6]) if len(cells) > 6 else ""
                            rd = "*" in (cells[7] if len(cells) > 7 else "")
                            wr = "*" in (cells[8] if len(cells) > 8 else "")
                        else:
                            fmt, unit, rd, wr = "", "", True, True
                            nb = _clean(cells[6]) if len(cells) > 6 else ""
                        entries.append({
                            "di": di, "name": nm, "fmt": fmt, "nbytes": nb,
                            "unit": unit, "read": rd, "write": wr,
                            "group": group, "appx": appx,
                        })
        for p in ERR_PAGES:
            if p >= len(pdf.pages):
                continue
            for table in pdf.pages[p].extract_tables() or []:
                for row in table:
                    cells = _norm(row)
                    if len(cells) < 2:
                        continue
                    m = re.match(r"^([0-9A-Fa-f]{2})H$", cells[0])
                    if not m:
                        continue
                    code = m.group(1).upper()
                    if code in err_seen:
                        continue
                    err_seen.add(code)
                    errs.append({"code": code, "name": _clean(cells[1])})

    entries.sort(key=lambda e: e["di"])
    errs.sort(key=lambda e: e["code"])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write('"""本文件由 tools/gen_csg_uplink_di.py 自动生成，请勿手工编辑。"""\n\n')
        f.write("#: 附 A/B/D/E 数据标识索引（DI 4 字节 → 名称/格式/字节数/单位/读写/归属表）\n")
        f.write("DI_ENTRIES = [\n")
        for e in entries:
            f.write(
                "    {\"di\": %r, \"name\": %r, \"fmt\": %r, \"nbytes\": %r, "
                "\"unit\": %r, \"read\": %r, \"write\": %r, \"group\": %r, \"appx\": %r},\n"
                % (e["di"], e["name"], e["fmt"], e["nbytes"], e["unit"],
                   e["read"], e["write"], e["group"], e["appx"])
            )
        f.write("]\n\n")
        f.write("#: 附 F 出错否定代码 ERR（F.1）\n")
        f.write("ERR_CODES = [\n")
        for e in errs:
            f.write("    {\"code\": %r, \"name\": %r},\n" % (e["code"], e["name"]))
        f.write("]\n")
    print(f"written {OUT}: {len(entries)} DI, {len(errs)} ERR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
