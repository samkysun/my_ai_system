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
        need = st.number_input("最少匹配几期", 1, 20, 3, 1,
                               key="lab_l_need")

    idx = periods.index(pick)
    seq = [val_of(d[1][ball - 1], attr) for d in data]
    v = seq[idx]
    lo, hi = int(ball), 43 + int(ball)

    cnt = _C()
    rows_n = 0
    detail = []
    for j in range(idx):
        if seq[j] == v:
            rows_n += 1
            nx = seq[j + 1]
            cnt[nx] += 1
            detail.append({"历史触发期": periods[j],
                           "下一期": periods[j + 1],
                           f"下一期第{ball}球{attr}": nx})

    st.markdown(f"### 本期：{pick} 期，第{ball}球 {attr} = **{v}**")
    st.markdown(f"历史上同值共 **{rows_n}** 期（要求 ≥{int(need)} 期）")
    if rows_n < int(need):
        st.warning(f"匹配只有 {rows_n} 期，不足 {int(need)} 期，仅供参考")

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

    tab2, tabh, tabi, tabj, tabk, tabl, tab4, tab3 = st.tabs(
        ["实验B 组合池", "实验H 六码中三", "实验I 加注模拟",
         "实验J 属性杀号", "实验K 追热追冷", "实验L 简单版", "结论档案", "清理"])
    with tab2:
        _exp_pool(H)
    with tabh:
        _exp_six_pick(H)
    with tabi:
        _exp_stake_plan(H)
    with tabj:
        _exp_kill_rank(H)
    with tabk:
        _exp_hot_cold(H)
    with tabl:
        _exp_simple(H)
    with tab4:
        _archive()
    with tab3:
        _cleanup(H)

    st.divider()
    st.caption("📁 旧实验（已收进下拉框，需要时再打开）")
    _old = st.selectbox(
        "选择旧实验",
        ["（不打开）", "实验C 形态组合", "实验D 属性联动",
         "实验E 锁定目标球", "实验F 三三组合", "实验G 热号回测"],
        index=0, key="lab_old_pick")
    if _old.startswith("实验C"):
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
