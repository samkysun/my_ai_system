import requests
import os
import openpyxl

# =======================================================
# ⚙️ 配置区（已根据你的实际情况修改为两个独立文件）
# =======================================================
FILE_ORDERED = "按序源文件.xlsm"   # 按序 Excel 文件名
FILE_SORTED = "升序源文件.xlsm"    # 升序 Excel 文件名
SHEET_NAME = "数据源"              # 两个文件里都叫这个名字
# =======================================================

def fetch_data():
    # 使用 GitHub 上稳定的自动化数据源
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

def get_existing_issue(ws):
    """读取第3行的 A、B、C 列，拼出已存在的期数"""
    a = ws.cell(row=3, column=1).value
    b = ws.cell(row=3, column=2).value
    c = ws.cell(row=3, column=3).value
    if all(v is not None for v in [a, b, c]):
        try:
            return f"{int(a)}{int(b)}{int(c)}"
        except:
            return ""
    return ""

def write_to_sheet(ws, issue, numbers_list):
    """将期数和号码写入第3行（插入新行）"""
    # 插入新行，保持新数据在第 3 行
    ws.insert_rows(3)
    
    # 写入期数（A、B、C 列）
    issue_str = str(issue).strip()[-3:].zfill(3)  # 比如 117
    ws.cell(row=3, column=1).value = int(issue_str[0])
    ws.cell(row=3, column=2).value = int(issue_str[1])
    ws.cell(row=3, column=3).value = int(issue_str[2])
    
    # 写入号码（从 D 列即第4列开始，拆分十位和个位）
    current_col = 4
    for num in numbers_list:
        num_int = int(num)
        ws.cell(row=3, column=current_col).value = num_int // 10  # 十位
        ws.cell(row=3, column=current_col + 1).value = num_int % 10 # 个位
        current_col += 2

def process_excel(file_path, issue, numbers_list, file_desc):
    """通用的处理单个 Excel 文件的函数"""
    if not os.path.exists(file_path):
        print(f"❌ 找不到文件: {file_path}，请确保它和本脚本在同一个文件夹。")
        return

    print(f"正在处理 {file_desc}...")
    # 加载 Excel 文件（保留 VBA 宏）
    wb = openpyxl.load_workbook(file_path, keep_vba=True)
    
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        existing_issue = get_existing_issue(ws)
        
        # 判断第3行期数是否与最新期数一致，防止重复写入
        if existing_issue != issue[-3:]:
            print(f"正在将 {issue} 期数据写入 {file_path} 的【{SHEET_NAME}】表...")
            write_to_sheet(ws, issue, numbers_list)
            wb.save(file_path)
            print(f"✅ {file_desc} 更新成功！")
        else:
            print(f"⏭️ {file_desc} 第3行已是 {issue} 期，跳过更新。")
    else:
        print(f"⚠️ 在 {file_path} 中找不到工作表: {SHEET_NAME}")

def main():
    result = fetch_data()
    if not result:
        return
    
    issue, ordered_nums, special = result
    print(f"成功获取最新数据: {issue}期")
    
    # 1. 准备按序数据（直接拼接，特码在最后）
    all_ordered = ordered_nums + [special]
    
    # 2. 准备升序数据（前6个平码升序排列，特码在最后）
    all_sorted = sorted([int(n) for n in ordered_nums]) + [special]

    # 3. 分别处理两个独立的 Excel 文件
    process_excel(FILE_ORDERED, issue, all_ordered, "按序源文件")
    process_excel(FILE_SORTED, issue, all_sorted, "升序源文件")

if __name__ == "__main__":
    main()