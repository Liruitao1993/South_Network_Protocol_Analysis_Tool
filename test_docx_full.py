# -*- coding: utf-8 -*-
"""导出 docx 全部表格 + 所在段落标题"""
import zipfile, re, sys
sys.stdout.reconfigure(encoding="utf-8")

z = zipfile.ZipFile("南网新一代20260226校对/宽带双模通信模块（通感一体物联版）相关测试命令定义_增加相关接口.docx")
xml = z.read("word/document.xml").decode("utf-8")

# 按段落和表格顺序提取（w:p 段落, w:tbl 表格）
# 简化：先找所有表格 + 表格前面的段落标题
paras = re.split(r"(<w:tbl>.*?</w:tbl>)", xml, flags=re.DOTALL)

def cell_text(tc):
    return "".join(re.findall(r"<w:t>(.*?)</w:t>", tc, re.DOTALL)).strip()

def para_text(p):
    return "".join(re.findall(r"<w:t>(.*?)</w:t>", p, re.DOTALL)).strip()

out = []
for seg in paras:
    if seg.startswith("<w:tbl>"):
        rows = re.findall(r"<w:tr.*?</w:tr>", seg, re.DOTALL)
        for r in rows:
            cells = [cell_text(tc) for tc in re.findall(r"<w:tc>.*?</w:tc>", r, re.DOTALL)]
            if cells and any(cells):
                out.append("  TBL | " + " | ".join(cells))
    elif seg.strip():
        t = para_text(seg)
        if t:
            out.append(t)

with open("docx_tables_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("done", len(out), "lines")
