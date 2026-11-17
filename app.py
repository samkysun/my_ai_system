# -*- coding: utf-8 -*-
"""
智能数据分析系统 —— 整合修订版
================================
相对你原来那版的改动（其余逻辑未动）：
  1. NUM_HE[22] 由 "05合" 修正为 "04合"（2+2=4，与前后邻居一致）
  2. get_supabase_client 不再缓存 None（否则第一次没读到 Secrets 就永久失效）
  3. 新增 register_user / check_credentials，注册与登录的错误按 PostgREST 错误码分类
  4. login_page 重写：区分“用户不存在/密码错误”，注册成功清空表单，去掉 rerun 后不可达的 stop
  5. build_rule_database(debug=True) 返回失败原因，不再只报“规则表读取失败”
  6. call_deepseek_api：超时 60→180 秒、429/5xx 自动重试、system 消息前置、报错带状态码与原文
  7. get_analysis_prompt：压缩输出长度（超时根因），要求输出 FINAL 行
  8. 新增 extract_numbers，取代 re.findall(r'\b([0-4][0-9])\b')（中文旁无词边界，必漏抓）
  9. 补上 .ball / .ball-red 等样式（这三个类名原来被引用但从未定义，号码球是没样式的）

需要额外装的依赖不变：streamlit pandas openpyxl requests supabase
"""

import streamlit as st
import pandas as pd
import hashlib
import time
import os
import itertools
import requests
import openpyxl
import io
import base64
import re
import json
from collections import Counter
from datetime import datetime
from openpyxl.utils import get_column_letter, column_index_from_string
from supabase import create_client

# 两个可选模块：缺失时只影响对应标签页，不影响主程序启动
try:
    from ai_chat_page import render_ai_chat
except Exception:
    render_ai_chat = None
try:
    from auto_upgrade import render_upgrade_tab
except Exception:
    render_upgrade_tab = None
try:
    from omission_page import render_omission_page
except Exception:
    render_omission_page = None

# ==========================================
# 1. 全局配置与初始化
# ==========================================
st.set_page_config(page_title="💻智能数据分析系统", layout="wide")

# 号码球样式（原来只用了类名没有定义，补上）
st.markdown("""
<style>
.ball-container{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0 4px 0}
.ball{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;
      font-size:17px;font-weight:700;color:#fff;box-shadow:0 2px 6px rgba(0,0,0,.18)}
.ball-red{background:linear-gradient(145deg,#ef4444,#b91c1c)}
.ball-blue{background:linear-gradient(145deg,#3b82f6,#1d4ed8)}
.ball-green{background:linear-gradient(145deg,#22c55e,#15803d)}
</style>
""", unsafe_allow_html=True)

EXCEL_FILE = "总数据.xlsx"
SHEET_NAME = "总数据表"
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")


@st.cache_resource
def _make_client(url, key):
    return create_client(url, key)


def get_supabase_client():
    """只有创建成功才进缓存。原版把 None 也缓存了，导致之后改 Secrets 也一直连不上。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return _make_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


# 密码加密（保持原样：已注册用户的哈希依赖它，不可随意改）
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "synced_df" not in st.session_state: st.session_state.synced_df = None
if "calc_data_single" not in st.session_state: st.session_state.calc_data_single = None
if "calc_data_multi" not in st.session_state: st.session_state.calc_data_multi = None
if "calc_result_preview" not in st.session_state: st.session_state.calc_result_preview = None
if "predicted_nums_single" not in st.session_state: st.session_state.predicted_nums_single = None
if "predicted_nums_multi" not in st.session_state: st.session_state.predicted_nums_multi = None

# ==========================================
# 2. 核心引擎：28个属性纯代码计算器
# ==========================================
NUM_WUXING = {1: "水", 2: "火", 3: "火", 4: "金", 5: "金", 6: "土", 7: "土", 8: "木", 9: "木", 10: "火", 11: "火", 12: "金", 13: "金", 14: "水", 15: "水", 16: "木", 17: "木", 18: "火", 19: "火", 20: "土", 21: "土", 22: "水", 23: "水", 24: "木", 25: "木", 26: "金", 27: "金", 28: "土", 29: "土", 30: "水", 31: "水", 32: "火", 33: "火", 34: "金", 35: "金", 36: "土", 37: "土", 38: "木", 39: "木", 40: "火", 41: "火", 42: "金", 43: "金", 44: "水", 45: "水", 46: "木", 47: "木", 48: "火", 49: "火"}
NUM_ZODIAC = {1: "马", 2: "蛇", 3: "龙", 4: "兔", 5: "虎", 6: "牛", 7: "鼠", 8: "猪", 9: "狗", 10: "鸡", 11: "猴", 12: "羊", 13: "马", 14: "蛇", 15: "龙", 16: "兔", 17: "虎", 18: "牛", 19: "鼠", 20: "猪", 21: "狗", 22: "鸡", 23: "猴", 24: "羊", 25: "马", 26: "蛇", 27: "龙", 28: "兔", 29: "虎", 30: "牛", 31: "鼠", 32: "猪", 33: "狗", 34: "鸡", 35: "猴", 36: "羊", 37: "马", 38: "蛇", 39: "龙", 40: "兔", 41: "虎", 42: "牛", 43: "鼠", 44: "猪", 45: "狗", 46: "鸡", 47: "猴", 48: "羊", 49: "马"}
# 注意：22 号原为 "05合"，按各位数字相加应为 04合（2+2=4），已修正
NUM_HE = {1: "01合", 2: "02合", 3: "03合", 4: "04合", 5: "05合", 6: "06合", 7: "07合", 8: "08合", 9: "09合", 10: "01合", 11: "02合", 12: "03合", 13: "04合", 14: "05合", 15: "06合", 16: "07合", 17: "08合", 18: "09合", 19: "10合", 20: "02合", 21: "03合", 22: "04合", 23: "05合", 24: "06合", 25: "07合", 26: "08合", 27: "09合", 28: "10合", 29: "11合", 30: "03合", 31: "04合", 32: "05合", 33: "06合", 34: "07合", 35: "08合", 36: "09合", 37: "10合", 38: "11合", 39: "12合", 40: "04合", 41: "05合", 42: "06合", 43: "07合", 44: "08合", 45: "09合", 46: "10合", 47: "11合", 48: "12合", 49: "13合"}
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
    return [NUM_WUXING.get(n, ""), z, str(tail), NUM_HE.get(n, ""), NUM_MEN.get(n, ""), NUM_DUAN.get(n, ""), NUM_SINGLE_DOUBLE.get(n, ""), "单笔" if z in ["鼠", "龙", "蛇", "马", "鸡", "猪"] else "双笔", "独字" if z in ["鼠", "牛", "虎", "兔", "马", "羊"] else "合字", "单头" if (n // 10) in [1, 3] else "双头", "单数" if n % 2 != 0 else "双数", f"{NUM_BOSE.get(n, '')}{'单数' if n % 2 != 0 else '双数'}", ZODIAC_WUXING.get(z, ""), ZODIAC_COLOR.get(z, ""), ZODIAC_FOUR_TREASURES.get(z, ""), ZODIAC_OBJECT_IMAGE.get(z, ""), NUM_BOSE.get(n, ""), "阳" if z in YANG_ZODIACS else "阴", "家" if z in JIA_ZODIACS else "野", "天" if z in TIAN_ZODIACS else "地", f"{'阳' if z in YANG_ZODIACS else '阴'}{'天' if z in TIAN_ZODIACS else '地'}", "凶" if z in XIONG_ZODIACS else "吉", "男" if z in NAN_ZODIACS else "女", ZODIAC_DIRECTION.get(z, ""), f"3余{tail % 3}", TAIL_WUXING.get(tail, ""), ZODIAC_FU_LU_SHOU.get(z, ""), ZODIAC_SIZE.get(z, "")]

# ==========================================
# 3. 基础数据加载
# ==========================================
def get_ball_color(num):
    red = [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46]
    blue = [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48]
    return "ball-red" if num in red else ("ball-blue" if num in blue else "ball-green")


def clean_period(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    return s[:-2] if s.endswith(".0") else s


@st.cache_data(ttl=86400, show_spinner=False)
def load_real_data():
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")
    file_name = "升序源文件.xlsx"
    if not token or not repo:
        if not os.path.exists(file_name): return None
        try: df_raw = pd.read_excel(file_name, sheet_name="数据源", header=None)
        except Exception as e: return str(e)
    else:
        try:
            url = f"https://api.github.com/repos/{repo}/contents/{file_name}"
            r = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"})
            if r.status_code == 200:
                df_raw = pd.read_excel(io.BytesIO(requests.get(r.json()["download_url"]).content), sheet_name="数据源", header=None)
            else: return "云端源文件读取失败"
        except Exception as e: return str(e)
    try:
        synced_rows = []
        def clean_val(v):
            if pd.isna(v): return ""
            try: return str(int(float(v)))
            except: return str(v).strip()
        for idx, row in df_raw.iterrows():
            year_val = clean_val(row[26]) if len(row) > 26 else ""
            p1, p2, p3 = clean_val(row[0]), clean_val(row[1]), clean_val(row[2])
            if not year_val.isdigit() or not p1.isdigit(): continue
            period_str = f"{year_val}{p1}{p2}{p3}"
            nums = []
            for i in range(7):
                tens, units = clean_val(row[3 + i*2]), clean_val(row[4 + i*2])
                if tens == "" and units == "": nums.append(None)
                else: nums.append(int((tens if tens.isdigit() else "0") + (units if units.isdigit() else "0")))
            new_row = [None] * 30
            new_row[18] = period_str
            for i in range(6): new_row[19+i] = nums[i]
            new_row[25] = nums[6]
            synced_rows.append(new_row)
        result_df = pd.DataFrame(synced_rows)
        try: result_df = result_df.sort_values(by=18, ascending=False).reset_index(drop=True)
        except: pass
        return result_df
    except Exception as e: return f"数据转换异常: {e}"

@st.cache_data(show_spinner=False, ttl=3600)
def load_excel_data(file_path, sheet_name=None):
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")
    def parse_content(content):
        if file_path.lower().endswith(".csv"):
            try: text = content.decode("utf-8-sig")
            except: text = content.decode("gbk", errors="ignore")
            return [[cell.replace('\r', '').replace('\n', '').strip() for cell in line.split(',')] for line in text.splitlines() if line.strip()]
        else:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            return list(wb[sheet_name].iter_rows(values_only=True))
    if not token or not repo:
        try:
            with open(file_path, "rb") as f: return parse_content(f.read())
        except: return []
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200: return parse_content(requests.get(r.json()["download_url"]).content)
        else: return []
    except: return []

# ==========================================
# 4. 核心算法引擎
# ==========================================
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
    special_num = int(clean_period(current_row.iloc[25])) if pd.notna(current_row.iloc[25]) else None
    if len(base_nums) < 6: return None, None, "基准期开奖号码不足6个"
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    if is_descending: start_idx, end_idx = base_idx + 1, len(df_data) - 1
    else: start_idx, end_idx = 0, base_idx - 1
    if start_idx > end_idx: return None, None, "附近没有历史数据"
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
    if matched.empty: return None, f"找不到本期 {target_period}！"
    base_pos = df_data.index.get_loc(matched.index[0])
    next_pos = base_pos - 1
    if next_pos < 0: return {"下期期数": "待开奖", "预测组合": ",".join(predicted_nums), "状态": "本期未开奖"}, "本期未开奖"
    next_row = df_data.iloc[next_pos]
    next_period = clean_period(next_row.iloc[18])
    nums = [clean_period(next_row.iloc[i]) for i in range(19, 25)]
    z_val = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    match_nums = [n for n in nums if n and n in predicted_nums]
    try: match_nums.sort(key=lambda x: int(x))
    except: pass
    z_matched = z_val in predicted_nums if z_val else False
    status = "有命中" if (len(match_nums) > 0 or z_matched) else "无中任何数字"
    result = {"下期期数": next_period, "预测组合": ",".join(predicted_nums), "中出平码1": match_nums[0] if len(match_nums)>0 else "", "中出平码2": match_nums[1] if len(match_nums)>1 else "", "中出平码3": match_nums[2] if len(match_nums)>2 else "", "中出平码4": match_nums[3] if len(match_nums)>3 else "", "中出平码5": match_nums[4] if len(match_nums)>4 else "", "中出平码6": match_nums[5] if len(match_nums)>5 else "", "中出特码": z_val if z_matched else "", "状态": status}
    return result, None

# ==========================================
# 5. 各页面渲染
# ==========================================
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


def render_multi_analysis(df_data):
    st.title("📐多维分析系统")
    if "current_file" not in st.session_state: st.session_state.current_file = "升序全套"
    if "multi_result_text" not in st.session_state: st.session_state.multi_result_text = ""
    if "full_scan_results" not in st.session_state: st.session_state.full_scan_results = []

    ATTR_MAP = {"数字五行": 6, "生肖": 7, "尾数": 8, "数字合": 9, "门数": 10, "段数": 11, "单双组合": 12, "单双笔": 13, "独合字": 14, "单双头": 15, "单双": 16, "波单双": 17, "生肖五行": 18, "颜色肖": 19, "四宝": 20, "物象": 21, "波色": 22, "阴阳": 23, "家野": 24, "天地": 25, "阴阳天地": 26, "吉凶": 27, "男女": 28, "方位": 29, "3模": 30, "尾五行": 31, "福禄寿": 32, "大小肖": 33, "生肖五行相生": 18, "生肖五行相克": 18, "数字五行相生": 6, "数字五行相克": 6, "尾五行相生": 31, "尾五行相克": 31, "生肖五行与数字五行相生": 18, "生肖五行与数字五行相克": 18, "数字五行与生肖五行相生": 6, "数字五行与生肖五行相克": 6}

    st.markdown("### 分析参数设置")
    analysis_mode = st.radio("分析模式：", ["单属性透视 (按球查属性)", "单球全属性透视 (按球查全部)"], horizontal=True)

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    with row1_col1:
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)
        if unique_periods:
            try:
                next_p = str(int(float(unique_periods[0])) + 1)
                if next_p not in unique_periods: unique_periods.insert(0, next_p)
            except: pass
        selected_period = st.selectbox("选择分析/预测期数", unique_periods)
    with row1_col2: selected_file_type = st.selectbox("选择分析文件", ["升序全套", "按序全套"])
    with row1_col3:
        show_attrs = ["生肖", "尾数", "数字合", "数字五行", "门数", "段数", "单双组合", "波单双", "生肖五行", "四宝", "物象", "阴阳天地", "方位", "尾五行", "颜色肖", "波色", "3模", "福禄寿", "大小肖", "生肖五行相生", "生肖五行相克", "数字五行相生", "数字五行相克", "尾五行相生", "尾五行相克", "生肖五行与数字五行相生", "生肖五行与数字五行相克", "数字五行与生肖五行相生", "数字五行与生肖五行相克"]
        selected_attr = st.selectbox("分析属性", show_attrs, index=0)
    with row1_col4:
        ball_str = st.selectbox("基准球号", ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"])
        ball_num = int(ball_str.replace("第", "").split("球")[0])

    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
    with row2_col1: min_len = st.number_input("最少对比行数", min_value=3, max_value=20, value=7)
    with row2_col2: max_len = st.number_input("最多对比行数", min_value=3, max_value=20, value=12)
    with row2_col3:
        st.write(""); st.write("")
        run_btn = st.button("🚀执行分析", use_container_width=True, type="primary")
    with row2_col4:
        st.write(""); st.write("")
        if st.button("☁️刷新云端数据", use_container_width=True, type="secondary"):
            load_excel_data.clear()
            st.toast("✅ 缓存已清空！")
            st.rerun()

    st.divider()

    if run_btn:
        current_sig = f"{selected_file_type}_{selected_period}_{selected_attr}_{ball_str}_{min_len}_{max_len}_{analysis_mode}"
        if st.session_state.get("last_multi_sig") == current_sig and "全属性" not in analysis_mode:
            st.warning("⚠️ 条件未改变，已跳过计算。"); st.stop()
        st.session_state.last_multi_sig = current_sig

        target_file = "升序全套.csv" if selected_file_type == "升序全套" else "按序全套.csv"
        progress_bar = st.progress(0); status_text = st.empty()
        try:
            all_rows = load_excel_data(target_file, None)
            if not all_rows: st.error(f"读取失败"); st.stop()
            progress_bar.progress(20)

            def clean_str(v):
                if v is None: return ""
                try: return str(int(float(v)))
                except: return str(v).replace("\r", "").replace("\n", "").replace(" ", "").strip()

            target_row_idx = -1
            for r_idx in range(len(all_rows)):
                year_val = clean_str(all_rows[r_idx][213]) if len(all_rows[r_idx]) > 213 else "2026"
                p1 = clean_str(all_rows[r_idx][0]) if len(all_rows[r_idx]) > 0 else ""
                p2 = clean_str(all_rows[r_idx][1]) if len(all_rows[r_idx]) > 1 else ""
                p3 = clean_str(all_rows[r_idx][2]) if len(all_rows[r_idx]) > 2 else ""
                if f"{year_val}{p1}{p2}{p3}" == selected_period:
                    target_row_idx = r_idx; break
            if target_row_idx == -1:
                try:
                    prev_period = str(int(selected_period) - 1)
                    for r_idx in range(len(all_rows)):
                        year_val = clean_str(all_rows[r_idx][213]) if len(all_rows[r_idx]) > 213 else "2026"
                        p1 = clean_str(all_rows[r_idx][0]) if len(all_rows[r_idx]) > 0 else ""
                        p2 = clean_str(all_rows[r_idx][1]) if len(all_rows[r_idx]) > 1 else ""
                        p3 = clean_str(all_rows[r_idx][2]) if len(all_rows[r_idx]) > 2 else ""
                        if f"{year_val}{p1}{p2}{p3}" == prev_period:
                            target_row_idx = r_idx
                            st.info(f"💡 自动使用上一期 {prev_period} 作为基准推演。")
                            break
                except: pass
            if target_row_idx == -1: st.error(f"找不到基准期数！"); st.stop()

            cross_sheng = {"金": ["土", "水"], "木": ["水", "火"], "水": ["金", "木"], "火": ["木", "土"], "土": ["火", "金"]}
            cross_ke = {"金": ["木", "火"], "木": ["土", "金"], "水": ["火", "土"], "火": ["金", "水"], "土": ["水", "木"]}
            def get_wx(s):
                core = s.replace("肖", "").replace("号", "").replace("尾", "")
                return {"鼠":"水","牛":"土","虎":"木","兔":"木","龙":"土","蛇":"火","马":"火","羊":"土","猴":"金","鸡":"金","狗":"土","猪":"水"}.get(core, core)

            def do_match(attr_name, attr_base_col, ball_n, min_l, max_l):
                is_cross_mode = attr_name in ["生肖五行与数字五行相生", "生肖五行与数字五行相克", "数字五行与生肖五行相生", "数字五行与生肖五行相克"]
                is_zodiac_to_num = attr_name.startswith("生肖")
                is_cross_sheng = "相生" in attr_name
                is_cross_ke = "相克" in attr_name
                is_sheng_mode = "相生" in attr_name
                is_ke_mode = "相克" in attr_name
                is_normal_mode = not (is_sheng_mode or is_ke_mode) and not is_cross_mode
                wx_suffix = "号" if ("数字" in attr_name or "号" in attr_name) else ("尾" if "尾" in attr_name else ("肖" if "肖" in attr_name else ""))

                ball_cols = [get_column_letter(attr_base_col + (x - 1) * 30) for x in range(1, 8)]
                ref_col_letter = ball_cols[ball_n - 1]
                ref_col_idx_0 = column_index_from_string(ref_col_letter) - 1

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
                    return [(r, clean_str(all_rows[r][col_idx_0]) if col_idx_0 < len(all_rows[r]) else "") for r in range(len(all_rows))]

                ref_col_data = get_col_data(ref_col_idx_0)
                template = []
                for r in range(target_row_idx, len(ref_col_data)):
                    if ref_col_data[r][1]: template.append(ref_col_data[r][1])
                    if len(template) >= max_len: break
                if len(template) < min_l: return []

                results = []
                for n in range(1, 8):
                    target_base_col = (6 if is_zodiac_to_num else 18) if is_cross_mode else attr_base_col
                    col_name = get_column_letter(target_base_col + (n - 1) * 30)
                    current_col_idx = column_index_from_string(col_name) - 1
                    disp_name = f"{n}球({col_name})"
                    is_self = (col_name == ref_col_letter)
                    col_data = get_col_data(current_col_idx)
                    valid_data = [(r, col_data[r][1]) for r in range(2, len(col_data)) if col_data[r][1]]
                    vc = len(valid_data)

                    if vc >= min_l:
                        k = 0
                        while k <= vc - min_l:
                            max_l_hit = 0
                            for j in range(vc - k):
                                if j >= len(template): break
                                if j > 0 and valid_data[k+j][0] != valid_data[k+j-1][0] + 1: break
                                if not check_match(template[j], valid_data[k+j][1]): break
                                max_l_hit = j + 1
                            if max_l_hit >= min_l:
                                real_l = max_l_hit
                                sr = valid_data[k][0]; er = valid_data[k + real_l - 1][0]
                                def get_ctx(r_idx):
                                    if r_idx < 0 or r_idx >= len(col_data): return "无"
                                    v = col_data[r_idx][1]
                                    if not v: return "空"
                                    if is_cross_mode: return f"{v}{'号' if is_zodiac_to_num else '肖'}"
                                    if v in ["鼠","牛","虎","兔","龙","蛇","马","羊","猴","鸡","狗","猪"]: return v + "肖"
                                    if v in ["金", "木", "水", "火", "土"]: return v + wx_suffix
                                    if v.isdigit() and wx_suffix == "尾": return f"{v}尾"
                                    return v

                                w1, w2 = get_ctx(sr-1), get_ctx(er+1)
                                actual_match_str = "".join([x[1] for x in valid_data[k : k + real_l]])
                                display_w1 = w1
                                kill_str = ""
                                if is_cross_mode or is_sheng_mode or is_ke_mode:
                                    core_w1 = w1.replace("号", "").replace("肖", "")[0] if is_cross_mode else get_wx(w1)
                                    t_suffix = ("肖" if is_zodiac_to_num else "号") if is_cross_mode else wx_suffix
                                    if is_cross_sheng or is_sheng_mode:
                                        rule_str = "".join([f"{x}{t_suffix}" for x in cross_sheng.get(core_w1, [])]) if is_cross_mode else {"金": f"水{wx_suffix}土{wx_suffix}", "木": f"水{wx_suffix}火{wx_suffix}", "水": f"金{wx_suffix}木{wx_suffix}", "火": f"土{wx_suffix}木{wx_suffix}", "土": f"金{wx_suffix}火{wx_suffix}"}.get(core_w1, "")
                                        if rule_str: display_w1 = f"{w1} (生{rule_str})"; kill_str = f" (杀{rule_str})"
                                    elif is_cross_ke or is_ke_mode:
                                        rule_str = "".join([f"{x}{t_suffix}" for x in cross_ke.get(core_w1, [])]) if is_cross_mode else {"金": f"火{wx_suffix}木{wx_suffix}", "木": f"土{wx_suffix}金{wx_suffix}", "水": f"火{wx_suffix}土{wx_suffix}", "火": f"水{wx_suffix}金{wx_suffix}", "土": f"木{wx_suffix}水{wx_suffix}"}.get(core_w1, "")
                                        if rule_str: display_w1 = f"{w1} (克{rule_str})"; kill_str = f" (杀{rule_str})"

                                detail_txt = f"上:{display_w1} (匹配:{actual_match_str}) 下:{w2}{kill_str}"
                                if is_self: detail_txt += " [自身参考列匹配]"
                                w1_str = str(w1).strip()
                                if w1_str not in ["空", "无", "", "0", "0.0", "None", "nan"]:
                                    if er + 1 <= 25:
                                        line_txt = f"触发行：{disp_name} 行{sr+1}-{er+1}({real_l}行)近{real_l}期一致: {detail_txt}"
                                        if 5 <= real_l <= 9:
                                            st.session_state.play_alert = True
                                            line_txt = f"[[HIGHLIGHT]]{line_txt}[[/HIGHLIGHT]]"
                                    else: line_txt = f"触发行：{disp_name} 行{sr+1}-{er+1}({real_l}行): {detail_txt}"
                                    results.append(line_txt)
                                k += real_l
                            else: k += 1
                return results

            attr_map_val = ATTR_MAP[selected_attr]
            res_lines = do_match(selected_attr, attr_map_val, ball_num, min_len, max_len)

            base_col_num = attr_map_val + (ball_num - 1) * 30
            base_col_letter = get_column_letter(base_col_num)
            base_col_idx = column_index_from_string(base_col_letter) - 1
            wx_suffix_global = "尾" if "尾" in selected_attr else ""
            base_rows = []
            for r in range(target_row_idx, len(all_rows)):
                val = clean_str(all_rows[r][base_col_idx]) if base_col_idx < len(all_rows[r]) else ""
                if val:
                    if val.isdigit() and wx_suffix_global == "尾": base_rows.append(f"{base_col_letter}{r+1}:{val}尾")
                    else: base_rows.append(f"{base_col_letter}{r+1}:{val}")
                if len(base_rows) >= max_len: break

            if not res_lines:
                st.markdown("""<style>@keyframes slideFadeOut {0% { opacity: 1; max-height: 50px; padding: 12px;} 80% { opacity: 1; max-height: 50px; padding: 12px;} 100% { opacity: 0; max-height: 0; padding: 0; overflow: hidden;}} .auto-hide {background-color:#fef08a; color:#854d0e; border-radius:6px; text-align:center; font-weight:bold; animation: slideFadeOut 2s forwards;}</style><div class="auto-hide">⚠️ 未找到符合条件的匹配记录</div>""", unsafe_allow_html=True)
            else:
                out_txt = f"========== {selected_file_type} - {selected_period} - {selected_attr} - {ball_str} ==========\n【基准行排列】({len(base_rows)}行): {', '.join(base_rows)}\n\n"
                for line in res_lines: out_txt += f"{line}\n"

                if "全属性" in analysis_mode:
                    if out_txt not in st.session_state.full_scan_results:
                        st.session_state.full_scan_results.append(out_txt)
                        st.session_state.multi_result_text = "\n\n".join(st.session_state.full_scan_results)
                else:
                    if st.session_state.multi_result_text != out_txt:
                        st.session_state.full_scan_results = [out_txt]
                        st.session_state.multi_result_text = out_txt

            if st.session_state.get("play_alert", False):
                import streamlit.components.v1 as components
                components.html("""<script>var AudioContext = window.AudioContext || window.webkitAudioContext; var ctx = new AudioContext(); function playCoin() { if (ctx.state === 'suspended') ctx.resume(); var o1 = ctx.createOscillator(), g1 = ctx.createGain(); o1.frequency.setValueAtTime(987.77, ctx.currentTime); g1.gain.setValueAtTime(0.5, ctx.currentTime); g1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime+0.3); o1.connect(g1); g1.connect(ctx.destination); o1.start(); o1.stop(ctx.currentTime+0.3); var o2 = ctx.createOscillator(), g2 = ctx.createGain(); o2.frequency.setValueAtTime(1318.51, ctx.currentTime+0.1); g2.gain.setValueAtTime(0.5, ctx.currentTime+0.1); g2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime+0.4); o2.connect(g2); g2.connect(ctx.destination); o2.start(ctx.currentTime+0.1); o2.stop(ctx.currentTime+0.4);} playCoin();</script>""", height=0, width=0)
                st.session_state.play_alert = False
            progress_bar.progress(100); status_text.success(f"✅ 计算完成：{selected_attr} | {ball_str}")
        except Exception as e: st.error(f"计算报错: {e}")

    st.divider()
    col_title, col_btn = st.columns([8, 2])
    with col_title: st.subheader("详细结果 (累积报告)")
    with col_btn:
        if st.button("🗑️清空所有结果", use_container_width=True):
            st.session_state.multi_result_text = ""
            st.session_state.full_scan_results = []
            st.rerun()

    if st.session_state.multi_result_text != "":
        import streamlit.components.v1 as components
        import html
        import base64
        clean_text = st.session_state.multi_result_text.replace(chr(92) + 'n', chr(10)).replace(chr(92) + 'r', '')
        with st.expander("📝手动编辑/精简当前报告 (点击展开)", expanded=False):
            st.markdown('<style>div[data-testid="stTextArea"] textarea { font-size: 20px !important; line-height: 1.8 !important; }</style>', unsafe_allow_html=True)
            edited_text = st.text_area("删掉你不想看的内容，然后点下方保存：", value=clean_text, height=300)
            if st.button("💾保存修改并更新结果", type="secondary"):
                st.session_state.multi_result_text = edited_text
                st.rerun()

        escaped_text = html.escape(clean_text).replace("\n", "<br>")
        highlighted_display = escaped_text.replace("[[HIGHLIGHT]]", '<span style="color: #dc2626; background-color: #fef08a; font-weight: bold; padding: 2px 4px; border-radius: 4px;">').replace("[[/HIGHLIGHT]]", '</span>')
        display_html = f"""<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; font-family: Consolas, monospace; font-size: 20px; line-height: 2.2; white-space: pre-wrap; word-wrap: break-word; max-height: 480px; overflow-y: auto; text-align: center;">{highlighted_display}</div>"""
        print_html = f"""<html><head><meta charset="utf-8"><style>body {{ font-family: Consolas, monospace; padding: 20px; line-height: 1.8; text-align: center; }} pre {{ white-space: pre-wrap; word-wrap: break-word; font-size: 14px; text-align: center; }}</style></head><body><pre>{html.escape(clean_text)}</pre></body></html>"""
        b64_display = base64.b64encode(display_html.encode('utf-8')).decode('utf-8')
        b64_print = base64.b64encode(print_html.encode('utf-8')).decode('utf-8')

        components.html(f"""<div id="report-container"></div><div style="margin-top: 15px; text-align: center;"><button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold;">🖨️ 打印当前报告</button></div><script>function b64DecodeUnicode(str) {{ return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{ return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2); }}).join('')); }} document.getElementById('report-container').innerHTML = b64DecodeUnicode("{b64_display}"); function printReport() {{ var win = window.open(""); win.document.write(b64DecodeUnicode("{b64_print}")); win.document.close(); win.focus(); setTimeout(function() {{ win.print(); }}, 500); }}</script>""", height=620, scrolling=False)

        file_name = f"报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        st.download_button(label="📥 保存完整报告到本地 (TXT格式)", data=clean_text.encode('utf-8-sig'), file_name=file_name, mime="text/plain", use_container_width=True)


def render_deep_linkage(df_data):
    st.title("🔗 深度联动分析系统")
    st.info("💡 功能说明：提取基准期开奖号码的属性组合，在全历史数据中寻找相同组合，并统计命中后下一期各球位的属性频次。")
    st.divider()
    st.markdown("### 分析参数设置")
    col1, col2, col3, col4 = st.columns(4)
    with col1: mode = st.selectbox("分析模式", ["升序生肖", "按序生肖", "升序尾数", "按序尾数", "升序数字", "按序数字"])
    with col2:
        if df_data is not None and not isinstance(df_data, str):
            unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
            try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
            except: unique_periods.sort(reverse=True)
        else: unique_periods = ["暂无数据"]
        selected_period = st.selectbox("基准期数", unique_periods)
    with col3:
        pick_num = st.number_input("预测前N名", min_value=4, max_value=9, value=5) if "生肖" in mode else st.number_input("预测前N名", min_value=3, max_value=7, value=5)
    with col4:
        st.write(""); st.write("")
        run_btn = st.button("🚀执行联动分析", use_container_width=True, type="primary")

    if "升序" in mode: target_file = "升序全套.csv"
    else: target_file = "按序全套.csv"
    sheet_name = None
    st.info(f"💡当前读取文件：【{target_file}】 (CSV 极速模式)")

    if run_btn:
        with st.spinner(f"正在读取并统计..."):
            import csv
            try:
                all_rows = load_excel_data(target_file, sheet_name)
                if not all_rows: st.error(f"读取失败！"); st.stop()
                grouped_data = {}
                def clean_cell(c):
                    if c is None: return ""
                    try: return str(int(float(c)))
                    except: return str(c).strip()

                if "生肖" in mode: col_names = ['G', 'AK', 'BO', 'CS', 'DW', 'FA', 'GE']
                elif "尾数" in mode: col_names = ['H', 'AL', 'BP', 'CT', 'DX', 'FB', 'GF']
                else: col_names = ['D', 'AH', 'BL', 'CP', 'DT', 'EX', 'GB']

                for r_idx in range(2, len(all_rows)):
                    row = all_rows[r_idx]
                    def get_val(c_idx): return clean_cell(row[c_idx]) if c_idx < len(row) else ""
                    p1, p2, p3 = get_val(0), get_val(1), get_val(2)
                    year_val = get_val(213) or "2026"
                    if not p1 and not p2 and not p3: continue
                    period_str = f"{year_val}{p1}{p2}{p3}"
                    if period_str in grouped_data: continue
                    ball_attrs = []
                    for ball_i in range(7):
                        col_letter = col_names[ball_i]
                        col_idx = column_index_from_string(col_letter)
                        if "数字" in mode:
                            tens, units = get_val(col_idx - 1), get_val(col_idx)
                            val = f"{tens or '0'}{units or '0'}"
                        else: val = get_val(col_idx - 1)
                        ball_attrs.append(val)
                    grouped_data[period_str] = ball_attrs

                sorted_periods = sorted(list(grouped_data.keys()))
                if selected_period not in sorted_periods: st.error(f"找不到基准期数 {selected_period}！"); st.stop()
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
                            if next_attrs[ball_i] in freq_dict[ball_i]: freq_dict[ball_i][next_attrs[ball_i]] += 1

                report_lines = [f"========== {mode} 3码联动分析 ==========", f"【基准期数】: {selected_period}", f"【基准开出】: {', '.join(base_attrs)}", f"【联动组合数】: 共生成 {len(target_combos)} 个三码组合", f"【历史命中】: 共找到 {hit_count} 期包含这些组合\n"]
                ball_names = ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"]

                # 回测：取基准期的下一期真实开出值，用于高亮命中
                next_attrs = None
                if target_idx + 1 < len(sorted_periods):
                    next_attrs = grouped_data[sorted_periods[target_idx + 1]]

                for ball_i in range(7):
                    sorted_freq = sorted(freq_dict[ball_i].items(), key=lambda x: (-x[1], str(x[0])))
                    top_names = [item[0] for item in sorted_freq[:pick_num]]
                    kill_names = [item[0] for item in sorted_freq[pick_num:]]
                    line = f"{ball_names[ball_i]}: {', '.join(top_names)}"
                    if "数字" not in mode and kill_names:
                        line += f"  | 杀({','.join(kill_names)})"
                    report_lines.append(line)
                report_lines.append("\n(注：各球位数据完全独立计算，历史频次基于三码组合命中后的下一期真实开出情况)")
                st.session_state.deep_linkage_result = "\n".join(report_lines)

                # 生成带高亮的 HTML 报告
                import html as _html
                hl_style = "background-color:#fef08a;color:#dc2626;font-weight:bold;padding:1px 4px;border-radius:4px;"
                html_parts = []
                html_parts.append(f"<div style='font-family:Consolas,monospace;font-size:16px;line-height:2.0;'>")
                html_parts.append(f"<div style='font-weight:bold;font-size:18px;margin-bottom:8px;'>{_html.escape(mode)} 3码联动分析</div>")
                html_parts.append(f"<div>【基准期数】: {_html.escape(str(selected_period))}</div>")
                html_parts.append(f"<div>【基准开出】: {_html.escape(', '.join(base_attrs))}</div>")
                html_parts.append(f"<div>【联动组合数】: 共生成 {len(target_combos)} 个三码组合</div>")
                html_parts.append(f"<div>【历史命中】: 共找到 {hit_count} 期包含这些组合</div>")
                if next_attrs is not None:
                    html_parts.append(f"<div style='color:#64748b;'>【回测校对】: 下一期 {_html.escape(str(sorted_periods[target_idx + 1]))} 开出 {_html.escape(', '.join(next_attrs))}</div>")
                else:
                    html_parts.append("<div style='color:#64748b;'>【回测校对】: 基准期之后暂无开奖数据，不做高亮</div>")
                html_parts.append("<hr style='margin:10px 0;'>")

                for ball_i in range(7):
                    sorted_freq = sorted(freq_dict[ball_i].items(), key=lambda x: (-x[1], str(x[0])))
                    top_names = [item[0] for item in sorted_freq[:pick_num]]
                    kill_names = [item[0] for item in sorted_freq[pick_num:]]
                    actual = next_attrs[ball_i] if next_attrs is not None else None
                    hit = actual is not None and actual in top_names

                    chips = []
                    for name in top_names:
                        safe = _html.escape(str(name))
                        if hit and name == actual:
                            chips.append(f"<span style='{hl_style}'>{safe} ✔</span>")
                        else:
                            chips.append(f"<span>{safe}</span>")
                    line_html = f"<div style='margin:4px 0;'><b>{ball_names[ball_i]}</b>: " + ", ".join(chips)
                    if "数字" not in mode and kill_names:
                        line_html += f"  <span style='color:#94a3b8;'>| 杀({_html.escape(','.join(str(x) for x in kill_names))})</span>"
                    if hit:
                        line_html += f"  <span style='color:#16a34a;font-weight:bold;'>[命中 {_html.escape(str(actual))}]</span>"
                    elif actual is not None:
                        line_html += f"  <span style='color:#94a3b8;'>[实开 {_html.escape(str(actual))}]</span>"
                    line_html += "</div>"
                    html_parts.append(line_html)

                html_parts.append("<div style='color:#64748b;margin-top:10px;'>(注：各球位数据完全独立计算，历史频次基于三码组合命中后的下一期真实开出情况；红底黄字为回测命中项)</div>")
                html_parts.append("</div>")
                st.session_state.deep_linkage_html = "".join(html_parts)
            except Exception as e: st.error(f"分析异常: {e}")

    if st.session_state.get("deep_linkage_html"):
        st.markdown("### 深度联动分析报告（回测命中高亮）")
        st.markdown(st.session_state.deep_linkage_html, unsafe_allow_html=True)
        with st.expander("📄 查看纯文本版报告", expanded=False):
            st.text_area("深度联动分析报告", value=st.session_state.get("deep_linkage_result", ""), height=300)
    elif st.session_state.get("deep_linkage_result"):
        st.text_area("深度联动分析报告", value=st.session_state.deep_linkage_result, height=400)


def render_ai(df_data):
    st.title("🧠 AI 严谨推演系统")
    if df_data is not None and not isinstance(df_data, str):
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)
        if unique_periods and unique_periods[0] != "暂无数据":
            latest_period = unique_periods[0]
            try:
                next_period = str(int(float(latest_period)) + 1)
                if next_period not in unique_periods: unique_periods.insert(0, next_period)
            except: pass
    else: unique_periods = ["暂无数据"]

    if "reset_version" not in st.session_state: st.session_state.reset_version = 0
    v_prefix = f"v{st.session_state.reset_version}_chk_"
    CHECKBOX_MAP = {
        "金肖": "杀金肖（猴鸡），", "木肖": "杀木肖（虎兔），", "水肖": "杀水肖（鼠猪），", "火肖": "杀火肖（蛇马），", "土肖": "杀土肖（牛龙羊狗），", "红肖": "杀红肖（马兔鼠鸡），", "蓝肖": "杀蓝肖（虎猴蛇猪），", "绿肖": "杀绿肖（龙狗牛羊），",
        "0尾": "杀0尾，", "1尾": "杀1尾，", "2尾": "杀2尾，", "3尾": "杀3尾，", "4尾": "杀4尾，", "5尾": "杀5尾，", "6尾": "杀6尾，", "7尾": "杀7尾，", "8尾": "杀8尾，", "9尾": "杀9尾，",
        "杀鼠": "杀鼠，", "杀牛": "杀牛，", "杀虎": "杀虎，", "杀兔": "杀兔，", "杀龙": "杀龙，", "杀蛇": "杀蛇，", "杀马": "杀马，", "杀羊": "杀羊，", "杀猴": "杀猴，", "杀鸡": "杀鸡，", "杀狗": "杀狗，", "杀猪": "杀猪，",
        "1门": "杀1门，", "2门": "杀2门，", "3门": "杀3门，", "4门": "杀4门，", "5门": "杀5门，",
        "1段": "杀1段，", "2段": "杀2段，", "3段": "杀3段，", "4段": "杀4段，", "5段": "杀5段，", "6段": "杀6段，", "7段": "杀7段，",
        "01合": "杀01合，", "02合": "杀02合，", "03合": "杀03合，", "04合": "杀04合，", "05合": "杀05合，", "06合": "杀06合，", "07合": "杀07合，", "08合": "杀08合，", "09合": "杀09合，", "10合": "杀10合，", "11合": "杀11合，", "12合": "杀12合，", "13合": "杀13合，",
        "红波": "杀红波，", "蓝波": "杀蓝波，", "绿波": "杀绿波，", "红波单": "杀红波单，", "红波双": "杀红波双，", "蓝波单": "杀蓝波单，", "蓝波双": "杀蓝波双，", "绿波单": "杀绿波单，", "绿波双": "杀绿波双，",
        "金号": "杀金号，", "木号": "杀木号，", "水号": "杀水号，", "火号": "杀火号，", "土号": "杀土号，", "金尾": "杀金尾，", "木尾": "杀木尾，", "水尾": "杀水尾，", "火尾": "杀火尾，", "土尾": "杀土尾，",
        "大肖": "杀大肖，", "中肖": "杀中肖，", "小肖": "杀小肖，", "书肖": "杀书肖，", "琴肖": "杀琴肖，", "棋肖": "杀棋肖，", "画肖": "杀画肖，", "福肖": "杀福肖，", "禄肖": "杀禄肖，", "寿肖": "杀寿肖，",
        "家臣": "杀家臣，", "美女": "杀美女，", "君王": "杀君王，", "恶人": "杀恶人，", "东": "杀东肖，", "南": "杀南肖，", "西": "杀西肖，", "北": "杀北肖，",
        "双双": "杀双双，", "双单": "杀双单，", "单单": "杀单单，", "单双": "杀单双，", "阳天": "杀阳天，", "阳地": "杀阳地，", "阴天": "杀阴天，", "阴地": "杀阴地，", "3余0": "杀3余0，", "3余1": "杀3余1，", "3余2": "杀3余2，"
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

    def _fmt_nums(nums):
        return ",".join(f"{n:02d}" for n in sorted(set(nums)))

    def _nums_by(pred):
        return [n for n in range(1, 50) if pred(n)]

    def expand_condition(key):
        """恢复原来的直出模式：直接返回 CHECKBOX_MAP 中的文本；仅 04合 额外补上号码范围。"""
        if key == "04合":
            nums = _nums_by(lambda n: NUM_HE.get(n) == "04合")
            return f"杀04合（{_fmt_nums(nums)}），"
        return CHECKBOX_MAP.get(key, "")

    col1, col2, col3 = st.columns(3)
    with col1: qishu = st.selectbox("选择期数：", unique_periods, index=0)
    with col2: qiu = st.selectbox("选择球数：", ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"], index=0)
    with col3: order_type = st.radio("核算模式：", ["升序", "按序"], horizontal=True)

    st.divider()
    checked_texts = []
    for key in CHECKBOX_MAP.keys():
        if st.session_state.get(f"{v_prefix}{key}", False): checked_texts.append(expand_condition(key))
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        extra = st.session_state.get("ai_extra_condition", "")
        full_text = get_prefix(qishu, qiu, order_type) + "".join(checked_texts) + extra
        st.text_area("已选核算条件：", value=full_text, height=200, disabled=True)

        b1, b2 = st.columns(2)
        with b1:
            if st.button("🚀 开始推演 (呼叫 API)", use_container_width=True, type="primary"):
                if not checked_texts: st.warning("请先勾选！")
                else:
                    question = full_text + f"\n请严格根据以上文本中的【取值区间】和所有【排杀条件】（括号内已列出每个条件对应的具体号码，必须逐号核对，不得自行推断），一步步详细列出推导过程，最终核算{qiu}剩余什么生肖与号码。要求：\n1) 对区间内每一个号码，逐一列出它触犯了哪些排杀条件（写清条件名），触犯即剔除；\n2) 若区间内号码被全部杀光，则从触犯次数最少的号码中后补：先取只触犯 1 个条件的号码；若没有只触犯 1 个条件的，再取触犯 2 个条件的号码；触犯 3 个及以上的一律不得进入 FINAL；\n3) 输出必须包含【逐条剔除】【保留结果】【FINAL】三节，FINAL 行只放最终号码。"
                    with st.spinner("正在呼叫 DeepSeek 进行全量推演（最长 180 秒）..."):
                        db, rules_err = build_rule_database(debug=True)
                        if not db:
                            st.error(f"规则表读取失败：{rules_err}")
                        else:
                            system_prompt = get_analysis_prompt(build_full_table_text(db))
                            answer = call_deepseek_api(question, system_prompt)
                            st.session_state.ai_api_result = answer
                            if "请求失败" in answer or "运行错误" in answer:
                                st.error(f"AI 接口报错：{answer}")
                                st.session_state.ai_ball_result = []
                            else:
                                st.success("✅ AI 推演成功！")
                                st.session_state.ai_ball_result = extract_numbers(answer)

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
            for i in range(1, 13):
                with cols[(i+11) % 3]: st.checkbox(f"{i:02d}合", key=f"{v_prefix}{i:02d}合")
            with cols[(13+11) % 3]: st.checkbox("13合", key=f"{v_prefix}13合")
            with cols[(14+11) % 3]: st.checkbox("04合", key=f"{v_prefix}04合_extra")
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
            cols = st.columns(4)
            for idx, key in enumerate(["家臣", "美女", "君王", "恶人"]):
                with cols[idx % 4]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("方位专属"):
            cols = st.columns(4)
            for idx, key in enumerate(["东", "南", "西", "北"]):
                with cols[idx % 4]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("单双组合"):
            cols = st.columns(4)
            for idx, key in enumerate(["双双", "双单", "单单", "单双"]):
                with cols[idx % 4]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("阴阳天地 / 3模"):
            cols = st.columns(3)
            for idx, key in enumerate(["阳天", "阳地", "阴天", "阴地", "3余0", "3余1", "3余2"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")

    st.divider()
    st.markdown("### 📝 AI 完整推演结果")
    if st.session_state.ai_api_result and st.session_state.ai_api_result != "等待推演...":
        import streamlit.components.v1 as components
        import html
        import base64
        clean_ai_text = st.session_state.ai_api_result.replace('\\\\n', '\\n').replace('\\\\\\\\n', '\\n').replace("【严格筛选结果】", "").replace("【后补筛选结果】", "").replace("(如果有的话)", "").strip()
        table_header = f"#============={qishu}期{order_type}{qiu}核算结果======================"
        full_result_text = f"{table_header}\n\n{clean_ai_text}"
        escaped_header, escaped_body = html.escape(table_header), html.escape(clean_ai_text).replace("\n", "<br>").replace("\\\\n", "<br>")
        display_html = f"""<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; font-family: Consolas, monospace; max-height: 500px; overflow-y: auto;"><div style="text-align: center; font-weight: bold; font-size: 18px; margin-bottom: 20px; color: #1e293b;">{escaped_header}</div><div style="text-align: left; font-size: 15px; line-height: 2.2; color: #334155;">{escaped_body}</div></div>"""
        print_html = f"""<html><head><meta charset="utf-8"><style>@page {{ margin: 15mm; }} body {{ font-family: Consolas, monospace; padding: 20px; }} .header {{ text-align: center; font-weight: bold; font-size: 16px; margin-bottom: 25px; }} .body {{ text-align: left; line-height: 2.2; font-size: 14px; white-space: pre-wrap; word-wrap: break-word; }}</style></head><body><div class="header">{escaped_header}</div><div class="body">{escaped_body}</div></body></html>"""
        b64_display = base64.b64encode(display_html.encode('utf-8')).decode('utf-8')
        b64_print = base64.b64encode(print_html.encode('utf-8')).decode('utf-8')
        components.html(f"""<div id="report-container"></div><div style="margin-top: 15px; text-align: center;"><button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold;">🖨️ 打印当前推演报告</button></div><script>function b64DecodeUnicode(str) {{ return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{ return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2); }}).join('')); }} document.getElementById('report-container').innerHTML = b64DecodeUnicode("{b64_display}"); function printReport() {{ var win = window.open(""); win.document.write(b64DecodeUnicode("{b64_print}")); win.document.close(); win.focus(); setTimeout(function() {{ win.print(); }}, 500); }}</script>""", height=620, scrolling=False)
        st.write("")
        st.download_button(label="📥 保存完整推演报告到本地 (TXT格式)", data=full_result_text.encode('utf-8-sig'), file_name=f"AI推演_{qishu}_{qiu}_{order_type}.txt", mime="text/plain", use_container_width=True)
    else: st.info("👈 请先在上方设置参数，然后点击【开始推演】。")

# ==========================================
# 6. AI 相关：规则库 / 提示词 / 调用 / 提取
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def build_rule_database(debug=False):
    """debug=True 时返回 (db, 错误原因)，否则只返回 db 或 None。"""
    try:
        client = get_supabase_client()
    except Exception as e:
        msg = f"Supabase 客户端创建失败：{e}"
        return (None, msg) if debug else None
    if not client:
        msg = "Supabase 客户端为空：Secrets 里缺 SUPABASE_URL 或 SUPABASE_KEY。"
        return (None, msg) if debug else None

    try:
        response = client.table("rules").select("*").execute()
    except Exception as e:
        msg = f"读取 rules 表失败：{e}"
        return (None, msg) if debug else None

    rows = getattr(response, "data", None) or []
    if not rows:
        msg = "rules 表是空的，或 RLS 让本次查询返回 0 行。"
        return (None, msg) if debug else None

    db = {}
    for row in rows:
        num_raw = row.get("号码")
        if num_raw is None: continue
        try: n = str(int(float(num_raw)))
        except: continue
        db[n] = {"生肖": str(row.get("生肖", "")), "肖五行": str(row.get("肖五行", "")), "号五行": str(row.get("号五行", "")), "尾五行": str(row.get("尾五行", "")), "波色": str(row.get("波色", "")), "大小": str(row.get("大小", "")), "物象": str(row.get("物象", "")), "人物": str(row.get("人物", "")), "合数": str(row.get("合数", "")), "方位": str(row.get("方位", ""))}

    if not db:
        msg = "rules 表有数据，但「号码」列一个都没解析出来（列名或类型不对）。"
        return (None, msg) if debug else None
    return (db, "") if debug else db


def build_full_table_text(db):
    result = "【1-49号完整属性表（绝对权威）】\n"
    for i in range(1, 50):
        if str(i) in db:
            info = db[str(i)]
            tens, units = i // 10, i % 10
            if tens % 2 == 0 and units % 2 == 0: combo = "双双"
            elif tens % 2 == 0 and units % 2 == 1: combo = "双单"
            elif tens % 2 == 1 and units % 2 == 1: combo = "单单"
            else: combo = "单双"
            direction = info.get('方位', '无')
            result += f"{i}号:{{生肖:{info['生肖']}, 肖五行:{info['肖五行']}, 号五行:{info['号五行']}, 尾五行:{info['尾五行']}, 物象:{info['物象']}, 人物:{info['人物']}, 大小:{info['大小']}, 波色:{info['波色']}, 合数:{info['合数']}, 方位:{direction}, 单双组合:{combo}}}\n"
    return result


def get_analysis_prompt(full_table):
    return f"""你是一个精通集合运算与条件排除的推演助手。以下是 1-49 号号码的绝对属性参照表：
{full_table}

【推演与输出规则】
1. 用户的提问已明确给出了排杀条件和【取值区间】。请从该区间内挑选号码，区间外的号码绝对不能选。然后严格从区间内剔除不符合条件的号码。
2. 注意多重条件叠加，比如一个号码可能同时触犯了多个排杀条件。
3. 输出结构固定为三节，不要写客套话：
   【逐条剔除】每个被剔除的号一行，格式：`07号：触犯杀木肖 → 剔除`。最终保留的号不要列在这一节。
   【保留结果】保留的号，每个一行，写明号码、生肖、五行。
   【FINAL】单独一行，只放最终号码，两位数字、英文逗号分隔，例如：
   FINAL: 01,05,12,23,38
4. 若区间内全被杀光，则从「只触犯 1~2 个排杀条件」的号里挑后补写进 FINAL；触犯 3 个及以上条件的绝对不进 FINAL。
5. 绝对禁止复述属性表，禁止复述以上规则，直接给出三节内容。
6. 注意用户选择的是升序还是按序作为条件限制。"""


def _deepseek_headers():
    key = (DEEPSEEK_API_KEY or "").strip()
    if not key:
        try: key = str(st.secrets.get("DEEPSEEK_API_KEY", "")).strip()
        except Exception: key = ""
    if not key:
        return None, "未读到 DEEPSEEK_API_KEY（Secrets 缺键时会静默返回空串，改完需要 Reboot app）"
    if not key.startswith("sk-"):
        return None, f"DEEPSEEK_API_KEY 格式异常：应以 sk- 开头，当前长度 {len(key)}"
    return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, None


def _explain_status(status, body):
    tail = (body or "").strip().replace("\n", " ")[:300]
    table = {400: "报文格式被拒", 401: "Key 无效或为空 —— 余额再足也没用，说明 Key 与账号对不上",
             402: "该账号余额不足", 403: "无权限", 422: "参数非法",
             429: "触发频率限制", 500: "服务端错误", 502: "网关错误", 503: "服务繁忙"}
    return f"HTTP {status}｜{table.get(status, '未知错误')}｜{tail}"


def call_deepseek_api(question, system_prompt, max_tokens=8192, timeout=180, retries=3):
    """超时 180 秒；429/5xx 自动重试；system 消息前置。"""
    headers, err = _deepseek_headers()
    if err: return f"请求失败：{err}"

    payload = {
        "model": "deepseek-chat",
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    }
    last = ""
    for attempt in range(retries):
        try:
            response = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=timeout)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            return f"运行错误：{last}"

        if response.status_code == 200:
            try:
                content = response.json()["choices"][0]["message"]["content"]
            except Exception:
                return f"请求失败：返回体无法解析｜{response.text[:300]}"
            for token in ("**", "###", "##", "`"):
                content = content.replace(token, "")
            content = re.sub(r"(?m)^#[^\n]*\n?", "", content)
            return content.strip()

        last = _explain_status(response.status_code, response.text)
        if response.status_code in (429, 500, 502, 503) and attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1)); continue
        return f"请求失败：{last}"
    return f"请求失败：{last}"


def extract_numbers(answer, lo=1, hi=49):
    """从 AI 输出里提取号码。FINAL 行优先，其次保留结果段，最后按“NN号”兜底。"""
    if not answer: return []
    text = str(answer)

    def _nums(seg):
        out = []
        for tok in re.findall(r"\d{1,2}", seg or ""):
            n = int(tok)
            if lo <= n <= hi: out.append(n)
        return out

    # 1) FINAL 行
    for m in re.finditer(r"FINAL[\]】\s]*[：:]?\s*([0-9][^\n\r]*)", text, re.I):
        got = _nums(m.group(1))
        if got: return sorted(set(got))

    # 2) 保留结果段
    keep = re.search(r"(?:保留结果|严格筛选结果|剩余号码|筛选结果)\s*[：:]?([\s\S]{0,1500})", text)
    if keep:
        seg = re.split(r"【|\n\s*(?:注|说明|后补)", keep.group(1))[0]
        got = _nums(seg)
        if got: return sorted(set(got))

    # 3) 所有“NN号”写法
    got = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})\s*号", text)]
    return sorted(set(n for n in got if lo <= n <= hi))

# ==========================================
# 7. 主控台
# ==========================================
def render_console(df_data):
    st.title("💻智能数据分析总控台")
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：" + str(EXCEL_FILE)); return
    unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
    try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    except: unique_periods.sort(reverse=True)
    if unique_periods:
        latest_period = unique_periods[0]
        try:
            next_period = str(int(float(latest_period)) + 1)
            if next_period not in unique_periods: unique_periods.insert(0, next_period)
        except: pass

    col1, col2 = st.columns(2)
    with col1: selected_period = st.selectbox("选择期数：", unique_periods)
    with col2: analysis_mode = st.radio("模式切换：", ["单排分析", "多排分析"], horizontal=True)

    st.write("")
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    start_btn = b1.button("⚡批量联动分析", use_container_width=True, type="primary")
    result_btn = b2.button("🏆中奖结果", use_container_width=True)
    clear_btn = b3.button("🗑️清空数据", use_container_width=True)
    sync_btn = b4.button("🔄同步数据", use_container_width=True)
    trend_btn = b5.button("📈走势图", use_container_width=True)
    fetch_btn = b6.button("🤏抓取香港数据", use_container_width=True)

    st.divider()
    df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
    matched_rows = df_data[df_data['_temp_period'] == selected_period]
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
        if next_special_num > 0: balls_html += f'<div style="font-size: 32px; font-weight: bold; color: #64748b; display: flex; align-items: center; margin: 0 5px;">+</div><div class="ball {get_ball_color(next_special_num)}">{next_special_num:02d}</div>'
        balls_html += '</div>'
        st.markdown(balls_html, unsafe_allow_html=True)
    else:
        try: next_period_str = str(int(float(selected_period)) + 1)
        except: next_period_str = "下一期"
        st.subheader(f"{next_period_str} 期开奖结果")
        st.info(f"{next_period_str} 期待开奖（暂无数据）")

    if fetch_btn:
        with st.spinner("发送抓取指令..."):
            try:
                token = st.secrets.get("GITHUB_TOKEN"); repo = st.secrets.get("GITHUB_REPO")
                url = f"https://api.github.com/repos/{repo}/actions/workflows/update_data.yml/dispatches"
                res = requests.post(url, headers={"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {token}"}, json={"ref": "main"})
                if res.status_code == 204: st.success("✅ 指令已发送！请稍后点击【同步数据】。")
                else: st.error(f"指令发送失败: {res.status_code}")
            except Exception as e: st.error(f"请求异常：{e}")

    if sync_btn:
        with st.spinner("同步数据中..."):
            FILE_SORTED = "升序源文件.xlsx"
            if os.path.exists(FILE_SORTED):
                try:
                    wb_src = openpyxl.load_workbook(FILE_SORTED, read_only=True, data_only=True)
                    ws_src = wb_src["数据源"]
                    synced_rows = []
                    for row in ws_src.iter_rows(min_row=3, max_col=27):
                        p1, p2, p3 = row[0].value, row[1].value, row[2].value
                        if p1 is None: continue
                        nums = [int(str(row[3 + i*2].value or 0))*10 + int(str(row[4 + i*2].value or 0)) for i in range(7)]
                        new_row = [None]*30
                        new_row[18] = f"{row[26].value or '2026'}{str(int(p1))}{str(int(p2))}{str(int(p3))}"
                        for i in range(6): new_row[19+i] = nums[i]
                        new_row[25] = nums[6]
                        synced_rows.append(new_row)
                    wb_src.close()
                    st.session_state.synced_df = pd.DataFrame(synced_rows).sort_values(by=18, ascending=False).reset_index(drop=True)
                    st.success("✅ 数据同步成功！"); st.rerun()
                except Exception as e: st.error(f"同步异常: {e}")
            else: st.error(f"找不到 {FILE_SORTED}")

    if trend_btn: render_trend_chart(df_data)
    if clear_btn:
        st.session_state.calc_data_single = None; st.session_state.calc_data_multi = None; st.session_state.calc_result_preview = None; st.session_state.predicted_nums_single = None; st.session_state.predicted_nums_multi = None
        st.success("✅ 数据已清空！")
    if start_btn:
        progress_bar = st.progress(0); status_text = st.empty()
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
        if not predicted_nums: st.warning("请先点击【批量联动分析】！")
        else:
            with st.spinner("比对中..."):
                res_data, err = calculate_prize(df_data, selected_period, predicted_nums)
                if err == "本期未开奖": st.warning(f"⏳ {selected_period} 期的下期未开奖！")
                elif err: st.error(err)
                else: st.success("预祝您中奖！"); st.session_state.calc_result_preview = pd.DataFrame([res_data])

    st.divider()
    col_lb1, col_lb2 = st.columns(2)
    with col_lb1:
        st.subheader("单排结果")
        if st.session_state.calc_data_single is not None:
            st.dataframe(st.session_state.calc_data_single[0], use_container_width=True, height=200)
            st.dataframe(st.session_state.calc_data_single[1], use_container_width=True, height=200)
        else: st.info("暂无单排数据。")
    with col_lb2:
        st.subheader("多排结果")
        if st.session_state.calc_data_multi is not None:
            st.dataframe(st.session_state.calc_data_multi[0], use_container_width=True, height=200)
            st.dataframe(st.session_state.calc_data_multi[1], use_container_width=True, height=200)
        else: st.info("暂无多排数据。")
    st.divider()
    st.subheader("中出结果预览")
    if st.session_state.calc_result_preview is not None: st.dataframe(st.session_state.calc_result_preview, use_container_width=True)
    else: st.info("暂无中出结果。")

# ==========================================
# 8. 管理员专属后台管理页
# ==========================================
def render_admin_panel():
    st.title("⚙️ 系统后台管理中心")
    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["👑 用户 VIP 授权", "📝 数据录入与同步",
                                           "☁️ 云端数据流转", "💬 AI 助手", "🛠️ 自动升级"])

    with tab1:
        try:
            client = get_supabase_client()
            if client:
                users = client.table("users").select("username, is_vip").neq("username", admin_name).execute().data
                if users:
                    user_dict = {row["username"]: row.get("is_vip", False) for row in users}
                    all_users = list(user_dict.keys())
                    current_vips = [u for u, is_vip in user_dict.items() if is_vip]
                    selected_vips = st.multiselect("选择授权用户（允许查看高级页面）：", all_users, default=current_vips)
                    if st.button("💾 保存授权更改", type="primary"):
                        client.table("users").update({"is_vip": False}).neq("username", admin_name).execute()
                        if selected_vips:
                            client.table("users").update({"is_vip": True}).in_("username", selected_vips).execute()
                        st.success("✅ 授权已更新！")
                else: st.warning("暂无其他注册用户。")
        except Exception as e: st.error(f"读取失败: {e}")

    with tab2:
        st.markdown("### 📝 手动补录开奖数据 (云端同步)")
        with st.form("manual_input_form", clear_on_submit=True):
            st.info("💡 提示：保存后，数据将直接更新到 GitHub 云端的两个 Excel 源文件中，并插入第 3 行。")
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
                if not year_val or not p1 or not p2 or not p3: st.error("年份和期号不能为空！")
                elif len(set(nums)) < 7: st.error("录入的 7 个号码中有重复，请检查！")
                else:
                    raw_nums = nums.copy()
                    asc_nums = sorted(nums[:6]) + [nums[6]]
                    if not token or not repo: st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        def update_github_excel(file_path, nums_list, commit_msg):
                            try:
                                api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
                                headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                                r = requests.get(api_url, headers=headers)
                                if r.status_code != 200: return False, f"找不到云端文件或API错误: {r.status_code}"
                                file_info = r.json()
                                sha = file_info["sha"]
                                download_url = file_info["download_url"]
                                file_content = requests.get(download_url).content

                                wb = openpyxl.load_workbook(io.BytesIO(file_content))
                                if "数据源" not in wb.sheetnames: return False, "源文件中找不到“数据源”工作表"
                                ws = wb["数据源"]

                                def get_cell_str(r, c):
                                    v = ws.cell(row=r, column=c).value
                                    return str(v).replace(".0", "").strip() if v is not None else ""

                                current_year = str(year_val).replace(".0", "").strip()
                                for row_idx in range(3, ws.max_row + 1):
                                    if get_cell_str(row_idx, 27) == current_year and get_cell_str(row_idx, 1) == p1 and get_cell_str(row_idx, 2) == p2 and get_cell_str(row_idx, 3) == p3:
                                        return False, f"{current_year}年的 {p1}-{p2}-{p3} 期已经存在！"

                                ws.insert_rows(3)
                                ws.cell(row=3, column=1, value=p1); ws.cell(row=3, column=2, value=p2)
                                ws.cell(row=3, column=3, value=p3); ws.cell(row=3, column=27, value=year_val)
                                for i, num in enumerate(nums_list):
                                    ws.cell(row=3, column=4 + i*2, value=str(num // 10))
                                    ws.cell(row=3, column=5 + i*2, value=str(num % 10))

                                output = io.BytesIO(); wb.save(output)
                                b64_content = base64.b64encode(output.getvalue()).decode('utf-8')
                                payload = {"message": commit_msg, "content": b64_content, "sha": sha, "branch": "main"}
                                put_res = requests.put(api_url, headers=headers, json=payload)
                                return (True, "成功") if put_res.status_code in [200, 201] else (False, put_res.text)
                            except Exception as e: return False, str(e)

                        with st.spinner("覆盖更新中..."):
                            s1, m1 = update_github_excel("升序源文件.xlsx", asc_nums, f"更新升序数据 {year_val}-{p1}{p2}{p3}")
                            s2, m2 = update_github_excel("按序源文件.xlsx", raw_nums, f"更新按序数据 {year_val}-{p1}{p2}{p3}")
                            if s1 and s2:
                                st.success("✅数据已永久存入 GitHub 云端！")
                                load_real_data.clear()
                            else:
                                if not s1: st.error(f"❌ 升序文件同步失败: {m1}")
                                if not s2: st.error(f"❌ 按序文件同步失败: {m2}")

    with tab3:
        st.markdown("### ☁️ 云端数据流转控制台")
        col_sync1, col_sync2 = st.columns(2)

        with col_sync1:
            if st.button("🚀 同步【升序源文件】至【总数据表】", use_container_width=True, type="primary"):
                with st.spinner("正在合并总表..."):
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

                            m_file = "总数据.xlsx"
                            m_info = get_info(m_file)
                            if not m_info: st.error("找不到总数据文件"); st.stop()

                            wb = openpyxl.load_workbook(io.BytesIO(requests.get(m_info["download_url"]).content))
                            ws = wb["总数据表"]

                            if ws.max_row > 2: ws.delete_rows(3, ws.max_row)

                            def clean_val(v):
                                if pd.isna(v) or v is None: return ""
                                try: return str(int(float(v)))
                                except: return str(v).strip()

                            row_idx = 3
                            for idx, row in df_src.iterrows():
                                if idx < 2: continue
                                p1, p2, p3 = clean_val(row[0]), clean_val(row[1]), clean_val(row[2])
                                if not p1 and not p2 and not p3: continue
                                y_val = clean_val(row[26]) if len(row) > 26 else "2026"

                                ws.cell(row=row_idx, column=1, value=p1); ws.cell(row=row_idx, column=2, value=p2); ws.cell(row=row_idx, column=3, value=p3)

                                for i in range(7):
                                    t = clean_val(row[3 + i*2]) if len(row) > 3 + i*2 else ""
                                    u = clean_val(row[4 + i*2]) if len(row) > 4 + i*2 else ""
                                    ws.cell(row=row_idx, column=4 + i*2, value=t)
                                    ws.cell(row=row_idx, column=5 + i*2, value=u)

                                ws.cell(row=row_idx, column=19, value=f"{y_val}{p1}{p2}{p3}")

                                for i in range(7):
                                    t = clean_val(row[3 + i*2]) if len(row) > 3 + i*2 else ""
                                    u = clean_val(row[4 + i*2]) if len(row) > 4 + i*2 else ""
                                    num = int(t)*10 + int(u) if t.isdigit() and u.isdigit() else 0
                                    if i < 6: ws.cell(row=row_idx, column=20 + i, value=num)
                                    else: ws.cell(row=row_idx, column=26, value=num)

                                ws.cell(row=row_idx, column=27, value=y_val)
                                row_idx += 1

                            out = io.BytesIO(); wb.save(out)
                            res = requests.put(f"https://api.github.com/repos/{repo}/contents/{m_file}", headers=headers, json={"message": "更新总数据表", "content": base64.b64encode(out.getvalue()).decode('utf-8'), "sha": m_info["sha"], "branch": "main"})

                            if res.status_code in [200, 201]:
                                st.success("✅ 总数据表已完美更新！")
                                load_real_data.clear()
                            else: st.error(f"❌ 推送失败: {res.text}")
                        except Exception as e: st.error(f"异常: {e}")

        with col_sync2:
            if st.button("🚀 一键计算属性并同步全套表", use_container_width=True, type="secondary"):
                with st.spinner("正在计算 214 列属性并同步..."):
                    if not token or not repo:
                        st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        try:
                            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                            def get_info(fp):
                                r = requests.get(f"https://api.github.com/repos/{repo}/contents/{fp}", headers=headers)
                                return r.json() if r.status_code == 200 else None

                            def sync_attrs(src_f, dst_f, table_name):
                                import csv
                                s_info = get_info(src_f)
                                if not s_info: return False, f"找不到 {src_f}"
                                wb_src = openpyxl.load_workbook(io.BytesIO(requests.get(s_info["download_url"]).content), data_only=True)
                                ws_src = wb_src["数据源"]

                                def clean_val(cell):
                                    if cell is None: return ""
                                    val = str(cell).strip()
                                    if val.endswith(".0"): val = val[:-2]
                                    return val

                                p1, p2, p3 = clean_val(ws_src["A3"].value), clean_val(ws_src["B3"].value), clean_val(ws_src["C3"].value)
                                year_val = clean_val(ws_src["AA3"].value) or "2026"
                                period_str = f"{year_val}{p1}{p2}{p3}"

                                d_info = get_info(dst_f)
                                if not d_info: return False, f"找不到 {dst_f}"
                                csv_content = requests.get(d_info["download_url"]).content

                                try: text = csv_content.decode("utf-8-sig")
                                except: text = csv_content.decode("gbk", errors="ignore")

                                all_rows = list(csv.reader(io.StringIO(text)))
                                if not all_rows: return False, f"{dst_f} 数据为空"

                                if len(all_rows) > 2:
                                    exist_row = all_rows[2]
                                    if len(exist_row) >= 214 and f"{exist_row[213]}{exist_row[0]}{exist_row[1]}{exist_row[2]}" == period_str:
                                        return True, f"该期 ({period_str}) 已存在，跳过同步"

                                new_row_dict = {}
                                for n_idx in range(7):
                                    tens = clean_val(ws_src.cell(row=3, column=4 + n_idx*2).value)
                                    units = clean_val(ws_src.cell(row=3, column=5 + n_idx*2).value)
                                    ball_num = int((tens if tens.isdigit() else "0") + (units if units.isdigit() else "0")) if (tens or units) else 0

                                    base_col = 4 + n_idx * 30
                                    new_row_dict[str(base_col)] = str(ball_num // 10) if ball_num else ""
                                    new_row_dict[str(base_col+1)] = str(ball_num % 10) if ball_num else ""

                                    if ball_num:
                                        attrs = calculate_all_attributes(ball_num)
                                        for a_idx, attr_val in enumerate(attrs): new_row_dict[str(base_col + 2 + a_idx)] = str(attr_val)
                                    else:
                                        for a_idx in range(28): new_row_dict[str(base_col + 2 + a_idx)] = ""

                                new_row_dict["1"], new_row_dict["2"], new_row_dict["3"] = p1, p2, p3
                                new_row_dict["214"] = year_val

                                all_rows.insert(2, [new_row_dict.get(str(i), "") for i in range(1, 215)])

                                out_io = io.StringIO()
                                csv.writer(out_io).writerows(all_rows)
                                b64_content = base64.b64encode(out_io.getvalue().encode('utf-8-sig')).decode('utf-8')

                                res = requests.put(f"https://api.github.com/repos/{repo}/contents/{dst_f}", headers=headers, json={"message": f"更新 {dst_f}", "content": b64_content, "sha": d_info["sha"], "branch": "main"})

                                if res.status_code not in [200, 201]: return False, res.text

                                try:
                                    client = get_supabase_client()
                                    if client: client.table(table_name).upsert({"期数": period_str, "data": new_row_dict}, on_conflict="期数").execute()
                                except: pass

                                return True, "成功"

                            s1, m1 = sync_attrs("升序源文件.xlsx", "升序全套.csv", "full_asc")
                            s2, m2 = sync_attrs("按序源文件.xlsx", "按序全套.csv", "full_desc")

                            if s1 and s2:
                                st.success(f"✅ 极速同步成功！\n升序：{m1}\n按序：{m2}")
                                load_excel_data.clear()
                            else:
                                if not s1: st.error(f"❌ 升序失败: {m1}")
                                if not s2: st.error(f"❌ 按序失败: {m2}")
                        except Exception as e:
                            st.error(f"运行异常: {e}")

    # --- 标签 4：AI 对话助手 ---
    with tab4:
        if render_ai_chat:
            render_ai_chat()
        else:
            st.warning("缺少 ai_chat_page.py —— 需与 app.py 同目录并一起提交到 GitHub 仓库。")

    # --- 标签 5：自动升级 ---
    with tab5:
        if render_upgrade_tab:
            render_upgrade_tab()
        else:
            st.warning("缺少 auto_upgrade.py —— 需与 app.py 同目录并一起提交到 GitHub 仓库。")

# ==========================================
# 9. 登录与系统入口
# ==========================================
def register_user(username, password):
    """返回 (是否成功, 提示)。错误按 PostgREST 错误码分类，界面能看懂卡在哪。"""
    client = get_supabase_client()
    if not client:
        return False, "数据库连接失败：没读到 SUPABASE_URL / SUPABASE_KEY。改完 Secrets 必须 Reboot app。"
    u = (username or "").strip()
    p = password or ""
    if len(u) < 2: return False, "用户名至少 2 个字符（首尾空格会被去掉）"
    if len(p) < 4: return False, "密码至少 4 位"
    if any(ch.isspace() for ch in u): return False, "用户名不能包含空格"
    try:
        client.table("users").insert({"username": u, "password": hash_password(p), "is_vip": False}).execute()
        return True, f"注册成功！请到【登录】页签用 {u} 登录。"
    except Exception as e:
        code = str(getattr(e, "code", "") or "")
        raw = str(e)
        if code == "23505" or "duplicate key" in raw or "unique constraint" in raw:
            return False, "该用户名已被注册（也可能你连点了两次注册，先去表里看一下）"
        if code == "42501" or "row-level security" in raw:
            return False, '写入被拒：users 表开了 RLS 但没有 INSERT 策略。SQL: create policy "signup insert" on public.users for insert to anon with check (true);'
        if code == "PGRST204" or "schema cache" in raw:
            return False, "users 表缺少 is_vip 列。SQL: alter table public.users add column if not exists is_vip boolean not null default false;"
        if code == "PGRST205" or "Could not find the table" in raw:
            return False, "找不到 users 表：确认在 public schema，然后 Settings -> API -> Reload schema。"
        if "401" in raw or "Invalid API key" in raw:
            return False, "SUPABASE_KEY 无效（Key 格式过旧或已轮换）"
        return False, f"注册失败：{raw[:300]}"


def check_credentials(username, password):
    """返回 (是否通过, 提示)。区分“用户不存在”和“密码错误”。"""
    client = get_supabase_client()
    if not client: return False, "数据库连接失败：请检查 SUPABASE_URL / SUPABASE_KEY"
    u = (username or "").strip()
    try:
        rows = client.table("users").select("username,password").eq("username", u).execute().data
    except Exception as e:
        return False, f"查询出错（users 表是否存在？）: {str(e)[:200]}"
    if not rows: return False, "该用户名不存在，请先注册"
    if rows[0].get("password") != hash_password(password or ""): return False, "密码错误"
    return True, "登录成功"


def login_page():
    st.title("🔐 智能系统客户端登录")
    tab1, tab2 = st.tabs(["已有账号？登录", "没有账号？立即注册"])

    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    admin_pass = st.secrets.get("ADMIN_PASSWORD", "")

    # ---- 登录
    with tab1:
        login_user = st.text_input("用户名", key="login_user")
        login_pass = st.text_input("密码", type="password", key="login_pass")
        if st.button("登录", use_container_width=True, type="primary"):
            u = (login_user or "").strip()
            if not u or not login_pass:
                st.warning("用户名和密码都要填")
            elif u == admin_name:
                if login_pass == admin_pass or hash_password(login_pass) == admin_pass:
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.success("👑 管理员登录成功！")
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.error("管理员密码错误")
            else:
                ok, msg = check_credentials(u, login_pass)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.success("登录成功，正在进入系统…")
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.error(msg)

    # ---- 注册
    # widget 一旦渲染就不能再改它的 session_state，所以清空表单要放在渲染之前
    if st.session_state.pop("_clear_reg_form", False):
        for k in ("reg_user", "reg_pass", "reg_confirm"):
            st.session_state.pop(k, None)
    # rerun 会冲掉 success，所以提示先存起来，渲染前再弹
    if st.session_state.get("_reg_done_msg"):
        st.success(st.session_state.pop("_reg_done_msg"))

    with tab2:
        reg_user = st.text_input("设置用户名", key="reg_user")
        reg_pass = st.text_input("密码", type="password", key="reg_pass")
        reg_confirm = st.text_input("确认密码", type="password", key="reg_confirm")
        if st.button("注册账号", use_container_width=True):
            if not reg_user or not reg_pass:
                st.warning("用户名和密码都要填")
            elif reg_pass != reg_confirm:
                st.error("两次输入的密码不一致")
            else:
                ok, msg = register_user(reg_user, reg_pass)
                if ok:
                    st.session_state["_clear_reg_form"] = True
                    st.session_state["_reg_done_msg"] = msg
                    st.rerun()
                else:
                    st.error(msg)


def main_app():
    current_user = st.session_state.username
    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    is_admin = (current_user == admin_name)

    is_vip = False
    if not is_admin:
        client = get_supabase_client()
        if client:
            try:
                res = client.table("users").select("is_vip").eq("username", current_user).execute().data
                if res and res[0].get("is_vip") == True: is_vip = True
            except: pass

    df_data = load_real_data()

    with st.sidebar:
        st.markdown("欢迎来到AI精算中心")
        st.write(f"👤 **{current_user}**")
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()
        st.divider()

        menu_options = ["📊 主控台"]
        if is_admin or is_vip: menu_options.extend(["📐 多维分析", "🔗 深度联动", "🧠 AI推演", "📉 遗漏核算"])
        if is_admin: menu_options.append("⚙️ 后台管理")

        page = st.radio("导航菜单", menu_options)
        st.divider()

    if page == "📊 主控台": render_console(df_data)
    elif page == "📐 多维分析": render_multi_analysis(df_data)
    elif page == "🔗 深度联动": render_deep_linkage(df_data)
    elif page == "🧠 AI推演": render_ai(df_data)
    elif page == "📉 遗漏核算":
        if render_omission_page:
            render_omission_page()
        else:
            st.warning("缺少 omission_page.py —— 需与 app.py 同目录并一起提交到 GitHub 仓库。")
    elif page == "⚙️ 后台管理": render_admin_panel()


if not st.session_state.logged_in:
    login_page()
else:
    main_app()
