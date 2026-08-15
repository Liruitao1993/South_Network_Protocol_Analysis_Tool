# -*- coding: utf-8 -*-
"""解析 docx 表格，提取 OFDMA 多用户下发定义"""
import zipfile, re, sys
sys.stdout.reconfigure(encoding="utf-8")

z = zipfile.ZipFile("南网新一代20260226校对/宽带双模通信模块（通感一体物联版）相关测试命令定义_增加相关接口.docx")
xml = z.read("word/document.xml").decode("utf-8")

# 提取所有表格（<w:tbl>...</w:tbl>）
tables = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.DOTALL)
print(f"共 {len(tables)} 个表格")

def cell_text(tc):
    texts = re.findall(r"<w:t>(.*?)</w:t>", tc, re.DOTALL)
    return "".join(texts).strip()

for ti, tbl in enumerate(tables):
    rows = re.findall(r"<w:tr.*?</w:tr>", tbl, re.DOTALL)
    first_row = [cell_text(tc) for tc in re.findall(r"<w:tc>.*?</w:tc>", rows[0], re.DOTALL)] if rows else []
    joined = " | ".join(first_row)
    if "字段" in joined or "字节" in joined or "比特" in joined or "说明" in joined:
        print(f"\n===== 表格{ti} 表头: {joined[:100]} =====")
        # 检查这个表是否含 OFDMA 相关
        full = " ".join("".join(cell_text(tc) for tc in re.findall(r"<w:tc>.*?</w:tc>", r, re.DOTALL)) for r in rows)
        if "OFDMA" in full or "多用户" in full or "TF" in full or "eFC" in full or "RU" in full or "TMI" in full:
            for r in rows[:20]:
                cells = [cell_text(tc) for tc in re.findall(r"<w:tc>.*?</w:tc>", r, re.DOTALL)]
                print("  | " + " | ".join(cells))
