import streamlit as st
import pandas as pd

# ==========================================
# 1. 核心美化：页面配置与自定义 CSS 注入
# ==========================================
st.set_page_config(page_title="智能同现分析系统", page_icon="??", layout="wide")

# 注入自定义 CSS，彻底告别默认的简陋样式
st.markdown("""
<style>
    /* 整体背景改成高级浅灰渐变 */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
    }
    /* 标题居中，加深颜色，增加阴影 */
    h1 {
        color: #1E3A8A !important;
        text-align: center;
        font-family: 'Microsoft YaHei', sans-serif;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
        padding-bottom: 20px;
    }
    h2, h3 {
        color: #374151 !important;
        font-family: 'Microsoft YaHei', sans-serif;
    }
    /* 按钮美化：渐变蓝，圆角，悬浮动画 */
    .stButton>button {
        background: linear-gradient(90deg, #3B82F6 0%, #2563EB 100%);
        color: white;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: bold;
        border: none;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(37, 99, 235, 0.4);
        color: white;
    }
    /* 输入框和下拉框美化 */
    .stSelectbox>div>div, .stNumberInput>div>div {
        border-radius: 8px;
    }
    /* 数据表格卡片化 */
    .stDataFrame {
        background: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 页面标题与说明
# ==========================================
st.title("?? 历史同现号码预测系统")
st.markdown("<p style='text-align: center; color: #6B7280;'>基于 6000+ 期历史数据的深度同频扫描</p>", unsafe_allow_html=True)
st.divider()

# ==========================================
# 3. 读取数据（使用缓存）
# ==========================================
@st.cache_data
def load_data():
    try:
        # 读取 Excel，跳过前 2 行，读取 C 到 H 列
        df = pd.read_excel("data.xlsx", sheet_name="升序纯数据表", skiprows=2, usecols="C:H")
        df = df.dropna(how='all')
        return df
    except Exception as e:
        return str(e)

data = load_data()

if isinstance(data, str):
    st.error(f"数据读取失败！请确保 data.xlsx 存在且表名正确。报错：{data}")
else:
    st.success(f"? 数据读取成功！共加载 **{len(data)}** 期历史数据。")
    
    # ==========================================
    # 4. 左右分栏布局：左边操作，右边展示
    # ==========================================
    col1, col2 = st.columns([1, 2], gap="large")
    
    # --- 左侧：控制面板 ---
    with col1:
        st.markdown("### ??? 核算控制台")
        with st.container():
            target_num = st.number_input("请输入目标号码 (1-49):", min_value=1, max_value=49, value=30)
            top_n = st.selectbox("显示同频前几名:", [3, 5, 8, 10])
            calc_btn = st.button("?? 开始深度扫描", use_container_width=True)
            
    # --- 右侧：结果展示 ---
    with col2:
        st.markdown("### ?? 扫描结果")
        result_placeholder = st.empty()
        
        if calc_btn:
            with result_placeholder.container():
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
                        
                        # 展示美化后的表格
                        st.dataframe(result_df, use_container_width=True, hide_index=True)
                        
                        # 加一个可视化的柱状图，看起来更高级
                        st.bar_chart(result_df.set_index("同频号码")["同现次数"], color="#3B82F6")
        else:
            result_placeholder.info("?? 请在左侧输入号码并点击【开始深度扫描】")