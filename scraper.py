import requests
import os
import openpyxl
from datetime import datetime

# =======================================================
# ⚙️ 配置区
# =======================================================
FILE_ORDERED = "按序源文件.xlsx"   
FILE_SORTED = "升序源文件.xlsx"    
SHEET_NAME = "数据源"              
# =======================================================

def fetch_data():
    # 🔥 核心修改：直接请求香港马会官方 GraphQL 接口
    url = "https://info.cld.hkjc.com/graphql/base/"
    query = """
    query marksixResult($lastNDraw: Int) {
      lotteryDraws(lastNDraw: $lastNDraw) {
        no
        drawDate
        drawResult {
          drawnNo
          xDrawnNo
        }
      }
    }
    """
    payload = {
        "operationName": "marksixResult",
        "variables": {"lastNDraw": 1},
        "query": query
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }
    
    try:
        print("正在连接香港马会官方数据源...")
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        draws = data.get("data", {}).get("lotteryDraws", [])
        if not draws:
            print("❌ 官方接口未返回数据")
            return None
            
        latest = draws[0]
        issue = str(latest.get("no", "")).strip()
        ordered_nums = latest.get("drawResult", {}).get("drawnNo", [])
        special = latest.get("drawResult", {}).get("xDrawnNo", "")
        
        return issue, ordered_nums, special
    except Exception as e:
        print(f"❌ 获取官方数据失败: {e}")
        return None

def process_excel(file_path, issue, numbers_list, file_desc):
    if not os.path.exists(file_path):
        print(f"❌ 找不到文件: {file_path}")
        return

    print(f"--- 开始处理: {file_desc} ---")
    try:
        wb = openpyxl.load_workbook(file_path)
    except Exception as e:
        print(f"❌ 打开失败: {e}")
        return
        
    if SHEET_NAME not in wb.sheetnames:
        print(f"❌ 找不到工作表: {SHEET_NAME}")
        return
        
    ws = wb[SHEET_NAME]
    
    # 拆解期数 (例如 2026120 -> 年份2026, 尾数120)
    issue_str = str(issue).strip()
    if len(issue_str) >= 7:
        year, tail = int(issue_str[:4]), issue_str[-3:]
    else:
        year, tail = 2026, issue_str.zfill(3)[-3:]
        
    print(f"✅ 正在写入 {issue} 期 | 年份:{year} 尾数:{tail}")
    
    # 插入新行到第3行
    ws.insert_rows(3)
    
    # 写入期数 (A, B, C 列)
    ws["A3"], ws["B3"], ws["C3"] = int(tail[0]), int(tail[1]), int(tail[2])
    # 写入年份 (AA 列)
    ws["AA3"] = year
    
    # 写入拆分的号码 (D, F, H, J, L, N, P 列是十位，后面一列是个位)
    cols = ["D", "F", "H", "J", "L", "N", "P"] 
    for i, num in enumerate(numbers_list):
        num_int = int(num)
        col_letter = cols[i]
        ws[f"{col_letter}3"] = num_int // 10  # 十位
        ws[f"{chr(ord(col_letter) + 1)}3"] = num_int % 10  # 个位
        
    try:
        wb.save(file_path)
        print(f"✅ {file_desc} 写入成功！")
    except Exception as e:
        print(f"❌ 保存失败: {e}")

def main():
    # 强制生成一个变动文件，防止 git 认为没有变化而不推送
    with open("trigger_test.txt", "w") as f:
        f.write(f"Last run at: {datetime.now()}")
        
    result = fetch_data()
    if not result:
        return
        
    issue, ordered_nums, special = result
    print(f"✅ 抓取到最新开奖: {issue}期 | 平码: {ordered_nums} | 特码: {special}")
    
    # 组合数据（前6个平码 + 第7个特码）
    all_ordered = ordered_nums + [special]
    all_sorted = sorted([int(n) for n in ordered_nums]) + [int(special)]

    process_excel(FILE_ORDERED, issue, all_ordered, "按序源文件")
    process_excel(FILE_SORTED, issue, all_sorted, "升序源文件")

if __name__ == "__main__":
    main()
