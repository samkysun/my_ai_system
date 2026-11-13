import streamlit as st
import pandas as pd
import hashlib
import time

import os
import itertools
from collections import Counter
import requests
import openpyxl
import io       # 👈 新增
import base64   # 👈 新增

# ==========================================
# ⚙️ 配置区
# ==========================================
EXCEL_FILE = "数据分析系统最终版本(智能全套).xlsm"
SHEET_NAME = "总数据" 
USER_FILE = "users.csv"
# ==========================================
# 🔥 核心引擎：28个属性纯代码计算器 (绝对不遗漏版)
# ==========================================
NUM_WUXING = {1: "水", 2: "火", 3: "火", 4: "金", 5: "金", 6: "土", 7: "土", 8: "木", 9: "木", 10: "火", 11: "火", 12: "金", 13: "金", 14: "水", 15: "水", 16: "木", 17: "木", 18: "火", 19: "火", 20: "土", 21: "土", 22: "水", 23: "水", 24: "木", 25: "木", 26: "金", 27: "金", 28: "土", 29: "土", 30: "水", 31: "水", 32: "火", 33: "火", 34: "金", 35: "金", 36: "土", 37: "土", 38: "木", 39: "木", 40: "火", 41: "火", 42: "金", 43: "金", 44: "水", 45: "水", 46: "木", 47: "木", 48: "火", 49: "火"}
NUM_ZODIAC = {1: "马", 2: "蛇", 3: "龙", 4: "兔", 5: "虎", 6: "牛", 7: "鼠", 8: "猪", 9: "狗", 10: "鸡", 11: "猴", 12: "羊", 13: "马", 14: "蛇", 15: "龙", 16: "兔", 17: "虎", 18: "牛", 19: "鼠", 20: "猪", 21: "狗", 22: "鸡", 23: "猴", 24: "羊", 25: "马", 26: "蛇", 27: "龙", 28: "兔", 29: "虎", 30: "牛", 31: "鼠", 32: "猪", 33: "狗", 34: "鸡", 35: "猴", 36: "羊", 37: "马", 38: "蛇", 39: "龙", 40: "兔", 41: "虎", 42: "牛", 43: "鼠", 44: "猪", 45: "狗", 46: "鸡", 47: "猴", 48: "羊", 49: "马"}
NUM_HE = {1: "01合", 2: "02合", 3: "03合", 4: "04合", 5: "05合", 6: "06合", 7: "07合", 8: "08合", 9: "09合", 10: "01合", 11: "02合", 12: "03合", 13: "04合", 14: "05合", 15: "06合", 16: "07合", 17: "08合", 18: "09合", 19: "10合", 20: "02合", 21: "03合", 22: "05合", 23: "05合", 24: "06合", 25: "07合", 26: "08合", 27: "09合", 28: "10合", 29: "11合", 30: "03合", 31: "04合", 32: "05合", 33: "06合", 34: "07合", 35: "08合", 36: "09合", 37: "10合", 38: "11合", 39: "12合", 40: "04合", 41: "05合", 42: "06合", 43: "07合", 44: "08合", 45: "09合", 46: "10合", 47: "11合", 48: "12合", 49: "13合"}
NUM_MEN = {1: "1门", 2: "1门", 3: "1门", 4: "1门", 5: "1门", 6: "1门", 7: "1门", 8: "1门", 9: "1门", 10: "2门", 11: "2门", 12: "2门", 13: "2门", 14: "2门", 15: "2门", 16: "2门", 17: "2门", 18: "2门", 19: "2门", 20: "3门", 21: "3门", 22: "3门", 23: "3门", 24: "3门", 25: "3门", 26: "3门", 27: "3门", 28: "3门", 29: "3门", 30: "4门", 31: "4门", 32: "4门", 33: "4门", 34: "4门", 35: "4门", 36: "4门", 37: "4门", 38: "4门", 39: "4门", 40: "5门", 41: "5门", 42: "5门", 43: "5门", 44: "5门", 45: "5门", 46: "5门", 47: "5门", 48: "5门", 49: "5门"}
NUM_DUAN = {1: "1段", 2: "1段", 3: "1段", 4: "1段", 5: "1段", 6: "1段", 7: "1段", 8: "2段", 9: "2段", 10: "2段", 11: "2段", 12: "2段", 13: "2段", 14: "2段", 15: "3段", 16: "3段", 17: "3段", 18: "3段", 19: "3段", 20: "3段", 21: "3段", 22: "4段", 23: "4段", 24: "4段", 25: "4段", 26: "4段", 27: "4段", 28: "4段", 29: "5段", 30: "5段", 31: "5段", 32: "5段", 33: "5段", 34: "5段", 35: "5段", 36: "6段", 37: "6段", 38: "6段", 39: "6段", 40: "6段", 41: "6段", 42: "6段", 43: "7段", 44: "7段", 45: "7段", 46: "7段", 47: "7段", 48: "7段", 49: "7段"}
NUM_SINGLE_DOUBLE = {1: "双单", 2: "双双", 3: "双单", 4: "双双", 5: "双单", 6: "双双", 7: "双单", 8: "双双", 9: "双单", 10: "单双", 11: "单单", 12: "单双", 13: "单单", 14: "单双", 15: "单单", 16: "单双", 17: "单单", 18: "单双", 19: "单单", 20: "双双", 21: "双单", 22: "双双", 23: "双单", 24: "双双", 25: "双单", 26: "双双", 27: "双单", 28: "双双", 29: "双单", 30: "单双", 31: "单单", 32: "单双", 33: "单单", 34: "单双", 35: "单单", 36: "单双", 37: "单单", 38: "单双", 39: "单单", 40: "双双", 41: "双单", 42: "双双", 43: "双单", 44: "双双", 45: "双单", 46: "双双", 47: "双单", 48: "双双", 49: "双单"}
NUM_BOSE = {1: "红波", 2: "红波", 7: "红波", 8: "红波", 12: "红波", 13: "红波", 18: "红波", 19: "红波", 23: "红波", 24: "红波", 29: "红波", 30: "红波", 34: "红波", 35: "红波", 40: "红波", 45: "红波", 46: "红波", 3: "蓝波", 4: "蓝波", 9: "蓝波", 10: "蓝波", 14: "蓝波", 15: "蓝波", 20: "蓝波", 25: "蓝波", 26: "蓝波", 31: "蓝波", 36: "蓝波", 37: "蓝波", 41: "蓝波", 42: "蓝波", 47: "蓝波", 48: "蓝波", 5: "绿波", 6: "绿波", 11: "绿波", 16: "绿波", 17: "绿波", 21: "绿波", 22: "绿波", 27: "绿波", 28: "绿波", 32: "绿波", 33: "绿波", 38: "绿波", 39: "绿波", 43: "绿波", 44: "绿波", 49: "绿波"}
ZODIAC_WUXING = {"鼠": "水", "牛": "土", "虎": "木", "兔": "木", "龙": "土", "蛇": "火", "马": "火", "羊": "土", "猴": "金", "鸡": "金", "狗": "土", "猪": "水"}
ZODIAC_COLOR = {"鼠": "红色", "马": "红色", "鸡": "红色", "兔": "红色", "牛": "绿色", "羊": "绿色", "龙": "绿色", "狗": "绿色", "虎": "蓝色", "猴": "蓝色", "蛇": "蓝色", "猪": "蓝色"}
ZODIAC_FOUR_TREASURES = {"鼠": "棋", "牛": "棋", "狗": "棋", "鸡": "琴", "兔": "琴", "蛇": "琴", "马": "书", "虎": "书", "龙": "书", "猴": "画", "羊": "画", "猪": "画"}
ZODIAC_OBJECT_IMAGE = {"鼠": "恶人", "猴": "恶人", "牛": "家臣", "狗": "家臣", "马": "家臣", "猪": "家臣", "鸡": "美女", "兔": "美女", "蛇": "美女", "羊": "美女", "虎": "君王", "龙": "君王"}
YANG_ZODIACS = ["牛", "虎", "兔", "羊", "猴", "鸡"]
JIA_ZODIACS = ["牛", "马", "羊", "鸡", "狗", "猪"]
TIAN_ZODIACS = ["牛", "兔", "龙", "马", "猴", "猪"]
XIONG_ZODIACS = ["鼠", "牛", "虎", "猴", "狗", "猪"]
NAN_ZODIACS = ["鼠", "牛", "虎", "龙", "马", "猴", "狗"]
ZODIAC_DIRECTION = {"鼠": "北", "牛": "北", "猪": "北", "虎": "东", "兔": "东", "龙": "东", "马": "南", "蛇": "南", "羊": "南", "猴": "西", "鸡": "西", "狗": "西"}
TAIL_WUXING = {0: "土", 5: "土", 2: "火", 7: "火", 1: "水", 6: "水", 3: "木", 8: "木", 4: "金", 9: "金"}
ZODIAC_FU_LU_SHOU = {"鼠": "福肖", "马": "福肖", "虎": "福肖", "龙": "福肖", "牛": "禄肖", "兔": "禄肖", "猴": "禄肖", "猪": "禄肖", "狗": "寿肖", "鸡": "寿肖", "蛇": "寿肖", "羊": "寿肖"}
ZODIAC_SIZE = {"鼠": "小肖", "鸡": "小肖", "兔": "小肖", "蛇": "小肖", "牛": "大肖", "马": "大肖", "虎": "大肖", "龙": "大肖", "狗": "中肖", "猴": "中肖", "羊": "中肖", "猪": "中肖"}

def calculate_all_attributes(num):
    if not num: return [""] * 28
    n = int(num)
    z = NUM_ZODIAC.get(n, "")
    tail = n % 10
    return [
        NUM_WUXING.get(n, ""), 
        z, 
        str(tail), 
        NUM_HE.get(n, ""), 
        NUM_MEN.get(n, ""), 
        NUM_DUAN.get(n, ""), 
        NUM_SINGLE_DOUBLE.get(n, ""), 
        "单笔" if z in ["鼠", "龙", "蛇", "马", "鸡", "猪"] else "双笔",
        "独字" if z in ["鼠", "牛", "虎", "兔", "马", "羊"] else "合字",
        "单头" if (n // 10) in [1, 3] else "双头",
        "单数" if n % 2 != 0 else "双数",
        f"{NUM_BOSE.get(n, '')}{'单数' if n % 2 != 0 else '双数'}",
        ZODIAC_WUXING.get(z, ""), 
        ZODIAC_COLOR.get(z, ""), 
        ZODIAC_FOUR_TREASURES.get(z, ""), 
        ZODIAC_OBJECT_IMAGE.get(z, ""), 
        NUM_BOSE.get(n, ""), 
        "阳" if z in YANG_ZODIACS else "阴", 
        "家" if z in JIA_ZODIACS else "野", 
        "天" if z in TIAN_ZODIACS else "地", 
        f"{'阳' if z in YANG_ZODIACS else '阴'}{'天' if z in TIAN_ZODIACS else '地'}", 
        "凶" if z in XIONG_ZODIACS else "吉", 
        "男" if z in NAN_ZODIACS else "女", 
        ZODIAC_DIRECTION.get(z, ""), 
        f"3余{tail % 3}", 
        TAIL_WUXING.get(tail, ""), 
        ZODIAC_FU_LU_SHOU.get(z, ""), 
        ZODIAC_SIZE.get(z, "")
    ]
# ==========================================
st.set_page_config(page_title="智能数据分析系统", layout="wide")

# 🔐 从 Streamlit Secrets 中安全读取密钥（彻底删除了写死的密钥）
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]

st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 100%); }
    h1, h2, h3 { color: #102A43 !important; }
    .stButton>button { background: linear-gradient(90deg, #0284c7 0%, #0369a1 100%); color: white; border-radius: 6px; border: none; font-weight: bold; }
    .ball-container { display: flex; gap: 12px; justify-content: center; margin: 20px 0; }
    .ball { width: 55px; height: 55px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold; color: white; box-shadow: 2px 4px 8px rgba(0,0,0,0.3); }
    .ball-red { background: radial-gradient(circle at 30% 30%, #fca5a5, #dc2626); }
    .ball-blue { background: radial-gradient(circle at 30% 30%, #93c5fd, #2563eb); }
    .ball-green { background: radial-gradient(circle at 30% 30%, #86efac, #16a34a); }
    .ball-special { background: radial-gradient(circle at 30% 30%, #fde047, #ca8a04); border: 2px solid #fff; }
</style>
""", unsafe_allow_html=True)

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "synced_df" not in st.session_state: st.session_state.synced_df = None
if "calc_data_single" not in st.session_state: st.session_state.calc_data_single = None
if "calc_data_multi" not in st.session_state: st.session_state.calc_data_multi = None
if "calc_result_preview" not in st.session_state: st.session_state.calc_result_preview = None
if "predicted_nums_single" not in st.session_state: st.session_state.predicted_nums_single = None
if "predicted_nums_multi" not in st.session_state: st.session_state.predicted_nums_multi = None

def load_users():
    import requests
    import io
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    
    # 如果没配置 Secrets，退回本地（用于你本地调试）
    if not token or not repo:
        if not os.path.exists(USER_FILE):
            pd.DataFrame(columns=['username', 'password']).to_csv(USER_FILE, index=False)
        return pd.read_csv(USER_FILE)
        
    try:
        url = f"https://api.github.com/repos/{repo}/contents/users.csv"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            download_url = r.json()["download_url"]
            content = requests.get(download_url).content
            return pd.read_csv(io.BytesIO(content))
        else:
            return pd.DataFrame(columns=['username', 'password'])
    except:
        return pd.DataFrame(columns=['username', 'password'])    
def get_ball_color(num):
    red = [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46]
    blue = [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48]
    if num in red: return "ball-red"
    elif num in blue: return "ball-blue"
    else: return "ball-green"

def clean_period(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    if s.endswith(".0"): s = s[:-2]
    return s
    
@st.cache_data(ttl=60, show_spinner=False) 
def load_real_data():
    import requests
    import io
    
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    
    file_name = "升序源文件.xlsx"
    
    if not token or not repo:
        if not os.path.exists(file_name): return None
        try:
            df_raw = pd.read_excel(file_name, sheet_name="数据源", header=None)
        except Exception as e:
            return str(e)
    else:
        try:
            url = f"https://api.github.com/repos/{repo}/contents/{file_name}"
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                download_url = r.json()["download_url"]
                content = requests.get(download_url).content
                df_raw = pd.read_excel(io.BytesIO(content), sheet_name="数据源", header=None)
            else:
                return "云端源文件读取失败"
        except Exception as e:
            return str(e)

    try:
        synced_rows = []
        
        def clean_val(v):
            if pd.isna(v): return ""
            try: return str(int(float(v)))
            except: return str(v).strip()
            
        for idx, row in df_raw.iterrows():
            year_val = clean_val(row[26]) if len(row) > 26 else ""
            p1 = clean_val(row[0])
            p2 = clean_val(row[1])
            p3 = clean_val(row[2])
            
            if not year_val.isdigit() or not p1.isdigit():
                continue
                
            period_str = f"{year_val}{p1}{p2}{p3}"
            
            nums = []
            for i in range(7):
                tens = clean_val(row[3 + i*2])
                units = clean_val(row[4 + i*2])
                if tens == "" and units == "":
                    nums.append(None)
                else:
                    t = tens if tens.isdigit() else "0"
                    u = units if units.isdigit() else "0"
                    nums.append(int(t + u))
                    
            new_row = [None] * 30
            new_row[18] = period_str
            for i in range(6): new_row[19+i] = nums[i]
            new_row[25] = nums[6]
            
            synced_rows.append(new_row)
            
        result_df = pd.DataFrame(synced_rows)
        
        try:
            result_df = result_df.sort_values(by=18, ascending=False).reset_index(drop=True)
        except:
            pass
            
        return result_df
    except Exception as e:
        return f"数据转换异常: {e}"
def generate_20_combos(nums):
    combos = list(itertools.combinations(nums, 3))
    return [",".join([str(x).zfill(2) for x in c]) for c in combos]

def calculate_linkage(df_data, target_period, mode):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: return None, None, "未找到该期数据"
    base_idx = matched.index[0]
    current_row = matched.iloc[0]
    base_nums = [int(clean_period(current_row.iloc[i])) for i in range(19, 25) if pd.notna(current_row.iloc[i]) and clean_period(current_row.iloc[i]) != ""]
    special_num = int(clean_period(current_row.iloc[25])) if pd.notna(current_row.iloc[25]) and clean_period(current_row.iloc[25]) != "" else None
    if len(base_nums) < 6: return None, None, "基准期开奖号码不足6个"
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    if is_descending: start_idx, end_idx = base_idx + 1, len(df_data) - 1
    else: start_idx, end_idx = 0, base_idx - 1
    if start_idx > end_idx: return None, None, "基准期附近没有可匹配的历史数据"
    triggers, total_counter = [], Counter()
    if mode == "单排分析":
        combos_str = generate_20_combos(base_nums)
        for idx in range(start_idx, end_idx + 1):
            row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
            row_period = clean_period(df_data.iloc[idx, 18])
            for combo_str in combos_str:
                combo = [int(x) for x in combo_str.split(",")]
                if all(n in row_nums for n in combo):
                    triggers.append({"组合": combo_str, "触发行": idx + 1, "触发期数": row_period, "触发行号码": ",".join([f"{n:02d}" for n in row_nums])})
                    next_idx = idx - 1 if is_descending else idx + 1
                    if 0 <= next_idx < len(df_data):
                        next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                        for n in next_row_nums: total_counter[n] += 1
    else:
        dict_history = set() 
        for i in range(7):
            current_base = list(base_nums)
            if i >= 1 and special_num is not None: current_base[i-1] = special_num
            if len(current_base) < 6: continue
            new_combos = generate_20_combos(current_base)
            valid_combos = [c for c in new_combos if c not in dict_history]
            for c in valid_combos: dict_history.add(c)
            if not valid_combos: continue
            for idx in range(start_idx, end_idx + 1):
                row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
                row_period = clean_period(df_data.iloc[idx, 18])
                for combo_str in valid_combos:
                    combo = [int(x) for x in combo_str.split(",")]
                    if all(n in row_nums for n in combo):
                        triggers.append({"组合": combo_str, "触发行": idx + 1, "触发期数": row_period, "触发行号码": ",".join([f"{n:02d}" for n in row_nums])})
                        next_idx = idx - 1 if is_descending else idx + 1
                        if 0 <= next_idx < len(df_data):
                            next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                            for n in next_row_nums: total_counter[n] += 1
    sorted_counts = sorted(total_counter.items(), key=lambda x: x[1], reverse=True)
    df_triggers = pd.DataFrame(triggers) if triggers else pd.DataFrame(columns=["组合", "触发行", "触发期数", "触发行号码"])
    df_counts = pd.DataFrame([{"下期数字": f"{n:02d}", "出现次数": c} for n, c in sorted_counts])
    return df_triggers, df_counts, None

def calculate_prize(df_data, target_period, predicted_nums):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: return None, f"总数据里找不到本期 {target_period}！"
    base_pos = df_data.index.get_loc(matched.index[0])
    next_pos = base_pos - 1
    if next_pos < 0: return {"下期期数": "待开奖", "预测组合": ",".join(predicted_nums), "状态": "本期开奖数据未更新"}, "本期开奖数据未更新"
    next_row = df_data.iloc[next_pos]
    next_period = clean_period(next_row.iloc[18])
    if not next_period: return {"下期期数": "待开奖", "预测组合": ",".join(predicted_nums), "状态": "本期开奖数据未更新"}, "本期开奖数据未更新"
    nums = [clean_period(next_row.iloc[i]) for i in range(19, 25)]
    z_val = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    match_nums = []
    for n in nums:
        if n and n in predicted_nums and n not in match_nums: match_nums.append(n)
    try: match_nums.sort(key=lambda x: int(x))
    except: pass
    z_matched = z_val in predicted_nums if z_val else False
    status = "有命中" if (len(match_nums) > 0 or z_matched) else "本期无中任何数字"
    result = {
        "下期期数": next_period, "预测组合": ",".join(predicted_nums),
        "中出平码1": match_nums[0] if len(match_nums) > 0 else "", "中出平码2": match_nums[1] if len(match_nums) > 1 else "",
        "中出平码3": match_nums[2] if len(match_nums) > 2 else "", "中出平码4": match_nums[3] if len(match_nums) > 3 else "",
        "中出平码5": match_nums[4] if len(match_nums) > 4 else "", "中出平码6": match_nums[5] if len(match_nums) > 5 else "",
        "中出特码": z_val if z_matched else "", "状态": status
    }
    return result, None
def login_page():
    st.title("🔐 智能系统客户端登录")
    
    if st.session_state.get("reg_success", False):
        st.success("✅ 注册成功！请去左侧登录。")
        st.session_state.reg_success = False

    tab1, tab2 = st.tabs(["登录", "注册新账号"])
    
    if "reg_version" not in st.session_state:
        st.session_state.reg_version = 0
    v = st.session_state.reg_version
    
    with tab1:
        user = st.text_input("用户名", key="login_user")
        pwd = st.text_input("密码", type="password", key="login_pass")
        if st.button("登录", use_container_width=True):
            if user and pwd:
                user_clean = user.strip()
                pwd_clean = pwd.strip()
                
                # 🔥 核心：管理员 VIP 直通车逻辑
                admin_name = st.secrets.get("ADMIN_USERNAME", "admin") # 默认 admin
                admin_pass = st.secrets.get("ADMIN_PASSWORD", "123456") # 建议你去 Secrets 里设个真密码
                
                is_admin = False
                if user_clean == admin_name:
                    if pwd_clean == admin_pass or hashlib.sha256(pwd_clean.encode()).hexdigest() == admin_pass:
                        st.session_state.logged_in = True
                        st.session_state.username = user_clean
                        is_admin = True
                        st.rerun()
                
                # 如果上面没进管理员通道，再走普通用户通道
                if not is_admin:
                    users_df = load_users()
                    users_df['username'] = users_df['username'].astype(str).str.strip()
                    users_df['password'] = users_df['password'].astype(str).str.strip()
                    
                    hashed = hashlib.sha256(pwd_clean.encode()).hexdigest()
                    match = users_df[(users_df['username'] == user_clean) & (users_df['password'] == hashed)]
                    
                    if not match.empty:
                        st.session_state.logged_in = True
                        st.session_state.username = user_clean
                        st.rerun()
                    else: 
                        st.error("用户名或密码错误！(可能账号未成功保存，请重新注册)")
                
    with tab2:
        # 下面是原来的注册代码，原封不动放这里
        reg_user = st.text_input("设置用户名", key=f"v{v}_reg_user")
        reg_pwd = st.text_input("设置密码", type="password", key=f"v{v}_reg_pass")
        reg_confirm = st.text_input("确认密码", type="password", key=f"{v}_reg_confirm")
        
        if st.button("注册", use_container_width=True):
            reg_user_clean = reg_user.strip()
            reg_pwd_clean = reg_pwd.strip()
            
            if reg_user_clean and reg_pwd_clean:
                if reg_pwd_clean != reg_confirm.strip(): 
                    st.error("两次密码不一致")
                else:
                    users_df = load_users()
                    if reg_user_clean in users_df['username'].values: 
                        st.error("该用户名已被注册")
                    else:
                        # 注册新用户的逻辑（这里保持你刚才的代码就行）
                        new_user = pd.DataFrame({'username': [reg_user_clean], 'password': [hashlib.sha256(reg_pwd_clean.encode()).hexdigest()]})
                        updated_df = pd.concat([users_df, new_user], ignore_index=True)
                        
                        token = st.secrets.get("GITHUB_TOKEN")
                        repo = st.secrets.get("GITHUB_REPO")
                        
                        if token and repo:
                            import requests
                            import io
                            import base64
                            
                            try:
                                url = f"https://api.github.com/repos/{repo}/contents/users.csv"
                                headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                                r = requests.get(url, headers=headers)
                                sha = r.json()["sha"] if r.status_code == 200 else None
                                
                                out = io.StringIO()
                                updated_df.to_csv(out, index=False)
                                b64_content = base64.b64encode(out.getvalue().encode('utf-8')).decode('utf-8')
                                
                                payload = {"message": f"新用户注册: {reg_user_clean}", "content": b64_content, "branch": "main"}
                                if sha: payload["sha"] = sha
                                
                                res = requests.put(url, headers=headers, json=payload)
                                
                                if res.status_code in [200, 201]:
                                    st.session_state.reg_success = True
                                    st.session_state.reg_version += 1
                                    st.rerun()
                                else:
                                    st.error(f"❌ 注册失败，状态码: {res.status_code}")
                            except Exception as e:
                                st.error(f"❌ 异常: {e}")            

def render_console(df_data):
    # 👇 导入模块
    import requests
    import openpyxl
    import io
    import base64
    
    # 只保留一个标题
    st.title("智能数据分析总控台")
    
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：" + str(EXCEL_FILE))
        return
        
    unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
    try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    except: unique_periods.sort(reverse=True)
    
    # 自动推算下一期并置顶
    if unique_periods:
        latest_period = unique_periods[0]
        try:
            next_period = str(int(float(latest_period)) + 1)
            if next_period not in unique_periods:
                unique_periods.insert(0, next_period)
        except:
            pass
    
    # 这里只创建一组两列，绝不会出现两个下拉框
    col1, col2 = st.columns(2)
    with col1: 
        selected_period = st.selectbox("选择期数：", unique_periods)
    with col2: 
        analysis_mode = st.radio("模式切换：", ["单排分析", "多排分析"], horizontal=True)    
    
    
    st.write("") 
    
    # ==========================================
    # 1. 按钮布局 (增加了抓取按钮，去除了 Emoji)
    # ==========================================
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    start_btn = b1.button("批量联动分析", use_container_width=True, type="primary")
    result_btn = b2.button("中奖结果", use_container_width=True)
    clear_btn = b3.button("清空数据", use_container_width=True)
    sync_btn = b4.button("同步数据", use_container_width=True)
    trend_btn = b5.button("走势图", use_container_width=True)
    fetch_btn = b6.button("抓取香港数据", use_container_width=True)

    # ==========================================
    # ?? 管理员专属：云端数据录入与同步
    # ==========================================
    # 读取 Secrets 里的管理员用户名，如果没有配置，默认叫 "admin"
    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    
    # 只有当前登录的用户名和 Secrets 里一致，才显示录入面板
    if st.session_state.username == admin_name:
        with st.expander("📝管理员专属：手动补录开奖数据 (云端同步)", expanded=False):
            with st.form("manual_input_form", clear_on_submit=True):
                st.info("💡提示：保存后，数据将直接更新到 GitHub 云端的两个 Excel 源文件中，并插入第 3 行。")
                
                col_year, col_p1, col_p2, col_p3 = st.columns(4)
                with col_year: year_val = st.text_input("年份 (AA列)", value="2026")
                with col_p1: p1 = st.text_input("A列 (百位)", value="1")
                with col_p2: p2 = st.text_input("B列 (十位)", value="1")
                with col_p3: p3 = st.text_input("C列 (个位)", value="8")
                
                st.write("---")
                col_nums = st.columns(7)
                nums = []
                for i in range(7):
                    label = "特码 (第7球)" if i == 6 else f"平码{i+1}"
                    with col_nums[i]:
                        n = st.number_input(label, min_value=1, max_value=49, value=i+1, key=f"manual_num_{i}")
                        nums.append(n)
                        
                submit_btn = st.form_submit_button("💾保存并同步到云端两个文件", use_container_width=True, type="primary")
    
                if submit_btn:
                    if not year_val or not p1 or not p2 or not p3:
                        st.error("年份和期号不能为空！")
                    elif len(set(nums)) < 7:
                        st.error("录入的 7 个号码中有重复，请检查！")
                    else:
                        # 1. 准备数据 (按序 和 升序)
                        raw_nums = nums.copy()
                        asc_nums = sorted(nums[:6]) + [nums[6]]
                        
                        # 2. 获取 GitHub 配置
                        token = st.secrets.get("GITHUB_TOKEN")
                        repo = st.secrets.get("GITHUB_REPO") 
                        
                        if not token or not repo:
                            st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                        else:
                            # 3. 核心函数：拉取 -> 修改 -> 推送 GitHub
                            def update_github_excel(file_path, nums_list, commit_msg):
                                # 🔥 核心修复：必须在这里加一遍，打破 Streamlit 的作用域魔咒
                                import requests
                                import openpyxl
                                import io
                                import base64
                                try:
                                    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
                                    headers = {
                                        "Authorization": f"Bearer {token}",
                                        "Accept": "application/vnd.github.v3+json"
                                    }
                                    
                                    # 3.1 获取文件的 SHA 和下载链接
                                    r = requests.get(api_url, headers=headers)
                                    if r.status_code != 200:
                                        return False, f"找不到云端文件或API错误: {r.status_code}"
                                    
                                    file_info = r.json()
                                    sha = file_info["sha"]
                                    download_url = file_info["download_url"]
                                    
                                    # 3.2 从云端下载现有 Excel
                                    file_content = requests.get(download_url).content
                                    
                                    # 3.3 在内存中操作 openpyxl
                                    wb = openpyxl.load_workbook(io.BytesIO(file_content))
                                    if "数据源" not in wb.sheetnames:
                                        return False, "源文件中找不到“数据源”工作表"
                                    ws = wb["数据源"]
                                    
                                    # 🔥 新增：拦截重复期号（结合 AA 列年份）
                                    def get_cell_str(r, c):
                                        v = ws.cell(row=r, column=c).value
                                        if v is None: return ""
                                        return str(v).replace(".0", "").strip()
                                        
                                    current_year = str(year_val).replace(".0", "").strip()
                                    
                                    for row_idx in range(3, ws.max_row + 1):
                                        r_p1 = get_cell_str(row_idx, 1)
                                        r_p2 = get_cell_str(row_idx, 2)
                                        r_p3 = get_cell_str(row_idx, 3)
                                        r_year = get_cell_str(row_idx, 27)
                                        
                                        if r_year == current_year and r_p1 == p1 and r_p2 == p2 and r_p3 == p3:
                                            return False, f"{current_year}年的 {p1}-{p2}-{p3} 期已经存在，禁止重复录入！"
                                    
                                    # 3.4 强制在第 3 行插入空白行
                                    ws.insert_rows(3)
                                    
                                    # 3.5 写入期号 (A, B, C 列)
                                    ws.cell(row=3, column=1, value=p1)
                                    ws.cell(row=3, column=2, value=p2)
                                    ws.cell(row=3, column=3, value=p3)
                                    
                                    # 3.6 写入年份 (AA列 第27列)
                                    ws.cell(row=3, column=27, value=year_val)
                                    
                                    # 3.7 写入7个号码
                                    for i, num in enumerate(nums_list):
                                        tens = num // 10
                                        units = num % 10
                                        col_tens = 4 + i*2
                                        col_units = 5 + i*2
                                        ws.cell(row=3, column=col_tens, value=str(tens))
                                        ws.cell(row=3, column=col_units, value=str(units))
                                    
                                    # 3.8 保存到内存字节流
                                    output = io.BytesIO()
                                    wb.save(output)
                                    b64_content = base64.b64encode(output.getvalue()).decode('utf-8')
                                    
                                    # 3.9 推送到 GitHub (覆盖原文件)
                                    payload = {
                                        "message": commit_msg,
                                        "content": b64_content,
                                        "sha": sha,
                                        "branch": "main" # ?? 如果你的分支叫 master，请改成 master
                                    }
                                    
                                    put_res = requests.put(api_url, headers=headers, json=payload)
                                    
                                    if put_res.status_code in [200, 201]:
                                        return True, "成功"
                                    else:
                                        return False, f"推送失败: {put_res.text}"
                                        
                                except Exception as e:
                                    return False, str(e)
    
                            # 4. 执行双写
                            with st.spinner("正在覆盖更新 GitHub 云端的两个 Excel 文件..."):
                                # 先更新升序源文件
                                s1, m1 = update_github_excel("升序源文件.xlsx", asc_nums, f"更新升序数据 {year_val}-{p1}{p2}{p3}")
                                # 再更新按序源文件
                                s2, m2 = update_github_excel("按序源文件.xlsx", raw_nums, f"更新按序数据 {year_val}-{p1}{p2}{p3}")
                                
                                if s1 and s2:
                                    st.success("✅数据已永久存入 GitHub 云端！")
                                    st.info("👉云端数据已刷新，请点击上方【同步数据】按钮重新加载。")
                                    load_real_data.clear()
                                else:
                                    if not s1: st.error(f"? 升序文件同步失败: {m1}")
                                    if not s2: st.error(f"? 按序文件同步失败: {m2}")
    
    st.divider()
   
    
    
    # ==========================================
    # 🔥 管理员专属：云端数据流转控制台
    # ==========================================
    if st.session_state.username == admin_name:
        st.markdown("### ☁️ 云端数据流转 (管理员操作)")
        
        col_sync1, col_sync2 = st.columns(2)
        
        with col_sync1:
            if st.button("🚀 同步【升序源文件】至【主总数据表】", use_container_width=True, type="primary"):
                with st.spinner("正在合并总表..."):
                    token = st.secrets.get("GITHUB_TOKEN")
                    repo = st.secrets.get("GITHUB_REPO")
                    if not token or not repo:
                        st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        try:
                            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                            def get_info(fp):
                                r = requests.get(f"https://api.github.com/repos/{repo}/contents/{fp}", headers=headers)
                                return r.json() if r.status_code == 200 else None
                            
                            src_info = get_info("升序源文件.xlsx")
                            if not src_info: st.error("找不到升序源文件"); st.stop()
                            df_src = pd.read_excel(io.BytesIO(requests.get(src_info["download_url"]).content), sheet_name="数据源", header=None)
                            
                            m_file = "数据分析系统最终版本(智能全套).xlsm"
                            m_info = get_info(m_file)
                            if not m_info: st.error("找不到主文件"); st.stop()
                            wb = openpyxl.load_workbook(io.BytesIO(requests.get(m_info["download_url"]).content), keep_vba=True)
                            ws = wb["总数据"]
                            if ws.max_row > 1: ws.delete_rows(2, ws.max_row)
                                
                            def clean_val(v):
                                if pd.isna(v) or v is None: return ""
                                try: return str(int(float(v)))
                                except: return str(v).strip()
                                
                            row_idx = 2
                            for idx, row in df_src.iterrows():
                                if idx < 2: continue
                                p1, p2, p3 = clean_val(row[0]), clean_val(row[1]), clean_val(row[2])
                                if not p1 and not p2 and not p3: continue
                                y_val = clean_val(row[26]) if len(row) > 26 else "2026"
                                
                                ws.cell(row=row_idx, column=19, value=f"{y_val}{p1}{p2}{p3}")
                                for i in range(6):
                                    t, u = clean_val(row[3 + i*2]), clean_val(row[4 + i*2])
                                    num = int(t)*10 + int(u) if t.isdigit() and u.isdigit() else (int(t) if t.isdigit() else 0)
                                    ws.cell(row=row_idx, column=20 + i, value=num)
                                t, u = clean_val(row[15]), clean_val(row[16])
                                z_num = int(t)*10 + int(u) if t.isdigit() and u.isdigit() else (int(t) if t.isdigit() else 0)
                                ws.cell(row=row_idx, column=26, value=z_num)
                                row_idx += 1
                                
                            out = io.BytesIO()
                            wb.save(out)
                            res = requests.put(f"https://api.github.com/repos/{repo}/contents/{m_file}", headers=headers, json={"message": "自动更新总数据", "content": base64.b64encode(out.getvalue()).decode('utf-8'), "sha": m_info["sha"], "branch": "main"})
                            if res.status_code in [200, 201]:
                                st.success("✅ 主总数据表已更新！")
                                load_real_data.clear()
                            else: st.error(f"❌ 推送失败: {res.text}")
                        except Exception as e: st.error(f"异常: {e}")
    
        with col_sync2:
            if st.button("🚀 一键计算属性并同步全套表", use_container_width=True, type="secondary"):
                with st.spinner("正在启动超级宏引擎，精准填入第三行属性..."):
                    
                    token = st.secrets.get("GITHUB_TOKEN")
                    repo = st.secrets.get("GITHUB_REPO")
                    
                    if not token or not repo:
                        st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        try:
                            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                            
                            def get_info(fp):
                                r = requests.get(f"https://api.github.com/repos/{repo}/contents/{fp}", headers=headers)
                                return r.json() if r.status_code == 200 else None
                            
                            def sync_attrs(src_f, dst_f, sheet):
                                # 1. 拉取最新数字
                                s_info = get_info(src_f)
                                if not s_info: return False, f"找不到 {src_f}"
                                wb_src = openpyxl.load_workbook(io.BytesIO(requests.get(s_info["download_url"]).content), data_only=True)
                                ws_src = wb_src["数据源"]
                                
                                # 2. 拉取全套表
                                d_info = get_info(dst_f)
                                if not d_info: return False, f"找不到 {dst_f}"
                                wb_dst = openpyxl.load_workbook(io.BytesIO(requests.get(d_info["download_url"]).content))
                                ws_dst = wb_dst[sheet]
                                
                                # ========================================================
                                # ?? 新增：防重复校验
                                # ========================================================
                                def get_clean_val(cell):
                                    if cell is None: return ""
                                    val = str(cell).strip()
                                    if val.endswith(".0"): val = val[:-2]
                                    return val
                            
                                src_a = get_clean_val(ws_src["A3"].value)
                                src_b = get_clean_val(ws_src["B3"].value)
                                src_c = get_clean_val(ws_src["C3"].value)
                                src_aa = get_clean_val(ws_src["AA3"].value)
                            
                                dst_a = get_clean_val(ws_dst["A3"].value)
                                dst_b = get_clean_val(ws_dst["B3"].value)
                                dst_c = get_clean_val(ws_dst["C3"].value)
                                dst_hf = get_clean_val(ws_dst["HF3"].value)
                            
                                if src_a == dst_a and src_b == dst_b and src_c == dst_c and src_aa == dst_hf:
                                    return True, f"该期数据已存在 (年份:{src_aa} 期数:{src_a}-{src_b}-{src_c})，已跳过同步"
                                # ========================================================
                            
                                # 3. 插入新的第 3 行
                                ws_dst.insert_rows(3)
                                
                                # 4. 把最新的数字和期数填入第 3 行 (?? 加上 A, B, C 列)
                                mapping = {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E', 'F': 'AH', 'G': 'AI', 'H': 'BL', 'I': 'BM', 'J': 'CP', 'K': 'CQ', 'L': 'DT', 'M': 'DU', 'N': 'EX', 'O': 'EY', 'P': 'GB', 'Q': 'GC', 'AA': 'HF'}
                                for sc, dc in mapping.items():
                                    val = ws_src[f"{sc}3"].value
                                    ws_dst[f"{dc}3"] = val if val is not None else ""
                                
                                # 5. 提取这 7 个球的数字 (?? 修复列偏移为 30)
                                ball_nums = []
                                for n in range(7):
                                    tens = ws_dst.cell(row=3, column=4 + n*30).value
                                    units = ws_dst.cell(row=3, column=5 + n*30).value
                                    
                                    if tens is None and units is None: 
                                        ball_nums.append(None)
                                    else:
                                        t = str(int(tens)) if str(tens).isdigit() else "0"
                                        u = str(int(units)) if str(units).isdigit() else "0"
                                        ball_nums.append(int(t + u))
                                
                                # 6. 填入 1-7 球属性
                                for n_idx, ball_num in enumerate(ball_nums):
                                    if ball_num:
                                        attrs = calculate_all_attributes(ball_num)
                                        for j_idx, attr_val in enumerate(attrs):
                                            target_col = 6 + j_idx + (n_idx * 30)
                                            ws_dst.cell(row=3, column=target_col, value=attr_val)
                                
                                # 7. 保存并推送
                                out = io.BytesIO()
                                wb_dst.save(out)
                                res = requests.put(f"https://api.github.com/repos/{repo}/contents/{dst_f}", 
                                                   headers=headers, 
                                                   json={"message": f"更新属性 {sheet}", "content": base64.b64encode(out.getvalue()).decode('utf-8'), "sha": d_info["sha"], "branch": "main"})
                                
                                if res.status_code in [200, 201]: return True, "成功"
                                return False, res.text
    
                            s1, m1 = sync_attrs("升序源文件.xlsx", "升序全套.xlsx", "升序全套分析")
                            s2, m2 = sync_attrs("按序源文件.xlsx", "按序全套.xlsx", "按序全套分析")
                            
                            if s1 and s2:
                                st.success(f"✅ 极速同步成功！\\n升序：{m1}\\n按序：{m2}")
                                
                                # 👇 👇 就是这里，加上这一行代码 👇 👇
                                load_excel_data.clear() 
                                # 👆 👆 清除网页内存中的旧表格 👆 👆
                                
                                if m1 == "成功" or m2 == "成功":
                                    st.info("👉 请点上方【同步数据】刷新网页！")
                            else:
                                if not s1: st.error(f"❌ 升序失败: {m1}")
                                if not s2: st.error(f"❌ 按序失败: {m2}")
                        except Exception as e:
                            st.error(f"运行异常: {e}")    


    
    st.divider()
    
    df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
    matched_rows = df_data[df_data['_temp_period'] == selected_period]
    # ... 后面的代码保持不变 ...
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    
    next_period_str, next_flat_nums, next_special_num, has_next_data = "", [], 0, False
    if not matched_rows.empty:
        base_idx = matched_rows.index[0]
        next_idx = base_idx - 1 if is_descending else base_idx + 1
        if 0 <= next_idx < len(df_data):
            next_row = df_data.iloc[next_idx]
            next_period_str = clean_period(next_row.iloc[18])
            try:
                next_flat_nums = [int(clean_period(next_row.iloc[i])) for i in range(19, 25) if pd.notna(next_row.iloc[i])]
                next_special_num = int(clean_period(next_row.iloc[25])) if pd.notna(next_row.iloc[25]) else 0
                if len(next_flat_nums) > 0: has_next_data = True
            except: pass
            
    if has_next_data:
        st.subheader(f"{next_period_str} 期开奖结果")
        balls_html = '<div class="ball-container">'
        for num in next_flat_nums: balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
        if next_special_num > 0: balls_html += f'<div class="ball {get_ball_color(next_special_num)} ball-special">★ {next_special_num:02d}</div>'
        balls_html += '</div>'
        st.markdown(balls_html, unsafe_allow_html=True)
    else:
        try: next_period_str = str(int(float(selected_period)) + 1)
        except: next_period_str = "下一期"
        st.subheader(f"{next_period_str} 期开奖结果")
        st.info(f"{next_period_str} 期待开奖（暂无数据）")

    # ==========================================
    # 2. 抓取香港数据逻辑 (新增)
    # ==========================================
    if fetch_btn:
        import requests
        with st.spinner("正在向 GitHub 发送抓取指令..."):
            try:
                token = st.secrets.get("GITHUB_TOKEN")
                repo = st.secrets.get("GITHUB_REPO")
                
                if not token or not repo:
                    st.error("请在 Streamlit Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                else:
                    url = f"https://api.github.com/repos/{repo}/actions/workflows/update_data.yml/dispatches"
                    headers = {
                        "Accept": "application/vnd.github.v3+json",
                        "Authorization": f"Bearer {token}"
                    }
                    data = {"ref": "main"} # 如果主分支是 master，请改成 master
                    
                    res = requests.post(url, headers=headers, json=data)
                    
                    if res.status_code == 204:
                        st.success("✅ 指令已发送！GitHub 机器人正在后台抓取最新数据并更新源文件。")
                        st.info("⏳ 抓取过程大约需要 1 分钟。请稍后点击旁边的【同步数据】按钮获取最新结果。")
                    else:
                        st.error(f"指令发送失败，状态码：{res.status_code}。请检查 Token 权限。")
            except Exception as e:
                st.error(f"网络请求异常：{e}")

    # ==========================================
    # 3. 同步数据逻辑 (保留原样)
    # ==========================================
    if sync_btn:
        with st.spinner("正在从源文件同步数据..."):
            FILE_SORTED = "升序源文件.xlsx"
            if os.path.exists(FILE_SORTED):
                wb_src = openpyxl.load_workbook(FILE_SORTED, read_only=True, data_only=True)
                if "数据源" in wb_src.sheetnames: ws_src = wb_src["数据源"]
                else: st.error("源文件里找不到名为“数据源”的工作表！"); st.stop()
                def clean_val(v):
                    if v is None: return ""
                    try: return str(int(float(v)))
                    except: return str(v).strip()
                synced_rows = []
                for row in ws_src.iter_rows(min_row=3, max_col=27):
                    if all(cell.value is None for cell in row): break
                    p1, p2, p3 = row[0].value, row[1].value, row[2].value
                    if p1 is None: continue
                    raw_p = f"{clean_val(p1)}{clean_val(p2)}{clean_val(p3)}"
                    year_val = row[26].value if len(row) > 26 else None
                    year_str = clean_val(year_val) if clean_val(year_val) != "" else "2026"
                    period_str = f"{year_str}{raw_p}"
                    nums = []
                    for i in range(7):
                        t_str = clean_val(row[3 + i*2].value)
                        u_str = clean_val(row[4 + i*2].value)
                        if t_str == "" and u_str == "": nums.append(None)
                        else:
                            t_int = int(t_str) if t_str.isdigit() else 0
                            u_int = int(u_str) if u_str.isdigit() else 0
                            nums.append(t_int * 10 + u_int)
                    new_row = [None]*30
                    new_row[18] = period_str
                    for i in range(6): new_row[19+i] = nums[i]
                    new_row[25] = nums[6]
                    synced_rows.append(new_row)
                wb_src.close()
                if synced_rows:
                    synced_df = pd.DataFrame(synced_rows)
                    synced_df = synced_df.sort_values(by=18, ascending=False).reset_index(drop=True)
                    st.session_state.synced_df = synced_df
                    st.success("✅ 数据同步成功！已加载最新源文件。")
                    st.rerun()
                else: st.warning("【数据源】工作表没有数据！")
            else: st.error(f"找不到文件！请确认 {FILE_SORTED} 在根目录。")

    if trend_btn: render_trend_chart(df_data)
    if clear_btn:
        st.session_state.calc_data_single = None; st.session_state.calc_data_multi = None; st.session_state.calc_result_preview = None; st.session_state.predicted_nums_single = None; st.session_state.predicted_nums_multi = None
        st.success("✅ 数据已清空！")
    if start_btn:
        progress_bar = st.progress(0); status_text = st.empty()
        status_text.text("进度: 10%..."); time.sleep(0.2); progress_bar.progress(40); status_text.text("进度: 40%..."); time.sleep(0.2)
        df_triggers, df_counts, error_msg = calculate_linkage(df_data, selected_period, analysis_mode)
        progress_bar.progress(100); status_text.text("进度: 100% | 完成")
        if error_msg: st.error(error_msg)
        else:
            predicted_nums = df_counts.head(7)["下期数字"].tolist() if df_counts is not None and not df_counts.empty else []
            if analysis_mode == "单排分析": st.session_state.calc_data_single = (df_triggers, df_counts); st.session_state.predicted_nums_single = predicted_nums
            else: st.session_state.calc_data_multi = (df_triggers, df_counts); st.session_state.predicted_nums_multi = predicted_nums
            st.success(f"✅ 分析完成！找到 {len(df_triggers)} 处触发。")
    if result_btn:
        predicted_nums = st.session_state.predicted_nums_single if analysis_mode == "单排分析" else st.session_state.predicted_nums_multi
        if not predicted_nums: st.warning("请先点击【开始分析】！")
        else:
            with st.spinner("正在比对..."):
                res_data, err = calculate_prize(df_data, selected_period, predicted_nums)
                if err == "本期开奖数据未更新": st.warning(f"⏳ {selected_period} 期的下期开奖数据未更新！"); st.session_state.calc_result_preview = pd.DataFrame([res_data])
                elif err: st.error(err)
                else: st.success("预祝您中奖！"); st.session_state.calc_result_preview = pd.DataFrame([res_data])

    st.divider()
    col_lb1, col_lb2 = st.columns(2)
    with col_lb1:
        st.subheader("单排结果")
        if st.session_state.calc_data_single is not None:
            df_t1, df_c1 = st.session_state.calc_data_single
            st.dataframe(df_t1, use_container_width=True, hide_index=True, height=200); st.dataframe(df_c1, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无单排数据。")
    with col_lb2:
        st.subheader("多排结果")
        if st.session_state.calc_data_multi is not None:
            df_t2, df_c2 = st.session_state.calc_data_multi
            st.dataframe(df_t2, use_container_width=True, hide_index=True, height=200); st.dataframe(df_c2, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无多排数据。")
    st.divider()
    st.subheader("中出结果预览")
    if st.session_state.calc_result_preview is not None: st.dataframe(st.session_state.calc_result_preview, use_container_width=True, hide_index=True)
    else: st.info("暂无中出结果。")

def render_trend_chart(df_data):
    st.divider()
    st.subheader("📈 历史走势图（最近30期）")
    if df_data is None or isinstance(df_data, str): return
    recent_data = df_data.head(30).copy()
    if recent_data.empty: return
    periods = recent_data.iloc[:, 18].apply(clean_period).tolist()
    tab1, tab2 = st.tabs(["平 码 区", "特 码 区"])
    with tab1:
        cols = [f"{i:02d}" for i in range(1, 50)]
        matrix = pd.DataFrame("", index=periods, columns=cols)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            for i in range(19, 25):
                num_str = clean_period(row.iloc[i])
                if num_str in cols: matrix.at[period, num_str] = "●"
        st.dataframe(matrix, use_container_width=True, height=600)
    with tab2:
        cols = [f"{i:02d}" for i in range(1, 50)]
        matrix_special = pd.DataFrame("", index=periods, columns=cols)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            num_str = clean_period(row.iloc[25]) if len(row) > 25 else ""
            if num_str in cols: matrix_special.at[period, num_str] = "★"
        st.dataframe(matrix_special, use_container_width=True, height=600)

def render_stats(df_data):
    st.title("?? 历史同现深度分析")
    if df_data is None or isinstance(df_data, str): return
    target_num = st.number_input("目标号码 (1-49):", min_value=1, max_value=49, value=30)
    top_n = st.selectbox("提取前几名:", [3, 5, 8, 10])
    if st.button("?? 开始扫描", use_container_width=True):
        with st.spinner("正在比对..."):
            try:
                nums_df = df_data.iloc[:, 19:25].apply(pd.to_numeric, errors='coerce')
                filtered = nums_df[nums_df.isin([target_num]).any(axis=1)]
                if len(filtered) == 0: st.warning("未出现过。")
                else:
                    counts = {}
                    for _, row in filtered.iterrows():
                        for num in row.values:
                            if pd.notna(num) and int(num) != target_num: counts[int(num)] = counts.get(int(num), 0) + 1
                    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
                    res_df = pd.DataFrame([{"排名": i+1, "同频号码": f"{num:02d}", "同现次数": count} for i, (num, count) in enumerate(sorted_counts)])
                    st.success(f"与 {target_num:02d} 号同现频率最高的结果：")
                    st.dataframe(res_df, use_container_width=True, hide_index=True)
                    st.bar_chart(res_df.set_index("同频号码")["同现次数"])
            except Exception as e: st.error(f"出错：{e}")

def build_rule_database():
    try:
        # 🔥 确保后缀是 .xlsm，括号是英文
        file_name = "数据分析系统最终版本(智能全套).xlsm" 
        df = pd.read_excel(file_name, sheet_name="规则")
        db = {}
        col_num = next((c for c in df.columns if "号码" in str(c)), "号码")
        col_zodiac = next((c for c in df.columns if "生肖" in str(c)), "生肖")
        col_wuxing = next((c for c in df.columns if "肖五行" in str(c)), "肖五行")
        col_element = next((c for c in df.columns if "号五行" in str(c)), "号五行")
        col_tail = next((c for c in df.columns if "尾五行" in str(c)), "尾五行")
        col_color = next((c for c in df.columns if "波色" in str(c)), "波色")
        col_size = next((c for c in df.columns if "大小" in str(c)), "大小")
        col_obj = next((c for c in df.columns if "物象" in str(c)), "物象")
        col_role = next((c for c in df.columns if "人物" in str(c)), "人物")
        col_sum = next((c for c in df.columns if "合数" in str(c)), "合数")
        
        for _, row in df.iterrows():
            num_str = str(row[col_num]).strip()
            if num_str.replace('.', '', 1).isdigit():
                n = str(int(float(num_str)))
                db[n] = {
                    "生肖": str(row[col_zodiac]), "肖五行": str(row[col_wuxing]), 
                    "号五行": str(row[col_element]), "尾五行": str(row[col_tail]), 
                    "波色": str(row[col_color]), "大小": str(row[col_size]), 
                    "物象": str(row[col_obj]), "人物": str(row[col_role]), 
                    "合数": str(row[col_sum])
                }
        return db
    except Exception as e: 
        # 遇到错误直接把真实原因打印出来
        st.error(f"底层读取失败，真实原因：{e}")
        return None

def build_full_table_text(db):
    result = "【1-49号完整属性表（绝对权威）】\\n"
    for i in range(1, 50):
        if str(i) in db:
            info = db[str(i)]
            result += f"{i}号:{{{info['生肖']},{info['肖五行']},{info['号五行']},{info['尾五行']},{info['物象']},{info['人物']},{info['大小']},{info['波色']},{info['合数']}}}\\n"
    return result

def get_analysis_prompt(full_table):
    return f"""你是一个精通集合运算与条件排除的推演助手。以下是 1-49 号号码的绝对属性参照表：
{full_table}
【推演与输出规则】
1. 用户的提问已明确给出了排杀条件，请严格从 1-49 中剔除不符合条件的号码。
2. 注意多重条件叠加，比如一个号码可能同时触犯了多个排杀条件。
3. 如果严格剔除后，剩下的号码大于 0 个，直接输出剩下的生肖和号码。
4. 如果严格剔除后，剩下 0 个号码（即全被杀光），请触发后补机制：筛选出【只触犯了一个排杀条件】的号码作为候补，【触犯两个及以上条件】的号码绝对不能作为候补。
5. 格式要求：请先在心中默默推演，直接给出结果。最后输出格式必须包含：'【严格筛选结果】'和'【后补筛选结果】(如果有的话)。
6. 绝对禁止复述属性表，直接给出最终号码和生肖。"""

def call_deepseek_api(question, system_prompt):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    payload = {"model": "deepseek-chat", "temperature": 0, "messages": [{"role": "system", "content": "你是一个严谨的数据推演与集合运算助手。"}, {"role": "user", "content": question}, {"role": "system", "content": system_prompt}]}
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].replace("**", "").replace("###", "").replace("##", "").replace("#", "").replace("`", "")
        else: return f"请求失败：{response.status_code}\\n{response.text}"
    except Exception as e: return f"运行错误：{e}"

def render_ai(df_data):
    st.title("?? AI 严谨推演系统")
    
    if df_data is not None and not isinstance(df_data, str):
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)
        
        # ?? 核心新增：自动推算下一期并置顶
        if unique_periods and unique_periods[0] != "暂无数据":
            latest_period = unique_periods[0] # 此时拿到的是 2026119
            try:
                # 强转成数字后 +1
                next_period = str(int(float(latest_period)) + 1)
                # 如果算出来的下一期还没有在历史数据里，就把它插到最前面
                if next_period not in unique_periods:
                    unique_periods.insert(0, next_period)
            except:
                pass
    else: 
        unique_periods = ["暂无数据"]    

    if "reset_version" not in st.session_state: st.session_state.reset_version = 0
    v_prefix = f"v{st.session_state.reset_version}_chk_"

    CHECKBOX_MAP = {
        "金肖": "杀金肖（猴鸡），", "木肖": "杀木肖（虎兔），", "水肖": "杀水肖（鼠猪），", "火肖": "杀火肖（蛇马），", "土肖": "杀土肖（牛龙羊狗），",
        "红肖": "杀红肖（马兔鼠鸡），", "蓝肖": "杀蓝肖（虎猴蛇猪），", "绿肖": "杀绿肖（龙狗牛羊），",
        "0尾": "杀0尾（10、20、30、40），", "1尾": "杀1尾（01、11、21、31、41），", "2尾": "杀2尾（02、12、22、32、42），",
        "3尾": "杀3尾（03、13、23、33、43），", "4尾": "杀4尾（04、14、24、34、44），", "5尾": "杀5尾（05、15、25、35、45），",
        "6尾": "杀6尾（06、16、26、36、46），", "7尾": "杀7尾（07、17、27、37、47），", "8尾": "杀8尾（08、18、28、38、48），", "9尾": "杀9尾（09、19、29、39、49），",
        "杀鼠": "杀鼠，", "杀牛": "杀牛，", "杀虎": "杀虎，", "杀兔": "杀兔，", "杀龙": "杀龙，", "杀蛇": "杀蛇，", "杀马": "杀马，", "杀羊": "杀羊，", "杀猴": "杀猴，", "杀鸡": "杀鸡，", "杀狗": "杀狗，", "杀猪": "杀猪，",
        "1门": "杀1门（01、02、03、04、05、06、07、08、09），", "2门": "杀2门（10、11、12、13、14、15、16、17、18、19），", "3门": "杀3门（20、21、22、23、24、25、26、27、28、29），", "4门": "杀4门（30、31、32、33、34、35、36、37、38、39），", "5门": "杀5门（40、41、42、43、44、45、46、47、48、49），",
        "1段": "杀1段（01、02、03、04、05、06、07），", "2段": "杀2段（08、09、10、11、12、13、14），", "3段": "杀3段（15、16、17、18、19、20、21），", "4段": "杀4段（22、23、24、25、26、27、28），", "5段": "杀5段（29、30、31、32、33、34、35），", "6段": "杀6段（36、37、38、39、40、41、42），", "7段": "杀7段（43、44、45、46、47、48、49），",
        "01合": "杀01合（01、10），", "02合": "杀02合（02、11、20），", "03合": "杀03合（03、12、21、30），", "04合": "杀04合（04、13、22、31、40），", "05合": "杀05合（05、14、23、32、41），", "06合": "杀06合（06、15、24、33、42），", "07合": "杀07合（07、16、25、34、43），", "08合": "杀08合（08、17、26、35、44），", "09合": "杀09合（09、18、27、36、45），", "10合": "杀10合（19、28、37、46），", "11合": "杀11合（29、38、47），", "12合": "杀12合（39、48），", "13合": "杀13合（49），",
        "红波": "杀红波（01、02、07、08、12、13、18、19、23、24、29、30、34、35、40、45、46），", "蓝波": "杀蓝波（03、04、09、10、14、15、20、25、26、31、36、37、41、42、47、48），", "绿波": "杀绿波（05、06、11、16、17、21、22、27、28、32、33、38、39、43、44、49），",
        "红波单": "杀红波单（01、07、13、19、23、29、35、45），", "红波双": "杀红波双（02、08、12、18、24、30、34、40、46），", "蓝波单": "杀蓝波单（03、09、15、25、31、37、41、47），", "蓝波双": "杀蓝波双（04、10、14、20、26、36、42、48），", "绿波单": "杀绿波单（05、11、17、21、27、33、39、43、49），", "绿波双": "杀绿波双（06、16、22、28、32、38、44），",
        "金号": "杀金号（04、05、12、13、26、27、34、35、42、43），", "木号": "杀木号（08、09、16、17、24、25、38、39、46、47），", "水号": "杀水号（01、14、15、22、23、30、31、44、45），", "火号": "杀火号（02、03、10、11、18、19、32、33、40、41、48、49），", "土号": "杀土号（06、07、20、21、28、29、36、37），",
        "金尾": "杀金尾（04、09、14、19、24、29、34、39、44、49），", "木尾": "杀木尾（03、08、13、18、23、28、33、38、43、48），", "水尾": "杀水尾（01、06、11、16、21、26、31、36、41、46），", "火尾": "杀火尾（02、07、12、17、22、27、32、37、42、47），", "土尾": "杀土尾（05、10、15、20、25、30、35、40、45），",
        "大肖": "杀大肖（牛虎龙马），", "中肖": "杀中肖（羊猴狗猪），", "小肖": "杀小肖（鼠兔蛇鸡），", "书肖": "杀书肖（马龙虎），", "琴肖": "杀琴肖（蛇兔鸡），", "棋肖": "杀棋肖（牛鼠狗），", "画肖": "杀画肖（猪猴羊），", "福肖": "杀福肖（马龙虎鼠），", "禄肖": "杀禄肖（兔牛猪猴），", "寿肖": "杀寿肖（蛇狗鸡羊），",
        "家臣": "杀家臣（马牛猪狗），", "美女": "杀美女（蛇兔鸡羊），", "君王": "杀君王（龙虎），", "恶人": "杀恶人（鼠猴），"
    }

    if "ai_api_result" not in st.session_state: st.session_state.ai_api_result = "等待推演..."
    if "ai_ball_result" not in st.session_state: st.session_state.ai_ball_result = []

    def get_prefix(qishu, qiu, order_type):
        if order_type == "按序": interval = f"{qiu}的取值区间为1号至49号之间，"
        else:
            if qiu == "第1球": interval = "第一球的取值区间为1号至20号之间，"
            elif qiu == "第2球": interval = "第二球的取值区间为2号至25号之间，"
            elif qiu == "第3球": interval = "第三球的取值区间为3号至30号之间，"
            elif qiu == "第4球": interval = "第四球的取值区间为4号至40号之间，"
            elif qiu == "第5球": interval = "第五球的取值区间为15号至48号之间，"
            elif qiu == "第6球": interval = "第六球的取值区间为25号至49号之间，"
            else: interval = "第七球的取值区间为1号至49号之间，"
        return f"这是{qishu}期{order_type}{qiu}的核算条件，{interval}"

    col1, col2, col3 = st.columns(3)
    with col1: qishu = st.selectbox("选择期数：", unique_periods, index=0)
    with col2: qiu = st.selectbox("选择球数：", ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"], index=0)
    with col3: order_type = st.radio("核算模式：", ["升序", "按序"], horizontal=True)

    st.divider()
    checked_texts = []
    for key in CHECKBOX_MAP.keys():
        if st.session_state.get(f"{v_prefix}{key}", False): checked_texts.append(CHECKBOX_MAP[key])
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        # 🔥 接收多维分析传过来的条件
        extra = st.session_state.get("ai_extra_condition", "")
    
        full_text = get_prefix(qishu, qiu, order_type) + "".join(checked_texts) + extra
        st.text_area("已选核算条件：", value=full_text, height=200, disabled=True)
        
        
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🚀 开始推演 (呼叫 API)", use_container_width=True, type="primary"):
                if not checked_texts: st.warning("请先勾选！")
                else:
                    question = full_text + f"请根据以上触犯条件全面分析{qiu}剩余什么生肖与号码。如果全部触犯，那么请将触犯次数最少的作为后补。请开始精准核算。"
                    with st.spinner("正在呼叫 DeepSeek 进行全量推演..."):
                        db = build_rule_database()
                        if not db: st.error("规则表读取失败！")
                        else:
                            system_prompt = get_analysis_prompt(build_full_table_text(db))
                            answer = call_deepseek_api(question, system_prompt)
                            st.session_state.ai_api_result = answer
                            if "请求失败" in answer or "运行错误" in answer:
                                st.error(f"AI 接口报错：{answer}")
                                st.session_state.ai_ball_result = []
                            else:
                                st.success("✅ AI 推演成功！")
                                import re
                                nums = re.findall(r'\\b([0-4][0-9])\\b', answer)
                                st.session_state.ai_ball_result = sorted(list(set(int(n) for n in nums if 1 <= int(n) <= 49)))
                            
        with b2:
            if st.button("🗑️ 清理勾选", use_container_width=True):
                st.session_state.reset_version += 1
                st.session_state.ai_api_result = "等待推演..."
                st.session_state.ai_ball_result = []
                st.rerun()

        if st.session_state.ai_ball_result:
            st.markdown("### 🎯 AI 提取的推演号码")
            balls_html = '<div class="ball-container" style="flex-wrap: wrap; justify-content: flex-start;">'
            for num in st.session_state.ai_ball_result:
                balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
            balls_html += '</div>'
            st.markdown(balls_html, unsafe_allow_html=True)

    with col_right:
        with st.expander("生肖与五行", expanded=True):
            cols = st.columns(3)
            for idx, key in enumerate(["金肖", "木肖", "水肖", "火肖", "土肖", "红肖", "蓝肖", "绿肖"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("尾数杀号"):
            cols = st.columns(3)
            for i in range(10):
                with cols[i % 3]: st.checkbox(f"{i}尾", key=f"{v_prefix}{i}尾")
        with st.expander("生肖专属"):
            cols = st.columns(3)
            for idx, z in enumerate(["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]):
                with cols[idx % 3]: st.checkbox(f"杀{z}", key=f"{v_prefix}杀{z}")
        with st.expander("门数 / 段数 / 合数"):
            cols = st.columns(3)
            for i in range(1, 6):
                with cols[(i-1) % 3]: st.checkbox(f"{i}门", key=f"{v_prefix}{i}门")
            for i in range(1, 8):
                with cols[(i+4) % 3]: st.checkbox(f"{i}段", key=f"{v_prefix}{i}段")
            for i in range(1, 14):
                with cols[(i+11) % 3]: st.checkbox(f"{i:02d}合", key=f"{v_prefix}{i:02d}合")
        with st.expander("波色 / 波单双"):
            cols = st.columns(3)
            for idx, key in enumerate(["红波", "蓝波", "绿波", "红波单", "红波双", "蓝波单", "蓝波双", "绿波单", "绿波双"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("其他属性"):
            cols = st.columns(3)
            others = ["金号", "木号", "水号", "火号", "土号", "金尾", "木尾", "水尾", "火尾", "土尾", "大肖", "中肖", "小肖", "书肖", "琴肖", "棋肖", "画肖", "福肖", "禄肖", "寿肖"]
            for idx, key in enumerate(others):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("物象专属"):
            cols = st.columns(3)
            for idx, key in enumerate(["家臣", "美女", "君王", "恶人"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")

    st.divider()
    st.markdown("### 📝 AI 完整推演结果")
    st.text_area("DeepSeek 返回：", value=st.session_state.ai_api_result, height=300)
# ==========================================
# 页面 6：多维分析系统 (功能原封不动，仅修复后缀版)
# ==========================================
import pandas as pd
import os
from datetime import datetime
from openpyxl.utils import get_column_letter

# 🔥 核心优化：使用缓存读取，极大提升速度
@st.cache_data(show_spinner=False, ttl=1800)
def load_excel_data(file_path, sheet_name):
    import requests
    import io
    import openpyxl
    
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    
    if not token or not repo:
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb[sheet_name]
            return list(ws.iter_rows(values_only=True))
        except Exception:
            return []
        
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            download_url = r.json()["download_url"]
            content = requests.get(download_url).content
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws = wb[sheet_name]
            return list(ws.iter_rows(values_only=True))
        else:
            st.error(f"读取云端文件失败，状态码: {r.status_code}")
            return []
    except Exception as e:
        st.error(f"云端读取异常: {e}")
        return []
def render_multi_analysis(df_data):
    from openpyxl.utils import get_column_letter, column_index_from_string
    
    st.title("多维分析系统")
    if "current_attr" not in st.session_state: st.session_state.current_attr = "生肖"
    if "current_file" not in st.session_state: st.session_state.current_file = "升序全套"
    if "multi_results_dict" not in st.session_state: st.session_state.multi_results_dict = {}
    if "multi_result_text" not in st.session_state: st.session_state.multi_result_text = ""

    # 🔥 核心：只在列表里增加 4 个交叉选项，原有全部保留
    ATTR_MAP = {
        "数字五行": 6, "生肖": 7, "尾数": 8, "数字合": 9, "门数": 10, "段数": 11, "单双组合": 12, "单双笔": 13, "独合字": 14, "单双头": 15, "单双": 16, "波单双": 17, "生肖五行": 18, "颜色肖": 19, "四宝": 20, "物象": 21, "波色": 22, "阴阳": 23, "家野": 24, "天地": 25, "阴阳天地": 26, "吉凶": 27, "男女": 28, "方位": 29, "3模": 30, "尾五行": 31, "福禄寿": 32, "大小肖": 33,
        "生肖五行相生": 18, "生肖五行相克": 18, "数字五行相生": 6, "数字五行相克": 6, "尾五行相生": 31, "尾五行相克": 31, "生肖与五行相生": 18, "生肖与五行相克": 18,
        "生肖与数字相生": 18, "生肖与数字相克": 18, "数字与生肖相生": 6, "数字与生肖相克": 6
    }

    st.markdown("### 分析参数设置")
    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    with row1_col1:
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)
        selected_period = st.selectbox("基准期数", unique_periods)
    with row1_col2: 
        selected_file_type = st.selectbox("选择分析文件", ["升序全套", "按序全套"])
    with row1_col3: 
        selected_attr = st.selectbox("分析属性", list(ATTR_MAP.keys()), index=1) 
    with row1_col4:
        ball_str = st.selectbox("基准球号", ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"])
        ball_num = int(ball_str.replace("第", "").split("球")[0])

    row2_col1, row2_col2, row2_col3 = st.columns([1, 1, 1])
    with row2_col1: 
        min_len = st.number_input("最少对比行数", min_value=3, max_value=20, value=7, step=1)
    with row2_col2: 
        max_len = st.number_input("最多分组行数", min_value=3, max_value=20, value=12, step=1)
    with row2_col3:
        st.write("")
        st.write("")
        run_btn = st.button("执行当前球分析", use_container_width=True, type="primary")

    # 🔥 交叉模式专属判断（绝对隔离）
    is_cross_mode = selected_attr in ["生肖与数字相生", "生肖与数字相克", "数字与生肖相生", "数字与生肖相克"]
    is_zodiac_to_num = "生肖与数字" in selected_attr
    is_cross_sheng = "相生" in selected_attr
    is_cross_ke = "相克" in selected_attr

    base_excel_col = ATTR_MAP[selected_attr]
    check_col_letter = get_column_letter(base_excel_col + (ball_num - 1) * 30)
    st.info(f"💡 校验信息：以【{selected_period}】期为基准，属性【{selected_attr}】锁定在 {check_col_letter} 列")

    if selected_attr != st.session_state.current_attr or selected_file_type != st.session_state.current_file:
        st.session_state.current_attr = selected_attr
        st.session_state.current_file = selected_file_type
        st.session_state.multi_results_dict = {}
        st.session_state.multi_result_text = ""
        st.rerun()

    st.divider()
    
    if run_btn:
        is_sheng_mode = "相生" in selected_attr
        is_ke_mode = "相克" in selected_attr
        # 普通模式：只要不是交叉，就是普通模式
        is_normal_mode = not (is_sheng_mode or is_ke_mode) and not is_cross_mode
        
        if "数字" in selected_attr or "号" in selected_attr: wx_suffix = "号"
        elif "尾" in selected_attr: wx_suffix = "尾"
        elif "肖" in selected_attr: wx_suffix = "肖"
        else: wx_suffix = ""
        
        target_file = "升序全套.xlsx" if selected_file_type == "升序全套" else "按序全套.xlsx"
        sheet_name = "升序全套分析" if selected_file_type == "升序全套" else "按序全套分析"
            
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            status_text.text("正在读取 Excel 数据...")
            all_rows = load_excel_data(target_file, sheet_name)
            if not all_rows:
                st.error(f"读取 {target_file} 失败或文件为空。"); st.stop()
            progress_bar.progress(20)
            
            def clean_str(v):
                if v is None: return ""
                try: return str(int(float(v)))
                except: return str(v).replace("\\r", "").replace("\\n", "").replace(" ", "").strip()

            target_row_idx = -1
            for r_idx in range(len(all_rows)):
                year_val = clean_str(all_rows[r_idx][213]) if len(all_rows[r_idx]) > 213 else "2026"
                p1 = clean_str(all_rows[r_idx][0]) if len(all_rows[r_idx]) > 0 else ""
                p2 = clean_str(all_rows[r_idx][1]) if len(all_rows[r_idx]) > 1 else ""
                p3 = clean_str(all_rows[r_idx][2]) if len(all_rows[r_idx]) > 2 else ""
                if f"{year_val}{p1}{p2}{p3}" == selected_period: target_row_idx = r_idx; break
            
            if target_row_idx == -1: st.error(f"找不到基准期数 {selected_period}！"); st.stop()
            
            ball_cols = [get_column_letter(base_excel_col + (n - 1) * 30) for n in range(1, 8)]
            ref_col_letter = ball_cols[ball_num - 1]
            ref_col_idx_0 = column_index_from_string(ref_col_letter) - 1
            
            # 交叉五行专属字典
            cross_sheng = {"金": ["土", "水"], "木": ["水", "火"], "水": ["金", "木"], "火": ["木", "土"], "土": ["火", "金"]}
            cross_ke = {"金": ["火", "木"], "木": ["金", "土"], "水": ["土", "火"], "火": ["水", "金"], "土": ["木", "水"]}
            
            def get_wx(s):
                core = s.replace("肖", "").replace("号", "").replace("尾", "")
                return {"鼠":"水","牛":"土","虎":"木","兔":"木","龙":"土","蛇":"火","马":"火","羊":"土","猴":"金","鸡":"金","狗":"土","猪":"水"}.get(core, core)
                
            def check_match(a, b):
                if is_cross_mode:
                    if is_cross_sheng: return b in cross_sheng.get(a, [])
                    elif is_cross_ke: return b in cross_ke.get(a, [])
                if is_normal_mode: return a == b
                core_a, core_b = get_wx(a), get_wx(b)
                child = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
                mother = {"金": "土", "土": "火", "火": "木", "木": "水", "水": "金"}
                ke_dict = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
                if is_sheng_mode: return (child.get(core_a) == core_b) or (mother.get(core_a) == core_b)
                elif is_ke_mode: return (ke_dict.get(core_a) == core_b) or (ke_dict.get(core_b) == core_a)
                return False

            def get_col_data(col_idx_0):
                return [(r_idx, clean_str(all_rows[r_idx][col_idx_0]) if col_idx_0 < len(all_rows[r_idx]) else "") for r_idx in range(len(all_rows))]

            status_text.text("正在提取基准列...")
            ref_col_data = get_col_data(ref_col_idx_0)
            template = []
            for r in range(target_row_idx, len(ref_col_data)):
                if ref_col_data[r][1]: template.append(ref_col_data[r][1])
                if len(template) >= max_len: break
                    
            if len(template) < min_len:
                progress_bar.empty(); status_text.empty(); st.warning(f"基准列数据不足 {min_len} 个"); st.stop()
                
            gColl = {i: [] for i in range(min_len, max_len + 1)}
            status_text.text("正在扫描匹配项...")
            
            for n in range(1, 8):
                # 🔥 核心隔离：交叉模式下，目标列的寻找逻辑完全不同
                if is_cross_mode:
                    target_base_col = 6 if is_zodiac_to_num else 18
                    col_name = get_column_letter(target_base_col + (n - 1) * 30)
                else:
                    col_name = ball_cols[n - 1]
                    
                current_col_idx = column_index_from_string(col_name) - 1
                disp_name = f"{n}球({col_name})"
                is_self = (col_name == ref_col_letter)
                
                col_data = get_col_data(current_col_idx)
                valid_data = [(r, col_data[r][1]) for r in range(2, len(col_data)) if col_data[r][1]]
                vc = len(valid_data)
                
                if vc >= min_len:
                    k = 0
                    while k <= vc - min_len:
                        max_l = 0
                        for j in range(vc - k):
                            if j >= len(template): break
                            if j > 0 and valid_data[k+j][0] != valid_data[k+j-1][0] + 1: break
                            if not check_match(template[j], valid_data[k+j][1]): break
                            max_l = j + 1
                            
                        if max_l >= min_len:
                            real_l = max_l; group_l = min(real_l, max_len)
                            sr = valid_data[k][0]; er = valid_data[k + real_l - 1][0]
                            
                            def get_ctx(r_idx):
                                if r_idx < 0 or r_idx >= len(col_data): return "无"
                                v = col_data[r_idx][1]
                                if not v: return "空"
                                
                                # 🔥 交叉模式专属输出格式
                                if is_cross_mode:
                                    rules = cross_sheng.get(v, []) if is_cross_sheng else cross_ke.get(v, [])
                                    v_suffix = "肖" if is_zodiac_to_num else "号" # 基准后缀
                                    target_suffix = "号" if is_zodiac_to_num else "肖" # 目标后缀
                                    rule_str = "".join([f"{x}{target_suffix}" for x in rules])
                                    prefix = "生" if is_cross_sheng else "克"
                                    return f"{v}{v_suffix} ({prefix}{rule_str})"
                                    
                                if v in ["鼠","牛","虎","兔","龙","蛇","马","羊","猴","鸡","狗","猪"]: return v + "肖"
                                if v in ["金", "木", "水", "火", "土"]: return v + wx_suffix 
                                return v
                                
                            w1, w2, w3, w4 = get_ctx(sr-1), get_ctx(er+1), get_ctx(er+2), get_ctx(er+3)
                            
                            # 原汁原味保留原有逻辑
                            if is_normal_mode or is_cross_mode:
                                detail_txt = f"上:{w1} 下:{w2} 再下:{w3} 再再下:{w4}"
                            else:
                                core_w1 = get_wx(w1)
                                if is_sheng_mode:
                                    rule_str = {"金": f"水{wx_suffix}土{wx_suffix}", "木": f"水{wx_suffix}火{wx_suffix}", "水": f"金{wx_suffix}木{wx_suffix}", "火": f"土{wx_suffix}木{wx_suffix}", "土": f"金{wx_suffix}火{wx_suffix}"}.get(core_w1, "")
                                    full_w1 = f"{w1} (生{rule_str})" if rule_str else w1
                                    sha_str = f"本期杀{rule_str}。" if rule_str else ""
                                else:
                                    rule_str = {"金": f"火{wx_suffix}木{wx_suffix}", "木": f"土{wx_suffix}金{wx_suffix}", "水": f"火{wx_suffix}土{wx_suffix}", "火": f"水{wx_suffix}金{wx_suffix}", "土": f"木{wx_suffix}水{wx_suffix}"}.get(core_w1, "")
                                    full_w1 = f"{w1} (克{rule_str})" if rule_str else w1
                                    sha_str = f"本期杀{rule_str}。" if rule_str else ""
                                detail_txt = f"上:{full_w1} 下:{w2} 再下:{w3} 再再下:{w4}。{sha_str}"
                                
                            if is_self: detail_txt += " [自身参考列匹配]"
                            w1_str = str(w1).strip()
                            if w1_str not in ["空", "无", "", "0", "0.0", "None", "nan"]:
                                if er + 1 <= 25:
                                    line_txt = f"{disp_name} 行{sr+1}-{er+1}({real_l}行)近{real_l}期一致: {detail_txt}"
                                    if 5 <= real_l <= 9:
                                        st.session_state.play_alert = True
                                        line_txt = f"[[HIGHLIGHT]]{line_txt}[[/HIGHLIGHT]]"
                                else:
                                    line_txt = f"{disp_name} 行{sr+1}-{er+1}({real_l}行): {detail_txt}"
                                gColl[group_l].append({"line": line_txt, "sr": sr})
                            k += real_l
                        else:
                            k += 1
                                
            progress_bar.progress(90)
            status_text.text("正在整理报告...")
#=================第三次粘贴位置=============            
            ball_lines = [f"========== {selected_file_type} - {selected_period} - {selected_attr} - {ball_str} =========="]
            for L in range(min_len, max_len + 1):
                if not gColl[L]: continue
                ball_lines.append(f"--- 连续{L}行匹配（共{len(gColl[L])}处）---")
                for item in gColl[L]:
                    ball_lines.append(item["line"]); ball_lines.append("")
            
            st.session_state.multi_results_dict[ball_num] = "\\n".join(ball_lines)
            combined_text = []
            for i in range(1, 8):
                if i in st.session_state.multi_results_dict: combined_text.append(st.session_state.multi_results_dict[i])
            st.session_state.multi_result_text = "\\n\\n\\n".join(combined_text)
            
            if st.session_state.get("play_alert", False):
                import streamlit.components.v1 as components
                components.html("<script>var AudioContext = window.AudioContext || window.webkitAudioContext; var ctx = new AudioContext(); function playCoin() { if (ctx.state === 'suspended') ctx.resume(); var osc1 = ctx.createOscillator(); var gain1 = ctx.createGain(); osc1.type = 'sine'; osc1.frequency.setValueAtTime(987.77, ctx.currentTime); gain1.gain.setValueAtTime(0.5, ctx.currentTime); gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3); osc1.connect(gain1); gain1.connect(ctx.destination); osc1.start(); osc1.stop(ctx.currentTime + 0.3); var osc2 = ctx.createOscillator(); var gain2 = ctx.createGain(); osc2.type = 'sine'; osc2.frequency.setValueAtTime(1318.51, ctx.currentTime + 0.1); gain2.gain.setValueAtTime(0.5, ctx.currentTime + 0.1); gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4); osc2.connect(gain2); gain2.connect(ctx.destination); osc2.start(ctx.currentTime + 0.1); osc2.stop(ctx.currentTime + 0.4); } playCoin(); </script>", height=0, width=0)
                st.session_state.play_alert = False

            progress_bar.progress(100)
            status_text.text("计算完成！")
            
        except Exception as e:
            st.error(f"计算报错: {e}")

    st.divider()
    
    col_title, col_btn = st.columns([8, 2])
    with col_title: st.subheader("详细结果 (累积报告)")
    with col_btn:
        if st.button("清空所有结果", use_container_width=True):
            st.session_state.multi_results_dict = {}
            st.session_state.multi_result_text = ""
            st.rerun()

    if st.session_state.multi_result_text != "":
        import streamlit.components.v1 as components
        import html
        import base64
        
        clean_text = st.session_state.multi_result_text.replace('\\r', '').replace('\\\\n', '\\n').replace('\\\\\\\\n', '\\n')
        escaped_text = html.escape(clean_text).replace("\\n", "<br>")
        
        highlighted_display = escaped_text.replace(
            "[[HIGHLIGHT]]", 
            '<span style="color: #dc2626; background-color: #fef08a; font-weight: bold; padding: 2px 4px; border-radius: 4px;">'
        ).replace("[[/HIGHLIGHT]]", '</span>')
    
        display_html = f"""
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; font-family: Consolas, monospace; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-wrap: break-word; max-height: 500px; overflow-y: auto;">
            {highlighted_display}
        </div>
        """
        
        print_html = f"""
        <html><head><meta charset="utf-8"><style>
        body {{ font-family: Consolas, monospace; padding: 20px; line-height: 1.8; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; font-size: 14px; }}
        </style></head><body><pre>{highlighted_display}</pre></body></html>
        """
        
        b64_display = base64.b64encode(display_html.encode('utf-8')).decode('utf-8')
        b64_print = base64.b64encode(print_html.encode('utf-8')).decode('utf-8')
        
        components.html(
            f"""
            <div id="report-container"></div>
            <div style="margin-top: 15px; text-align: center;">
                <button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold;">🖨️ 打印当前报告 (排版不乱)</button>
            </div>
            <script>
            function b64DecodeUnicode(str) {{
                return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }}).join(''));
            }}
            document.getElementById('report-container').innerHTML = b64DecodeUnicode("{b64_display}");
            function printReport() {{
                var win = window.open("");
                win.document.write(b64DecodeUnicode("{b64_print}"));
                win.document.close();
                win.focus();
                setTimeout(function() {{ win.print(); }}, 500);
            }}
            </script>
            """,
            height=620,
            scrolling=False
        )
    
        st.write("") 
        file_name = f"报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        st.download_button(
            label="📥 保存完整报告到本地 (TXT格式)", 
            data=clean_text.encode('utf-8-sig'), 
            file_name=file_name, 
            mime="text/plain", 
            use_container_width=True
        )
    else:
        st.info("请选择文件、属性及球号后点击【执行当前球分析】。")
                                    

       
#=======多维分析终点============
def render_deep_linkage(df_data):
    # 🌟 页面大标题
    st.title("🔗 深度联动分析系统")
    
    # 🌟 间隔区说明
    st.info("""
    **💡 功能说明：** 
    本系统通过提取基准期开奖号码的属性组合（每3个一组），在全历史数据中寻找相同组合，并统计命中后**下一期各球位的属性频次**。
    系统会自动将出现次数最多的排在前列，剩余次数较少的作为杀码参考。
    """)
    
    st.divider()

    # ==========================
    # 1. 界面参数设置
    # ==========================
    st.markdown("### 分析参数设置")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        mode = st.selectbox("分析模式", ["升序生肖", "按序生肖", "升序尾数", "按序尾数", "升序数字", "按序数字"])
    with col2:
        if df_data is not None and not isinstance(df_data, str):
            unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
            try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
            except: unique_periods.sort(reverse=True)
        else:
            unique_periods = ["暂无数据"]
        selected_period = st.selectbox("基准期数", unique_periods)
    with col3:
        if "生肖" in mode:
            pick_num = st.number_input("预测前N名", min_value=4, max_value=9, value=5)
        else:
            pick_num = st.number_input("预测前N名", min_value=3, max_value=7, value=5)
    with col4:
        st.write("")
        st.write("")
        run_btn = st.button("🚀执行联动分析", use_container_width=True, type="primary")

    if "升序" in mode:
        target_file = "升序全套.xlsx"
        sheet_name = "升序全套分析"
    else:
        target_file = "按序全套.xlsx"
        sheet_name = "按序全套分析"

    st.info(f"💡当前读取文件：【{target_file}】 | 工作表：【{sheet_name}】")

    # ==========================
    # 2. 执行分析逻辑
    # ==========================
    if run_btn:
        with st.spinner(f"正在从云端读取 {target_file} 并进行按球位的深度频次统计..."):
            import requests
            import io
            import itertools
            import openpyxl
            from openpyxl.utils import get_column_letter, column_index_from_string
            
            token = st.secrets.get("GITHUB_TOKEN")
            repo = st.secrets.get("GITHUB_REPO")
            
            try:
                url = f"https://api.github.com/repos/{repo}/contents/{target_file}"
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                r = requests.get(url, headers=headers)
                
                if r.status_code == 200:
                    download_url = r.json()["download_url"]
                    file_content = requests.get(download_url).content
                    
                    # ?? 核心绝杀：彻底抛弃 pandas 的错位，改用 openpyxl 绝对精准定位
                    wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
                    ws = wb[sheet_name]
                    
                    grouped_data = {}
                    
                    def clean_cell(c):
                        if c is None: return ""
                        try: return str(int(float(c)))
                        except: return str(c).strip()
                        
                    # 根据你的要求，定义精准的字母列
                    if "生肖" in mode:
                        col_names = ['G', 'AK', 'BO', 'CS', 'DW', 'FA', 'GE']
                    elif "尾数" in mode:
                        col_names = ['H', 'AL', 'BP', 'CT', 'DX', 'FB', 'GF']
                    else:
                        col_names = ['D', 'AH', 'BL', 'CP', 'DT', 'EX', 'GB']
    
                    # 遍历每一行（跳过前两行表头）
                    for r in range(3, ws.max_row + 1):
                        p1 = clean_cell(ws.cell(row=r, column=1).value) # A列
                        p2 = clean_cell(ws.cell(row=r, column=2).value) # B列
                        p3 = clean_cell(ws.cell(row=r, column=3).value) # C列
                        year_val = clean_cell(ws.cell(row=r, column=214).value) # HF列(214列)
                        
                        if not p1 and not p2 and not p3: continue
                        if not year_val: year_val = "2026" 
                            
                        period_str = f"{year_val}{p1}{p2}{p3}"
                        
                        # ?? 防覆盖盾：如果这期已经有了，绝对不让后面的脏行覆盖
                        if period_str in grouped_data:
                            continue
                            
                        ball_attrs = []
                        for ball_i in range(7):
                            col_letter = col_names[ball_i]
                            
                            if "数字" in mode:
                                # 数字模式，取当前字母列（十位）和它的下一列（个位）
                                col_idx = column_index_from_string(col_letter)
                                next_col_letter = get_column_letter(col_idx + 1)
                                tens = clean_cell(ws[f"{col_letter}{r}"].value)
                                units = clean_cell(ws[f"{next_col_letter}{r}"].value)
                                if not tens: tens = "0"
                                if not units: units = "0"
                                val = f"{tens}{units}"
                            else:
                                # 生肖和尾数，直接取对应字母列
                                val = clean_cell(ws[f"{col_letter}{r}"].value)
                                
                            ball_attrs.append(val)
                            
                        grouped_data[period_str] = ball_attrs
                            
                    sorted_periods = sorted(list(grouped_data.keys()))
                    
                    if selected_period not in sorted_periods:
                        st.error(f"在历史数据中找不到基准期数 {selected_period}！")
                        st.stop()
                        
                    target_idx = sorted_periods.index(selected_period)
                    base_attrs = grouped_data[selected_period]
                    target_combos = list(itertools.combinations(base_attrs, 3))
                    
                    if "生肖" in mode: all_possible = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
                    elif "尾数" in mode: all_possible = [str(i) for i in range(10)]
                    else: all_possible = [f"{i:02d}" for i in range(1, 50)]
                        
                    freq_dict = {i: {attr: 0 for attr in all_possible} for i in range(7)}
                    hit_count = 0
                    
                    for i in range(target_idx):
                        hist_attrs = grouped_data[sorted_periods[i]]
                        is_hit = any(all(x in hist_attrs for x in combo) for combo in target_combos)
                                
                        if is_hit and i + 1 < target_idx:
                            next_attrs = grouped_data[sorted_periods[i+1]]
                            hit_count += 1
                            for ball_i in range(7):
                                attr = next_attrs[ball_i]
                                if attr in freq_dict[ball_i]:
                                    freq_dict[ball_i][attr] += 1
                                    
                    report_lines = []
                    report_lines.append(f"========== {mode} 3码联动分析 ==========")
                    report_lines.append(f"【基准期数】: {selected_period}")
                    report_lines.append(f"【基准开出】: {', '.join(base_attrs)}")
                    report_lines.append(f"【联动组合数】: 共生成 {len(target_combos)} 个三码组合")
                    report_lines.append(f"【历史命中】: 共找到 {hit_count} 期包含这些组合\\\\n")
                    
                    ball_names = ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"]
                    
                    for ball_i in range(7):
                        sorted_freq = sorted(freq_dict[ball_i].items(), key=lambda x: (-x[1], str(x[0])))
                        top_N = sorted_freq[:pick_num]
                        kills = sorted_freq[pick_num:]
                        
                        top_names = [item[0] for item in top_N]
                        kill_names = [item[0] for item in kills]
                        
                        line = f"{ball_names[ball_i]}: {', '.join(top_names)}"
                        if kill_names:
                            line += f"  | 杀({','.join(kill_names)})"
                        report_lines.append(line)
                        
                    report_lines.append("\\\\n(注：各球位数据完全独立计算，历史频次基于三码组合命中后的下一期真实开出情况)")
                    
                    # ?? 修复了原本的 \\\\\\\\n 换行符，让报告可以直接正常显示
                    st.session_state.deep_linkage_result = "\\\\n".join(report_lines)
                else:
                    st.error(f"?云端文件 {target_file} 读取失败。")
            except Exception as e:
                st.error(f"?分析异常: {e}")

    # ==========================
    # 4. 结果显示与打印
    # ==========================
    if "deep_linkage_result" in st.session_state and st.session_state.deep_linkage_result != "":
        clean_text = st.session_state.deep_linkage_result
        st.text_area("联动分析报告:", value=clean_text, height=400)
        
        import html
        import base64
        import streamlit.components.v1 as components
        
        # 🔥 修复了原本被转义的 \\\\n 换行符
        escaped_text = html.escape(clean_text).replace("\\n", "<br>")
        display_html = f'<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; font-family: Consolas, monospace; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-wrap: break-word; max-height: 500px; overflow-y: auto;">{escaped_text}</div>'
        print_html = f'<html><head><meta charset="utf-8"><style>body {{ font-family: Consolas, monospace; padding: 20px; line-height: 1.8; }} pre {{ white-space: pre-wrap; word-wrap: break-word; font-size: 14px; }}</style></head><body><pre>{html.escape(clean_text)}</pre></body></html>'
        
        b64_display = base64.b64encode(display_html.encode('utf-8')).decode('utf-8')
        b64_print = base64.b64encode(print_html.encode('utf-8')).decode('utf-8')
        
        components.html(
            f"""
            <div id="report-container"></div>
            <div style="margin-top: 15px; text-align: center;">
                <button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold;">🖨️ 打印当前报告</button>
            </div>
            <script>
            function b64DecodeUnicode(str) {{ return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{ return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2); }}).join('')); }}
            document.getElementById('report-container').innerHTML = b64DecodeUnicode("{b64_display}");
            function printReport() {{ var win = window.open(""); win.document.write(b64DecodeUnicode("{b64_print}")); win.document.close(); win.focus(); setTimeout(function() {{ win.print(); }}, 500); }}
            </script>
            """, height=620, scrolling=False
        )

def main_app():
    with st.sidebar:
        st.write("👤 欢迎，" + st.session_state.username)
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
        st.divider()  
        
        # 🔥 带有 Emoji 的导航栏
        menu = st.radio("功能导航：", [
            "🖥️ 主控制台", 
            "📊 同现统计", 
            "🤖 AI推演", 
            "📐 多维分析", 
            "🔗 深度联动"
        ])
        
        st.divider()  

    if "synced_df" in st.session_state and st.session_state.synced_df is not None:
        df_data = st.session_state.synced_df
    else:
        df_data = load_real_data()
    
    # 🔥 使用 'in' 进行模糊匹配（防止 Emoji 乱码导致点不动）
    if "主控制台" in menu: render_console(df_data)
    elif "同现统计" in menu: render_stats(df_data)
    elif "AI推演" in menu: render_ai(df_data)
    elif "多维分析" in menu: render_multi_analysis(df_data)
    elif "深度联动" in menu: render_deep_linkage(df_data)

# ==========================================
# 底部启动代码（这部分千万不能漏）
# ==========================================
if not st.session_state.logged_in: 
    login_page()
else: 
    main_app()
