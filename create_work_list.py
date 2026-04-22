import re
import frame_generator_schema as s

with open('PLUZ计量自动化系统技术规范.md', 'r', encoding='utf-8') as f:
    pluz = f.read()
with open('1.md', 'r', encoding='utf-8') as f:
    doc1 = f.read()
with open('1-1.md', 'r', encoding='utf-8') as f:
    doc1_1 = f.read()

all_text = pluz + '\n' + doc1 + '\n' + doc1_1

def extract_di_downlink_fields(text, di):
    """Extract downlink field definitions for a specific DI."""
    di_s = f'{di[0]:02X} {di[1]:02X} {di[2]:02X} {di[3]:02X}'
    
    # Find DI section
    pattern = re.compile(
        r'(?:^|\n)(#{1,6}\s+' + re.escape(di_s) + r'[：:\s]+[^\n]+)\n'
        r'(.*?)'
        r'(?=(?:^|\n)#{1,6}\s+(?:E8|6\.8|6\.9|附录)\s|\Z)',
        re.DOTALL
    )
    m = pattern.search(text)
    if not m:
        return None
    
    content = m.group(2)
    
    # Split into downlink and uplink sections
    downlink = None
    uplink = None
    
    if '下行报文' in content:
        parts = content.split('上行报文', 1)
        downlink = parts[0]
        if len(parts) > 1:
            uplink = parts[1]
    elif '无数据标识内容' in content or '无数据内容' in content:
        downlink = content  # No data, but capture for confirmation
    else:
        downlink = content  # Assume all is downlink if not explicitly split
    
    # Extract table rows from downlink section
    rows = []
    if downlink:
        for tr_match in re.finditer(r'<tr>(.*?)</tr>', downlink, re.DOTALL):
            tr = tr_match.group(1)
            cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if cells and any(cells):
                rows.append(cells)
    
    # Determine if no data
    has_nodata = downlink and ('无数据标识内容' in downlink or '无数据内容' in downlink)
    
    # Filter data rows (skip header rows)
    data_rows = []
    for row in rows:
        if len(row) >= 3:
            # Skip header row
            if any(k in row[0] for k in ['数据内容', '数据标识内容', '数据项', '名称']):
                if any(k in ' '.join(row) for k in ['数据格式', '字节数', '长度']):
                    continue
            # Skip rows that are clearly headers
            if row[0] in ['数据内容', '数据标识内容']:
                continue
            data_rows.append(row)
    
    return {
        'has_nodata': has_nodata,
        'data_rows': data_rows,
        'all_rows': rows
    }

# Build comprehensive work list
with open('work_list.md', 'w', encoding='utf-8') as out:
    out.write('# 字段定义修正工作列表\n\n')
    out.write('## 总体情况\n\n')
    
    # Categorize by AFN
    afn_groups = {
        '01H': [],
        '02H': [],
        '03H': [],
        '04H': [],
        '05H': [],
        '07H': [],
        '其他': []
    }
    
    for di in sorted(s.DI_FIELD_SCHEMA.keys()):
        afn = di[1]
        if afn == 0x01:
            group = '01H'
        elif afn == 0x02:
            group = '02H'
        elif afn == 0x03:
            group = '03H'
        elif afn == 0x04:
            group = '04H'
        elif afn == 0x05:
            group = '05H'
        elif afn == 0x07:
            group = '07H'
        else:
            group = '其他'
        
        meta = s.DI_FIELD_SCHEMA[di]
        doc_info = extract_di_downlink_fields(all_text, di)
        
        afn_groups[group].append({
            'di': di,
            'name': meta['name'],
            'schema_fields': meta.get('fields', []),
            'doc_info': doc_info
        })
    
    for group, items in afn_groups.items():
        if not items:
            continue
        out.write(f'## AFN={group} ({len(items)}个DI)\n\n')
        for item in items:
            di = item['di']
            di_str = f'{di[0]:02X} {di[1]:02X} {di[2]:02X} {di[3]:02X}'
            name = item['name']
            schema_fields = item['schema_fields']
            doc_info = item['doc_info']
            
            out.write(f'### {di_str} {name}\n\n')
            
            if not doc_info:
                out.write('- **状态**: 文档中未找到定义\n')
                if schema_fields:
                    out.write(f'- **当前字段数**: {len(schema_fields)}\n')
                out.write('\n')
                continue
            
            if doc_info['has_nodata']:
                out.write('- **文档定义**: 无数据标识内容\n')
                if schema_fields:
                    out.write(f'- **当前字段数**: {len(schema_fields)} (⚠️ 文档说无数据，但schema定义了字段)\n')
                    for f in schema_fields:
                        out.write(f'  - {f}\n')
                else:
                    out.write('- **当前字段数**: 0 ✅\n')
            elif doc_info['data_rows']:
                out.write(f'- **文档定义**: 有数据内容 ({len(doc_info["data_rows"])}个字段)\n')
                out.write('- **文档字段**:\n')
                for row in doc_info['data_rows']:
                    out.write(f'  - {row}\n')
                if schema_fields:
                    out.write(f'- **当前字段数**: {len(schema_fields)}\n')
                    for f in schema_fields:
                        out.write(f'  - {f}\n')
                else:
                    out.write('- **当前字段数**: 0 ❌ (缺少字段定义)\n')
            else:
                out.write('- **文档定义**: 有表格但无法解析数据行\n')
                if schema_fields:
                    out.write(f'- **当前字段数**: {len(schema_fields)}\n')
                out.write('\n')
            
            out.write('\n')

print('Work list written to work_list.md')
