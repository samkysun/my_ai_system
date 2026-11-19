# -*- coding: utf-8 -*-
"""计算中心 v5 —— 全量触发行查档

流程：
  ① 把看板里【所有】触发行抓出来（几百条）
  ② 按（球位+匹配串）去重，得到"形态"
  ③ 每个形态在【升序+按序】历史里查它出现过几次，以及每次之后开出了什么
     （排除它自己那一处，避免自匹配）
  ④ 按球位汇总"后续开出的号码"热度
  ⑤ 叠加：深度联动保留法 + 写板删除法 + 遗漏倍率
  ⑥ 交给 AI 总结（AI 只读结果，不参与计算）
"""
import re
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

_RED = {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46}
_BLUE = {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48}
_GREEN = {5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49}
_RANGE = {1: (1, 20), 2: (2, 25), 3: (3, 30), 4: (4, 40),
          5: (15, 48), 6: (25, 49), 7: (1, 49)}


def _wave(n):
    if n in _RED:
        return "红波"
    if n in _BLUE:
        return "蓝波"
    if n in _GREEN:
        return "绿波"
    return ""


def _numbers_for(attr, value, zmap=None):
    v = re.sub(r"[肖号尾]$", "", str(value).strip())
    out = []
    if attr == "尾数":
        t = re.sub(r"\D", "", v)
        if t:
            out = [n for n in range(1, 50) if str(n)[-1] == t[-1]]
    elif attr == "数字合":
        t = re.sub(r"\D", "", v)
        if t:
            out = [n for n in range(1, 50) if sum(map(int, str(n))) == int(t)]
    elif attr == "门数":
        t = re.sub(r"\D", "", v)
        if t:
            k = int(t)
            lo = 1 if k == 1 else (k - 1) * 10
            hi = 9 if k == 1 else min(lo + 9, 49)
            out = list(range(lo, hi + 1))
    elif attr == "段数":
        t = re.sub(r"\D", "", v)
        if t:
            lo = (int(t) - 1) * 7 + 1
            out = list(range(lo, min(lo + 6, 49) + 1))
    elif attr == "波色":
        out = [n for n in range(1, 50) if _wave(n) == v]
    elif attr in ("生肖", "数字五行", "生肖五行", "尾五行") and zmap:
        mp = zmap.get(attr) or {}
        out = [n for n, z in mp.items() if re.sub(r"[肖号尾]$", "", str(z)) == v]
    elif attr == "波单双":
        w = next((x for x in ("红波", "蓝波", "绿波") if v.startswith(x)), "")
        parity = "单" if "单" in v else ("双" if "双" in v else "")
        out = [n for n in range(1, 50)
               if _wave(n) == w and (n % 2 == 1) == (parity == "单")]
    return out


# ---------------- 解析 ----------------
_AUTO_T = re.compile(r"=+\s*(\d{5,8})期(升序|按序)-(.+?)(\d)球\s*=+")
_T_OLD = re.compile(r"=+\s*(升序全套|按序全套)\s*-\s*(\d{5,8})\s*-\s*(.+?)\s*-\s*第(\d)球\s*=+")
_LINK_T = re.compile(r"=+\s*(升序|按序)(.+?)\s*\d?码?联动分析\s*=+")
_LINE_AUTO = re.compile(
    r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+)行\)"
    r"[^\n]*?上:(.*?)\s*\(匹配:(.*?)\)\s*下:(.*?)(?:\s*\[|$)")
_LINE_LINK = re.compile(r"^第(\d)球[:：]\s*(.+?)(?:\||$)")


def _blocks(text):
    out, cur = [], None
    for ln in str(text).splitlines():
        if ln.startswith("====="):
            cur = {"head": ln, "lines": []}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)
    return out


def collect(texts):
    """收集全部触发行(删除法)与保留值(保留法)，兼容两种标题格式"""
    if isinstance(texts, str):
        texts = [texts]
    kill, keep = [], []
    for tx in texts:
        for b in _blocks(tx):
            head = b["head"]
            period = attr = None
            ball = None
            m = _AUTO_T.search(head)
            if m:
                period, attr, ball = m.group(1), m.group(3).strip(), int(m.group(4))
            else:
                m2 = _T_OLD.search(head)
                if m2:
                    period, attr, ball = m2.group(2), m2.group(3).strip(), int(m2.group(4))

            if attr is not None:
                for ln in b["lines"]:
                    mm = _LINE_AUTO.search(ln)
                    if not mm:
                        continue
                    kill.append({
                        "attr": attr, "ball": int(mm.group(1)), "col": mm.group(2),
                        "a": int(mm.group(3)), "b": int(mm.group(4)),
                        "n": int(mm.group(5)), "match": mm.group(7),
                        "down": mm.group(8).strip(), "period": period,
                    })
                continue

            mk = _LINK_T.search(head)
            if mk:
                mode = mk.group(2).strip()
                for ln in b["lines"]:
                    ml = _LINE_LINK.search(ln.strip())
                    if not ml:
                        continue
                    bl = int(ml.group(1))
                    seg = ml.group(2).split("杀(")[0]
                    for v in re.split(r"[,，、]", seg):
                        v2 = re.sub(r"[✔✓\s]", "", v)
                        if v2:
                            keep.append({"attr": mode, "ball": bl, "value": v2})
    return kill, keep


def _ball_cols(rows):
    """{球位: [每期号码]}（从新到旧）"""
    out = {}
    for b in range(1, 8):
        i10 = 3 + (b - 1) * 30
        i1 = i10 + 1
        col = []
        for r in rows[2:]:
            if len(r) <= i1:
                col.append(None)
                continue
            try:
                col.append(int((r[i10].strip() + r[i1].strip()) or 0))
            except Exception:
                col.append(None)
        out[b] = col
    return out


def _attr_col(rows, ball, col_letter):
    from openpyxl.utils import column_index_from_string
    idx = column_index_from_string(col_letter) - 1
    out = []
    for r in rows[2:]:
        out.append(r[idx].strip() if idx < len(r) else "")
    return out


def _find_after(col, seq, skip=None):
    """在 col 里找 seq 出现的位置，返回其后一个值列表（skip=(起始索引) 要排除）"""
    n = len(seq)
    if n == 0:
        return []
    pos = defaultdict(list)
    for i, v in enumerate(col):
        pos[v].append(i)
    res = []
    for i in pos.get(seq[0], []):
        if skip is not None and i == skip:
            continue
        if i + n >= len(col):
            continue
        ok = True
        for k in range(1, n):
            if col[i + k] != seq[k]:
                ok = False
                break
        if ok:
            v = col[i + n]
            if v:
                res.append(v)
    return res


def target_period(texts):
    """从写板标题里取期号（没有就返回空）"""
    if isinstance(texts, str):
        texts = [texts]
    best = ""
    for tx in texts:
        for b in _blocks(tx):
            head = b["head"]
            m = _AUTO_T.search(head)
            if m:
                best = m.group(1)
                break
            m2 = _T_OLD.search(head)
            if m2:
                best = m2.group(2)
                break
        if best:
            break
    return best


def _build_maps(rows, year):
    maps = {"生肖": {}, "数字五行": {}, "生肖五行": {}, "尾五行": {}}
    for r in rows[2:]:
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}"
        if year and not p.startswith(str(year)):
            continue
        for b in range(7):
            i10 = 3 + (b - 1) * 30
            i1 = i10 + 1
            try:
                num = int((r[i10].strip() + r[i1].strip()) or 0)
            except Exception:
                continue
            if not num:
                continue
            for key, base in (("生肖", 6), ("数字五行", 5), ("生肖五行", 17), ("尾五行", 30)):
                i = base + (b - 1) * 30
                if i < len(r) and r[i].strip():
                    maps[key].setdefault(num, r[i].strip())
    return maps


def _omission_rates(series):
    stat = defaultdict(lambda: [0, 0])
    omi = {n: 0 for n in range(1, 50)}
    for v in series:
        for n in range(1, 50):
            k = omi[n]
            stat[k][1] += 1
            if v == n:
                stat[k][0] += 1
        for n in range(1, 50):
            omi[n] = 0 if n == v else omi[n] + 1
    return {k: (a / b if b else 0.0) for k, (a, b) in stat.items()}


def _cur_omission(series):
    out = {}
    for n in range(1, 50):
        idx = len(series)
        for i, v in enumerate(series):
            if v == n:
                idx = i
                break
        out[n] = idx
    return out


def _backtest_table(rows, n_test=600, start=300, prog=None):
    """滚动回测：边际热 / 查档 / 组合 / 随机，四者对比"""
    RNG = _RANGE

    def series(ball):
        i10 = 3 + (ball - 1) * 30
        i1 = i10 + 1
        out = []
        for r in rows[2:]:
            if len(r) <= i1:
                continue
            try:
                out.append(int((r[i10].strip() + r[i1].strip()) or 0))
            except Exception:
                pass
        return out

    def attr_of(n, kind):
        if kind == "尾数":
            return n % 10
        if kind == "数字合":
            return sum(map(int, str(n)))
        return 1 if n <= 9 else min(5, (n - 1) // 10 + 1)

    def nums_for(kind, v, lo, hi):
        if kind == "尾数":
            return [n for n in range(lo, hi + 1) if n % 10 == v]
        if kind == "数字合":
            return [n for n in range(lo, hi + 1) if sum(map(int, str(n))) == v]
        return [n for n in range(lo, hi + 1) if attr_of(n, "门数") == v]

    L = 6
    out = []
    tot = {"q": [0, 0], "m": [0, 0], "c": [0, 0], "u": 0.0}
    for b in range(1, 8):
        if prog:
            prog(b / 7.0, text=f"回测第{b}球…")
        seq = series(b)
        lo, hi = RNG[b]
        attrs = {k: [attr_of(n, k) for n in seq] for k in ("尾数", "数字合", "门数")}
        hq = hm = hc = 0
        cnt = 0
        for t_ in range(start, min(len(seq) - 1, start + n_test)):
            actual = seq[t_]
            if not actual:
                continue
            cnt += 1
            votes = Counter()
            for kind, arr in attrs.items():
                if t_ < L:
                    continue
                pat = arr[t_ - L:t_]
                for i in range(2, t_ - L):
                    if arr[i:i + L] == pat:
                        for num in nums_for(kind, arr[i + L], lo, hi):
                            votes[num] += 1
            top_q = [n for n, _ in votes.most_common(3)]
            c = Counter(x for x in seq[:t_] if x and lo <= x <= hi)
            for n in range(lo, hi + 1):
                c.setdefault(n, 0)
            top_m = [n for n, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
            blend = Counter()
            mv = max(votes.values()) if votes else 1
            mc = max(c.values()) or 1
            for n in range(lo, hi + 1):
                blend[n] = votes.get(n, 0) / mv + 0.5 * c.get(n, 0) / mc
            top_c = [n for n, _ in blend.most_common(3)]
            hq += actual in top_q
            hm += actual in top_m
            hc += actual in top_c
        if not cnt:
            continue
        for k, h in (("q", hq), ("m", hm), ("c", hc)):
            tot[k][0] += h
            tot[k][1] += cnt
        tot["u"] += 3.0 / (hi - lo + 1) * cnt
        out.append({"球位": f"第{b}球",
                    "查档": f"{hq/cnt*100:.1f}%",
                    "边际热": f"{hm/cnt*100:.1f}%",
                    "组合": f"{hc/cnt*100:.1f}%",
                    "随机": f"{3.0/(hi-lo+1)*100:.1f}%",
                    "样本": cnt})
    if tot["q"][1]:
        n_ = tot["q"][1]
        out.append({"球位": "合计",
                    "查档": f"{tot['q'][0]/n_*100:.1f}%",
                    "边际热": f"{tot['m'][0]/n_*100:.1f}%",
                    "组合": f"{tot['c'][0]/n_*100:.1f}%",
                    "随机": f"{tot['u']/n_*100:.1f}%",
                    "样本": n_})
    return out


def _threshold_sweep(rows, thresholds=(0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)):
    """阈值扫描（无前视：用前 70% 建表，后 30% 评估）"""
    RNG = _RANGE

    def series(ball):
        i10 = 3 + (ball - 1) * 30
        i1 = i10 + 1
        out = []
        for r in rows[2:]:
            if len(r) <= i1:
                continue
            try:
                out.append(int((r[i10].strip() + r[i1].strip()) or 0))
            except Exception:
                pass
        return out

    stat_all = {th: {"kill": 0, "wrong": 0, "periods": 0} for th in thresholds}

    for b in range(1, 8):
        seq = series(b)
        if len(seq) < 200:
            continue
        lo, hi = RNG[b]
        base = 1.0 / max(1, hi - lo + 1)
        cut = int(len(seq) * 0.7)

        # 用前 cut 期建「遗漏 K -> 出现率」表
        rate_stat = {}
        cur = {n: 0 for n in range(lo, hi + 1)}
        for v in seq[:cut]:
            for n in range(lo, hi + 1):
                k = cur[n]
                a, bb = rate_stat.get(k, (0, 0))
                rate_stat[k] = (a + (1 if v == n else 0), bb + 1)
            for n in range(lo, hi + 1):
                cur[n] = 0 if v == n else cur[n] + 1
        rate = {k: (a / c if c >= 5 else None) for k, (a, c) in rate_stat.items()}

        # 后 30% 评估
        omi = {n: 0 for n in range(lo, hi + 1)}
        for idx in range(cut, len(seq)):
            actual = seq[idx]
            if not actual:
                continue
            for th in thresholds:
                killed = [n for n in range(lo, hi + 1)
                          if rate.get(omi[n]) is not None and rate[omi[n]] < base * th]
                if killed:
                    stat_all[th]["periods"] += 1
                    stat_all[th]["kill"] += len(killed)
                    if actual in killed:
                        stat_all[th]["wrong"] += 1
            for n in range(lo, hi + 1):
                omi[n] = 0 if n == actual else omi[n] + 1

    out = []
    for th in thresholds:
        s = stat_all[th]
        if not s["periods"]:
            continue
        avg_kill = s["kill"] / s["periods"]
        prec = 1 - s["wrong"] / s["periods"] / avg_kill if avg_kill else 0
        out.append({
            "阈值(×均分)": th,
            "每期平均杀": round(avg_kill, 1),
            "杀错期数": s["wrong"],
            "总评估期": s["periods"],
            "杀对率": f"{prec*100:.1f}%",
            "杀错率": f"{(1-prec)*100:.1f}%",
        })
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def _period_options(rows_key: str, _rows):
    """从数据里取期号（新→旧），供下拉框用"""
    seen, out = set(), []
    for r in _rows[2:]:
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}".strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _period_list(rows):
    """按从旧到新返回 (期号列表, 各球开奖号序列)"""
    periods, balls = [], {b: [] for b in range(1, 8)}
    for r in rows[2:]:
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}"
        if not p.strip():
            continue
        periods.append(p)
        for b in range(1, 8):
            i10 = 3 + (b - 1) * 30
            i1 = i10 + 1
            try:
                balls[b].append(int((r[i10].strip() + r[i1].strip()) or 0))
            except Exception:
                balls[b].append(0)
    periods.reverse()
    for b in balls:
        balls[b].reverse()
    return periods, balls


def backtest_period(rows, target, k=3):
    """回测指定期号：只用该期之前的数据"""
    periods, balls = _period_list(rows)
    if target not in periods:
        return None, "数据里没有这个期号"
    pos = periods.index(target)
    if pos < 60:
        return None, f"该期之前只有 {pos} 期数据，不足以回测"

    out = []
    for b in range(1, 8):
        lo, hi = _RANGE[b]
        hist = balls[b][:pos]
        c = Counter(x for x in hist if x and lo <= x <= hi)
        for n in range(lo, hi + 1):
            c.setdefault(n, 0)
        top = [n for n, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

        # 遗漏
        omi = {}
        for n in range(lo, hi + 1):
            d = len(hist)
            for j in range(len(hist) - 1, -1, -1):
                if hist[j] == n:
                    d = len(hist) - 1 - j
                    break
            omi[n] = d

        # 累计命中率（历史）
        cum = sum(1 for v in hist if v in top) / (len(hist) or 1)
        actual = balls[b][pos]
        out.append({
            "球位": f"第{b}球",
            "推荐": " ".join(f"{n:02d}" for n in top),
            "实际开出": f"{actual:02d}",
            "命中": "✅" if actual in top else "❌",
            "该组合历史命中率": f"{cum*100:.1f}%",
            "推荐号遗漏": "／".join(f"{n:02d}:{omi[n]}" for n in top),
        })
    n_hit = sum(1 for r in out if r["命中"] == "✅")
    return out, f"{target} 期：{n_hit}/7 个球位命中"


def _prog_rec(balls, periods, target, k=3):
    """用目标期之前的数据给出各球推荐"""
    if target not in periods:
        return None, None
    pos = periods.index(target)
    if pos < 60:
        return None, None
    rec = {}
    for b in range(1, 8):
        lo, hi = _RANGE[b]
        hist = balls[b][:pos]
        c = Counter(x for x in hist if x and lo <= x <= hi)
        for n in range(lo, hi + 1):
            c.setdefault(n, 0)
        rec[b] = [n for n, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]
    actual = {b: balls[b][pos] for b in range(1, 8)}
    return rec, actual


def _ai_picks(call_ai, period, rec):
    """让 AI 按固定格式给每球号码，返回 {球位: [号]}"""
    lines = [f"期号 {period} 的号码推演。以下是程序统计出的各球位历史最常出现的号码："]
    for b in range(1, 8):
        lines.append(f"第{b}球：{' '.join(f'{n:02d}' for n in rec[b])}")
    lines += ["", "请据此给出你的最终推荐，严格按下面格式输出，每行一个球位，只写号码：",
              "第1球: 05 09 12",
              "第2球: …",
              "不要写任何解释、标题或其它内容。"]
    prompt = "\n".join(lines)
    ans = call_ai(prompt, "你是严谨的数据助手，只按指定格式输出，不解释。")
    out = {}
    for ln in str(ans).splitlines():
        m = re.match(r"\s*第\s*([1-7])\s*球\s*[:：]\s*(.+)", ln)
        if m:
            b = int(m.group(1))
            out[b] = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", m.group(2))
                      if 1 <= int(x) <= 49]
    return out


def render(df_data, H):
    st.title("🧮 计算中心")
    st.caption("全量查档：把看板里所有触发行拿到历史里查「之后开出了什么」，"
               "再叠加删除法/保留法/遗漏，最后交给 AI 总结。")

    load = H["load_excel_data"]
    call_ai = H["call_deepseek_api"]

    board = st.session_state.get("ai_board") or []

    with st.expander("🔧 自检（页面没显示内容时先看这里）", expanded=False):
        st.write("版本：v9（含一键全量分析 / 两个滑块 / 回测区）")
        st.write(f"看板条数：{len(board)}")
        st.write(f"是否有 raw_report：{'是' if H.get('raw_report') else '否'}")
        try:
            _test = load("升序全套.csv", None) or []
            st.write(f"读数据：成功，{len(_test)} 行")
        except Exception as _e:
            st.write(f"读数据：失败 {type(_e).__name__}: {_e}")

    one_click = False
    go = False
    self_run = True
    full_mode = True
    kill_th = st.session_state.get("cc_kill_th", 0.8)
    pick_k = st.session_state.get("cc_pick_k", 3)
    picks = []
    _have = bool(st.session_state.get("cc_table"))
    if _have:
        _cA, _cB = st.columns([1, 3])
        with _cA:
            if st.button("🧹 清空结果，重新设置", use_container_width=True,
                         key="cc_clear"):
                for _k in ("cc_table", "cc_scores", "cc_probs", "cc_hits",
                           "cc_counts", "cc_patterns", "cc_bt_table",
                           "cc_sw_table", "cc_answer", "cc_pred_save"):
                    st.session_state.pop(_k, None)
                st.rerun()
        with _cB:
            st.caption("参数已收起（界面保持整洁）。点左边按钮可重新设置并重算。")
    if not _have:
        st.markdown("### 🚀 一键全量分析")
        _o1, _o2 = st.columns([1, 2])
        with _o1:
            one_click = st.button("🚀 开始全量分析（1-7球 × 4~17行）",
                                  type="primary", use_container_width=True, key="cc_one")
        with _o2:
            st.caption("自动跑 7 个球 × 29 个属性的全部对比行数（4~17），自动去重后查档。"
                       "不需要先推送看板。")

        opts = [f"{i+1}. {e['source']} · {e['title']}" for i, e in enumerate(board)]
        c1, c2 = st.columns([4, 1])
        with c1:
            if opts:
                picks = st.multiselect("参与分析的内容（默认全选）", opts, default=opts,
                                       key="cc_picks")
            else:
                picks = []
                st.info("看板还是空的（可不管它，直接用上面的「🚀 开始全量分析」自己跑 1-7 球）")
                st.caption("想让看板有内容：去「多维分析 / 深度联动 / 遗漏核算」点【📌 推送看板】。")
        with c2:
            st.write(""); st.write("")
            go = st.button("🔎 全量查档并评分", type="primary", use_container_width=True, key="cc_go")
        _c1, _c2 = st.columns([1, 1])
        with _c1:
            self_run = st.checkbox("自己跑 1-7 球全部属性（不依赖看板，约 20~40 秒）",
                                   value=True, key="cc_self")
        with _c2:
            full_mode = st.checkbox("全量模式：全部形态都查档（约 1 分钟）",
                                    value=True, key="cc_full")

        _maxk = st.session_state.get("cc_max_k_hint", 20)
        pick_k = st.slider(
            "每球推荐几个号（想看几个就滑到几个，1~20 任意）",
            min_value=1, max_value=20, value=4, step=1, key="cc_pick_k")

        kill_th = st.slider(
            "杀号阈值（×区间均分）：越高杀得越多　—　回测显示 0.8~0.9 性价比较好",
            min_value=0.3, max_value=1.2, value=0.8, step=0.05, key="cc_kill_th")

    if one_click and H.get("raw_report"):
        go = True
        self_run = True

    if go:
        texts = []
        if self_run and H.get("raw_report"):
            _b = st.progress(0.0, text="正在计算 1-7 球…")
            for _i in range(1, 8):
                _b.progress(_i / 8, text=f"正在计算第{_i}球全部属性…")
                try:
                    _tx = H["raw_report"](f"第{_i}球")
                    if _tx:
                        texts.append(_tx)
                except Exception as _e:
                    st.warning(f"第{_i}球计算失败：{_e}")
            _b.empty()
        else:
            texts = [board[int(p.split(".")[0]) - 1]["text"] for p in picks]
        if not texts:
            st.warning("没有可分析的内容（可勾选上面的「自己跑 1-7 球」）")
            return

        kill, keep = collect(texts)
        if not kill and not keep:
            st.error("没解析出触发行/保留值，请确认写板格式。")
            return

        bar = st.progress(0.0, text="准备中…")
        rows_up = load("升序全套.csv", None) or []
        rows_an = load("按序全套.csv", None) or []

        # 映射表：以【被分析期号的年份】为准，不用最新年份
        _tp = target_period(texts)
        if _tp:
            _yr = str(_tp)[:4]
        else:
            _r0 = rows_up[2] if rows_up and len(rows_up) > 2 else None
            try:
                _yr = f"{_r0[213]}{_r0[0]}{_r0[1]}{_r0[2]}"[:4] if _r0 else ""
            except Exception:
                _yr = ""
        zmap_early = _build_maps(rows_up, _yr)
        _cov = len(zmap_early.get("生肖") or {})
        st.caption(f"映射年份：{_yr or '未知'}（按被分析期号所属年份）"
                   f"｜该年生肖映射覆盖 {_cov}/49 个号码")

        # 形态去重
        uniq = {}
        for k in kill:
            key = (k["ball"], k["col"], k["match"])
            if key not in uniq:
                uniq[key] = {"ball": k["ball"], "col": k["col"], "match": k["match"],
                             "attr": k["attr"], "n": k["n"],
                             "times": 0, "downs": Counter(), "windows": []}
            uniq[key]["times"] += 1
            uniq[key]["downs"][k["down"]] += 1
            uniq[key]["windows"].append((k["a"], k["b"], k["period"]))

        # 全量模式：全部形态；快速模式：出现≥3次的前800个
        if full_mode:
            keys = sorted(uniq.keys(), key=lambda k: -uniq[k]["times"])
            st.caption(f"全量模式：{len(keys)} 个形态全部查档（较慢）")
        else:
            MIN_OCC, MAX_PAT = 3, 800
            _f = {k: v for k, v in uniq.items() if v["times"] >= MIN_OCC} or uniq
            keys = sorted(_f.keys(), key=lambda k: -_f[k]["times"])[:MAX_PAT]
            st.caption(f"快速模式：{len(uniq)} 个形态 → 出现≥{MIN_OCC}次的前 {len(keys)} 个")
        total = max(1, len(keys))
        _colcache = {}
        heat = defaultdict(Counter)          # ball -> Counter(number)
        evid = defaultdict(lambda: defaultdict(list))
        pattern_rows = []
        for idx, key in enumerate(keys):
            bar.progress(idx / total, text=f"查档 {idx+1}/{total}：第{key[0]}球 {key[2][:14]}")
            u = uniq[key]
            seq = list(u["match"])
            if len(seq) != u["n"]:
                # 匹配串长度与行数不一致时，按匹配串长度截取
                seq = seq[:u["n"]] if u["n"] <= len(seq) else seq
            ball, col_letter = u["ball"], u["col"]
            if ("up", col_letter) not in _colcache:
                _colcache[("up", col_letter)] = _attr_col(rows_up, ball, col_letter) if rows_up else []
            if ("an", col_letter) not in _colcache:
                _colcache[("an", col_letter)] = _attr_col(rows_an, ball, col_letter) if rows_an else []
            col_up = _colcache[("up", col_letter)]
            col_an = _colcache[("an", col_letter)]
            skip_up = None
            if u["windows"]:
                w0 = u["windows"][0][0]
                skip_up = w0 - 3 if w0 >= 3 else None   # CSV 行号 -> 列表索引
            got = _find_after(col_up, seq, skip_up) + _find_after(col_an, seq, None)
            cnt = Counter(got)
            if not cnt:
                continue
            _hits = sum(cnt.values())
            # 收缩权重：命中次数少的形态权重打折，避免偶然命中放大
            _w = _hits / (_hits + 2.0)
            nums = Counter()
            for v, c in cnt.items():
                for num in _numbers_for(u["attr"], v, zmap_early):
                    nums[num] += c
            for num, c in nums.items():
                heat[ball][num] += c * _w
                evid[ball][num].append((u["attr"], u["match"][:14], _hits))
            pattern_rows.append({
                "球位": f"第{ball}球", "属性": u["attr"], "匹配": u["match"][:24],
                "写板出现": u["times"], "历史命中": sum(cnt.values()),
                "后续分布": "／".join(f"{v}×{c}" for v, c in cnt.most_common(3)),
            })
        bar.progress(1.0, text="查档完成")

        zmap = zmap_early

        # 保留 / 杀
        keep_s, kill_s = defaultdict(Counter), defaultdict(Counter)
        for kp in keep:
            for num in _numbers_for(kp["attr"], kp["value"], zmap):
                keep_s[kp["ball"]][num] += 1
        for k in kill:
            for num in _numbers_for(k["attr"], k["down"], zmap):
                kill_s[k["ball"]][num] += max(1, k["n"])

        # 遗漏修正
        omi_rate, base_rate = {}, {}
        for b in range(1, 8):
            ser = _ball_cols(rows_up)[b] if rows_up else []
            if not ser:
                continue
            omi_rate[b] = _omission_rates(ser)
            lo, hi = _RANGE.get(b, (1, 49))
            base_rate[b] = 1.0 / max(1, hi - lo + 1)

        cols_up = _ball_cols(rows_up) if rows_up else {}
        # 全历史边际频次（每球位每个号码的历史出现率，归一化）
        marg = {}
        for b in range(1, 8):
            _c = Counter(x for x in (cols_up.get(b) or []) if x)
            lo_, hi_ = _RANGE.get(b, (1, 49))
            _mx = max([_c.get(n, 0) for n in range(lo_, hi_ + 1)] or [1]) or 1
            marg[b] = {n: _c.get(n, 0) / _mx for n in range(lo_, hi_ + 1)}

        # 综合
        scores, table = {}, []
        for b in range(1, 8):
            hs, ks, kls = heat.get(b, Counter()), keep_s.get(b, Counter()), kill_s.get(b, Counter())
            th = sum(hs.values()) or 1
            tk = sum(ks.values()) or 1
            tl = sum(kls.values()) or 1
            cur = _cur_omission(cols_up.get(b, [])) if cols_up else {}
            rr = omi_rate.get(b, {})
            bc = base_rate.get(b, 0.02) or 0.02
            lo_, hi_ = _RANGE.get(b, (1, 49))
            cand = [n for n in (set(hs) | set(ks) | set(kls)) if lo_ <= n <= hi_]
            arr = []
            _max_omi = max([cur.get(n, 0) for n in cand] or [1]) or 1
            for n in cand:
                h_ = hs.get(n, 0) / th
                k_ = ks.get(n, 0) / tk
                l_ = kls.get(n, 0) / tl
                mg = marg.get(b, {}).get(n, 0.0)
                kk = cur.get(n, 0)
                om = kk / _max_omi
                _p = rr.get(kk) or 0.0          # 该遗漏期数的历史出现率
                _base = bc
                _kill = 1 if (_p and _p < _base * kill_th) else 0
                sc = 0.05 * h_ + 0.65 * mg + 0.15 * k_ - 0.10 * l_ - 0.05 * om
                if _kill:
                    sc -= 0.15                   # 冷号额外扣分（决定要杀）
                arr.append((n, h_, k_, l_, kk, mg, om, sc, _p, _kill))
            arr.sort(key=lambda x: (x[9], -x[7]))   # 先留后杀
            scores[b] = arr[:8]
            for it in arr[:6]:
                _ev = evid.get(b, {}).get(it[0], [])
                table.append({"球位": f"第{b}球", "号码": f"{it[0]:02d}",
                              "查档热度": round(it[1], 3), "边际频次": round(it[5], 2),
                              "保留分": round(it[2], 2), "杀分": round(it[3], 2),
                              "当前遗漏": it[4],
                              "该遗漏出现率": f"{it[8]*100:.1f}%" if it[8] else "<5样本",
                              "判定": "杀" if it[9] else "留",
                              "命中形态": len(_ev),
                              "综合分": round(it[7], 3),
                              "证据": "；".join(f"{a}·{m}({h}次)" for a, m, h in
                                              sorted(_ev, key=lambda x: -x[2])[:2])})

        st.session_state["cc_scores"] = scores
        st.session_state["cc_table"] = table
        st.session_state["cc_patterns"] = pattern_rows
        st.session_state["cc_counts"] = (len(kill), len(uniq), len(keep))

    # ---------- 预测下一期（未开奖） ----------
    st.divider()
    st.markdown("### 🔮 预测下一期（未开奖）")
    st.caption("用全部历史数据，为下一个期号每个球位给出 4 个号（已避开按当前阈值的杀号）。")
    _nc1, _nc2 = st.columns([1, 3])
    with _nc1:
        _next_go = st.button("🔮 算下一期", use_container_width=True, key="cc_next")
    with _nc2:
        _nk = st.slider("每球覆盖几个号", min_value=1, max_value=7, value=4, step=1,
                        key="cc_next_k")
        st.caption(f"杀号阈值 {kill_th:g} ｜ 用全部历史数据")

    if _next_go:
        _rows_n = load("升序全套.csv", None) or []
        if not _rows_n:
            st.error("读不到 升序全套.csv")
        else:
            _per_n, _balls_n = _period_list(_rows_n)
            _last = _per_n[-1] if _per_n else ""
            try:
                _nxt = str(int(_last) + 1)
            except Exception:
                _nxt = "下一期"
            st.markdown(f"#### 目标期号：{_nxt}（上一期 {_last} 已开奖）")
            _nr = []
            for b in range(1, 8):
                lo, hi = _RANGE[b]
                hist = _balls_n[b]
                c = Counter(x for x in hist if x and lo <= x <= hi)
                for n in range(lo, hi + 1):
                    c.setdefault(n, 0)
                # 杀号
                _rate = _omission_rates(hist)
                _cur = _cur_omission(hist)
                _base = 1.0 / max(1, hi - lo + 1)
                killed = set()
                for n in range(lo, hi + 1):
                    pv = _rate.get(_cur.get(n, 0))
                    if pv is not None and pv < _base * kill_th:
                        killed.add(n)
                # 留下的里按边际热度取前 4
                cand = [(n, c.get(n, 0)) for n in range(lo, hi + 1) if n not in killed]
                cand.sort(key=lambda x: (-x[1], x[0]))
                pick = [n for n, _ in cand[:_nk]]
                cum = sum(1 for v in hist if v in pick) / (len(hist) or 1)
                _nr.append({
                    "球位": f"第{b}球",
                    f"推荐 {_nk} 个": " ".join(f"{n:02d}" for n in pick),
                    "历史累计命中率": f"{cum*100:.1f}%",
                    "本球杀号数": len(killed),
                })
            st.dataframe(pd.DataFrame(_nr), use_container_width=True, hide_index=True)
            _s = "　".join(f"{r['球位']}:{list(r.values())[1]}" for r in _nr)
            st.success(f"{_nxt} 期推荐（每球 {_nk} 个，共 {_nk*7} 注）：{_s}")
            st.caption("历史上这 4 个号在该球位出现的期数占比见第三列；"
                       "「本球杀号数」是按阈值排除掉的号码个数。")

    # ---------- 仅看杀号结果 ----------
    st.divider()
    st.markdown("### 🚫 仅看杀号结果")
    st.caption("不跑全量分析，直接按当前阈值列出每个球位「杀掉哪些、留下哪些」。")
    _kc1, _kc2 = st.columns([1, 3])
    with _kc1:
        _kill_only = st.button("🎯 只算杀号", use_container_width=True, key="cc_kill_only")
    with _kc2:
        st.caption(f"当前阈值：出现率 < 区间均分 × {kill_th:g} → 判杀（可用上方滑块调整）")

    if _kill_only:
        _rows_k = load("升序全套.csv", None) or []
        if not _rows_k:
            st.error("读不到 升序全套.csv")
        else:
            _cols_k = _ball_cols(_rows_k)
            _kr = []
            _tot_kill = 0
            for b in range(1, 8):
                lo, hi = _RANGE[b]
                ser = [x for x in (_cols_k.get(b) or []) if x]
                if not ser:
                    continue
                _rate = _omission_rates(ser)
                _cur = _cur_omission(ser)
                _base = 1.0 / max(1, hi - lo + 1)
                killed = []
                for n in range(lo, hi + 1):
                    pv = _rate.get(_cur.get(n, 0))
                    if pv is not None and pv < _base * kill_th:
                        killed.append(n)
                kept = [n for n in range(lo, hi + 1) if n not in killed]
                _tot_kill += len(killed)
                _kr.append({
                    "球位": f"第{b}球",
                    "区间": f"{lo}-{hi}",
                    "杀掉": " ".join(f"{n:02d}" for n in killed) or "（无）",
                    "杀号数": len(killed),
                    "留下": " ".join(f"{n:02d}" for n in kept) or "（全杀）",
                    "留下数": len(kept),
                })
            st.dataframe(pd.DataFrame(_kr), use_container_width=True, hide_index=True)
            st.success(f"共杀 {_tot_kill} 个号；阈值 {kill_th:g}，"
                       f"阈值越大杀得越多，可在上方滑块调整后重新点此按钮。")

    # ---------- 指定期号回测 ----------
    st.divider()
    st.markdown("### 🎯 指定期号回测")
    st.caption("输入一个历史期号，程序只用「该期之前」的数据算推荐，再与该期实际开奖对照。")
    _rows_sel = load("升序全套.csv", None) or []
    _opts = _period_options("升序全套", _rows_sel) if _rows_sel else []
    _pc1, _pc2, _pc3 = st.columns([2, 1, 2])
    with _pc1:
        if _opts:
            _tp_in = st.selectbox("选择期号（来自升序全套，与多维分析同源）",
                                  _opts, index=0, key="cc_tp")
        else:
            _tp_in = ""
            st.warning("读不到升序全套.csv，无法列出期号")
    with _pc2:
        st.write(""); st.write("")
        _tp_go = st.button("▶ 回测这一期", use_container_width=True, key="cc_tp_go")
    with _pc3:
        _tp_k = st.slider(每球覆盖几个号, min_value=1, max_value=7, value=4, step=1,
                          key=cc_tp_k)

    st.caption(f"共 {len(_opts)} 个期号可选，最新在列表顶部")

    if _tp_go and str(_tp_in).strip():
        _rows_p = load("升序全套.csv", None) or []
        _res, _msg = backtest_period(_rows_p, _tp_in.strip(), int(_tp_k))
        if _res is None:
            st.warning(_msg)
        else:
            st.success(_msg)
            st.dataframe(pd.DataFrame(_res), use_container_width=True, hide_index=True)
            st.session_state["cc_pred_save"] = {
                "period": _tp_in.strip(),
                "rows": _res,
                "k": int(_tp_k),
            }
            if H.get("pred_save"):
                if st.button("💾 存入推演档案", key="cc_tp_save"):
                    _ok = 0
                    for _r in _res:
                        _nums = [int(x) for x in _r["推荐"].split() if x.isdigit()]
                        try:
                            _ok += 1 if H["pred_save"](_tp_in.strip(),
                                                       _r["球位"], "升序", _nums) else 0
                        except Exception:
                            pass
                    st.success(f"已存入 {_ok}/7 条（可在 AI推演页的存档区查看）")
            st.download_button("📥 下载这一期结果",
                               pd.DataFrame(_res).to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"回测_{_tp_in.strip()}.csv",
                               mime="text/csv", key="cc_tp_dl")

    # ---------- 逐期对照：程序 vs AI ----------
    st.divider()
    st.markdown("### 🤖 程序 vs AI 逐期对照")
    st.caption("对每一期：只用该期之前的数据算程序推荐 → 交给 AI 总结 → 与该期实际开奖对照。"
               "用来量出「AI 总结」到底有没有增益。注意：每期调用一次 AI，费用随期数线性增加。")

    _ac1, _ac2, _ac3 = st.columns([2, 1, 1])
    with _ac1:
        _ai_start = st.selectbox("从哪一期开始", _opts[:200] if _opts else ["-"], index=0,
                                 key="cc_ai_start")
    with _ac2:
        _ai_n = st.number_input("连续验证几期", 1, 30, 3, 1, key="cc_ai_n")
    with _ac3:
        st.write(""); st.write("")
        _ai_go = st.button("▶ 开始逐期对照", use_container_width=True, key="cc_ai_go")

    if _ai_go and _opts:
        _rows_a = load("升序全套.csv", None) or []
        _periods_a, _balls_a = _period_list(_rows_a)
        if _ai_start in _periods_a:
            _pos0 = _periods_a.index(_ai_start)
            _targets = _periods_a[_pos0:_pos0 + int(_ai_n)]
            _out, _detail, _ai_calls = [], [], 0
            _blocked = len(_periods_a) - _pos0 - 1
            st.info(f"已屏蔽 {_ai_start} 之后的 {_blocked} 期数据；"
                    f"每一期只用「该期之前」的历史计算。")
            _bar2 = st.progress(0.0, text="逐期计算中…")
            for _i, _tg in enumerate(_targets):
                _bar2.progress(_i / max(1, len(_targets)), text=f"计算 {_tg} …")
                _rec, _act = _prog_rec(_balls_a, _periods_a, _tg, int(pick_k))
                if _rec is None:
                    continue
                try:
                    _aip = _ai_picks(call_ai, _tg, _rec)
                    _ai_calls += 1
                except Exception:
                    _aip = {}
                _p_hit = sum(1 for b in range(1, 8) if _act[b] in _rec[b])
                _a_hit = sum(1 for b in range(1, 8) if _aip.get(b) and _act[b] in _aip[b])
                for b in range(1, 8):
                    _p_ok = _act[b] in _rec[b]
                    _a_ok = bool(_aip.get(b)) and _act[b] in _aip[b]
                    _detail.append({
                        "期号": _tg, "球位": f"第{b}球",
                        "程序推荐": " ".join(f"{n:02d}" for n in _rec[b]),
                        "程序": "✅" if _p_ok else "❌",
                        "AI推荐": " ".join(f"{n:02d}" for n in _aip.get(b, [])) or "-",
                        "AI": "✅" if _a_ok else ("❌" if _aip.get(b) else "-"),
                        "实际开出": f"{_act[b]:02d}",
                    })
                _out.append({
                    "期号": _tg,
                    "程序命中": f"{_p_hit}/7",
                    "AI命中": f"{_a_hit}/7" if _aip else "无返回",
                    "程序推荐(第1球)": " ".join(f"{n:02d}" for n in _rec[1]),
                    "AI推荐(第1球)": " ".join(f"{n:02d}" for n in _aip.get(1, [])) or "-",
                    "第1球实际": f"{_act[1]:02d}",
                })
            _bar2.progress(1.0, text="完成")
            if _out:
                st.dataframe(pd.DataFrame(_out), use_container_width=True, hide_index=True)
                _sp = sum(int(r["程序命中"].split("/")[0]) for r in _out)
                _sa = sum(int(r["AI命中"].split("/")[0]) for r in _out
                          if r["AI命中"] != "无返回")
                st.success(f"{len(_out)} 期合计：程序命中 {_sp} 个球位，AI 命中 {_sa} 个球位"
                           f"（AI 调用 {_ai_calls} 次）")
                st.caption("命中 = 该球位实际开出的号在推荐的那几个号里。"
                           "两者同一口径，可直接比较。")
                with st.expander(f"🔍 明细：每期每球位的推荐与命中（{len(_detail)} 行）",
                                 expanded=True):
                    st.dataframe(pd.DataFrame(_detail), use_container_width=True,
                                 hide_index=True)
                    st.download_button("📥 下载明细",
                                       pd.DataFrame(_detail).to_csv(index=False)
                                       .encode("utf-8-sig"),
                                       file_name="程序vsAI明细.csv", mime="text/csv",
                                       key="cc_ai_dl")
            else:
                st.warning("没有可用的期号（可能期号太早，之前数据不足）")

    # ---------- 模型回测 ----------
    st.divider()
    st.markdown("### 📊 模型回测验证")
    st.caption("用「只看过去」的方式逐期回测：边际热 / 查档 / 组合 / 随机，四种对比。"
               "跑一次约 20~60 秒。")
    _rc1, _rc2 = st.columns([1, 2])
    with _rc1:
        do_bt = st.button("▶ 跑回测", use_container_width=True, key="cc_bt")
    with _rc2:
        _bt_n = st.number_input("回测期数（每球）", 200, 2000, 600, 100, key="cc_bt_n")
    if do_bt:
        _rows_all = load("升序全套.csv", None) or []
        if not _rows_all:
            st.error("读不到 升序全套.csv")
        else:
            _pb = st.progress(0.0, text="回测中…")
            _tab = _backtest_table(_rows_all, n_test=int(_bt_n), prog=_pb.progress)
            _pb.empty()
            st.session_state["cc_bt_table"] = _tab
    _tc1, _tc2 = st.columns([1, 2])
    with _tc1:
        do_sw = st.button("🎯 扫描杀号阈值", use_container_width=True, key="cc_sw")
    with _tc2:
        st.caption("用前 70% 历史建立「遗漏→出现率」表，在后 30% 上评估："
                   "阈值越高杀得越多，杀对率会下降——找一个平衡点。")
    if do_sw:
        _rows_all = load("升序全套.csv", None) or []
        if _rows_all:
            st.session_state["cc_sw_table"] = _threshold_sweep(_rows_all)
    _sw = st.session_state.get("cc_sw_table")
    if _sw:
        st.dataframe(pd.DataFrame(_sw), use_container_width=True, hide_index=True)
        st.caption("「杀对率」= 杀掉的号里确实没开出的比例；每期平均杀得多、杀对率又不掉，越好。")

    table = st.session_state.get("cc_table")
    if not table:
        return

    nk, nu, nkp = st.session_state.get("cc_counts", (0, 0, 0))
    st.markdown(f"#### 解析：触发行 {nk} 条　·　去重后形态 {nu} 个　·　保留类 {nkp} 条")

    st.markdown("**【各球位综合评分】**")
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    st.caption("综合分 = 边际频次×0.65 + 保留×0.15 + 查档×0.05 − 杀×0.10 − 遗漏×0.05"
               "　｜回测实据：边际热 18.6% ＞ 组合 17.9% ＞ 查档 9.3% ＜ 随机 10.5%；"
               "查档权重压到 0.05，仅用于展示证据链")

    # ---------- 杀号策略 ----------
    _kill_rows = []
    _scores_now = st.session_state.get("cc_scores", {})
    for b in sorted(_scores_now):
        arr = _scores_now[b]
        killed = [x for x in arr if x[9]]
        kept = [x for x in arr if not x[9]]
        if not arr:
            continue
        # 用该球位候选的平均出现率估算"杀错率"
        ps = [x[8] for x in arr if x[8]]
        avg_p = (sum(ps) / len(ps)) if ps else 0.0
        _kill_rows.append({
            "球位": f"第{b}球",
            "候选数": len(arr),
            "判杀": len(killed),
            "判留": len(kept),
            "被杀号": " ".join(f"{x[0]:02d}" for x in killed[:10]) or "-",
            "杀错率(估)": f"{avg_p*100:.1f}%",
            "杀对率(估)": f"{(1-avg_p)*100:.1f}%",
        })
    if _kill_rows:
        st.markdown("**【杀号策略：宁可杀错，换多次正确】**")
        st.dataframe(pd.DataFrame(_kill_rows), use_container_width=True, hide_index=True)
        st.caption(f"判定规则：该号码当前遗漏的历史出现率 < 区间均分×{kill_th:g} → 判杀；"
                   "「杀错率」= 这种遗漏状态下它实际开出的概率，越低说明杀得越值。")

    _bl = []
    for b in sorted(st.session_state.get("cc_scores", {})):
        arr = st.session_state["cc_scores"][b]
        if not arr:
            continue
        top = arr[0][7]
        avg = sum(x[7] for x in arr) / len(arr)
        lo_, hi_ = _RANGE.get(b, (1, 49))
        _bl.append({"球位": f"第{b}球", "最高分": round(top, 3),
                    "平均分": round(avg, 3),
                    "集中度": round(top / avg, 2) if avg else 0,
                    "随机基线": f"{100.0/(hi_-lo_+1):.1f}%"})
    if _bl:
        st.markdown("**【信号集中度 vs 随机基线】**")
        st.dataframe(pd.DataFrame(_bl), use_container_width=True, hide_index=True)
        st.caption("集中度越高，说明该球位有几个号码被多个形态共同指向；接近 1 表示完全分散。")

    pats = st.session_state.get("cc_patterns") or []
    if pats:
        with st.expander(f"🔍 形态查档明细（{len(pats)} 个形态在历史里查到结果）", expanded=False):
            st.dataframe(pd.DataFrame(pats).sort_values("历史命中", ascending=False),
                         use_container_width=True, hide_index=True)

    lines = ["【统计口径】",
             "① 全量触发行按（球位+匹配串）去重，逐形态在升序/按序历史里查它之后开出了什么",
             "② 热度分 = 该号码在查档结果中的占比",
             "③ 保留分/杀分来自深度联动（保留法）与写板行数（删除法）",
             "④ 遗漏修正 = 该遗漏期数历史出现率 ÷ 区间均分",
             "", "【各球位评分】"]
    for b in sorted(st.session_state.get("cc_scores", {})):
        _kd = [x for x in st.session_state["cc_scores"][b] if x[9]]
        if _kd:
            lines.append(f"  第{b}球 判杀：" + " ".join(f"{x[0]:02d}" for x in _kd[:8]))
        seg = "　".join(f"{n:02d}(分{sc:.2f})" for n, h_, k_, l_, kk, mg, om, sc, _p, _k
                        in st.session_state["cc_scores"][b][:6])
        lines.append(f"  第{b}球：{seg}")
    lines += ["", "【任务】基于以上统计，输出：",
              "1. 哪些球位的信号最集中、哪些分散",
              "2. 每球位建议关注的号码及理由（只能从评分列表里选，不得编造）",
              "3. 一句话风险提示"]
    prompt = "\n".join(lines)

    with st.expander("查看/复制送给 AI 的内容", expanded=False):
        st.text_area("提示词", value=prompt, height=300, key="cc_prompt")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🤖 让 AI 总结", type="primary", use_container_width=True, key="cc_ai"):
            with st.spinner("AI 总结中…"):
                ans = call_ai(prompt, "你是严谨的数据分析助手。只依据给定数据作答，"
                                      "号码只能从评分列表里选，禁止编造。")
            st.session_state["cc_answer"] = ans
    with b2:
        st.download_button("📥 下载统计与提示词", prompt.encode("utf-8-sig"),
                           file_name="计算中心_全量查档.txt", mime="text/plain",
                           use_container_width=True, key="cc_dl")

    # ---------- 覆盖模式：每球 K 个号，累计命中率 ----------
    if _bl:
        _cols3 = _ball_cols(load("升序全套.csv", None) or [])
        _rows3 = []
        _tops = {}
        for b in sorted(_scores_now):
            arr = [x for x in _scores_now[b] if not x[9]] or _scores_now[b]
            topk = [x[0] for x in arr[:pick_k]]
            topk = [n for n in topk if _RANGE.get(b, (1, 49))[0] <= n <= _RANGE.get(b, (1, 49))[1]]
            if not topk:
                continue
            _tops[b] = topk
            ser = [x for x in (_cols3.get(b) or []) if x]
            n_hist = len(ser) or 1
            cum = []
            for k in range(1, len(topk) + 1):
                cum.append(sum(1 for v in ser if v in topk[:k]) / n_hist)
            _rows3.append({
                "球位": f"第{b}球",
                "推荐（累计命中率）": "　".join(
                    f"{n:02d}({c*100:.0f}%)" for n, c in zip(topk, cum)),
                "号码数": len(topk),
                "累计命中率": f"{cum[-1]*100:.1f}%",
            })

        if _rows3:
            st.markdown(f"**【每球 {pick_k} 个号 · 累计命中率】**")
            st.dataframe(pd.DataFrame(_rows3), use_container_width=True, hide_index=True)

            # 历史上「至少中一个」的实际占比
            _lens = min((len(_cols3.get(b) or []) for b in _tops), default=0)
            _hit = 0
            _cnt = 0
            for i in range(_lens):
                _cnt += 1
                for b, tk in _tops.items():
                    ser = _cols3.get(b) or []
                    if i < len(ser) and ser[i] in tk:
                        _hit += 1
                        break
            if _cnt:
                st.success(f"7 个球各押 {pick_k} 个号（共 {sum(len(v) for v in _tops.values())} 注）"
                           f" → 历史上「至少中一个」的期数占比 = {_hit/_cnt*100:.1f}%"
                           f"（样本 {_cnt} 期）")
            st.caption("累计命中率 = 该球位历史上开出「这几个号里任意一个」的期数 ÷ 总期数。"
                       "最后一行的百分比 = 这几注在历史上真的中过的比例。")

    _bt = st.session_state.get("cc_bt_table")
    if _bt:
        st.dataframe(pd.DataFrame(_bt), use_container_width=True, hide_index=True)
        st.caption("「查档」= 用最近6期属性序列去历史里找同样序列的结果；"
                   "「边际热」= 该球位历史上最常出的3个号；「组合」= 两者各半。")
        _txt = "\n".join(f"{r['球位']}\t查档{r['查档']}\t边际热{r['边际热']}"
                         f"\t组合{r['组合']}\t随机{r['随机']}\t样本{r['样本']}"
                         for r in _bt)
        st.download_button("📥 下载回测结果", _txt.encode("utf-8-sig"),
                           file_name="模型回测.txt", mime="text/plain",
                           key="cc_bt_dl")

    ans = st.session_state.get("cc_answer")
    if ans:
        st.divider()
        st.markdown("#### 🤖 AI 总结")
        st.text_area("结果", value=ans, height=460, key="cc_ans_box",
                     label_visibility="collapsed")
