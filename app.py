import streamlit as st
import pandas as pd
import random

# ==========================================
# 1. 页面配置与高级 CSS 美化（完美复刻你的界面质感）
# ==========================================
st.set_page_config(page_title="智能分析总控台", page_icon="🧊", layout="wide")

st.markdown("""
<style>
    /* 整体背景 */
    .stApp { background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%); }
    /* 标题美化 */
    h1, h2, h3 { color: #0369a1 !important; font-family: 'Microsoft YaHei', sans-serif; }
    /* 按钮样式（模仿 VBA 里的蓝色按钮） */
    .stButton>button {
        background: linear-gradient(90deg, #0284c7 0%, #0369a1 100%);
        color: white; border-radius: 6px; border: none; transition: all 0.3s; font-weight: bold;
    }
    .stButton>button:hover { box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4); transform: translateY(-2px); }
    
    /* 完美复刻 VBA 里的 3D 彩球 */
    .ball-container { display: flex; gap: 12px; justify-content: center; margin: 20px 0; align-items: center; }
    .ball {
        width: 55px; height: 55px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px; font-weight: bold; color: white;
        box-shadow: 2px 4px 8px rgba(0,0,0,0.3);
        text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
    }
    /* 红波、蓝波、绿波、特码 的渐变颜色 */
    .ball-red { background: radial-gradient(circle at 30% 30%, #fca5a5, #dc2626); }
    .ball-blue { background: radial-gradient(circle at 30% 30%, #93c5fd, #2563eb); }
    .ball-green { background: radial-gradient(circle at 30% 30%, #86efac, #16a34a); }
    .ball-special { background: radial-gradient(circle at 30% 30%, #fde047, #ca8a04); border: 2px solid #fff; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 模拟数据（代替你的“总数据”工作表）
# ==========================================
@st.cache_data
def load_mock_data():
    # 生成模拟的期数和开奖数据
    data = []
    periods = [str(2026120 - i) for i in range(20)]
    for p in periods:
        nums = [random.randint(1, 49) for _ in range(6)]
        special = random.randint(1, 49)
        data.append({
            "期数": p,
            "平码": nums,
            "特码": special
        })
    return data

mock_data = load_mock_data()

# 辅助函数：判断波色（模仿你的 VBA 逻辑）
def get_ball_color(num):
    red = [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46]
    blue = [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48]
    if num in red: return "ball-red"
    elif num in blue: return "ball-blue"
    else: return "ball-green"

# ==========================================
# 3. 侧边栏导航（模仿你的界面跳转）
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/1055/1055666.png", width=60)
    st.title("系统导航")
    menu = st.radio("请选择功能模块：", [
        "🏠 主控制台", 
        "📊 走势图分析", 
        "🤖 AI 智能推演", 
        "📈 同现频率统计",
        "⚙️ 多维分析"
    ])
    st.divider()
    st.caption("数据状态：✅ 已加载 20 期")

# ==========================================
# 4. 页面 1：主控制台 (高仿 frmMain)
# ==========================================
if menu == "🏠 主控制台":
    st.title("🧊 智能数据分析总控台")
    
    # 顶部控制区
    col_period, col_btn = st.columns([2, 1])
    with col_period:
        periods = [d["期数"] for d in mock_data]
        selected_period = st.selectbox("🎯 请选择期数：", periods)
    
    with col_btn:
        st.write("")
        st.write("")
        if st.button("🔄 同步最新数据", use_container_width=True):
            with st.spinner("正在从云端拉取..."):
                st.success("✅ 数据同步成功！")

    # 查找当前期数的数据
    current_data = next(item for item in mock_data if item["期数"] == selected_period)
    
    # ==========================================
    # ★★★ 核心视觉：顶部开奖彩球展示 ★★★
    # ==========================================
    st.subheader(f"🎯 {selected_period} 期开奖结果")
    
    # 生成 HTML 彩球
    balls_html = '<div class="ball-container">'
    for num in current_data["平码"]:
        color_class = get_ball_color(num)
        balls_html += f'<div class="ball {color_class}">{num:02d}</div>'
    
    # 特码球
    sp_color = get_ball_color(current_data["特码"])
    balls_html += f'<div class="ball {sp_color} ball-special">★ {current_data["特码"]:02d}</div>'
    balls_html += '</div>'
    
    st.markdown(balls_html, unsafe_allow_html=True)

    st.divider()

    # 中部操作按钮区
    st.subheader("⚙️ 核心操作区")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 生成/查看走势图", use_container_width=True):
            st.info("请点击左侧菜单栏的【走势图分析】进入该功能。")
    with col2:
        if st.button("🚀 开始核心分析", use_container_width=True):
            with st.spinner("正在计算..."):
                st.success("✅ 分析执行完毕！")
    with col3:
        if st.button("📥 导出中出结果", use_container_width=True):
            st.success("导出成功！")
    with col4:
        if st.button("💾 一键保存下推", use_container_width=True):
            st.success("走势图已自动下推，所有数据已保存！")

    st.divider()

    # 底部数据展示区（模仿你的列表框）
    st.subheader("📋 实时数据镜像预览")
    
    # 构造表格数据
    df_preview = pd.DataFrame({
        "期数": [d["期数"] for d in mock_data[:10]],
        "开奖号码 (平码)": [", ".join(f"{n:02d}" for n in d["平码"]) for d in mock_data[:10]],
        "特码": [f"{d['特码']:02d}" for d in mock_data[:10]]
    })
    
    st.dataframe(df_preview, use_container_width=True, hide_index=True)

# ==========================================
# 5. 其他页面占位（后续可逐渐把 VBA 代码搬进去）
# ==========================================
elif menu == "📊 走势图分析":
    st.title("📊 历史走势图分析")
    st.info("在网页版中，原来用图片画的走势图，我们可以直接生成极其清晰的动态图表。")
    # 这里用散点图演示走势
    st.write("图表加载中...")

elif menu == "🤖 AI 智能推演":
    st.title("🤖 AI 智能推演系统")
    st.info("这里是你之前对接 DeepSeek 的 AI 界面。")

elif menu == "📈 同现频率统计":
    st.title("📈 同现频率统计")
    st.info("这里是你之前做的同现前 N 名分析界面。")

elif menu == "⚙️ 多维分析":
    st.title("⚙️ 多维分析控制台")
    st.info("这里是你的多维分析系统。")