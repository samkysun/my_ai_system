import streamlit as st

import pandas as pd

# 强制指定网页使用微软雅黑字体，彻底封杀乱码
st.markdown(
    """
    <style>
    * {
        font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ... 下面的代码保持你原有的不变 ...
import pandas as pd

# 1. 网页基础设置（去掉了表情符号）
st.set_page_config(page_title="同现核算系统", layout="wide")
st.title("历史同现号码预测系统")
st.divider()

# 2. 读取 Excel 数据的函数
@st.cache_data
def load_data():
    try:
        df = pd.read_excel("data.xlsx", sheet_name="升序纯数据表", skiprows=2, usecols="C:H")
        df = df.dropna(how='all')
        return df
    except FileNotFoundError:
        return "找不到文件"
    except Exception as e:
        return str(e)

data = load_data()

# 3. 判断数据是否读取成功
if isinstance(data, str):
    st.error(f"数据读取失败！请确保桌面有 data.xlsx 文件，且表名正确。错误：{data}")
else:
    st.success(f"数据读取成功！共加载 {len(data)} 期历史数据。")
    
    # 4. 左侧控制面板
    with st.sidebar:
        st.header("核算控制台")
        target_num = st.number_input("请输入目标号码 (1-49):", min_value=1, max_value=49, value=30)
        top_n = st.selectbox("显示前几名:", [3, 5, 8, 10])
        calc_btn = st.button("开始同现扫描", use_container_width=True)

    # 5. 核心核算逻辑
    if calc_btn:
        with st.spinner('正在进行深度扫描比对...'):
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
                        "排名": rank,
                        "同频号码": f"{num:02d}",
                        "同现次数": count
                    })
                
                st.subheader(f"与 {target_num:02d} 号同现频率最高的前 {top_n} 名：")
                st.dataframe(result_data, use_container_width=True)