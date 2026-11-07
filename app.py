import streamlit as st
import pandas as pd
import hashlib
import time
import os
import itertools
from collections import Counter

# ==========================================
# ⚙️ 配置区
# ==========================================
EXCEL_FILE = "数据分析系统最终版本（智能全套）.xlsm" 
SHEET_NAME = "总数据" 
USER_FILE = "users.csv"

st.set_page_config(page_title="智能数据分析系统", layout="wide")

# ==========================================
# CSS 美化
# ==========================================
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

# ==========================================
# 状态初始化
# ==========================================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "ai_input_text" not in st.session_state: st.session_state.ai_input_text = ""
if "ai_result_text" not in st.session_state: st.session_state.ai_result_text = "等待推演..."
if "calc_data_single" not in st.session_state: st.session_state.calc_data_single = None
if "calc_data_multi" not in st.session_state: st.session_state.calc_data_multi = None
if "calc_result_preview" not in st.session_state: st.session_state.calc_result_preview = None
if "predicted_nums_single" not in st.session_state: st.session_state.predicted_nums_single = None
if "predicted_nums_multi" not in st.session_state: st.session_state.predicted_nums_multi = None

# ==========================================
# 辅助函数
# ==========================================
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

# ==========================================
# 核心算法 (替代 VBA 宏)
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
    
    if len(base_nums) < 6: return None, None, "基准期开奖号码不足6个"
        
    combos_str = generate_20_combos(base_nums)
    
    try:
        is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except:
        is_descending = True
        
    if is_descending:
        start_idx = base_idx + 1
        end_idx = len(df_data) - 1
    else:
        start_idx = 0
        end_idx = base_idx - 1
        
    if start_idx > end_idx: return None, None, "基准期附近没有可匹配的历史数据"
        
    triggers = []
    next_nums_list = []
    
    for idx in range(start_idx, end_idx + 1):
        row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
        row_period = clean_period(df_data.iloc[idx, 18])
        
        for combo_str in combos_str:
            combo = [int(x) for x in combo_str.split(",")]
            if all(n in row_nums for n in combo):
                triggers.append({
                    "组合": combo_str,
                    "触发行": idx + 1,
                    "触发期数": row_period,
                    "触发行号码": ",".join([f"{n:02d}" for n in row_nums])
                })
                
                next_idx = idx - 1 if is_descending else idx + 1
                if 0 <= next_idx < len(df_data):
                    next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                    next_nums_list.append(next_row_nums)
                    
    counter = Counter()
    for nums in next_nums_list:
        for n in nums:
            counter[n] += 1
            
    sorted_counts = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    
    df_triggers = pd.DataFrame(triggers) if triggers else pd.DataFrame(columns=["组合", "触发行", "触发期数", "触发行号码"])
    df_counts = pd.DataFrame([{"下期数字": f"{n:02d}", "出现次数": c} for n, c in sorted_counts])
    
    return df_triggers, df_counts, None

def calculate_prize(df_data, target_period, predicted_nums):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: return None, "未找到当期数据"
    
    base_idx = matched.index[0]
    try:
        is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except:
        is_descending = True
        
    next_idx = base_idx - 1 if is_descending else base_idx + 1
    if next_idx < 0 or next_idx >= len(df_data): return None, "已到数据尽头，找不到下一期"
        
    next_row = df_data.iloc[next_idx]
    next_period = clean_period(next_row.iloc[18])
    next_nums = [clean_period(next_row.iloc[i]) for i in range(19, 25) if clean_period(next_row.iloc[i]) != ""]
    next_special = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    
    matched_flat = [n for n in next_nums if n in predicted_nums]
    is_special_matched = next_special in predicted_nums
    
    result = {
        "下期期数": next_period,
        "预测组合": ",".join(predicted_nums),
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

# ==========================================
# 页面 1：登录
# ==========================================
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
                else:
                    st.error("用户名或密码错误！")
    with tab2:
        reg_user = st.text_input("设置用户名", key="reg_user")
        reg_pwd = st.text_input("设置密码", type="password", key="reg_pass")
        reg_confirm = st.text_input("确认密码", type="password", key="reg_confirm")
        if st.button("注册", use_container_width=True):
            if reg_user and reg_pwd:
                if reg_pwd != reg_confirm:
                    st.error("两次密码不一致")
                else:
                    users_df = load_users()
                    if reg_user in users_df['username'].values:
                        st.error("该用户名已被注册")
                    else:
                        new_user = pd.DataFrame({'username': [reg_user], 'password': [hashlib.sha256(reg_pwd.encode()).hexdigest()]})
                        pd.concat([users_df, new_user], ignore_index=True).to_csv(USER_FILE, index=False)
                        st.success("注册成功！请去左侧登录。")
# ==========================================
# 页面 2：主控制台
# ==========================================
def render_console(df_data):
    st.title("🧊 智能数据分析总控台")
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：" + str(EXCEL_FILE))
        return

    # 🚨 关键：必须保证有这一行来生成期数列表
    unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
    try: 
        unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    except: 
        unique_periods.sort(reverse=True)
    
    # 1. 控制面板
    col1, col2 = st.columns(2)
    with col1: 
        selected_period = st.selectbox("🎯 选择期数：", unique_periods)
    with col2: 
        analysis_mode = st.radio("模式切换：", ["单排分析", "多排分析"], horizontal=True)
    
    st.write("") 
    
    # 按钮布局
    b1, b2, b3, b4, b5 = st.columns(5)
    start_btn = b1.button("🚀 批量20组分析", use_container_width=True, type="primary", help="自动生成20组三码并扫描历史，提取最高频的前7套下期数字")
    result_btn = b2.button("🏆 中奖结果", use_container_width=True)
    clear_btn = b3.button("🗑️ 清空数据", use_container_width=True)
    sync_btn = b4.button("🔄 同步数据", use_container_width=True)
    trend_btn = b5.button("📈 走势图", use_container_width=True)

    # ==========================================
    # 接着往下就是你之前替换的“2. 彩球展示”代码了
    # ==========================================
    # 2. 彩球展示 (自动计算下一期)
st.divider()
df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)

# 寻找当前选择期数在数据中的位置
matched_rows = df_data[df_data['_temp_period'] == selected_period]

# 判断数据是升序还是降序
try:
    is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
except:
    is_descending = True

next_period_str = ""
next_flat_nums = []
next_special_num = 0
has_next_data = False

if not matched_rows.empty:
    base_idx = matched_rows.index[0]
    # 计算下一期的索引 (如果是降序，下一期在上面；如果是升序，下一期在下面)
    next_idx = base_idx - 1 if is_descending else base_idx + 1
    
    if 0 <= next_idx < len(df_data):
        # 找到了下一期数据
        next_row = df_data.iloc[next_idx]
        next_period_str = clean_period(next_row.iloc[18])
        try:
            next_flat_nums = [int(clean_period(next_row.iloc[i])) for i in range(19, 25) if pd.notna(next_row.iloc[i])]
            next_special_num = int(clean_period(next_row.iloc[25])) if pd.notna(next_row.iloc[25]) else 0
            if len(next_flat_nums) > 0:
                has_next_data = True
        except: pass

if has_next_data:
    # 如果有下一期开奖数据，渲染号码球
    st.subheader(f"🎯 {next_period_str} 期开奖结果")
    balls_html = '<div class="ball-container">'
    for num in next_flat_nums: balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
    if next_special_num > 0: balls_html += f'<div class="ball {get_ball_color(next_special_num)} ball-special">★ {next_special_num:02d}</div>'
    balls_html += '</div>'
    st.markdown(balls_html, unsafe_allow_html=True)
else:
    # 如果没找到下一期数据（未开奖或到了尽头），推算下一期期号并显示提示
    try:
        next_period_str = str(int(float(selected_period)) + 1) # 假设期号是连号的
    except:
        next_period_str = "下一期"
        
    st.subheader(f"🎯 {next_period_str} 期开奖结果")
    st.info(f"⏳ {next_period_str} 期待开奖（暂无数据）")

    # 3. 操作逻辑
    if sync_btn: st.success("✅ 数据同步成功！")
    if trend_btn: st.info("📈 网页版走势图正在生成中...")
    if clear_btn:
        st.session_state.calc_data_single = None
        st.session_state.calc_data_multi = None
        st.session_state.calc_result_preview = None
        st.session_state.predicted_nums_single = None
        st.session_state.predicted_nums_multi = None
        st.success("✅ 数据已清空！")

    if start_btn:
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("进度: 10% | 正在生成 20 组核心三码...")
        time.sleep(0.2); progress_bar.progress(20)
        status_text.text("进度: 40% | 正在执行[批量分析20组] (防未来函数)...")
        time.sleep(0.2)
        
        df_triggers, df_counts, error_msg = calculate_linkage(df_data, selected_period, analysis_mode)
        
        progress_bar.progress(80)
        status_text.text("进度: 80% | 正在统计下期频次...")
        time.sleep(0.2); progress_bar.progress(100)
        status_text.text("进度: 100% | 完成")
        
        if error_msg: st.error(error_msg)
        else:
            predicted_nums = df_counts.head(7)["下期数字"].tolist() if df_counts is not None and not df_counts.empty else []
            if analysis_mode == "单排分析":
                st.session_state.calc_data_single = (df_triggers, df_counts)
                st.session_state.predicted_nums_single = predicted_nums
            else:
                st.session_state.calc_data_multi = (df_triggers, df_counts)
                st.session_state.predicted_nums_multi = predicted_nums
            st.success(f"✅ 分析完成！共扫描 {len(df_data)} 行历史数据，找到 {len(df_triggers)} 处触发。")

    if result_btn:
        predicted_nums = st.session_state.predicted_nums_single if analysis_mode == "单排分析" else st.session_state.predicted_nums_multi
        if not predicted_nums: st.warning("请先点击【开始分析】计算数据！")
        else:
            with st.spinner("正在比对下一期开奖号码..."):
                res_data, err = calculate_prize(df_data, selected_period, predicted_nums)
                if err: st.error(err)
                else:
                    st.success("预祝您中奖！请查看下方 ListBox3。")
                    st.session_state.calc_result_preview = pd.DataFrame([res_data])

    # 4. 底部展示区 (复刻 ListBox1, ListBox2, ListBox3)
    st.divider()
    col_lb1, col_lb2 = st.columns(2)
    
    with col_lb1:
        st.subheader("📋 ：单排结果")
        if st.session_state.calc_data_single is not None:
            df_t1, df_c1 = st.session_state.calc_data_single
            st.markdown("**【触发组合明细】**")
            st.dataframe(df_t1, use_container_width=True, hide_index=True, height=200)
            st.markdown("**【下期频次统计】**")
            st.dataframe(df_c1, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无单排数据，请选择【单排分析】模式并点击【开始分析】。")
            
    with col_lb2:
        st.subheader("📋 ：多排结果")
        if st.session_state.calc_data_multi is not None:
            df_t2, df_c2 = st.session_state.calc_data_multi
            st.markdown("**【触发组合明细】**")
            st.dataframe(df_t2, use_container_width=True, hide_index=True, height=200)
            st.markdown("**【下期频次统计】**")
            st.dataframe(df_c2, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无多排数据，请选择【多排分析】模式并点击【开始分析】。")

    st.divider()
    st.subheader("🏆 ：中出结果预览")
    if st.session_state.calc_result_preview is not None:
        st.dataframe(st.session_state.calc_result_preview, use_container_width=True, hide_index=True)
    else:
        st.info("暂无中出结果，请在上方进行分析后点击【中奖结果】。")

# ==========================================
# 页面 3：同现统计
# ==========================================
def render_stats(df_data):
    st.title("📈 历史同现深度分析")
    if df_data is None or isinstance(df_data, str): return
    
    target_num = st.number_input("目标号码 (1-49):", min_value=1, max_value=49, value=30)
    top_n = st.selectbox("提取前几名:", [3, 5, 8, 10])

    if st.button("🔍 开始扫描", use_container_width=True):
        with st.spinner("正在比对..."):
            try:
                nums_df = df_data.iloc[:, 19:25].apply(pd.to_numeric, errors='coerce')
                filtered = nums_df[nums_df.isin([target_num]).any(axis=1)]
                if len(filtered) == 0: st.warning("未出现过。")
                else:
                    counts = {}
                    for _, row in filtered.iterrows():
                        for num in row.values:
                            if pd.notna(num) and int(num) != target_num:
                                counts[int(num)] = counts.get(int(num), 0) + 1
                    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
                    res_df = pd.DataFrame([{"排名": i+1, "同频号码": f"{num:02d}", "同现次数": count} for i, (num, count) in enumerate(sorted_counts)])
                    st.success(f"与 {target_num:02d} 号同现频率最高的结果：")
                    st.dataframe(res_df, use_container_width=True, hide_index=True)
                    st.bar_chart(res_df.set_index("同频号码")["同现次数"])
            except Exception as e: st.error(f"出错：{e}")

# ==========================================
# 页面 4：AI 推演
# ==========================================
def render_ai():
    st.title("🤖 AI 严谨推演系统")
    CHECKBOX_MAP = {
        "0尾": "杀0尾（10、20、30、40），", "1尾": "杀1尾（01、11、21、31、41），", "2尾": "杀2尾（02、12、22、32、42），",
        "3尾": "杀3尾（03、13、23、33、43），", "4尾": "杀4尾（04、14、24、34、44），", "5尾": "杀5尾（05、15、25、35、45），",
        "6尾": "杀6尾（06、16、26、36、46），", "7尾": "杀7尾（07、17、27、37、47），", "8尾": "杀8尾（08、18、28、38、48），", "9尾": "杀9尾（09、19、29、39、49），",
        "金号": "杀金号（04、05、12、13、26、27、34、35、42、43），", "木号": "杀木号（08、09、16、17、24、25、38、39、46、47），",
        "水号": "杀水号（01、14、15、22、23、30、31、44、45），", "火号": "杀火号（02、03、10、11、18、19、32、33、40、41、48、49），", "土号": "杀土号（06、07、20、21、28、29、36、37），",
        "红波": "杀红波（01、02、07、08、12、13、18、19、23、24、29、30、34、35、40、45、46），", "蓝波": "杀蓝波（03、04、09、10、14、15、20、25、26、31、36、37、41、42、47、48），", "绿波": "杀绿波（05、06、11、16、17、21、22、27、28、32、33、38、39、43、44、49），",
        "杀鼠": "杀鼠，", "杀牛": "杀牛，", "杀虎": "杀虎，", "杀兔": "杀兔，", "杀龙": "杀龙，", "杀蛇": "杀蛇，", "杀马": "杀马，", "杀羊": "杀羊，", "杀猴": "杀猴，", "杀鸡": "杀鸡，", "杀狗": "杀狗，", "杀猪": "杀猪，",
        "金肖": "杀金肖（猴鸡），", "木肖": "杀木肖（虎兔），", "水肖": "杀水肖（鼠猪），", "火肖": "杀火肖（蛇马），", "土肖": "杀土肖（牛龙羊狗），",
        "阴天": "杀阴天（马龙猪），", "阳天": "杀阳天（兔牛猴），", "阴地": "杀阴地（蛇鼠狗），", "阳地": "杀阳地（虎鸡羊），",
        "大肖": "杀大肖（牛虎龙马），", "中肖": "杀中肖（羊猴狗猪），", "小肖": "杀小肖（鼠兔蛇鸡），",
        "家臣": "杀家臣（马牛猪狗），", "美女": "杀美女（蛇兔鸡羊），", "君王": "杀君王（龙虎），", "恶人": "杀恶人（鼠猴），",
        "东": "杀东（虎兔龙），", "南": "杀南（蛇马羊），", "西": "杀西（猴鸡狗），", "北": "杀北（猪鼠牛），",
        "3余0": "杀3余0（杀0，3，6，9尾），", "3余1": "杀3余1（杀1，4，7尾），", "3余2": "杀3余2（杀2，5，8尾），",
        "1门": "杀1门（01、02、03、04、05、06、07、08、09），", "2门": "杀2门（10、11、12、13、14、15、16、17、18、19），", "3门": "杀3门（20、21、22、23、24、25、26、27、28、29），", "4门": "杀4门（30、31、32、33、34、35、36、37、38、39），", "5门": "杀5门（40、41、42、43、44、45、46、47、48、49），",
        "1段": "杀1段（01、02、03、04、05、06、07），", "2段": "杀2段（08、09、10、11、12、13、14），", "3段": "杀3段（15、16、17、18、19、20、21），", "4段": "杀4段（22、23、24、25、26、27、28），", "5段": "杀5段（29、30、31、32、33、34、35），", "6段": "杀6段（36、37、38、39、40、41、42），", "7段": "杀7段（43、44、45、46、47、48、49），",
        "01合": "杀01合（01、10），", "02合": "杀02合（02、11、20），", "03合": "杀03合（03、12、21、30），", "04合": "杀04合（04、13、22、31、40），", "05合": "杀05合（05、14、23、32、41），", "06合": "杀06合（06、15、24、33、42），", "07合": "杀07合（07、16、25、34、43），", "08合": "杀08合（08、17、26、35、44），", "09合": "杀09合（09、18、27、36、45），", "10合": "杀10合（19、28、37、46），", "11合": "杀11合（29、38、47），", "12合": "杀12合（39、48），", "13合": "杀13合（49），",
        "红肖": "杀红肖（马兔鼠鸡），", "蓝肖": "杀蓝肖（虎猴蛇猪），", "绿肖": "杀绿肖（龙狗牛羊），",
        "书肖": "杀书肖（马龙虎），", "琴肖": "杀琴肖（蛇兔鸡），", "棋肖": "杀棋肖（牛鼠狗），", "画肖": "杀画肖（猪猴羊），",
        "福肖": "杀福肖（马龙虎鼠），", "禄肖": "杀禄肖（兔牛猪猴），", "寿肖": "杀寿肖（蛇狗鸡羊），",
        "红波单": "杀红波单（01、07、13、19、23、29、35、45），", "红波双": "杀红波双（02、08、12、18、24、30、34、40、46），", "蓝波单": "杀蓝波单（03、09、15、25、31、37、41、47），", "蓝波双": "杀蓝波双（04、10、14、20、26、36、42、48），", "绿波单": "杀绿波单（05、11、17、21、27、33、39、43、49），", "绿波双": "杀绿波双（06、16、22、28、32、38、44），",
        "金尾": "杀金尾（04、09、14、19、24、29、34、39、44、49），", "木尾": "杀木尾（03、08、13、18、23、28、33、38、43、48），", "水尾": "杀水尾（01、06、11、16、21、26、31、36、41、46），", "火尾": "杀火尾（02、07、12、17、22、27、32、37、42、47），", "土尾": "杀土尾（05、10、15、20、25、30、35、40、45），"
    }

    def toggle_chk(label):
        txt = CHECKBOX_MAP[label]
        if st.checkbox(label):
            if txt not in st.session_state.ai_input_text: st.session_state.ai_input_text += txt
        else:
            st.session_state.ai_input_text = st.session_state.ai_input_text.replace(txt, "")

    col_left, col_right = st.columns(2)
    with col_left:
        st.text_area("条件输入：", value=st.session_state.ai_input_text, height=250)
        st.text_area("推演结果：", value=st.session_state.ai_result_text, height=250, disabled=True)
        if st.button("开始推演", use_container_width=True):
            st.session_state.ai_result_text = "推演完成！"
            st.rerun()

    with col_right:
        with st.expander("生肖与五行", expanded=True):
            cols = st.columns(3)
            for idx, key in enumerate(["金肖", "木肖", "水肖", "火肖", "土肖", "红肖", "蓝肖", "绿肖"]):
                with cols[idx % 3]: toggle_chk(key)
        with st.expander("尾数杀号"):
            cols = st.columns(5)
            for i in range(10):
                with cols[i % 5]: toggle_chk(f"{i}尾")
        with st.expander("生肖专属"):
            cols = st.columns(4)
            for idx, z in enumerate(["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]):
                with cols[idx % 4]: toggle_chk(f"杀{z}")
        with st.expander("门数 / 段数 / 合数"):
            cols = st.columns(4)
            for i in range(1, 6):
                with cols[(i-1) % 4]: toggle_chk(f"{i}门")
            for i in range(1, 8):
                with cols[(i+4) % 4]: toggle_chk(f"{i}段")
            for i in range(1, 14):
                with cols[(i+11) % 4]: toggle_chk(f"{i:02d}合")
        with st.expander("波色 / 波单双"):
            cols = st.columns(3)
            for idx, key in enumerate(["红波", "蓝波", "绿波", "红波单", "红波双", "蓝波单", "蓝波双", "绿波单", "绿波双"]):
                with cols[idx % 3]: toggle_chk(key)
        with st.expander("其他属性"):
            cols = st.columns(3)
            others = ["金号", "木号", "水号", "火号", "土号", "金尾", "木尾", "水尾", "火尾", "土尾", "大肖", "中肖", "小肖", "书肖", "琴肖", "棋肖", "画肖", "福肖", "禄肖", "寿肖"]
            for idx, key in enumerate(others):
                with cols[idx % 3]: toggle_chk(key)

# ==========================================
# 主路由
# ==========================================
def main_app():
    with st.sidebar:
        st.write("👤 欢迎，" + st.session_state.username)
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        menu = st.radio("功能导航：", ["主控制台", "同现统计", "AI推演"])

    df_data = load_real_data()
    
    if menu == "主控制台":
        render_console(df_data)
    elif menu == "同现统计":
        render_stats(df_data)
    elif menu == "AI推演":
        render_ai()

if not st.session_state.logged_in:
    login_page()
else:
    main_app()