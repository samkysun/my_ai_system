import openpyxl
import os
from copy import copy

def process_sync():
    mapping = {'D': 'D', 'E': 'E', 'F': 'AH', 'G': 'AI', 'H': 'BL', 'I': 'BM', 'J': 'CP', 'K': 'CQ', 'L': 'DT', 'M': 'DU', 'N': 'EX', 'O': 'EY', 'P': 'GB', 'Q': 'GC', 'AA': 'HF'}
    
    # 我们要生成的全新安全文件
    tasks = [
        ("升序源文件.xlsx", "升序全套.xlsx", "升序全套分析", "升序分析_纯净版.xlsx"),
        ("按序源文件.xlsx", "按序全套.xlsx", "按序全套分析", "按序分析_纯净版.xlsx")
    ]

    for src_file, template_file, sheet_name, out_file in tasks:
        if not os.path.exists(src_file) or not os.path.exists(template_file):
            print(f"跳过：找不到 {src_file} 或 {template_file}")
            continue
            
        print(f"正在安全生成: {out_file} ...")
        
        # 1. 读取源文件最新数据
        wb_src = openpyxl.load_workbook(src_file, data_only=True)
        ws_src = wb_src["数据源"]
        
        # 2. 打开模板文件（只是读取公式，不保存回去）
        wb_tpl = openpyxl.load_workbook(template_file, keep_vba=False)
        ws_tpl = wb_tpl[sheet_name]
        
        # 3. 创建一个全新的纯净工作簿
        wb_out = openpyxl.Workbook()
        ws_out = wb_out.active
        ws_out.title = sheet_name
        
        # 4. 从模板复制前 10 行（连带公式）到新文件
        for r in range(1, 11): 
            for c in range(1, ws_tpl.max_column + 1):
                cell_tpl = ws_tpl.cell(row=r, column=c)
                cell_out = ws_out.cell(row=r, column=c)
                cell_out.value = cell_tpl.value
                if cell_tpl.has_style:
                    cell_out._style = copy(cell_tpl._style)
                    
        # 5. 把最新数据覆盖到第 3 行
        for s_col, d_col in mapping.items():
            val = ws_src[f"{s_col}3"].value
            ws_out[f"{d_col}3"] = val if val is not None else ""
            
        # 6. 保存为全新的安全文件
        wb_out.save(out_file)
        print(f"✅ 安全生成完毕: {out_file}")

if __name__ == "__main__":
    process_sync()
