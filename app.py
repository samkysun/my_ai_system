import streamlit as st
import pandas as pd
import hashlib, time, os, itertools, requests, json, re
from collections import Counter

EXCEL_FILE = "数据分析系统最终版本（智能全套）.xlsm" 
SHEET_NAME = "总数据" 
USER_FILE = "users.csv"
DEEPSEEK_API_KEY = "sk-03230269b092411eb4db85a4ea906dd3" # ★★★ 请务必换成你自己的Key ★★★

st.set_page_config(page_title="智能系统", layout="wide")
st.markdown("<style>.stApp{background:linear-gradient(135deg,#f0f4f8 0%,#d9e2ec 100%)}h1,h2,h3{color:#102A43!important}.stButton>button{background:linear-gradient(90deg,#0284c7 0%,#0369a1 100%);color:white;border-radius:6px;border:none;font-weight:bold}.ball-container{display:flex;gap:12px;justify-content:center;margin:20px 0}.ball{width:55px;height:55px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:bold;color:white;box-shadow:2px 4px 8px rgba(0,0,0,0.3)}.ball-red{background:radial-gradient(circle at 30% 30%,#fca5a5,#dc2626)}.ball-blue{background:radial-gradient(circle at 30% 30%,#93c5fd,#2563eb)}.ball-green{background:radial-gradient(circle at 30% 30%,#86efac,#16a34a)}.ball-special{background:radial-gradient(circle at 30% 30%,#fde047,#ca8a04);border:2px solid #fff}</style>", unsafe_allow_html=True)

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
    if not os.path.exists(USER_FILE): pd.DataFrame(columns=['username', 'password']).to_csv(USER_FILE, index=False)
    return pd.read_csv(USER_FILE)

def get_ball_color(num):
    if num in [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46]: return "ball-red"
    elif num in [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48]: return "ball-blue"
    else: return "ball-green"

def clean_period(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    return s[:-2] if s.endswith(".0") else s

@st.cache_data
def load_real_data():
    if not os.path.exists(EXCEL_FILE): return None
    try: return pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME).dropna(how='all')
    except Exception as e: return str(e)
def calculate_linkage(df, target, mode):
    df['_t'] = df.iloc[:, 18].apply(clean_period)
    matched = df[df['_t'] == target]
    if matched.empty: return None, None, "未找到数据"
    base_idx = matched.index[0]
    base_nums = [int(clean_period(matched.iloc[0, i])) for i in range(19, 25) if pd.notna(matched.iloc[0, i]) and clean_period(matched.iloc[0, i]) != ""]
    special_num = int(clean_period(matched.iloc[0, 25])) if pd.notna(matched.iloc[0, 25]) else 0
    if len(base_nums) < 6: return None, None, "开奖号码不足6个"
    
    # ★ 多套组合核心：生成7套号码
    sets_of_6 = []
    if mode == "多排分析" and special_num > 0:
        sets_of_6.append(base_nums)
        for i in range(6):
            new_nums = base_nums.copy()
            new_nums[i] = special_num
            sets_of_6.append(new_nums)
    else:
        sets_of_6 = [base_nums]

    try: is_desc = int(clean_period(df.iloc[0, 18])) > int(clean_period(df.iloc[1, 18]))
    except: is_desc = True
    start, end = (base_idx + 1, len(df) - 1) if is_desc else (0, base_idx - 1)
    
    triggers = []
    total_counter = Counter()
    
    for set_idx, six_nums in enumerate(sets_of_6):
        combos = [",".join([str(x).zfill(2) for x in c]) for c in itertools.combinations(six_nums, 3)]
        for idx in range(start, end + 1):
            row_nums = [int(clean_period(df.iloc[idx, j])) for j in range(19, 26) if pd.notna(df.iloc[idx, j]) and clean_period(df.iloc[idx, j]) != ""]
            for c_str in combos:
                if all(int(x) in row_nums for x in c_str.split(",")):
                    triggers.append({"套数": set_idx+1, "组合": c_str, "触发期数": clean_period(df.iloc[idx, 18])})
                    n_idx = idx - 1 if is_desc else idx + 1
                    if 0 <= n_idx < len(df): 
                        next_nums = [int(clean_period(df.iloc[n_idx, j])) for j in range(19, 26) if pd.notna(df.iloc[n_idx, j]) and clean_period(df.iloc[n_idx, j]) != ""]
                        for n in next_nums: total_counter[n] += 1

    df_t = pd.DataFrame(triggers) if triggers else pd.DataFrame(columns=["套数", "组合", "触发期数"])
    df_c = pd.DataFrame([{"下期数字": f"{n:02d}", "出现次数": c} for n, c in sorted(total_counter.items(), key=lambda x: x[1], reverse=True)])
    return df_t, df_c, None

def calculate_prize(df, target, pred_nums):
    df['_t'] = df.iloc[:, 18].apply(clean_period)
    matched = df[df['_t'] == target]
    if matched.empty: return None
    base_idx = matched.index[0]
    try: is_desc = int(clean_period(df.iloc[0, 18])) > int(clean_period(df.iloc[1, 18]))
    except: is_desc = True
    n_idx = base_idx - 1 if is_desc else base_idx + 1
    if n_idx < 0 or n_idx >= len(df): return None
    next_row = df.iloc[n_idx]
    next_nums = [clean_period(next_row.iloc[i]) for i in range(19, 25) if clean_period(next_row.iloc[i]) != ""]
    next_sp = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    m_flat = [n for n in next_nums if n in pred_nums]
    res = {"下期期数": clean_period(next_row.iloc[18]), "预测组合": ",".join(pred_nums), "中出平码1": m_flat[0] if len(m_flat) > 0 else "", "中出平码2": m_flat[1] if len(m_flat) > 1 else "", "中出平码3": m_flat[2] if len(m_flat) > 2 else "", "中出平码4": m_flat[3] if len(m_flat) > 3 else "", "中出平码5": m_flat[4] if len(m_flat) > 4 else "", "中出平码6": m_flat[5] if len(m_flat) > 5 else "", "中出特码": next_sp if next_sp in pred_nums else "", "状态": "有命中" if (len(m_flat) > 0 or next_sp in pred_nums) else "无中"}
    return res
def login_page():
    st.title("系统登录")
    t1, t2 = st.tabs(["登录", "注册"])
    with t1:
        u, p = st.text_input("用户名"), st.text_input("密码", type="password")
        if st.button("登录", use_container_width=True):
            users = load_users()
            if not users[(users['username'] == u) & (users['password'] == hashlib.sha256(p.encode()).hexdigest())].empty:
                st.session_state.logged_in, st.session_state.username = True, u
                st.rerun()
            else: st.error("错误")
    with t2:
        ru, rp, rc = st.text_input("设置用户名"), st.text_input("设置密码", type="password"), st.text_input("确认密码", type="password")
        if st.button("注册", use_container_width=True):
            if rp != rc: st.error("不一致")
            else:
                users = load_users()
                if ru in users['username'].values: st.error("已注册")
                else:
                    pd.concat([users, pd.DataFrame({'username': [ru], 'password': [hashlib.sha256(rp.encode()).hexdigest()]})]).to_csv(USER_FILE, index=False)
                    st.success("成功")

def render_console(df):
    st.title("智能数据分析总控台")
    if df is None or isinstance(df, str): st.error("读取失败"); return
    periods = sorted(list(set([p for p in df.iloc[:, 18].apply(clean_period).tolist() if p != ""])), key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    
    c1, c2 = st.columns(2)
    with c1: target = st.selectbox("选择期数：", periods)
    with c2: mode = st.radio("模式：", ["单排分析", "多排分析"], horizontal=True)
    
    st.markdown("### 操作面板")
    b1, b2, b3, b4, b5 = st.columns(5)
    start_b = b1.button("开始分析", use_container_width=True, type="primary")
    res_b = b2.button("中奖结果", use_container_width=True)
    clear_b = b3.button("清空数据", use_container_width=True)
    sync_b = b4.button("同步数据", use_container_width=True)
    trend_b = b5.button("走势图", use_container_width=True)
    
    st.divider()
    flat, sp = [], 0
    df['_t'] = df.iloc[:, 18].apply(clean_period)
    mr = df[df['_t'] == target]
    if not mr.empty:
        try: flat, sp = [int(clean_period(mr.iloc[0, i])) for i in range(19, 25) if pd.notna(mr.iloc[0, i])], (int(clean_period(mr.iloc[0, 25])) if pd.notna(mr.iloc[0, 25]) else 0)
        except: pass
        st.markdown(f'<div class="ball-container">{"".join([f"<div class=\\'ball {get_ball_color(n)}\\'>{n:02d}</div>" for n in flat])}<div class="ball {get_ball_color(sp)} ball-special">★ {sp:02d}</div></div>', unsafe_allow_html=True)
        
    if clear_b:
        st.session_state.calc_data_single, st.session_state.calc_data_multi, st.session_state.calc_result_preview = None, None, None
        st.success("已清空")
    if start_b:
        with st.spinner("计算中..."):
            df_t, df_c, err = calculate_linkage(df, target, mode)
            if not err:
                preds = df_c.head(7)["下期数字"].tolist()
                if mode == "单排分析": st.session_state.calc_data_single, st.session_state.predicted_nums_single = (df_t, df_c), preds
                else: st.session_state.calc_data_multi, st.session_state.predicted_nums_multi = (df_t.head(200), df_c), preds
                st.success("完成")
            else: st.error(err)
    if res_b:
        preds = st.session_state.predicted_nums_single if mode == "单排分析" else st.session_state.predicted_nums_multi
        if not preds: st.warning("请先分析")
        else:
            res = calculate_prize(df, target, preds)
            if res: st.session_state.calc_result_preview = pd.DataFrame([res]); st.success("中奖结果已出")
            
    st.divider()
    c_l, c_r = st.columns(2)
    with c_l:
        st.subheader("单排结果列表")
        if st.session_state.calc_data_single:
            st.dataframe(st.session_state.calc_data_single[0], use_container_width=True)
            st.dataframe(st.session_state.calc_data_single[1], use_container_width=True)
        else: st.info("暂无")
    with c_r:
        st.subheader("多排结果列表 (七套汇总)")
        if st.session_state.calc_data_multi:
            st.dataframe(st.session_state.calc_data_multi[0], use_container_width=True)
            st.dataframe(st.session_state.calc_data_multi[1], use_container_width=True)
        else: st.info("暂无")
    st.divider()
    st.subheader("中出结果预览")
    if st.session_state.calc_result_preview is not None: st.dataframe(st.session_state.calc_result_preview, use_container_width=True)
    else: st.info("暂无")
def render_ai():
    st.title("AI 智能推演")
    c1, c2, c3, c4 = st.columns(4)
    with c1: asc = st.checkbox("升序", value=True)
    with c2: desc = st.checkbox("按序", value=False)
    with c3: per = st.selectbox("期数", ["2026117", "2026116"])
    with c4: ball = st.selectbox("球号", [f"第{i}球" for i in range(1, 8)])
    
    mode = "升序" if asc else "按序"
    interval = f"{ball}的区间为1-49之间，" if mode == "按序" else "第一球区间为1-20之间，"
    prefix = f"这是{per}期{mode}{ball}的核算条件，{interval}"
    if "ai_input_text" not in st.session_state: st.session_state.ai_input_text = prefix
    if prefix not in st.session_state.ai_input_text: st.session_state.ai_input_text = prefix + re.sub(r'^这是.*?之间，', '', st.session_state.ai_input_text)
    
    c_mat, c_btn = st.columns([3, 1.5])
    
    with c_mat:
        items = ["鼠","金肖","红肖","金号","东肖","1段","1门", "牛","木肖","蓝肖","木号","南肖","2段","2门", "虎","水肖","绿肖","水号","西肖","3段","3门", "兔","火肖","阴天","火号","北肖","4段","4门", "龙","土肖","阳天","土号","1门","5段","5门", "蛇","君王","阳地","红波","2门","6段","0合", "马","美女","阴地","蓝波","3门","7段","1合", "羊","家臣","金尾","绿波","4门","8段","2合", "猴","恶人","木尾","大肖","5门","9段","3合", "鸡","福肖","水尾","中肖","0尾","10段","4合", "狗","禄肖","火尾","小肖","1尾","11段","5合", "猪","寿肖","土尾","红波单","2尾","12段","6合"]
        # ✅ 修复后的代码
for i in range(...):
    for j in range(...):
        # 将原来的 key 替换成这样，确保每个 checkbox 的 key 绝对唯一
        key = f"checkbox_{i}_{j}" 
        st.checkbox(items[i+j], key=key)
                        
    with c_btn:
        st.markdown("### 操作")
        if st.button("开始推算", use_container_width=True, type="primary"):
            q = st.session_state.ai_input_text + f"请分析{ball}剩余什么生肖与号码，后补取触犯次数最少的。输出严格结果和后补结果。禁止复述属性表。"
            try:
                res = requests.post("https://api.deepseek.com/v1/chat/completions", headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, json={"model": "deepseek-chat", "messages": [{"role": "user", "content": q}], "stream": True}, stream=True)
                full = "".join([json.loads(l.decode('utf-8')[6:])["choices"][0]["delta"].get("content", "") for l in res.iter_lines() if l and l.decode('utf-8').startswith("data: ") and l.decode('utf-8') != "data: [DONE]"])
                st.session_state.ai_result_text = full; st.rerun()
            except Exception as e: st.error(f"失败: {e}")
        if st.button("导出结果", use_container_width=True):
            if st.session_state.ai_result_text and st.session_state.ai_result_text != "等待推演...": st.download_button("点击下载TXT", st.session_state.ai_result_text, "result.txt")
        if st.button("删除结果", use_container_width=True, type="secondary"):
            st.session_state.ai_result_text = "等待推演..."; st.session_state.ai_input_text = prefix
            for k in list(st.session_state.keys()):
                if k.startswith("chk_"): st.session_state[k] = False
            st.rerun()
        if st.button("停止语音", use_container_width=True): pass
        if st.button("打开数据", use_container_width=True): pass
        if st.button("六合合一", use_container_width=True): pass
        if st.button("多维分析", use_container_width=True): pass
        if st.button("返回主页", use_container_width=True): pass
    
    st.divider()
    texts = [k.replace("chk_", "") for k, v in st.session_state.items() if k.startswith("chk_") and v]
    if texts:
        txt = " ".join(texts) + "，"
        if txt not in st.session_state.ai_input_text: st.session_state.ai_input_text += txt
    st.text_area("条件：", value=st.session_state.ai_input_text, height=100)
    st.text_area("结果：", value=st.session_state.ai_result_text, height=300, disabled=True)

def main_app():
    with st.sidebar:
        st.write(f"用户: {st.session_state.username}")
        if st.button("退出", use_container_width=True): st.session_state.logged_in = False; st.rerun()
        menu = st.radio("导航：", ["主控制台", "AI推演"])
    df = load_real_data()
    if menu == "主控制台": render_console(df)
    elif menu == "AI推演": render_ai()

if not st.session_state.logged_in: login_page()
else: main_app()