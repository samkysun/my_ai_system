# -*- coding: utf-8 -*-
"""三中三组合池
   ① 选一期 → 其 6 个平码拆成 20 组（C(6,3)）
   ② 这 20 组去历史里找「同时出现这 3 个号」的期（触发期）
   ③ 每个触发期的「下一期」6 个平码，同样拆成 20 组，汇总
   ④ 按出现次数降序成表（去重）
   ⑤ 可排除含指定数字的组合
   ⑥ 输入新开奖号码 → 检查表格中有多少组「三中三」
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
        if not ok or sum(1 for x in nums[:6] if x) < 6:
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
        if sum(1 for x in nums[:6] if x) < 6:
            continue
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def combos3(nums6):
    """6 个平码 → 20 组（升序排列、去重）"""
    seen, out = set(), []
    for a, b, c in itertools.combinations(sorted(nums6), 3):
        t = (a, b, c)
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def build_pool(data, seed_nums6):
    """返回 (触发期列表, 组合计数 Counter, 明细: [(触发期, 下一期, 组合列表)])"""
    seed = combos3(seed_nums6)
    idx_of = {p: i for i, (p, _) in enumerate(data)}
    triggers = []          # 触发期期号
    detail = []
    for cmb in seed:
        s = set(cmb)
        for i, (p, nums) in enumerate(data):
            if s.issubset({v for v in nums[:6] if v}):
                if i + 1 < len(data):
                    nxt_p, nxt_nums = data[i + 1]
                    if sum(1 for v in nxt_nums[:6] if v) == 6:
                        triggers.append(p)
                        detail.append((p, nxt_p, nxt_nums[:6], combos3(nxt_nums[:6])))
    cnt = Counter()
    for _, _, _, cs in detail:
        for c in cs:
            cnt[c] += 1
    return sorted(set(triggers)), cnt, detail


def render(df_data, H):
    st.title("🎯 三中三组合池")
    st.caption("选一期 → 20 组三号组合 → 找历史上同时出现这些组合的期 → "
               "取它们的下一期再拆 20 组 → 汇总成表。")

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

    # ---------- 一、选期 ----------
    st.markdown("### 一、选期数")
    per_list = [p for p, _ in reversed(data)]
    c1, c2 = st.columns([2, 3])
    with c1:
        pick = st.selectbox("选一期", per_list, index=0, key="c2_period")
    row = dict(data).get(pick, [0] * 7)
    seed6 = [v for v in row[:6] if v]
    with c2:
        st.markdown(f"该期平码：**{' '.join(f'{v:02d}' for v in seed6)}**"
                    f"　特码：{row[6]:02d}")
        st.markdown("20 组：" + "　".join(
            ",".join(f"{x:02d}" for x in c))[:1] + "")
        st.caption("20 组：" + " ｜ ".join(
            ",".join(f"{x:02d}" for x in c) for c in combos3(seed6)))

    if st.button("▶ 生成并汇总", type="primary", key="c2_run"):
        st.session_state["c2_go"] = True

    if not st.session_state.get("c2_go"):
        st.info("点「生成并汇总」开始计算")
        return

    with st.spinner("正在扫描历史…"):
        trig, cnt, detail = build_pool(data, seed6)

    st.markdown(f"### 二、结果概览")
    st.markdown(f"- 触发期数：**{len(trig)}** 期")
    st.markdown(f"- 汇总组合（去重后）：**{len(cnt)}** 组")
    if trig:
        st.caption("触发期（前 20）：" + "、".join(trig[:20])
                   + ("…" if len(trig) > 20 else ""))

    # ---------- 三、排除数字 ----------
    st.markdown("### 三、排除数字")
    ex_txt = st.text_input("不想出现的数字（逗号分隔，如 12,35）", "",
                           key="c2_ex")
    excl = {int(x) for x in re.findall(r"\d+", ex_txt)}
    if excl:
        st.caption("已排除： " + " ".join(f"{x:02d}" for x in sorted(excl)))

    items = [(c, n) for c, n in cnt.most_common()
             if not (set(c) & excl)]
    st.markdown(f"### 四、组合汇总表（按出现次数降序，共 {len(items)} 组）")

    rows = [{"序": i, "组合": ",".join(f"{x:02d}" for x in c), "出现次数": n}
            for i, (c, n) in enumerate(items, 1)]
    df_show = pd.DataFrame(rows)
    st.dataframe(df_show, use_container_width=True, hide_index=True, height=420)

    st.download_button("📥 下载表格（CSV）",
                       df_show.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"三中三_{pick}.csv", mime="text/csv",
                       key="c2_dl")

    # ---------- 五、中奖核对 ----------
    st.markdown("### 五、开奖核对（三中三）")
    z_txt = st.text_input("输入开奖号码（6 个平码，逗号分隔）", "",
                          key="c2_win")
    zs = [int(x) for x in re.findall(r"\d+", z_txt)][:6]
    if len(zs) == 6:
        pool = {c: n for c, n in items}
        win_combos = combos3(zs)
        hits = [(c, pool[c]) for c in win_combos if c in pool]
        st.markdown(f"**开奖号码：{' '.join(f'{v:02d}' for v in zs)}**")
        if hits:
            total = sum(n for _, n in hits)
            st.success(f"🎉 恭喜！三中三命中 **{len(hits)}** 组"
                       f"（累计出现次数 {total}）")
            hrows = [{"组合": ",".join(f"{x:02d}" for x in c),
                      "出现次数": n} for c, n in sorted(hits, key=lambda t: -t[1])]
            st.dataframe(pd.DataFrame(hrows), use_container_width=True,
                         hide_index=True)
        else:
            st.warning("本期没有命中三中三组合")
    else:
        st.caption("填满 6 个号码后自动核对")
