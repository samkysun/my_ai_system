# -*- coding: utf-8 -*-
"""
遗漏核算页
==========
按【升序全套.csv / 按序全套.csv】统计各球位各属性的遗漏期数。

列规则（与 app.py 的 ATTR_MAP 一致，CSV 为 0 基索引）：
  每球占 30 列，第 n 球（n=1..7）的属性基列 = 属性基列 + (n-1)*30
  属性基列（1 基，来自 app.py ATTR_MAP）：
    数字五行 6 / 生肖 7 / 尾数 8 / 数字合 9 / 门数 10 / 段数 11 /
    单双组合 12 / 单双笔 13 / 独合字 14 / 单双头 15 / 单双 16 /
    波单双 17 / 生肖五行 18 / 颜色肖 19 / 四宝 20 / 物象 21 /
    波色 22 / 阴阳 23 / 家野 24 / 天地 25 / 阴阳天地 26 /
    吉凶 27 / 男女 28 / 方位 29 / 3模 30 / 尾五行 31 /
    福禄寿 32 / 大小肖 33

数据为降序：最新一期在最上面（第 3 行，索引 2）。
遗漏 = 从最新一期向下逐行扫描，遇到该属性值即停止，计为遗漏期数。
"""

import streamlit as st
import pandas as pd

from app import load_excel_data


# 属性名 -> 1 基列号（第 1 球的基列）
ATTR_BASE_COL = {
    "数字五行": 6,
    "生肖": 7,
    "尾数": 8,
    "数字合": 9,
    "门数": 10,
    "段数": 11,
    "单双组合": 12,
    "单双笔": 13,
    "独合字": 14,
    "单双头": 15,
    "单双": 16,
    "波单双": 17,
    "生肖五行": 18,
    "颜色肖": 19,
    "四宝": 20,
    "物象": 21,
    "波色": 22,
    "阴阳": 23,
    "家野": 24,
    "天地": 25,
    "阴阳天地": 26,
    "吉凶": 27,
    "男女": 28,
    "方位": 29,
    "3模": 30,
    "尾五行": 31,
    "福禄寿": 32,
    "大小肖": 33,
}

# 各属性的完整取值域（用于展示“未出现”的属性）
ATTR_DOMAIN = {
    "生肖": ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"],
    "尾数": [str(i) for i in range(10)],
    "数字五行": ["金", "木", "水", "火", "土"],
    "生肖五行": ["金", "木", "水", "火", "土"],
    "尾五行": ["金", "木", "水", "火", "土"],
    "波色": ["红波", "蓝波", "绿波"],
    "门数": [f"{i}门" for i in range(1, 6)],
    "段数": [f"{i}段" for i in range(1, 8)],
    "数字合": [f"{i:02d}合" for i in range(1, 14)],
    "单双组合": ["双双", "双单", "单单", "单双"],
    "单双": ["单数", "双数"],
    "单双笔": ["单笔", "双笔"],
    "独合字": ["独字", "合字"],
    "单双头": ["单头", "双头"],
    "阴阳": ["阴", "阳"],
    "家野": ["家", "野"],
    "天地": ["天", "地"],
    "阴阳天地": ["阳天", "阳地", "阴天", "阴地"],
    "吉凶": ["吉", "凶"],
    "男女": ["男", "女"],
    "方位": ["东", "南", "西", "北"],
    "3模": ["3余0", "3余1", "3余2"],
    "福禄寿": ["福肖", "禄肖", "寿肖"],
    "大小肖": ["大肖", "中肖", "小肖"],
    "四宝": ["琴", "棋", "书", "画"],
    "物象": ["家臣", "美女", "君王", "恶人"],
    "颜色肖": ["红色", "绿色", "蓝色"],
}


def _clean(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _attr_col_index(attr_name, ball_no):
    """返回 CSV 中该球该属性的 0 基列索引。"""
    base_1based = ATTR_BASE_COL[attr_name]
    return base_1based + (ball_no - 1) * 30 - 1


def _compute_omission(rows, col_idx, domain):
    """从索引 2（第 3 行，最新一期）向下扫描，统计每个属性值的遗漏期数。"""
    # 收集该列从最新到最旧的值序列
    seq = []
    for r in range(2, len(rows)):
        row = rows[r]
        if col_idx >= len(row):
            continue
        val = _clean(row[col_idx])
        if val == "":
            continue
        seq.append(val)

    total = len(seq)
    result = {}
    for attr_val in domain:
        miss = total  # 默认全表未出现
        for i, v in enumerate(seq):
            if v == attr_val:
                miss = i
                break
        result[attr_val] = miss

    # 补上域外出现的值（防止属性表与数据不一致时漏项）
    for v in seq:
        if v not in result:
            miss = total
            for i, x in enumerate(seq):
                if x == v:
                    miss = i
                    break
            result[v] = miss

    return result, total


def render_omission_page():
    st.title("📉 遗漏核算")
    st.info("💡 基准期为最新一期（降序文件最上面一行）。遗漏 = 从最新一期向下连续未出现的期数。")

    col1, col2, col3 = st.columns(3)
    with col1:
        file_type = st.selectbox("选择数据文件", ["升序全套", "按序全套"])
    with col2:
        ball_str = st.selectbox("选择球号", [f"第{i}球" for i in range(1, 8)])
    with col3:
        attr_name = st.selectbox("选择属性", list(ATTR_BASE_COL.keys()))

    ball_no = int(ball_str.replace("第", "").replace("球", ""))

    st.write("")
    run_btn = st.button("🚀 开始遗漏核算", use_container_width=True, type="primary")

    if not run_btn:
        return

    target_file = "升序全套.csv" if file_type == "升序全套" else "按序全套.csv"
    with st.spinner(f"正在读取 {target_file} 并核算…"):
        try:
            rows = load_excel_data(target_file, None)
        except Exception as e:
            st.error(f"读取失败：{e}")
            return

    if not rows:
        st.error(f"{target_file} 读取为空，请检查云端文件是否存在。")
        return

    col_idx = _attr_col_index(attr_name, ball_no)
    domain = ATTR_DOMAIN.get(attr_name, [])

    # 若未定义域，则从数据中自动收集
    if not domain:
        seen = []
        for r in range(2, len(rows)):
            row = rows[r]
            if col_idx < len(row):
                v = _clean(row[col_idx])
                if v and v not in seen:
                    seen.append(v)
        domain = seen

    result, total = _compute_omission(rows, col_idx, domain)

    if total == 0:
        st.warning("该列没有有效数据，请确认属性列映射是否正确。")
        return

    # 展示
    st.subheader(f"{file_type} · {ball_str} · {attr_name} 遗漏统计")
    st.caption(f"有效期数：{total} 期（从最新一期向下）")

    df = pd.DataFrame(
        [{"属性值": k, "遗漏期数": v} for k, v in result.items()]
    ).sort_values("遗漏期数", ascending=False).reset_index(drop=True)

    st.dataframe(df, use_container_width=True, height=min(600, 40 + 35 * len(df)))

    # 高亮遗漏最大的几项
    if not df.empty:
        top = df.iloc[0]
        st.success(f"🔥 当前遗漏最大：**{top['属性值']}**，已遗漏 **{top['遗漏期数']}** 期")


if __name__ == "__main__":
    render_omission_page()
