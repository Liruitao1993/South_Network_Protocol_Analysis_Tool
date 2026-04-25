import json

# 加载LME信息条目
with open(r'e:\python\南网解析工具\lme_info_entries.json', 'r', encoding='utf-8') as f:
    entries = json.load(f)

# 按分类组织
from collections import defaultdict
groups = defaultdict(list)

for entry in entries[1:]:  # 跳过表头
    group_id = entry['group_id'].replace('\n', '').strip()
    item_id = entry['item_id'].strip()
    name = entry['name']
    
    if item_id:
        try:
            item_num = int(item_id)
            groups[group_id].append({
                'id': item_num,
                'name': name,
                'hex': f"0x{item_num:02X}"
            })
        except:
            pass

# 打印所有分类和条目
for group_name, items in sorted(groups.items()):
    print(f"\n{'='*80}")
    print(f"分类: {group_name}")
    print(f"{'='*80}")
    for item in sorted(items, key=lambda x: x['id']):
        print(f"  ID: {item['hex']} ({item['id']:3d}) - {item['name']}")

# 从报文中提取的ID
frame_ids = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 
             0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B, 0x50, 0x51, 0x54, 0x55, 0x56, 0x57, 0x58, 0x5E,
             0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x8B, 0x94, 0x95, 0x96, 0x97, 0x99, 0xC1, 0xC2]

print(f"\n{'='*80}")
print("报文中出现的ID与LME文档的匹配情况:")
print(f"{'='*80}")

# 建立ID到条目的映射
id_map = {}
for group_name, items in groups.items():
    for item in items:
        id_map[item['id']] = item['name']

for fid in frame_ids:
    if fid in id_map:
        print(f"  0x{fid:02X} ({fid:3d}): ✓ {id_map[fid]}")
    else:
        print(f"  0x{fid:02X} ({fid:3d}): ✗ 未知ID")
