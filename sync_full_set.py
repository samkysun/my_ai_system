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
            continue
            
        wb_src = openpyxl.load_workbook(src_file, data_only=True)
        ws_src = wb_src["数据源"]
        
        wb_dst = openpyxl.load_workbook(dst_file, keep_vba=True)
        ws_dst = wb_dst[dst_sheet]
        
        ws_dst.insert_rows(3)
        max_col = ws_dst.max_column
        for col in range(1, max_col + 1):
            old_cell = ws_dst.cell(row=4, column=col)
            new_cell = ws_dst.cell(row=3, column=col)
            new_cell.value = old_cell.value
            if old_cell.has_style:
                new_cell._style = copy(old_cell._style)
                
        for s_col, d_col in mapping.items():
            val = ws_src[f"{s_col}3"].value
            ws_dst[f"{d_col}3"] = val if val is not None else ""
            
        wb_dst.save(dst_file)
        print(f"✅ {dst_file} 更新完毕！")

if __name__ == "__main__":
    process_sync()
