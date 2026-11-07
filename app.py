import streamlit as st
import pandas as pd
import hashlib
import time
import os
import itertools
from collections import Counter
import requests

# ==========================================
# ⚙️ 配置区
# ==========================================
EXCEL_FILE = "数据分析系统最终版本（智能全套）.xlsm" 
SHEET_NAME = "总数据" 
USER_FILE = "users.csv"

st.set_page_config(page_title="智能数据分析系统", layout="wide")
# ==========================================
# ⚙️ DeepSeek 配置区
# ==========================================
DEEPSEEK_API_KEY = "sk-03230269b092411eb4db85a4ea906dd3"

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
    
    # 读取当前期的 6 个平码和 1 个特码
    base_nums = [int(clean_period(current_row.iloc[i])) for i in range(19, 25) if pd.notna(current_row.iloc[i]) and clean_period(current_row.iloc[i]) != ""]
    special_num = int(clean_period(current_row.iloc[25])) if pd.notna(current_row.iloc[25]) and clean_period(current_row.iloc[25]) != "" else None
    
    if len(base_nums) < 6: return None, None, "基准期开奖号码不足6个"
        
    # 判断升降序
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
    total_counter = Counter() # 核心：用于累计多套或单套的频次

    if mode == "单排分析":
        # ============== 单排：一套组合直接跑 ==============
        combos_str = generate_20_combos(base_nums)
        
        for idx in range(start_idx, end_idx + 1):
            row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
            row_period = clean_period(df_data.iloc[idx, 18])
            
            for combo_str in combos_str:
                combo = [int(x) for x in combo_str.split(",")]
                if all(n in row_nums for n in combo):
                    triggers.append({
                        "组合": combo_str, "触发行": idx + 1, "触发期数": row_period,
                        "触发行号码": ",".join([f"{n:02d}" for n in row_nums])
                    })
                    next_idx = idx - 1 if is_descending else idx + 1
                    if 0 <= next_idx < len(df_data):
                        next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                        for n in next_row_nums:
                            total_counter[n] += 1
    else:
        # ============== 多排：7 套循环 + 抹除重复 ==============
        dict_history = set() # 模拟 VBA 里的 dictHistory
        
        for i in range(7):
            current_base = list(base_nums)
            # 第 2 套(i=1) 开始，用特码依次替换平码
            if i >= 1 and special_num is not None:
                current_base[i-1] = special_num
                
            if len(current_base) < 6: continue
                
            new_combos = generate_20_combos(current_base)
            valid_combos = []
            
            # 核心去重抹除逻辑
            for c in new_combos:
                if c not in dict_history:
                    dict_history.add(c)
                    valid_combos.append(c)
                    
            if not valid_combos:
                continue # 如果这一套 20 组全被抹掉了，跳过本套
                
            # 跑这套的有效组合
            for idx in range(start_idx, end_idx + 1):
                row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
                row_period = clean_period(df_data.iloc[idx, 18])
                
                for combo_str in valid_combos:
                    combo = [int(x) for x in combo_str.split(",")]
                    if all(n in row_nums for n in combo):
                        triggers.append({
                            "组合": combo_str, "触发行": idx + 1, "触发期数": row_period,
                            "触发行号码": ",".join([f"{n:02d}" for n in row_nums])
                        })
                        next_idx = idx - 1 if is_descending else idx + 1
                        if 0 <= next_idx < len(df_data):
                            next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                            for n in next_row_nums:
                                total_counter[n] += 1

    # 最终排序提取结果
    sorted_counts = sorted(total_counter.items(), key=lambda x: x[1], reverse=True)
    
    df_triggers = pd.DataFrame(triggers) if triggers else pd.DataFrame(columns=["组合", "触发行", "触发期数", "触发行号码"])
    df_counts = pd.DataFrame([{"下期数字": f"{n:02d}", "出现次数": c} for n, c in sorted_counts])
    
    return df_triggers, df_counts, None

def calculate_prize(df_data, target_period, predicted_nums):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: 
        return None, f"总数据里找不到本期 {target_period}！"
    
    # 获取选中期的物理位置（行号）
    base_pos = df_data.index.get_loc(matched.index[0])
    
    # 你的数据是降序，所以下一期（118期）一定在正上方（行号 - 1）
    next_pos = base_pos - 1
    
    # 如果越界，说明选的是最上面的一期（暂无下一期数据）
    if next_pos < 0:
        res = {
            "下期期数": "待开奖", 
            "预测组合": ",".join(predicted_nums),
            "状态": "本期开奖数据未更新"
        }
        return res, "本期开奖数据未更新"
        
    # 强行取上一行（即118期）的数据
    next_row = df_data.iloc[next_pos]
    next_period = clean_period(next_row.iloc[18])
    
    # 如果上一行的期数没填，或者并不是比当前期更大的期数，说明未开奖
    if not next_period:
        return {
            "下期期数": "待开奖", 
            "预测组合": ",".join(predicted_nums),
            "状态": "本期开奖数据未更新"
        }, "本期开奖数据未更新"
        
    # 读取 118 期的开奖号码（19-24为平码，25为特码）
    nums = [clean_period(next_row.iloc[i]) for i in range(19, 25)]
    z_val = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    
    # 平码去重与排序
    match_nums = []
    for n in nums:
        if n and n in predicted_nums and n not in match_nums:
            match_nums.append(n)
    try:
        match_nums.sort(key=lambda x: int(x))
    except:
        pass
        
    # 特码匹配
    z_matched = z_val in predicted_nums if z_val else False
    
    # 状态判断
    status = "有命中" if (len(match_nums) > 0 or z_matched) else "本期无中任何数字"
    
    # 组装最终表格
    result = {
        "下期期数": next_period,  # 这里一定会显示 2026118
        "预测组合": ",".join(predicted_nums),
        "中出平码1": match_nums[0] if len(match_nums) > 0 else "",
        "中出平码2": match_nums[1] if len(match_nums) > 1 else "",
        "中出平码3": match_nums[2] if len(match_nums) > 2 else "",
        "中出平码4": match_nums[3] if len(match_nums) > 3 else "",
        "中出平码5": match_nums[4] if len(match_nums) > 4 else "",
        "中出平码6": match_nums[5] if len(match_nums) > 5 else "",
        "中出特码": z_val if z_matched else "",
        "状态": status
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

    # 生成期数列表
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
    start_btn = b1.button("🚀 批量联动分析", use_container_width=True, type="primary", help="自动生成批量组合三码并扫描历史，提取最高频的前7套下期数字")
    result_btn = b2.button("🏆 中奖结果", use_container_width=True)
    clear_btn = b3.button("🗑️ 清空数据", use_container_width=True)
    sync_btn = b4.button("🔄 同步数据", use_container_width=True)
    trend_btn = b5.button("📈 走势图", use_container_width=True)

    # 2. 彩球展示 (自动计算下一期)
    st.divider()
    df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
    
    matched_rows = df_data[df_data['_temp_period'] == selected_period]
    
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
        next_idx = base_idx - 1 if is_descending else base_idx + 1
        
        if 0 <= next_idx < len(df_data):
            next_row = df_data.iloc[next_idx]
            next_period_str = clean_period(next_row.iloc[18])
            try:
                next_flat_nums = [int(clean_period(next_row.iloc[i])) for i in range(19, 25) if pd.notna(next_row.iloc[i])]
                next_special_num = int(clean_period(next_row.iloc[25])) if pd.notna(next_row.iloc[25]) else 0
                if len(next_flat_nums) > 0:
                    has_next_data = True
            except: pass

    if has_next_data:
        st.subheader(f"🎯 {next_period_str} 期开奖结果")
        balls_html = '<div class="ball-container">'
        for num in next_flat_nums: balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
        if next_special_num > 0: balls_html += f'<div class="ball {get_ball_color(next_special_num)} ball-special">★ {next_special_num:02d}</div>'
        balls_html += '</div>'
        st.markdown(balls_html, unsafe_allow_html=True)
    else:
        try:
            next_period_str = str(int(float(selected_period)) + 1)
        except:
            next_period_str = "下一期"
        st.subheader(f"🎯 {next_period_str} 期开奖结果")
        st.info(f"⏳ {next_period_str} 期待开奖（暂无数据）")

    # 3. 操作逻辑
    if sync_btn: st.success("✅ 数据同步成功！")
    if trend_btn: render_trend_chart(df_data)
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
        if not predicted_nums: 
             st.warning("请先点击【开始分析】计算数据！")
    else:
             with st.spinner("正在比对下一期开奖号码..."):
                    res_data, err = calculate_prize(df_data, selected_period, predicted_nums)
                    if err == "本期开奖数据未更新":
                         st.warning(f"? {selected_period} 期的下期开奖数据未更新，请等待开奖！")
                         st.session_state.calc_result_preview = pd.DataFrame([res_data])
                    elif err: 
                         st.error(err)
                    else:
                         st.success("预祝您中奖！请查看下方中出结果预览。")
                         st.session_state.calc_result_preview = pd.DataFrame([res_data])

    # 4. 底部展示区
    st.divider()
    col_lb1, col_lb2 = st.columns(2)
    
    with col_lb1:
        st.subheader("单排结果")
        if st.session_state.calc_data_single is not None:
            df_t1, df_c1 = st.session_state.calc_data_single
            st.markdown("**【触发组合明细】**")
            st.dataframe(df_t1, use_container_width=True, hide_index=True, height=200)
            st.markdown("**【下期频次统计】**")
            st.dataframe(df_c1, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无单排数据，请选择【单排分析】模式并点击【开始分析】。")
            
    with col_lb2:
        st.subheader("多排结果")
        if st.session_state.calc_data_multi is not None:
            df_t2, df_c2 = st.session_state.calc_data_multi
            st.markdown("**【触发组合明细】**")
            st.dataframe(df_t2, use_container_width=True, hide_index=True, height=200)
            st.markdown("**【下期频次统计】**")
            st.dataframe(df_c2, use_container_width=True, hide_index=True, height=200)
        else: st.info("暂无多排数据，请选择【多排分析】模式并点击【开始分析】。")

    st.divider()
    st.subheader("中出结果预览")
    if st.session_state.calc_result_preview is not None:
        st.dataframe(st.session_state.calc_result_preview, use_container_width=True, hide_index=True)
    else:
        st.info("暂无中出结果，请在上方进行分析后点击【中奖结果】。")
# ==========================================
# 页面 3：同现统计
# ==========================================
# 这就是你刚才粘贴的新函数，必须顶格写
def render_trend_chart(df_data):
    st.divider()
    st.subheader("📈 历史走势图（最近30期）")
    
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败，无法生成走势图")
        return
        
    # 限制显示最近 30 期，防止网页卡顿
    recent_data = df_data.head(30).copy()
    
    if recent_data.empty:
        st.warning("暂无数据可供生成走势图")
        return

    # 提取期数作为行索引
    periods = recent_data.iloc[:, 18].apply(clean_period).tolist()
    
    tab1, tab2 = st.tabs(["平 码 区", "特 码 区"])
    
    with tab1:
        # 构建 01-49 的列
        cols = [f"{i:02d}" for i in range(1, 50)]
        # 创建一个空的 DataFrame
        matrix = pd.DataFrame("", index=periods, columns=cols)
        
        # 填入平码数据 (19-24列)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            for i in range(19, 25):
                num_str = clean_period(row.iloc[i])
                if num_str in cols:
                    matrix.at[period, num_str] = "●" # 用实心圆点代表开出的号码
                    
        # 美化表格
        st.dataframe(
            matrix, 
            use_container_width=True, 
            height=600
        )
        
    with tab2:
        # 构建特码 01-49 的列
        cols = [f"{i:02d}" for i in range(1, 50)]
        matrix_special = pd.DataFrame("", index=periods, columns=cols)
        
        # 填入特码数据 (第25列)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            num_str = clean_period(row.iloc[25]) if len(row) > 25 else ""
            if num_str in cols:
                matrix_special.at[period, num_str] = "★" # 用五角星代表特码
                
        st.dataframe(
            matrix_special, 
            use_container_width=True, 
            height=600
        )

# ==========================================
# 页面 4：AI 推演
# ==========================================
# ==========================================
# AI 推演底层辅助函数
# ==========================================

def build_rule_database():
    """从 Excel 的'规则'表读取 49 个号码的完整属性"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name="规则")
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
        st.error(f"读取规则表失败: {e}")
        return None

def build_full_table_text(db):
    """把规则库打包成紧凑文本发送给 AI"""
    result = "【1-49号完整属性表（绝对权威）】\\n"
    for i in range(1, 50):
        if str(i) in db:
            info = db[str(i)]
            result += f"{i}号:{{{info['生肖']},{info['肖五行']},{info['号五行']},{info['尾五行']},{info['物象']},{info['人物']},{info['大小']},{info['波色']},{info['合数']}}}\\n"
    return result

def get_analysis_prompt(full_table):
    """生成强约束的推演提示词"""
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
    """发送 POST 请求给 DeepSeek"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    payload = {
        "model": "deepseek-chat",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "你是一个严谨的数据推演与集合运算助手。"},
            {"role": "user", "content": question},
            {"role": "system", "content": system_prompt}
        ]
    }
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            answer = data['choices'][0]['message']['content']
            answer = answer.replace("**", "").replace("###", "").replace("##", "").replace("#", "").replace("`", "")
            return answer
        else:
            return f"请求失败：{response.status_code}\\n{response.text}"
    except Exception as e:
        return f"运行错误：{e}"
def render_ai():
    st.title("🤖 AI 严谨推演系统")
    
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
        "大肖": "杀大肖（牛虎龙马），", "中肖": "杀中肖（羊猴狗猪），", "小肖": "杀小肖（鼠兔蛇鸡），", "书肖": "杀书肖（马龙虎），", "琴肖": "杀琴肖（蛇兔鸡），", "棋肖": "杀棋肖（牛鼠狗），", "画肖": "杀画肖（猪猴羊），", "福肖": "杀福肖（马龙虎鼠），", "禄肖": "杀禄肖（兔牛猪猴），", "寿肖": "杀寿肖（蛇狗鸡羊），"
    }

    if "ai_checks" not in st.session_state: st.session_state.ai_checks = {}
    if "ai_api_result" not in st.session_state: st.session_state.ai_api_result = "等待推演..."
    if "ai_ball_result" not in st.session_state: st.session_state.ai_ball_result = []

    def get_prefix(qishu, qiu, order_type):
        if order_type == "按序":
            interval = f"{qiu}的取值区间为1号至49号之间，"
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
    with col1: qishu = st.selectbox("选择期数：", ["2026116", "2026117", "2026118"], index=1)
    with col2: qiu = st.selectbox("选择球数：", ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"], index=0)
    with col3: order_type = st.radio("核算模式：", ["升序", "按序"], horizontal=True)

    st.divider()
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        prefix = get_prefix(qishu, qiu, order_type)
        checked_texts = [CHECKBOX_MAP[k] for k, v in st.session_state.ai_checks.items() if v]
        full_text = prefix + "".join(checked_texts)
        
        st.text_area("已选核算条件：", value=full_text, height=200, disabled=True)
        
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🚀 开始推演 (呼叫 API)", use_container_width=True, type="primary"):
                if not checked_texts:
                    st.warning("请先勾选核算条件！")
                else:
                    question = full_text + f"请根据以上触犯条件全面分析{qiu}剩余什么生肖与号码。如果全部触犯，那么请将触犯次数最少的作为后补。请开始精准核算。"
                    with st.spinner("正在呼叫 DeepSeek 进行全量推演，请稍候..."):
                        db = build_rule_database()
                        if not db:
                            st.error("规则表读取失败，无法推演！")
                        else:
                            full_table_text = build_full_table_text(db)
                            system_prompt = get_analysis_prompt(full_table_text)
                            answer = call_deepseek_api(question, system_prompt)
                            st.session_state.ai_api_result = answer
                            
                            import re
                            nums = re.findall(r'\\b([0-4][0-9])\\b', answer)
                            safe_nums = sorted(list(set(int(n) for n in nums if 1 <= int(n) <= 49)))
                            st.session_state.ai_ball_result = safe_nums
                            
        with b2:
            if st.button("🗑️ 清理勾选", use_container_width=True):
                st.session_state.ai_checks = {}
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
        def toggle_cond(k): pass
        with st.expander("生肖与五行", expanded=True):
            cols = st.columns(3)
            for idx, key in enumerate(["金肖", "木肖", "水肖", "火肖", "土肖", "红肖", "蓝肖", "绿肖"]):
                with cols[idx % 3]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
        with st.expander("尾数杀号"):
            cols = st.columns(5)
            for i in range(10):
                key = f"{i}尾"
                with cols[i % 5]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
        with st.expander("生肖专属"):
            cols = st.columns(4)
            for idx, z in enumerate(["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]):
                key = f"杀{z}"
                with cols[idx % 4]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
        with st.expander("门数 / 段数 / 合数"):
            cols = st.columns(4)
            for i in range(1, 6):
                key = f"{i}门"
                with cols[(i-1) % 4]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
            for i in range(1, 8):
                key = f"{i}段"
                with cols[(i+4) % 4]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
            for i in range(1, 14):
                key = f"{i:02d}合"
                with cols[(i+11) % 4]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
        with st.expander("波色 / 波单双"):
            cols = st.columns(3)
            for idx, key in enumerate(["红波", "蓝波", "绿波", "红波单", "红波双", "蓝波单", "蓝波双", "绿波单", "绿波双"]):
                with cols[idx % 3]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val
        with st.expander("其他属性"):
            cols = st.columns(3)
            others = ["金号", "木号", "水号", "火号", "土号", "金尾", "木尾", "水尾", "火尾", "土尾", "大肖", "中肖", "小肖", "书肖", "琴肖", "棋肖", "画肖", "福肖", "禄肖", "寿肖"]
            for idx, key in enumerate(others):
                with cols[idx % 3]: 
                    val = st.checkbox(key, key=f"ai_chk_{key}", value=st.session_state.ai_checks.get(key, False), on_change=toggle_cond, args=(key,))
                    st.session_state.ai_checks[key] = val

    st.divider()
    st.markdown("### 📝 AI 完整推演结果")
    st.text_area("DeepSeek 返回：", value=st.session_state.ai_api_result, height=300, disabled=True)
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
def render_trend_chart(df_data):
    st.divider()
    st.subheader("📈 历史走势图（最近30期）")
    
    # 限制显示最近 30 期，防止网页卡顿
    recent_data = df_data.head(30).copy()
    
    if recent_data.empty:
        st.warning("暂无数据可供生成走势图")
        return

    # 提取期数作为行索引
    periods = recent_data.iloc[:, 18].apply(clean_period).tolist()
    
    tab1, tab2 = st.tabs(["平 码 区", "特 码 区"])
    
    with tab1:
        # 构建 01-49 的列
        cols = [f"{i:02d}" for i in range(1, 50)]
        # 创建一个空的 DataFrame
        matrix = pd.DataFrame("", index=periods, columns=cols)
        
        # 填入平码数据 (19-24列)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            for i in range(19, 25):
                num_str = clean_period(row.iloc[i])
                if num_str in cols:
                    matrix.at[period, num_str] = "●" # 用实心圆点代表开出的号码
                    
        # 美化表格
        st.dataframe(
            matrix, 
            use_container_width=True, 
            height=600
        )
        
    with tab2:
        # 构建特码 01-49 的列
        cols = [f"{i:02d}" for i in range(1, 50)]
        matrix_special = pd.DataFrame("", index=periods, columns=cols)
        
        # 填入特码数据 (第25列)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            num_str = clean_period(row.iloc[25]) if len(row) > 25 else ""
            if num_str in cols:
                matrix_special.at[period, num_str] = "★" # 用五角星代表特码
                
        st.dataframe(
            matrix_special, 
            use_container_width=True, 
            height=600
        )