"""
Extract OI -> class_id mappings from Appendix A tables in the 698.45 protocol doc.
"""
import re
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

with open('面向对象的用电信息数据交换协议(20210910).md', 'r', encoding='utf-8') as f:
    content = f.read()

def extract_table_rows(html_table):
    rows = []
    for tr_match in re.finditer(r'<tr>(.*?)</tr>', html_table, re.DOTALL):
        tr = tr_match.group(1)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if cells and any(cells):
            rows.append(cells)
    return rows

# Find all Appendix A OI definition tables (表A.2 through A.12, excluding A.11)
# Pattern: 表A.N OIA1=XH 对象标识定义
oi_to_class = {}

# Find all tables that look like OI definition tables
for m in re.finditer(r'表A\.(\d+)\s+.*?OIA1=([0-9A-Fa-f])H\s+对象标识定义.*?(?=<table)(<table[^>]*>.*?</table>)', content, re.DOTALL):
    table_num = int(m.group(1))
    oia1 = m.group(2).upper()
    table_html = m.group(3)
    rows = extract_table_rows(table_html)

    for row in rows:
        if len(row) >= 2:
            # First cell is OI, second cell is IC (class_id)
            oi_str = row[0].strip()
            ic_str = row[1].strip()
            # Skip header rows
            if oi_str.upper() in ('OI', '01', '对象标识'):
                continue
            if not all(c in '0123456789ABCDEFabcdef' for c in oi_str):
                continue
            try:
                oi = int(oi_str, 16)
                class_id = int(ic_str)
                if 1 <= class_id <= 50:
                    oi_to_class[oi] = class_id
            except ValueError:
                pass

# Also find tables with slightly different format
for m in re.finditer(r'(<table[^>]*>.*?</table>)', content, re.DOTALL):
    table_html = m.group(1)
    rows = extract_table_rows(table_html)
    for row in rows:
        if len(row) >= 4:
            # Format: OI | IC | 对象名称 | 实例的对象属性及方法定义
            oi_str = row[0].strip()
            ic_str = row[1].strip()
            if oi_str.upper() in ('OI', '01', '对象标识', '0I'):
                continue
            if not all(c in '0123456789ABCDEFabcdef' for c in oi_str):
                continue
            try:
                oi = int(oi_str, 16)
                class_id = int(ic_str)
                if 1 <= class_id <= 50 and oi not in oi_to_class:
                    oi_to_class[oi] = class_id
            except ValueError:
                pass

print(f"Extracted {len(oi_to_class)} OI->class_id mappings")

# Verify some known mappings
for oi in [0x0010, 0x1010, 0x2000, 0x3000, 0x4000, 0x5000, 0x6000, 0x7000, 0x8000, 0xF000]:
    print(f"  0x{oi:04X} -> class_id={oi_to_class.get(oi, 'N/A')}")

with open('oi_to_class.json', 'w', encoding='utf-8') as f:
    json.dump({f"0x{k:04X}": v for k, v in sorted(oi_to_class.items())}, f, ensure_ascii=False, indent=2)
print("Saved to oi_to_class.json")
