# -*- coding: utf-8 -*-
"""组合分析页（移植 Excel「数据分析系统」核心流程）
单排 / 多排 两种模式：
  单排：选一期 → 6 个正码 + 第 7 球 → 7 套组合（原始 20 组 + 6 种替换，共 35 组三数字）
  多排：选多期 → 每期各生成 35 组 → 合并统计
联动：每个组合（3 个号）→ 找历史同时出现这 3 个号的期 → 统计下一期的号码频次
"""
from collections import Counter
from itertools import combinations

import pandas as pd
import streamlit as st


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


def _sets_of_seven(six, seventh):
    """7 套组合：原始 6 球 20 组 + 每个位置换成第 7 球各 20 组"""
    outs = {}
    outs["原始6球"] = six
    names = ["1球", "2球", "3球", "4球", "5球", "6球"]
    for i in range(6):
        arr = list(six)
        arr[i] = seventh
        outs[f"替换{names[i]}"] = arr
    return outs


def _combos35(six, seventh):
    pool = sorted(set(six + [seventh]))
    return sorted(combinations(pool, 3))


def _link_stats(data, combos, scan_limit=3000, take_next=True):
    """每个组合触发后，下一期的号码频次"""
    cnt = Counter()
    matches = {}
    lo = max(0, len(data) - scan_limit)
    for cb in combos:
        need = set(cb)
        hits = 0
        for i in range(lo, len(data) - 1):
            if need <= set(data[i][1]):
                hits += 1
                tgt = data[i + 1][1] if take_next else data[i][1]
                for x in tgt:
                    cnt[x] += 1
        matches[cb] = hits
    return cnt, matches


def render(df_data, loader):
    st.markdown("## 🧩 组合分析")
    st.caption("单排 / 多排两种模式；每个组合去历史里做联动，"
               "统计下一期的号码频次，得到候选号。")

    data = _load_data(loader)
    if not data:
        st.error("读取不到升序数据源（_index.csv）")
        return
    periods = [p for p, _ in data]
    pmap = dict(data)

    mode = st.radio("模式", ["单排（一期）", "多排（多期）"],
                    horizontal=True, key="ca_mode")

    if mode.startswith("单排"):
        pick = st.selectbox("选择期号", periods[::-1], index=0,
                            key="ca_pick")
        chosen = [pick]
    else:
        c1, c2 = st.columns(2)
        with c1:
            n_multi = st.number_input("取最近几期", 2, 50, 5, 1,
                                      key="ca_n")
        with c2:
            st.caption("从最新一期往前取")
        chosen = periods[-int(n_multi):][::-1]

    combine_mode = st.selectbox(
        "记录方式", ["每期各算（单排展开）", "合并后再算"],
        help="每期各算 = 每期生成 35 组分别联动；合并后再算 = 把多期号码合在一起生成组合",
        key="ca_cmb")

    all_combos = []
    for p in chosen:
        six, sev = pmap[p][:6], pmap[p][6]
        if combine_mode.startswith("每期各算"):
            all_combos.extend(_combos35(six, sev))
        else:
            pass
    if combine_mode.startswith("合并后再算"):
        pool = []
        for p in chosen:
            pool.extend(pmap[p])
        pool = sorted(set(pool))
        if len(pool) >= 3:
            all_combos = list(combinations(pool, 3))
    all_combos = sorted(set(all_combos))
    st.info(f"参与组合：{len(all_combos)} 组　｜　涉及期数：{len(chosen)}")

    tab1, tab2, tab3 = st.tabs(["① 号码组（35组）", "② 联动统计", "③ 中出核对"])

    with tab1:
        p0 = chosen[0]
        six, sev = pmap[p0][:6], pmap[p0][6]
        st.markdown(f"#### {p0} 的号码组")
        st.write("6 个正码：" + "、".join(str(x) for x in six)
                 + f"　｜　第 7 球：{sev}")
        sets = _sets_of_seven(six, sev)
        rows = []
        for name, arr in sets.items():
            combos = list(combinations(sorted(arr), 3))
            rows.append({"套别": name, "号码": "、".join(str(x) for x in arr),
                         "组合数": len(combos),
                         "组合": " / ".join("、".join(str(x) for x in c)
                                           for c in combos[:6]) + " …"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     hide_index=True)
        st.caption("7 套 × 20 组 = 140 组，去重后为 C(7,3)=35 组")

    with tab2:
        st.markdown("#### 联动统计（每个组合 → 历史下一期号码频次）")
        scan = st.number_input("扫描历史期数", 200, 6000, 3000, 100,
                               key="ca_scan")
        if st.button("▶ 开始联动统计", key="ca_run"):
            with st.spinner("计算中…"):
                cnt, matches = _link_stats(data, all_combos, int(scan))
            if not cnt:
                st.warning("没有匹配")
            else:
                ranked = cnt.most_common()
                st.session_state["_ca_cand"] = [n for n, _ in ranked[:7]]
                st.dataframe(pd.DataFrame(
                    [{"号码": n, "出现次数": c} for n, c in ranked]),
                    use_container_width=True, hide_index=True, height=340)
                st.success("候选号码（前 7 个）："
                           + "、".join(str(n) for n, _ in ranked[:7]))
                top = sorted(matches.items(), key=lambda x: -x[1])[:20]
                with st.expander("组合触发次数（前 20）", expanded=False):
                    st.dataframe(pd.DataFrame(
                        [{"组合": "、".join(str(x) for x in cb),
                          "触发次数": c} for cb, c in top]),
                        use_container_width=True, hide_index=True)

    with tab3:
        st.markdown("#### 中出核对")
        cand = st.session_state.get("_ca_cand") or []
        txt = st.text_input("候选号（逗号分隔）",
                            value="、".join(str(x) for x in cand),
                            key="ca_cand_txt")
        use = [int(x) for x in txt.replace("，", ",").replace("、", ",")
               .split(",") if x.strip().isdigit()]
        if not use:
            st.info("先在「② 联动统计」生成候选")
        else:
            rows = []
            for p in chosen:
                nums = pmap[p]
                got = sorted(set(use) & set(nums[:6]))
                rows.append({"期号": p, "开奖": "、".join(str(x) for x in nums),
                             "正码命中": "、".join(str(x) for x in got) or "—",
                             "命中数": len(got)})
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                         hide_index=True)
            if len(chosen) == 1:
                st.metric("本期命中数", rows[0]["命中数"])
            else:
                st.metric("平均命中数",
                          f"{sum(r['命中数'] for r in rows)/len(rows):.2f}")
