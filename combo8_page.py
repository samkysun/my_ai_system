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
        # 一期只有 7 个号（6 正码 + 第7球），补上上一期第 1 个号凑 8 个
        _base = list(data[-1][1])[:7]
        _prev = [x for x in data[-2][1] if x not in _base]
        if _prev:
            _base.append(_prev[0])
        _defv = "、".join(str(x) for x in sorted(_base[:8]))
    else:
        _defv = "、".join(str(x) for x in data[-1][1][:7])
        _prev2 = [x for x in data[-2][1]
                  if x not in data[-1][1]]
        if _prev2:
            _defv += "、" + str(_prev2[0])
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

    # ---------- 中奖进度（自动） ----------
    st.markdown("### ② 中奖进度（自动跟踪）")
    _scan = data[-200:]
    _gap = 0
    _last_period = ""
    for _p, _arr in reversed(_scan):
        if len(set(nums) & set(_arr)) >= 3:
            _last_period = _p
            break
        _gap += 1
    if _last_period:
        st.warning(f"上次中奖：**{_last_period}**　→ 已过 **{_gap}** 期")
        _pnl = PAYOUT - len(combos) * (_gap + 1)
        st.metric("自上次中奖以来的盈亏", f"{_pnl:+.0f}",
                  "赚" if _pnl > 0 else "亏")
        st.caption(f"按每期投入 {len(combos)}、中奖 {int(PAYOUT)} 倍计算；"
                   f"超过 {int(PAYOUT)//len(combos)} 期才中就会亏")
    else:
        st.error("最近 200 期内从未中过 3 个号（这 8 码偏冷，建议换号）")

    tab1, tab2, tab3 = st.tabs(["③ 组合清单", "④ 逐期核对", "⑤ 回测统计"])

    with tab1:
        st.dataframe(pd.DataFrame({
            "序号": range(1, len(combos) + 1),
            "组合": ["、".join(str(x) for x in c) for c in combos]}),
            use_container_width=True, hide_index=True, height=380)
        # 打印单
        import datetime as _dt
        _rows_html = ""
        _per = 4
        for _i in range(0, len(combos), _per):
            _cells = ""
            for _c in combos[_i:_i + _per]:
                _cells += ("<td class='c'>" + "、".join(str(x) for x in _c)
                           + "</td><td class='k'>☐</td>")
            _rows_html += "<tr>" + _cells + "</tr>"
        _html = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>8码三中三打印单</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:14px;}}
h2{{margin:4px 0 8px 0;font-size:18px;}}
.info{{font-size:13px;margin-bottom:8px;}}
table{{border-collapse:collapse;width:100%;}}
td,th{{border:1px solid #999;padding:5px 6px;font-size:13px;}}
th{{background:#eee;}}
td.c{{width:32%;}}
td.k{{width:8%;text-align:center;}}
@media print{{ @page{{size:A4;margin:10mm;}} }}
</style></head><body>
<h2>8 码复式 · 三中三（共 {len(combos)} 组）</h2>
<div class='info'>号码：{('、'.join(str(x) for x in nums))}　｜　
单组赔率：{int(PAYOUT)} 倍　｜　每期投入：{len(combos)} 注　｜　
打印时间：{_dt.datetime.now():%Y-%m-%d %H:%M}</div>
<table><thead><tr><th>组合</th><th>✔</th><th>组合</th><th>✔</th>
<th>组合</th><th>✔</th><th>组合</th><th>✔</th></tr></thead>
<tbody>{_rows_html}</tbody></table>
<div class='info' style='margin-top:8px;'>核对：开奖 7 个号中与你 8 码重合 3 个 → 1 组中奖；
重合 4 个 → 4 组中奖；重合 5 个 → 10 组中奖。</div>
</body></html>"""
        st.download_button("🖨 生成打印单（HTML，可打印）",
                           _html.encode("utf-8"),
                           file_name="8码三中三打印单.html",
                           mime="text/html", key="c8_print")
        st.caption("下载后双击打开 → Ctrl+P 打印，可带到投注点逐组对照。")

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
