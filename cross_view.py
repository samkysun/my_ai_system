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


def _row_index(rows):
    """期号 -> 该期在文件里的行号（从 1 开始，含表头行）"""
    out = {}
    for i, r in enumerate(rows):
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}".strip()
        if p and p not in out:
            out[p] = i + 1
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


def position_series(seq, which=1, direction="up2an"):
    """up2an：升序第N球的号码 → 它在按序中的位置
       an2up：按序第N球的号码 → 它在升序中的排名(第几小)"""
    out = []
    for p, u, a in reversed(seq):
        try:
            if direction == "up2an":
                val = u[which - 1]
                pos = a[:6].index(val) + 1
            else:
                val = a[which - 1]
                pos = sorted(u[:6]).index(val) + 1
        except Exception:
            continue
        out.append((p, val, pos))
    return out


def base_line(rows, which, direction="up2an"):
    """基准列：升序N球XX：按序M球 / 按序N球XX：升序第M位"""
    if not rows:
        return ""
    chrono = list(reversed(rows))          # 旧 -> 新 展示
    if direction == "up2an":
        seg = "，".join(f"升序{which}球{r[1]:02d}：按序{r[2]}球" for r in chrono)
    else:
        seg = "，".join(f"按序{which}球{r[1]:02d}：升序第{r[2]}位" for r in chrono)
    span = "、".join(r[0] for r in chrono)
    return f"基准期 {span}（共{len(chrono)}期）：基准列：{seg}"


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
    hits.sort(key=lambda x: x[0])          # 按时间排列，不再截断
    return hits if top_n is None else hits[:top_n]


def backtest_period(seq, which, rows_n, target, direction="up2an"):
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
            if direction == "up2an":
                posv.append(a[:6].index(u[which - 1]) + 1)
            else:
                posv.append(sorted(u[:6]).index(a[which - 1]) + 1)
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


def print_block(report_text, key="cv_print"):
    """打印按钮：隐藏 iframe，只打印报告内容"""
    import base64 as _b64
    import html as _html
    import streamlit.components.v1 as _comp
    _body = ("<html><head><meta charset='utf-8'><style>"
             "@page{margin:12mm}"
             "body{font-family:Consolas,'Microsoft YaHei',monospace;padding:12px}"
             "pre{white-space:pre-wrap;word-break:break-word;font-size:15px;"
             "line-height:1.9;text-align:left}</style></head><body><pre>"
             + _html.escape(report_text) + "</pre></body></html>")
    _b = _b64.b64encode(_body.encode("utf-8")).decode()
    _comp.html(f"""
    <div style="text-align:center">
      <button onclick="pr()" style="width:100%;padding:9px;background:#ffffff;
        color:#111827;border:1px solid rgba(49,51,63,0.2);border-radius:8px;
        cursor:pointer;font-size:14px;">🖨️ 打印</button>
    </div>
    <script>
    function d(s) {{
      return decodeURIComponent(Array.prototype.map.call(atob(s), function(c) {{
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }}).join(''));
    }}
    function pr() {{
      var h = d("{_b}");
      var f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
      document.body.appendChild(f);
      var x = f.contentWindow.document;
      x.open(); x.write(h); x.close();
      setTimeout(function() {{ f.contentWindow.focus(); f.contentWindow.print(); }}, 400);
    }}
    </script>""", height=44, scrolling=False)


def solve_matching(forbid_up, forbid_an=None, required=None):
    """forbid_up: {升序位1-6: [不能落的按序位...]}
       返回 (合法排列列表, 信息)  排列 = 升序位1..6 各自落在的按序位"""
    import itertools as _it
    banned = set()
    for j, lst in (forbid_up or {}).items():
        for i in lst:
            banned.add((int(j), int(i)))
    for i, lst in (forbid_an or {}).items():
        for j in lst:
            banned.add((int(j), int(i)))

    req = {int(j): int(i) for j, i in (required or {}).items() if i}
    sols = []
    for perm in _it.permutations(range(1, 7)):
        ok = True
        for j in range(1, 7):
            if (j, perm[j - 1]) in banned:
                ok = False
                break
            if j in req and perm[j - 1] != req[j]:
                ok = False
                break
        if ok:
            sols.append(perm)
    return sols, banned


def render(df_data, H):
    st.title("🔀 升降交集")
    st.caption("「升序」是 6 个平码从小到大排列 + 特码；「按序」是落球顺序。"
               "同一期的前 6 个号是同一组数，两套候选取交集能压缩范围。")

    load = H["load_excel_data"]
    netok = H.get("netok")

    # ---------- 数据缓存：同一会话只解析一次 ----------
    import time as _t
    _ck = "cv_cache_v1"
    _ttl = 1800
    _c = st.session_state.get(_ck)
    _need = (_c is None) or (_t.time() - _c.get("ts", 0) > _ttl)

    _c1, _c2 = st.columns([3, 1])
    with _c2:
        if st.button("🔄 重新载入数据", key="cv_reload", use_container_width=True):
            st.session_state.pop(_ck, None)
            st.rerun()

    if _need:
        with st.spinner("首次载入数据（约 5~15 秒，之后会变快）…"):
            rows_up = load(_UP_FILE, None) or []
            rows_an = load(_AN_FILE, None) or []
            if not rows_up or not rows_an:
                st.error("读不到数据文件")
                return
            up, an = _parse(rows_up), _parse(rows_an)
            _rowno_up = _row_index(rows_up)
            _rowno_an = _row_index(rows_an)
            seq = _aligned(up, an)
            st.session_state[_ck] = {
                "seq": seq, "row_up": _rowno_up, "row_an": _rowno_an,
                "up": up, "an": an, "ts": _t.time(),
            }
    _c = st.session_state.get(_ck)
    if not _c:
        st.error("数据载入失败")
        return
    seq = _c["seq"]
    _rowno_up, _rowno_an = _c["row_up"], _c["row_an"]
    if not seq:
        st.error("两套数据没有可对齐的期")
        return

    # ---------- 数据范围 ----------
    _rng_c1, _rng_c2 = st.columns([1, 3])
    with _rng_c1:
        _range = st.selectbox("数据范围", ["2023年后（干净）", "全部历史"],
                              index=0, key="cv_range")
    _seq_all = seq
    if _range.startswith("2023"):
        seq = [x for x in seq if x[0][:4] >= "2023"]
    with _rng_c2:
        st.caption(f"可对齐期数：{len(seq)}（{seq[0][0] if seq else '—'} ~ "
                   f"{seq[-1][0] if seq else '—'}）"
                   f"　｜　缓存 {int(_t.time()-_c['ts'])} 秒前"
                   f"　｜　全库可对齐 {len(_seq_all)} 期")
        if _range.startswith("2023"):
            st.caption("⚠️ 已剔除 2019 年前数据：早期「按序」第6球有 100% 是最大值的拼接痕迹，"
                       "会污染排列统计。")
    if not seq:
        st.error("该范围内没有可用数据")
        return

    c1, c2 = st.columns([1, 1])
    with c1:
        k = st.slider("每个位置取前几个候选", 3, 20, 8, 1, key="cv_k")
    with c2:
        mode = st.radio("模式", ["预测下一期", "回测对比", "位置序列", "配位求解"],
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
        st.caption("先选目标期号，用它之前的若干行做基准排列，再去历史里找 100% 相同的排列。")

        # ---------- 目标期号 ----------
        _periods = [x[0] for x in seq]
        _next_p = "—"
        try:
            _next_p = str(int(_periods[-1]) + 1)
        except Exception:
            pass
        _choices = [_next_p] + list(reversed(_periods[-300:]))

        _q1, _q2, _q3, _q4 = st.columns([1, 1, 1, 1])
        with _q1:
            _dir_label = st.selectbox("方向", ["升序 → 按序", "按序 → 升序"],
                                      index=0, key="cv_dir")
            direction = "up2an" if _dir_label.startswith("升序") else "an2up"
        with _q2:
            _tgt = st.selectbox(f"目标期号（下一期 {_next_p}）", _choices,
                                index=0, key="cv_tgt")
        with _q3:
            which = st.selectbox(
                "升序第几球" if direction == "up2an" else "按序第几球",
                [1, 2, 3, 4, 5, 6], index=0, key="cv_which")
        with _q4:
            rows_n = st.number_input("基准行数", 2, 20, 3, 1, key="cv_rows")

        # ---------- 序列与目标位置 ----------
        ser = position_series(seq, int(which), direction)          # 新 -> 旧
        chrono = list(reversed(ser))                               # 旧 -> 新
        _posv = [x[2] for x in chrono]
        _pere = [x[0] for x in chrono]

        if _tgt in _pere:
            _pos = _pere.index(_tgt)
            _note = f"（该期已开奖，回测）"
        else:
            _pos = len(chrono)
            _note = "（该期未开奖，预测）"

        if _pos < int(rows_n):
            st.warning("目标期之前的数据不足，无法取基准行")
            return

        _base_idx = list(range(_pos - int(rows_n), _pos))
        _base = [_posv[i] for i in _base_idx]
        _base_rows = [(chrono[i][0], chrono[i][1], chrono[i][2]) for i in _base_idx]

        st.markdown(f"**目标期号：{_tgt}** {_note}")
        st.markdown("**" + base_line(_base_rows, int(which), direction) + "**")
        st.markdown(f"**基准排列（{len(_base)}行）**：" + " → ".join(str(x) for x in _base))

        # ---------- 历史匹配（只用目标期之前的） ----------
        _hits = []
        for i in range(0, _pos - int(rows_n)):
            if _posv[i:i + int(rows_n)] != _base:
                continue
            # 上 = 向上一行（更新的期）；下 = 向下一行（更旧的期）
            _p_up = chrono[i + int(rows_n)][0] if i + int(rows_n) < len(chrono) else "-"
            _p_dn = chrono[i - 1][0] if i - 1 >= 0 else "-"
            _up = _posv[i + int(rows_n)] if i + int(rows_n) < len(chrono) else None
            _dn = _posv[i - 1] if i - 1 >= 0 else None
            _seg = [(chrono[j][0], chrono[j][1], chrono[j][2])
                    for j in range(i, i + int(rows_n))]
            _hits.append({"i": i, "up": _up, "up_p": _p_up,
                          "dn": _dn, "dn_p": _p_dn, "seg": _seg})

        st.markdown(f"**【触发行】**：历史中 100% 相同的排列共 **{len(_hits)}** 段（不允许错位）")

        if _pos < len(chrono):
            _actual = _posv[_pos]
            _act_p = _tgt
        else:
            _actual, _act_p = None, None

        if _hits:
            _rows_t = []
            for k, h in enumerate(_hits[:60], 1):
                _ro = (_rowno_up if direction == "up2an" else _rowno_an)
                _r1 = _ro.get(h["seg"][0][0], "-")
                _r2 = _ro.get(h["seg"][-1][0], "-")
                try:
                    _ra, _rb = sorted([int(_r1), int(_r2)])
                    _rspan = f"{_ra}~{_rb}"
                except Exception:
                    _rspan = "-"
                _rows_t.append({
                    "序": k,
                    "文件行号": _rspan,
                    "期数": "、".join(r[0] for r in h["seg"]),
                    "上": f"{h['up']}({h['up_p']}期)" if h["up"] is not None else "-",
                    "下": f"{h['dn']}({h['dn_p']}期)" if h["dn"] is not None else "-",
                })
            st.dataframe(pd.DataFrame(_rows_t), use_container_width=True, hide_index=True)

            from collections import Counter as _C
            _dist = _C(h["dn"] for h in _hits if h["dn"] is not None)
            _tot = sum(_dist.values()) or 1
            _rows_d = [{"位置": f"第{i}位", "次数": _dist.get(i, 0),
                        "占比": f"{_dist.get(i,0)/_tot*100:.1f}%",
                        "期数": "、".join(h["dn_p"] for h in _hits if h["dn"] == i)[:80]}
                       for i in range(1, 7)]
            st.markdown("**【触发行之后的位置分布（含期数）】**")
            st.dataframe(pd.DataFrame(_rows_d), use_container_width=True, hide_index=True)

            # 文本报告
            _lines = [f"========== 目标期 {_tgt} {_note} ==========",
                      base_line(_base_rows, int(which), direction),
                      f"【基准排列】({len(_base)}行): " + " → ".join(str(x) for x in _base),
                      f"【历史命中】: {len(_hits)} 段 100% 相同", ""]
            for k, h in enumerate(_hits[:60], 1):
                _det = ("，".join(
                    (f"升序{which}球{r[1]:02d}：按序{r[2]}球" if direction == "up2an"
                     else f"按序{which}球{r[1]:02d}：升序第{r[2]}位") for r in reversed(h["seg"])))
                _ro2 = (_rowno_up if direction == "up2an" else _rowno_an)
                _rr1 = _ro2.get(h["seg"][0][0], "-")
                _rr2 = _ro2.get(h["seg"][-1][0], "-")
                try:
                    _na, _nb = sorted([int(_rr1), int(_rr2)])
                    _rspan2 = f"{_na}~{_nb}"
                except Exception:
                    _rspan2 = "-"
                _lines.append(
                    f"触发行{k}：行{_rspan2}({len(_base)}期): "
                    f"上:{h['up']}({h['up_p']}期) 下:{h['dn']}({h['dn_p']}期)"
                    f"　[{'、'.join(r[0] for r in h['seg'])}]")
                _lines.append(f"　　　　　{h['seg'][0][0]}：{_det}")
            if _dist:
                _lines.append("")
                _lines.append("【触发行之后的位置分布】")
                _lines.append("  " + "　".join(
                    f"第{i}位:{_dist.get(i,0)}次({_dist.get(i,0)/_tot*100:.0f}%)"
                    for i in range(1, 7)))
            _report = "\n".join(_lines)
            st.text_area("位置序列报告", value=_report, height=340,
                         key="cv_seq_report", label_visibility="collapsed")
            st.download_button("📥 下载报告", _report.encode("utf-8-sig"),
                               file_name=f"位置序列_{_tgt}.txt", mime="text/plain",
                               key="cv_seq_dl")

            if _actual is not None:
                _pred = _dist.most_common(1)[0][0] if _dist else None
                st.markdown(f"**实际（{_act_p}）：第{_actual}位**　"
                            f"**预测：第{_pred}位**　"
                            + ("✅ 命中" if _pred == _actual else "❌ 不符"))
        else:
            st.info("历史中没有出现 100% 相同的排列，可以把基准行数调小试试。")

    elif mode == "配位求解":
        st.markdown("### 配位求解")
        st.caption("6 个升序位置对应 6 个按序位置（一个排列，共 720 种）。"
                   "下面填「不能落在」的条件，程序枚举出所有合法排列。")

        _DEF_UP = {1: [3, 5], 2: [1, 2, 3, 4], 3: [4], 4: [2], 5: [1], 6: [1, 2, 6]}
        _DEF_AN = {1: [5], 2: [1, 2], 3: [2, 3, 4, 5], 4: [3], 5: [1, 4], 6: [6]}

        _ver = st.session_state.get("cv_ver", 0)
        st.markdown("**升序各球位：不能落在按序的哪几球**")
        _cols = st.columns(6)
        _f_up = {}
        for j in range(1, 7):
            with _cols[j - 1]:
                _f_up[j] = st.multiselect(
                    f"升序{j}球", [1, 2, 3, 4, 5, 6],
                    default=_DEF_UP.get(j, []), key=f"cv_fu{j}_{_ver}")

        st.markdown("**按序各球位：不能落在升序的哪几球**")
        _cols2 = st.columns(6)
        _f_an = {}
        for i in range(1, 7):
            with _cols2[i - 1]:
                _f_an[i] = st.multiselect(
                    f"按序{i}球", [1, 2, 3, 4, 5, 6],
                    default=_DEF_AN.get(i, []), key=f"cv_fa{i}_{_ver}")

        st.markdown("**正向约束：某升序位必须落在按序第几球（可选）**")
        _cols3 = st.columns(6)
        _req = {}
        for j in range(1, 7):
            with _cols3[j - 1]:
                _v = st.selectbox(f"升序{j}位", ["任意", 1, 2, 3, 4, 5, 6],
                                  index=0, key=f"cv_rq{j}_{_ver}")
                _req[j] = 0 if _v == "任意" else int(_v)

        st.markdown("**反向约束：某按序位必须来自升序第几球（可选）**")
        _cols4 = st.columns(6)
        _req_an = {}
        for i in range(1, 7):
            with _cols4[i - 1]:
                _v2 = st.selectbox(f"按序{i}位", ["任意", 1, 2, 3, 4, 5, 6],
                                   index=0, key=f"cv_ra{i}_{_ver}")
                _req_an[i] = 0 if _v2 == "任意" else int(_v2)

        _a, _b = st.columns(2)
        with _a:
            if st.button("🔍 计算合法排列", type="primary", key="cv_solve",
                         use_container_width=True):
                # 合并正向约束：升序j必须在按序i / 按序i必须来自升序j（同一个排列约束）
                _req_all = {j: i for j, i in _req.items() if i}
                _conflict = []
                for i, j in _req_an.items():
                    if not j:
                        continue
                    if j in _req_all and _req_all[j] != i:
                        _conflict.append((j, _req_all[j], i))
                    else:
                        _req_all[j] = i
                if _conflict:
                    st.error("正向约束互相冲突：" + "；".join(
                        f"升序第{j}位被要求同时在按序第{a}球和第{b}球"
                        for j, a, b in _conflict))
                _sols, _banned = solve_matching(_f_up, _f_an, _req_all)
                st.session_state["cv_sols"] = _sols
                st.session_state["cv_banned"] = len(_banned)
        with _b:
            if st.button("↩ 恢复示例条件", key="cv_reset", use_container_width=True):
                st.session_state["cv_ver"] = st.session_state.get("cv_ver", 0) + 1
                st.rerun()

        _sols = st.session_state.get("cv_sols")
        if _sols is not None:
            st.divider()
            if not _sols:
                st.error("没有合法排列：这些条件互相冲突，请放宽其中几条")
            else:
                st.success(f"共 {len(_sols)} 种合法排列（禁用组合 {st.session_state.get('cv_banned',0)} 条）")

                # 每个升序位可落在哪些按序位
                _rows1 = []
                for j in range(1, 7):
                    _can = sorted({p[j - 1] for p in _sols})
                    _rows1.append({
                        "升序位": f"第{j}位",
                        "可能落在按序": " ".join(f"第{i}球" for i in _can) or "无",
                        "候选数": len(_can),
                    })
                st.markdown("**【升序位 → 按序候选】**")
                st.dataframe(pd.DataFrame(_rows1), use_container_width=True, hide_index=True)

                # 每个按序位可来自哪些升序位
                _rows2 = []
                for i in range(1, 7):
                    _can = sorted({j for j in range(1, 7)
                                   for p in _sols if p[j - 1] == i})
                    _rows2.append({
                        "按序位": f"第{i}球",
                        "可能来自升序": " ".join(f"第{j}位" for j in _can) or "无",
                        "候选数": len(_can),
                    })
                st.markdown("**【按序位 ← 升序来源】**")
                st.dataframe(pd.DataFrame(_rows2), use_container_width=True, hide_index=True)

                # 明细
                with st.expander(f"全部 {len(_sols)} 种合法排列", expanded=False):
                    _rows3 = []
                    for k, p in enumerate(_sols[:200], 1):
                        _rows3.append({"序": k,
                                       **{f"升序{j}": f"按序{p[j-1]}"
                                          for j in range(1, 7)}})
                    st.dataframe(pd.DataFrame(_rows3), use_container_width=True,
                                 hide_index=True)

                # ---------- 历史回测 ----------
                st.markdown("**历史回测：这些约束在历史上成立多少期**")
                _bc1, _bc2 = st.columns([1, 2])
                with _bc1:
                    _bt_n = st.number_input("回测期数", 20, 1000, 200, 20,
                                            key="cv_solve_bt_n")
                with _bc2:
                    st.write("")
                    _bt = st.button("▶ 开始回测", key="cv_solve_bt")

                if _bt:
                    _set = set(_sols)
                    _tot = 0
                    _ok = 0
                    _rows_bt = []
                    _seq_now = st.session_state.get("cv_cache_v1", {}).get("seq") or seq
                    for _p, _u, _a in list(reversed(_seq_now))[:int(_bt_n)]:
                        try:
                            _perm = tuple(_a[:6].index(_u[j - 1]) + 1 for j in range(1, 7))
                        except Exception:
                            continue
                        _tot += 1
                        _in = _perm in _set
                        if _in:
                            _ok += 1
                        _rows_bt.append({
                            "期号": _p,
                            "实际排列": " ".join(str(x) for x in _perm),
                            "符合约束": "✅" if _in else "❌",
                        })
                    if _tot:
                        _rand = len(_sols) / 720 * 100
                        st.success(f"最近 {_tot} 期：符合约束 {_ok} 期 = "
                                   f"{_ok/_tot*100:.1f}%（随机基线 {_rand:.1f}%）")
                        with st.expander("逐期明细", expanded=False):
                            st.dataframe(pd.DataFrame(_rows_bt),
                                         use_container_width=True, hide_index=True)

                # ---------- 文本报告 + 打印 ----------
                _rl = ["========== 配位求解报告 ==========", ""]
                _rl.append("【不在约束】")
                for j in range(1, 7):
                    if _f_up.get(j):
                        _rl.append(f"  升序{j}球 不能在按序: "
                                   + "、".join(str(x) for x in _f_up[j]))
                for i in range(1, 7):
                    if _f_an.get(i):
                        _rl.append(f"  按序{i}球 不能在升序: "
                                   + "、".join(str(x) for x in _f_an[i]))
                _rl.append("")
                _rl.append("【必须在约束】")
                _any_req = False
                for j in range(1, 7):
                    if _req.get(j):
                        _rl.append(f"  升序{j}位 必须在 按序第{_req[j]}球")
                        _any_req = True
                for i in range(1, 7):
                    if _req_an.get(i):
                        _rl.append(f"  按序{i}位 必须来自 升序第{_req_an[i]}位")
                        _any_req = True
                if not _any_req:
                    _rl.append("  （无）")
                _rl.append("")
                _rl.append(f"【合法排列】共 {len(_sols)} 种")
                _rl.append("")
                _rl.append("【升序位 → 按序候选】")
                for r in _rows1:
                    _rl.append(f"  {r['升序位']} → {r['可能落在按序']}（{r['候选数']} 个）")
                _rl.append("")
                _rl.append("【按序位 ← 升序来源】")
                for r in _rows2:
                    _rl.append(f"  {r['按序位']} ← {r['可能来自升序']}（{r['候选数']} 个）")
                _rl.append("")
                _rl.append("【全部合法排列】（升序1~6位各自落在按序第几球）")
                for k, _p in enumerate(_sols, 1):
                    _rl.append(f"  {k:>3}. " + " ".join(str(x) for x in _p))
                _report = "\n".join(_rl)

                st.markdown("**报告（可编辑 / 下载 / 打印）**")
                st.text_area("配位报告", value=_report, height=300,
                             key="cv_solve_report", label_visibility="collapsed")
                _pc1, _pc2 = st.columns(2)
                with _pc1:
                    st.download_button("📥 下载 TXT", _report.encode("utf-8-sig"),
                                       file_name="配位求解.txt", mime="text/plain",
                                       use_container_width=True, key="cv_solve_dl")
                with _pc2:
                    print_block(_report)

                if H.get("board_add"):
                    if st.button("📌 推送到 AI 推演看板", key="cv_solve_push"):
                        _txt = f"【配位求解】合法排列 {len(_sols)} 种\n"
                        for r in _rows1:
                            _txt += f"  {r['升序位']} → {r['可能落在按序']}\n"
                        H["board_add"]("配位求解", f"{len(_sols)} 种合法排列", _txt)
                        st.success("已推送到看板")

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
