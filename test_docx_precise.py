# -*- coding: utf-8 -*-
"""精确解析 docx 表格，含合并单元格信息"""
import zipfile, re, sys
sys.stdout.reconfigure(encoding="utf-8")

z = zipfile.ZipFile("南网新一代20260226校对/宽带双模通信模块（通感一体物联版）相关测试命令定义_增加相关接口.docx")
xml = z.read("word/document.xml").decode("utf-8")

tables = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.DOTALL)

def cell_text(tc):
    return "".join(re.findall(r"<w:t>(.*?)</w:t>", tc, re.DOTALL)).strip()

# 表格7（索引7）是 OFDMA多用户下发
for ti, tbl in enumerate(tables):
    rows = re.findall(r"<w:tr.*?</w:tr>", tbl, re.DOTALL)
    first = " | ".join(cell_text(tc) for tc in re.findall(r"<w:tc>.*?</w:tc>", rows[0], re.DOTALL)) if rows else ""
    if "字节号" in first or "域" in first:
        print(f"\n===== 表格{ti} =====")
        for ri, r in enumerate(rows):
            # 每行：提取单元格文本 + vMerge状态
            tcs = re.findall(r"<w:tc>.*?</w:tc>", r, re.DOTALL)
            cells = []
            for tc in tcs:
                t = cell_text(tc)
                # vMerge: <w:vMerge/> 续, <w:vMerge w:val="restart"/> 起始
                vm = re.search(r'<w:vMerge[^>]*/>', tc)
                vmval = vm.group(0) if vm else ""
                # gridSpan
                gs = re.search(r'<w:gridSpan w:val="(\d+)"', tc)
                gsval = gs.group(1) if gs else "1"
                cells.append(f"{t}[vm:{'restart' if 'restart' in vmval else ('cont' if vmval else 'none')},gs:{gsval}]")
            print(f"  R{ri}: {' | '.join(cells)}")
        if ti >= 11:
            break
