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
import json
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


def _load_order(loader, order="升序"):
    """按排序载入 7 个号码：升序用 1~7 列，按序用 8~14 列"""
    key = "_lab_" + ("asc" if order == "升序" else "draw")
    if key in st.session_state:
        return st.session_state[key]
    rows = _as_rows(loader["load_excel_data"]("_index.csv", None))
    out = []
    if rows:
        base = 1 if order == "升序" else 8
        for r in rows[1:]:
            if len(r) < base + 7:
                continue
            period = str(r[0]).strip()
            try:
                nums = tuple(int(float(r[base + k] or 0)) for k in range(7))
            except Exception:
                continue
            if period and all(nums):
                out.append((period, nums))
    out.sort(key=lambda x: x[0])
    st.session_state[key] = out
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
    _rows = []
    _poolcnt = Counter()
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
        hit_combo = [c for c in pool if all(v in sets[i] for v in c)]
        hit = len(hit_combo)
        tot_hit += hit
        if hit:
            win_draws += 1
        _rows.append({
            "期号": data[i][0],
            "池注数": len(pool),
            "命中注数": hit,
            "命中组合": "、".join("-".join(f"{v:02d}" for v in sorted(c))
                                for c in hit_combo[:5]),
            "开奖": " ".join(f"{v:02d}" for v in sorted(sets[i])),
        })
        for _c in pool:
            _poolcnt[_c] += 1

    if not draws:
        st.warning("没有样本")
        return

    st.success(f"✅ 计算完成：样本 {draws} 期｜共 {tot_pool} 注｜"
               f"命中 {tot_hit} 注｜有命中的期 {win_draws} 期")
    _m1, _m2, _m3 = st.columns(3)
    _m1.metric("单注命中率", f"{tot_hit/tot_pool*100:.4f}%")
    _m2.metric("有命中的期数占比", f"{win_draws/draws*100:.2f}%",
               f"{win_draws}/{draws} 期")
    _m3.metric("平均每期注数", f"{tot_pool/draws:.0f} 注")
    st.caption("理论单注命中率 0.1086%（1/921）")
    if _rows:
        st.markdown("**明细结果（最新在上）**")
        _df = pd.DataFrame(list(reversed(_rows)))

        def _hl(row):
            if row["命中注数"]:
                return ["background-color:#ffe08a;font-weight:bold"] * len(row)
            return [""] * len(row)

        st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                     hide_index=True, height=320)
        st.download_button(
            "📥 下载明细",
            _df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"实验B_{year_from}.csv", mime="text/csv",
            key="lab_b_dl")

        with st.expander("组合池组成（按出现次数）", expanded=False):
            st.dataframe(pd.DataFrame(
                [{"组合": "-".join(f"{v:02d}" for v in sorted(c)),
                  "出现期数": n}
                 for c, n in _poolcnt.most_common(50)]),
                use_container_width=True, hide_index=True, height=280)

        # ---- 存档 ----
        st.markdown("**存档**")
        _ARC = "lab_exp_b_runs.json"
        _arc = []
        try:
            _txt = loader["gh_read"](_ARC) if loader.get("gh_read") else ""
            if _txt:
                _arc = json.loads(_txt)
                if not isinstance(_arc, list):
                    _arc = []
        except Exception:
            _arc = []

        if st.button("💾 保存本次结果", key="lab_b_save"):
            _rec = {
                "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
                "参数": f"≥{minc}次｜{year_from}年起｜{int(limit)}期",
                "样本期数": draws,
                "平均每期注数": round(tot_pool / draws, 1),
                "单注命中率": f"{tot_hit/tot_pool*100:.4f}%",
                "有命中期数": f"{win_draws}/{draws}",
                "明细": list(reversed(_rows))[:200],
            }
            _arc.append(_rec)
            try:
                loader["gh_write"](_ARC, json.dumps(_arc, ensure_ascii=False),
                                   "保存实验B结果")
                st.success("已存档")
                st.rerun()
            except Exception as _e2:
                st.warning(f"存档失败：{_e2}")

        if _arc:
            st.caption(f"已有 {len(_arc)} 条存档")
            _pick2 = st.selectbox(
                "查看存档",
                [f"{i+1}. {r.get('时间','')}｜{r.get('参数','')}"
                 for i, r in enumerate(reversed(_arc))],
                index=0, key="lab_b_arcpick")
            _idx2 = len(_arc) - 1 - int(_pick2.split(".")[0]) + 1
            _r2 = _arc[max(0, min(len(_arc) - 1, _idx2 - 1))]
            st.json({k: v for k, v in _r2.items() if k != "明细"})
            if _r2.get("明细"):
                st.dataframe(pd.DataFrame(_r2["明细"]),
                             use_container_width=True, hide_index=True,
                             height=240)

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
    _rng = st.radio("球位区间口径",
                    ["严格（数学边界 k~43+k）", "经验（历史 99% 区间）"],
                    horizontal=True, key="lab_d_rng",
                    help="严格：只要数学上可能出现就纳入；"
                         "经验：只保留历史上 99% 情况的范围")

    if not st.button("▶ 运行实验 D", key="lab_d_run"):
        return

    _strict = st.checkbox("严格模式：匹配期不包含紧邻基准期的那一期",
                          value=False, key="lab_d_strict")
    _blind = st.checkbox("盲测：不显示真实下一期结果",
                         value=False, key="lab_d_blind")
    idx = (len(data) - 1 if base.startswith("最新一期")
           else periods.index(base))
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
        _detail = []
        _lim = idx - 1 if _strict else idx
        for i in range(0, max(0, _lim)):
            a1 = _attr_of(data[i], _b1, attr, zodiac, zattrs, amap)
            a2 = _attr_of(data[i], _b2, attr, zodiac, zattrs, amap)
            if a1 == _v1 and a2 == _v2:
                nv = _attr_of(data[i + 1], _tgt, attr, zodiac, zattrs, amap)
                if nv:
                    cnt[nv] += 1
                    hits += 1
                    _detail.append({"触发期": data[i][0],
                                    f"第{_b1}球": a1,
                                    f"第{_b2}球": a2,
                                    "下一期": data[i + 1][0],
                                    f"下一期第{_tgt}球{attr}": nv})
        _EMP = {1: (1, 28), 2: (2, 36), 3: (5, 41), 4: (9, 45),
                5: (14, 48), 6: (22, 49), 7: (1, 49)}
        if _rng.startswith("经验"):
            _lo, _hi = _EMP.get(_tgt, (_tgt, 43 + _tgt))
        else:
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
        _real = (_attr_of(data[idx + 1], _tgt, attr, zodiac, zattrs, amap)
                 if idx + 1 < len(data) else "")
        _rank = [r[attr] for r in rows]
        _pos = (_rank.index(_real) + 1) if (_real and _real in _rank) else None
        if _blind:
            _real = ""
            st.caption("盲测模式：已隐藏真实下一期结果")
        if _real:
            if _pos:
                st.success(f"真实下一期 {data[idx+1][0]} 开 **{_real}**，"
                           f"在榜上第 {_pos} 位 ✅")
            else:
                st.error(f"真实下一期 {data[idx+1][0]} 开 **{_real}**，"
                         f"未进榜 ❌")
        _df = pd.DataFrame(rows)
        if _real:
            def _hl(row):
                c = ("background-color:#ffe08a;font-weight:bold"
                     if row[attr] == _real else "")
                return [c] * len(row)
            st.dataframe(_df.style.apply(_hl, axis=1),
                         use_container_width=True, hide_index=True)
        else:
            st.dataframe(_df, use_container_width=True, hide_index=True)
        with st.expander(f"🔍 触发行明细（全部 {len(_detail)} 条，可核对）",
                         expanded=False):
            _ddf = pd.DataFrame(_detail)
            st.dataframe(_ddf, use_container_width=True, hide_index=True,
                         height=320)
            st.download_button(
                f"📥 下载第{_tgt}球明细",
                _ddf.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"实验D_第{_tgt}球_{attr}_{periods[idx]}.csv",
                mime="text/csv", key=f"lab_d_dl_{_tgt}")
        all_txt.append(f"第{_tgt}球（{_b1}+{_b2} → {_v1}+{_v2}）历史 {hits} 期：" +
                       "；".join(f"{k} {v}次" for k, v in cnt.most_common(5)))

    if all_txt:
        _save(loader, f"实验D {attr} {periods[idx]}", "\n".join(all_txt))


# =====================================================================
# 实验 E：锁定目标球 · 多组合联动（前二）
# =====================================================================
def _exp_target_multi(loader):
    st.markdown("#### 实验 E：锁定目标球 · 多组合联动（取前二）")
    st.caption("锁定一个目标球位，用 1+2、2+3、3+4、4+5、5+6、6+7 六组分别联动，"
               "汇总后取前 2 名作为目标球属性，回测命中高亮。")

    data = _load_index6(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    zrows = _load_zodiac(loader)
    zodiac = {r[0]: r[1:8] for r in zrows}
    zattrs = _load_zodiac_attrs(loader)
    amap = _load_attr(loader)
    periods = [p for p, _ in data]
    if not zodiac or not amap:
        st.error("生肖表或属性表未加载成功，请 Reboot app")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        tgt = st.selectbox("锁定目标球位", list(range(1, 8)), index=0,
                           key="lab_e_tgt")
    with c2:
        attr = st.selectbox("属性", _LAB_ATTRS, index=0, key="lab_e_attr")
    with c3:
        base = st.selectbox(
            "计算来源期（用它推算下一期）",
            ["最新一期（算下一期）"] + list(reversed(periods[-300:])),
            index=0, key="lab_e_base")
    _rng = st.radio("球位区间口径",
                    ["严格（数学边界）", "经验（历史99%）"],
                    horizontal=True, key="lab_e_rng")

    if not st.button("▶ 运行实验 E", key="lab_e_run"):
        return

    idx = (len(data) - 1 if base.startswith("最新一期")
           else periods.index(base))
    pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
    _EMP = {1: (1, 28), 2: (2, 36), 3: (5, 41), 4: (9, 45),
            5: (14, 48), 6: (22, 49), 7: (1, 49)}
    _lo, _hi = (_EMP.get(tgt, (tgt, 43 + tgt)) if _rng.startswith("经验")
                else (tgt, 43 + tgt))

    _tgtname = (periods[idx + 1] if idx + 1 < len(data)
                else f"{periods[idx]} 的下一期（未开）")
    st.markdown(f"**用 {periods[idx]} 推算 {_tgtname}｜锁定第{tgt}球｜"
                f"属性 {attr}｜号码区间 {_lo}~{_hi}**")

    from collections import Counter
    total = Counter()
    per_pair = []
    for (a, b) in pairs:
        v1 = _attr_of(data[idx], a, attr, zodiac, zattrs, amap)
        v2 = _attr_of(data[idx], b, attr, zodiac, zattrs, amap)
        if not v1 or not v2:
            continue
        c = Counter()
        n = 0
        for i in range(0, idx):
            if _attr_of(data[i], a, attr, zodiac, zattrs, amap) != v1:
                continue
            if _attr_of(data[i], b, attr, zodiac, zattrs, amap) != v2:
                continue
            nv = _attr_of(data[i + 1], tgt, attr, zodiac, zattrs, amap)
            if nv:
                c[nv] += 1
                n += 1
        total.update(c)
        top = c.most_common(1)[0] if c else ("—", 0)
        per_pair.append({"组合": f"{a}+{b}", "取值": f"{v1}+{v2}",
                         "历史期数": n,
                         "该组首位": top[0],
                         "首位次数": top[1],
                         "该组分布": "、".join(f"{k}{v}"
                                              for k, v in c.most_common())})

    st.markdown("**各组合分别结果**")
    st.dataframe(pd.DataFrame(per_pair), use_container_width=True,
                 hide_index=True)

    if not total:
        st.warning("六组都没有历史命中")
        return
    allc = sum(total.values())
    st.markdown(f"**汇总累计（锁定第{tgt}球，{attr}，共 {allc} 次）**")
    _rank = total.most_common()
    _top1 = _rank[0][1] if _rank else 0
    _second = next((v for _, v in _rank if v < _top1), None)
    _thr = _second if _second is not None else _top1
    _top_set = [k for k, v in _rank if v >= _thr] if _rank else []
    if len(_top_set) > 1:
        st.info(f"前二名：{'、'.join(_top_set)}" +
                ("（含并列）" if len(_top_set) > 2 else ""))
    rows = []
    _prev = None
    _rank_no = 0
    for _i, (k, v) in enumerate(_rank):
        if v != _prev:
            _rank_no = _i + 1
            _prev = v
        nums = [n for n, aa in amap.items()
                if _lo <= n <= _hi and aa.get(attr) == k]
        rows.append({"名次": _rank_no, attr: k, "总次数": v,
                     "占比": f"{v/allc*100:.1f}%",
                     "对应号码": " ".join(f"{n:02d}" for n in sorted(nums))})
    _top2 = list(_top_set)

    _real = (_attr_of(data[idx + 1], tgt, attr, zodiac, zattrs, amap)
             if idx + 1 < len(data) else "")
    if _real:
        if _real in _top2:
            st.success(f"✅ 回测命中：真实 {data[idx+1][0]} 第{tgt}球 {attr} = "
                       f"**{_real}**（前二：{'、'.join(_top2)}）")
        else:
            st.error(f"❌ 未命中：真实 {data[idx+1][0]} 第{tgt}球 {attr} = "
                     f"**{_real}**（前二：{'、'.join(_top2)}）")

    _df = pd.DataFrame(rows)
    def _hl(row):
        if _real and row[attr] == _real:
            return ["background-color:#ffe08a;font-weight:bold"] * len(row)
        if row[attr] in _top2:
            return ["background-color:#e8f0fe"] * len(row)
        return [""] * len(row)
    st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                 hide_index=True)

    st.download_button("📥 下载汇总",
                       _df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"实验E_第{tgt}球_{attr}_{periods[idx]}.csv",
                       mime="text/csv", key="lab_e_dl")
    _save(loader, f"实验E 第{tgt}球 {attr} {periods[idx]}",
          "前二：" + "、".join(_top2) + "\n" +
          "\n".join(f"{k} {v}次" for k, v in total.most_common(6)))


# =====================================================================
# 实验 F：三三组合 → 上一期球位号码
# =====================================================================
def _exp_combo_prev(loader):
    st.markdown("#### 实验 F：三三组合 → 上一期球位号码")
    st.caption("计算目标期的球位：用「目标期的上一期」7 个号码做三三组合，"
               "到目标期之前的历史里找触发，统计触发期的「上一期」指定球位号码。")

    _ord = st.radio("排序方式", ["升序", "按序"], horizontal=True,
                    key="lab_f_ord")
    if _ord == "按序":
        st.warning("按序各球位没有取值边界（都是 1~49），"
                   "同样条件下命中率会明显低于升序；建议以升序为主。")
    data = _load_order(loader, _ord)
    if not data:
        st.error("该排序没有数据（按序数据可能从 2000 年才有）")
        return
    periods = [p for p, _ in data]

    c1, c2, c3 = st.columns(3)
    with c1:
        base = st.selectbox(
            "目标期",
            ["下一期（预测，未开）", "最新已开期"]
            + list(reversed(periods[-300:])),
            index=0, key="lab_f_base")
    with c2:
        ball = st.selectbox("取第几球", list(range(1, 8)), index=0,
                            key="lab_f_ball")
    with c3:
        span = st.selectbox("历史范围", ["全部", "最近 2000 期",
                                        "最近 1000 期", "最近 500 期"],
                            index=0, key="lab_f_span")

    if st.button("📊 对比升序/按序命中率（近 100 期）", key="lab_f_cmp"):
        _cmp = {}
        for _o in ("升序", "按序"):
            _d = _load_order(loader, _o)
            if len(_d) < 120:
                continue
            _ps = [x[0] for x in _d]
            _hit = _tot = 0
            for _i in range(len(_d) - 100, len(_d)):
                if _i < 3:
                    continue
                _src = _i - 1
                _cb = [frozenset(c) for c in
                       __import__("itertools").combinations(
                           sorted(_d[_src][1]), 3)]
                from collections import Counter as _C
                _cnt = _C()
                for _j in range(1, _src):
                    _s = set(_d[_j][1])
                    if any(c.issubset(_s) for c in _cb):
                        _cnt[_d[_j - 1][1][ball - 1]] += 1
                if not _cnt:
                    continue
                _top = [k for k, _ in _cnt.most_common(5)]
                _tot += 1
                if _d[_i][1][ball - 1] in _top:
                    _hit += 1
            if _tot:
                _cmp[_o] = (_hit, _tot, _hit / _tot)
        if _cmp:
            st.markdown("**近 100 期前 5 名命中率对比**")
            st.dataframe(pd.DataFrame(
                [{"排序": k, "命中": v[0], "样本": v[1],
                  "命中率": f"{v[2]*100:.1f}%"} for k, v in _cmp.items()]),
                use_container_width=True, hide_index=True)
        else:
            st.info("数据不足，无法对比")

    if not st.button("▶ 运行实验 F", key="lab_f_run"):
        return

    import itertools
    from collections import Counter

    _virtual = base.startswith("下一期")
    if _virtual:
        src = len(data) - 1              # 最新一期做组合
        idx = len(data)                  # 不存在（未开）
        _tname = "下一期（未开）"
    else:
        idx = (len(data) - 1 if base == "最新已开期"
               else periods.index(base))
        src = idx - 1
        _tname = periods[idx]
    if src < 2:
        st.warning("历史不足")
        return
    nums = data[src][1]
    combos = list(itertools.combinations(sorted(nums), 3))
    st.markdown(f"**{_ord}｜目标 {_tname}**（待算第{ball}球）　"
                f"**组合来源 {periods[src]}**：{nums}")
    _hint = (f"触发范围：全部历史" if _virtual
             else f"触发范围：{periods[src]} 之前")
    st.caption(f"三三组合共 {len(combos)} 组；{_hint}")

    limits = {"全部": 0, "最近 2000 期": 2000, "最近 1000 期": 1000,
              "最近 500 期": 500}
    lo = max(1, src - limits[span]) if limits[span] else 1

    combo_set = [frozenset(c) for c in combos]
    cnt = Counter()
    matched = []
    for j in range(lo, src):
        s = set(data[j][1])
        if any(c.issubset(s) for c in combo_set):
            prev = data[j - 1][1][ball - 1]
            cnt[prev] += 1
            matched.append((periods[j], periods[j - 1], prev))

    st.metric("历史命中期数", len(matched))
    if not cnt:
        st.info("历史上没有包含这些组合的期")
        return

    if not cnt:
        st.warning("该区间内没有历史数据")
        return
    ranked = cnt.most_common()
    order = [k for k, _ in ranked]
    # 球位区间锁定（升序才有边界）
    if _ord == "升序":
        _lo, _hi = int(ball), 43 + int(ball)
    else:
        _lo, _hi = 1, 49
    cnt = Counter({k: v for k, v in cnt.items() if _lo <= k <= _hi})
    st.caption(f"球位区间：第{ball}球 {_lo}~{_hi}（只统计此区间内的号码）")

    actual = None if _virtual else data[idx][1][ball - 1]
    pos = (order.index(actual) + 1) if (actual in order) else None
    if _virtual:
        st.info(f"预测结果：第{ball}球最可能开出前 5 名 → " +
                "、".join(f"{k:02d}" for k, _ in ranked[:5]))
    elif pos:
        st.success(f"✅ {_tname} 第{ball}球实开 {actual:02d}，排第 {pos} 位")
    else:
        st.error(f"❌ {_tname} 第{ball}球实开 {actual:02d}，未进榜")

    total = sum(cnt.values())
    rows = [{"名次": i + 1, "号码": f"{k:02d}", "次数": v,
             "占比": f"{v/total*100:.1f}%",
             "命中": "★" if k == actual else ""}
            for i, (k, v) in enumerate(ranked)]
    _df = pd.DataFrame(rows)

    def _hl(row):
        if row["命中"]:
            return ["background-color:#ffe08a;font-weight:bold"] * len(row)
        return [""] * len(row)

    st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                 hide_index=True)
    st.download_button("📥 下载结果",
                       _df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"实验F_{_ord}_第{ball}球_{_tname}.csv",
                       mime="text/csv", key="lab_f_dl")

    with st.expander(f"🔍 命中明细（全部 {len(matched)} 条）", expanded=False):
        st.dataframe(pd.DataFrame(
            [{"命中四期": a, "上一期": b, f"上一期第{ball}球": f"{c:02d}"}
             for a, b, c in matched]),
            use_container_width=True, hide_index=True, height=320)


# =====================================================================
# 实验 G：球位热号（1~2 个）+ 可选期回测
# =====================================================================
def _exp_hot_pick(loader):
    st.markdown("#### 实验 G：单球位热号（1~2 个）+ 回测")
    st.caption("按历史出现频率取最热的 1~2 个号码，回测每 4~7 期中一次的可行性。")

    data = _load_index6(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p for p, _ in data]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ball = st.selectbox("球位（升序）", list(range(1, 8)), index=0,
                            key="lab_g_ball")
    with c2:
        topn = st.radio("输出个数", [1, 2, 3], horizontal=True, index=1,
                        key="lab_g_topn")
    with c3:
        hist_span = st.selectbox("取频次的历史范围",
                                 ["全部", "最近 2000 期", "最近 1000 期",
                                  "最近 500 期"], index=0, key="lab_g_span")
    with c4:
        _start_p = st.selectbox("回测起始期", list(reversed(periods)),
                                index=min(299, len(periods) - 1),
                                key="lab_g_start")
    with st.columns([1, 3])[0]:
        _end_p = st.selectbox("回测结束期", list(reversed(periods)), index=0,
                              key="lab_g_end")
    _win = st.selectbox(
        "回测滚动窗口（每期用最近多少期算热号）",
        [50, 100, 200, 500, 0], index=1, key="lab_g_win",
        format_func=lambda x: "全部累计（推荐不变）" if x == 0 else f"最近 {x} 期")

    if not st.button("▶ 运行实验 G", key="lab_g_run"):
        return

    from collections import Counter
    limits = {"全部": 0, "最近 2000 期": 2000, "最近 1000 期": 1000,
              "最近 500 期": 500}
    span = limits[hist_span]
    seq = [d[1][ball - 1] for d in data]
    n = len(seq)

    # ---- 当前推荐（用全部历史）----
    hist = seq[-span:] if span else seq
    cnt = Counter(hist)
    top = [v for v, _ in cnt.most_common(topn)]
    lo, hi = ball, 43 + ball
    try:
        _next_p = str(int(periods[-1]) + 1)
    except Exception:
        _next_p = "下一期"
    _sum_top = sum(cnt[v] for v in top)
    _p_top = _sum_top / len(hist) if hist else 0
    st.success(f"🎯 预测 {_next_p} 期 第{ball}球：" +
               "、".join(f"**{v:02d}**" for v in top) +
               f"　（历史占比 {_p_top*100:.1f}%，平均 {1/_p_top:.1f} 期一次）"
               if _p_top else "")
    st.caption(f"依据：{hist_span} 频次统计｜区间 {lo}~{hi}｜"
               f"最近一期 {periods[-1]} 开 {seq[-1]:02d}")

    # ---- 回测（walk-forward）----
    hit = tot = hits_series = 0
    rows = []
    _i1 = periods.index(_start_p)
    _i2 = periods.index(_end_p)
    if _i1 > _i2:
        _i1, _i2 = _i2, _i1
    start = max(topn, _i1)
    end = min(n, _i2 + 1)
    for i in range(start, end):
        _w = int(_win) if int(_win) > 0 else (span or i)
        c_hist = seq[max(0, i - _w):i]
        if not c_hist:
            continue
        c = Counter(c_hist)
        pick = [v for v, _ in c.most_common(topn)]
        actual = seq[i]
        ok = actual in pick
        tot += 1
        hit += 1 if ok else 0
        rows.append({"期号": periods[i], "推荐": " ".join(f"{v:02d}" for v in pick),
                     "实开": f"{actual:02d}", "命中": "★" if ok else ""})
    if not tot:
        st.warning("样本不足")
        return

    rate = hit / tot
    gap = (1 / rate) if rate else 0
    st.caption(f"回测区间：{periods[start]} ~ {periods[end-1]}"
               f"（{tot} 期）")
    st.metric("回测命中率", f"{rate*100:.1f}%",
              f"{hit}/{tot} 期")
    st.metric("平均多少期中一次", f"{gap:.1f} 期" if gap else "—",
              "目标 4~7 期")

    rows = list(reversed(rows))
    _df = pd.DataFrame(rows)

    def _hl(row):
        if row["命中"]:
            return ["background-color:#ffe08a;font-weight:bold"] * len(row)
        return [""] * len(row)

    st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                 hide_index=True, height=360)
    st.download_button("📥 下载回测明细",
                       _df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"实验G_第{ball}球_top{topn}.csv",
                       mime="text/csv", key="lab_g_dl")

    # 连续性统计
    streaks = []
    cur = 0
    for r in rows:
        if r["命中"]:
            if cur:
                streaks.append(cur)
            cur = 0
        else:
            cur += 1
    if cur:
        streaks.append(cur)
    if streaks:
        streaks.sort()
        mid = streaks[len(streaks) // 2]
        st.caption(f"未中连续期数：最长 {max(streaks)} 期，中位 {mid} 期，"
                   f"共 {len(streaks)} 段")


# =====================================================================
# 实验 H：6 码分配（1球1个、2球2个、5球2个、6球1个）+ 中3回测
# =====================================================================
def _exp_six_pick(loader):
    from math import comb

    st.markdown("#### 实验 H：6 码分配 + 中 3 回测")
    st.caption("按位置优势分配号码数：第1球 1 个、第2球 2 个、第5球 2 个、"
               "第6球 1 个，合计 6 个；回测统计每期中几个、能否中 3 个。")

    data = _load_index6(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p for p, _ in data]
    n = len(data)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _win = st.selectbox("滚动窗口（热号）", [50, 100, 200, 500],
                            index=1, key="lab_h_win")
    with c2:
        _start_p = st.selectbox("回测起始期", list(reversed(periods)),
                                index=min(299, len(periods) - 1),
                                key="lab_h_start")
    with c3:
        _end_p = st.selectbox("回测结束期", list(reversed(periods)), index=0,
                              key="lab_h_end")
    with c4:
        _need = st.number_input("目标命中个数", 1, 4, 3, 1, key="lab_h_need")

    _PLAN = {
        "4码：第1球2个 + 第6球2个": {1: 2, 6: 2},
        "5码：第1球2 + 第2球1 + 第6球2": {1: 2, 2: 1, 6: 2},
        "6码：第1球1 + 第2球2 + 第5球2 + 第6球1": {1: 1, 2: 2, 5: 2, 6: 1},
        "7码：第1球2 + 第2球2 + 第5球2 + 第6球1": {1: 2, 2: 2, 5: 2, 6: 1},
        "8码：第1球2 + 第2球2 + 第5球2 + 第6球2": {1: 2, 2: 2, 5: 2, 6: 2},
    }
    _pk = st.selectbox("号码方案", list(_PLAN.keys()), index=2,
                       key="lab_h_plan")
    ALLOC = _PLAN[_pk]
    _tote = sum(ALLOC.values())
    from math import comb as _cb
    st.caption("号码分配：" + "　".join(f"第{k}球 {v} 个"
                                       for k, v in ALLOC.items())
               + f"　（合计 {_tote} 个，复式 {_cb(_tote, 3)} 组/期）")

    if not st.button("▶ 运行实验 H", key="lab_h_run"):
        return

    from collections import Counter
    seqs = {b: [d[1][b - 1] for d in data] for b in range(1, 8)}
    _i1 = periods.index(_start_p)
    _i2 = periods.index(_end_p)
    if _i1 > _i2:
        _i1, _i2 = _i2, _i1
    start = max(int(_win), _i1)
    end = min(n, _i2 + 1)

    rows = []
    dist = Counter()
    ge = 0
    tot = 0
    _last_hit = None
    for i in range(start, end):
        _picks = set()
        _pk_desc = []
        for b, k in ALLOC.items():
            c = Counter(seqs[b][max(0, i - int(_win)):i])
            pick = [v for v, _ in c.most_common(k)]
            _picks.update(pick)
            _pk_desc.append(f"第{b}球 " + "/".join(f"{v:02d}" for v in pick))
        _draw6 = set(data[i][1][:6])          # 只用 6 平码，特码不计
        ok_cnt = len(_picks & _draw6)
        tot += 1
        dist[ok_cnt] += 1
        if ok_cnt >= int(_need):
            ge += 1
        _hit = ok_cnt >= int(_need)
        _gap = (i - _last_hit) if _last_hit is not None else None
        if _hit:
            _last_hit = i
        rows.append({
            "期号": periods[i],
            "年份": periods[i][:4],
            "推荐号码": "　".join(_pk_desc),
            "开奖平码": " ".join(f"{v:02d}" for v in sorted(_draw6)),
            "命中个数": ok_cnt,
            "距上次中奖": _gap if _gap is not None else "—",
            "达标": "★" if _hit else "",
        })

    if not tot:
        st.warning("样本不足")
        return

    st.metric(f"中 {int(_need)} 个及以上的概率", f"{ge/tot*100:.1f}%",
              f"{ge}/{tot} 期")
    st.metric("平均每期中几个",
              f"{sum(k*v for k, v in dist.items())/tot:.2f} 个",
              f"目标 {int(_need)} 个")

    st.markdown("**命中个数分布**")
    st.dataframe(pd.DataFrame(
        [{"命中个数": k, "期数": v, "占比": f"{v/tot*100:.1f}%"}
         for k, v in sorted(dist.items())]),
        use_container_width=True, hide_index=True)

    rows = list(reversed(rows))
    _df = pd.DataFrame(rows)

    def _hl(row):
        if row["达标"]:
            return ["background-color:#ffe08a;font-weight:bold"] * len(row)
        return [""] * len(row)

    st.markdown("**回测明细（最新在上，★=达标）**")
    st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                 hide_index=True, height=380)
    # 年度汇总
    _hits_by_year = Counter(r["年份"] for r in rows if r["达标"])
    _cnt_by_year = Counter(r["年份"] for r in rows)
    if _hits_by_year:
        st.markdown("**各年中奖次数**")
        st.dataframe(pd.DataFrame(
            [{"年份": y, "期数": _cnt_by_year[y], "中奖": _hits_by_year.get(y, 0)}
             for y in sorted(_cnt_by_year, reverse=True)]),
            use_container_width=True, hide_index=True)
    else:
        st.info("该区间内没有中奖记录")

    # 中奖间隔
    _gaps = [r["距上次中奖"] for r in rows
             if r["达标"] and isinstance(r["距上次中奖"], int)]
    if _gaps:
        _gaps_sorted = sorted(_gaps)
        st.caption(
            f"中奖间隔：共 {len(_gaps)} 次｜最短 {min(_gaps)} 期｜"
            f"中位 {_gaps_sorted[len(_gaps_sorted)//2]} 期｜"
            f"最长 {max(_gaps)} 期")

    st.download_button("📥 下载明细",
                       _df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"实验H_6码_{periods[start]}_{periods[end-1]}.csv",
                       mime="text/csv", key="lab_h_dl")

    # ---- 多种 6 码分配对比 ----
    st.markdown("**📊 6 码不同分配方式对比（同区间）**")
    strats = [("单押第1球 6个", {1: 6}, 1), ("单押第6球 6个", {6: 6}, 1),
              ("单押第5球 6个", {5: 6}, 1), ("单押第2球 6个", {2: 6}, 1),
              ("1球1+2球2+5球2+6球1", ALLOC, 3),
              ("1球2+2球2+6球2", {1: 2, 2: 2, 6: 2}, 3),
              ("五个球各1个", {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}, 1)]
    _rows_cmp = []
    for _name, _alloc, _need2 in strats:
        _ok = _tot = 0
        _sub = list(_alloc.items())
        for i2 in range(start, end):
            _ps = set()
            for b, k in _sub:
                cc = Counter(seqs[b][max(0, i2 - int(_win)):i2])
                _ps.update(v for v, _ in cc.most_common(k))
            _c2 = len(_ps & set(data[i2][1][:6]))
            _tot += 1
            if _c2 >= _need2:
                _ok += 1
        _rows_cmp.append({"分配方式": _name,
                          "号码数": sum(v for v in _alloc.values()),
                          "达标条件": f"中{_need2}个",
                          "达标率": f"{_ok/_tot*100:.1f}%",
                          "期数": f"{_ok}/{_tot}"})
    st.dataframe(pd.DataFrame(_rows_cmp), use_container_width=True,
                 hide_index=True)
    st.caption("单押一个球位 6 个号，达标率明显更高；分散押 3 个球几乎不可能。")

    # ---- 全量测算（复式口径）----
    st.markdown("**📜 全量测算（6 码复式 = 20 组/期）**")
    _c1h, _c2h = st.columns(2)
    with _c1h:
        _po = st.number_input("中奖赔率（倍）", 1, 100000, 655, 1,
                              key="lab_h_payout")
    with _c2h:
        _era = st.selectbox("统计起点", ["1976", "2005", "2015"], index=0,
                            key="lab_h_era")
    st.caption("判定口径：只比 6 个平码，特码不计入")

    _dist = Counter()
    _groups = 0
    _tot2 = 0
    _cost = 0
    _win2 = int(_win) if int(_win) > 0 else 0
    _c = {b: Counter() for b in ALLOC}
    for i in range(300, len(periods)):
        if _win2:
            for b in ALLOC:
                if i - _win2 - 1 >= 0:
                    _old = seqs[b][i - _win2 - 1]
                    _c[b][_old] -= 1
                    if _c[b][_old] <= 0:
                        del _c[b][_old]
        if periods[i][:4] >= _era:
            _picks = set()
            for b, k in ALLOC.items():
                _picks.update(v for v, _ in _c[b].most_common(k))
            _draws = set(data[i][1][:6])
            _k = len(_picks & _draws)
            _dist[_k] += 1
            _tot2 += 1
            _cost += comb(len(_picks), 3) if len(_picks) >= 3 else 0
            if _k >= 3:
                _groups += comb(_k, 3)
        for b in ALLOC:
            _c[b][seqs[b][i]] += 1

    from math import comb as _comb
    st.dataframe(pd.DataFrame(
        [{"命中个数": k, "期数": v, "占比": f"{v/_tot2*100:.2f}%"}
         for k, v in sorted(_dist.items())]),
        use_container_width=True, hide_index=True)

    _n3 = _dist.get(3, 0)
    _n4 = _dist.get(4, 0)
    _n5 = _dist.get(5, 0)
    _back = _groups * int(_po)
    st.markdown(
        f"- 统计：{_era} 年起，共 **{_tot2}** 期｜每期 20 组（6 码复式）\n"
        f"- 中 3 个：**{_n3}** 期｜中 4 个：**{_n4}** 期｜"
        f"中 5 个：**{_n5}** 期\n"
        f"- 折合中奖组数：**{_groups}** 组"
        f"（中4=4组、中5=10组）\n"
        f"- 总投入 **{_cost}** 组｜按 {int(_po)} 倍回收 **{_back}** 组\n"
        f"- **回报率 {_back/max(1,_cost)*100:.1f}%**｜"
        f"回本需 **{_cost/max(1,_groups):.0f}** 倍")

    # 下一期推荐
    st.markdown(f"**下一期推荐（6 个号，窗口 {int(_win)} 期）**")
    _next = []
    for b, k in ALLOC.items():
        c = Counter(seqs[b][-int(_win):])
        pick = [v for v, _ in c.most_common(k)]
        _next.append(f"第{b}球：" + "、".join(f"{v:02d}" for v in pick))
    st.success("　".join(_next))


# =====================================================================
# 实验 I：递增加注模拟
# =====================================================================
def _exp_stake_plan(loader):
    from math import comb
    from collections import Counter

    st.markdown("#### 实验 I：递增加注模拟")
    st.caption("中奖后归零重新计数；连续未中达到起点后，每 N 期加注一档。")

    data = _load_index6(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p for p, _ in data]
    n = len(data)

    _PLAN = {
        "4码：第1球2 + 第6球2": {1: 2, 6: 2},
        "5码：第1球2 + 第2球1 + 第6球2": {1: 2, 2: 1, 6: 2},
        "6码：第1球1 + 第2球2 + 第5球2 + 第6球1": {1: 1, 2: 2, 5: 2, 6: 1},
    }

    # ---- 锁定状态 ----
    import json as _json
    _LOCK_FILE = "stake_plan_lock.json"
    _lock = None
    try:
        _raw = loader.get("gh_read")
        if _raw:
            _txt = _raw(_LOCK_FILE)
            if _txt:
                _lock = _json.loads(_txt)
    except Exception:
        _lock = None

    if _lock:
        st.success(
            f"🔒 已锁定方案（{_lock.get('locked_at', '')} 锁定）："
            f"{_lock.get('plan', '')}｜窗口 {_lock.get('win', '')} 期｜"
            f"推荐号码：{'、'.join('%02d' % v for v in _lock.get('picks', []))}")
        _c1l, _c2l = st.columns(2)
        with _c1l:
            if st.button("🔓 解锁方案", key="lab_i_unlock"):
                try:
                    loader["gh_write"](_LOCK_FILE, "{}", "解锁加注方案")
                except Exception:
                    pass
                st.warning("已解锁，请刷新页面")
                st.rerun()
        with _c2l:
            st.caption("解锁后可以换方案；未中奖前不建议解锁")

    # ---- 第一行：方案 + 赔率 ----
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        _pk = st.selectbox("号码方案", list(_PLAN.keys()), index=0,
                           key="lab_i_plan")
    with r1c2:
        _odds = st.number_input("中奖赔率（倍）", 1, 100000, 655, 1,
                                key="lab_i_odds")

    # ---- 第二行：起点 + 递增间隔 ----
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        _start_at = st.number_input("连续多少期开始下注", 1, 2000, 150, 10,
                                    key="lab_i_start")
    with r2c2:
        _step = st.number_input("每隔多少期加注一次", 5, 500, 50, 5,
                                key="lab_i_step")

    # ---- 第三行：递增比例 + 加注上限 ----
    r3c1, r3c2 = st.columns(2)
    with r3c1:
        _inc = st.number_input("每次加注比例（%）", 0, 500, 20, 5,
                               key="lab_i_inc")
    with r3c2:
        _cap = st.number_input("加注上限（倍）", 1, 1000, 10, 1,
                               key="lab_i_cap")

    # ---- 第四行：本金 + 统计起点 ----
    r4c1, r4c2 = st.columns(2)
    with r4c1:
        _bank0 = st.number_input("本金（元）", 1000, 100000000, 100000, 1000,
                                 key="lab_i_bank")
    with r4c2:
        _era = st.selectbox("统计起点", ["1976", "2005", "2015"], index=0,
                            key="lab_i_era")

    # ---- 第五行：滚动窗口 + 执行 ----
    st.caption("热号计算方式")
    _allw = st.checkbox("用全部历史（不滚动）", value=False, key="lab_i_allw")
    _win = st.slider("滚动窗口（期）", 20, 500, 100, 10, key="lab_i_win")
    if _allw:
        st.warning("当前是「全部历史」模式：推荐号码会长期恒定不变")
    else:
        st.info(f"当前是「滚动 {int(_win)} 期」模式：推荐号码会随期变化")
    _go = st.button("▶ 运行加注模拟", type="primary", key="lab_i_run")
    if st.button("🔒 锁定当前方案（长期跟踪用）", key="lab_i_lock"):
        _cur = set()
        for b, k in _PLAN[_pk].items():
            _c2 = [v for v, _ in Counter(
                [d[1][b - 1] for d in data[-int(_win):]]).most_common(k)]
            _cur.update(_c2)
        _obj = {"plan": _pk, "win": int(_win), "allw": bool(_allw),
                "era": _era, "start_at": int(_start_at), "step": int(_step),
                "inc": int(_inc), "cap": int(_cap), "odds": int(_odds),
                "picks": sorted(_cur), "locked_at": periods[-1]}
        try:
            loader["gh_write"](_LOCK_FILE,
                               _json.dumps(_obj, ensure_ascii=False),
                               "锁定加注方案")
            st.success("已锁定：" + "、".join("%02d" % v for v in sorted(_cur)))
            st.rerun()
        except Exception as _e:
            st.warning(f"锁定失败：{_e}")

    if not _go:
        return

    ALLOC = _PLAN[_pk]
    seqs = {b: [d[1][b - 1] for d in data] for b in ALLOC}

    # 锁定方案时，推荐号码固定为锁定时的那一组
    _locked_picks = None
    if _lock:
        try:
            _locked_picks = [int(x) for x in _lock.get("picks", [])]
        except Exception:
            _locked_picks = None
    draws = [set(d[1][:6]) for d in data]

    c = {b: Counter() for b in ALLOC}
    gap = 0
    mult = 1.0
    spent = back = 0.0
    bank = float(_bank0)
    peak = bank
    max_dd = 0.0
    max_mult = 1.0
    hits = 0
    ruin_at = None
    gaps = []
    rows = []

    _w = 0 if _allw else int(_win)
    for i in range(max(1, int(_win)), n):
        if periods[i][:4] >= _era:
            if _locked_picks:
                picks = set(_locked_picks)
            else:
                picks = set()
                for b, k in ALLOC.items():
                    picks.update(v for v, _ in c[b].most_common(k))
            groups = comb(len(picks), 3)
            cost = groups * mult
            spent += cost
            bank -= cost
            k2 = len(picks & draws[i])
            if k2 >= 3:
                win = comb(k2, 3) * _odds * mult
                back += win
                bank += win
                hits += 1
                gaps.append(gap)
                rows.append({"期号": periods[i],
                             "推荐号码": " ".join(f"{v:02d}" for v in sorted(picks)),
                             "倍数": f"{mult:.2f}",
                             "投入": f"{cost:.0f}", "命中": k2,
                             "回收": f"{win:.0f}", "资金": f"{bank:.0f}",
                             "结果": "★中奖"})
                gap = 0
                mult = 1.0
            else:
                gap += 1
                if gap >= int(_start_at):
                    mult = min(1.0 * (1 + _inc / 100) **
                               ((gap - int(_start_at)) // int(_step) + 1),
                               float(_cap))
                    max_mult = max(max_mult, mult)
                if gap == int(_start_at):
                    rows.append({"期号": periods[i],
                                 "推荐号码": " ".join(f"{v:02d}" for v in sorted(picks)),
                                 "倍数": "1.00",
                                 "投入": "—", "命中": 0, "回收": "—",
                                 "资金": f"{bank:.0f}", "结果": "开始下注"})
            peak = max(peak, bank)
            max_dd = max(max_dd, peak - bank)
            if bank <= 0 and ruin_at is None:
                ruin_at = periods[i]
        for b in ALLOC:
            c[b][seqs[b][i]] += 1
            if _w and i - _w >= 0:
                _oldv = seqs[b][i - _w]
                c[b][_oldv] -= 1
                if c[b][_oldv] <= 0:
                    del c[b][_oldv]

    roi = (back / spent * 100) if spent else 0
    st.markdown("**模拟结果**")
    _m1, _m2, _m3 = st.columns(3)
    _m1.metric("中奖次数", hits)
    _m2.metric("回报率", f"{roi:.1f}%")
    _m3.metric("期末资金", f"{bank:,.0f}")

    _m4, _m5, _m6 = st.columns(3)
    _m4.metric("总投入", f"{spent:,.0f}")
    _m5.metric("最高加注", f"{max_mult:.1f} 倍")
    _m6.metric("最大回撤", f"{max_dd:,.0f}")

    if ruin_at:
        st.error(f"❌ 资金在中途耗尽：{ruin_at} 期（本金 {_bank0:,}）")
    else:
        st.success("✅ 全程未爆仓")

    if gaps:
        st.caption(f"中奖间隔：{len(gaps)} 次｜最短 {min(gaps)} 期｜"
                   f"中位 {sorted(gaps)[len(gaps)//2]} 期｜最长 {max(gaps)} 期")

    # 每期推荐（全部期数）
    _all_rows = []
    _cc = {b: Counter() for b in ALLOC}
    for i in range(len(periods)):
        if i >= 1:
            _ps = set()
            for b, k in ALLOC.items():
                _ps.update(v for v, _ in _cc[b].most_common(k))
            _all_rows.append({"期号": periods[i],
                              "推荐号码": " ".join(f"{v:02d}" for v in sorted(_ps))})
        for b in ALLOC:
            _cc[b][seqs[b][i]] += 1
            if not _allw and i - int(_win) >= 0:
                _ov = seqs[b][i - int(_win)]
                _cc[b][_ov] -= 1
                if _cc[b][_ov] <= 0:
                    del _cc[b][_ov]

    st.markdown("**每期推荐号码（最近 100 期，最新在上）**")
    _show = list(reversed(_all_rows))[:100]
    st.dataframe(pd.DataFrame(_show), use_container_width=True,
                 hide_index=True, height=300)
    st.download_button("📥 下载全部期数的推荐号码",
                       pd.DataFrame(list(reversed(_all_rows))).to_csv(
                           index=False).encode("utf-8-sig"),
                       file_name="每期推荐号码.csv", mime="text/csv",
                       key="lab_i_allcsv")

    # 下一期推荐
    st.markdown("**下一期推荐号码**")
    if _locked_picks:
        _np = set(_locked_picks)
    else:
        _np = set()
        for b, k in ALLOC.items():
            _np.update(v for v, _ in c[b].most_common(k))
    _np_list = sorted(_np)
    _cur_gap = gap
    _cur_mult = mult
    st.success("　".join(f"{v:02d}" for v in _np_list) +
               f"　（共 {len(_np_list)} 个号，复式 {comb(len(_np_list), 3)} 组）")
    st.caption(f"当前连续未中：{_cur_gap} 期｜下一次下注倍数：{_cur_mult:.2f} 倍"
               + ("（已进入下注区间）" if _cur_gap >= int(_start_at) else
                  f"（还差 {int(_start_at) - _cur_gap} 期开始下注）"))

    if rows:
        _df = pd.DataFrame(list(reversed(rows)))

        def _hl(row):
            if row["结果"] == "★中奖":
                return ["background-color:#ffe08a;font-weight:bold"] * len(row)
            return [""] * len(row)

        st.markdown("**关键节点（最新在上）**")
        st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                     hide_index=True, height=360)


# =====================================================================
# 实验 J：多维属性杀号排行
# =====================================================================
def _load_attr_map(loader):
    key = "_lab_amap"
    if key in st.session_state:
        return st.session_state[key]
    out = {}
    try:
        rows = _as_rows(loader["load_excel_data"]("_attr_map.csv", None))
        if rows:
            head = [str(h).strip() for h in rows[0]]
            for r in rows[1:]:
                if not r or not str(r[0]).strip():
                    continue
                try:
                    n = int(float(r[0]))
                except Exception:
                    continue
                out[n] = {head[i]: (str(r[i]).strip() if i < len(r) else "")
                          for i in range(len(head))}
                # 数字合一律按各位相加重算（CSV 有错，如 22 被写成 05合）
                out[n]["数字合"] = f"{sum(int(c) for c in str(n)):02d}合"
    except Exception:
        out = {}
    st.session_state[key] = out
    return out


def _exp_kill_rank(loader):
    from collections import Counter as _C
    st.markdown("#### 实验 J：多维属性杀号排行")
    st.caption("统计每个属性「最热取值」的再出率，杀号率 = 1 − 再出率；"
               "再按交叉杀号后的剩余号码做回测。")

    data = _load_index6(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    amap = _load_attr_map(loader)
    periods = [p2 for p2, _ in data]
    n = len(data)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ball = st.selectbox("球位", list(range(1, 7)), index=0, key="lab_j_ball")
    with c2:
        win = st.selectbox("观察窗口", [50, 100, 200], index=1, key="lab_j_win")
    with c3:
        topk = st.number_input("交叉杀号个数", 1, 8, 3, 1, key="lab_j_k")
    with c4:
        bt = st.number_input("回测期数", 50, 2000, 300, 50, key="lab_j_bt")

    if not st.button("▶ 运行实验 J", key="lab_j_run"):
        return

    def val_of(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        if key == "单双":
            return "单" if num % 2 else "双"
        if key == "大小":
            return "大" if num >= 25 else "小"
        return amap.get(num, {}).get(key, "")

    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿", "大小肖",
             "阴阳天地", "生肖五行", "波色", "3模", "单双", "门数", "段数"]
    seqs = {k: [val_of(d[1][ball - 1], k) for d in data] for k in ATTRS}

    start = max(win, n - int(bt))
    # 属性维度统计
    stat = {k: {"trig": 0, "kill": 0} for k in ATTRS}
    cross_ok = 0
    cross_tot = 0
    remain_sum = 0
    for i in range(start, n):
        actual = data[i][1][ball - 1]
        kills = []
        for k in ATTRS:
            seq = seqs[k]
            c = _C(x for x in seq[i - win:i] if x)
            if not c:
                continue
            v, cnt = c.most_common(1)[0]
            if cnt < 10 or not v:
                continue
            stat[k]["trig"] += 1
            if val_of(actual, k) != v:
                stat[k]["kill"] += 1
            kills.append((k, v, cnt))
        # 交叉杀：按历史再出率最低（此处用计数占比近似）排序取 topk
        kills.sort(key=lambda x: -(x[2]))
        use = kills[:int(topk)]
        dead_vals = {(k, v) for k, v, _ in use}
        remain = [num for num in range(1, 50)
                  if not any(val_of(num, k) == v for k, v in dead_vals)]
        cross_tot += 1
        remain_sum += len(remain)
        if actual in remain:
            cross_ok += 1

    rows = []
    for k in ATTRS:
        tr = stat[k]["trig"]
        if tr < 20:
            continue
        rate = stat[k]["kill"] / tr
        rows.append({"属性": k, "触发期数": tr,
                     "杀中": stat[k]["kill"],
                     "杀号率": f"{rate*100:.1f}%"})
    rows.sort(key=lambda x: -float(x["杀号率"].rstrip("%")))
    st.markdown("**单属性杀号排行（杀最热取值）**")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown(f"**交叉杀 {int(topk)} 个属性后的效果**")
    st.metric("实际号码仍存活的概率",
              f"{cross_ok/max(1,cross_tot)*100:.1f}%",
              f"{cross_ok}/{cross_tot} 期")
    st.metric("平均剩余号码数", f"{remain_sum/max(1,cross_tot):.1f} 个")
    st.caption("说明：存活概率越低，说明杀得越狠但越容易误杀；"
               "理想是剩余号码少、存活概率仍高。")


# =====================================================================
# 实验 K：追热 / 追冷 对比回测
# =====================================================================
def _exp_hot_cold(loader):
    from collections import Counter as _C, defaultdict as _dd
    st.markdown("#### 实验 K：追热 vs 追冷（分球位回测）")
    st.caption("规则：取目标期该球属性值 → 找历史上同值的期（匹配行）→ "
               "看这些期的下一期该球属性值分布 → 追热取最多、追冷取最少。")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)

    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿",
             "生肖五行", "阴阳天地", "3模", "波色", "单双", "门数", "段数"]

    def val_of(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        if key == "单双":
            return "单" if num % 2 else "双"
        return amap.get(num, {}).get(key, "")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        attr = st.selectbox("属性", ATTRS, index=0, key="lab_k_attr")
    with c2:
        need = st.number_input("最少匹配行数", 1, 20, 3, 1, key="lab_k_need")
    with c3:
        _st_p = st.selectbox("起始期", list(reversed(periods)),
                             index=min(299, len(periods) - 1),
                             key="lab_k_start")
    _c5 = st.columns(2)
    with _c5[0]:
        _en_p = st.selectbox("结束期", list(reversed(periods)), index=0,
                             key="lab_k_end")
    with c4:
        ball0 = st.selectbox("基准球位", list(range(1, 7)), index=0,
                             key="lab_k_ball")

    if not st.button("▶ 运行实验 K", key="lab_k_run"):
        return

    vals = {}
    for b in range(1, 7):
        vals[b] = [val_of(d[1][b - 1], attr) for d in data]

    _i1 = periods.index(_st_p)
    _i2 = periods.index(_en_p)
    if _i1 > _i2:
        _i1, _i2 = _i2, _i1
    start = max(50, _i1)
    end_i = min(n - 1, _i2)
    st.caption(f"回测区间：{periods[start]} ~ {periods[end_i]}（{end_i - start + 1} 期）")
    rows = []
    per_ball = {b: {"hot": [0, 0], "cold": [0, 0]} for b in range(1, 7)}
    detail = []

    # 逐球独立回测
    for b in range(1, 7):
        seq = vals[b]
        universe = sorted({v for v in seq if v})
        idx = _dd(_C)          # 值 -> 下一期值计数
        seen = _C()            # 值 -> 匹配行数
        for i in range(1, end_i):
            idx[seq[i - 1]][seq[i]] += 1
            seen[seq[i - 1]] += 1
            if i < start or i > end_i - 1:
                continue
            v = seq[i]
            cnt = seen.get(v, 0)
            if cnt < int(need):
                continue
            mc = idx.get(v)
            if not mc:
                continue
            hot = mc.most_common(1)[0][0]
            cold = None
            best = None
            for u in universe:
                c = mc.get(u, 0)
                if best is None or c < best:
                    best, cold = c, u
            actual = seq[i + 1]
            per_ball[b]["hot"][0] += 1
            per_ball[b]["hot"][1] += 1 if actual == hot else 0
            per_ball[b]["cold"][0] += 1
            per_ball[b]["cold"][1] += 1 if actual == cold else 0
            if b == int(ball0):
                detail.append({"期号": periods[i + 1], "上期值": v,
                               "匹配行": cnt, "追热": hot, "追冷": cold,
                               "实开": actual,
                               "热中": "★" if actual == hot else "",
                               "冷中": "★" if actual == cold else ""})

    st.markdown("**各球位命中率对比**")
    trows = []
    for b in range(1, 7):
        h = per_ball[b]["hot"]
        c = per_ball[b]["cold"]
        trows.append({
            "球位": f"第{b}球",
            "追热期数": h[0], "追热命中": h[1],
            "追热命中率": f"{h[1]/max(1,h[0])*100:.1f}%",
            "追冷期数": c[0], "追冷命中": c[1],
            "追冷命中率": f"{c[1]/max(1,c[0])*100:.1f}%",
        })
    st.dataframe(pd.DataFrame(trows), use_container_width=True,
                 hide_index=True)

    _h = per_ball[int(ball0)]["hot"]
    _c = per_ball[int(ball0)]["cold"]
    st.markdown(f"**基准球位：第{ball0}球**")
    _m1, _m2, _m3 = st.columns(3)
    _m1.metric("追热命中率", f"{_h[1]/max(1,_h[0])*100:.1f}%",
               f"{_h[1]}/{_h[0]} 期")
    _m2.metric("追冷命中率", f"{_c[1]/max(1,_c[0])*100:.1f}%",
               f"{_c[1]}/{_c[0]} 期")
    _m3.metric("属性取值数", len({v for v in vals[int(ball0)] if v}))

    if detail:
        _df = pd.DataFrame(list(reversed(detail)))

        def _hl(row):
            if row["热中"] or row["冷中"]:
                return ["background-color:#ffe08a"] * len(row)
            return [""] * len(row)

        st.dataframe(_df.style.apply(_hl, axis=1), use_container_width=True,
                     hide_index=True, height=360)
        st.download_button("📥 下载明细",
                           _df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"实验K_{attr}_第{ball0}球.csv",
                           mime="text/csv", key="lab_k_dl")
    st.markdown("---")
    st.markdown(f"**下一期（{periods[-1]} 之后）第{ball0}球预测**")
    _seq = vals[int(ball0)]
    _last = len(_seq) - 1
    _v = _seq[_last]
    _mc = _dd(_C)
    _rows_n = 0
    _det = []
    for _i in range(_last):
        if _seq[_i] == _v:
            _rows_n += 1
            _nx = _seq[_i + 1]
            _mc[_nx] += 1
            _det.append({"触发期": periods[_i], "下一期": periods[_i + 1],
                         f"下一期第{ball0}球{attr}": _nx})
    if not _mc or _rows_n < 1:
        st.info(f"历史中没有「{_v}」的记录，无法给出预测")
    else:
        _hot = _mc.most_common(1)[0][0]
        _uni = sorted({x for x in _seq if x})
        _cold = min(_uni, key=lambda u: _mc.get(u, 0))
        _lo, _hi = int(ball0), 43 + int(ball0)
        _nums_hot = [x for x in range(_lo, _hi + 1)
                     if amap.get(x, {}).get(attr, "") == _hot]
        _nums_cold = [x for x in range(_lo, _hi + 1)
                      if amap.get(x, {}).get(attr, "") == _cold]
        st.markdown(f"- 最新一期（{periods[-1]}）第{ball0}球 = **{_v}**")
        st.markdown(f"- 历史上同值出现 **{_rows_n}** 次")
        _dist = "、".join(f"{k}（{v}次）" for k, v in _mc.most_common())
        st.markdown(f"- 这些期的下一期分别是：{_dist}")
        st.success(f"追热 → **{_hot}**：重点号码 "
                   + "、".join(str(x) for x in _nums_hot))
        st.warning(f"追冷 → **{_cold}**（历史最少出现）："
                   f"可考虑回避 " + "、".join(str(x) for x in _nums_cold))
        with st.expander(f"🔍 这 {_rows_n} 期的明细", expanded=False):
            st.dataframe(pd.DataFrame(_det), use_container_width=True,
                         hide_index=True)
    st.caption("说明：追热=历史上这些期的下一期最常出现的值；"
               "追冷=最少出现的值。号码区间按球位自动限定。")

    st.caption("提示：命中率高不代表能盈利，还要看与「随机取值」基线比较；"
               "追热命中率若低于 1/取值数，说明该属性无规律。")
    st.markdown("**跨球位对照（用 A 球的匹配规律预测 B 球）**")
    if st.button("▶ 运行跨球对照", key="lab_k_cross"):
        _seqs = vals
        _mat = []
        for _b0 in range(1, 7):
            _row = {"规律来源": f"第{_b0}球"}
            for _b1 in range(1, 7):
                _s0 = _seqs[_b0]
                _s1 = _seqs[_b1]
                _idx = _dd(_C)
                _seen = _C()
                _ok = _tot2 = 0
                for _i in range(1, n - 1):
                    _idx[_s0[_i - 1]][_s1[_i]] += 1
                    _seen[_s0[_i - 1]] += 1
                    if _i < start:
                        continue
                    _v = _s0[_i]
                    if _seen.get(_v, 0) < int(need):
                        continue
                    _mc = _idx.get(_v)
                    if not _mc:
                        continue
                    _pred = _mc.most_common(1)[0][0]
                    _tot2 += 1
                    if _s1[_i + 1] == _pred:
                        _ok += 1
                _row[f"第{_b1}球"] = (f"{_ok/_tot2*100:.1f}%"
                                      if _tot2 else "—")
            _mat.append(_row)
        st.dataframe(pd.DataFrame(_mat), use_container_width=True,
                     hide_index=True)
        st.caption("行 = 提供规律（基准列）的球位；列 = 被预测的球位。"
                   "数值为追热命中率，可与你单球回测结果对照。")




# =====================================================================
# 实验 L：简单版（预测 + 回测）
# =====================================================================
def _exp_simple(loader):
    from collections import Counter as _C
    st.markdown("#### 实验 L：单期回测（冷热一眼看清）")
    st.info("选一期 → 看这一期某球属性值 → 找历史上相同的期 → "
            "它们下一期开什么：最多的叫「热」，最少的叫「冷」。")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)
    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿",
             "生肖五行", "阴阳天地", "3模", "波色"]

    def val_of(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        return amap.get(num, {}).get(key, "")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        pick = st.selectbox("选择期号（回测这一期）",
                            list(reversed(periods)), index=0,
                            key="lab_l_period")
    with c2:
        ball = st.selectbox("球位", [1, 2, 3, 4, 5, 6], index=0,
                            key="lab_l_ball")
    with c3:
        attr = st.selectbox("属性", ATTRS, index=0, key="lab_l_attr")
    with c4:
        depth = st.number_input("联动行数（连续几期）", 1, 8, 3, 1,
                                key="lab_l_depth")
    need = 1

    idx = periods.index(pick)
    seq = [val_of(d[1][ball - 1], attr) for d in data]
    v = seq[idx]
    lo, hi = int(ball), 43 + int(ball)

    d = int(depth)
    _strict_l = st.checkbox("严格屏蔽基准行之后的数据（推荐）", value=True,
                            key="lab_l_strict")
    pat = seq[idx - d + 1: idx + 1]
    cnt = _C()
    rows_n = 0
    detail = []
    _lim_l = idx - 1 if _strict_l else idx
    for j in range(d - 1, max(d - 1, _lim_l)):
        if seq[j - d + 1: j + 1] == pat:
            rows_n += 1
            nx = seq[j + 1]
            cnt[nx] += 1
            _seg_p = [periods[j - d + 1 + q] for q in range(d)]
            _seg_v = [seq[j - d + 1 + q] for q in range(d)]
            _seg_n = [data[j - d + 1 + q][1][ball - 1] for q in range(d)]
            detail.append({
                "起 ~ 止": f"{_seg_p[0]} ~ {_seg_p[-1]}",
                "排列(属性)": " → ".join(_seg_v),
                "排列(号码)": " → ".join(str(x) for x in _seg_n),
                f"下一期({periods[j + 1]})": nx,
            })

    st.markdown(f"### 本期：{pick} 期，第{ball}球 {attr} = **{v}**")
    _cur_nums = [data[idx - d + 1 + q][1][ball - 1] for q in range(d)]
    st.caption("本期排列：" + " → ".join(str(x) for x in _cur_nums)
               + f"（{attr}：" + " → ".join(pat) + f"，共 {d} 期）")
    st.markdown(f"历史上连续相同的有 **{rows_n}** 期（要求 ≥{int(need)} 期）")

    if not cnt:
        st.warning("历史上没有可比对的期，无法判断冷热")
        return

    hot, hot_n = cnt.most_common(1)[0]
    uni = sorted({x for x in seq if x})
    cold = min(uni, key=lambda u: cnt.get(u, 0))
    cold_n = cnt.get(cold, 0)

    st.markdown("**这些期的下一期都开了什么：** "
                + "、".join(f"{k}（{vv}次）" for k, vv in cnt.most_common()))

    nums_hot = [x for x in range(lo, hi + 1) if val_of(x, attr) == hot]
    nums_cold = [x for x in range(lo, hi + 1) if val_of(x, attr) == cold]

    st.success(f"🔥 热：{hot}（{hot_n} 次）→ 号码 "
               + "、".join(str(x) for x in nums_hot))
    st.warning(f"❄ 冷：{cold}（{cold_n} 次）→ 号码 "
               + "、".join(str(x) for x in nums_cold))

    # 该期的下一期是否已开
    if idx + 1 < n:
        nxt_period = periods[idx + 1]
        actual = seq[idx + 1]
        st.markdown(f"### 下一期：{nxt_period} 期，第{ball}球 {attr} = "
                    f"**{actual}**")
        hot_hit = actual == hot
        cold_hit = actual == cold
        _m1, _m2, _m3 = st.columns(3)
        _m1.metric("热是否命中", "✅ 命中" if hot_hit else "❌ 未中")
        _m2.metric("冷是否命中", "✅ 命中" if cold_hit else "❌ 未中")
        _m3.metric("该属性取值数", len(uni))
        if hot_hit:
            st.success(f"追热正确：{nxt_period} 开的就是 {hot}")
        elif cold_hit:
            st.info(f"追冷正确：{nxt_period} 开的是最冷的 {cold}")
        else:
            st.error(f"冷热都没中：实际开 {actual}")
        with st.expander("查看这一期的历史触发明细", expanded=False):
            st.dataframe(pd.DataFrame(detail), use_container_width=True,
                         hide_index=True)
    else:
        st.info(f"{pick} 是最新一期，下一期还没开奖")

# =====================================================================
# 实验 M：跨球联动（用 A 球排列预测 B 球）
# =====================================================================
def _exp_cross_ball(loader):
    from collections import Counter as _C
    st.markdown("#### 实验 M：跨球联动（用 A 球的排列，预测 B 球）")
    st.info("看 A 球最近 N 期的属性排列 → 找历史上排列相同的期 → "
            "统计这些期的下一期 B 球开什么 → 最多的热、最少的是冷。")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)
    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿",
             "生肖五行", "阴阳天地", "3模", "波色"]

    def val_of(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        return amap.get(num, {}).get(key, "")

    c1, c2, c3 = st.columns(3)
    with c1:
        pick = st.selectbox("选择期号", list(reversed(periods)), index=0,
                            key="lab_m_period")
    with c2:
        b_src = st.selectbox("A 球（提供排列）", [1, 2, 3, 4, 5, 6],
                             index=0, key="lab_m_src")
    with c3:
        b_tgt = st.selectbox("B 球（被预测）", [1, 2, 3, 4, 5, 6],
                             index=5, key="lab_m_tgt")
    c4, c5 = st.columns(2)
    with c4:
        attr_s = st.selectbox("A 球属性", ATTRS, index=0, key="lab_m_as")
    with c5:
        attr_t = st.selectbox("B 球属性", ATTRS, index=0, key="lab_m_at")
    depth = st.number_input("联动行数（连续几期）", 1, 8, 2, 1,
                            key="lab_m_depth")

    idx = periods.index(pick)
    d = int(depth)
    _strict_m = st.checkbox("严格屏蔽基准行之后的数据（推荐）", value=True,
                            key="lab_m_strict")
    seq_s = [val_of(x[1][b_src - 1], attr_s) for x in data]
    seq_t = [val_of(x[1][b_tgt - 1], attr_t) for x in data]
    pat = seq_s[idx - d + 1: idx + 1]

    cnt = _C()
    rows_n = 0
    detail = []
    _lim_m = idx - 1 if _strict_m else idx
    for j in range(d - 1, max(d - 1, _lim_m)):
        if seq_s[j - d + 1: j + 1] == pat:
            rows_n += 1
            cnt[seq_t[j + 1]] += 1
            detail.append({
                "起 ~ 止": f"{periods[j - d + 1]} ~ {periods[j]}",
                "A球排列": " → ".join(seq_s[j - d + 1: j + 1]),
                f"B球下一期({periods[j + 1]})": seq_t[j + 1],
            })

    st.markdown("### A 球排列：" + " → ".join(pat)
                + f"（{attr_s}，共 {d} 期）")
    st.markdown(f"历史相同排列共 **{rows_n}** 期")
    if not cnt:
        st.warning("历史上没有相同排列，无法预测 B 球")
        return

    hot, hot_n = cnt.most_common(1)[0]
    uni = sorted({x for x in seq_t if x})
    cold = min(uni, key=lambda u: cnt.get(u, 0))
    lo, hi = int(b_tgt), 43 + int(b_tgt)
    nums_hot = [x for x in range(lo, hi + 1) if val_of(x, attr_t) == hot]
    nums_cold = [x for x in range(lo, hi + 1) if val_of(x, attr_t) == cold]

    st.markdown("这些期的下一期，B 球分别开了："
                + "、".join(f"{k}（{v}次）" for k, v in cnt.most_common()))
    st.success(f"🔥 热：{hot}（{hot_n} 次）→ B 球号码 "
               + "、".join(str(x) for x in nums_hot))
    st.warning(f"❄ 冷：{cold}（0 次）→ B 球号码 "
               + "、".join(str(x) for x in nums_cold))

    if idx + 1 < n:
        actual = seq_t[idx + 1]
        st.markdown(f"### 实际：{periods[idx + 1]} 期，B 球 {attr_t} = "
                    f"**{actual}**")
        m1, m2 = st.columns(2)
        m1.metric("热是否命中", "✅ 命中" if actual == hot else "❌ 未中")
        m2.metric("冷是否命中", "✅ 命中" if actual == cold else "❌ 未中")
    else:
        st.info(f"{pick} 是最新一期，下一期还没开")

    with st.expander(f"查看这 {rows_n} 期的明细", expanded=False):
        st.dataframe(pd.DataFrame(detail), use_container_width=True,
                     hide_index=True)

    st.markdown("**6×6 组合命中率（最近 300 期）**")
    if st.button("▶ 计算 6×6", key="lab_m_all"):
        ss = {q: [val_of(x[1][q - 1], attr_s) for x in data]
              for q in range(1, 7)}
        tt = {q: [val_of(x[1][q - 1], attr_t) for x in data]
              for q in range(1, 7)}
        start = max(d, n - 300)
        mat = []
        for _a in range(1, 7):
            row = {"A 球": f"第{_a}球"}
            for _b in range(1, 7):
                s_a, s_b = ss[_a], tt[_b]
                ok = tot = 0
                for i in range(start, end_i):
                    pat2 = s_a[i - d + 1: i + 1]
                    c2 = _C()
                    for j in range(d - 1, i):
                        if s_a[j - d + 1: j + 1] == pat2:
                            c2[s_b[j + 1]] += 1
                    if not c2:
                        continue
                    tot += 1
                    if s_b[i + 1] == c2.most_common(1)[0][0]:
                        ok += 1
                row[f"→第{_b}球"] = f"{ok/tot*100:.0f}%" if tot else "—"
            mat.append(row)
        st.dataframe(pd.DataFrame(mat), use_container_width=True,
                     hide_index=True)


# =====================================================================
# 实验 N：自由组合深度联动
# =====================================================================
def _exp_flex(loader):
    from collections import Counter as _C
    st.markdown("#### 实验 N：自由组合深度联动")
    st.success("回测最优组合：基准=第1球 / 属性=尾数 / 联动 1 行 / 目标=第6球，"
               "追热取 2 个值 → 候选约 10 个，命中率约 28~30%（随机约 20%）")
    st.info("自选基准球位（可多选）+ 自选属性 + 自选联动行数（1~12），"
            "到历史里找完全一致的排列，统计下一期目标球的开出情况，"
            "按次数从多到少排列。")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)
    nball = len(data[0][1])
    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿",
             "生肖五行", "阴阳天地", "3模", "波色", "单双", "门数", "段数"]

    def val_of(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        if key == "单双":
            return "单" if num % 2 else "双"
        if key == "门数":
            return f"{num // 10 + 1}门"
        if key == "段数":
            return f"{(num - 1) // 7 + 1}段"
        return amap.get(num, {}).get(key, "")

    st.markdown("**① 基准设置**")
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        base_balls = st.multiselect(
            "基准球位（可多选，如 1+2 或 1+2+3）",
            list(range(1, nball + 1)),
            default=[1], key="lab_n_balls")
    with c2:
        base_attrs = st.multiselect(
            "基准属性（每个球位都用这些属性）",
            ATTRS, default=["尾数"], key="lab_n_attrs")
    with c3:
        depth = st.number_input("联动行数", 1, 12, 1, 1, key="lab_n_depth")

    st.markdown("**② 预测目标**")
    c4, c5, c6 = st.columns(3)
    with c4:
        tgt_ball = st.selectbox("目标球位", list(range(1, nball + 1)),
                                index=5, key="lab_n_tball")
    with c5:
        tgt_attr = st.selectbox("目标属性", ATTRS, index=0,
                                key="lab_n_tattr")
    with c6:
        pick = st.selectbox("预测期号", list(reversed(periods)), index=0,
                            key="lab_n_period")

    if not base_balls or not base_attrs:
        st.warning("请至少选 1 个基准球位和 1 个基准属性")
        return

    idx = periods.index(pick)
    d = int(depth)
    _strict = st.checkbox("严格屏蔽基准行之后的数据（推荐）", value=True,
                          key="lab_n_strict")

    seqs = {}
    for b in base_balls:
        for a in base_attrs:
            seqs[(b, a)] = [val_of(x[1][b - 1], a) for x in data]
    seq_tgt = [val_of(x[1][tgt_ball - 1], tgt_attr) for x in data]

    def pattern_at(i):
        out = []
        for q in range(d):
            r = i - d + 1 + q
            for b in base_balls:
                for a in base_attrs:
                    out.append(seqs[(b, a)][r])
        return tuple(out)

    pat = pattern_at(idx)
    cnt = _C()
    rows_n = 0
    detail = []
    _lim = idx - 1 if _strict else idx
    for j in range(d - 1, max(d - 1, _lim)):
        if pattern_at(j) == pat:
            rows_n += 1
            nx = seq_tgt[j + 1]
            cnt[nx] += 1
            detail.append({
                "起 ~ 止": f"{periods[j - d + 1]} ~ {periods[j]}",
                "排列": " | ".join(pat[q * len(base_balls) * len(base_attrs)]
                                   for q in range(d)),
                f"下一期({periods[j + 1]})目标球{tgt_ball}": nx,
            })

    st.markdown(f"### 当前排列（{pick} 起，{d} 行）")
    st.caption("基准：" + "、".join(f"第{b}球" for b in base_balls)
               + " ｜ 属性：" + "、".join(base_attrs))
    _show = []
    for q in range(d):
        r = idx - d + 1 + q
        _row = {"第几行": f"第{q+1}行", "期号": periods[r]}
        for b in base_balls:
            for a in base_attrs:
                _row[f"第{b}球{a}"] = seqs[(b, a)][r]
        _show.append(_row)
    st.dataframe(pd.DataFrame(_show), use_container_width=True,
                 hide_index=True)

    st.markdown(f"历史相同排列共 **{rows_n}** 期")
    if not cnt:
        st.warning("历史无相同排列，换少几个基准或减少行数再试")
        return

    hot = cnt.most_common(1)[0][0]
    lo, hi = int(tgt_ball), 43 + int(tgt_ball)
    nums_attr = {}
    for k, v in cnt.most_common():
        nums_attr[k] = [x for x in range(lo, hi + 1) if val_of(x, tgt_attr) == k]

    rows = []
    for k, v in cnt.most_common():
        rows.append({f"目标{tgt_attr}": k, "次数": v,
                     "占比": f"{v/rows_n*100:.1f}%",
                     "对应号码": "、".join(str(x) for x in nums_attr[k])})
    st.markdown(f"**统计：下一期第{tgt_ball}球 {tgt_attr} 分布（多的在上）**")
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True)

    st.success(f"🔥 最多：{hot}（{cnt[hot]} 次）→ 号码 "
               + "、".join(str(x) for x in nums_attr[hot]))

    if idx + 1 < n:
        actual = seq_tgt[idx + 1]
        st.markdown(f"### 实际下一期（{periods[idx + 1]}）："
                    f"第{tgt_ball}球 {tgt_attr} = **{actual}**")
        m1, m2 = st.columns(2)
        m1.metric("最多项是否命中", "✅ 命中" if actual == hot else "❌ 未中")
        m2.metric("实际在统计里排第",
                  f"{[k for k, _ in cnt.most_common()].index(actual)+1} 位"
                  if actual in cnt else "—")
    else:
        st.info(f"{pick} 是最新一期，下一期还没开")

    with st.expander(f"查看这 {rows_n} 期的明细", expanded=False):
        st.dataframe(pd.DataFrame(detail), use_container_width=True,
                     hide_index=True)


    # ---------------- 双模式综合筛选 ----------------
    st.markdown("---")
    st.markdown("### 双模式综合筛选（追热 / 杀冷）")
    mode = st.radio("模式", ["追热（选号）", "杀冷（排除）"],
                    horizontal=True, key="lab_n_mode")
    c7, c8 = st.columns(2)
    with c7:
        kk = st.number_input("每个维度取几个值", 1, 6, 2, 1,
                             key="lab_n_k")
    with c8:
        bt = st.number_input("回测期数", 50, 1000, 200, 50,
                             key="lab_n_bt")

    lo, hi = int(tgt_ball), 43 + int(tgt_ball)

    def dim_predict(b, a, i):
        """用球 b 的属性 a 排列，预测目标球属性分布"""
        s = seqs.get((b, a))
        if s is None:
            s = [val_of(x[1][b - 1], a) for x in data]
            seqs[(b, a)] = s
        pat2 = tuple(s[i - d + 1: i + 1])
        c = _C()
        for j in range(d - 1, i):
            if tuple(s[j - d + 1: j + 1]) == pat2:
                c[seq_tgt[j + 1]] += 1
        return c

    # 当前期筛选
    dims = [(b, a) for b in base_balls for a in base_attrs]
    hot_sets, cold_sets = [], []
    dim_rows = []
    for (b, a) in dims:
        c = dim_predict(b, a, idx)
        if not c:
            continue
        ranked = [k for k, _ in c.most_common()]
        uni2 = sorted({x for x in seq_tgt if x})
        colds = sorted(uni2, key=lambda u: c.get(u, 0))
        htop = ranked[:int(kk)]
        ctop = colds[:int(kk)]
        hn = [x for x in range(lo, hi + 1) if val_of(x, tgt_attr) in htop]
        cn = [x for x in range(lo, hi + 1) if val_of(x, tgt_attr) in ctop]
        hot_sets.append(set(hn))
        cold_sets.append(set(cn))
        dim_rows.append({"维度": f"第{b}球{a}", "热值": "、".join(htop),
                         "热号码数": len(hn), "冷值": "、".join(ctop),
                         "冷号码数": len(cn)})
    if not hot_sets:
        st.warning("没有可用维度")
        return
    st.dataframe(pd.DataFrame(dim_rows), use_container_width=True,
                 hide_index=True)

    allnums = set(range(lo, hi + 1))
    if mode.startswith("追热"):
        final = set.intersection(*hot_sets) if len(hot_sets) > 1 else hot_sets[0]
        if not final:
            final = set.union(*hot_sets)
            st.caption("各维度无交集，已改用并集")
        st.success(f"建议号码（{len(final)} 个）："
                   + "、".join(str(x) for x in sorted(final)))
    else:
        killed = set.union(*cold_sets)
        final = allnums - killed
        st.warning(f"排除号码（{len(killed)} 个）："
                   + "、".join(str(x) for x in sorted(killed)))
        st.success(f"剩余号码（{len(final)} 个）："
                   + "、".join(str(x) for x in sorted(final)))

    # 回测
    if st.button("▶ 回测这套筛选", key="lab_n_bt2"):
        start2 = max(200, n - int(bt))
        ok2 = tot2 = sumcnt = 0
        for i in range(start2, n - 1):
            hs, cs = [], []
            for (b, a) in dims:
                c = dim_predict(b, a, i)
                if not c:
                    continue
                ranked = [k for k, _ in c.most_common()]
                uni2 = sorted({x for x in seq_tgt if x})
                colds = sorted(uni2, key=lambda u: c.get(u, 0))
                hs.append({x for x in range(lo, hi + 1)
                           if val_of(x, tgt_attr) in ranked[:int(kk)]})
                cs.append({x for x in range(lo, hi + 1)
                           if val_of(x, tgt_attr) in colds[:int(kk)]})
            if not hs:
                continue
            if mode.startswith("追热"):
                f2 = (set.intersection(*hs) if len(hs) > 1 else hs[0])
                if not f2:
                    f2 = set.union(*hs)
            else:
                f2 = allnums - set.union(*cs)
            if not f2:
                continue
            tot2 += 1
            sumcnt += len(f2)
            if data[i + 1][1][tgt_ball - 1] in f2:
                ok2 += 1
        if tot2:
            st.metric("命中率", f"{ok2/tot2*100:.1f}%",
                      f"{ok2}/{tot2} 期")
            st.metric("平均候选数", f"{sumcnt/tot2:.1f} 个")


# =====================================================================
# 实验 O：多属性融合评分
# =====================================================================
def _exp_fusion(loader):
    import math as _m
    from collections import Counter as _C, defaultdict as _dd
    st.markdown("#### 实验 O：多属性融合评分（综合选号）")
    with st.expander("📘 计算说明（点开看怎么算的）", expanded=False):
        st.markdown("""
**第一步：取触发排列**
- 用第 1 球每个属性的最近 N 期（联动行数）取值，组成「排列」。
- 例：尾数 3 → 7 → 9（3 行）。

**第二步：找历史相同排列**
- 在历史中找排列完全相同的期（严格模式：只用基准期之前的数据）。

**第三步：统计下一期目标球的属性分布**
- 统计这些期的下一期，目标球（如第 1 球）的属性值出现次数。
- 例：下一期尾数为 4 出现 12 次、5 出现 9 次、9 出现 3 次……

**第四步：换算成概率（拉普拉斯平滑）**
- 概率 =（该值次数 + 0.5）/（总次数 + 0.5 × 取值个数）
- 加 0.5 是为了防止「某值 0 次」时概率为 0，导致整条得分为负无穷。

**第五步：给每个号码打分**
- 对每个候选号码，取它在各属性下的概率。
- 得分 = 各属性概率取对数后相加（ln p1 + ln p2 + ln p3）。
- 概率越高，得分越高（越接近 0）。

**第六步：取前 N 名**
- 按得分从高到低排序，取前 N 个号码作为建议。

**回测怎么算**
- 从历史某期开始，逐期滚动：每期只用「该期之前」的数据算分，取前 N 个。
- 用下一期实际开奖号核对：在候选里 = 命中。
- 随机基线 = N ÷ 该球位的号码个数（第 1 球为 43 个，第 6 球为 49 个）。
- 命中率 − 随机基线 = 真实优势。
""")
    st.info("把多个属性各自的历史匹配结果折算成概率，给每个号码打分，"
            "取分数最高的 N 个。属性越多、方向越一致，号码越集中。")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)
    nball = len(data[0][1])
    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿",
             "生肖五行", "阴阳天地", "3模", "波色", "门数", "段数"]

    def val(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        if key == "门数":
            return f"{num // 10 + 1}门"
        if key == "段数":
            return f"{(num - 1) // 7 + 1}段"
        return amap.get(num, {}).get(key, "")

    c1, c2, c3 = st.columns(3)
    with c1:
        tgt_ball = st.selectbox("目标球位", list(range(1, nball + 1)),
                                index=0, key="lab_o_ball")
    with c2:
        attr_t = st.selectbox("目标属性", ATTRS, index=0, key="lab_o_attr")
    with c3:
        topN = st.number_input("输出号码个数", 3, 20, 6, 1, key="lab_o_n")

    used = st.multiselect("参与融合的属性（越多越集中）",
                          ATTRS, default=["数字合", "尾数", "方位"],
                          key="lab_o_attrs")
    c4, c5 = st.columns(2)
    with c4:
        depth = st.number_input("联动行数", 1, 6, 1, 1, key="lab_o_depth")
    with c5:
        pick = st.selectbox("预测期号（看这一期的下一期）",
                            list(reversed(periods)), index=0,
                            key="lab_o_pick")
    c8, c9 = st.columns(2)
    with c8:
        min_rows = st.number_input("优势期：每属性最少匹配期数（0=不过滤）", 0, 500, 0, 5,
                                   key="lab_o_minrows")
    with c9:
        min_edge = st.number_input("优势期：最高分领先幅度（0=不过滤）",
                                   0.0, 5.0, 0.0, 0.1, key="lab_o_minedge")
    c6, c7 = st.columns(2)
    with c6:
        p_start = st.selectbox("回测起始期", list(reversed(periods)),
                               index=min(1999, len(periods) - 1),
                               key="lab_o_start")
    with c7:
        p_end = st.selectbox("回测结束期", list(reversed(periods)),
                             index=0, key="lab_o_end")

    if not used:
        st.warning("请至少选一个属性")
        return

    d = int(depth)
    lo, hi = int(tgt_ball), 43 + int(tgt_ball)
    tseq = [val(x[1][tgt_ball - 1], attr_t) for x in data]
    uni_t = sorted({x for x in tseq if x})

    # 每个属性维度：用第 1 球该属性的排列做触发
    seqs = {a: [val(x[1][0], a) for x in data] for a in used}

    def scores_at(i, tables):
        sc = {x: 0.0 for x in range(lo, hi + 1)}
        for a in used:
            s = seqs[a]
            if i < d:
                continue
            pat = tuple(s[i - d + 1: i + 1])
            c = tables[a].get(pat)
            if not c:
                continue
            tot = sum(c.values())
            for x in range(lo, hi + 1):
                v = val(x, attr_t)
                p = (c.get(v, 0) + 0.5) / (tot + 0.5 * max(1, len(uni_t)))
                sc[x] += _m.log(p)
        return sc

    st.markdown("**当前期打分结果**")
    tables = {a: _dd(_C) for a in used}
    for i in range(1, n - 1):
        for a in used:
            s = seqs[a]
            if i >= d:
                tables[a][tuple(s[i - d: i])][tseq[i]] += 1
    idx0 = periods.index(pick)
    tables = {a: _dd(_C) for a in used}
    for i in range(1, idx0 + 1):
        for a in used:
            s = seqs[a]
            if i >= d:
                tables[a][tuple(s[i - d: i])][tseq[i]] += 1
    sc = scores_at(idx0, tables)
    ranked = sorted(sc.items(), key=lambda x: -x[1])[:int(topN)]
    st.success(f"建议号码（{len(ranked)} 个）："
               + "、".join(str(x) for x, _ in ranked))
    st.dataframe(pd.DataFrame([{"号码": x, "得分": round(v, 2)}
                               for x, v in ranked]),
                 use_container_width=True, hide_index=True)
    with st.expander("🔍 属性贡献明细（每个属性各自偏向哪些值）",
                     expanded=False):
        _rows_c = []
        for a in used:
            s = seqs[a]
            if idx0 < d:
                continue
            pat = tuple(s[idx0 - d + 1: idx0 + 1])
            c = tables[a].get(pat)
            if not c:
                _rows_c.append({"属性": a, "触发排列": " → ".join(pat),
                                "历史匹配": 0, "最偏向的值": "—"})
                continue
            tot = sum(c.values())
            top3 = c.most_common(3)
            _rows_c.append({
                "属性": a,
                "触发排列": " → ".join(pat),
                "历史匹配": tot,
                "最偏向的值": "、".join(
                    f"{k}({v}次,{v/tot*100:.0f}%)" for k, v in top3),
            })
        st.dataframe(pd.DataFrame(_rows_c), use_container_width=True,
                     hide_index=True)
        st.caption("每个属性独立统计「历史上同排列的下一期」开出什么；"
                   "偏向一致 → 该值得分高；偏向分散 → 该属性作用小。")

    st.caption(f"基于 {pick} 期数据，预测它之后下一期的第{tgt_ball}球 {attr_t}"
               + ("（最新期，下一期未开）" if idx0 == n - 1 else ""))

    if not st.button("▶ 回测融合评分", key="lab_o_run"):
        return

    _s1 = periods.index(p_start)
    _s2 = periods.index(p_end)
    if _s1 > _s2:
        _s1, _s2 = _s2, _s1
    start = max(300, _s1)
    end_i = min(n - 1, _s2)
    st.caption(f"回测区间：{periods[start]} ~ {periods[end_i]}")
    tables = {a: _dd(_C) for a in used}
    ok = tot = cnt = 0
    detail = []
    for i in range(start, n - 1):
        if i >= d:
            for a in used:
                s = seqs[a]
                tables[a][tuple(s[i - d: i])][tseq[i]] += 1
        sc = scores_at(i, tables)
        # 优势期判断：每个维度匹配数 + 最高分相对平均的倍数
        _rows_ok = True
        for a in used:
            s = seqs[a]
            if i < d:
                _rows_ok = False
                break
            c0 = tables[a].get(tuple(s[i - d + 1: i + 1]))
            if not c0 or sum(c0.values()) < int(min_rows):
                _rows_ok = False
                break
        if not _rows_ok:
            continue
        _avg = sum(sc.values()) / len(sc)
        _best = max(sc.values())
        if _avg != 0 and (_best - _avg) < float(min_edge):
            continue
        rk = sorted(sc.items(), key=lambda x: -x[1])[:int(topN)]
        nums = [x for x, _ in rk]
        if not nums:
            continue
        actual = data[i + 1][1][tgt_ball - 1]
        tot += 1
        cnt += len(nums)
        hit = actual in nums
        ok += 1 if hit else 0
        detail.append({"期号": periods[i + 1], "开奖号": actual,
                       "候选": "、".join(str(x) for x in nums),
                       "命中": "★" if hit else ""})

    if not tot:
        st.warning("样本不足")
        return
    rate = ok / tot * 100
    avg = cnt / tot
    base = avg / (hi - lo + 1) * 100
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("命中率", f"{rate:.1f}%", f"{ok}/{tot}")
    m2.metric("平均候选", f"{avg:.1f} 个")
    m3.metric("随机基线", f"{base:.1f}%")
    m4.metric("优势", f"{rate-base:+.1f}")
    st.caption(f"优势期过滤：每属性匹配 ≥{int(min_rows)} 期 且 最高分领先"
               f" ≥{float(min_edge)} → 实际出手 {tot} 期"
               f"（回测区间共 {end_i - start} 期）")
    detail.reverse()
    st.dataframe(pd.DataFrame(detail), use_container_width=True,
                 hide_index=True, height=320)


# =====================================================================
# 说明书
# =====================================================================
_DOCS = {
    "实验B 组合池": {
        "原理": "把每期的开奖号码按组合展开，统计每种组合出现的次数与等待期数，"
                "用于判断哪些组合长期偏热或偏冷。",
        "使用": [
            "1. 选择球位范围与组合个数（如 3 个号）",
            "2. 点运行，得到组合的历史出现次数与当前遗漏",
            "3. 看「遗漏/次数比」：偏高说明等待过久，偏低说明正热",
        ],
        "读结果": "次数多=常见组合；遗漏远超平均=久未出现（可能回补，也可能继续冷）。",
    },
    "实验H 六码中三": {
        "原理": "从候选池里任选 6 个号，统计其中任意 3 个命中的历史概率。"
                "C(6,3)=20 组三中三，用于评估小复式性价比。",
        "使用": [
            "1. 输入或选择 6 个号码",
            "2. 选回测区间",
            "3. 运行后看「三中三」命中次数与频率",
        ],
        "读结果": "理论单组三中三约 0.1086%（1/921）；实际高于此值才算有效。",
    },
    "实验I 加注模拟": {
        "原理": "模拟不同加注方式（平注、倍投、递进）在给定命中率下的资金曲线，"
                "用于评估风险与所需本金。",
        "使用": [
            "1. 设定命中率、赔率、本金、注数",
            "2. 选择加注方式",
            "3. 运行看资金曲线与破产概率",
        ],
        "读结果": "关注最大回撤与破产概率；倍投在低命中率下很快爆仓。",
    },
    "实验J 属性杀号": {
        "原理": "统计每个属性「最热取值」在下一期的再出率，杀号率 = 1 − 再出率。"
                "交叉杀号后统计剩余号码数与实际存活率。",
        "使用": [
            "1. 选球位、观察窗口、交叉个数",
            "2. 运行看单属性杀号排行",
            "3. 看交叉后「剩余号码数」与「存活概率」",
        ],
        "读结果": "取值多的属性（尾数/数字合）杀号率 83~86%；大小、门数不可用来杀。",
    },
    "实验K 追热追冷": {
        "原理": "把某一期的属性值作为触发条件，找历史上同值的期，"
                "统计它们下一期的属性值分布：最多的=热，最少的=冷。",
        "使用": [
            "1. 选属性、最少匹配行数、起止期、基准球位",
            "2. 点运行，看各球位追热/追冷命中率",
            "3. 看最下方「下一期预测」",
        ],
        "读结果": "追热应高于「1/取值数」才有意义；追冷通常低于随机。",
    },
    "实验L 简单版": {
        "原理": "单期回测：取选定期的属性排列（可多行），找历史相同排列，"
                "统计下一期属性值 → 热/冷，并核对实际结果。",
        "使用": [
            "1. 选期号、球位、属性、联动行数",
            "2. 看本期排列与历史匹配数",
            "3. 看热/冷建议与下一期是否命中",
        ],
        "读结果": "匹配期数少于 5 期时，冷热基本是噪声。",
    },
    "实验M 跨球联动": {
        "原理": "用 A 球的排列去触发，统计下一期 B 球的开出情况，"
                "检验「球与球之间是否存在带动关系」。",
        "使用": [
            "1. 选 A 球、B 球、各自属性、联动行数",
            "2. 看 A 球排列、历史匹配与 B 球热/冷",
            "3. 点「▶ 计算 6×6」看全部组合的命中率",
        ],
        "读结果": "6×6 矩阵里明显高于随机的格子，才是可用的跨球关系。",
    },
    "实验N 自由联动": {
        "原理": "自选多个基准球位 + 多个属性 + 1~12 行联动，"
                "到历史找完全一致的排列，统计下一期目标球的属性分布，"
                "提供追热（选号）与杀冷（排除）双模式并回测。",
        "使用": [
            "1. ①基准设置：选球位、属性、联动行数",
            "2. ②预测目标：选目标球位、目标属性、预测期号",
            "3. 看统计表（按次数降序）与热/冷号码",
            "4. 下半部分选模式 → 点「▶ 回测这套筛选」",
        ],
        "读结果": "看「命中率」与「平均候选数」之比：候选 10 个、命中 30% 才算有优势。",
    },
    "实验P 精准选号": {
        "原理": "【目标】不直接预测号码，而是预测该球的「数字合」（1~49 共 11 类，"
                "每类 4~5 个号）。【投票】每个「基准球位+属性」组合各自找历史"
                "相似期，统计下一期目标属性值分布；把各属性值的概率取对数相加"
                "作为得分。【选值】取分数最高的 K 个属性值，对应的号码即建议。"
                "【为何比尾数准】数字合类数少、历史条件分布更集中，投票更一致。"
                "【内测】第1球单球：取 1 值≈2.7 号命中 17.2%（随机 6.2%）；"
                "取 2 值≈5.9 号命中 33.0%（随机 13.4%）；取 3 值≈9.4 号命中 46.6%。"
                "【多球位】1+2、1+2+3、1~6 全融合：号码略减（5.9→5.4），"
                "命中略降（33.0%→32.2%），未见提升。",
        "使用": [
            "1. 选目标球位（默认第1球）、目标属性（默认数字合）",
            "2. 设「取几个属性值」（1~4，2 为平衡点）",
            "3. 基准球位默认只选 1；想压缩号码可多选，但命中会略降",
            "4. 参与融合属性建议：尾数 + 方位 + 四宝",
            "5. 设联动行数、预测期号，点「▶ 回测」看命中率与号码数",
        ],
        "读结果": "看「命中率」与「平均号码数」：取 1 值约 3 个号命中 17%，"
                  "取 2 值约 6 个号命中 33%，比随机高 20 个点左右。",
    },
    "实验O 融合评分": {
        "原理": "【一、属性角色】目标往往是某个球位的属性（如第1球尾数），"
                "参与融合的属性（数字合、方位、四宝…）不是答案，而是"
                "「不同的历史分组方式」：每种分组各自统计一次下一期目标值，"
                "各投一票，票数合并后决定买哪几个号码。"
                "【二、举例】当前第1球 尾数=3、数字合=9、方位=东："
                "历史上尾数=3 的期→下一期尾数 4(6次)/5(3次)/9(2次)；"
                "数字合=9 的期→ 4(9次)/7(4次)/2(2次)；"
                "方位=东 的期→ 4(15次)/6(8次)/8(5次)。"
                "三条线索都指向 4 尾，则 4 尾得分最高。"
                "【三、打分公式】概率 =（次数+0.5）/（总次数+0.5×取值数）；"
                "得分 = ln(数字合概率)+ln(尾数概率)+ln(方位概率)。"
                "【四、实测效果】只用尾数：候选 9.8 个、命中 30.3%、随机 22.3%、优势 +8；"
                "尾数+数字合+方位：候选 6.0 个、命中 27.4%、随机 14.0%、优势 +13.4。"
                "命中略降但候选减半，真实优势翻倍。"
                "【五、精度上限】输出 1 个号命中约 12%、2 个约 16%、"
                "3 个约 18%、6 个约 27%（第1球 43 个号，随机 2.3%）；"
                "越少号码命中越低，这是概率规律，无法强行压缩到 1~2 个还保持高命中。",
        "使用": [
            "1. 选目标球位、目标属性、输出号码个数",
            "2. 勾选参与融合的属性（建议 数字合 + 尾数 + 方位）",
            "3. 设联动行数、预测期号",
            "4. 点「▶ 回测融合评分」，看命中率/候选数/随机基线/优势",
            "5. 展开「🔍 属性贡献明细」，看每个属性偏向哪些值",
        ],
        "读结果": "6 个号命中约 27%（随机 14%）；2 个号约 16%（随机 4.7%）；"
                  "1 个号约 12%（随机 2.3%）。要更高把握就多买几个号。",
    },
}


def _exp_docs():
    st.markdown("#### 说明书（原理 + 使用）")
    st.caption("每个实验都有两段：原理说明「为什么这样算」，"
               "使用说明「怎么点、看哪里、怎么读结果」。")
    for name, d in _DOCS.items():
        with st.expander(f"📘 {name}", expanded=False):
            st.markdown("**原理**")
            st.write(d["原理"])
            st.markdown("**使用步骤**")
            for s in d["使用"]:
                st.write(s)
            st.markdown("**怎么读结果**")
            st.info(d["读结果"])


# =====================================================================
# 实验 P：属性值精准选号（内测最优：数字合）
# =====================================================================
BALL_RANGES = {1: (1, 30), 2: (2, 35), 3: (5, 41),
               4: (9, 45), 5: (25, 48), 6: (29, 49), 7: (1, 49)}


def ball_range(tb, use_exp=True):
    """球位的号码区间：经验区间或全区间"""
    if use_exp:
        return BALL_RANGES.get(int(tb), (int(tb), 43 + int(tb)))
    return (int(tb), 43 + int(tb))


def _exp_precise(loader):
    import math as _m
    from collections import Counter as _C, defaultdict as _dd
    st.markdown("#### 实验 P：属性值精准选号（支持多球位融合）")
    st.success("内测结论（修正数字合后，2000 期）："
               "第1球有效（1 个号 11.8%、5 个号 31.7%，随机 3.3%/16.7%）；"
               "第6球有效（1 个号 9.9%、5 个号 33.8%）；"
               "第2球、第5球基本无效（优势 ≤ +1.6 甚至为负），不建议使用。")
    st.caption("说明：数字合按「各位相加」分组（0合、1合…13合），"
               "第1球 0 号不存在，0~36 中 0 归 0合。")
    with st.expander("📘 原理与使用", expanded=False):
        st.markdown("""
**原理**
1. 目标是该球的「属性值」（默认数字合，共 11 类，每类 4~5 个号）。
2. 每个「基准球位 + 属性」组合各自找历史相似期，统计下一期目标属性分布。
3. 各组合给属性值投票（概率），取对数相加得分。
4. 取分数最高的 K 个属性值 → 对应号码即建议。

**多球位融合**
勾选多个基准球位时，每个球位的属性各自投票，合起来算分。
内测结论：1 个球位（第1球）已经最好；多球位会让候选略少但命中略降。

**使用**
1. 选目标球位、目标属性、取几个属性值
2. 勾选基准球位（默认只选 1）
3. 勾选参与融合的属性
4. 点「▶ 回测」
""")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)
    nball = len(data[0][1])
    ATTRS = ["尾数", "数字合", "四宝", "物象", "方位", "福禄寿",
             "生肖五行", "阴阳天地", "3模", "波色"]

    def v_of(num, key):
        if key == "尾数":
            return str(num % 10)
        if key == "3模":
            return str(num % 3)
        if key == "生肖":
            return ""      # 生肖需按期，用 v_at / v_num 处理
        return amap.get(num, {}).get(key, "")

    def v_at(i, num, key):
        """第 i 期（当年生肖）下该号码的属性值"""
        if key == "生肖":
            return _zod_of_num(int(num), _offset_of(i))
        return v_of(num, key)

    c1, c2, c3 = st.columns(3)
    with c1:
        tb = st.selectbox("目标球位", list(range(1, nball + 1)), index=0,
                          key="lab_p_ball")
    with c2:
        tattr = st.selectbox("目标属性（建议数字合）",
                             ["数字合", "尾数", "四宝", "方位", "生肖五行"],
                             index=0, key="lab_p_tattr")
    with c3:
        kk = st.number_input("输出几个号码（1~5）", 1, 5, 2, 1,
                             key="lab_p_k")

    use_exp = st.checkbox("使用经验区间（按球位收窄，减少号码数）",
                          value=True, key="lab_p_exprange")
    base_balls = st.multiselect("基准球位（可多选做融合）",
                                list(range(1, nball + 1)), default=[1],
                                key="lab_p_balls")
    used = st.multiselect("参与融合的属性",
                          ATTRS, default=["尾数", "方位", "四宝"],
                          key="lab_p_attrs")
    c4, c5, c6 = st.columns(3)
    with c4:
        d = st.number_input("联动行数", 1, 6, 1, 1, key="lab_p_depth")
    with c5:
        pick = st.selectbox("预测期号", list(reversed(periods)), index=0,
                            key="lab_p_pick")
    with c6:
        bt = st.number_input("回测期数", 100, 3000, 2000, 100,
                             key="lab_p_bt")

    if not used or not base_balls:
        st.warning("请至少选 1 个基准球位和 1 个属性")
        return

    _zrows = _load_zodiac(loader)
    _zmap = {r[0]: r[1:8] for r in _zrows}
    _ZOD = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

    def _zod_of_num(num, offset):
        return _ZOD[(num - 1 + offset) % 12]

    def _offset_of(i):
        """按该期第1球推算当年生肖偏移"""
        row = _zmap.get(periods[i])
        if not row:
            return 0
        z0 = row[0]
        n0 = data[i][1][0]
        if z0 not in _ZOD:
            return 0
        return (_ZOD.index(z0) - (n0 - 1)) % 12

    lo, hi = ball_range(tb, bool(use_exp))
    st.caption(f"第{tb}球区间：{lo} ~ {hi}（共 {hi - lo + 1} 个号）"
               + ("" if use_exp else "　全区间"))
    tseq = [v_at(i, data[i][1][tb - 1], tattr) for i in range(n)]
    uni = sorted({x for x in tseq if x})
    dims = [(b, a) for b in base_balls for a in used]
    seqs = {k: [v_of(x[1][k[0] - 1], k[1]) for x in data] for k in dims}
    dd = int(d)

    def predict(i, tables):
        if i < dd:
            return None
        sc = {v: 0.0 for v in uni}
        for k in dims:
            c = tables[k].get(tuple(seqs[k][i - dd + 1: i + 1]))
            if not c:
                continue
            tot = sum(c.values())
            for v in uni:
                sc[v] += _m.log((c.get(v, 0) + 0.5) / (tot + 0.5 * len(uni)))
        return sorted(sc.items(), key=lambda z: -z[1])[:int(kk)]

    idx0 = periods.index(pick)
    tables = {k: _dd(_C) for k in dims}
    for i in range(1, idx0 + 1):
        if i >= dd:
            for k in dims:
                tables[k][tuple(seqs[k][i - dd: i])][tseq[i]] += 1
    rk = predict(idx0, tables) or []
    nums = []
    if rk:
        _sc_map = {v: s for v, s in rk}
        # 近期热度微调：出现多的号码在同分时优先

        _recent = data[max(0, idx0 - 59): idx0 + 1]
        _rc = {}
        for _row in _recent:
            _vv = _row[1][tb - 1]
            _rc[_vv] = _rc.get(_vv, 0) + 1
        _all_n = list(range(lo, hi + 1))
        _all_n.sort(key=lambda x: (-_sc_map.get(v_at(idx0, x, tattr), -1e9),
                                   -_rc.get(x, 0), x))
        nums = _all_n[:int(kk)]
        st.markdown(f"### 基于 {pick} 期 → 下一期第{tb}球")
        _act_line = ""
        if idx0 + 1 < n:
            _act_line = str(data[idx0 + 1][1][tb - 1])
        st.dataframe(pd.DataFrame(
            [{"属性值": v, "得分": round(s, 2),
              "该属性值对应号码": "、".join(
                  str(x) for x in range(lo, hi + 1)
                  if v_at(idx0, x, tattr) == v),
              "实际下期号码": _act_line if j == 0 else ""}
             for j, (v, s) in enumerate(rk)]),
            use_container_width=True, hide_index=True)
        st.success(f"建议号码（{len(nums)} 个）："
                   + "、".join(str(x) for x in nums))

    if idx0 + 1 < n:
        _act_num = data[idx0 + 1][1][tb - 1]
        act = v_of(_act_num, tattr)
        st.info(f"实际下一期（{periods[idx0 + 1]}）：第{tb}球开奖号码 = "
                f"{_act_num}（{tattr} {act}）"
                + ("　✅ 命中" if _act_num in nums
                   else "　❌ 未中" if nums else ""))
    else:
        st.caption("最新一期，下一期未开")

    if not st.button("▶ 回测", key="lab_p_run"):
        return
    start = max(300, n - int(bt))
    tables = {k: _dd(_C) for k in dims}
    ok = tot = cnt = 0
    for i in range(start, n - 1):
        if i >= dd:
            for k in dims:
                tables[k][tuple(seqs[k][i - dd: i])][tseq[i]] += 1
        rr = predict(i, tables)
        if not rr:
            continue
        _m2 = {v: s for v, s in rr}
        _rc2 = {}
        for _row in data[max(0, i - 59): i + 1]:
            _vv = _row[1][tb - 1]
            _rc2[_vv] = _rc2.get(_vv, 0) + 1
        _lst = list(range(lo, hi + 1))
        _lst.sort(key=lambda x: (-_m2.get(v_at(i, x, tattr), -1e9),
                                 -_rc2.get(x, 0), x))
        _nums2 = set(_lst[:int(kk)])
        if not _nums2:
            continue
        tot += 1
        cnt += len(_nums2)
        ok += 1 if data[i + 1][1][tb - 1] in _nums2 else 0
    if not tot:
        st.warning("样本不足")
        return
    rate, avg = ok / tot * 100, cnt / tot
    base = avg / (hi - lo + 1) * 100
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("命中率", f"{rate:.1f}%", f"{ok}/{tot}")
    m2.metric("平均号码数", f"{avg:.1f} 个")
    m3.metric("随机基线", f"{base:.1f}%")
    m4.metric("优势", f"{rate-base:+.1f}")


# =====================================================================
# 实验 Q：属性融合推荐（属性口径 + 明细 + 报告）
# =====================================================================
def _exp_attr_fusion(loader):
    import math as _m
    from collections import Counter as _C, defaultdict as _dd
    st.markdown("#### 实验 Q：属性融合推荐（结果用属性表达）")
    st.info("推荐结果是「属性值」：选生肖就推生肖、选尾数就推 X尾、"
            "选 3 模就推 3余X；下方有每一条的匹配期号，可逐条核对。")

    data = _load_index6(loader)
    amap = _load_attr_map(loader)
    zodiac = {r[0]: r[1:8] for r in _load_zodiac(loader)}
    zattrs = _load_zodiac_attrs(loader)
    if not data:
        st.error("缺少 _index.csv")
        return
    periods = [p2 for p2, _ in data]
    n = len(data)
    nball = len(data[0][1])

    ATTRS = ["生肖", "尾数", "3模", "数字合", "四宝", "物象", "方位",
             "生肖五行", "波色", "波单双", "门数", "段数"]

    def label(v, attr):
        if attr == "尾数":
            return f"{v}尾"
        if attr == "3模":
            s2 = str(v)
            return s2 if s2.startswith("3余") else f"3余{s2}"
        if attr == "数字合":
            return v if str(v).endswith("合") else f"{v}合"
        return str(v)

    c1, c2, c3 = st.columns(3)
    with c1:
        tb = st.selectbox("目标球位", list(range(1, nball + 1)), index=0,
                          key="lab_q_ball")
    with c2:
        tattr = st.selectbox("目标属性（结果就用这个属性表达）", ATTRS,
                             index=0, key="lab_q_tattr")
    with c3:
        pick = st.selectbox("预测期号", list(reversed(periods)), index=0,
                            key="lab_q_pick")

    c4, c5, c6 = st.columns(3)
    with c4:
        depth = st.number_input("联动行数", 1, 6, 1, 1, key="lab_q_depth")
    with c5:
        kk = st.number_input("推荐几个属性值", 1, 6, 3, 1, key="lab_q_k")
    with c6:
        st.caption("回测区间在下方选择")

    _bc1, _bc2 = st.columns(2)
    with _bc1:
        _bstart = st.selectbox("回测起始期", list(reversed(periods)),
                               index=min(999, len(periods) - 1),
                               key="lab_q_start")
    with _bc2:
        _bend = st.selectbox("回测结束期", list(reversed(periods)), index=0,
                             key="lab_q_end")
    base_balls = st.multiselect("基准球位", list(range(1, nball + 1)),
                                default=[1], key="lab_q_balls")
    used = st.multiselect("参与融合的属性", ATTRS,
                          default=["尾数", "方位", "四宝"], key="lab_q_attrs")
    if not base_balls or not used:
        st.warning("请至少选 1 个基准球位和 1 个融合属性")
        return

    def v_at(i, ball, attr):
        val = _attr_of(data[i], ball, attr, zodiac, zattrs, amap)
        return str(val) if val is not None else ""

    d = int(depth)
    dims = [(b, a) for b in base_balls for a in used]
    seqs = {k: [v_at(i, k[0], k[1]) for i in range(n)] for k in dims}
    tseq = [v_at(i, tb, tattr) for i in range(n)]
    uni = sorted({x for x in tseq if x})
    # 各球位号码区间（经验区间）
    lo, hi = BALL_RANGES.get(int(tb), (int(tb), 43 + int(tb)))

    def build_tables(upto):
        tabs = {k: _dd(_C) for k in dims}
        for i in range(1, upto + 1):
            if i >= d:
                for k in dims:
                    tabs[k][tuple(seqs[k][i - d: i])][tseq[i]] += 1
        return tabs

    def dim_match(k, i, tabs):
        pat = tuple(seqs[k][i - d + 1: i + 1])
        return tabs[k].get(pat), pat

    idx0 = periods.index(pick)
    tabs = build_tables(idx0)
    score = {v: 0.0 for v in uni}
    dim_reports = []
    for k in dims:
        c, pat = dim_match(k, idx0, tabs)
        if not c:
            dim_reports.append({"维度": f"第{k[0]}球{k[1]}",
                                "排列": " → ".join(pat),
                                "匹配期数": 0, "最偏向": "—"})
            continue
        tot = sum(c.values())
        for v in uni:
            score[v] += _m.log((c.get(v, 0) + 0.5) / (tot + 0.5 * len(uni)))
        top = c.most_common(3)
        dim_reports.append({"维度": f"第{k[0]}球{k[1]}",
                            "排列": " → ".join(pat),
                            "匹配期数": tot,
                            "最偏向": "、".join(f"{label(v, tattr)}({x}次)"
                                             for v, x in top)})

    ranked = sorted(score.items(), key=lambda z: -z[1])[:int(kk)]

    st.markdown(f"### 推荐（{pick} 之后，第{tb}球 {tattr}）")
    _ZOD = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

    def _num_attr(x):
        """号码 x 在第 idx0 期所属年的属性值"""
        if tattr == "生肖":
            zrow = zodiac.get(periods[idx0])
            if not zrow:
                return ""
            z0, n0 = zrow[0], data[idx0][1][0]
            if z0 not in _ZOD:
                return ""
            off = (_ZOD.index(z0) - (n0 - 1)) % 12
            return _ZOD[(int(x) - 1 + off) % 12]
        if tattr == "尾数":
            return str(int(x) % 10)
        if tattr == "3模":
            return str(int(x) % 3)
        return amap.get(int(x), {}).get(tattr, "")

    rows = []
    for v, s in ranked:
        nums = [x for x in range(lo, hi + 1) if _num_attr(x) == v]
        rows.append({"属性值": label(v, tattr), "得分": round(s, 2),
                     "对应号码": "、".join(str(x) for x in nums) or "—"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True)
    st.success("推荐属性值：" + "、".join(label(v, tattr) for v, _ in ranked))

    # 实际结果对比
    if idx0 + 1 < len(periods):
        _act_num = data[idx0 + 1][1][tb - 1]
        _act = tseq[idx0 + 1]
        _hit = _act in {v for v, _ in ranked}
        st.markdown(f"### 实际：{periods[idx0 + 1]} 期，第{tb}球 = "
                    f"**{_act_num}**（{tattr}：{label(_act, tattr)}）")
        m1, m2 = st.columns(2)
        m1.metric("是否命中", "✅ 命中" if _hit else "❌ 未中")
        _pos = [v for v, _ in ranked]
        m2.metric("实际排第几",
                  f"{_pos.index(_act)+1} 位" if _act in _pos else "未进推荐")
    else:
        st.info(f"{pick} 是最新一期，下一期尚未开奖")

    with st.expander("🔍 各属性匹配明细（可逐条核对）", expanded=False):
        st.dataframe(pd.DataFrame(dim_reports), use_container_width=True,
                     hide_index=True)
        for k in dims:
            c, pat = dim_match(k, idx0, tabs)
            if not c:
                continue
            hits = []
            for j in range(d - 1, idx0):
                if tuple(seqs[k][j - d + 1: j + 1]) == pat:
                    hits.append({"历史触发期": periods[j],
                                 "下一期": periods[j + 1],
                                 "下一期目标值": label(tseq[j + 1], tattr)})
            with st.expander(f"第{k[0]}球{k[1]}：{len(hits)} 条匹配", expanded=False):
                if hits:
                    st.dataframe(pd.DataFrame(hits[::-1][:100]),
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("无匹配")

    # ---------- 多属性叠加报告 ----------
    st.markdown("---")
    st.markdown("### 多属性推荐叠加（逐个属性出报告，最后汇总）")
    def _num_attr2(x, attr):
        if attr == "生肖":
            zrow = zodiac.get(periods[idx0]) or []
            if zrow and zrow[0] in _ZOD:
                off = (_ZOD.index(zrow[0]) - (data[idx0][1][0] - 1)) % 12
                return _ZOD[(int(x) - 1 + off) % 12]
            return ""
        if attr == "尾数":
            return str(int(x) % 10)
        if attr == "3模":
            return str(int(x) % 3)
        return amap.get(int(x), {}).get(attr, "")

    multi_attrs = st.multiselect("要逐个测的属性", ATTRS,
                                 default=[tattr], key="lab_q_multi")
    _kmap = {}
    _probs = {}
    if multi_attrs:
        st.caption("各属性推荐个数（可分别设置）")
        _cols = st.columns(min(4, len(multi_attrs)))
        for _i2, _a2 in enumerate(multi_attrs):
            with _cols[_i2 % len(_cols)]:
                _kmap[_a2] = st.number_input(
                    f"{_a2} 推荐几个", 1, 8,
                    3 if _a2 in ("生肖", "尾数", "数字合") else 2,
                    1, key=f"lab_q_k_{_a2}")
        _final_n = st.number_input("最终号码个数", 1, 12, 5, 1,
                                   key="lab_q_finaln")
        _method = st.radio("最终号码生成方式",
                           ["联合概率（推荐）", "投票叠加"],
                           horizontal=True, key="lab_q_method")
    if multi_attrs and st.button("▶ 生成叠加报告", key="lab_q_multi_run"):
        acc_num = {}
        acc_val = []
        _ZOD2 = _ZOD
        for _a in multi_attrs:
            _tseq = [_attr_of(data[i], tb, _a, zodiac, zattrs, amap) or ""
                     for i in range(n)]
            _uni = sorted({x for x in _tseq if x})
            _sc = {v: 0.0 for v in _uni}
            for k in dims:
                _c = tabs[k].get(tuple(seqs[k][idx0 - d + 1: idx0 + 1]))
                if not _c:
                    continue
                _tt = sum(_c.values())
                for v in _uni:
                    _sc[v] += _m.log((_c.get(v, 0) + 0.5)
                                     / (_tt + 0.5 * len(_uni)))
            _kk2 = int(_kmap.get(_a, int(kk)))
            _rk = sorted(_sc.items(), key=lambda z: -z[1])[:_kk2]
            _mx = max(_sc.values()) if _sc else 0.0
            _w = {v: _m.exp(s - _mx) for v, s in _sc.items()}
            _wt = sum(_w.values()) or 1.0
            _probs[_a] = {v: w / _wt for v, w in _w.items()}
            st.markdown(f"#### ========= {periods[idx0]}期 升序 第{tb}球 "
                        f"{_a} 推荐 =========")
            st.write("推荐：" + "、".join(label(v, _a) for v, _ in _rk)
                     + f"　（取前 {_kk2} 个）")
            _rows = []
            for v, s in _rk:
                if _a == "生肖":
                    zrow = zodiac.get(periods[idx0]) or []
                    nums = []
                    if zrow and zrow[0] in _ZOD2:
                        off = (_ZOD2.index(zrow[0]) - (data[idx0][1][0] - 1)) % 12
                        nums = [x for x in range(lo, hi + 1)
                                if _ZOD2[(x - 1 + off) % 12] == v]
                elif _a == "尾数":
                    nums = [x for x in range(lo, hi + 1) if str(x % 10) == v]
                elif _a == "3模":
                    nums = [x for x in range(lo, hi + 1) if str(x % 3) == v]
                else:
                    nums = [x for x in range(lo, hi + 1)
                            if amap.get(x, {}).get(_a, "") == v]
                _rows.append({"属性值": label(v, _a),
                              "推荐个数": _kk2,
                              "得分": round(s, 2),
                              "对应号码": "、".join(str(x) for x in nums) or "—"})
                for x in nums:
                    _ent = acc_num.setdefault(x, {"次数": 0, "属性": []})
                    _ent["次数"] += 1
                    if _a not in _ent["属性"]:
                        _ent["属性"].append(_a)
            st.dataframe(pd.DataFrame(_rows), use_container_width=True,
                         hide_index=True)
            # 实际结果核对（逐属性）
            if idx0 + 1 < n:
                _anum = data[idx0 + 1][1][tb - 1]
                _aval = _tseq[idx0 + 1]
                _rec_vals = {v for v, _ in _rk}
                _say = (", ".join(label(v, _a) for v, _ in _rk))
                if _aval in _rec_vals:
                    st.success(f"{{}} 期开 {{}}（{{}}：{{}}）→ ✅ 测中 {{}}".format(
                        periods[idx0 + 1], _anum, _a, label(_aval, _a),
                        label(_aval, _a)))
                else:
                    st.error(f"{{}} 期开 {{}}（{{}}：{{}}）→ ❌ 未中".format(
                        periods[idx0 + 1], _anum, _a, label(_aval, _a)))
            acc_val.append((_a, [label(v, _a) for v, _ in _rk]))

        _pkg = {"期号": periods[idx0], "球位": tb,
                "目标属性": tattr, "推荐个数": int(kk),
                "各属性推荐": [], "号码累计": {}}
        for _a, vals in acc_val:
            _pkg["各属性推荐"].append({"属性": _a, "推荐个数": _kmap.get(_a, 0),
                                         "推荐值": vals})

        st.markdown("#### ========= 叠加汇总（号码被推荐次数）========")
        if acc_num:
            rank = sorted(acc_num.items(),
                          key=lambda x: (-len(x[1]["属性"]),
                                         -x[1]["次数"], x[0]))
            st.dataframe(pd.DataFrame(
                [{"号码": x, "覆盖属性数": len(d["属性"]),
                  "被推荐次数": d["次数"],
                  "推荐属性": "、".join(d["属性"])} for x, d in rank]),
                use_container_width=True, hide_index=True)
            top_n = rank[:int(_final_n)]
            _joint_top = []
            if _probs:
                _js = {}
                for _x in range(lo, hi + 1):
                    _s = 0.0
                    for _a3, _pp in _probs.items():
                        _v4 = _num_attr2(_x, _a3)
                        _s += _m.log(_pp.get(_v4, 1e-6))
                    _js[_x] = _s
                _joint_top = [x for x, _ in sorted(_js.items(),
                                                   key=lambda z: -z[1])][:int(_final_n)]
            _vote_list = [x for x, _ in rank[:int(_final_n)]]
            _act_now = (data[idx0 + 1][1][tb - 1]
                        if idx0 + 1 < len(periods) else None)
            if _method.startswith("联合") and _joint_top:
                _final_list = list(_joint_top)
                st.success("最终号码（联合概率最高）："
                           + "、".join(
                               (f"**{x}** ★" if x == _act_now else str(x))
                               for x in _final_list)
                           + (f"　→ 实际开 {_act_now}，✅ 测中"
                              if _act_now in _final_list else
                              (f"　→ 实际开 {_act_now}，❌ 未中"
                               if _act_now is not None else "")))
                st.caption("投票叠加法会给出："
                           + "、".join(str(x) for x in _vote_list))
            else:
                _final_list = list(_vote_list)
                st.success("最终号码（推荐次数最多）："
                           + "、".join(
                               (f"**{x}** ★" if x == _act_now else str(x))
                               for x in _final_list)
                           + (f"　→ 实际开 {_act_now}，✅ 测中"
                              if _act_now in _final_list else
                              (f"　→ 实际开 {_act_now}，❌ 未中"
                               if _act_now is not None else "")))
            _pkg["号码累计"] = {str(x): {"覆盖属性数": len(d["属性"]),
                                          "次数": d["次数"],
                                          "属性": d["属性"]}
                                for x, d in rank}
            _pkg["最终号码"] = list(_final_list)
            _pkg["生成方式"] = _method

            # 是否测中（有下一期时）
            if idx0 + 1 < n:
                _an2 = data[idx0 + 1][1][tb - 1]
                _hit2 = _an2 in _final_list
                _ok_attrs = [x.get("属性") for x in _pkg["各属性推荐"]
                             if label(tseq[idx0 + 1], tattr) in x["推荐值"]]
                st.markdown(f"### 实际：{periods[idx0 + 1]} 期，第{tb}球 = "
                            f"**{_an2}**")
                _mm1, _mm2 = st.columns(2)
                _mm1.metric("最终号码是否测中",
                            "✅ 测中" if _hit2 else "❌ 未中")
                _mm2.metric("号码在最终单里的位置",
                            f"{_final_list.index(_an2)+1} 位"
                            if _hit2 else "未进单")
                _pkg["实际结果"] = {
                    "下一期": periods[idx0 + 1], "开奖号": _an2,
                    "最终号码测中": bool(_hit2)}
            else:
                st.info(f"{periods[idx0]} 是最新一期，下一期尚未开奖")

            st.session_state["_lab_q_pkg"] = _pkg
        else:
            st.warning("没有累计到任何号码：请确认所选属性在目标球位区间内有对应号码")
        if acc_val:
            st.markdown("**各属性推荐清单**")
        for _a, vals in acc_val:
            st.caption(f"{_a}：{'、'.join(vals)}")

    _pkg2 = st.session_state.get("_lab_q_pkg")
    if _pkg2:
        st.markdown("---")
        st.markdown("### 📤 分析包（供系统汇总用）")
        st.caption("后续「系统大总结」会读取这份分析包，自动生成结论。")
        import json as _json
        _txt = _json.dumps(_pkg2, ensure_ascii=False, indent=2)
        st.code(_txt, language="json")
        _c1, _c2 = st.columns(2)
        with _c1:
            st.download_button("📥 下载分析包 JSON", _txt.encode("utf-8"),
                               file_name=f"分析包_{_pkg2['期号']}.json",
                               mime="application/json", key="lab_q_pkg_dl")
        with _c2:
            if st.button("📨 送入汇总看板", key="lab_q_pkg_send"):
                try:
                    if H.get("board_add"):
                        H["board_add"](
                            f"实验Q {_pkg2['期号']} 第{_pkg2['球位']}球 "
                            f"{_pkg2['目标属性']}", _txt)
                        st.success("已送入汇总看板")
                    else:
                        st.warning("当前环境没有看板接口")
                except Exception as e:
                    st.error(f"送入失败：{e}")


    # ---------- 回测 ----------
    _i1 = periods.index(_bstart)
    _i2 = periods.index(_bend)
    if _i1 > _i2:
        _i1, _i2 = _i2, _i1
    st.caption(f"回测区间：{periods[_i1]} ~ {periods[_i2]}（{_i2 - _i1 + 1} 期）"
               f"｜预测期号：{pick}")

    # 预计算多属性序列（避免回测里重复遍历）
    _seq_multi = {}
    _uni_multi = {}
    for _a0 in (multi_attrs or []):
        _sq = [_attr_of(data[_j], tb, _a0, zodiac, zattrs, amap) or ""
               for _j in range(n)]
        _seq_multi[_a0] = _sq
        _uni_multi[_a0] = sorted({x for x in _sq if x})

    if st.button("▶ 回测这套推荐", key="lab_q_run"):
        start = max(300, _i1)
        end_i = min(n - 1, _i2)
        tabs2 = {k: _dd(_C) for k in dims}
        ok = tot = 0
        detail = []
        for i in range(start, end_i):
            if i >= d:
                for k in dims:
                    tabs2[k][tuple(seqs[k][i - d: i])][tseq[i]] += 1
            sc = {v: 0.0 for v in uni}
            for k in dims:
                c, _pat = dim_match(k, i, tabs2)
                if not c:
                    continue
                tt = sum(c.values())
                for v in uni:
                    sc[v] += _m.log((c.get(v, 0) + 0.5) / (tt + 0.5 * len(uni)))
            rk = sorted(sc.items(), key=lambda z: -z[1])[:int(kk)]
            vals = {v for v, _ in rk}
            if not vals:
                continue
            tot += 1
            act = tseq[i + 1]
            ok += 1 if act in vals else 0

            # 最终号码（多属性交叉叠加）是否命中
            _num_hit = ""
            _final = []
            if multi_attrs:
                _acc = {}
                for _a2 in multi_attrs:
                    _all2 = _seq_multi[_a2]
                    _un2 = _uni_multi[_a2]
                    _sc2 = {}
                    for _v2 in _un2:
                        _s2 = 0.0
                        for k in dims:
                            _c2 = tabs2[k].get(tuple(seqs[k][i - d + 1: i + 1]))
                            if not _c2:
                                continue
                            _tt2 = sum(_c2.values())
                            _s2 += _m.log((_c2.get(_v2, 0) + 0.5)
                                          / (_tt2 + 0.5 * len(_un2)))
                        _sc2[_v2] = _s2
                    _rk2 = sorted(_sc2.items(), key=lambda z: -z[1])[
                        :int(_kmap.get(_a2, 1))]
                    for _v3, _ in _rk2:
                        for _x3 in range(lo, hi + 1):
                            if _num_attr2(_x3, _a2) == _v3:
                                _acc[_x3] = _acc.get(_x3, 0) + 1
                _final = [x for x, _ in sorted(
                    _acc.items(), key=lambda z: (-z[1], z[0]))][:int(_final_n)]
                _num_hit = "号码★" if data[i + 1][1][tb - 1] in _final else ""

            detail.append({"期号": periods[i + 1], "推荐": "、".join(
                label(v, tattr) for v in vals),
                "实开": label(act, tattr), "命中": "★" if act in vals else "",
                "最终号码": "、".join(str(x) for x in _final) or "—",
                "号码命中": _num_hit})
        if tot:
            _n_hit = sum(1 for x in detail if x.get("号码命中"))
            m1, m2, m3 = st.columns(3)
            m1.metric("属性命中率", f"{ok/tot*100:.1f}%", f"{ok}/{tot}")
            m2.metric("最终号码命中率", f"{_n_hit/tot*100:.1f}%",
                      f"{_n_hit}/{tot}")
            m3.metric("随机基线",
                      f"{min(1.0, int(kk)/max(1,len(uni)))*100:.1f}%")
            st.dataframe(pd.DataFrame(detail[::-1][:300]),
                         use_container_width=True, hide_index=True,
                         height=300)

    st.caption("说明：推荐值用目标属性表达；对应号码按球位区间换算，"
               "最终仍可交给系统转成具体数字下注。")


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

    tabd, tabh, tabl, tabm, tabn, tabo, tabq, tab4, tab3 = st.tabs(
        ["📖 说明书", "实验H 六码中三", "实验L 简单版",
         "实验M 跨球联动", "实验N 自由联动", "实验O 融合评分",
         "实验Q 属性推荐", "结论档案", "清理"])
    with tabd:
        _exp_docs()
    with tabh:
        _exp_six_pick(H)
    with tabl:
        _exp_simple(H)
    with tabm:
        _exp_cross_ball(H)
    with tabn:
        _exp_flex(H)
    with tabo:
        _exp_fusion(H)
    with tabq:
        _exp_attr_fusion(H)
    # 实验P 已独立成「🎯 精准选号」页
    with tab4:
        _archive()
    with tab3:
        _cleanup(H)

    st.divider()
    st.caption("📁 实验下拉框（选一个再打开）")
    _old = st.selectbox(
        "选择实验",
        ["（不打开）",
         "实验B 组合池", "实验I 加注模拟", "实验J 属性杀号",
         "实验K 追热追冷",
         "实验C 形态组合", "实验D 属性联动",
         "实验E 锁定目标球", "实验F 三三组合", "实验G 热号回测"],
        index=0, key="lab_old_pick")
    if _old.startswith("实验B"):
        _exp_pool(H)
    elif _old.startswith("实验I"):
        _exp_stake_plan(H)
    elif _old.startswith("实验J"):
        _exp_kill_rank(H)
    elif _old.startswith("实验K"):
        _exp_hot_cold(H)
    elif _old.startswith("实验C"):
        _exp_gate3(H)
    elif _old.startswith("实验D"):
        _exp_link_attr(H)
    elif _old.startswith("实验E"):
        _exp_target_multi(H)
    elif _old.startswith("实验F"):
        _exp_combo_prev(H)
    elif _old.startswith("实验G"):
        _exp_hot_pick(H)

    st.divider()
    st.caption(f"本页所有实验数据统一存入看板的「{SRC_TAG}」来源，便于一键清除。")
