"""
提取 PDF 文档中所有 DI 的数据内容格式定义
"""
import re

# 读取 PDF 提取内容
with open("pdf_extract内容.txt", "r", encoding="utf-8") as f:
    content = f.read()

# 查找所有 DI 定义 (格式: E8 XX XX XX：描述)
di_pattern = r"E8 [0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2}[:：]([^\n]+)"
di_matches = re.findall(di_pattern, content)

print(f"找到 {len(di_matches)} 个 DI 定义:\n")
for i, desc in enumerate(di_matches[:30], 1):  # 先显示前30个
    print(f"{i}. {desc.strip()}")

# 查找所有包含"数据标识内容格式"的部分
print("\n\n=== 包含数据标识内容格式的 DI ===")
format_pattern = r"E8 [0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2}[:：][^\n]+\n数据标识内容格式见下表"
format_matches = re.findall(format_pattern, content)
print(f"找到 {len(format_matches)} 个有数据内容格式的 DI")
for match in format_matches[:10]:
    print(match.replace("\n", " | "))
