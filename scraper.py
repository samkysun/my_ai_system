import requests
import os
import openpyxl

# =======================================================
# ?? 配置区
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
        latest = data[0]
        issue = str(latest.get("no", "")).strip()
        ordered_nums = latest.get("drawnNo", [])
        special = latest.get("xDrawnNo", "")
        return issue, ordered_nums, special
    except Exception as e:
        print(f"? 获取数据失败: {e}")
        return None

def process_excel(file_path, issue, numbers_list, file_desc):
    print(f"\\\\n--- 开始处理: {file_desc} ---")
    
    if not os.path.exists(file_path):
        print(f"? 找不到文件: {file_path}")
        return

    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb[SHEET_NAME]
    except Exception as e:
        print(f"? 打开文件或工作表失败: {e}")
        return
    
    # 拆解期数
    issue_str = str(issue).strip()
    if len(issue_str) >= 7:
        year = int(issue_str[:4]) # 例如 2026
        tail = issue_str[-3:]     # 例如 119
    else:
        year = 2026
        tail = issue_str.zfill(3)[-3:]
        
    print(f"?? 准备写入期数: {issue_str} -> 年份:{year}, 尾数:{tail}")
    print(f"?? 准备写入号码: {numbers_list}")
    
    # 插入新行
    ws.insert_rows(3)
    
    # ==========================================
    # ?? 核心：绝对精准的列名写入 (A, B, C...)
    # ==========================================
    # 1. 写入期数后3位 (A, B, C列)
    ws["A3"] = int(tail[0])
    ws["B3"] = int(tail[1])
    ws["C3"] = int(tail[2])
    
    # 2. 写入年份 (AA列，即第27列)
    ws["AA3"] = year
    
    # 3. 写入拆分的号码 (D列开始，按字母顺序给)
    # 号码列表一共 7 个：6个平码 + 1个特码
    cols = ["D", "F", "H", "J", "L", "N", "P"] # 每个号码的十位所在的列
    
    for i, num in enumerate(numbers_list):
        num_int = int(num)
        col_letter = cols[i]
        
        # 写入十位
        ws[f"{col_letter}3"] = num_int // 10
        # 写入个位 (列往后推一格，比如 D 的个位在 E)
        next_col_letter = chr(ord(col_letter) + 1)
        ws[f"{next_col_letter}3"] = num_int % 10
        
        print(f"   -> 第{i+1}球: {num_int} 写入 {col_letter}3 和 {next_col_letter}3")
        
    # 保存
    try:
        wb.save(file_path)
        print(f"?? {file_desc} 保存成功！")
    except Exception as e:
        print(f"? 保存失败，原因: {e}")

def main():
    result = fetch_data()
    if not result:
        return
    
    issue, ordered_nums, special = result
    print(f"=====================================")
    print(f"? 抓取成功！当前期数: {issue}")
    print(f"? 平码数据: {ordered_nums}")
    print(f"? 特码数据: {special}")
    print(f"=====================================")
    
    # 按序：前6平码 + 特码
    all_ordered = ordered_nums + [special]
    # 升序：前6平码升序 + 特码
    all_sorted = sorted([int(n) for n in ordered_nums]) + [special]

    process_excel(FILE_ORDERED, issue, all_ordered, "按序源文件")
    process_excel(FILE_SORTED, issue, all_sorted, "升序源文件")

if __name__ == "__main__":
    main()
