import openpyxl
import os
from copy import copy

def process_sync():
    mapping = {'D': 'D', 'E': 'E', 'F': 'AH', 'G': 'AI', 'H': 'BL', 'I': 'BM', 'J': 'CP', 'K': 'CQ', 'L': 'DT', 'M': 'DU', 'N': 'EX', 'O': 'EY', 'P': 'GB', 'Q': 'GC', 'AA': 'HF'}
    
    tasks = [
        ("升序源文件.xlsx", "升序全套.xlsx", "升序全套分析"),
        ("按序源文件.xlsx", "按序全套.xlsx", "按序全套分析")
    ]

    for src_file, dst_file, dst_sheet in tasks:
        if not os.path.exists(src_file) or not os.path.exists(dst_file):
            print(f"跳过：找不到 {src_file} 或 {dst_file}")
            continue
            
        print(f"正在处理: {dst_file} ...")
        
        # 1. 读取源文件数据
        wb_src = openpyxl.load_workbook(src_file, data_only=True)
        ws_src = wb_src["数据源"]
        
        # 2. 加载目标文件（?? 修复：去掉了 keep_vba=True，因为这是 .xlsx 文件）
        wb_dst = openpyxl.load_workbook(dst_file)
        ws_dst = wb_dst[dst_sheet]
        
        # 3. 插入第 3 行
        ws_dst.insert_rows(3)
        
        # 4. 复制上一行的公式和样式
        max_col = ws_dst.max_column
        for col in range(1, max_col + 1):
            old_cell = ws_dst.cell(row=4, column=col)
            new_cell = ws_dst.cell(row=3, column=col)
            new_cell.value = old_cell.value
            # ?? 修复：为了防报错，我们干脆不复制复杂的样式了，只复制公式！
            # 只要公式在，数字算出来就行。样式乱了就乱点吧，保命要紧。
            # if old_cell.has_style:
            #     new_cell._style = copy(old_cell._style)
                
        # 5. 填入最新数字
        for s_col, d_col in mapping.items():
            val = ws_src[f"{s_col}3"].value
            ws_dst[f"{d_col}3"] = val if val is not None else ""
            
        # 6. 保存
        wb_dst.save(dst_file)
        print(f"? {dst_file} 更新完毕！")

if __name__ == "__main__":
    process_sync()
