import streamlit as st
import pandas as pd
import hashlib
import time
import os
import itertools
from collections import Counter
import requests
import openpyxl

# ==========================================
# ⚙️ 配置区
# ==========================================
EXCEL_FILE = "数据分析系统最终版本(智能全套).xlsm"
SHEET_NAME = "总数据" 
USER_FILE = "users.csv"

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
    if not os.path.exists(USER_FILE):
        pd.DataFrame(columns=['username', 'password']).to_csv(USER_FILE, index=False)
    return pd.read_csv(USER_FILE)

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

@st.cache_data
def load_real_data():
    if not os.path.exists(EXCEL_FILE): return None
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
        return df.dropna(how='all')
    except Exception as e:
        return str(e)
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
    tab1, tab2 = st.tabs(["登录", "注册新账号"])
    with tab1:
        user = st.text_input("用户名", key="login_user")
        pwd = st.text_input("密码", type="password", key="login_pass")
        if st.button("登录", use_container_width=True):
            if user and pwd:
                users_df = load_users()
                hashed = hashlib.sha256(pwd.encode()).hexdigest()
                match = users_df[(users_df['username'] == user) & (users_df['password'] == hashed)]
                if not match.empty:
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    st.rerun()
                else: st.error("用户名或密码错误！")
    with tab2:
        reg_user = st.text_input("设置用户名", key="reg_user")
        reg_pwd = st.text_input("设置密码", type="password", key="reg_pass")
        reg_confirm = st.text_input("确认密码", type="password", key="reg_confirm")
        if st.button("注册", use_container_width=True):
            if reg_user and reg_pwd:
                if reg_pwd != reg_confirm: st.error("两次密码不一致")
                else:
                    users_df = load_users()
                    if reg_user in users_df['username'].values: st.error("该用户名已被注册")
                    else:
                        new_user = pd.DataFrame({'username': [reg_user], 'password': [hashlib.sha256(reg_pwd.encode()).hexdigest()]})
                        pd.concat([users_df, new_user], ignore_index=True).to_csv(USER_FILE, index=False)
                        st.success("注册成功！请去左侧登录。")

def render_console(df_data):
    st.title("智能数据分析总控台")
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：" + str(EXCEL_FILE))
        return
    unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
    try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    except: unique_periods.sort(reverse=True)
    
    col1, col2 = st.columns(2)
    with col1: selected_period = st.selectbox("选择期数：", unique_periods)
    with col2: analysis_mode = st.radio("模式切换：", ["单排分析", "多排分析"], horizontal=True)
    
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
    st.title("🤖 AI 严谨推演系统")
    
    if df_data is not None and not isinstance(df_data, str):
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)
    else: unique_periods = ["暂无数据"]

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
@st.cache_data(show_spinner=False)
def load_excel_data(file_path, sheet_name):
    return pd.read_excel(file_path, sheet_name=sheet_name, header=None)

def render_multi_analysis(df_data):
    st.title("多维分析系统")
    
    if "current_attr" not in st.session_state: st.session_state.current_attr = "生肖"
    if "current_file" not in st.session_state: st.session_state.current_file = "升序全套"
    if "multi_results_dict" not in st.session_state: st.session_state.multi_results_dict = {}
    if "multi_result_text" not in st.session_state: st.session_state.multi_result_text = ""

    # 绝对列号字典
    ATTR_MAP = {
        "数字五行": 6, "生肖": 7, "尾数": 8, "数字合": 9, "门数": 10, "段数": 11,
        "单双组合": 12, "单双笔": 13, "独合字": 14, "单双头": 15, "单双": 16, "波单双": 17,
        "生肖五行": 18, "颜色肖": 19, "四宝": 20, "物象": 21, "波色": 22, "阴阳": 23,
        "家野": 24, "天地": 25, "阴阳天地": 26, "吉凶": 27, "男女": 28, "方位": 29,
        "3模": 30, "尾五行": 31, "福禄寿": 32, "大小肖": 33,
        "生肖五行相生": 18, "生肖五行相克": 18,
        "数字五行相生": 6, "数字五行相克": 6,
        "尾五行相生": 31, "尾五行相克": 31,
        "生肖与五行相生": 18, "生肖与五行相克": 18
    }

    st.markdown("### 分析参数设置")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1: selected_file_type = st.selectbox("选择分析文件", ["升序全套", "按序全套"])
    with col2: selected_attr = st.selectbox("分析属性", list(ATTR_MAP.keys()), index=1) 
    with col3:
        ball_options = ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"]
        ball_str = st.selectbox("基准球号", ball_options)
        ball_num = int(ball_str.replace("第", "").split("球")[0])
    with col4: min_len = st.number_input("最少对比行数", min_value=3, max_value=20, value=7)
    with col5: max_len = st.number_input("最多分组行数", min_value=3, max_value=20, value=12)
    with col6:
        st.write("")
        st.write("")
        run_btn = st.button("执行当前球分析", use_container_width=True, type="primary")

    check_excel_col = ATTR_MAP[selected_attr] + (ball_num - 1) * 30
    check_col_letter = get_column_letter(check_excel_col)
    st.info(f"💡 校验信息：属性【{selected_attr}】的【{ball_str}】锁定在 {check_col_letter} 列")

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
        is_normal_mode = not (is_sheng_mode or is_ke_mode)
        
        # 🔥 唯一改动：动态判断后缀是“号”、“肖”还是“尾”
        if "数字" in selected_attr or "号" in selected_attr:
            wx_suffix = "号"
        elif "尾" in selected_attr:
            wx_suffix = "尾"
        elif "肖" in selected_attr:
            wx_suffix = "肖"
        else:
            wx_suffix = ""
        
        if selected_file_type == "升序全套":
            target_file = "升序全套.xlsx"
            sheet_name = "升序全套分析"
        else:
            target_file = "按序全套.xlsx"
            sheet_name = "按序全套分析"
            
        if not os.path.exists(target_file):
            st.error(f"找不到文件：{target_file}")
        else:
            # 进度条功能原封不动
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("正在读取 Excel 数据...")
                df = load_excel_data(target_file, sheet_name)
                progress_bar.progress(20)
                
                base_excel_col = ATTR_MAP[selected_attr]
                ref_excel_col = base_excel_col + (ball_num - 1) * 30
                ref_col_idx = ref_excel_col - 1 
                
                def clean_str(v):
                    if pd.isna(v): return ""
                    return str(v).replace("\\r", "").replace("\\n", "").replace(" ", "").strip()
                    
                def get_wx(s):
                    core = s.replace("肖", "").replace("号", "").replace("尾", "")
                    zx2wx = {"鼠":"水","牛":"土","虎":"木","兔":"木","龙":"土","蛇":"火","马":"火","羊":"土","猴":"金","鸡":"金","狗":"土","猪":"水"}
                    return zx2wx.get(core, core)
                    
                def check_match(a, b):
                    if is_normal_mode: return a == b
                    core_a, core_b = get_wx(a), get_wx(b)
                    child = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
                    mother = {"金": "土", "土": "火", "火": "木", "木": "水", "水": "金"}
                    ke_dict = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
                    if is_sheng_mode: return (child.get(core_a) == core_b) or (mother.get(core_a) == core_b)
                    elif is_ke_mode: return (ke_dict.get(core_a) == core_b) or (ke_dict.get(core_b) == core_a)
                    return False
                
                status_text.text("正在提取基准列...")
                ref_col_data = [clean_str(x) for x in df.iloc[:, ref_col_idx].tolist()]
                
                template = []
                for r in range(2, len(ref_col_data)):
                    if ref_col_data[r]:
                        template.append(ref_col_data[r])
                    if len(template) >= max_len: break
                        
                if len(template) < min_len:
                    progress_bar.empty()
                    status_text.empty()
                    st.warning(f"基准列数据不足 {min_len} 个")
                    st.stop()
                    
                gColl = {i: [] for i in range(min_len, max_len + 1)}
                
                status_text.text("正在扫描匹配项...")
                for n in range(1, 8):
                    current_excel_col = base_excel_col + (n - 1) * 30
                    current_col_idx = current_excel_col - 1
                    col_name = get_column_letter(current_excel_col)
                    disp_name = f"{n}球({col_name})"
                    is_self = (current_excel_col == ref_excel_col)
                    
                    col_data = [clean_str(x) for x in df.iloc[:, current_col_idx].tolist()]
                    valid_data = [(r, col_data[r]) for r in range(2, len(col_data)) if col_data[r]]
                            
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
                                real_l = max_l
                                group_l = min(real_l, max_len)
                                sr = valid_data[k][0]
                                er = valid_data[k + real_l - 1][0]
                                
                                # 上下文自动补全
                                def get_ctx(r_idx):
                                    if r_idx < 0 or r_idx >= len(col_data): return "无"
                                    v = col_data[r_idx]
                                    if not v: return "空"
                                    if v in ["鼠","牛","虎","兔","龙","蛇","马","羊","猴","鸡","狗","猪"]:
                                        return v + "肖"
                                    if v in ["金", "木", "水", "火", "土"]:
                                        return v + wx_suffix # 🔥 动态后缀
                                    # 🔥 新增的智能后缀补齐逻辑：
                                    if selected_attr == "尾数": return v if "尾" in v else v + "尾"
                                    if selected_attr == "数字合": return v if "合" in v else v + "合"
                                    if selected_attr == "门数": return v if "门" in v else v + "门"
                                    if selected_attr == "段数": return v if "段" in v else v + "段"
                                    if selected_attr == "颜色肖": return v if "肖" in v else v + "肖"
                                    if selected_attr == "四宝": return v if "肖" in v else v + "肖"
                                    if selected_attr == "波色": return v if "波" in v else v + "波"
                                    if selected_attr == "单双头": return v if "头" in v else v + "头"
                                    if selected_attr == "单双笔": return v if "笔" in v else v + "笔"    
                                    return v
                                    
                                w1, w2, w3, w4 = get_ctx(sr-1), get_ctx(er+1), get_ctx(er+2), get_ctx(er+3)
                                
                                if is_normal_mode:
                                    detail_txt = f"上:{w1} 下:{w2} 再下:{w3} 再再下:{w4}"
                                else:
                                    core_w1 = get_wx(w1)
                                    
                                    # 🔥 动态生成生克字典
                                    sheng_dict = {
                                        "金": f"水{wx_suffix}土{wx_suffix}", "木": f"水{wx_suffix}火{wx_suffix}", 
                                        "水": f"金{wx_suffix}木{wx_suffix}", "火": f"土{wx_suffix}木{wx_suffix}", "土": f"金{wx_suffix}火{wx_suffix}"
                                    }
                                    ke_dict = {
                                        "金": f"火{wx_suffix}木{wx_suffix}", "木": f"土{wx_suffix}金{wx_suffix}", 
                                        "水": f"火{wx_suffix}土{wx_suffix}", "火": f"水{wx_suffix}金{wx_suffix}", "土": f"木{wx_suffix}水{wx_suffix}"
                                    }
                                    
                                    if is_sheng_mode:
                                        rule_str = sheng_dict.get(core_w1, "")
                                        full_w1 = f"{w1} (生{rule_str})" if rule_str else w1
                                        sha_str = f"本期杀{rule_str}。" if rule_str else ""
                                    else:
                                        rule_str = ke_dict.get(core_w1, "")
                                        full_w1 = f"{w1} (克{rule_str})" if rule_str else w1
                                        sha_str = f"本期杀{rule_str}。" if rule_str else ""
                                    detail_txt = f"上:{full_w1} 下:{w2} 再下:{w3} 再再下:{w4}。{sha_str}"
                                    
                                if is_self: detail_txt += " [自身参考列匹配]"

                                # 1. 先把 w1 转成纯文本去掉多余空格
                                w1_str = str(w1).strip()
                                # 2. 只要不在这个黑名单里(0尾 不在里面，所以0尾会被保留
                                if w1_str not in ["空", "无", "", "0", "0.0", "None", "nan"]:
                                    # 原有的25行以内判断
                                    if er + 1 <= 25:
                                        line_txt = f"{disp_name} 行{sr+1}-{er+1}({real_l}行)近{real_l}期一致: {detail_txt}"
                                    else:
                                        line_txt = f"{disp_name} 行{sr+1}-{er+1}({real_l}行): {detail_txt}"
                                    
                                    # 只有通过了上面的判断，才会加入到最终结果中
                                    gColl[group_l].append({"line": line_txt, "sr": sr})
                                    # 🔥 新增：如果命中5到9期一致，就打个标记
                                    if 5 <= real_l <= 9:
                                        st.session_state.play_alert = True
                                        # 用特殊的占位符包裹起来
                                        line_txt = f"[[HIGHLIGHT]]{line_txt}[[/HIGHLIGHT]]"
                                # 无论是否加入结果，k 都要前进，防止死循环
                                k += real_l
                            else:
                                k += 1
                                
                progress_bar.progress(90)
                status_text.text("正在整理报告...")
                
                ball_lines = []
                ball_lines.append(f"========== {selected_file_type} - {selected_attr} - {ball_str} ==========")
                
                minSr = 999999
                finalC = []
                for L in range(min_len, max_len + 1):
                    for item in gColl[L]:
                        if item["sr"] < 500:
                            if item["sr"] < minSr:
                                minSr = item["sr"]
                                finalC = [item]
                            elif item["sr"] == minSr:
                                finalC.append(item)
                                
                #if finalC:
                    #ball_lines.append("起始行最近且<500行:")
                    #for item in finalC:
                        #ball_lines.append(item["line"])
                        #ball_lines.append("")

                for L in range(min_len, max_len + 1):
                    if not gColl[L]: continue
                    ball_lines.append(f"--- 连续{L}行匹配（共{len(gColl[L])}处）---")
                    for item in gColl[L]:
                        ball_lines.append(item["line"])
                        ball_lines.append("")
                
                ball_text = "\n".join(ball_lines)

                st.session_state.multi_results_dict[ball_num] = ball_text
                
                combined_text = []
                for i in range(1, 8):
                    if i in st.session_state.multi_results_dict:
                        combined_text.append(st.session_state.multi_results_dict[i])
                        
                st.session_state.multi_result_text = "\n\n\n".join(combined_text)
                # ================= 新增声音提醒 =================
                # 只要标记为 True，就说明检测到了 5-9 期一致的数据
                if st.session_state.get("play_alert", False):
                    import streamlit.components.v1 as components
                    components.html(
                        """
                        <script>
                        var AudioContext = window.AudioContext || window.webkitAudioContext;
                        var ctx = new AudioContext();
                        function playCoin() {
                            if (ctx.state === 'suspended') ctx.resume();
                            var osc1 = ctx.createOscillator();
                            var gain1 = ctx.createGain();
                            osc1.type = 'sine';
                            osc1.frequency.setValueAtTime(987.77, ctx.currentTime);
                            gain1.gain.setValueAtTime(0.5, ctx.currentTime);
                            gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
                            osc1.connect(gain1);
                            gain1.connect(ctx.destination);
                            osc1.start();
                            osc1.stop(ctx.currentTime + 0.3);
                
                            var osc2 = ctx.createOscillator();
                            var gain2 = ctx.createGain();
                            osc2.type = 'sine';
                            osc2.frequency.setValueAtTime(1318.51, ctx.currentTime + 0.1);
                            gain2.gain.setValueAtTime(0.5, ctx.currentTime + 0.1);
                            gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
                            osc2.connect(gain2);
                            gain2.connect(ctx.destination);
                            osc2.start(ctx.currentTime + 0.1);
                            osc2.stop(ctx.currentTime + 0.4);
                        }
                        playCoin();
                        </script>
                        """,
                        height=0, width=0
                    )
                    st.session_state.play_alert = False
                # =================================================
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
        
        # 1. 清理文本
        clean_text = st.session_state.multi_result_text.replace('\r', '')
        # 一步到位：转义 + 换行 + 替换高亮标签
        safe_text = html.escape(clean_text).replace("\\n", "<br>").replace("[[HIGHLIGHT]]", '<span style="color: #dc2626; background-color: #fef08a; font-weight: bold; padding: 2px 4px; border-radius: 4px;">').replace("[[/HIGHLIGHT]]", '</span>')
        
        # 🔥 新增：把占位符替换成真正的 HTML 高亮标签（红字+黄底加粗）
        safe_text = safe_text.replace("[[HIGHLIGHT]]", '<span style="color: #dc2626; background-color: #fef08a; font-weight: bold; padding: 2px 4px; border-radius: 4px;">')
        safe_text = safe_text.replace("[[/HIGHLIGHT]]", '</span>')
        
        # 2. 构建展示用的 HTML 和 打印用的 HTML
        display_html = f"""
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; font-family: Consolas, monospace; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-wrap: break-word; max-height: 500px; overflow-y: auto;">
            {html.escape(clean_text).replace(chr(10), '<br>')}
        </div>
        """
        # 1. 直接合并成一步：转义 + 替换标签（这样绝对不会找不到变量）
        highlighted_print_text = html.escape(clean_text).replace("[[HIGHLIGHT]]", '<span style="color: #dc2626; background-color: #fef08a; font-weight: bold; padding: 2px 4px; border-radius: 4px;">').replace("[[/HIGHLIGHT]]", '</span>')
        
        # 2. 塞进打印模板

            
        print_html = f"""
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Consolas, monospace; padding: 20px; line-height: 1.8; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; font-size: 14px; }}
        </style>
        </head>
        <body>
        <pre>{highlighted_print_text}</pre>
        </body>
        </html>
        """
        
        # 3. 把两段 HTML 都转成 Base64
        b64_display = base64.b64encode(display_html.encode('utf-8')).decode('utf-8')
        b64_print = base64.b64encode(print_html.encode('utf-8')).decode('utf-8')
    
        # 4. 注入前端代码（使用了 JavaScript 的 decodeURIComponent 来完美解析中文）
        components.html(
            f"""
            <div id="report-container"></div>
            
            <div style="margin-top: 15px; text-align: center;">
                <button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; transition: 0.3s;" onmouseover="this.style.backgroundColor='#0369a1'" onmouseout="this.style.backgroundColor='#0284c7'">
                    🖨️ 打印当前报告 (排版不乱)
                </button>
            </div>
    
            <script>
            // ?? 核心修复：这个函数专门用来正确解析含有中文的 Base64 字符串
            function b64DecodeUnicode(str) {{
                return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }}).join(''));
            }}
    
            // 把展示的文本塞进上面的 div 里
            document.getElementById('report-container').innerHTML = b64DecodeUnicode("{b64_display}");
    
            // 打印函数
            function printReport() {{
                var win = window.open("");
                // 这里也换成新的解码函数，打印出来的中文就不会乱码了
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
        
        # --- 下载按钮保留 ---
        file_name = f"报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        st.download_button(
            label="📥保存完整报告到本地 (TXT格式)", 
            data=clean_text.encode('utf-8-sig'), 
            file_name=file_name, 
            mime="text/plain", 
            use_container_width=True
        )
    else:
        st.info("请选择文件、属性及球号后点击【执行当前球分析】。")    
def main_app():
    with st.sidebar:
        st.write("👤 欢迎，" + st.session_state.username)
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        menu = st.radio("功能导航：", ["主控制台", "同现统计", "AI推演", "多维分析"])

    if "synced_df" in st.session_state and st.session_state.synced_df is not None:
        df_data = st.session_state.synced_df
    else:
        df_data = load_real_data()
    
    if menu == "主控制台": render_console(df_data)
    elif menu == "同现统计": render_stats(df_data)
    elif menu == "AI推演": render_ai(df_data)  # 🔥 核心修改：传参进去
    elif menu == "多维分析": render_multi_analysis(df_data) # 🔥 新增这一行    

if not st.session_state.logged_in: login_page()
else: main_app()
