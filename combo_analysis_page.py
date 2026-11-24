# -*- coding: utf-8 -*-
"""组合分析页：移植 Excel「数据分析系统」的核心功能
一、号码组：选一期 → 生成三数字/四数字组合
二、数字联动：输入某个号码 → 找历史同号期 → 统计下一期的 7 个号
三、中出核对：用联动候选 与 下一期开奖号比对，统计命中
四、七套汇总：把多次联动的候选合并计数，按次数降序
"""
import sys
from collections import Counter
from itertools import combinations

import pandas as pd
import streamlit as st


def _load_data(loader):
    """升序数据库源：返回 [(期号, [7个号码])]"""
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


def _link_numbers(data, value, look="上一期"):
    """找历史中某个号出现的位置，取相邻期的 7 个号"""
    res = []
    for i in range(1, len(data) - 1):
        if value in data[i][1]:
            if look == "上一期":
                res.append((data[i][0], data[i - 1][1]))
            else:
                res.append((data[i][0], data[i + 1][1]))
    return res


def _check_hits(data, cand_nums, next_n=True):
    """用候选号与每期的 6 个正码比对"""
    cset = set(cand_nums)
    hits = []
    for i in range(len(data) - 1):
        period, nums = data[i + 1] if next_n else data[i]
        got = sorted(cset & set(nums[:6]))
        hits.append({"期号": period, "命中数": len(got),
                     "命中号码": "、".join(str(x) for x in got)})
    return hits


def render(df_data, loader):
    st.markdown("## 🧩 组合分析（移植 Excel 版核心功能）")
    st.caption("数据源：系统数据库的升序开奖记录。"
               "四块内容：号码组组合 / 数字联动 / 中出核对 / 七套汇总。")

    data = _load_data(loader)
    if not data:
        st.error("读取不到升序数据源（_index.csv）")
        return
    st.info(f"已载入 {len(data)} 期，范围 {data[0][0]} ~ {data[-1][0]}")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["① 号码组组合", "② 数字联动", "③ 中出核对", "④ 七套汇总"])

    # ---------- ① 号码组组合 ----------
    with tab1:
        st.markdown("#### 号码组：选一期，生成所有三数字组合")
        periods = [p for p, _ in data][::-1]
        pick = st.selectbox("选择期号", periods, index=0, key="ca_period")
        row = dict((p, n) for p, n in data)[pick]
        six, seventh = row[:6], row[6]
        st.write(f"**{pick} 开奖：** 6 个正码 "
                 + "、".join(str(x) for x in six)
                 + f"　｜　第 7 球 {seventh}")

        c1, c2 = st.columns(2)
        with c1:
            use7 = st.checkbox("把第 7 球也纳入组合", value=True,
                               key="ca_use7")
        with c2:
            k = st.number_input("每组合几个号", 2, 5, 3, 1, key="ca_k")
        pool = six + ([seventh] if use7 else [])
        combos = sorted(combinations(sorted(pool), int(k)))
        st.success(f"共 {len(combos)} 组")
        st.dataframe(pd.DataFrame({
            "序号": range(1, len(combos) + 1),
            "组合": ["、".join(str(x) for x in c) for c in combos]}),
            use_container_width=True, hide_index=True, height=320)
        st.download_button("📥 下载号码组",
                           pd.DataFrame({"组合": ["、".join(str(x) for x in c)
                                                for c in combos]})
                           .to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"号码组_{pick}.csv", mime="text/csv",
                           key="ca_dl1")

    # ---------- ② 数字联动 ----------
    with tab2:
        st.markdown("#### 数字联动：某个号出现时，相邻期开什么")
        c1, c2, c3 = st.columns(3)
        with c1:
            val = st.number_input("要查的号码", 1, 49, 12, 1, key="ca_val")
        with c2:
            look = st.selectbox("取相邻哪一期", ["上一期", "下一期"],
                                index=1, key="ca_look")
        with c3:
            topn = st.number_input("候选取前几个", 3, 12, 7, 1, key="ca_topn")

        res = _link_numbers(data, int(val), look)
        if not res:
            st.warning("历史中没有该号")
        else:
            cnt = Counter()
            for _p, nums in res:
                for x in nums:
                    cnt[x] += 1
            ranked = cnt.most_common()
            st.markdown(f"**共 {len(res)} 次匹配**，相邻期号码出现次数：")
            tab = pd.DataFrame([{"号码": n, "次数": c,
                                 "占比": f"{c/len(res)*100:.0f}%"}
                                for n, c in ranked])
            st.dataframe(tab, use_container_width=True, hide_index=True,
                         height=320)
            cand = [n for n, _ in ranked[:int(topn)]]
            st.session_state["_ca_cand"] = cand
            st.success("候选号码（前 {} 个）：{}".format(
                len(cand), "、".join(str(x) for x in cand)))
            with st.expander("查看匹配明细", expanded=False):
                st.dataframe(pd.DataFrame(
                    [{"期号": p, "相邻期号码": "、".join(str(x) for x in n)}
                     for p, n in res]), use_container_width=True,
                    hide_index=True, height=280)

    # ---------- ③ 中出核对 ----------
    with tab3:
        st.markdown("#### 中出核对：候选号 与 每一期开奖号比对")
        cand = st.session_state.get("_ca_cand") or []
        manual = st.text_input("也可以手动输入候选号（逗号分隔）",
                               value="、".join(str(x) for x in cand),
                               key="ca_manual")
        use = [int(x) for x in manual.replace("，", ",")
               .replace("、", ",").split(",") if x.strip().isdigit()]
        if not use:
            st.info("请先在「② 数字联动」生成候选，或手动输入")
        else:
            hits = _check_hits(data, use)
            total = len(hits)
            hit3 = sum(1 for h in hits if h["命中数"] >= 3)
            hit2 = sum(1 for h in hits if h["命中数"] >= 2)
            hit1 = sum(1 for h in hits if h["命中数"] >= 1)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("候选号", len(use))
            m2.metric("至少中 1 个", f"{hit1/total*100:.1f}%",
                      f"{hit1}/{total}")
            m3.metric("至少中 2 个", f"{hit2/total*100:.1f}%",
                      f"{hit2}/{total}")
            m4.metric("中 3 个以上", f"{hit3/total*100:.1f}%",
                      f"{hit3}/{total}")
            st.dataframe(pd.DataFrame(hits[::-1]).head(200),
                         use_container_width=True, hide_index=True,
                         height=320)
            st.download_button("📥 下载中出核对",
                               pd.DataFrame(hits).to_csv(
                                   index=False).encode("utf-8-sig"),
                               file_name="中出核对.csv", mime="text/csv",
                               key="ca_dl3")

    # ---------- ④ 七套汇总 ----------
    with tab4:
        st.markdown("#### 七套汇总：多次联动的候选合并，按次数降序")
        st.caption("Excel 里是 7 套组合各列「号码/次数」再汇总；"
                   "这里改成输入 7 组联动号，自动合并计数。")
        default = ",".join(str(x) for x in
                           (st.session_state.get("_ca_cand") or []))
        txt = st.text_area("7 组联动号（每组一行，逗号分隔）",
                           value="\n".join([default] * 7) if default else "",
                           height=160, key="ca_sets")
        sets = []
        for line in (txt or "").splitlines():
            nums = [int(x) for x in line.replace("，", ",")
                    .replace("、", ",").split(",") if x.strip().isdigit()]
            if nums:
                sets.append(nums)
        if not sets:
            st.info("请先填写至少一组")
        else:
            cnt = Counter()
            for s in sets:
                for x in s:
                    cnt[x] += 1
            rows = sorted(cnt.items(), key=lambda x: -x[1])
            st.success(f"共 {len(sets)} 组，{len(rows)} 个不同号码")
            st.dataframe(pd.DataFrame(
                [{"号码": n, "出现次数": c} for n, c in rows]),
                use_container_width=True, hide_index=True, height=340)
            st.session_state["_ca_cand"] = [n for n, _ in rows[:7]]
            st.caption("已把次数最高的 7 个号写入候选，可到「③ 中出核对」验证")
