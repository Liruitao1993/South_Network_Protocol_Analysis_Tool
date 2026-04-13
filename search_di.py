import sys
sys.path.append('.')

# 读取提取的文本
with open('pdf_extract 内容.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"总行数：{len(lines)}")
print("\n" + "="*80)
print("搜索包含 '05 05 05' 的行:")
print("="*80)

for i, line in enumerate(lines):
    if '05 05 05' in line:
        print(f"\n第 {i+1} 行:")
        print("-" * 80)
        # 显示上下文
        start = max(0, i-3)
        end = min(len(lines), i+8)
        for j in range(start, end):
            marker = ">>> " if j == i else "    "
            print(f"{marker}{lines[j]}", end='')

print("\n" + "="*80)
print("搜索包含'上报任务状态'的行:")
print("="*80)

for i, line in enumerate(lines):
    if '上报任务状态' in line:
        print(f"\n第 {i+1} 行:")
        print("-" * 80)
        start = max(0, i-2)
        end = min(len(lines), i+15)
        for j in range(start, end):
            marker = ">>> " if j == i else "    "
            print(f"{marker}{lines[j]}", end='')
