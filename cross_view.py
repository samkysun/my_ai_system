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


def position_series(seq, which=1):
    """返回 [(期号, 号码, 该号在按序中的位置1-6)]，按时间从新到旧"""
    out = []
    for p, u, a in reversed(seq):          # seq 是旧->新，反转成新->旧
        try:
            val = u[which - 1]
            pos = a[:6].index(val) + 1
        except Exception:
            continue
        out.append((p, val, pos))
    return out


def base_line(rows, which):
    """2026120：期起始 基准列：升序1球20：按序2球，升序1球03：按序4球，…"""
    if not rows:
        return ""
    chrono = list(reversed(rows))          # 旧 -> 新 展示
    seg = "，".join(f"升序{which}球{r[1]:02d}：按序{r[2]}球" for r in chrono)
    return f"{chrono[0][0]}：期起始 基准列：{seg}"


def find_patterns(series, base, allow_miss=0, top_n=30):
    """在 series（新->旧）里找与 base 相似的连续片段
       返回 [(索引, 期号列表, 上一行值, 后续值, 吻合位数)]
       allow_miss=0 时要求完全一致"""
    n = len(base)
    hits = []
    for i in range(1, len(series) - n):          # i=0 是当前基准本身，跳过
        seg = [x[2] for x in series[i:i + n]]
        same = sum(1 for a, b in zip(seg, base) if a == b)
        if same < n - allow_miss:
            continue
        prev_val = series[i - 1][2] if i - 1 >= 0 else None
        next_val = series[i + n][2] if i + n < len(series) else None
        hits.append((i, [x[0] for x in series[i:i + n]], prev_val, next_val, same))
    hits.sort(key=lambda x: (-x[4], x[0]))
    return hits[:top_n]


def backtest_period(seq, which, rows_n, target):
    """用 target 之前的排列预测 target 的位置
       seq 是旧->新；返回 dict"""
    periods = [x[0] for x in seq]
    if target not in periods:
        return None
    pos = periods.index(target)
    if pos < rows_n + 5:
        return {"error": "该期之前数据不足"}
    posv = []
    for q, u, a in seq:
        try:
            posv.append(a[:6].index(u[which - 1]) + 1)
        except Exception:
            posv.append(None)
    base = posv[pos - rows_n:pos]
    if any(v is None for v in base):
        return {"error": "基准行含无效值"}

    hits = []
    for i in range(0, pos - rows_n):
        if posv[i:i + rows_n] == base:
            nxt = posv[i + rows_n] if i + rows_n < len(posv) else None
            hits.append({"start": i, "periods": periods[i:i + rows_n], "next": nxt})
    from collections import Counter as _C
    dist = _C(h["next"] for h in hits if h["next"])
    actual = posv[pos]
    pred = dist.most_common(1)[0][0] if dist else None
    return {"target": target, "base": base, "hits": hits, "dist": dist,
            "actual": actual, "pred": pred,
            "hit": (pred == actual) if pred is not None else False}


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
        mode = st.radio("模式", ["预测下一期", "回测对比", "位置序列"],
                        horizontal=True, key="cv_mode")

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

    elif mode == "位置序列":
        st.markdown("### 位置序列分析")
        st.caption("把「升序第 N 球落在按序第几位」当成属性列，"
                   "用基准行排列去历史里找同样的排列。")

        _c1, _c2, _c3 = st.columns([1, 1, 1])
        with _c1:
            which = st.selectbox("看升序第几个球", [1, 2, 3, 4, 5, 6],
                                 index=0, key="cv_which")
        with _c2:
            rows_n = st.number_input("基准行排列（几行）", 2, 20, 2, 1, key="cv_rows")
        with _c3:
            st.write("")
        ser = position_series(seq, int(which))
        if not ser:
            st.warning("没有可用的序列数据")
            return

        _base_rows = ser[:int(rows_n)]
        base = [x[2] for x in _base_rows]
        st.markdown(f"**【基准行排列】({len(base)}行)**："
                    + " → ".join(str(x) for x in base))
        st.markdown("**" + base_line(_base_rows, which) + "**")

        hits = find_patterns(ser, base, 0)
        _expect = len(ser) / (6 ** len(base))
        st.markdown(f"**【触发行】**：历史中排列完全一致共出现 **{len(hits)}** 次")
        st.caption(f"（{len(base)} 行完全一致的期望出现次数约 {_expect:.2f} 次。"
                   "这个属性只有 6 个取值，实测：2 行约 12~30 次，3 行约 0~9 次，"
                   "4 行以上基本为 0。默认用 2 行，样本最多。）")

        if hits:
            rows_out = []
            for k, (i, periods, prev_val, next_val, _sm) in enumerate(hits[:50], 1):
                rows_out.append({
                    "序": k,
                    "吻合": f"{hits[k-1][4]}/{len(base)}",
                    "行号": f"{i+1}-{i+len(base)}",
                    "期号范围": f"{periods[-1]} ~ {periods[0]}",
                    "更近一期(上一行)": prev_val if prev_val is not None else "-",
                    "更早一期(下一行)": next_val if next_val is not None else "-",
                })
            st.dataframe(pd.DataFrame(rows_out), use_container_width=True,
                         hide_index=True)
            from collections import Counter as _C2
            nxt = _C2(h[3] for h in hits if h[3] is not None)

            # ---------- 多维分析风格的文本报告 ----------
            _lines = [f"========== 升序第{which}球 在按序中的位置序列 ==========",
                      f"【基准行排列】({len(base)}行): " + " → ".join(str(x) for x in base),
                      f"【历史命中】: 共找到 {len(hits)} 段完全一致",
                      ""]
            for k, (i, periods, pv, nv, _sm) in enumerate(hits, 1):
                _rows_seg = ser[i:i + len(base)]
                _seg = [x[2] for x in _rows_seg]
                _det = "，".join(f"升序{which}球{r[1]:02d}：按序{r[2]}球"
                                for r in reversed(_rows_seg))
                _p_prev = ser[i - 1][0] if i - 1 >= 0 else "-"
                _p_next = ser[i + len(base)][0] if i + len(base) < len(ser) else "-"
                _lines.append(
                    f"触发行：行{i+1}-{i+len(base)}({len(base)}行): "
                    f"上:{pv if pv is not None else '-'}({_p_prev}期) "
                    f"(匹配:{' '.join(str(x) for x in _seg)}) "
                    f"下:{nv if nv is not None else '-'}({_p_next}期)"
                    f"　[{periods[-1]}~{periods[0]}]")
                _lines.append(f"　　　　　{periods[-1]}：期起始 基准列：{_det}")
            if nxt:
                _lines.append("")
                _lines.append("【触发行之后的位置分布】")
                _tot_n = sum(nxt.values()) or 1
                _lines.append("  " + "　".join(
                    f"第{i}位:{nxt.get(i,0)}次({nxt.get(i,0)/_tot_n*100:.0f}%)"
                    for i in range(1, 7)))
                _lines.append("")
                _lines.append("【各位置对应的期号】")
                for _pos in range(1, 7):
                    _ps = [x[0] for x in ser if x[2] == _pos]   # 仅列出当期之后的
                    _periods_next = []
                    for _k, (ii, _pe, _pv, _nv, _sm) in enumerate(hits, 1):
                        if _nv == _pos:
                            _pp = ser[ii + len(base)][0] if ii + len(base) < len(ser) else "-"
                            _periods_next.append(_pp)
                    if _periods_next:
                        _lines.append(f"  第{_pos}位（{len(_periods_next)}次）："
                                      + "、".join(_periods_next[:15])
                                      + ("…" if len(_periods_next) > 15 else ""))
            _report = "\n".join(_lines)

            st.markdown("**文本报告（可复制/保存）**")
            st.text_area("位置序列报告", value=_report, height=320,
                         key="cv_seq_report", label_visibility="collapsed")
            st.download_button("📥 下载报告", _report.encode("utf-8-sig"),
                               file_name=f"位置序列_升序第{which}球.txt",
                               mime="text/plain", key="cv_seq_dl")

            from collections import Counter as _C
            if nxt:
                st.markdown("**【触发行之后的取值分布】**（位置 1~6 出现次数）")
                dist = [{"位置": f"第{i}位", "次数": nxt.get(i, 0),
                         "占比": f"{nxt.get(i,0)/sum(nxt.values())*100:.1f}%"}
                        for i in range(1, 7)]
                st.dataframe(pd.DataFrame(dist), use_container_width=True,
                             hide_index=True)
                st.caption("「之后的取值」= 该排列出现后，更早一期的位置值（新→旧方向）。")

            # ---------- 选期号回测 ----------
        st.markdown("**选期号回测：拿某一期做验证**")
        _rc1, _rc2 = st.columns([2, 1])
        with _rc1:
            _recent = [x[0] for x in list(reversed(seq))[:200]]
            _tgt = st.selectbox("选择要回测的期号（该期之后的数据不使用）",
                                _recent, index=0, key="cv_seq_tgt")
        with _rc2:
            st.write("")
            _bt_go = st.button("▶ 回测这一期", key="cv_seq_bt", use_container_width=True)

        if _bt_go:
            _r = backtest_period(seq, int(which), int(rows_n), _tgt)
            if _r is None:
                st.error("没找到这一期")
            elif _r.get("error"):
                st.warning(_r["error"])
            else:
                st.markdown(f"**{_tgt} 期回测**")
                st.write(f"基准排列（{len(_r['base'])}行）："
                         + " → ".join(str(x) for x in _r["base"]))
                _tpos = [x[0] for x in seq].index(_tgt)
                _brows = [(seq[j][0], seq[j][1][int(which) - 1],
                           seq[j][2][:6].index(seq[j][1][int(which) - 1]) + 1)
                          for j in range(_tpos - int(rows_n), _tpos)]
                st.markdown("**" + base_line(_brows, which) + "**")
                st.write(f"历史相同排列：**{len(_r['hits'])} 段**")
                if _r["dist"]:
                    _tot = sum(_r["dist"].values())
                    st.write("后续位置分布：" + "　".join(
                        f"第{i}位 {_r['dist'].get(i,0)}次({_r['dist'].get(i,0)/_tot*100:.0f}%)"
                        for i in range(1, 7)))
                    st.write(f"预测位置：**第{_r['pred']}位**　"
                             f"实际位置：**第{_r['actual']}位**")
                    if _r["hit"]:
                        st.success("✅ 预测正确")
                    else:
                        st.error("❌ 预测不符（本方法允许错期）")
                    if _r["hits"]:
                        _rows_h = []
                        for k, h in enumerate(_r["hits"][:30], 1):
                            _rows_h.append({
                                "序": k,
                                "期号范围": f"{h['periods'][0]} ~ {h['periods'][-1]}",
                                "之后的位置": h["next"],
                            })
                        st.dataframe(pd.DataFrame(_rows_h), use_container_width=True,
                                     hide_index=True)
                else:
                    st.warning("该期的基准排列在历史中没有出现过，无法回测")

        if H.get("board_add"):
                if st.button("📌 推送到 AI 推演看板", key="cv_seq_push"):
                    txt = (f"【位置序列】升序第{which}球在按序中的位置\n"
                           f"基准排列({len(base)}行)：{base}\n"
                           f"历史出现 {len(hits)} 次\n")
                    for k, (i, periods, pv, nv, _sm) in enumerate(hits[:30], 1):
                        txt += (f"  触发行{k}: 行{i+1}-{i+len(base)} "
                                f"({periods[-1]}~{periods[0]}) 上一行={pv} 下一行={nv}\n")
                    H["board_add"]("位置序列", f"升序第{which}球 → 按序位置", txt)
                    st.success("已推送到看板")
        else:
            st.info("历史中没有出现过完全相同的排列，可以把行数调小或换一个球位试试。")

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
