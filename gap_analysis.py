import re
import frame_generator_schema as s

# Build a comprehensive gap analysis report
with open('PLUZ计量自动化系统技术规范.md', 'r', encoding='utf-8') as f:
    pluz = f.read()
with open('1.md', 'r', encoding='utf-8') as f:
    doc1 = f.read()
with open('1-1.md', 'r', encoding='utf-8') as f:
    doc1_1 = f.read()

all_text = pluz + '\n' + doc1 + '\n' + doc1_1

# Find all DI sections with tables
def find_di_tables(text):
    """Find DI sections that contain data format tables (indicating they have data content)."""
    results = {}
    # Pattern: DI header followed by content with table
    pattern = re.compile(
        r'(?:^|\n)(#{1,6}\s+)?(E8\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2})[：:\s]+([^\n]+)\n'
        r'(.*?)'
        r'(?=(?:^|\n)(?:#{1,6}\s+)?E8\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}[：:\s]+|\Z)',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        di_str = m.group(2)
        name = m.group(3).strip()
        content = m.group(4)
        has_table = '<table' in content
        has_nodata = '无数据' in content or '无数据标识内容' in content
        di_t = tuple(int(x, 16) for x in di_str.split())
        if di_t not in results:
            results[di_t] = {
                'name': name,
                'has_table': has_table,
                'has_nodata': has_nodata,
                'content_preview': content[:200].replace('\n', ' ')
            }
    return results

doc_analysis = find_di_tables(all_text)

with open('field_gap_analysis.txt', 'w', encoding='utf-8') as out:
    out.write('=== Field Definition Gap Analysis ===\n\n')
    
    # Categorize DIs
    schema_only = set(s.DI_FIELD_SCHEMA.keys())
    doc_only = set(doc_analysis.keys())
    
    missing_in_schema = doc_only - schema_only
    missing_in_doc = schema_only - doc_only
    
    out.write(f'DIs in schema: {len(schema_only)}\n')
    out.write(f'DIs found in docs: {len(doc_only)}\n')
    out.write(f'DIs in docs but not schema: {len(missing_in_schema)}\n')
    out.write(f'DIs in schema but not docs: {len(missing_in_doc)}\n\n')
    
    # For each DI in schema, compare fields with doc
    out.write('=== Per-DI Analysis ===\n\n')
    
    for di in sorted(schema_only):
        meta = s.DI_FIELD_SCHEMA[di]
        di_str = f'{di[0]:02X} {di[1]:02X} {di[2]:02X} {di[3]:02X}'
        name = meta['name']
        fields = meta.get('fields', [])
        
        doc_info = doc_analysis.get(di)
        
        if doc_info:
            doc_has_data = doc_info['has_table'] and not doc_info['has_nodata']
            schema_has_data = len(fields) > 0
            
            if doc_has_data and not schema_has_data:
                status = 'MISSING_FIELDS - Doc has table but schema has no fields'
            elif not doc_has_data and schema_has_data:
                status = 'EXTRA_FIELDS - Doc says no data but schema has fields'
            elif doc_has_data and schema_has_data:
                status = 'HAS_FIELDS - Need verification'
            else:
                status = 'OK - No data in both'
        else:
            status = 'NO_DOC - No documentation found'
            doc_has_data = False
        
        out.write(f'{di_str} {name}\n')
        out.write(f'  Status: {status}\n')
        if doc_info:
            out.write(f'  Doc has table: {doc_info["has_table"]}, Doc says no data: {doc_info["has_nodata"]}\n')
        out.write(f'  Schema fields count: {len(fields)}\n')
        if fields:
            for f in fields:
                out.write(f'    - {f.get("name", "unnamed")} ({f.get("type", "?")}, len={f.get("length", "?")})\n')
        out.write('\n')

print('Gap analysis written to field_gap_analysis.txt')
