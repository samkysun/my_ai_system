# -*- coding: utf-8 -*-
"""升降交集：把「升序」与「按序」两套数据交叉求解
   · 各位置按历史频率取候选
   · 两套候选取交集 + 升序递增约束
   · 输出每个位置剩余候选，并可跑回测对比
"""
import re
from collections import Counter

import pandas as pd
import streamlit as st

_UP_FILE = "升序全套.csv"
_AN_FILE = "按序全套.csv"


def _parse(rows):
    """期号 -> [7 个球号]（按文件中的顺序）"""
    out = {}
    for r in rows[2:]:
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}".strip()
        if not p:
            continue
        nums = []
        for b in range(1, 8):
            i10 = 3 + (b - 1) * 30
            i1 = i10 + 1
            try:
                nums.append(int((r[i10].strip() + r[i1].strip()) or 0))
            except Exception:
                nums.append(0)
        out[p] = nums
    return out


def _aligned(up, an):
    """取两套一致（前6同集合且无重复）的期，按时间升序"""
    seq = []
    for p in sorted(set(up) & set(an)):
        u, a = up[p], an[p]
        if len(set(u[:6])) < 6 or len(set(a[:6])) < 6:
            continue
        if sorted(u[:6]) != sorted(a[:6]):
            continue
        seq.append((p, u, a))
    return seq


def _topk(counter, k):
    return [n for n, _ in counter.most_common(k)]


def _candidates(seq_hist, k):
    """返回 (升序各位置候选, 按序各球位候选)"""
    S, A = {}, {}
    for j in range(6):
        S[j] = _topk(Counter(x[1][j] for x in seq_hist), k)
    for i in range(6):
        A[i] = _topk(Counter(x[2][i] for x in seq_hist), k)
    # 特码
    S[6] = _topk(Counter(x[1][6] for x in seq_hist), k)
    A[6] = _topk(Counter(x[2][6] for x in seq_hist), k)
    return S, A


def _cross(S, A):
    """升序候选 ∩ 按序候选并集，再施加递增约束"""
    unionA = set()
    for i in range(6):
        unionA |= set(A[i])
    filt = {}
    for j in range(6):
        filt[j] = [n for n in S[j] if n in unionA]
    for j in range(4, -1, -1):
        if filt[j + 1]:
            lo = min(filt[j + 1])
            filt[j] = [n for n in filt[j] if n < lo]
    return filt


def _bucket(v):
    if v <= 9:
        return "01-09"
    if v <= 19:
        return "10-19"
    if v <= 29:
        return "20-29"
    if v <= 39:
        return "30-39"
    return "40-49"


_BUCKETS = ["01-09", "10-19", "20-29", "30-39", "40-49"]


def _rank_table(seq_hist):
    """{区间: Counter(升序排名0-5)}"""
    tab = {}
    for bk in _BUCKETS:
        tab[bk] = Counter()
    for p, u, a in seq_hist:
        srt = sorted(u[:6])
        for i in range(6):
            tab[_bucket(a[i])][srt.index(a[i])] += 1
    return tab


def rank_probs(seq_hist, A):
    """给定按序各球位候选，推算每个球位的升序位置概率
       返回 {(球位i, 排名r): 概率}"""
    tab = _rank_table(seq_hist)
    freq = {}
    for i in range(6):
        freq[i] = Counter(x[2][i] for x in seq_hist)
    out = []
    for i in range(6):
        total = sum(freq[i].values()) or 1
        probs = [0.0] * 6
        for v in A.get(i, []):
            w = freq[i].get(v, 0) / total
            row = tab.get(_bucket(v))
            if not row:
                continue
            s = sum(row.values()) or 1
            for r in range(6):
                probs[r] += w * (row.get(r, 0) / s)
        sm = sum(probs) or 1
        probs = [x / sm for x in probs]
        out.append(probs)
    return out


def render(df_data, H):
    st.title("🔀 升降交集")
    st.caption("「升序」是 6 个平码从小到大排列 + 特码；「按序」是落球顺序。"
               "同一期的前 6 个号是同一组数，两套候选取交集能压缩范围。")

    load = H["load_excel_data"]
    netok = H.get("netok")

    rows_up = load(_UP_FILE, None) or []
    rows_an = load(_AN_FILE, None) or []
    if not rows_up or not rows_an:
        st.error("读不到数据文件")
        return

    up, an = _parse(rows_up), _parse(rows_an)
    seq = _aligned(up, an)
    if not seq:
        st.error("两套数据没有可对齐的期")
        return

    st.caption(f"可对齐期数：{len(seq)}（{seq[0][0]} ~ {seq[-1][0]}）")

    c1, c2 = st.columns([1, 1])
    with c1:
        k = st.slider("每个位置取前几个候选", 3, 20, 8, 1, key="cv_k")
    with c2:
        mode = st.radio("模式", ["预测下一期", "回测对比"], horizontal=True, key="cv_mode")

    if mode == "预测下一期":
        st.markdown("### 下一期候选")
        S, A = _candidates(seq, k)
        f = _cross(S, A)
        _next = "—"
        try:
            _next = str(int(seq[-1][0]) + 1)
        except Exception:
            pass
        st.markdown(f"**目标期号：{_next}**（上一期 {seq[-1][0]} 已开奖）")

        rows = []
        for j in range(6):
            rows.append({
                "升序位置": f"第{j+1}位",
                "升序候选": " ".join(f"{n:02d}" for n in S[j]),
                "按序候选并集": "—",
                "交叉后候选": " ".join(f"{n:02d}" for n in f[j]) or "（空）",
                "个数": len(f[j]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        rows2 = []
        for i in range(6):
            rows2.append({
                "按序球位": f"第{i+1}球",
                "按序候选": " ".join(f"{n:02d}" for n in A[i]),
            })
        rows2.append({"按序球位": "第7球(特码)", "按序候选": " ".join(f"{n:02d}" for n in A[6])})
        st.markdown("**按序各球位候选**")
        st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)

        # ---------- 位置推断 ----------
        st.markdown("**位置推断：这个球最可能处在升序第几位**")
        probs = rank_probs(seq, A)
        rows3 = []
        for i in range(6):
            pb = probs[i]
            order = sorted(range(6), key=lambda r: -pb[r])
            best1, best2 = order[0], order[1]
            rows3.append({
                "按序球位": f"第{i+1}球",
                "最可能升序位": f"第{best1+1}位",
                "把握": f"{pb[best1]*100:.0f}%",
                "次选": f"第{best2+1}位",
                "次选把握": f"{pb[best2]*100:.0f}%",
                "前2合计": f"{(pb[best1]+pb[best2])*100:.0f}%",
                "升1": f"{pb[0]*100:.0f}%",
                "升2": f"{pb[1]*100:.0f}%",
                "升3": f"{pb[2]*100:.0f}%",
                "升4": f"{pb[3]*100:.0f}%",
                "升5": f"{pb[4]*100:.0f}%",
                "升6": f"{pb[5]*100:.0f}%",
            })
        st.dataframe(pd.DataFrame(rows3), use_container_width=True, hide_index=True)
        st.caption("依据：该球位候选号码所在的区间（01-09/10-19/…）在历史上对应的升序排名比例。"
                   "端区（1-9、40-49）把握最高，约 63~65%。")

        # 只在交叉里出现的（精度更高）
        only = sorted({n for j in range(6) for n in f[j]})
        st.markdown("**交叉结果去重后（升序位置可出现的号码）**")
        st.markdown(" ".join(f"`{n:02d}`" for n in only) or "（空）")

        if st.button("📌 推送到 AI 推演看板", key="cv_push"):
            txt = f"【升降交集】目标 {_next}\n升序位置候选：\n"
            for j in range(6):
                txt += f"  第{j+1}位：{' '.join(f'{n:02d}' for n in f[j]) or '空'}\n"
            txt += "按序球位候选：\n"
            for i in range(6):
                txt += f"  第{i+1}球：{' '.join(f'{n:02d}' for n in A[i])}\n"
            txt += f"  第7球(特码)：{' '.join(f'{n:02d}' for n in A[6])}\n"
            if H.get("board_add"):
                H["board_add"]("升降交集", f"目标 {_next}", txt)
                st.success("已推送到看板")
            else:
                st.warning("看板接口不可用")

    else:
        st.markdown("### 回测对比")
        n_test = st.number_input("回测期数", 50, 500, 200, 50, key="cv_n")
        if st.button("▶ 开始回测", key="cv_run"):
            start = max(300, len(seq) - int(n_test))
            res = {"single_hit": 0, "cross_hit": 0, "single_cand": 0,
                   "cross_cand": 0, "n": 0}
            bar = st.progress(0.0, text="回测中…")
            total = len(seq) - start
            for idx in range(start, len(seq)):
                bar.progress((idx - start) / max(1, total), text=f"{seq[idx][0]} …")
                p, u, a = seq[idx]
                S, A = _candidates(seq[:idx], int(k))
                f = _cross(S, A)
                for j in range(6):
                    res["n"] += 1
                    res["single_cand"] += len(S[j])
                    res["cross_cand"] += len(f[j])
                    if u[j] in S[j]:
                        res["single_hit"] += 1
                    if u[j] in f[j]:
                        res["cross_hit"] += 1
            bar.empty()
            n = res["n"]
            if n:
                out = pd.DataFrame([
                    {"方案": "单视图（前K）",
                     "平均候选": round(res["single_cand"] / n, 2),
                     "命中率": f"{res['single_hit']/n*100:.1f}%",
                     "每候选命中率": f"{res['single_hit']/res['single_cand']*100:.1f}%"},
                    {"方案": "双视图交叉",
                     "平均候选": round(res["cross_cand"] / n, 2),
                     "命中率": f"{res['cross_hit']/n*100:.1f}%",
                     "每候选命中率": f"{res['cross_hit']/res['cross_cand']*100:.1f}%"},
                ])
                st.dataframe(out, use_container_width=True, hide_index=True)
                st.caption(f"样本：{n//6} 期 / {n} 个位置；随机基线约 2.0%/候选")
