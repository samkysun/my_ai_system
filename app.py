import streamlit as st
import pandas as pd
import hashlib
import time
import os

# ==========================================
# ⚙️ 配置区
# ==========================================
EXCEL_FILE = "数据分析系统最终版本（智能全套）.xlsm" 
SHEET_NAME = "总数据" 

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
    .ball-container { display: flex; gap: 12px; justify-content: center; margin: 20px 0; align-items: center; }
    .ball {
        width: 55px; height: 55px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px; font-weight: bold; color: white;
        box-shadow: 2px 4px 8px rgba(0,0,0,0.3); text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
    }
    .ball-red { background: radial-gradient(circle at 30% 30%, #fca5a5, #dc2626); }
    .ball-blue { background: radial-gradient(circle at 30% 30%, #93c5fd, #2563eb); }
    .ball-green { background: radial-gradient(circle at 30% 30%, #86efac, #16a34a); }
    .ball-special { background: radial-gradient(circle at 30% 30%, #fde047, #ca8a04); border: 2px solid #fff; }
</style>
""", unsafe_allow_html=True)

# 初始化状态
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "ai_input_text" not in st.session_state: st.session_state.ai_input_text = ""
if "ai_result_text" not in st.session_state: st.session_state.ai_result_text = "等待推演..."

# ==========================================
# 2. 用户系统 (登录/注册)
# ==========================================
USER_FILE = "users.csv"

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

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
                match = users_df[(users_df['username'] == login_user) & (users_df['password'] == hash_password(login_pass))]
                if not match.empty:
                    st.session_state.logged_in = True
                    st.session_state.username = login_user
                    st.success("登录成功！")
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
                        st.error("该用户名已被注册")
                    else:
                        save_user(reg_user, reg_pass)
                        st.success("🎉 注册成功！请去左侧登录。")
            else:
                st.warning("请填写完整信息")

# ==========================================
# 3. 数据读取与辅助函数
# ==========================================
@st.cache_data
def load_real_data():
    if not os.path.exists(EXCEL_FILE): return None
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
        return df.dropna(how='all')
    except Exception as e:
        return str(e)

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

    
     #==========================================
    # 页面 1：主控制台
    # ==========================================
    if menu == "🏠 主控制台":
        st.title("🧊 智能数据分析总控台")
        if df_data is None or isinstance(df_data, str):
            st.error(f"❌ 数据读取失败：{EXCEL_FILE}")
            return

        raw_periods = df_data.iloc[:, 18].apply(clean_period).tolist()
        unique_periods = list(set([p for p in raw_periods if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)

        if unique_periods:
            col_period, col_btn = st.columns([2, 1])
            with col_period: selected_period = st.selectbox("🎯 请选择期数：", unique_periods)
            
            df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
            matched_rows = df_data[df_data['_temp_period'] == selected_period]
            
            if not matched_rows.empty:
                current_row = matched_rows.iloc[0]
                try:
                    flat_nums = [int(current_row.iloc[i]) for i in range(19, 25) if pd.notna(current_row.iloc[i])]
                    special_num = int(current_row.iloc[25]) if pd.notna(current_row.iloc[25]) else 0
                except: flat_nums, special_num = [], 0

                st.subheader(f"🎯 {selected_period} 期开奖结果")
                balls_html = '<div class="ball-container">'
                for num in flat_nums: balls_html += f'<div class="ball {get_ball_color(num)}">{num:02d}</div>'
                if special_num > 0: balls_html += f'<div class="ball {get_ball_color(special_num)} ball-special">★ {special_num:02d}</div>'
                balls_html += '</div>'
                st.markdown(balls_html, unsafe_allow_html=True)

            st.divider()
            st.subheader("📋 历史数据预览 (最新10期)")
            show_df = df_data.drop(columns=['_temp_period']).tail(10)
            st.dataframe(show_df, use_container_width=True, hide_index=True)

    # ==========================================
    # 页面 2：同现频率统计
    # ==========================================
    elif menu == "📈 同现频率统计":
        st.title("📈 历史同现深度分析")
        if df_data is None or isinstance(df_data, str):
            st.error("数据加载失败。")
            return
            
        col_num, col_top = st.columns(2)
        with col_num: target_num = st.number_input("目标号码 (1-49):", min_value=1, max_value=49, value=30)
        with col_top: top_n = st.selectbox("提取前几名:", [3, 5, 8, 10])

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
                                counts[int(num)] = counts.get(int(num), 0) + 1
                    
                    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
                    result_df = pd.DataFrame([{"排名": f"Top {i+1}", "同频号码": f"{num:02d}", "同现次数": count} for i, (num, count) in enumerate(sorted_counts)])
                    
                    st.success(f"与 {target_num:02d} 号同现频率最高的结果：")
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    st.bar_chart(result_df.set_index("同频号码")["同现次数"])

    # ---------- 页面 3：AI 智能推演 ----------
elif menu == "?? AI 智能推演":
    st.title("?? AI 严谨推演系统")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        period = st.selectbox("期数：", ["2026117", "2026116"])
    with c2:
        ball = st.selectbox("球号：", [f"第{i}球" for i in range(1, 8)])
    with c3:
        mode = st.radio("模式：", ["升序", "按序"], horizontal=True)
    with c4:
        if st.button("一键清空"):
            st.session_state.ai_input_text = ""
            st.session_state.ai_result_text = "等待推演..."
            st.rerun()

    # ★ 这里是所有的分类和对应的号码文本，完全和你 VBA 一模一样
    CHECKBOX_MAP = {
        "0尾": "杀0尾（10、20、30、40），", "1尾": "杀1尾（01、11、21、31、41），", "2尾": "杀2尾（02、12、22、32、42），",
        "3尾": "杀3尾（03、13、23、33、43），", "4尾": "杀4尾（04、14、24、34、44），", "5尾": "杀5尾（05、15、25、35、45），",
        "6尾": "杀6尾（06、16、26、36、46），", "7尾": "杀7尾（07、17、27、37、47），", "8尾": "杀8尾（08、18、28、38、48），", "9尾": "杀9尾（09、19、29、39、49），",
        "金号": "杀金号（04、05、12、13、26、27、34、35、42、43），", "木号": "杀木号（08、09、16、17、24、25、38、39、46、47），",
        "水号": "杀水号（01、14、15、22、23、30、31、44、45），", "火号": "杀火号（02、03、10、11、18、19、32、33、40、41、48、49），", "土号": "杀土号（06、07、20、21、28、29、36、37），",
        "红波": "杀红波（01、02、07、08、12、13、18、19、23、24、29、30、34、35、40、45、46），", 
        "蓝波": "杀蓝波（03、04、09、10、14、15、20、25、26、31、36、37、41、42、47、48），", 
        "绿波": "杀绿波（05、06、11、16、17、21、22、27、28、32、33、38、39、43、44、49），",
        "杀鼠": "杀鼠，", "杀牛": "杀牛，", "杀虎": "杀虎，", "杀兔": "杀兔，", "杀龙": "杀龙，", "杀蛇": "杀蛇，",
        "杀马": "杀马，", "杀羊": "杀羊，", "杀猴": "杀猴，", "杀鸡": "杀鸡，", "杀狗": "杀狗，", "杀猪": "杀猪，",
        "金肖": "杀金肖（猴鸡），", "木肖": "杀木肖（虎兔），", "水肖": "杀水肖（鼠猪），", "火肖": "杀火肖（蛇马），", "土肖": "杀土肖（牛龙羊狗），",
        "阴天": "杀阴天（马龙猪），", "阳天": "杀阳天（兔牛猴），", "阴地": "杀阴地（蛇鼠狗），", "阳地": "杀阳地（虎鸡羊），",
        "大肖": "杀大肖（牛虎龙马），", "中肖": "杀中肖（羊猴狗猪），", "小肖": "杀小肖（鼠兔蛇鸡），",
        "家臣": "杀家臣（马牛猪狗），", "美女": "杀美女（蛇兔鸡羊），", "君王": "杀君王（龙虎），", "恶人": "杀恶人（鼠猴），",
        "东": "杀东（虎兔龙），", "南": "杀南（蛇马羊），", "西": "杀西（猴鸡狗），", "北": "杀北（猪鼠牛），",
        "3余0": "杀3余0（杀0，3，6，9尾），", "3余1": "杀3余1（杀1，4，7尾），", "3余2": "杀3余2（杀2，5，8尾），",
        "1门": "杀1门（01、02、03、04、05、06、07、08、09），", "2门": "杀2门（10、11、12、13、14、15、16、17、18、19），",
        "3门": "杀3门（20、21、22、23、24、25、26、27、28、29），", "4门": "杀4门（30、31、32、33、34、35、36、37、38、39），", "5门": "杀5门（40、41、42、43、44、45、46、47、48、49），",
        "1段": "杀1段（01、02、03、04、05、06、07），", "2段": "杀2段（08、09、10、11、12、13、14），", "3段": "杀3段（15、16、17、18、19、20、21），",
        "4段": "杀4段（22、23、24、25、26、27、28），", "5段": "杀5段（29、30、31、32、33、34、35），", "6段": "杀6段（36、37、38、39、40、41、42），", "7段": "杀7段（43、44、45、46、47、48、49），",
        "01合": "杀01合（01、10），", "02合": "杀02合（02、11、20），", "03合": "杀03合（03、12、21、30），",
        "04合": "杀04合（04、13、22、31、40），", "05合": "杀05合（05、14、23、32、41），", "06合": "杀06合（06、15、24、33、42），",
        "07合": "杀07合（07、16、25、34、43），", "08合": "杀08合（08、17、26、35、44），", "09合": "杀09合（09、18、27、36、45），",
        "10合": "杀10合（19、28、37、46），", "11合": "杀11合（29、38、47），", "12合": "杀12合（39、48），", "13合": "杀13合（49），",
        "红肖": "杀红肖（马兔鼠鸡），", "蓝肖": "杀蓝肖（虎猴蛇猪），", "绿肖": "杀绿肖（龙狗牛羊），",
        "书肖": "杀书肖（马龙虎），", "琴肖": "杀琴肖（蛇兔鸡），", "棋肖": "杀棋肖（牛鼠狗），", "画肖": "杀画肖（猪猴羊），",
        "福肖": "杀福肖（马龙虎鼠），", "禄肖": "杀禄肖（兔牛猪猴），", "寿肖": "杀寿肖（蛇狗鸡羊），",
        "红波单": "杀红波单（01、07、13、19、23、29、35、45），", "红波双": "杀红波双（02、08、12、18、24、30、34、40、46），",
        "蓝波单": "杀蓝波单（03、09、15、25、31、37、41、47），", "蓝波双": "杀蓝波双（04、10、14、20、26、36、42、48），",
        "绿波单": "杀绿波单（05、11、17、21、27、33、39、43、49），", "绿波双": "杀绿波双（06、16、22、28、32、38、44），",
        "金尾": "杀金尾（04、09、14、19、24、29、34、39、44、49），", "木尾": "杀木尾（03、08、13、18、23、28、33、38、43、48），",
        "水尾": "杀水尾（01、06、11、16、21、26、31、36、41、46），", "火尾": "杀火尾（02、07、12、17、22、27、32、37、42、47），", "土尾": "杀土尾（05、10、15、20、25、30、35、40、45），"
    }

    def toggle_chk(label):
        txt = CHECKBOX_MAP[label]
        if st.checkbox(label):
            if txt not in st.session_state.ai_input_text:
                st.session_state.ai_input_text += txt
        else:
            st.session_state.ai_input_text = st.session_state.ai_input_text.replace(txt, "")

    col_left, col_right = st.columns(2)
    with col_left:
        st.text_area("条件输入：", value=st.session_state.ai_input_text, height=250)
        st.text_area("推演结果：", value=st.session_state.ai_result_text, height=250, disabled=True)
        if st.button("?? 开始推演", use_container_width=True):
            st.session_state.ai_result_text = "推演完成！"
            st.rerun()

    with col_right:
        with st.expander("?? 生肖与五行", expanded=True):
            cols = st.columns(3)
            for idx, key in enumerate(["金肖", "木肖", "水肖", "火肖", "土肖", "红肖", "蓝肖", "绿肖"]):
                with cols[idx % 3]:
                    toggle_chk(key)
        with st.expander("?? 尾数杀号"):
            cols = st.columns(5)
            for i in range(10):
                with cols[i % 5]:
                    toggle_chk(f"{i}尾")
        with st.expander("?? 生肖专属"):
            cols = st.columns(4)
            for idx, z in enumerate(["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]):
                with cols[idx % 4]:
                    toggle_chk(f"杀{z}")
        with st.expander("?? 门数 / 段数 / 合数"):
            cols = st.columns(4)
            for i in range(1, 6):
                with cols[(i-1) % 4]:
                    toggle_chk(f"{i}门")
            for i in range(1, 8):
                with cols[(i+4) % 4]:
                    toggle_chk(f"{i}段")
            for i in range(1, 14):
                with cols[(i+11) % 4]:
                    toggle_chk(f"{i:02d}合")
        with st.expander("?? 波色 / 波单双"):
            cols = st.columns(3)
            for idx, key in enumerate(["红波", "蓝波", "绿波", "红波单", "红波双", "蓝波单", "蓝波双", "绿波单", "绿波双"]):
                with cols[idx % 3]:
                    toggle_chk(key)
        with st.expander("? 其他属性"):
            cols = st.columns(3)
            others = ["金号", "木号", "水号", "火号", "土号", "金尾", "木尾", "水尾", "火尾", "土尾", "大肖", "中肖", "小肖", "书肖", "琴肖", "棋肖", "画肖", "福肖", "禄肖", "寿肖"]
            for idx, key in enumerate(others):
                with cols[idx % 3]:
                    toggle_chk(key)
# ==========================================
# 5. 路由控制
# ==========================================
if not st.session_state.logged_in:
    login_page()
else:
    main_app()