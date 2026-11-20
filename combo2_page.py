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

    # ---------- 收益测算与风险提示 ----------
    st.markdown("### 六、收益测算与风险提示")
    _c1, _c2 = st.columns([1, 3])
    with _c1:
        _odds = st.number_input("每组中奖赔率", 1, 100000, 655, 1, key="c2_odds")
    with _c2:
        st.write("")
        st.caption("三中三的理论概率：C(46,3)/C(49,6) = 0.1086% = 1/921，"
                   "即公平赔率应为 921 倍。")

    _n = len(r["items"])              # 每期投注注数
    _fair = 921.0                     # 公平赔率
    _ev_per_bet = _odds / _fair       # 每注期望回收
    _per_draw_cost = _n
    _per_draw_back = _n * _odds / _fair
    _per_draw_net = _per_draw_back - _per_draw_cost

    _rows_e = [
        {"项目": "每期投注注数", "数值": f"{_n} 注"},
        {"项目": "单注命中概率", "数值": "0.1086%（1/921，理论值）"},
        {"项目": f"每注期望回收（赔率 {int(_odds)}）", "数值": f"{_ev_per_bet:.3f} 倍"},
        {"项目": "每期期望投入", "数值": f"{_per_draw_cost:.0f} 注"},
        {"项目": "每期期望回收", "数值": f"{_per_draw_back:.1f} 注"},
        {"项目": "每期期望盈亏", "数值": f"{_per_draw_net:+.1f} 注"},
        {"项目": "100 期期望盈亏", "数值": f"{_per_draw_net*100:+.0f} 注"},
        {"项目": "不亏所需的赔率", "数值": "921 倍"},
    ]
    st.dataframe(pd.DataFrame(_rows_e), use_container_width=True, hide_index=True)

    if _ev_per_bet < 1:
        st.error(
            f"⚠️ 按 {int(_odds)} 倍赔率，每投 1 注期望只收回 {_ev_per_bet:.3f} 注，"
            f"长期亏损 {(1-_ev_per_bet)*100:.1f}%。\n\n"
            f"每期投 {_n} 注的话，100 期预计亏 {-_per_draw_net*100:.0f} 注。\n"
            f"要提高胜率只能提高赔率——低于 921 倍的玩法在数学上必亏。"
        )
    elif _ev_per_bet > 1:
        st.success(f"按 {int(_odds)} 倍赔率，每注期望回收 {_ev_per_bet:.3f} 注，"
                   f"理论上有 {(_ev_per_bet-1)*100:.1f}% 正期望。"
                   "但这需要赔率真实且能兑现。")
    else:
        st.warning("赔率刚好等于公平值，长期不赚不亏（不含手续费）。")

    # ---------- 七、资金与盈亏计算器 ----------
    st.markdown("### 七、资金与盈亏计算器")
    st.caption("输入你自己的数字，直接看期望、破产概率和资金曲线。")

    _q1, _q2, _q3 = st.columns(3)
    with _q1:
        _bets = st.number_input("每期买几注", 1, 5000, max(1, len(r["items"])),
                                1, key="calc_bets")
        _per = st.number_input("每注金额（元）", 0.1, 100000.0, 1.0, 1.0,
                               key="calc_per")
    with _q2:
        _odds2 = st.number_input("赔率（倍）", 1, 100000, 655, 1,
                                 key="calc_odds")
        _addpct = st.number_input("不中后加注 %（0=平注）", 0, 200, 0, 5,
                                  key="calc_add")
    with _q3:
        _bank = st.number_input("起始本金（元）", 1.0, 100000000.0,
                                100000.0, 1000.0, key="calc_bank")
        _rounds = st.number_input("计算多少期", 10, 5000, 100, 10,
                                  key="calc_rounds")

    # 单期命中概率
    _p1 = 1 - (1 - 1 / 921) ** int(_bets)
    _avg_gap = 1 / _p1 if _p1 > 0 else 0
    _cost0 = _bets * _per
    _winamt1 = _odds2 * _per                     # 中 1 注的回收
    _ev_each = _p1 * _winamt1 - _cost0            # 每期期望盈亏（平注）

    st.markdown(f"**单期命中概率**：{_p1*100:.2f}%　→　"
                f"平均约 **{_avg_gap:.1f} 期**中一次")
    st.markdown(f"**每期成本**：{_cost0:,.0f} 元　"
                f"**中一次回收**：{_winamt1:,.0f} 元　"
                f"**每期期望**：{_ev_each:+,.0f} 元")

    # 平注 N 期
    _flat_net = _ev_each * int(_rounds)
    _rows_c = [
        {"项目": "每期投入", "数值": f"{_cost0:,.0f} 元"},
        {"项目": "单期中奖概率", "数值": f"{_p1*100:.2f}%"},
        {"项目": "平均中奖间隔", "数值": f"{_avg_gap:.1f} 期"},
        {"项目": "中一注回收", "数值": f"{_winamt1:,.0f} 元"},
        {"项目": "每期期望盈亏（平注）", "数值": f"{_ev_each:+,.0f} 元"},
        {"项目": f"{int(_rounds)} 期期望盈亏（平注）", "数值": f"{_flat_net:+,.0f} 元"},
        {"项目": "回本所需赔率", "数值": f"{1/_p1*_cost0/_per:.0f} 倍"
                                    if _p1 > 0 else "—"},
    ]
    st.dataframe(pd.DataFrame(_rows_c), use_container_width=True, hide_index=True)

    # 加注模拟（蒙特卡洛：真实连续不中随机发生）
    if _addpct > 0:
        import random as _rnd
        _step = 1 + _addpct / 100
        _runs = 500
        _rnd.seed(20261120)
        _ruins = 0
        _finals = []
        _maxmults = []
        for _r in range(_runs):
            _bank3 = _bank
            _mult = 1.0
            _mm = 1.0
            for _k in range(int(_rounds)):
                _c = _cost0 * _mult
                if _c > _bank3:
                    _ruins += 1
                    _bank3 = 0
                    break
                _bank3 -= _c
                if _rnd.random() < _p1:          # 本期命中
                    _bank3 += _winamt1 * _mult
                    _mult = 1.0
                else:
                    _mult *= _step
                    _mm = max(_mm, _mult)
            _finals.append(_bank3)
            _maxmults.append(_mm)

        _finals.sort()
        _avg = sum(_finals) / len(_finals)
        _med = _finals[len(_finals) // 2]
        _ruin_rate = _ruins / _runs * 100

        st.markdown(f"**加注 {int(_addpct)}% 蒙特卡洛模拟**"
                    f"（{_runs} 次实验，每次 {int(_rounds)} 期，按真实概率随机命中）")
        _rows_m = [
            {"项目": "加注倍数", "数值": f"×{_step:.2f} 每期"},
            {"项目": "破产概率", "数值": f"{_ruin_rate:.1f}%"},
            {"项目": "平均期末资金", "数值": f"{_avg:,.0f} 元"},
            {"项目": "中位数期末资金", "数值": f"{_med:,.0f} 元"},
            {"项目": "最差结果", "数值": f"{_finals[0]:,.0f} 元"},
            {"项目": "最好结果", "数值": f"{_finals[-1]:,.0f} 元"},
            {"项目": "平均最高加注", "数值": f"×{sum(_maxmults)/len(_maxmults):.1f}"},
        ]
        st.dataframe(pd.DataFrame(_rows_m), use_container_width=True, hide_index=True)

        if _ruin_rate > 0:
            st.error(f"❌ 约 {_ruin_rate:.0f}% 的可能在 {int(_rounds)} 期内破产"
                     f"（本金 {_bank:,.0f} 元全部亏光）")
        if _avg < _bank:
            st.warning(f"平均结局是亏损 {_avg-_bank:+,.0f} 元——"
                       "加注只是把亏损换成了'偶尔爆仓'。")

    # 连输概率表
    st.markdown("**连续不中概率表**")
    _rows_s = []
    _cum = 1.0
    _mult2 = 1.0
    _spent = 0.0
    for k in range(1, 16):
        _spent += _cost0 * _mult2
        _mult2 *= (1 + _addpct / 100) if _addpct > 0 else 1.0
        _rows_s.append({
            "连输期数": k,
            "概率": f"{_cum*(1-_p1)**k*100:.2f}%",
            "累计投入": f"{_spent:,.0f} 元",
            "下期需投": f"{_cost0*_mult2:,.0f} 元",
        })
    st.dataframe(pd.DataFrame(_rows_s), use_container_width=True, hide_index=True)

    if _ev_each < 0:
        st.error(f"每期期望 {_ev_each:+,.0f} 元，长期必亏。"
                 f"把赔率提到 {1/_p1*_cost0/_per:.0f} 倍以上才可能不亏。")

    st.info(
        "**重要提醒**：组合池只是把历史出现过的组合列出来，"
        "并不能改变每个组合 1/921 的中奖概率。"
        "任何选号方法都无法降低庄家的抽水比例。"
    )

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
