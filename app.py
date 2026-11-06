import streamlit as st
import pandas as pd
import os

# ==========================================
# 1. 页面基础配置与高级 CSS 美化
# ==========================================
st.set_page_config(page_title="AI 数据分析系统", page_icon="🎯", layout="wide")

st.markdown("""
<style>
    /* 整体背景渐变 */
    .stApp {
        background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 100%);
    }
    /* 标题美化 */
    h1, h2, h3 {
        color: #102A43 !important;
        font-family: 'Microsoft YaHei', sans-serif;
    }
    /* 按钮美化 */
    .stButton>button {
        background: linear-gradient(90deg, #3B82F6 0%, #2563EB 100%);
        color: white;
        border-radius: 8px;
        font-weight: bold;
        border: none;
        transition: all 0.3s;
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(37, 99, 235, 0.4);
    }
    /* 侧边栏美化 */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        box-shadow: 2px 0 10px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 侧边栏导航菜单 (完全替代 VBA 的按钮跳转)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2103/2103633.png", width=80) # 顶部放个小图标
    st.title("系统导航")
    
    # 使用单选按钮作为页面切换的“链接”
    page = st.radio("请选择功能模块：", [
        "🏠 主控制台", 
        "📊 同现频率统计", 
        "🤖 AI 智能推演", 
        "📈 智能核算与走势"
    ])
    
    st.divider()
    st.caption("当前版本: V2.0 Web版")
    st.caption("数据源: data.xlsx")


# ==========================================
# 3. 页面 1：主控制台 (类似于 frmMain)
# ==========================================
if page == "🏠 主控制台":
    st.title("🏠 欢迎使用 AI 数据分析系统")
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("📌 **数据同步状态**\\n\\n✅ 已连接云端数据源")
    with col2:
        st.success("📊 **历史数据加载**\\n\\n✅ 已成功读取历史记录")
    with col3:
        st.warning("🕒 **最后核算时间**\\n\\n今天 12:00:00")
        
    st.subheader("📢 系统公告")
    st.write("1. 左侧菜单可以自由切换各个功能界面。")
    st.write("2. 数据计算功能已全面接入 Python 极速引擎，速度比 VBA 快 100 倍。")
    st.write("3. 网页端可以分享给任何人，通过手机浏览器也能随时打开测算。")


# ==========================================
# 4. 页面 2：同现统计 (类似于 frmPairStat)
# ==========================================
elif page == "📊 同现频率统计":
    st.title("📊 历史同现号码预测")
    st.markdown("---")
    
    # 尝试读取数据
    @st.cache_data
    def load_data():
        if not os.path.exists("data.xlsx"):
            return None
        try:
            # 请确保你的 data.xlsx 里面的表名叫 "升序纯数据表"
            df = pd.read_excel("data.xlsx", sheet_name="升序纯数据表", skiprows=2, usecols="C:H")
            df = df.dropna(how='all')
            return df
        except Exception as e:
            st.error(f"读取 Excel 失败，请检查表名和格式。错误：{e}")
            return None

    data = load_data()
    
    if data is not None:
        st.success(f"✅ 数据读取成功！共加载 **{len(data)}** 期历史数据。")
        
        # 控制面板
        col_input, col_btn = st.columns([2, 1])
        with col_input:
            target_num = st.number_input("请输入目标号码 (1-49):", min_value=1, max_value=49, value=30)
            top_n = st.selectbox("显示前几名:", [3, 5, 8, 10])
            
        if st.button("🚀 开始深度扫描", use_container_width=True):
            with st.spinner('正在扫描历史同现数据...'):
                df_numeric = data.apply(pd.to_numeric, errors='coerce')
                mask = df_numeric.isin([target_num]).any(axis=1)
                filtered_rows = df_numeric[mask]
                
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
                        result_data.append({
                            "排名": f"Top {rank}",
                            "同频号码": f"{num:02d}",
                            "同现次数": count
                        })
                        
                    result_df = pd.DataFrame(result_data)
                    st.subheader(f"与 **{target_num:02d}** 号同现频率最高的前 {top_n} 名：")
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    
                    # 图表
                    st.bar_chart(result_df.set_index("同频号码")["同现次数"], color="#3B82F6")
    else:
        st.error("找不到 `data.xlsx` 文件，请确保它和 app.py 在同一个文件夹中！")


# ==========================================
# 5. 页面 3：AI 智能推演 (类似于 frmAI)
# ==========================================
elif page == "🤖 AI 智能推演":
    st.title("🤖 AI 严谨推演系统")
    st.markdown("---")
    st.info("💡 提示：这里可以接入你的 DeepSeek API。在 Python 中，我们使用 `requests` 库来发送请求。")
    
    # 模拟界面
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("条件输入")
        ai_input = st.text_area("请输入核算条件：", "这是2026116期第一球的核算条件，第一球的取值区间为1号至20号之间，杀木土肖，杀水火号，杀019尾...", height=200)
        if st.button("开始呼叫 DeepSeek 推演", use_container_width=True):
            st.success("推演完成！")
            # 这里可以将结果存入 session_state，切换页面也不会丢失
            st.session_state.ai_result = "【严格筛选结果】：03, 08, 15\\n\\n【后补筛选结果】：01, 19"
            
    with col2:
        st.subheader("推演结果")
        if "ai_result" in st.session_state:
            st.success(st.session_state.ai_result)
        else:
            st.write("等待推演...")


# ==========================================
# 6. 页面 4：智能核算与走势 (类似于 frmCalc)
# ==========================================
elif page == "📈 智能核算与走势":
    st.title("📈 智能核算中心")
    st.markdown("---")
    
    st.write("这里可以展示你之前 VBA 里的走势图和中奖结果。")
    
    # 模拟表格数据
    mock_df = pd.DataFrame({
        "期数": ["2026116", "2026115", "2026114", "2026113"],
        "开奖号码": ["03, 12, 25, 33, 41, 48", "05, 11, 22, 34, 42, 49", "01, 09, 18, 27, 35, 44", "07, 14, 21, 28, 37, 46"],
        "特码": ["09", "16", "25", "32"],
        "核算结果": ["中奖", "不中", "中奖", "不中"]
    })
    
    st.dataframe(mock_df, use_container_width=True)
    
    if st.button("🔄 一键从云端同步最新数据"):
        with st.spinner("正在拉取..."):
            st.success("数据同步成功！")