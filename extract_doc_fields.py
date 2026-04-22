"""
Extract precise field definitions from PLUZ markdown tables for all DIs in schema.
"""
import re
import frame_generator_schema as s

with open('PLUZ计量自动化系统技术规范.md','r',encoding='utf-8') as f:
    pluz = f.read()
with open('1.md','r',encoding='utf-8') as f:
    doc1 = f.read()
with open('1-1.md','r',encoding='utf-8') as f:
    doc1_1 = f.read()

all_text = pluz + '\n' + doc1 + '\n' + doc1_1

def extract_table_data(content):
    """Extract rows from HTML table in markdown content."""
    rows = []
    # Find table rows
    for tr_match in re.finditer(r'<tr>(.*?)</tr>', content, re.DOTALL):
        tr = tr_match.group(1)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if cells and any(cells):
            rows.append(cells)
    return rows

def find_di_sections(text):
    """Find all DI sections with their content."""
    sections = {}
    # Match DI headers
    pattern = re.compile(
        r'(?:^|\n)(#{1,6}\s+)?(E8\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2})[：:\s]+([^\n]+)\n'
        r'(.*?)'
        r'(?=(?:^|\n)(?:#{1,6}\s+)?(?:E8|6\.8|6\.9|附录)\s|\Z)',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        di_str = m.group(2)
        name = m.group(3).strip()
        content = m.group(4)
        di_t = tuple(int(x, 16) for x in di_str.split())
        if di_t not in sections or len(content) > len(sections[di_t]['content']):
            sections[di_t] = {'name': name, 'content': content}
    return sections

sections = find_di_sections(all_text)

with open('doc_field_extraction.txt', 'w', encoding='utf-8') as out:
    for di in sorted(s.DI_FIELD_SCHEMA.keys()):
        di_str = f'{di[0]:02X} {di[1]:02X} {di[2]:02X} {di[3]:02X}'
        name = s.DI_FIELD_SCHEMA[di]['name']
        section = sections.get(di)
        
        out.write(f'=== {di_str} {name} ===\n')
        
        if not section:
            out.write('  NO DOC SECTION FOUND\n\n')
            continue
        
        content = section['content']
        has_nodata = '无数据标识内容' in content or '无数据内容' in content
        rows = extract_table_data(content)
        
        # Filter rows that look like data format tables (have 数据内容/数据格式/字节数)
        data_rows = []
        for row in rows:
            if len(row) >= 3 and any(k in row[0] for k in ['数据内容', '数据标识内容', '数据项']):
                continue  # Skip header row
            if len(row) >= 3 and any(k in ' '.join(row) for k in ['数据格式', '字节数', 'BIN', 'BCD', 'ASCII']):
                data_rows.append(row)
        
        if has_nodata and not data_rows:
            out.write('  NO DATA UNIT (confirmed by doc)\n')
        elif data_rows:
            out.write(f'  DATA TABLE ({len(data_rows)} rows):\n')
            for row in data_rows:
                out.write(f'    {row}\n')
        else:
            out.write(f'  UNCLEAR - Has table but no clear data rows\n')
            for row in rows[:5]:
                out.write(f'    RAW: {row}\n')
        
        out.write('\n')

print('Extraction complete: doc_field_extraction.txt')
