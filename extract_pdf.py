import fitz  # PyMuPDF

def extract_pdf_text(pdf_path):
    """提取 PDF 文本内容"""
    doc = fitz.open(pdf_path)
    all_text = []
    
    print(f"PDF 文档信息:")
    print(f"  总页数：{len(doc)}")
    print(f"  标题：{doc.metadata.get('title', 'N/A')}")
    print()
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        
        if text.strip():
            all_text.append(f"\n{'='*80}\n第 {page_num + 1} 页\n{'='*80}\n")
            all_text.append(text)
    
    doc.close()
    
    # 保存提取的文本
    with open('pdf_extract内容.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_text))
    
    print(f"已提取 {len(all_text)} 段文本")
    print("完整内容已保存到：pdf_extract 内容.txt")
    
    return '\n'.join(all_text)

if __name__ == "__main__":
    text = extract_pdf_text("2.pdf")
    print("\n" + "="*80)
    print("开始搜索 DI=E8:05:05:05 相关内容...")
    print("="*80)
    
    # 搜索关键字
    keywords = ["E8:05:05:05", "05 05 05", "上报", "AFN=05", "DI 组合"]
    for keyword in keywords:
        if keyword in text:
            print(f"\n找到包含 '{keyword}' 的内容:")
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if keyword in line:
                    # 显示上下文
                    start = max(0, i-2)
                    end = min(len(lines), i+3)
                    print(f"\n  第 {start+1}-{end} 行:")
                    for j in range(start, end):
                        marker = ">>> " if j == i else "    "
                        print(f"{marker}{lines[j]}")
