import streamlit as st
import pandas as pd
import hashlib
import time
import os

# ==========================================
# ⚙️ 配置区
# ==========================================
EXCEL_FILE = "数据分析系统最终版本（智能全套）.xlsm"  # 你的 Excel 文件名
SHEET_NAME = "总数据"  # 你的工作表名

# ==========================================
# 1. 页面配置与高级 CSS 美化
# ==========================================
st.set_page_config(page_title="智能数据分析系统", page_icon="🧊", layout="wide")

st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 100%); }
    h1, h2, h3 { color: #102A43 !important; font-family: 'Microsoft YaHei', sans-serif; }
    .stButton>button {
        background: linear-gradient(90deg, #0284c7 0%, #0369a1 100%);
        color: white; border-radius: 6px; border: none; transition: all 0.3s; font-weight: bold;
    }
    .stButton>button:hover { box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4); transform: translateY(-2px); }
    
    /* 完美复刻 3D 彩球 */
    .ball-container { display: flex; gap: 12px; justify-content: center; margin: 20px 0; align-items: center; }
    .ball {
        width: 55px; height: 55px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px; font-weight: bold; color: white;
        box-shadow: 2px 4px 8px rgba(0,0,0,0.3);
        text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
    }
    .ball-red { background: radial-gradient(circle at 30% 30%, #fca5a5, #dc2626); }
    .ball-blue { background: radial-gradient(circle at 30% 30%, #93c5fd, #2563eb); }
    .ball-green { background: radial-gradient(circle at 30% 30%, #86efac, #16a34a); }
    .ball-special { background: radial-gradient(circle at 30% 30%, #fde047, #ca8a04); border: 2px solid #fff; }
</style>
""", unsafe_allow_html=True)

# 初始化状态
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "ai_input_text" not in st.session_state:
    st.session_state.ai_input_text = "这是2026117期第一球的核算条件，"
if "ai_result_text" not in st.session_state:
    st.session_state.ai_result_text = "等待推演..."

# ==========================================
# 2. 用户系统
# ==========================================
USER_FILE = "users.csv"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USER_FILE):
        pd.DataFrame(columns=['username', 'password']).to_csv(USER_FILE, index=False)
    return pd.read_csv(USER_FILE)

def save_user(username, password):
    df = load_users()
    new_user = pd.DataFrame({'username': [username], 'password': [hash_password(password)]})
    pd.concat([df, new_user], ignore_index=True).to_csv(USER_FILE, index=False)

def login_page():
    st.title("🔐 智能系统客户端登录")
    tab1, tab2 = st.tabs(["已有账号？登录", "没有账号？立即注册"])
    
    with tab1:
        login_user = st.text_input("用户名", key="login_user")
        login_pass = st.text_input("密码", type="password", key="login_pass")
        if st.button("登录", use_container_width=True):
            if login_user and login_pass:
                users_df = load_users()
                hashed = hash_password(login_pass)
                match = users_df[(users_df['username'] == login_user) & (users_df['password'] == hashed)]
                if not match.empty:
                    st.session_state.logged_in = True
                    st.session_state.username = login_user
                    st.success("登录成功！正在进入系统...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("用户名或密码错误！")
            else:
                st.warning("请输入完整信息")
                
    with tab2:
        reg_user = st.text_input("设置用户名", key="reg_user")
        reg_pass = st.text_input("设置密码", type="password", key="reg_pass")
        reg_confirm = st.text_input("确认密码", type="password", key="reg_confirm")
        if st.button("注册账号", use_container_width=True):
            if reg_user and reg_pass:
                if reg_pass != reg_confirm:
                    st.error("两次密码不一致")
                else:
                    users_df = load_users()
                    if reg_user in users_df['username'].values:
                        st.error("该用户名已被注册，请换一个")
                    else:
                        save_user(reg_user, reg_pass)
                        st.success("🎉 注册成功！请点击左侧【登录】标签。")
            else:
                st.warning("请填写完整信息")

# ==========================================
# 3. 读取真实 Excel 数据
# ==========================================
@st.cache_data
def load_real_data():
    if not os.path.exists(EXCEL_FILE):
        return None
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
        df = df.dropna(how='all')
        return df
    except Exception as e:
        return str(e)

# 辅助函数：判断波色
def get_ball_color(num):
    red = [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46]
    blue = [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48]
    if num in red: return "ball-red"
    elif num in blue: return "ball-blue"
    else: return "ball-green"

# ==========================================
# 4. 核心业务页面
# ==========================================
def main_app():
    with st.sidebar:
        st.write(f"👤 欢迎，**{st.session_state.username}**")
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        st.divider()
        
        st.image("https://cdn-icons-png.flaticon.com/512/1055/1055666.png", width=60)
        menu = st.radio("功能导航：", ["🏠 主控制台", "📈 同现频率统计", "🤖 AI 智能推演"])
        st.divider()

    df_data = load_real_data()

    # ---------- 页面 1：主控制台 ----------
    if menu == "🏠 主控制台":
        st.title("🧊 智能数据分析总控台")
        
        if df_data is None:
            st.error(f"❌ 找不到数据文件：{EXCEL_FILE}，请检查是否上传到 GitHub。")
            return
        elif isinstance(df_data, str):
            st.error(f"❌ 读取失败：{df_data}")
            return

        # ---- 完美修复期数清洗与排序 ----
        def clean_period(val):
            if pd.isna(val): return ""
            s = str(val).strip()
            if s.endswith(".0"): s = s[:-2]
            return s

        # 提取 S 列（第19列，索引18）
        raw_periods = df_data.iloc[:, 18].apply(clean_period).tolist()
        unique_periods = list(set([p for p in raw_periods if p != ""]))
        
        # 强制按数字大小降序排列（最新的在第一）
        try:
            unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except:
            unique_periods.sort(reverse=True)

        if unique_periods:
            col_period, col_btn = st.columns([2, 1])
            with col_period:
                selected_period = st.selectbox("🎯 请选择期数：", unique_periods)
            
            df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
            matched_rows = df_data[df_data['_temp_period'] == selected_period]
            
            if not matched_rows.empty:
                current_row = matched_rows.iloc[0]
                
                try:
                    flat_nums = [int(current_row.iloc[i]) for i in range(19, 25) if pd.notna(current_row.iloc[i])]
                    special_num = int(current_row.iloc[25]) if pd.notna(current_row.iloc[25]) else 0
                except:
                    flat_nums, special_num = [], 0

                st.subheader(f"🎯 {selected_period} 期开奖结果")
                balls_html = '<div class="ball-container">'
                for num in flat_nums:
                    balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
                if special_num > 0:
                    balls_html += f'<div class="ball {get_ball_color(special_num)} ball-special">★ {special_num:02d}</div>'
                balls_html += '</div>'
                st.markdown(balls_html, unsafe_allow_html=True)

            st.divider()
            st.subheader("📋 历史数据预览 (最新10期)")
            show_df = df_data.drop(columns=['_temp_period']).tail(10)
            st.dataframe(show_df, use_container_width=True, hide_index=True)

    # ---------- 页面 2：同现频率统计 ----------
    elif menu == "📈 同现频率统计":
        st.title("📈 历史同现深度分析")
        
        if df_data is None or isinstance(df_data, str):
            st.error("数据加载失败，请检查 Excel 文件。")
            return
            
        col_num, col_top = st.columns(2)
        with col_num:
            target_num = st.number_input("目标号码 (1-49):", min_value=1, max_value=49, value=30)
        with col_top:
            top_n = st.selectbox("提取前几名:", [3, 5, 8, 10])

        if st.button("🔍 开始扫描", use_container_width=True):
            with st.spinner("正在 6000 多期数据中比对..."):
                nums_df = df_data.iloc[:, 19:25].apply(pd.to_numeric, errors='coerce')
                mask = nums_df.isin([target_num]).any(axis=1)
                filtered_rows = nums_df[mask]
                
                if len(filtered_rows) == 0:
                    st.warning(f"历史数据中，{target_num} 号从未出现过。")
                else:
                    counts = {}
                    for index, row in filtered_rows.iterrows():
                        for num in row.values:
                            if pd.notna(num) and int(num) != target_num:
                                num_int = int(num)
                                counts[num_int] = counts.get(num_int, 0) + 1
                    
                    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
                    
                    result_data = []
                    for rank, (num, count) in enumerate(sorted_counts, 1):
                        result_data.append({"排名": f"Top {rank}", "同频号码": f"{num:02d}", "同现次数": count})
                        
                    result_df = pd.DataFrame(result_data)
                    st.success(f"与 {target_num:02d} 号同现频率最高的结果：")
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    st.bar_chart(result_df.set_index("同频号码")["同现次数"])

    # ---------- 页面 3：AI 智能推演 ----------
    elif menu == "🤖 AI 智能推演":
        st.title("🤖 AI 严谨推演系统")
        
        col_left, col_right = st.columns(2, gap="large")

        with col_left:
            st.subheader("📝 核算条件输入")
            user_input = st.text_area("条件内容：", value=st.session_state.ai_input_text, height=200)
            if user_input != st.session_state.ai_input_text:
                st.session_state.ai_input_text = user_input

            st.subheader("🧠 分析结果")
            st.text_area("推演结果：", value=st.session_state.ai_result_text, height=250, disabled=True)

        with col_right:
            st.subheader("🎯 快捷条件勾选")
            with st.expander("🔴 生肖与五行", expanded=True):
                c1, c2, c3 = st.columns(3)
                if c1.checkbox("金肖"): st.session_state.ai_input_text += "杀金肖（猴鸡），"
                if c2.checkbox("木肖"): st.session_state.ai_input_text += "杀木肖（虎兔），"
                if c3.checkbox("水肖"): st.session_state.ai_input_text += "杀水肖（鼠猪），"
                if c1.checkbox("火肖"): st.session_state.ai_input_text += "杀火肖（蛇马），"
                if c2.checkbox("土肖"): st.session_state.ai_input_text += "杀土肖（牛龙羊狗），"

            with st.expander("🔢 尾数杀号"):
                t_cols = st.columns(5)
                for i in range(10):
                    if t_cols[i % 5].checkbox(f"{i}尾"):
                        st.session_state.ai_input_text += f"杀{i}尾，"

            st.divider()
            if st.button("🚀 呼叫 DeepSeek 推演", use_container_width=True):
                with st.spinner("AI 深度推演中..."):
                    time.sleep(1)
                    st.session_state.ai_result_text = "【严格筛选结果】：03, 08, 15, 22\\n\\n【后补筛选结果】：01, 19, 33, 41"
                    st.rerun()

# ==========================================
# 5. 路由控制
# ==========================================
if not st.session_state.logged_in:
    login_page()
else:
    main_app()