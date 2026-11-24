# -*- coding: utf-8 -*-
"""8 码复式（三中三）页"""
from itertools import combinations

import pandas as pd
import streamlit as st

PAYOUT = 600.0     # 三中三赔率（含本金）


def _load_data(loader):
    try:
        rows = loader["load_excel_data"]("_index.csv", None)
    except Exception:
        return []
    out = []
    for r in list(rows)[1:]:
        if not r or len(r) < 8:
            continue
        try:
            nums = [int(float(r[1 + k] or 0)) for k in range(7)]
        except Exception:
            continue
        if all(n > 0 for n in nums):
            out.append((str(r[0]).strip(), nums))
    out.sort(key=lambda x: x[0])
    return out


def render(df_data, loader):
    st.markdown("## 🎯 8 码复式（三中三）")
    st.caption(f"8 个号 → C(8,3)=56 组；每注 1 单位，"
               f"命中一组按 {int(PAYOUT)} 倍计。")

    data = _load_data(loader)
    if not data:
        st.error("读取不到 _index.csv")
        return
    periods = [p for p, _ in data]
    pmap = dict(data)

    st.markdown("### ① 选号")
    _mode = st.radio("选号方式", ["手动输入", "系统推荐（近30期最热）",
                                "最近一期号码"], horizontal=True,
                     key="c8_mode")
    if _mode.startswith("系统推荐"):
        from collections import Counter as _C
        _cc = _C()
        for _row in data[-30:]:
            _cc.update(_row[1])
        _auto = [x for x, _ in _cc.most_common(8)]
        _defv = "、".join(str(x) for x in sorted(_auto))
    elif _mode.startswith("最近一期"):
        _defv = "、".join(str(x) for x in data[-1][1][:8])
    else:
        _defv = "、".join(str(x) for x in data[-1][1][:8])
    txt = st.text_input("8 个号码（逗号分隔）", value=_defv, key="c8_nums")
    try:
        nums = sorted({int(x) for x in txt.replace("，", ",")
                       .replace("、", ",").split(",") if x.strip().isdigit()})
    except Exception:
        nums = []
    if len(nums) < 3:
        st.warning("至少输入 3 个号")
        return
    if len(nums) != 8:
        st.info(f"当前 {len(nums)} 个号（不是 8 个也能算，只是组数不同）")
    combos = list(combinations(nums, 3))
    st.success(f"共 {len(nums)} 个号 → {len(combos)} 组三中三　"
               f"每期成本 {len(combos)} 单位")

    tab1, tab2, tab3 = st.tabs(["② 组合清单", "③ 逐期核对", "④ 回测统计"])

    with tab1:
        st.dataframe(pd.DataFrame({
            "序号": range(1, len(combos) + 1),
            "组合": ["、".join(str(x) for x in c) for c in combos]}),
            use_container_width=True, hide_index=True, height=380)
        st.download_button("📥 下载组合清单",
                           pd.DataFrame(
                               [{"组合": "、".join(str(x) for x in c)}
                                for c in combos]).to_csv(index=False)
                           .encode("utf-8-sig"),
                           file_name="8码三中三.csv", mime="text/csv",
                           key="c8_dl")

    with tab2:
        pick = st.selectbox("选择期号", periods[::-1], index=0,
                            key="c8_period")
        draw = pmap[pick]
        hit_nums = sorted(set(nums) & set(draw))
        # 中奖组合：三个号都在开奖号里
        win = [c for c in combos if set(c) <= set(draw)]
        st.markdown(f"**{pick} 开奖：** {'、'.join(str(x) for x in draw)}")
        st.markdown(f"**命中号码（{len(hit_nums)} 个）：** "
                    + ("、".join(str(x) for x in hit_nums) or "无"))
        m1, m2, m3 = st.columns(3)
        m1.metric("中奖组合数", len(win))
        m2.metric("投入", len(combos))
        m3.metric("回报", f"{len(win)*PAYOUT:.0f}")
        if win:
            st.success("中奖组合：" + " ｜ ".join(
                "、".join(str(x) for x in c) for c in win))
        else:
            st.warning("本期没有中奖组合")

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            n_bt = st.number_input("回测期数", 50, 3000, 300, 50,
                                   key="c8_bt")
        with c2:
            st.caption(f"每期成本 {len(combos)}，赔率 {int(PAYOUT)} 倍")
        if st.button("▶ 开始回测", key="c8_run"):
            start = max(0, len(periods) - int(n_bt))
            rows = []
            total_win = 0
            total_cost = 0
            for i in range(start, len(periods)):
                draw = set(pmap[periods[i]])
                w = [c for c in combos if set(c) <= draw]
                total_win += len(w)
                total_cost += len(combos)
                rows.append({"期号": periods[i], "中奖组合数": len(w),
                             "命中号码数": len(set(nums) & draw)})
            rev = total_win * PAYOUT
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("期数", len(rows))
            m2.metric("总中奖组合", total_win)
            m3.metric("总投入", total_cost)
            m4.metric("净收益", f"{rev-total_cost:+.0f}",
                      f"ROI {(rev/total_cost-1)*100:+.1f}%"
                      if total_cost else "")
            st.caption(f"总回报 {rev:.0f}（{total_win} 组 × {int(PAYOUT)}）")
            df = pd.DataFrame(rows[::-1])
            st.dataframe(df, use_container_width=True, hide_index=True,
                         height=340)
            st.download_button("📥 下载回测明细",
                               df.to_csv(index=False).encode("utf-8-sig"),
                               file_name="8码回测.csv", mime="text/csv",
                               key="c8_dl2")
            st.caption("说明：中奖组合数 = 开奖 7 个号里落进你 8 码的三数组合数；"
                       "命中 3 个号 = 1 组，中 4 个号 = 4 组。")
