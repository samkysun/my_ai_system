# -*- coding: utf-8 -*-
"""三码组合池（严格还原 Excel「组合分析」）
   ① 选一期 → 取该期 7 个号 → C(7,3)=35 组（可切换 2~5 码）
   ② 只在该期之前的历史里找「7 个号包含某个组合」的期
   ③ 命中则取它的下一期，收集下一期的 7 个号
   ④ 下一期再拆 35 组，全局统计出现次数与出现过的期号
   ⑤ 只保留出现次数 >= 2 的组合，按次数降序
   ⑥ 用「选中期的下一期」实际开奖号做命中高亮
"""
import csv
import itertools
import re
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

_INDEX = "_index.csv"


def _parse_zong(rows):
    out = []
    if not rows:
        return out
    for r in rows[2:]:
        if len(r) < 26:
            continue
        p = str(r[18]).strip()
        if not p or p.lower() == "nan" or not p.replace(".", "").isdigit():
            continue
        nums = []
        ok = True
        for k in range(7):
            v = str(r[19 + k]).strip()
            if v == "" or v.lower() == "nan":
                nums.append(0)
                continue
            try:
                nums.append(int(float(v)))
            except Exception:
                ok = False
                break
        if not ok or sum(1 for x in nums if x) < 7:
            continue
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def _parse_index(rows):
    out = []
    for r in rows[1:]:
        if len(r) < 15:
            continue
        p = str(r[0]).strip()
        if not p:
            continue
        nums = []
        for k in range(7):
            try:
                nums.append(int(float(r[1 + k] or 0)))
            except Exception:
                nums.append(0)
        if sum(1 for x in nums if x) < 7:
            continue
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def combos_of(nums, k):
    """从 7 个号里取 k 个 → 去重的组合（升序元组）"""
    seen, out = set(), []
    for c in itertools.combinations(sorted(nums), k):
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def analyze(data, sel_period, k):
    """返回 dict：pool(计数器)、periods(每组出现在哪些期)、
       trigger_periods、next_periods、target(下一期)、total"""
    idx_of = {p: i for i, (p, _) in enumerate(data)}
    if sel_period not in idx_of:
        return None
    si = idx_of[sel_period]
    base_nums = [v for v in data[si][1] if v]
    pool_combo_list = combos_of(base_nums, k)
    pool_set = set(pool_combo_list)

    # ② 历史对碰（只看选中期之前）
    triggers = []
    next_periods = []
    for i in range(si):
        p, nums = data[i]
        ns = {v for v in nums if v}
        hit = any(set(c).issubset(ns) for c in pool_set)
        if not hit:
            continue
        ni = i + 1
        if ni >= si:                     # 下一期必须早于选中期
            continue
        np_, nn = data[ni]
        triggers.append(p)
        next_periods.append((np_, [v for v in nn if v]))

    # ④ 下一期再拆 k 码，全局统计
    cnt = Counter()
    where = defaultdict(list)
    for np_, nn in next_periods:
        for c in combos_of(nn, k):
            cnt[c] += 1
            where[c].append(np_)

    # ⑤ 只保留 >= 2 次
    items = [(c, n) for c, n in cnt.most_common() if n >= 2]

    target = data[si + 1] if si + 1 < len(data) else None
    return {
        "base": base_nums,
        "pool": pool_combo_list,
        "triggers": triggers,
        "next_periods": next_periods,
        "items": items,
        "where": where,
        "target": target,
        "total": len(items),
    }


def render(df_data, H):
    st.title("🎯 三码组合池")
    st.caption("选一期 → 7 个号拆成 N 组 → 历史里找包含这些组合的期 → "
               "取它们的下一期再拆 → 统计出现 ≥2 次的组合。")

    # ---------- 数据 ----------
    data = []
    _load = H.get("load_excel_data")
    if _load:
        try:
            with st.spinner("读取总数据表…"):
                data = _parse_zong(_load("总数据.xlsx", "总数据表") or [])
        except Exception:
            data = []
    if not data:
        try:
            with open(_INDEX, encoding="utf-8-sig", errors="replace") as f:
                data = _parse_index(list(csv.reader(f)))
        except Exception:
            data = []
    if not data:
        st.error("读不到数据")
        return
    st.caption(f"数据源：总数据表　共 {len(data)} 期（{data[0][0]} ~ {data[-1][0]}）")

    # ---------- 一、参数 ----------
    st.markdown("### 一、选期与码数")
    c1, c2, c3 = st.columns([2, 1, 3])
    per_list = [p for p, _ in reversed(data)]
    with c1:
        pick = st.selectbox("选一期（已开奖）", per_list, index=0, key="c2_period")
    with c2:
        k = st.selectbox("几码一组", [2, 3, 4, 5], index=1, key="c2_k")
    with c3:
        st.write("")
        st.caption(f"{k} 码组合数：C(7,{k}) = {len(combos_of(list(range(1, 8)), k))}")

    row = dict(data).get(pick, [0] * 7)
    st.markdown(f"**{pick} 期 7 个号：** {' '.join(f'{v:02d}' for v in row if v)}")
    st.caption("本池组合（前 10）：" + "　".join(
        ",".join(f"{x:02d}" for x in c)
        for c in combos_of([v for v in row if v], k)[:10]))

    if st.button("▶ 开始计算", type="primary", key="c2_run"):
        st.session_state["c2_go"] = True

    if not st.session_state.get("c2_go"):
        st.info("点「开始计算」")
        return

    with st.spinner("扫描历史…"):
        r = analyze(data, pick, int(k))
    if not r:
        st.error("找不到该期")
        return

    # ---------- 二、概览 ----------
    st.markdown("### 二、结果概览")
    st.markdown(f"- 本池组合：**{len(r['pool'])}** 组")
    st.markdown(f"- 命中的历史触发期：**{len(r['triggers'])}** 期")
    st.markdown(f"- 取到的下一期：**{len(r['next_periods'])}** 期")
    st.markdown(f"- 出现 ≥2 次的组合（A 列总行数）：**{r['total']}** 组")
    if r["triggers"]:
        st.caption("触发期（前 15）：" + "、".join(r["triggers"][:15])
                   + ("…" if len(r["triggers"]) > 15 else ""))

    # ---------- 三、表格 ----------
    st.markdown("### 三、组合统计表（按出现次数降序）")
    if not r["items"]:
        st.warning("没有出现 2 次及以上的组合")
        return

    target = r["target"]
    win = [v for v in target[1] if v] if target else []
    rows = []
    hit_total = 0
    for i, (c, n) in enumerate(r["items"], 1):
        mark = ""
        if win:
            got = len(set(c) & set(win))
            if got == len(c):
                mark = f"全中{len(c)}码"
                hit_total += 1
            elif got > 0:
                mark = f"中{got}个"
        rows.append({
            "序": i,
            "组合": ",".join(f"{x:02d}" for x in c),
            "共同出现次数": n,
            "出现在哪些下一期": "|".join(sorted(set(r["where"][c]))),
            "本期命中": mark,
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=430)

    st.download_button("📥 下载 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"三码组合池_{pick}.csv", mime="text/csv",
                       key="c2_dl")

    # ---------- 四、命中核对 ----------
    if target:
        st.markdown("### 四、下一期开奖核对")
        st.markdown(f"**{pick} 的下一期：{target[0]} 期**　号码："
                    f"{' '.join(f'{v:02d}' for v in win)}")
        if hit_total:
            st.success(f"🎉 恭喜！全中{int(k)}码的组合共 **{hit_total}** 组")
        else:
            st.warning(f"本期没有全中{int(k)}码的组合")
    else:
        st.info(f"{pick} 是最新一期，还没有下一期开奖数据")
