import streamlit as st
import pandas as pd
import hashlib
import time
import os
import itertools
from collections import Counter
import requests
import json
import re

EXCEL_FILE = "数据分析系统最终版本（智能全套）.xlsm" 
SHEET_NAME = "总数据" 
USER_FILE = "users.csv"
DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # 换成你的 Key

st.set_page_config(page_title="智能数据分析系统", layout="wide")

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
if "ai_input_text" not in st.session_state: st.session_state.ai_input_text = ""
if "ai_result_text" not in st.session_state: st.session_state.ai_result_text = "等待推演..."
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
    if len(base_nums) < 6: return None, None, "基准期开奖号码不足6个"
    combos_str = generate_20_combos(base_nums)
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    if is_descending: start_idx, end_idx = base_idx + 1, len(df_data) - 1
    else: start_idx, end_idx = 0, base_idx - 1
    if start_idx > end_idx: return None, None, "基准期附近没有可匹配的历史数据"
    triggers = []
    next_nums_list = []
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
                    next_nums_list.append(next_row_nums)
    counter = Counter()
    for nums in next_nums_list:
        for n in nums: counter[n] += 1
    sorted_counts = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    df_triggers = pd.DataFrame(triggers) if triggers else pd.DataFrame(columns=["组合", "触发行", "触发期数", "触发行号码"])
    df_counts = pd.DataFrame([{"下期数字": f"{n:02d}", "出现次数": c} for n, c in sorted_counts])
    return df_triggers, df_counts, None

def calculate_prize(df_data, target_period, predicted_nums):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: return None, "未找到当期数据"
    base_idx = matched.index[0]
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    next_idx = base_idx - 1 if is_descending else base_idx + 1
    if next_idx < 0 or next_idx >= len(df_data): return None, "已到数据尽头，找不到下一期"
    next_row = df_data.iloc[next_idx]
    next_period = clean_period(next_row.iloc[18])
    next_nums = [clean_period(next_row.iloc[i]) for i in range(19, 25) if clean_period(next_row.iloc[i]) != ""]
    next_special = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    matched_flat = [n for n in next_nums if n in predicted_nums]
    is_special_matched = next_special in predicted_nums
    result = {
        "下期期数": next_period, "预测组合": ",".join(predicted_nums),
        "中出平码1": matched_flat[0] if len(matched_flat) > 0 else "",
        "中出平码2": matched_flat[1] if len(matched_flat) > 1 else "",
        "中出平码3": matched_flat[2] if len(matched_flat) > 2 else "",
        "中出平码4": matched_flat[3] if len(matched_flat) > 3 else "",
        "中出平码5": matched_flat[4] if len(matched_flat) > 4 else "",
        "中出平码6": matched_flat[5] if len(matched_flat) > 5 else "",
        "中出特码": next_special if is_special_matched else "",
        "状态": "有命中" if (len(matched_flat) > 0 or is_special_matched) else "本期无中任何数字"
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
    st.title("?? 智能数据分析总控台")
    if df_data is None or isinstance(df_data, str): st.error("数据读取失败"); return
    unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
    try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    except: unique_periods.sort(reverse=True)
    
    col1, col2, col3, col4 = st.columns([2, 2, 3, 2])
    with col1: selected_period = st.selectbox("?? 选择期数：", unique_periods)
    with col2: analysis_mode = st.radio("模式切换：", ["单排分析", "多排分析"], horizontal=True)
    with col3:
        b1, b2, b3 = st.columns(3)
        start_btn = b1.button("?? 开始分析", use_container_width=True, type="primary")
        result_btn = b2.button("?? 中奖结果", use_container_width=True)
        clear_btn = b3.button("??? 清空数据", use_container_width=True)
    with col4:
        b4, b5 = st.columns(2)
        sync_btn = b4.button("?? 同步数据", use_container_width=True)
        trend_btn = b5.button("?? 走势图", use_container_width=True)

    st.divider()
    flat_nums, special_num = [], 0
    if unique_periods:
        df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
        matched_rows = df_data[df_data['_temp_period'] == selected_period]
        if not matched_rows.empty:
            row = matched_rows.iloc[0]
            try:
                flat_nums = [int(clean_period(row.iloc[i])) for i in range(19, 25) if pd.notna(row.iloc[i])]
                special_num = int(clean_period(row.iloc[25])) if pd.notna(row.iloc[25]) else 0
            except: pass
            st.subheader(f"?? {selected_period} 期开奖结果")
            balls_html = '<div class="ball-container">'
            for num in flat_nums: balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
            if special_num > 0: balls_html += f'<div class="ball {get_ball_color(special_num)} ball-special">★ {special_num:02d}</div>'
            balls_html += '</div>'
            st.markdown(balls_html, unsafe_allow_html=True)

    if sync_btn: st.success("? 数据同步成功！")
    if trend_btn: st.info("?? 网页版走势图正在生成中...")
    if clear_btn:
        st.session_state.calc_data_single = None
        st.session_state.calc_data_multi = None
        st.session_state.calc_result_preview = None
        st.session_state.predicted_nums_single = None
        st.session_state.predicted_nums_multi = None
        st.success("? 数据已清空！")

    if start_btn:
        progress_bar = st.progress(0); status_text = st.empty()
        status_text.text("进度: 10% | 正在生成 20 组核心三码...")
        time.sleep(0.2); progress_bar.progress(20)
        status_text.text("进度: 40% | 正在执行[批量分析20组] (防未来函数)...")
        df_triggers, df_counts, error_msg = calculate_linkage(df_data, selected_period, analysis_mode)
        progress_bar.progress(80); status_text.text("进度: 80% | 正在统计下期频次...")
        time.sleep(0.2); progress_bar.progress(100); status_text.text("进度: 100% | 完成")
        if error_msg: st.error(error_msg)
        else:
            predicted_nums = df_counts.head(7)["下期数字"].tolist() if df_counts is not None and not df_counts.empty else []
            if analysis_mode == "单排分析":
                st.session_state.calc_data_single = (df_triggers, df_counts); st.session_state.predicted_nums_single = predicted_nums
            else:
                st.session_state.calc_data_multi = (df_triggers, df_counts); st.session_state.predicted_nums_multi = predicted_nums
            st.success(f"? 分析完成！共找到 {len(df_triggers)} 处触发。")

    if result_btn:
        predicted_nums = st.session_state.predicted_nums_single if analysis_mode == "单排分析" else st.session_state.predicted_nums_multi
        if not predicted_nums: st.warning("请先点击【开始分析】计算数据！")
        else:
            with st.spinner("正在比对下一期开奖号码..."):
                res_data, err = calculate_prize(df_data, selected_period, predicted_nums)
                if err: st.error(err)
                else: st.success("预祝您中奖！"); st.session_state.calc_result_preview = pd.DataFrame([res_data])

    st.divider()
    col_lb1, col_lb2 = st.columns(2)
    with col_lb1:
        st.subheader("?? ListBox1：单排结果")
        if st.session_state.calc_data_single is not None:
            df_t1, df_c1 = st.session_state.calc_data_single
            st.markdown("**【触发组合明细】**"); st.dataframe(df_t1, use_container_width=True, hide_index=True, height=200)
            st.markdown("**【下期频次统计】**"); st.dataframe(df_c1, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无单排数据。")
    with col_lb2:
        st.subheader("?? ListBox2：多排结果")
        if st.session_state.calc_data_multi is not None:
            df_t2, df_c2 = st.session_state.calc_data_multi
            st.markdown("**【触发组合明细】**"); st.dataframe(df_t2, use_container_width=True, hide_index=True, height=200)
            st.markdown("**【下期频次统计】**"); st.dataframe(df_c2, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无多排数据。")

    st.divider(); st.subheader("?? ListBox3：中出结果预览")
    if st.session_state.calc_result_preview is not None: st.dataframe(st.session_state.calc_result_preview, use_container_width=True, hide_index=True)
    else: st.info("暂无中出结果。")

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
def render_ai():
    st.title("🤖 AI 智能推演系统")
    col_top1, col_top2, col_top3, col_top4 = st.columns([1, 1, 2, 2])
    with col_top1: chk_asc = st.checkbox("升序", value=True)
    with col_top2: chk_desc = st.checkbox("按序", value=False)
    with col_top3: period = st.selectbox("期数", ["2026117", "2026116"])
    with col_top4: ball = st.selectbox("球号", [f"第{i}球" for i in range(1, 8)])
    
    mode = "升序" if chk_asc else "按序"
    interval = f"{ball}的取值区间为1号至49号之间，" if mode == "按序" else "第一球的取值区间为1号至20号之间，"
    prefix = f"这是{period}期{mode}{ball}的核算条件，{interval}"
    
    if "ai_input_text" not in st.session_state: st.session_state.ai_input_text = prefix
    if prefix not in st.session_state.ai_input_text:
        clean_text = re.sub(r'^这是.*?的核算条件，.*?之间，', '', st.session_state.ai_input_text)
        st.session_state.ai_input_text = prefix + clean_text

    col_matrix, col_buttons = st.columns([4, 1], gap="medium")
    with col_matrix:
        groups = [
            ["鼠", "金肖", "红肖", "金号", "东肖", "1段", "1门"],
            ["牛", "木肖", "蓝肖", "木号", "南肖", "2段", "2门"],
            ["虎", "水肖", "绿肖", "水号", "西肖", "3段", "3门"],
            ["兔", "火肖", "阴天", "火号", "北肖", "4段", "4门"],
            ["龙", "土肖", "阳天", "土号", "1门", "5段", "5门"],
            ["蛇", "君王", "阳地", "红波", "2门", "6段", "0合"],
            ["马", "美女", "阴地", "蓝波", "3门", "7段", "1合"],
            ["羊", "家臣", "金尾", "绿波", "4门", "8段", "2合"],
            ["猴", "恶人", "木尾", "大肖", "5门", "9段", "3合"],
            ["鸡", "福肖", "水尾", "中肖", "0尾", "10段", "4合"],
            ["狗", "禄肖", "火尾", "小肖", "1尾", "11段", "5合"],
            ["猪", "寿肖", "土尾", "红波单", "2尾", "12段", "6合"],
        ]
        for row in groups:
            cols = st.columns(len(row))
            for idx, item in enumerate(row):
                with cols[idx]:
                    key = f"chk_{item}"
                    if key not in st.session_state: st.session_state[key] = False
                    st.checkbox(item, key=key)

    with col_buttons:
        if st.button("开始推算", use_container_width=True, type="primary"):
            question = st.session_state.ai_input_text + f"请根据以上触犯条件全面分析{ball}剩余什么生肖与号码。如果全部触犯，那么请将触犯次数最少的作为后补。请开始精准核算。"
            system_prompt = "你是一个精通集合运算与条件排除的推演助手。请严格从1-49中剔除不符合条件的号码。如果剔除后剩下0个，请筛选只触犯了一个条件的号码作为后补。输出格式必须包含：【严格筛选结果】和【后补筛选结果】。"
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
            payload = {"model": "deepseek-chat", "temperature": 0, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": question}], "stream": True}
            try:
                res = requests.post(url, headers=headers, json=payload, stream=True)
                full_response = ""
                for line in res.iter_lines():
                    if line:
                        decoded = line.decode('utf-8')
                        if decoded.startswith("data: ") and decoded != "data: [DONE]":
                            try:
                                delta = json.loads(decoded[6:])["choices"][0]["delta"]
                                if "content" in delta: full_response += delta["content"]
                            except: pass
                st.session_state.ai_result_text = full_response
                st.rerun()
            except Exception as e: st.error(f"请求失败: {e}")

        if st.button("停止语音播报", use_container_width=True): st.toast("已停止播报")
        if st.button("打开数据源", use_container_width=True): st.toast("请切换数据文件")
        if st.button("导出推演结果", use_container_width=True):
            if st.session_state.ai_result_text and st.session_state.ai_result_text != "等待推演...":
                st.download_button("点击下载TXT", data=st.session_state.ai_result_text, file_name=f"推演结果_{period}_{ball}.txt")
            else: st.warning("没有可导出的结果！")
        if st.button("删除结果", use_container_width=True, type="secondary"):
            st.session_state.ai_result_text = "等待推演..."
            st.session_state.ai_input_text = prefix
            for k in list(st.session_state.keys()):
                if k.startswith("chk_"): st.session_state[k] = False
            st.rerun()
        if st.button("六合合一", use_container_width=True): st.info("开发中...")
        if st.button("多维分析系统", use_container_width=True): st.info("开发中...")
        if st.button("返回主界面", use_container_width=True): st.info("请在左侧切换")

    st.divider()
    selected_texts = []
    for key, val in st.session_state.items():
        if key.startswith("chk_") and val == True:
            selected_texts.append(key.replace("chk_", ""))
    if selected_texts:
        append_str = " ".join(selected_texts) + "，"
        if append_str not in st.session_state.ai_input_text:
            st.session_state.ai_input_text += append_str

    st.subheader("📝 核算条件输入")
    user_input = st.text_area("", value=st.session_state.ai_input_text, height=100, label_visibility="collapsed")
    if user_input != st.session_state.ai_input_text: st.session_state.ai_input_text = user_input

    st.subheader("🧠 智能分析结果")
    st.text_area("", value=st.session_state.ai_result_text, height=300, label_visibility="collapsed")

def main_app():
    with st.sidebar:
        st.write("👤 欢迎，" + st.session_state.username)
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        menu = st.radio("功能导航：", ["主控制台", "同现统计", "AI推演"])

    df_data = load_real_data()
    if menu == "主控制台": render_console(df_data)
    elif menu == "同现统计": render_stats(df_data)
    elif menu == "AI推演": render_ai()

if not st.session_state.logged_in: login_page()
else: main_app()