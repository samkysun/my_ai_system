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
    
    # 精准拆解期数和年份
    issue_str = str(issue).strip()
    if len(issue_str) >= 7:
        year = int(issue_str[:4]) # 提取前4位作为年份 (如 2026)
        tail = issue_str[-3:]     # 提取后3位 (如 117)
    else:
        year = 2026               # 兜底年份
        tail = issue_str.zfill(3)[-3:]
        
    # 写入期数到 A、B、C 列
    ws.cell(row=3, column=1).value = int(tail[0])
    ws.cell(row=3, column=2).value = int(tail[1])
    ws.cell(row=3, column=3).value = int(tail[2])
    
    # 写入年份到 AA 列（第 27 列）
    ws.cell(row=3, column=27).value = year
    
    # 写入号码到 D 列开始（拆分十位和个位）
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
    # 加载文件（保留宏）
    wb = openpyxl.load_workbook(file_path, keep_vba=True)
    
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        
        # 强制写入，绝不跳过
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
    print(f"原始平码数据: {ordered_nums}, 特码: {special}")
    
    # 1. 准备按序数据（按落球顺序，特码在最后）
    all_ordered = ordered_nums + [special]
    
    # 2. 准备升序数据（前6个平码强制升序排列，特码在最后）
    # 即使源头已经是升序，这里再排一次作为双保险
    all_sorted = sorted([int(n) for n in ordered_nums]) + [special]

    # 分别处理两个文件
    process_excel(FILE_ORDERED, issue, all_ordered, "按序源文件")
    process_excel(FILE_SORTED, issue, all_sorted, "升序源文件")

if __name__ == "__main__":
    main()
