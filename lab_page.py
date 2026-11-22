# -*- coding: utf-8 -*-
"""
🔬 研究中心（实验沙盒）
------------------------------------------------------------------
· 所有实验都在这里做，不影响正式页面
· 每做完一个实验，可保存到看板（source 统一为「研究所」）
· 一键清空：删掉本页所有实验数据（看板里 source=研究所 的条目）
· 想彻底恢复原状：删除本文件 + 去掉菜单一行即可（没有任何其它依赖）
------------------------------------------------------------------
"""
import itertools
import time
from collections import Counter
from datetime import datetime

import pandas as pd
import streamlit as st

SRC_TAG = "研究中心"
BAK_TAG = "研究中心·备份"
ENABLED = True          # 改成 False 即可停用本页（菜单自动隐藏）


# =====================================================================
# 通用：载入号码数据
# =====================================================================
def _as_rows(x):
    """把 DataFrame / list / tuple 统一成二维列表"""
    if x is None:
        return []
    if isinstance(x, list):
        return [list(r) for r in x]
    try:
        cols = list(getattr(x, "columns", []) or [])
        if cols:
            head = [str(c) for c in cols]
            body = x.values.tolist()
            return [head] + [list(r) for r in body]
        return [list(r) for r in x.values.tolist()]
    except Exception:
        try:
            return [list(r) for r in x]
        except Exception:
            return []


def _load_index6(loader):
    """期号 + 7 个号码（升序，第7位是特码）"""
    if "_lab_i7" in st.session_state:
        return st.session_state["_lab_i7"]
    out = []
    rows = _as_rows(loader["load_excel_data"]("_index.csv", None))
    ncol = 8
    if not rows:
        rows = _as_rows(loader["load_excel_data"]("_index6.csv", None))
        ncol = 7
    if rows:
        for r in rows[1:]:
            if len(r) < ncol:
                continue
            period = str(r[0]).strip()
            try:
                nums = tuple(int(float(r[1 + k] or 0)) for k in range(ncol - 1))
            except Exception:
                continue
            if period and all(nums):
                out.append((period, nums))
    out.sort(key=lambda x: x[0])
    st.session_state["_lab_i7"] = out
    return out


def _load_attr(loader):
    """号码 -> 属性 对照表"""
    if "_lab_attr2" in st.session_state:
        return st.session_state["_lab_attr2"]
    rows = _as_rows(loader["load_excel_data"]("_attr_map.csv", None))
    out = {}
    if rows:
        hdr = [str(x).strip() for x in rows[0]]
        for r in rows[1:]:
            if not r or not str(r[0]).strip().isdigit():
                continue
            out[int(float(r[0]))] = {hdr[i]: str(r[i]).strip()
                                     for i in range(1, min(len(hdr), len(r)))}
    st.session_state["_lab_attr2"] = out
    return out


def _num_of(cond, amap):
    """把杀号条件翻译成号码"""
    it = (cond or "").strip()
    if not it or not amap:
        return []
    if it.endswith("尾") and it[:-1].isdigit():
        return [n for n, a in amap.items() if a.get("尾数") == it[:-1]]
    if it.endswith("合"):
        return [n for n, a in amap.items() if a.get("数字合") == it]
    if it.endswith("段"):
        return [n for n, a in amap.items() if a.get("段数") == it]
    if it.endswith("门"):
        return [n for n, a in amap.items() if a.get("门数") == it]
    if it.endswith("号"):
        return [n for n, a in amap.items() if a.get("数字五行") == it[:-1]]
    if it.endswith("肖"):
        if it[:-1] in "金木水火土":
            return [n for n, a in amap.items() if a.get("生肖五行") == it[:-1]]
        return [n for n, a in amap.items() if a.get("生肖") == it[:-1]]
    if "波" in it:
        return [n for n, a in amap.items() if a.get("波单双") == it]
    return []


def _range_of(order, ball):
    UP = {1: (1, 20), 2: (2, 25), 3: (3, 30), 4: (4, 40),
          5: (15, 48), 6: (25, 49)}
    if order == "升序":
        return UP.get(int(ball), (1, 49))
    return (1, 49)


# =====================================================================
# 实验 A：单条件杀号回测
# =====================================================================
def _exp_single_kill(loader):
    st.markdown("#### 实验 A：单条件杀号回测")
    st.caption("输入一个杀号条件，统计历史上下期该球位是否真的避开了这些号。")

    c1, c2, c3 = st.columns(3)
    with c1:
        cond = st.text_input("杀号条件", "木肖", key="lab_a_cond",
                             placeholder="木肖 / 5尾 / 06合 / 3段")
    with c2:
        order = st.selectbox("排序", ["升序", "按序"], key="lab_a_order")
    with c3:
        ball = st.number_input("球位", 1, 6, 1, 1, key="lab_a_ball")

    c4, c5 = st.columns(2)
    with c4:
        year_from = st.text_input("起始年份", "2023", key="lab_a_year")
    with c5:
        mode = st.selectbox("判定口径",
                            ["被杀号的号码一个都没出", "被杀号的号码全没出(严格)",
                             "只看第一个被杀号"], key="lab_a_mode")

    if not st.button("▶ 运行实验 A", key="lab_a_run"):
        return

    data = _load_index6(loader)
    amap = _load_attr(loader)
    if not data or not amap:
        st.error("缺少 _index6.csv 或 _attr_map.csv")
        return

    nums = [n for n in _num_of(cond, amap)
            if _range_of(order, ball)[0] <= n <= _range_of(order, ball)[1]]
    if not nums:
        st.warning("这个条件在所选球位的区间里没有对应号码")
        return

    trial = hit = 0
    detail = []
    for period, balls in data:
        if period[:4] < year_from:
            continue
        draw = set(balls)
        if not (draw & set(nums)):
            continue
        trial += 1
        appeared = draw & set(nums)
        ok = (len(appeared) == 0) if mode.startswith("被杀号的号码一个都没出") else True
        if mode == "只看第一个被杀号":
            ok = nums[0] not in draw
        if ok:
            hit += 1
        detail.append((period, sorted(appeared)))

    if not trial:
        st.warning("样本为 0")
        return

    rate = hit / trial
    st.metric("杀中率", f"{rate*100:.2f}%", f"{trial} 期样本")
    st.caption(f"被杀号码：{' '.join(f'{n:02d}' for n in nums)}")
    st.dataframe(pd.DataFrame(
        [{"期号": p, "实际开出": " ".join(f"{x:02d}" for x in a)}
         for p, a in detail[-30:]]), use_container_width=True, hide_index=True)

    _save(loader, f"实验A {cond} {order}{ball}球 {year_from}+",
          f"条件 {cond}｜{order}第{ball}球｜{year_from} 年起\n"
          f"被杀号码 {' '.join(f'{n:02d}' for n in nums)}\n"
          f"样本 {trial} 期，杀中 {hit} 期，杀中率 {rate*100:.2f}%")


# =====================================================================
# 实验 B：组合池命中率
# =====================================================================
def _exp_pool(loader):
    st.markdown("#### 实验 B：三码组合池命中率")
    st.caption("从历史里找出出现 ≥N 次的组合，看下一期命中的比例。")

    c1, c2, c3 = st.columns(3)
    with c1:
        minc = st.number_input("组合最少出现次数", 1, 10, 2, 1, key="lab_b_minc")
    with c2:
        year_from = st.text_input("起始年份", "2023", key="lab_b_year")
    with c3:
        limit = st.number_input("回测期数上限", 50, 3000, 300, 50, key="lab_b_limit")

    if not st.button("▶ 运行实验 B", key="lab_b_run"):
        return

    data = _load_index6(loader)
    if len(data) < 100:
        st.error("数据不足")
        return

    sets = [frozenset(b) for _, b in data]
    start = max(50, len(data) - int(limit))
    tot_pool = tot_hit = draws = win_draws = 0
    for i in range(start, len(data)):
        if data[i][0][:4] < year_from:
            continue
        seed = list(itertools.combinations(sorted(data[i - 1][1]), 3))
        seed_sets = [frozenset(c) for c in seed]
        cnt = Counter()
        for j in range(i - 1):
            if any(s.issubset(sets[j]) for s in seed_sets) and j + 1 < i - 1:
                for c in itertools.combinations(sorted(data[j + 1][1]), 3):
                    cnt[c] += 1
        pool = [c for c, n in cnt.items() if n >= int(minc)]
        if not pool:
            continue
        draws += 1
        tot_pool += len(pool)
        hit = sum(1 for c in pool if all(v in sets[i] for v in c))
        tot_hit += hit
        if hit:
            win_draws += 1

    if not draws:
        st.warning("没有样本")
        return

    st.metric("单注命中率", f"{tot_hit/tot_pool*100:.4f}%",
              f"{tot_hit} 命中 / {tot_pool} 注")
    st.metric("有命中的期数", f"{win_draws/draws*100:.2f}%", f"{draws} 期")
    st.caption(f"理论单注命中率 0.1086%（1/921）")
    _save(loader, f"实验B 组合池 ≥{minc}次 {year_from}+",
          f"组合池 ≥{minc} 次｜{year_from} 年起｜{draws} 期\n"
          f"平均每期 {tot_pool/draws:.1f} 注\n"
          f"单注命中率 {tot_hit/tot_pool*100:.4f}%（理论 0.1086%）\n"
          f"有命中 {win_draws} 期（{win_draws/draws*100:.2f}%）")


# =====================================================================
# 实验 C：门数三三组合（3 期 × 3 位置）
# =====================================================================
def _exp_gate3(loader):
    st.markdown("#### 实验 C：数字形态组合（严格完全一致）")
    st.caption("把最近 N 期的指定位置按「门数」或「尾数」拼成数字串，"
               "要求历史中完全相同，统计下一期这些位置的形态。")

    _en = st.radio("编码方式", ["门数（十位）", "尾数（个位）"],
                   horizontal=True, key="lab_c_enc")
    r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
    with r1c1:
        npos = st.slider("球位数量", 2, 6, 3, 1, key="lab_c_npos")
    with r1c2:
        ps = st.multiselect("选择位置", list(range(1, 8)),
                            default=list(range(1, int(npos) + 1)),
                            max_selections=int(npos), key="lab_c_pos")
    with r1c3:
        nper = st.slider("叠加行数（期）", 2, 7, 3, 1, key="lab_c_nper",
                         help="2 期就是叠 2 行，7 期叠 7 行")
    with r1c4:
        _pdata = _load_index6(loader)
        _plist = ["最新"] + [p for p, _ in reversed(_pdata[-300:])]
        period = st.selectbox("基准期号", _plist, index=0,
                              key="lab_c_period")
    with r1c5:
        show_n = st.number_input("明细条数", 5, 50, 10, 5, key="lab_c_show")

    if st.button("▶ 运行实验 C", key="lab_c_run"):
        if len(ps) != int(npos):
            st.warning(f"需要选 {int(npos)} 个位置")
            return
        data = _load_index6(loader)
        if len(data) < 100:
            st.error("数据不足")
            return
        periods = [p for p, _ in data]
        if period and period != "最新":
            if period not in periods:
                st.warning("期号不存在")
                return
            idx = periods.index(period)
        else:
            idx = len(data) - 1

        _is_tail = ("尾数" in _en)
        _unit = "尾数" if _is_tail else "门数"

        def gate(n):
            return str(n % 10) if _is_tail else str(n // 10)

        def pat_at(i):
            return "".join(gate(data[i][1][b - 1]) for b in sorted(ps))

        from collections import Counter
        _summ = []
        _details = {}
        for _nper in range(2, 8):
            if idx < _nper - 1:
                continue
            _pat = "".join(pat_at(idx - k) for k in range(_nper))
            _ms = [i for i in range(_nper - 1, min(idx, len(data) - 1))
                   if "".join(pat_at(i - k) for k in range(_nper)) == _pat]
            _nxt = Counter(pat_at(i + 1) for i in _ms)
            _top = _nxt.most_common(1)[0] if _nxt else ("—", 0)
            _summ.append({
                "对比期数": _nper,
                "形态": _pat,
                "历史出现": len(_ms),
                "最常见下一期": _top[0] + (f"（{_top[1]}次）" if _nxt else ""),
                "集中度": f"{_top[1]/len(_ms)*100:.1f}%" if _ms else "—",
            })
            _details[_nper] = (_pat, _ms, _nxt)

        st.markdown(f"**{_unit}编码 · 位置 {sorted(ps)} · 叠加 {int(nper)} 期 · "
                    f"严格匹配（不允许容错）**")
        _cur = next((x for x in _summ if x["对比期数"] == int(nper)), None)
        if not _cur:
            st.warning("历史长度不足")
            return
        if _cur["历史出现"] == 0:
            st.warning(f"叠加 {int(nper)} 期：历史上没有完全相同的形态。"
                       "可减少球位数量、换位置，或改变叠加行数")
        with st.expander("参考：2~7 期各有几次样本", expanded=False):
            st.dataframe(pd.DataFrame(_summ), use_container_width=True,
                         hide_index=True)

        _pat, _ms, _nxt = _details[int(nper)]
        if not _ms:
            return
        st.markdown(f"**明细（叠加 {int(nper)} 期，形态 {_pat}，出现 {len(_ms)} 次）**")
        _rows = []
        for i in _ms[:int(show_n)]:
            _vals = [f"{data[i + 1][1][b - 1]:02d}" for b in sorted(ps)]
            _rows.append({"出现期号": data[i][0], "下一期": data[i + 1][0],
                          "下一期号码": " ".join(_vals),
                          f"下一期{_unit}": pat_at(i + 1)})
        st.dataframe(pd.DataFrame(_rows), use_container_width=True,
                     hide_index=True)
        # ---- 回测：与真实下一期对比 ----
        st.markdown("**回测对比**")
        _bx = idx + 1
        if _bx >= len(data):
            st.info(f"{data[idx][0]} 是最新一期，还没有下一期开奖，无法回测")
        else:
            _real_pat = pat_at(_bx)
            _real_vals = [f"{data[_bx][1][b - 1]:02d}" for b in sorted(ps)]
            _rank = [k for k, _v in _nxt.most_common()]
            _pos = _rank.index(_real_pat) + 1 if _real_pat in _rank else None
            _cnt = _nxt.get(_real_pat, 0)
            c_a, c_b, c_c = st.columns(3)
            c_a.metric("基准期", data[idx][0])
            c_b.metric("真实下一期", f"{data[_bx][0]}")
            c_c.metric(f"真实{_unit}", _real_pat)
            st.caption(f"真实号码：{' '.join(_real_vals)}")
            if _pos:
                st.success(f"✅ 命中：该形态在历史里出现过 {_cnt} 次，"
                           f"排第 {_pos} 位（共 {len(_nxt)} 种）")
            else:
                st.error(f"❌ 未命中：历史 {len(_ms)} 次里从未出现过 {_real_pat}")

        st.markdown(f"**下一期{_unit}分布**")
        st.dataframe(pd.DataFrame(
            [{f"{_unit}组合": k, "次数": v,
              "占比": f"{v/len(_ms)*100:.1f}%"} for k, v in _nxt.most_common()]),
            use_container_width=True, hide_index=True)

        _txt = (f"实验C｜{_unit}｜位置 {sorted(ps)}｜严格匹配\n"
                + "\n".join(f"{x['对比期数']}期 {x['形态']}："
                            f"{x['历史出现']} 次，最常见 {x['最常见下一期']}"
                            for x in _summ))
        _save(loader, f"实验C {_unit} {sorted(ps)} 扫描", _txt)


# =====================================================================
# 实验 D：属性联动
# =====================================================================
_LAB_ATTRS = ["生肖", "尾数", "门数", "段数", "数字合", "数字五行",
              "生肖五行", "波单双", "波色", "方位", "福禄寿",
              "大小肖", "阴阳天地", "3模", "尾五行", "物象",
              "颜色肖", "阴阳", "家野", "天地", "吉凶", "男女",
              "四宝", "头数", "单双", "单双组合"]


def _load_zodiac(loader):
    """逐期生肖表（走统一数据读取，云端本地都能取）"""
    if "_lab_zod2" in st.session_state:
        return st.session_state["_lab_zod2"]
    out = []
    try:
        rows = _as_rows(loader["load_excel_data"]("_zodiac_by_period.csv", None))
    except Exception:
        rows = None
    if rows:
        for r in rows[1:]:
            if r and len(r) >= 8 and str(r[0]).strip():
                out.append([str(r[0]).strip()] + [str(x).strip() for x in r[1:8]])
    st.session_state["_lab_zod2"] = out
    return out


def _load_zodiac_attrs(loader):
    if "_lab_zattr2" in st.session_state:
        return st.session_state["_lab_zattr2"]
    out = {}
    try:
        rows = _as_rows(loader["load_excel_data"]("_zodiac_attrs.csv", None))
    except Exception:
        rows = None
    if rows:
        hdr = [str(x).strip() for x in rows[0]]
        for r in rows[1:]:
            if r and str(r[0]).strip():
                out[str(r[0]).strip()] = {hdr[i]: str(r[i]).strip()
                                          for i in range(1, len(r))}
    st.session_state["_lab_zattr2"] = out
    return out


def _attr_of(period_key, ball, attr, zodiac, zattrs, amap, wx_mode="按号码"):
    """取某期某球某属性"""
    zrow = zodiac.get(period_key[0] if isinstance(period_key, (tuple, list)) else period_key)
    num = period_key[1][int(ball) - 1]
    if attr == "生肖":
        return zrow[int(ball) - 1] if zrow else ""
    if attr in ("生肖五行", "颜色肖", "物象", "方位", "福禄寿", "大小肖",
                "阴阳天地"):
        z = zrow[int(ball) - 1] if zrow else ""
        return zattrs.get(z, {}).get(attr, "")
    a = amap.get(num, {})
    if attr == "尾数":
        return str(num % 10)
    if attr == "数字合":
        return a.get("数字合", "")      # 严格取源数据值（含 22=05合）
    if attr == "门数":
        return a.get("门数", "")
    if attr == "段数":
        return a.get("段数", "")
    return a.get(attr, "")


def _exp_link_attr(loader):
    st.markdown("#### 实验 D：属性联动（两球推一球）")
    st.caption("选两个触发球位 + 一个目标球位；也可勾选「全部球位」一次算 6 组。")

    data = _load_index6(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    zrows = _load_zodiac(loader)
    zodiac = {r[0]: r[1:8] for r in zrows}
    zattrs = _load_zodiac_attrs(loader)
    amap = _load_attr(loader)
    periods = [p for p, _ in data]
    st.caption(f"数据：号码 {len(data)} 期｜生肖表 {len(zodiac)} 期｜"
               f"属性表 {len(amap)} 个号码")
    if not zodiac:
        st.error("生肖表没加载成功（_zodiac_by_period.csv）→ 先 Reboot app；"
                 "若仍为空说明文件没推到云端。")
        return
    if not amap:
        st.error("属性表没加载成功（_attr_map.csv），无法翻译号码。")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        attr = st.selectbox("属性", _LAB_ATTRS, index=0, key="lab_d_attr")
    with c2:
        b1 = st.selectbox("触发球位①", list(range(1, 8)), index=1,
                          key="lab_d_b1")
    with c3:
        b2 = st.selectbox("触发球位②", list(range(1, 8)), index=2,
                          key="lab_d_b2")
    _auto = (min(b1, b2) - 1) or 6
    with c4:
        tgt = st.selectbox("目标球位", list(range(1, 8)), index=_auto - 1,
                           key="lab_d_tgt",
                           help=f"规则建议 {_auto}：触发最小值-1（1,2 则推 6）")
    with c5:
        _plist0 = ["最新"] + list(reversed(periods[-300:]))
        base = st.selectbox("基准期", _plist0, index=0, key="lab_d_base")

    _all6 = st.checkbox("一次计算全部球位（2+3→1、3+4→2 … 1+2→6）",
                        value=False, key="lab_d_all")

    if not st.button("▶ 运行实验 D", key="lab_d_run"):
        return

    idx = len(data) - 1 if base == "最新" else periods.index(base)
    st.markdown(f"**基准期 {periods[idx]}｜属性 {attr}**")

    from collections import Counter
    _pairs = {1: (2, 3), 2: (3, 4), 3: (4, 5), 4: (5, 6), 5: (6, 7), 6: (1, 2)}
    jobs = list(_pairs.items()) if _all6 else [(tgt, (b1, b2))]
    if b1 == b2 and not _all6:
        st.warning("两个触发球位不能相同")
        return

    all_txt = []
    for _tgt, (_b1, _b2) in jobs:
        _v1 = _attr_of(data[idx], _b1, attr, zodiac, zattrs, amap)
        _v2 = _attr_of(data[idx], _b2, attr, zodiac, zattrs, amap)
        if not _v1 or not _v2:
            st.caption(f"第{_tgt}球：属性取值为空")
            continue
        cnt = Counter()
        hits = 0
        for i in range(0, idx):
            a1 = _attr_of(data[i], _b1, attr, zodiac, zattrs, amap)
            a2 = _attr_of(data[i], _b2, attr, zodiac, zattrs, amap)
            if a1 == _v1 and a2 == _v2:
                nv = _attr_of(data[i + 1], _tgt, attr, zodiac, zattrs, amap)
                if nv:
                    cnt[nv] += 1
                    hits += 1
        _lo, _hi = _tgt, 43 + _tgt
        st.markdown(f"**第{_tgt}球**（触发：第{_b1}球 {_v1} ＋ 第{_b2}球 {_v2}"
                    f"　历史 {hits} 期　区间 {_lo}~{_hi}）")
        if not cnt:
            st.caption("历史无相同组合")
            continue
        rows = []
        for k, v in cnt.most_common():
            nums = [n for n, a in amap.items()
                    if _lo <= n <= _hi and a.get(attr) == k]
            rows.append({attr: k, "次数": v, "占比": f"{v/hits*100:.1f}%",
                         "对应号码": " ".join(f"{n:02d}" for n in sorted(nums))})
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     hide_index=True)
        all_txt.append(f"第{_tgt}球（{_b1}+{_b2} → {_v1}+{_v2}）历史 {hits} 期：" +
                       "；".join(f"{k} {v}次" for k, v in cnt.most_common(5)))

    if all_txt:
        _save(loader, f"实验D {attr} {periods[idx]}", "\n".join(all_txt))


# =====================================================================
# 保存 / 清理
# =====================================================================
def _save(loader, title, text):
    fn = loader.get("board_add")
    if not fn:
        return
    if st.button(f"📌 保存实验结果到看板", key=f"lab_save_{abs(hash(title))%99999}"):
        try:
            fn(SRC_TAG, title, text)
            st.success("已保存到看板（来源：研究中心）")
        except Exception as e:
            st.warning(f"保存失败：{e}")


def _board_rows(loader):
    """直接读看板里本页的条目"""
    try:
        client = loader["supabase"]()
        if not client:
            return []
        res = (client.table("ai_board")
               .select("source,title,content,updated_at")
               .eq("source", SRC_TAG).execute())
        return res.data or []
    except Exception:
        return []


def _backup_rows(loader):
    try:
        client = loader["supabase"]()
        if not client:
            return []
        res = (client.table("ai_board")
               .select("source,title,content,updated_at")
               .eq("source", BAK_TAG).execute())
        return res.data or []
    except Exception:
        return []


_ARCHIVE = [
    ("触发行杀上值", "17 属性×7 球位，542 期", "最高 z=1.60", "无效"),
    ("上期同值延续", "生肖/尾数/五行 等", "与基准基本一致", "无效"),
    ("重号（上期同号）", "2318 期", "0.741 vs 0.735", "正常"),
    ("连号", "2318 期", "0.616 vs 0.612", "正常"),
    ("冷号（遗漏>20）", "2318 期", "12.51% vs 12.24%", "正常"),
    ("热号（近10期≥4）", "分年代", "符号来回翻", "噪声"),
    ("尾数延续", "2318 期", "49.06% vs 48.86%", "正常"),
    ("合数延续", "加权基线后", "z=+0.62", "假信号"),
    ("奇偶比 / 和值 / 区间", "2318 期", "符合随机", "正常"),
    ("号码间隔重复", "lag 1/2/3/5/10", "z 全部 <1.2", "正常"),
    ("马尔可夫（数字合 5 球 lag3）", "样本外", "p=0.0019 但", "不可用"),
    ("马尔可夫杀号转化", "杀最小 2~5 个", "z=-0.52~+1.38", "无效"),
    ("位置配对（升序↔按序）", "已多轮测试", "≈1/6 均匀", "无效"),
    ("三中三组合池", "5851 期回测", "期望 -29%", "数学必亏"),
    ("加注马丁格尔", "蒙特卡洛 500 次", "48% 破产", "危险"),
]


def _archive():
    st.markdown("#### 📚 结论档案（已检验的想法）")
    st.caption("测过的东西都记在这里，避免重复踩坑。")
    df = pd.DataFrame([{"方向": a, "方法/样本": b, "结果": c, "结论": d}
                       for a, b, c, d in _ARCHIVE])
    st.dataframe(df, use_container_width=True, hide_index=True)
    _ok = sum(1 for x in _ARCHIVE if x[3] in ("可用", "有效"))
    st.metric("通过验证的规律", _ok)
    st.info("结论：目前没有发现可稳定利用的规律。系统定位为分析工具，不做预测承诺。")


def _cleanup(loader):
    st.markdown("#### 🧹 无痕清理")
    st.caption("清理前会自动备份；清空后可从备份一键恢复。")

    rows = _board_rows(loader)
    baks = _backup_rows(loader)
    c1, c2, c3 = st.columns(3)
    c1.metric("待清理条目", len(rows))
    c2.metric("已有备份", len(baks))
    c3.metric("代码文件", "lab_page.py")

    if not st.session_state.get("username") == st.secrets.get("ADMIN_USERNAME", "admin"):
        st.info("仅管理员可清理")
        return

    st.divider()
    st.markdown("**第一步：确认要删除什么**")
    _scope = st.multiselect(
        "选择清理范围", ["实验数据（看板条目）", "代码文件（lab_page.py）"],
        default=["实验数据（看板条目）"], key="lab_scope")
    st.caption("代码文件不会被程序直接删除（避免破坏运行中的服务），"
               "会生成一条删除指引，你照做即可。")

    if rows:
        with st.expander(f"查看将被删除的 {len(rows)} 条数据", expanded=False):
            st.dataframe(pd.DataFrame(
                [{"标题": r.get("title", ""),
                  "时间": str(r.get("updated_at", ""))[:19]} for r in rows]),
                use_container_width=True, hide_index=True)

    st.markdown("**第二步：三道确认**")
    k1 = st.checkbox("我确认这些数据可以删除", key="lab_k1")
    k2 = st.checkbox("我确认已了解清理后需要从备份恢复", key="lab_k2")
    _word = st.text_input('请输入「确认清理」四个字', key="lab_kw")
    k3 = (_word.strip() == "确认清理")

    _ready = k1 and k2 and k3 and ("实验数据（看板条目）" in _scope)
    if not _ready:
        st.warning("三道确认全部通过后，按钮才会亮起")
    if st.button("🗑 执行清理", type="primary", disabled=not _ready,
                 key="lab_do_clear"):
        # ① 先备份
        ok_bak = 0
        try:
            client = loader["supabase"]()
            if client and rows:
                payload = [{"source": BAK_TAG, "title": r.get("title", ""),
                            "content": r.get("content", "")} for r in rows]
                client.table("ai_board").insert(payload).execute()
                ok_bak = len(payload)
        except Exception as e:
            st.error(f"备份失败，已中止清理：{e}")
            st.stop()
        # ② 再删除
        try:
            client = loader["supabase"]()
            client.table("ai_board").delete().eq("source", SRC_TAG).execute()
        except Exception as e:
            st.error(f"删除失败：{e}")
            st.stop()

        st.session_state.pop("ai_board", None)
        st.success(f"已备份 {ok_bak} 条，并清理 {len(rows)} 条数据")

        if "代码文件（lab_page.py）" in _scope:
            st.warning("代码文件请手动删除：")
            st.code("1. 删除仓库里的 lab_page.py\n"
                    "2. 删掉 app.py 菜单中的 \"🔬 研究中心\" 和对应分支\n"
                    "3. 或把 lab_page.py 里的 ENABLED 改成 False 立刻停用")
        time.sleep(0.8)
        st.rerun()

    st.divider()
    st.markdown("**♻️ 从备份恢复**")
    if not baks:
        st.caption("暂无备份")
    else:
        st.caption(f"共 {len(baks)} 条备份记录")
        if st.button(f"♻️ 恢复最近一次备份", key="lab_restore"):
            try:
                client = loader["supabase"]()
                payload = [{"source": SRC_TAG, "title": r.get("title", ""),
                            "content": r.get("content", "")} for r in baks]
                client.table("ai_board").insert(payload).execute()
                st.session_state.pop("ai_board", None)
                st.success(f"已恢复 {len(payload)} 条")
                time.sleep(0.8)
                st.rerun()
            except Exception as e:
                st.warning(f"恢复失败：{e}")
        if st.button("🧹 清空备份记录", key="lab_bak_clear"):
            try:
                client = loader["supabase"]()
                client.table("ai_board").delete().eq("source", BAK_TAG).execute()
                st.success("备份已清空")
                time.sleep(0.6)
                st.rerun()
            except Exception as e:
                st.warning(f"失败：{e}")

    st.divider()
    st.markdown("**⏸ 临时停用（不删任何东西）**")
    st.code("把 lab_page.py 里的 ENABLED 改成 False\n菜单会自动隐藏，"
            "数据保留；改回 True 即恢复", language=None)


# =====================================================================
# 页面入口
# =====================================================================
def render(df_data, H):
    if not ENABLED:
        st.warning("研究中心已停用（ENABLED = False），数据仍保留。")
        return
    st.title("🔬 研究中心（实验沙盒）")
    st.caption("在这里试各种公式，不满意就一键清空；确认可用再迁到正式页面。")
    with st.expander("📖 怎么用（30 秒看懂）", expanded=False):
        st.markdown(
            "**实验D 属性联动（你最常用的）**\n"
            "1. 选属性（生肖/尾数/物象…）\n"
            "2. 选球位①、球位②（比如 2 和 3）\n"
            "3. 选基准期（默认最新）\n"
            "4. 点「▶ 运行实验 D」\n\n"
            "结果 = 历史上同样组合出现过的期数 + 它们下一期目标球的属性排行"
            " + 每个属性对应的具体号码。\n\n"
            "**其它标签**：A 单条件杀号 / B 组合池 / C 数字串匹配，"
            "都是独立实验，互不影响。")

    tab1, tab2, tabc, tabd, tab4, tab3 = st.tabs(
        ["实验A 单条件杀号", "实验B 组合池", "实验C 形态组合",
         "实验D 属性联动", "结论档案", "清理"])
    with tab1:
        _exp_single_kill(H)
    with tab2:
        _exp_pool(H)
    with tabc:
        _exp_gate3(H)
    with tabd:
        _exp_link_attr(H)
    with tab4:
        _archive()
    with tab3:
        _cleanup(H)

    st.divider()
    st.caption(f"本页所有实验数据统一存入看板的「{SRC_TAG}」来源，便于一键清除。")
