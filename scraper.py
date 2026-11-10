import requests
import os
import openpyxl

# =======================================================
# ⚙️ 配置区
# =======================================================
FILE_ORDERED = "按序源文件.xlsm"   # 按序 Excel 文件名
FILE_SORTED = "升序源文件.xlsm"    # 升序 Excel 文件名
SHEET_NAME = "数据源"              # 两个文件里都叫这个名字
# =======================================================

def fetch_data():
    url = "https://raw.githubusercontent.com/icelam/mark-six-data-visualization/master/data/mark-six-results.json"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if not data:
            print("❌ 未抓取到数据，数据源返回为空")
            return None
        latest = data[0]
        issue = str(latest.get("no", "")).strip()
        ordered_nums = latest.get("drawnNo", [])
        special = latest.get("xDrawnNo", "")
        return issue, ordered_nums, special
    except Exception as e:
        print(f"❌ 获取数据失败: {e}")
        return None

def write_to_sheet(ws, issue, numbers_list):
    """将期数和号码写入第3行（强制插入新行）"""
    ws.insert_rows(3)
    
    issue_str = str(issue).strip()[-3:].zfill(3)  # 比如 117
    ws.cell(row=3, column=1).value = int(issue_str[0])
    ws.cell(row=3, column=2).value = int(issue_str[1])
    ws.cell(row=3, column=3).value = int(issue_str[2])
    
    current_col = 4
    for num in numbers_list:
        num_int = int(num)
        ws.cell(row=3, column=current_col).value = num_int // 10  # 十位
        ws.cell(row=3, column=current_col + 1).value = num_int % 10 # 个位
        current_col += 2

def process_excel(file_path, issue, numbers_list, file_desc):
    if not os.path.exists(file_path):
        print(f"❌ 找不到文件: {file_path}")
        return

    print(f"正在处理 {file_desc}...")
    # 注意：因为 GitHub 上处理 .xlsm 容易掉格式，如果你只是想纯更新数据，建议另存为 .xlsx 上传，并在这里改成 False
    wb = openpyxl.load_workbook(file_path, keep_vba=True)
    
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        
        print(f"🔥 强制将 {issue} 期数据写入 {file_desc} 的【{SHEET_NAME}】表...")
        write_to_sheet(ws, issue, numbers_list)
        try:
            wb.save(file_path)
            print(f"✅ {file_desc} 保存成功！")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
    else:
        print(f"⚠️ 在 {file_path} 中找不到工作表: {SHEET_NAME}")

def main():
    result = fetch_data()
    if not result:
        return
    
    issue, ordered_nums, special = result
    print(f"✅ 成功获取最新数据: {issue} 期")
    
    # 按序
    all_ordered = ordered_nums + [special]
    # 升序
    all_sorted = sorted([int(n) for n in ordered_nums]) + [special]

    process_excel(FILE_ORDERED, issue, all_ordered, "按序源文件")
    process_excel(FILE_SORTED, issue, all_sorted, "升序源文件")

if __name__ == "__main__":
    main()
