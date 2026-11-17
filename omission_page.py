# -*- coding: utf-8 -*-
"""
各属性遗漏统计页面
==================
按「球位 + 属性」定位升序/按序全套 CSV 中的列，计算截至基准期各取值的遗漏期数。

列定位规则与 app.py 中 render_multi_analysis 的 ATTR_MAP 保持一致：
  - 每个球位占 30 列，第 n 球（1-based）的起始列为 4 + (n-1)*30
  - 属性偏移（1-based，相对球位起始列）：
      数字五行=6, 生肖=7, 尾数=8, 数字合=9, 门数=10, 段数=11,
      单双组合=12, 单双笔=13, 独合字=14, 单双头=15, 单双=16, 波单双=17,
      生肖五行=18, 颜色肖=19, 四宝=20, 物象=21, 波色=22, 阴阳=23,
      家野=24, 天地=25, 阴阳天地=26, 吉凶=27, 男女=28, 方位=29,
      3模=30, 尾五行=31, 福禄寿=32, 大小肖=33
  - 期号列：第 214 列（索引 213）
"""

import streamlit as st

# 属性名 -> 相对球位起始列的 1-based 偏移（与 app.py ATTR_MAP 一致）
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

# 各属性的完整取值集合（用于展示未出现过的取值）
ATTR_VALUES = {
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


def _clean_cell(v):
    """与 app.py 中 clean_str 口径一致：去空白、去 .0。"""
    if v is None:
        return ""
    try:
        return str(int(float(v)))
    except Exception:
        return str(v).replace("\r", "").replace("\n", "").replace(" ", "").strip()


def _row_period(row):
    """从一行中取期号：年份列(索引213) + A/B/C 列。"""
    year_val = _clean_cell(row[213]) if len(row) > 213 else "2026"
    p1 = _clean_cell(row[0]) if len(row) > 0 else ""
    p2 = _clean_cell(row[1]) if len(row) > 1 else ""
    p3 = _clean_cell(row[2]) if len(row) > 2 else ""
    if not p1 and not p2 and not p3:
        return ""
    return f"{year_val}{p1}{p2}{p3}"


def _attr_col_index(ball_no, attr_name):
    """返回属性列在行中的 0-based 索引。ball_no 为 1..7。"""
    offset = ATTR_OFFSET[attr_name]
    # 球位起始列（1-based）= 4 + (ball_no-1)*30；属性列（1-based）= 起始列 + offset - 1
    return 4 + (ball_no - 1) * 30 + offset - 1 - 1


def _build_period_index(all_rows):
    """返回 [(period, row_index), ...]，按 CSV 原始顺序（升序全套为最新在前）。"""
    out = []
    for idx, row in enumerate(all_rows):
        p = _row_period(row)
        if p:
            out.append((p, idx))
    return out


def _pick_base_index(period_index, selected_period):
    """
    选择基准期在 period_index 中的位置。
    - 所选期号存在：直接用该期（包含该期本身）。
    - 不存在：取小于等于它的最大期号；若都大于它，取最小期号。
    返回 (base_pos, base_period, note)。
    """
    if not period_index:
        return None, None, "CSV 中没有可用期号"

    # 精确匹配
    for pos, (p, _) in enumerate(period_index):
        if p == selected_period:
            return pos, p, ""

    # 数值比较（期号是纯数字字符串）
    try:
        target = int(selected_period)
    except Exception:
        return 0, period_index[0][0], "所选期号非数字，已回退到最新一期"

    best_pos = None
    best_val = None
    min_pos = 0
    min_val = None
    for pos, (p, _) in enumerate(period_index):
        try:
            v = int(p)
        except Exception:
            continue
        if min_val is None or v < min_val:
            min_val = v
            min_pos = pos
        if v <= target and (best_val is None or v > best_val):
            best_val = v
            best_pos = pos

    if best_pos is not None:
        return best_pos, period_index[best_pos][0], f"所选期号 {selected_period} 未开奖，已回退到 {period_index[best_pos][0]}"
    return min_pos, period_index[min_pos][0], f"所选期号 {selected_period} 早于所有期号，已回退到最早一期 {period_index[min_pos][0]}"


def _compute_omission(all_rows, period_index, base_pos, col_idx, values):
    """
    从 base_pos 开始沿 CSV 顺序（升序全套为最新在前，即向索引增大方向为更早）
    计算每个取值的连续未出现期数。
    返回 {value: omission_count}。
    """
    result = {v: 0 for v in values}
    seen = set()
    for pos in range(base_pos, len(period_index)):
        _, row_idx = period_index[pos]
        row = all_rows[row_idx]
        cell = _clean_cell(row[col_idx]) if col_idx < len(row) else ""
        if not cell:
            continue
        if cell in seen:
            continue
        if cell in result:
            result[cell] = pos - base_pos
            seen.add(cell)
        else:
            # 出现未在预置取值集合中的值，也记录一下，避免死循环
            seen.add(cell)
        if len(seen) >= len(values):
            break
    # 未出现过的取值：遗漏 = 从基准期到 CSV 末尾的期数
    total = len(period_index) - base_pos
    for v in values:
        if v not in seen:
            result[v] = total
    return result


def render_omission_page():
    st.title("📉 各属性遗漏统计")
    st.info("💡 遗漏 = 从基准期往前数，该属性值连续未出现的期数。基准期已开奖时包含该期本身（该期出现则遗漏为 0）。")

    # 延迟导入，避免与 app.py 循环依赖
    try:
        from app import load_excel_data
    except Exception as e:
        st.error(f"无法导入 load_excel_data：{e}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        source = st.selectbox("数据源", ["升序全套", "按序全套"], index=0)
    target_file = "升序全套.csv" if source == "升序全套" else "按序全套.csv"

    with st.spinner(f"正在读取 {target_file} ..."):
        all_rows = load_excel_data(target_file, None)
    if not all_rows:
        st.error(f"读取 {target_file} 失败或为空")
        return

    period_index = _build_period_index(all_rows)
    if not period_index:
        st.error("CSV 中没有解析出任何期号")
        return

    # 期号下拉：最新在前，并允许输入未开奖期号
    period_options = [p for p, _ in period_index]
    with col2:
        selected_period = st.selectbox("选择期号", period_options, index=0)
    with col3:
        ball_no = st.selectbox("选择球位", [f"第{i}球" for i in range(1, 8)], index=0)
        ball_no = int(ball_no.replace("第", "").replace("球", ""))

    attr_names = list(ATTR_OFFSET.keys())
    attr_name = st.selectbox("选择属性", attr_names, index=attr_names.index("生肖"))

    if st.button("🔍 计算遗漏次数", type="primary", use_container_width=True):
        base_pos, base_period, note = _pick_base_index(period_index, selected_period)
        if base_pos is None:
            st.error(note)
            return
        if note:
            st.warning(note)

        col_idx = _attr_col_index(ball_no, attr_name)
        values = ATTR_VALUES.get(attr_name)
        if not values:
            # 未预置取值集合的属性：从 CSV 中扫描该列所有出现过的值
            scanned = set()
            for _, row_idx in period_index:
                row = all_rows[row_idx]
                cell = _clean_cell(row[col_idx]) if col_idx < len(row) else ""
                if cell:
                    scanned.add(cell)
            values = sorted(scanned)

        omission = _compute_omission(all_rows, period_index, base_pos, col_idx, values)

        st.success(f"基准期：{base_period}｜球位：第{ball_no}球｜属性：{attr_name}｜数据源：{source}")

        # 按遗漏降序展示
        rows = sorted(omission.items(), key=lambda x: (-x[1], str(x[0])))
        st.dataframe(
            [{"取值": k, "遗漏期数": v} for k, v in rows],
            use_container_width=True,
            height=min(600, 40 + 35 * len(rows)),
        )
