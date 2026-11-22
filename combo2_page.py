# -*- coding: utf-8 -*-
"""三码组合池（严格还原 Excel「组合分析」）
   ① 选一期 → 取该期 6 个平码 → C(6,3)=20 组（特码不参与）
   ② 只在该期之前的历史里找「6 个平码包含某个组合」的期
   ③ 命中则取它的下一期，收集下一期的 6 个平码
   ④ 下一期再拆成组合，全局统计出现次数与出现过的期号
   ⑤ 只保留出现次数 >= 2 的组合，按次数降序
   ⑥ 用「选中期的下一期」实际开奖号做命中高亮
"""
import csv
import itertools
import re
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

_INDEX = "_index6.csv"      # 153KB：期号 + 6 个平码


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
        if len(r) < 7:
            continue
        p = str(r[0]).strip()
        if not p:
            continue
        nums = []
        for k in range(6):
            try:
                nums.append(int(float(r[1 + k] or 0)))
            except Exception:
                nums.append(0)
        if sum(1 for x in nums if x) < 6:
            continue
        nums.append(0)
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def combos_of(nums, k):
    """从给定号码里取 k 个 → 去重的组合（升序元组）"""
    seen, out = set(), []
    for c in itertools.combinations(sorted(nums), k):
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def analyze(data, sel_period, k, min_count=1):
    """返回 dict：pool(计数器)、periods(每组出现在哪些期)、
       trigger_periods、next_periods、target(下一期)、total"""
    idx_of = {p: i for i, (p, _) in enumerate(data)}
    if sel_period not in idx_of:
        return None
    si = idx_of[sel_period]
    base_nums = [v for v in data[si][1][:6] if v]
    pool_combo_list = combos_of(base_nums, k)
    pool_set = set(pool_combo_list)

    # ② 历史对碰（只看选中期之前）
    triggers = []
    next_map = {}                        # 下一期去重：期号 -> 6 个平码
    for i in range(si):
        p, nums = data[i]
        ns = {v for v in nums[:6] if v}
        hit = any(set(c).issubset(ns) for c in pool_set)
        if not hit:
            continue
        ni = i + 1
        if ni >= si:                     # 下一期必须早于选中期
            continue
        np_, nn = data[ni]
        triggers.append(p)
        if np_ not in next_map:          # ★ 同一期只记一次
            next_map[np_] = [v for v in nn[:6] if v]
    next_periods = list(next_map.items())

    # ④ 下一期再拆 k 码，全局统计
    cnt = Counter()
    where = defaultdict(list)
    for np_, nn in next_periods:
        for c in combos_of(nn, k):
            cnt[c] += 1
            where[c].append(np_)

    # ⑤ 只保留 >= 2 次
    items = [(c, n) for c, n in cnt.most_common() if n >= min_count]

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
    st.caption("选一期 → 6 个平码拆成 N 组 → 历史里找包含这些组合的期 → "
               "取它们的下一期再拆 → 只保留出现 2 次及以上的组合。")

    # ---------- 数据（带缓存，避免每次都解析） ----------
    import time as _t
    _ck = "c2_data_cache"
    _c = st.session_state.get(_ck)
    if not _c or _t.time() - _c.get("ts", 0) > 1800:
        data = []
        _load = H.get("load_excel_data")
        # 优先用精简索引（322KB，最快）
        if _load:
            try:
                with st.spinner("读取索引…"):
                    idx_rows = _load(_INDEX, None) or []
                data = _parse_index(idx_rows)
            except Exception:
                data = []
        if not data:
            try:
                with open(_INDEX, encoding="utf-8-sig", errors="replace") as f:
                    data = _parse_index(list(csv.reader(f)))
            except Exception:
                data = []
        if not data and _load:
            try:
                with st.spinner("读取总数据表…"):
                    data = _parse_zong(_load("总数据.xlsx", "总数据表") or [])
            except Exception:
                data = []
        if not data:
            st.error("读不到数据")
            return
        st.session_state[_ck] = {"data": data, "ts": _t.time()}
    else:
        data = _c["data"]
    st.caption(f"数据源：升序索引　共 {len(data)} 期（{data[0][0]} ~ {data[-1][0]}）")

    # ---------- 一、参数 ----------
    st.markdown("### 一、选期与码数")
    c1, c2, c3 = st.columns([2, 1, 3])
    per_list = [p for p, _ in reversed(data)]
    with c1:
        pick = st.selectbox("选一期（已开奖）", per_list, index=0, key="c2_period")
    k = 3          # 固定：6 个平码三三组合
    with c2:
        _minc = st.selectbox("显示出现几次及以上", [1, 2, 3, 4, 5],
                             index=1, key="c2_minc")
        st.caption("1 次 = 全部列出；2 次 = 只看重复出现的")
    with c3:
        st.write("")
        st.caption(f"{k} 码组合数：C(6,{k}) = {len(combos_of(list(range(1, 7)), k))}")

    row = dict(data).get(pick, [0] * 7)
    st.markdown(f"**{pick} 期 6 个平码：** {' '.join(f'{v:02d}' for v in row if v)}")
    st.caption("本池组合（前 10）：" + "　".join(
        ",".join(f"{x:02d}" for x in c)
        for c in combos_of([v for v in row[:6] if v], k)[:10]))

    if st.button("▶ 开始计算", type="primary", key="c2_run"):
        st.session_state["c2_go"] = True

    if not st.session_state.get("c2_go"):
        st.info("点「开始计算」")
        return

    with st.spinner("扫描历史…"):
        r = analyze(data, pick, int(k), int(_minc))
    if not r:
        st.error("找不到该期")
        return

    # ---------- 二、概览 ----------
    st.markdown("### 二、结果概览")
    st.markdown(f"- 本池组合：**{len(r['pool'])}** 组")
    st.markdown(f"- 命中的历史触发期：**{len(r['triggers'])}** 期")
    st.markdown(f"- 取到的下一期：**{len(r['next_periods'])}** 期")
    st.markdown(f"- 出现 2 次及以上的组合：**{r['total']}** 组")
    if r["triggers"]:
        st.caption("触发期（前 15）：" + "、".join(r["triggers"][:15])
                   + ("…" if len(r["triggers"]) > 15 else ""))

    # ---------- 三、表格 ----------
    st.markdown("### 三、组合统计表（按出现次数降序）")
    if not r["items"]:
        st.warning("没有出现 2 次及以上的组合")
        return

    target = r["target"]
    win = [v for v in target[1][:6] if v] if target else []
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

    st.markdown("**把结果转到智能分析**")
    _btxt = (f"期号 {pick}　6 个平码：{' '.join(f'{v:02d}' for v in r['base'])}\n"
             f"触发 {len(r['triggers'])} 期　汇总组合 {r['total']} 组\n\n"
             + "\n".join(f"{x['组合']}\t{x['共同出现次数']}"
                          for x in rows[:200]))
    if H.get("board_add") and st.button("📤 转到全自动智能分析", key="c2_to_board"):
        try:
            H["board_add"]("三码组合池", f"{pick} 期 组合池", _btxt)
            st.success("已转到看板")
        except Exception as _e:
            st.warning(f"推送失败：{_e}")

    st.caption("说明：三中三理论中奖概率 0.1086%（1/921）。")

    # ---------- 号码频次排行 ----------
    st.markdown("### 五、号码出现频次排行（由多到少）")
    _nscore = Counter()      # 按组合出现次数加权
    _ncombo = Counter()      # 出现在多少个组合里
    for c, n in r["items"]:
        for v in c:
            _nscore[v] += n
            _ncombo[v] += 1
    if not _nscore:
        st.info("没有可统计的号码")
    else:
        _order = sorted(_nscore.keys(),
                        key=lambda v: (-_ncombo[v], -_nscore[v], v))
        _win_set = set(win) if win else set()
        rows_n = [{"排名": i, "号码": f"{v:02d}",
                   "出现次数（含该号的组合数）": _ncombo[v],
                   "累计出现（按组合次数加权）": _nscore[v],
                   "本期命中": ("✅ 开出" if v in _win_set else "")}
                  for i, v in enumerate(_order, 1)]
        df_n = pd.DataFrame(rows_n)

        def _hl(row):
            if row["本期命中"]:
                return ["background-color:#ffe08a;font-weight:700"] * len(row)
            return [""] * len(row)

        try:
            st.dataframe(df_n.style.apply(_hl, axis=1),
                         use_container_width=True, hide_index=True, height=380)
        except Exception:
            st.dataframe(df_n, use_container_width=True, hide_index=True, height=380)

        if _win_set:
            _hit_nums = [v for v in _order if v in _win_set]
            if _hit_nums:
                st.success(f"本期开出并出现在排行中的号码："
                           + " ".join(f"{v:02d}" for v in _hit_nums))
            else:
                st.warning("本期开出的号码都不在排行里")
        st.download_button("📥 下载号码排行",
                           df_n.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"号码排行_{pick}.csv", mime="text/csv",
                           key="c2_dl_n")
        st.markdown(
            "**怎么读这两列：**\n"
            "- 出现次数：有多少个组合包含这个号码"
            "（每个组合里同一个号只出现一次）\n"
            "- 累计出现（加权）：再乘上每个组合自己的出现次数。"
            "比如 03,08,25 出现了 4 次，08 号就从这一个组合累计 4 次。"
        )

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

    # ---------- 六、盈亏回测（页面最下面） ----------
    st.divider()
    st.markdown("### 六、盈亏回测（按上面所选参数）")
    st.caption(f"规则：用前一期 6 平码拆 {k} 码组合 → 对碰历史 → "
               f"取触发期的下一期再拆 → 保留出现 ≥{int(_minc)} 次的组合 → "
               f"下一期全买这些组合。")

    _b1, _b2, _b3 = st.columns(3)
    with _b1:
        _bt_n = st.number_input("回测期数（往前）", 20, 1000, 100, 20,
                                key="c2_bt_n")
    with _b2:
        _odds = st.number_input("中奖赔率（倍）", 1, 100000, 655, 1,
                                key="c2_bt_odds")
    with _b3:
        _unit = st.number_input("每注金额（元）", 1, 10000, 1, 1,
                                key="c2_bt_unit")

    if st.button("📉 运行盈亏回测", key="c2_bt_run"):
        st.session_state["c2_bt_go2"] = True

    if st.session_state.get("c2_bt_go2"):
        with st.spinner("回测中…"):
            _idx = {p2: i for i, (p2, _) in enumerate(data)}
            _end = _idx.get(pick, len(data) - 1)
            _start = max(2, _end - int(_bt_n))
            _rows, _spent, _back, _wins = [], 0, 0, 0
            for i in range(_start, _end):
                _seed = combos_of([v for v in data[i - 1][1][:6] if v], k)
                if not _seed:
                    continue
                _ss = [set(c) for c in _seed]
                _cnt = Counter()
                for j in range(i - 1):
                    _ns = {v for v in data[j][1][:6] if v}
                    if any(s.issubset(_ns) for s in _ss) and j + 1 < i - 1:
                        for c in combos_of(
                                [v for v in data[j + 1][1][:6] if v], k):
                            _cnt[c] += 1
                _pool = [c for c, n in _cnt.items() if n >= int(_minc)]
                if not _pool:
                    continue
                _draw = {v for v in data[i][1][:6] if v}
                _hit = [c for c in _pool if set(c).issubset(_draw)]
                _cost = len(_pool) * _unit
                _gain = len(_hit) * _odds * _unit
                _spent += _cost
                _back += _gain
                if _hit:
                    _wins += 1
                _rows.append({
                    "期号": data[i][0],
                    "买入注数": len(_pool),
                    "投入": _cost,
                    "命中注数": len(_hit),
                    "回收": _gain,
                    "盈亏": _gain - _cost,
                    "命中组合": "、".join(",".join(f"{x:02d}" for x in c)
                                        for c in _hit[:3]),
                    "开奖": " ".join(f"{v:02d}" for v in sorted(_draw)),
                })

            if not _rows:
                st.warning("没有可回测的期数")
            else:
                _profit = _back - _spent
                _c1b, _c2b, _c3b, _c4b = st.columns(4)
                _c1b.metric("总投入", f"{_spent:,.0f} 元")
                _c2b.metric("总回收", f"{_back:,.0f} 元")
                _c3b.metric("盈亏", f"{_profit:,.0f} 元")
                _c4b.metric("回报率",
                            f"{_back/max(1,_spent)*100:.1f}%")
                st.caption(f"回测 {len(_rows)} 期｜有命中 {_wins} 期｜"
                           f"共中 {sum(r['命中注数'] for r in _rows)} 注｜"
                           f"平均每期 {_spent/max(1,len(_rows)):.0f} 元")

                _d2 = pd.DataFrame(list(reversed(_rows)))

                def _hl2(row):
                    if row["命中注数"]:
                        return ["background-color:#ffe08a;font-weight:bold"] * len(row)
                    return [""] * len(row)

                try:
                    st.dataframe(_d2.style.apply(_hl2, axis=1),
                                 use_container_width=True, hide_index=True,
                                 height=360)
                except Exception:
                    st.dataframe(_d2, use_container_width=True,
                                 hide_index=True, height=360)
                st.download_button(
                    "📥 下载回测明细",
                    _d2.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"盈亏回测_{pick}.csv", mime="text/csv",
                    key="c2_bt_dl2")
