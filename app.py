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
    
    # 初始化状态变量
    if "ai_input_text" not in st.session_state:
        st.session_state.ai_input_text = ""
    if "ai_result_text" not in st.session_state:
        st.session_state.ai_result_text = "等待推演..."
    if "selected_period" not in st.session_state:
        st.session_state.selected_period = ""
    if "selected_ball" not in st.session_state:
        st.session_state.selected_ball = "第一球"
    if "order_mode" not in st.session_state:
        st.session_state.order_mode = "升序"
        
    # 提取所有期数
    period_list = []
    if df_data is not None and not isinstance(df_data, str):
        raw_periods = df_data.iloc[:, 18].apply(clean_period).tolist()
        period_list = list(set([p for p in raw_periods if p != ""]))
        try:
            period_list.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except:
            period_list.sort(reverse=True)
    
    if not period_list:
        period_list = ["暂无数据"]
        
    # 顶部控制栏
    st.markdown("### 🎯 核算条件生成")
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        selected_period = st.selectbox("选择期数：", period_list, index=0)
        st.session_state.selected_period = selected_period
    with col2:
        selected_ball = st.selectbox("选择球号：", [f"第{i}球" for i in range(1, 8)], index=0)
        st.session_state.selected_ball = selected_ball
    with col3:
        order_mode = st.radio("计算方式：", ["升序", "按序"], horizontal=True)
        st.session_state.order_mode = order_mode
    with col4:
        st.write("")
        st.write("")
        if st.button("🗑️ 一键清空", use_container_width=True):
            # 取消所有勾选，并清空文本
            for key in st.session_state.keys():
                if key.startswith("chk_"):
                    st.session_state[key] = False
            st.session_state.ai_input_text = ""
            st.session_state.ai_result_text = "等待推演..."
            st.rerun()

    # 生成前缀的函数
    def get_prefix(period, ball, mode):
        interval = ""
        if mode == "按序":
            interval = f"{ball}的取值区间为1号至49号之间，"
        else:
            ball_ranges = {
                "第一球": "第一球的取值区间为1号至20号之间，", "第二球": "第二球的取值区间为2号至25号之间，",
                "第三球": "第三球的取值区间为3号至30号之间，", "第四球": "第四球的取值区间为4号至40号之间，",
                "第五球": "第五球的取值区间为15号至48号之间，", "第六球": "第六球的取值区间为25号至49号之间，",
                "第七球": "第七球的取值区间为1号至49号之间，"
            }
            interval = ball_ranges.get(ball, "")
        return f"这是{period}期{mode}{ball}的核算条件，{interval}"

    # ============================================================
    # ★ 完美对齐 VBA 逻辑的字典
    # ============================================================
    checkbox_map = {
        # 1. 尾数（动态生成 01 11 21...）
        "0尾": "杀0尾（10、20、30、40），", "1尾": "杀1尾（01、11、21、31、41），", "2尾": "杀2尾（02、12、22、32、42），",
        "3尾": "杀3尾（03、13、23、33、43），", "4尾": "杀4尾（04、14、24、34、44），", "5尾": "杀5尾（05、15、25、35、45），",
        "6尾": "杀6尾（06、16、26、36、46），", "7尾": "杀7尾（07、17、27、37、47），", "8尾": "杀8尾（08、18、28、38、48），", "9尾": "杀9尾（09、19、29、39、49），",
        # 2. 号五行
        "金号": "杀金号（04、05、12、13、26、27、34、35、42、43），", "木号": "杀木号（08、09、16、17、24、25、38、39、46、47），",
        "水号": "杀水号（01、14、15、22、23、30、31、44、45），", "火号": "杀火号（02、03、10、11、18、19、32、33、40、41、48、49），", 
        "土号": "杀土号（06、07、20、21、28、29、36、37），",
        # 3. 波色
        "红波": "杀红波（01、02、07、08、12、13、18、19、23、24、29、30、34、35、40、45、46），", 
        "蓝波": "杀蓝波（03、04、09、10、14、15、20、25、26、31、36、37、41、42、47、48），", 
        "绿波": "杀绿波（05、06、11、16、17、21、22、27、28、32、33、38、39、43、44、49），",
        # 4. 生肖
        "杀鼠": "杀鼠，", "杀牛": "杀牛，", "杀虎": "杀虎，", "杀兔": "杀兔，", "杀龙": "杀龙，", "杀蛇": "杀蛇，",
        "杀马": "杀马，", "杀羊": "杀羊，", "杀猴": "杀猴，", "杀鸡": "杀鸡，", "杀狗": "杀狗，", "杀猪": "杀猪，",
        # 5. 五行肖
        "金肖": "杀金肖（猴鸡），", "木肖": "杀木肖（虎兔），", "水肖": "杀水肖（鼠猪），", "火肖": "杀火肖（蛇马），", "土肖": "杀土肖（牛龙羊狗），",
        # 6. 常规属性
        "阴天": "杀阴天（马龙猪），", "阳天": "杀阳天（兔牛猴），", "阴地": "杀阴地（蛇鼠狗），", "阳地": "杀阳地（虎鸡羊），",
        "大肖": "杀大肖（牛虎龙马），", "中肖": "杀中肖（羊猴狗猪），", "小肖": "杀小肖（鼠兔蛇鸡），",
        "家臣": "杀家臣（马牛猪狗），", "美女": "杀美女（蛇兔鸡羊），", "君王": "杀君王（龙虎），", "恶人": "杀恶人（鼠猴），",
        "东": "杀东（虎兔龙），", "南": "杀南（蛇马羊），", "西": "杀西（猴鸡狗），", "北": "杀北（猪鼠牛），",
        "3余0": "杀3余0（杀0，3，6，9尾），", "3余1": "杀3余1（杀1，4，7尾），", "3余2": "杀3余2（杀2，5，8尾），",
        # 7. 门数
        "1门": "杀1门（01、02、03、04、05、06、07、08、09），", "2门": "杀2门（10、11、12、13、14、15、16、17、18、19），",
        "3门": "杀3门（20、21、22、23、24、25、26、27、28、29），", "4门": "杀4门（30、31、32、33、34、35、36、37、38、39），", 
        "5门": "杀5门（40、41、42、43、44、45、46、47、48、49），",
        # 8. 段数
        "1段": "杀1段（01、02、03、04、05、06、07），", "2段": "杀2段（08、09、10、11、12、13、14），", "3段": "杀3段（15、16、17、18、19、20、21），",
        "4段": "杀4段（22、23、24、25、26、27、28），", "5段": "杀5段（29、30、31、32、33、34、35），", "6段": "杀6段（36、37、38、39、40、41、42），", 
        "7段": "杀7段（43、44、45、46、47、48、49），",
        # 9. 合数
        "01合": "杀01合（01、10），", "02合": "杀02合（02、11、20），", "03合": "杀03合（03、12、21、30），",
        "04合": "杀04合（04、13、22、31、40），", "05合": "杀05合（05、14、23、32、41），", "06合": "杀06合（06、15、24、33、42），",
        "07合": "杀07合（07、16、25、34、43），", "08合": "杀08合（08、17、26、35、44），", "09合": "杀09合（09、18、27、36、45），",
        "10合": "杀10合（19、28、37、46），", "11合": "杀11合（29、38、47），", "12合": "杀12合（39、48），", "13合": "杀13合（49），",
        # 10. 红蓝绿肖
        "红肖": "杀红肖（马兔鼠鸡），", "蓝肖": "杀蓝肖（虎猴蛇猪），", "绿肖": "杀绿肖（龙狗牛羊），",
        # 11. 琴棋书画
        "书肖": "杀书肖（马龙虎），", "琴肖": "杀琴肖（蛇兔鸡），", "棋肖": "杀棋肖（牛鼠狗），", "画肖": "杀画肖（猪猴羊），",
        # 12. 福禄寿
        "福肖": "杀福肖（马龙虎鼠），", "禄肖": "杀禄肖（兔牛猪猴），", "寿肖": "杀寿肖（蛇狗鸡羊），",
        # 13. 波单双
        "红波单": "杀红波单（01、07、13、19、23、29、35、45），", "红波双": "杀红波双（02、08、12、18、24、30、34、40、46），",
        "蓝波单": "杀蓝波单（03、09、15、25、31、37、41、47），", "蓝波双": "杀蓝波双（04、10、14、20、26、36、42、48），",
        "绿波单": "杀绿波单（05、11、17、21、27、33、39、43、49），", "绿波双": "杀绿波双（06、16、22、28、32、38、44），",
        # 14. 五行尾
        "金尾": "杀金尾（04、09、14、19、24、29、34、39、44、49），", "木尾": "杀木尾（03、08、13、18、23、28、33、38、43、48），",
        "水尾": "杀水尾（01、06、11、16、21、26、31、36、41、46），", "火尾": "杀火尾（02、07、12、17、22、27、32、37、42、47），", 
        "土尾": "杀土尾（05、10、15、20、25、30、35、40、45），"
    }

    # 更新文本的方法
    def handle_checkbox(label, text_to_add):
        chk_key = f"chk_{label}"
        if st.checkbox(label, key=chk_key):
            if text_to_add not in st.session_state.ai_input_text:
                st.session_state.ai_input_text += text_to_add
        else:
            st.session_state.ai_input_text = st.session_state.ai_input_text.replace(text_to_add, "")

    st.divider()
    
    # 左右两栏布局
    col_left, col_right = st.columns([1.2, 1], gap="large")

    # ---------------- 左侧：输入框与结果 ----------------
    with col_left:
        # 动态前缀处理
        current_prefix = get_prefix(selected_period, selected_ball, order_mode)
        if current_prefix not in st.session_state.ai_input_text:
            st.session_state.ai_input_text = current_prefix + st.session_state.ai_input_text.replace(current_prefix, "")

        st.subheader("📝 核算条件输入")
        user_input = st.text_area("生成的条件：", value=st.session_state.ai_input_text, height=250)
        if user_input != st.session_state.ai_input_text:
            st.session_state.ai_input_text = user_input

        st.subheader("🧠 分析结果")
        st.text_area("推演结果：", value=st.session_state.ai_result_text, height=300, disabled=True)
        
        if st.button("🚀 呼叫 DeepSeek 推演", use_container_width=True, type="primary"):
            with st.spinner("AI 深度推演中..."):
                time.sleep(1.5)
                st.session_state.ai_result_text = "【严格筛选结果】：03, 08, 15, 22\\n\\n【后补筛选结果】：01, 19, 33, 41\\n\\n【推演逻辑】：结合历史同频数据与限定区间..."
                st.rerun()

    # ---------------- 右侧：所有复选框折叠面板 ----------------
    with col_right:
        st.subheader("🎯 快捷条件勾选")
        
        with st.expander("🔴 生肖与五行 / 肖色", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1: handle_checkbox("金肖", checkbox_map["金肖"]); handle_checkbox("木肖", checkbox_map["木肖"])
            with c2: handle_checkbox("水肖", checkbox_map["水肖"]); handle_checkbox("火肖", checkbox_map["火肖"])
            with c3: handle_checkbox("土肖", checkbox_map["土肖"]); handle_checkbox("红肖", checkbox_map["红肖"])
            c4, c5 = st.columns(2)
            with c4: handle_checkbox("蓝肖", checkbox_map["蓝肖"])
            with c5: handle_checkbox("绿肖", checkbox_map["绿肖"])

        with st.expander("🌈 波色与单双"):
            b1, b2, b3 = st.columns(3)
            with b1: handle_checkbox("红波", checkbox_map["红波"]); handle_checkbox("红波单", checkbox_map["红波单"]); handle_checkbox("红波双", checkbox_map["红波双"])
            with b2: handle_checkbox("蓝波", checkbox_map["蓝波"]); handle_checkbox("蓝波单", checkbox_map["蓝波单"]); handle_checkbox("蓝波双", checkbox_map["蓝波双"])
            with b3: handle_checkbox("绿波", checkbox_map["绿波"]); handle_checkbox("绿波单", checkbox_map["绿波单"]); handle_checkbox("绿波双", checkbox_map["绿波双"])

        with st.expander("🔢 尾数杀号"):
            t_cols = st.columns(5)
            for i in range(10):
                with t_cols[i % 5]:
                    key = f"{i}尾"
                    handle_checkbox(key, checkbox_map[key])

        with st.expander("📦 门数 / 段数"):
            d_cols = st.columns(4)
            for i in range(1, 8):
                with d_cols[(i-1) % 4]:
                    key = f"{i}段"
                    handle_checkbox(key, checkbox_map[key])
            for i in range(1, 6):
                with d_cols[(i+6) % 4]:
                    key = f"{i}门"
                    handle_checkbox(key, checkbox_map[key])

        with st.expander("🧮 合数"):
            h_cols = st.columns(4)
            for i in range(1, 14):
                with h_cols[(i-1) % 4]:
                    key = f"{i:02d}合"
                    handle_checkbox(key, checkbox_map[key])

        with st.expander("🎭 生肖专属"):
            z_cols = st.columns(4)
            zodiacs = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
            for idx, z in enumerate(zodiacs):
                with z_cols[idx % 4]:
                    key = f"杀{z}"
                    handle_checkbox(key, checkbox_map[key])

        with st.expander("✨ 五行号 / 五行尾 / 其他"):
            o_cols = st.columns(3)
            with o_cols[0]:
                handle_checkbox("金号", checkbox_map["金号"]); handle_checkbox("木号", checkbox_map["木号"]); handle_checkbox("水号", checkbox_map["水号"])
            with o_cols[1]:
                handle_checkbox("火号", checkbox_map["火号"]); handle_checkbox("土号", checkbox_map["土号"]); handle_checkbox("大肖", checkbox_map["大肖"])
            with o_cols[2]:
                handle_checkbox("中肖", checkbox_map["中肖"]); handle_checkbox("小肖", checkbox_map["小肖"]); handle_checkbox("福肖", checkbox_map["福肖"])

# ==========================================
# 5. 路由控制
# ==========================================
if not st.session_state.logged_in:
    login_page()
else:
    main_app()