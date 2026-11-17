# -*- coding: utf-8 -*-
"""
遗漏统计页面
============
按球位 + 属性，统计升序/按序全套 CSV 中各属性值截至所选期数的遗漏期数。

列偏移规则（与 app.py 的 ATTR_MAP 一致）：
  属性列 = 6 + (球位-1)*30 + 属性偏移
其中属性偏移见 ATTR_OFFSET。
"""

import streamlit as st
import pandas as pd
from openpyxl.utils import get_column_letter, column_index_from_string

# 复用 app.py 的读取与清洗函数（同目录）
try:
    from app import load_excel_data, clean_period
except Exception:
    load_excel_data = None
    clean_period = None


# 属性名 -> 相对球位基列的偏移（与 app.py ATTR_MAP 保持一致）
ATTR_OFFSET = {
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

# 每个属性的全部可能取值（用于展示“从未出现”的项）
ATTR_VALUES = {
    "数字五行": ["金", "木", "水", "火", "土"],
    "生肖": ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"],
    "尾数": [str(i) for i in range(10)],
    "数字合": [f"{i:02d}合" for i in range(1, 14)],
    "门数": [f"{i}门" for i in range(1, 6)],
    "段数": [f"{i}段" for i in range(1, 8)],
    "单双组合": ["双双", "双单", "单单", "单双"],
    "单双笔": ["单笔", "双笔"],
    "独合字": ["独字", "合字"],
    "单双头": ["单头", "双头"],
    "单双": ["单数", "双数"],
    "波单双": [f"{b}{s}" for b in ["红波", "蓝波", "绿波"] for s in ["单数", "双数"]],
    "生肖五行": ["金", "木", "水", "火", "土"],
    "颜色肖": ["红色", "绿色", "蓝色"],
    "四宝": ["琴", "棋", "书", "画"],
    "物象": ["家臣", "美女", "君王", "恶人"],
    "波色": ["红波", "蓝波", "绿波"],
    "阴阳": ["阴", "阳"],
    "家野": ["家", "野"],
    "天地": ["天", "地"],
    "阴阳天地": ["阳天", "阳地", "阴天", "阴地"],
    "吉凶": ["吉", "凶"],
    "男女": ["男", "女"],
    "方位": ["东", "南", "西", "北"],
    "3模": ["3余0", "3余1", "3余2"],
    "尾五行": ["金", "木", "水", "火", "土"],
    "福禄寿": ["福肖", "禄肖", "寿肖"],
    "大小肖": ["大肖", "中肖", "小肖"],
}


def _clean_cell(v):
    if v is None:
        return ""
    try:
        return str(int(float(v)))
    except Exception:
        return str(v).replace("\r", "").replace("\n", "").replace(" ", "").strip()


def _row_period(row):
    """从一行 CSV 数据拼出期数：年份(第214列, 索引213) + A/B/C 列。"""
    year_val = _clean_cell(row[213]) if len(row) > 213 else "2026"
    p1 = _clean_cell(row[0]) if len(row) > 0 else ""
    p2 = _clean_cell(row[1]) if len(row) > 1 else ""
    p3 = _clean_cell(row[2]) if len(row) > 2 else ""
    if not (p1 or p2 or p3):
        return ""
    return f"{year_val}{p1}{p2}{p3}"


def _load_rows(file_type):
    """读取升序/按序全套 CSV，返回 (rows, 错误信息)。"""
    if load_excel_data is None:
        return None, "无法导入 app.load_excel_data，请确认 omission_page.py 与 app.py 同目录。"
    target_file = "升序全套.csv" if file_type == "升序全套" else "按序全套.csv"
    try:
        rows = load_excel_data(target_file, None)
    except Exception as e:
        return None, f"读取 {target_file} 失败：{e}"
    if not rows:
        return None, f"{target_file} 为空或读取失败。"
    return rows, None


def _build_period_index(rows):
    """返回 [(期数, 行索引)]，按 CSV 原始顺序（升序文件为最新在前）。"""
    out = []
    for idx, row in enumerate(rows):
        p = _row_period(row)
        if p:
            out.append((p, idx))
    return out


def _compute_omission(rows, period_index, target_period, ball_no, attr_name):
    """
    计算某球位某属性各取值的遗漏期数。
    返回 (DataFrame, 实际统计终点期数, 错误信息)。
    遗漏期数 = 从统计终点往前数，到该属性值最近一次出现所跨过的期数（0 表示终点期就是该值）。
    """
    offset = ATTR_OFFSET.get(attr_name)
    if offset is None:
        return None, None, f"未知属性：{attr_name}"
    col_idx = 6 + (ball_no - 1) * 30 + offset  # 0-based

    # 找到统计终点：CSV 中 <= target_period 的最新一期
    # 期数是数字串，直接字符串比较即可（同长度）
    candidates = [(p, i) for (p, i) in period_index if p <= target_period]
    if not candidates:
        return None, None, f"CSV 中没有 <= {target_period} 的数据。"
    # 取期数最大的那一行
    end_period, end_row_idx = max(candidates, key=lambda x: x[0])

    # 从终点行往前（CSV 顺序）遍历，记录每个属性值最近一次出现的“距离”
    # 升序文件：索引越小越新；按序文件：索引越大越新。用期数比较更稳妥。
    # 这里统一按“期数从大到小”排序后遍历。
    ordered = sorted(period_index, key=lambda x: x[0], reverse=True)
    ordered = [(p, i) for (p, i) in ordered if p <= end_period]

    last_seen = {}  # 属性值 -> 距离终点多少期（0 表示终点期）
    for dist, (p, i) in enumerate(ordered):
        row = rows[i]
        val = _clean_cell(row[col_idx]) if col_idx < len(row) else ""
        if not val:
            continue
        if val not in last_seen:
            last_seen[val] = dist

    # 组装结果：优先用预定义取值列表，再补上 CSV 中出现的其他值
    known = list(ATTR_VALUES.get(attr_name, []))
    extra = [v for v in last_seen.keys() if v not in known]
    all_vals = known + sorted(extra)

    records = []
    for v in all_vals:
        if v in last_seen:
            records.append({"属性值": v, "遗漏期数": last_seen[v]})
        else:
            records.append({"属性值": v, "遗漏期数": "从未出现"})

    df = pd.DataFrame(records)
    # 排序：数字型遗漏期数升序，字符串（从未出现）放最后
    def _sort_key(x):
        return (1, 0) if isinstance(x, str) else (0, x)
    df["_k"] = df["遗漏期数"].apply(_sort_key)
    df = df.sort_values("_k").drop(columns=["_k"]).reset_index(drop=True)
    return df, end_period, None


def render_omission_page():
    st.title("📉 遗漏统计")
    st.info("💡 选择文件、期数、球位与属性，统计各属性值截至该期数的遗漏期数（0 表示该期就是此值）。")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        file_type = st.selectbox("数据文件", ["升序全套", "按序全套"])
    with col2:
        ball_str = st.selectbox("球位", [f"第{i}球" for i in range(1, 8)])
        ball_no = int(ball_str.replace("第", "").split("球")[0])
    with col3:
        attr_name = st.selectbox("属性", list(ATTR_OFFSET.keys()))
    with col4:
        st.write("")
        st.write("")
        run_btn = st.button("🔍 计算遗漏次数", use_container_width=True, type="primary")

    rows, err = _load_rows(file_type)
    if err:
        st.error(err)
        return

    period_index = _build_period_index(rows)
    if not period_index:
        st.error("CSV 中没有解析出任何期数。")
        return

    # 期数下拉：CSV 中已有的期数 + 一个“下一期”（最新期+1）
    periods = sorted({p for p, _ in period_index}, reverse=True)
    latest = periods[0]
    try:
        next_p = str(int(latest) + 1)
    except Exception:
        next_p = latest
    period_options = [next_p] + periods if next_p not in periods else periods

    selected_period = st.selectbox("统计截至期数", period_options, index=0)

    if run_btn:
        df, end_period, err2 = _compute_omission(rows, period_index, selected_period, ball_no, attr_name)
        if err2:
            st.error(err2)
            return
        if end_period != selected_period:
            st.warning(f"⚠️ CSV 中不存在 {selected_period} 期，已自动以最新一期 {end_period} 作为统计终点。")
        else:
            st.success(f"✅ 统计终点：{end_period} 期 | {ball_str} | {attr_name}")

        st.dataframe(df, use_container_width=True, height=min(600, 40 + 35 * len(df)))

        # 简单柱状图（仅当遗漏期数全为数字时）
        numeric_df = df[df["遗漏期数"].apply(lambda x: isinstance(x, int))]
        if not numeric_df.empty:
            st.bar_chart(numeric_df.set_index("属性值")["遗漏期数"])
