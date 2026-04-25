import json

with open(r'e:\python\南网解析工具\lme_all_tables.json', 'r', encoding='utf-8') as f:
    tables = json.load(f)

# Table 11 是主要的信息条目定义表
table_11 = tables[11]
print(f'Table 11: {table_11["rows"]} rows, {table_11["cols"]} cols')
print('Header:', table_11['data'][0])
print()

# 提取所有数据行
info_entries = []
for row in table_11['data'][1:]:
    if len(row) >= 9 and row[0]:  # 确保有数据
        entry = {
            'group_id': row[0],
            'item_id': row[1],
            'name': row[2],
            'format': row[3],
            'data_type': row[4],
            'length': row[5],
            'storage': row[6],
            'permission': row[7],
            'description': row[8]
        }
        info_entries.append(entry)

print(f'提取了 {len(info_entries)} 条信息条目')
print()

# 保存到JSON
with open(r'e:\python\南网解析工具\lme_info_entries.json', 'w', encoding='utf-8') as f:
    json.dump(info_entries, f, ensure_ascii=False, indent=2)

print('信息条目已保存到 lme_info_entries.json')
print()
print('=== 前20条信息条目 ===')
for entry in info_entries[:20]:
    print(f"组: {entry['group_id']}, ID: {entry['item_id']}, 名称: {entry['name']}")
