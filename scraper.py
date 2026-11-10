import requests
import os
import openpyxl

# =======================================================
# ?? 配置区（确保后缀严格是 .xlsx）
# =======================================================
FILE_ORDERED = "按序源文件.xlsx"   
FILE_SORTED = "升序源文件.xlsx"    
SHEET_NAME = "数据源"              
# =======================================================

def fetch_data():
    url = "https://raw.githubusercontent.com/icelam/mark-six-data-visualization/master/data/mark-six-results.json"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if not data:
            print("未抓取到数据")
            return None
        latest = data[0]
        issue = str(latest.get("no", "")).strip()
        ordered_nums = latest.get("drawnNo", [])
        special = latest.get("xDrawnNo", "")
        return issue, ordered_nums, special
    except Exception as e:
        print(f"获取数据失败: {e}")
        return None

def write_to_sheet(ws, issue, numbers_list):
    """将期数、年份和拆分的号码强制写入第3行"""
    ws.insert_rows(3)
    
    issue_str = str(issue).strip()
    if len(issue_str) >= 7:
        year = int(issue_str[:4]) 
        tail = issue_str[-3:]     
    else:
        year = 2026               
        tail = issue_str.zfill(3)[-3:]
        
    ws.cell(row=3, column=1).value = int(tail[0])
    ws.cell(row=3, column=2).value = int(tail[1])
    ws.cell(row=3, column=3).value = int(tail[2])
    ws.cell(row=3, column=27).value = year
    
    current_col = 4
    for num in numbers_list:
        num_int = int(num)
        ws.cell(row=3, column=current_col).value = num_int // 10  
        ws.cell(row=3, column=current_col + 1).value = num_int % 10 
        current_col += 2

def process_excel(file_path, issue, numbers_list, file_desc):
    if not os.path.exists(file_path):
        print(f"? 找不到文件: {file_path}")
        return

    print(f"正在处理 {file_desc}...")
    
    # ?? 核心修改：因为已经是 xlsx，不要加 keep_vba，直接加载
    try:
        wb = openpyxl.load_workbook(file_path)
    except Exception as e:
        print(f"? 打开文件失败: {e}")
        return
    
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        
        print(f"?? 强制将 {issue} 期数据写入 {file_desc}...")
        write_to_sheet(ws, issue, numbers_list)
        try:
            wb.save(file_path)
            print(f"? {file_desc} 保存成功！")
        except Exception as e:
            print(f"? 保存失败: {e}")
    else:
        print(f"?? 在 {file_path} 中找不到工作表: {SHEET_NAME}")

def main():
    result = fetch_data()
    if not result:
        return
    
    issue, ordered_nums, special = result
    print(f"? 成功获取最新数据: {issue} 期")
    print(f"原始数据: {ordered_nums}, 特码: {special}")
    
    all_ordered = ordered_nums + [special]
    all_sorted = sorted([int(n) for n in ordered_nums]) + [special]

    process_excel(FILE_ORDERED, issue, all_ordered, "按序源文件")
    process_excel(FILE_SORTED, issue, all_sorted, "升序源文件")

if __name__ == "__main__":
    main()
