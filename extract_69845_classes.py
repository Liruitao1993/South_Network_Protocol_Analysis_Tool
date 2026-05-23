"""
Extract interface class definitions (attributes & methods) from DL/T 698.45 protocol doc.
Output: class_id-based map for dl_t698_45_oi_lookup.py
"""
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('面向对象的用电信息数据交换协议(20210910).md', 'r', encoding='utf-8') as f:
    content = f.read()

def extract_table_rows(html_table):
    """Extract text from HTML table rows."""
    rows = []
    for tr_match in re.finditer(r'<tr>(.*?)</tr>', html_table, re.DOTALL):
        tr = tr_match.group(1)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if cells and any(cells):
            rows.append(cells)
    return rows

def find_interface_classes(text):
    """Find all interface class definition tables in section 8.2."""
    classes = {}

    # Find all class definition tables: pattern "class_id=数字"
    # Each class section starts with #### 8.2.N 类名
    section_pattern = re.compile(
        r'#### 8\.2\.(\d+)\s+(.+?)\n.*?'
        r'class_id\s*=\s*(\d+).*?'
        r'<table[^>]*>(.*?)</table>',
        re.DOTALL
    )

    # Actually, let's use a simpler approach: find all "class_id = N" or "class_id=N"
    class_headers = list(re.finditer(r'class_id\s*=\s*(\d+)', text))

    for i, m in enumerate(class_headers):
        class_id = int(m.group(1))
        if class_id in classes:
            continue
        if class_id > 50:  # Skip manufacturer-specific classes
            continue

        start_pos = m.start()
        # Find the end of this class section (next class_id or end of 8.2)
        if i + 1 < len(class_headers):
            end_pos = class_headers[i + 1].start()
        else:
            end_pos = text.find('### 8.3', start_pos)
            if end_pos == -1:
                end_pos = len(text)

        section = text[start_pos:end_pos]

        # Extract class name from nearby text
        name_match = re.search(r'(.{0,50}class_id\s*=\s*\d+.{0,50})', section, re.DOTALL)
        class_name = f"接口类{class_id}"

        # Try to find class name from the header before class_id
        header_search = text[max(0, start_pos-500):start_pos]
        header_match = re.search(r'####\s+8\.2\.\d+\s+(.+?)\n', header_search)
        if header_match:
            class_name = header_match.group(1).strip()
            # Remove trailing "类" if present or keep it
            class_name = class_name.replace('接口类', '')

        # Find the main definition table (immediately after class_id)
        table_match = re.search(r'<table[^>]*>(.*?)</table>', section, re.DOTALL)
        if not table_match:
            continue

        rows = extract_table_rows(table_match.group(1))

        attributes = {}
        methods = {}
        in_methods = False

        for row in rows:
            if not row:
                continue
            # Check for method header row
            if any('方法' in cell for cell in row) and any('必选' in cell or '可选' in cell for cell in row):
                in_methods = True
                continue
            # Check for attribute header row
            if any('属性' in cell for cell in row) and any('数据类型' in cell for cell in row):
                in_methods = False
                continue

            if in_methods:
                # Method row: typically [number, method_name, m/o] or [number, method_name(parameter), m/o]
                # Or merged cells: [number, method_name\nparam, desc]
                method_num = None
                method_name = None
                for cell in row:
                    m = re.match(r'(\d+)\.', cell)
                    if m:
                        method_num = int(m.group(1))
                        method_name = cell[m.end():].strip()
                        break
                if method_num is None and len(row) >= 2:
                    # Try first cell as number
                    m = re.match(r'(\d+)', row[0])
                    if m:
                        method_num = int(m.group(1))
                        method_name = row[1] if len(row) > 1 else row[0]

                if method_num is not None and method_name:
                    # Clean up method name
                    method_name = method_name.split('\n')[0].strip()
                    method_name = re.sub(r'参数::=.*', '', method_name).strip()
                    method_name = re.sub(r'\(.*$', '', method_name).strip()
                    if method_name:
                        methods[method_num] = method_name
            else:
                # Attribute row: typically [number. name, (static/dyn.), type]
                attr_num = None
                attr_name = None
                for cell in row:
                    m = re.match(r'(\d+)\.\s*(.+)', cell)
                    if m:
                        attr_num = int(m.group(1))
                        attr_name = m.group(2).strip()
                        break

                if attr_num is None and len(row) >= 1:
                    m = re.match(r'(\d+)\.\s*(.+)', row[0])
                    if m:
                        attr_num = int(m.group(1))
                        attr_name = m.group(2).strip()

                if attr_num is not None and attr_name:
                    attr_name = attr_name.split('::=')[0].strip()
                    attr_name = re.sub(r'\(static\)|\(dyn\.\)', '', attr_name).strip()
                    if attr_name:
                        attributes[attr_num] = attr_name

        classes[class_id] = {
            'name': class_name,
            'attributes': attributes,
            'methods': methods,
        }

    return classes

# Also find attribute explanation tables for more accurate names
def find_attribute_tables(text, classes):
    """Find attribute explanation tables and merge better names."""
    # Pattern: 表XXX 类名属性说明
    for class_id, info in classes.items():
        class_name = info['name']
        # Search for "类名属性说明" or "class_name属性说明"
        search_name = class_name.replace('类', '').strip()
        patterns = [
            rf'表\d+\s*{re.escape(search_name)}类?属性说明.*?<table[^>]*>(.*?)</table>',
            rf'表\d+\s*{re.escape(class_name)}类?属性说明.*?<table[^>]*>(.*?)</table>',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL)
            if m:
                rows = extract_table_rows(m.group(1))
                for row in rows:
                    if len(row) >= 2:
                        num_match = re.match(r'(\d+)', row[0])
                        if num_match:
                            attr_num = int(num_match.group(1))
                            attr_desc = row[1].strip()
                            # Extract just the name before ::=
                            attr_name = attr_desc.split('::=')[0].strip()
                            attr_name = attr_name.split(' ')[0].strip()
                            if attr_num in info['attributes'] and len(attr_name) > len(info['attributes'][attr_num]):
                                info['attributes'][attr_num] = attr_name
                            elif attr_num not in info['attributes'] and attr_name:
                                info['attributes'][attr_num] = attr_name
                break

    return classes

# Also find method explanation tables
def find_method_tables(text, classes):
    """Find method explanation tables and merge better names."""
    for class_id, info in classes.items():
        class_name = info['name']
        search_name = class_name.replace('类', '').strip()
        patterns = [
            rf'表\d+\s*{re.escape(search_name)}类?方法说明.*?<table[^>]*>(.*?)</table>',
            rf'表\d+\s*{re.escape(class_name)}类?方法说明.*?<table[^>]*>(.*?)</table>',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL)
            if m:
                rows = extract_table_rows(m.group(1))
                for row in rows:
                    if len(row) >= 2:
                        num_match = re.match(r'(\d+)', row[0])
                        if num_match:
                            method_num = int(num_match.group(1))
                            method_desc = row[1].strip()
                            method_name = method_desc.split('（')[0].split('(')[0].strip()
                            if method_num in info['methods']:
                                info['methods'][method_num] = method_name
                            elif method_name:
                                info['methods'][method_num] = method_name
                break

    return classes

print("Extracting interface classes...")
classes = find_interface_classes(content)
print(f"Found {len(classes)} interface classes")

classes = find_attribute_tables(content, classes)
classes = find_method_tables(content, classes)

# Print summary
for cid in sorted(classes.keys()):
    info = classes[cid]
    print(f"\nclass_id={cid}: {info['name']}")
    print(f"  Attributes ({len(info['attributes'])}): {list(info['attributes'].items())[:5]}...")
    print(f"  Methods ({len(info['methods'])}): {list(info['methods'].items())}")

# Save to JSON for inspection
import json
with open('extracted_classes.json', 'w', encoding='utf-8') as f:
    json.dump(classes, f, ensure_ascii=False, indent=2)
print("\nSaved to extracted_classes.json")
