# -*- coding: utf-8 -*-
"""计算中心 v3：综合评分
   综合你原来的三套思路：
     ① 写板信号（多维/深度联动的达标条数与指向）  权重 50%
     ② 遗漏期数（该号码在该球位多久没开）          权重 30%
     ③ 近30期出现频次（热度）                      权重 20%
   程序算分，AI 只做总结。
"""
import re
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

_RED = {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46}
_BLUE = {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48}
_GREEN = {5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49}


def _wave(n):
    if n in _RED:
        return "红波"
    if n in _BLUE:
        return "蓝波"
    if n in _GREEN:
        return "绿波"
    return ""


def _sum_of(n):
    return sum(int(c) for c in str(n))


def _numbers_for(attr, value):
    v = re.sub(r"[肖号尾]$", "", str(value).strip())
    out = []
    if attr == "尾数":
        t = re.sub(r"\D", "", v)
        if t:
            out = [n for n in range(1, 50) if str(n)[-1] == t[-1]]
    elif attr == "数字合":
        t = re.sub(r"\D", "", v)
        if t:
            out = [n for n in range(1, 50) if _sum_of(n) == int(t)]
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
    elif attr == "波单双":
        w = next((x for x in ("红波", "蓝波", "绿波") if v.startswith(x)), "")
        parity = "单" if "单" in v else ("双" if "双" in v else "")
        out = [n for n in range(1, 50)
               if _wave(n) == w and (n % 2 == 1) == (parity == "单")]
    return out


_T_NEW = re.compile(r"=+\s*(\d{5,8})期(升序|按序)-(.+?)(\d)球\s*=+")
_T_OLD = re.compile(r"=+\s*(升序全套|按序全套)\s*-\s*(\d{5,8})\s*-\s*(.+?)\s*-\s*第(\d)球\s*=+")
_BASE = re.compile(r"【基准行排列】\(\d+行\):\s*(.+)")
_ITEM = re.compile(r"([A-Z]+)(\d+):([^,]+)")
_LINE = re.compile(
    r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+行)\)|"
    r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+)行\)")


def _parse_board(text):
    sigs, cur = [], None
    for ln in str(text).splitlines():
        m = _T_NEW.search(ln) or _T_OLD.search(ln)
        if m:
            g = m.groups()
            if g[0][:1].isdigit():
                period, order, attr, ball = g[0], g[1], g[2], g[3]
            else:
                order = "升序" if g[0] == "升序全套" else "按序"
                period, attr, ball = g[1], g[2], g[3]
            cur = {"period": period, "order": order, "attr": attr.strip(),
                   "ball": int(ball), "base": [], "lines": []}
            sigs.append(cur)
            continue
        if cur is None:
            continue
        mb = _BASE.search(ln)
        if mb:
            cur["base"] = [v.strip() for _, _, v in _ITEM.findall(mb.group(1))]
            continue
        if ln.startswith("触发行："):
            mm = re.search(r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+)行\)", ln)
            if mm:
                cur["lines"].append({"ball": int(mm.group(1)), "col": mm.group(2),
                                     "n": int(mm.group(5))})
    return sigs


def _cell(rows, r1, col):
    from openpyxl.utils import column_index_from_string
    try:
        idx = column_index_from_string(col) - 1
    except Exception:
        return ""
    if not (1 <= r1 <= len(rows)):
        return ""
    r = rows[r1 - 1]
    return r[idx].strip() if idx < len(r) else ""


def _backtest(rows, col, seq):
    n = len(seq)
    if n == 0 or not rows:
        return 0, Counter()
    hits, nxt = 0, Counter()
    for i in range(2, len(rows) - n):
        ok = True
        for k in range(n):
            if _cell(rows, i + k + 1, col) != seq[k]:
                ok = False
                break
        if ok:
            hits += 1
            v = _cell(rows, i + n + 1, col)
            if v:
                nxt[v] += 1
    return hits, nxt


def _ball_series(rows, ball):
    """某球位的开奖号码序列（从新到旧）"""
    i10 = 3 + (ball - 1) * 30
    i1 = i10 + 1
    out = []
    for r in rows[2:]:
        if len(r) <= i1:
            out.append(None)
            continue
        try:
            out.append(int((r[i10].strip() + r[i1].strip()) or 0))
        except Exception:
            out.append(None)
    return out


def _num_stats(series):
    """每个号码的遗漏期数与近30期出现次数"""
    omis, freq = {}, Counter()
    total = len(series)
    for n in range(1, 50):
        omi = total
        for i, v in enumerate(series):
            if v == n:
                omi = i
                break
        omis[n] = omi
    for v in series[:30]:
        if v:
            freq[v] += 1
    return omis, freq


def render(df_data, H):
    st.title("🧮 计算中心")
    st.caption("综合三套思路打分：① 写板信号 50%　② 遗漏期数 30%　③ 近30期热度 20%"
               "　—— 程序算分，AI 只做总结。")

    load = H["load_excel_data"]
    call_ai = H["call_deepseek_api"]

    board = st.session_state.get("ai_board") or []
    if not board:
        st.info("看板里还没有内容。请先到「多维分析 / 深度联动 / 遗漏核算」点【📌 推送看板】。")
        return

    opts = [f"{i+1}. {e['source']} · {e['title']}" for i, e in enumerate(board)]
    c1, c2 = st.columns([4, 1])
    with c1:
        picks = st.multiselect("参与统计的写板（默认全选）", opts, default=opts, key="cc_picks")
    with c2:
        st.write(""); st.write("")
        go = st.button("🔎 统计并评分", type="primary", use_container_width=True, key="cc_go")

    if go:
        texts = [board[int(p.split(".")[0]) - 1]["text"] for p in picks]
        if not texts:
            st.warning("至少选一条")
            return
        with st.spinner("解析写板 + 回测两个文件 + 计算遗漏与热度…"):
            sigs = []
            for tx in texts:
                sigs += _parse_board(tx)
            if not sigs:
                st.error("没解析出信号，请确认写板是全自动核算格式。")
                return

            rows_up = load("升序全套.csv", None) or []
            rows_an = load("按序全套.csv", None) or []
            files = {"升序": rows_up, "按序": rows_an}

            detail, votes = [], defaultdict(Counter)
            hits_all = Counter()
            for s in sigs:
                if not s["lines"]:
                    continue
                col = s["lines"][0]["col"]
                seq = s["base"][:s["lines"][0]["n"]]
                if not seq:
                    continue
                h1, c1_ = _backtest(files["升序"], col, seq)
                h2, c2_ = _backtest(files["按序"], col, seq)
                hits_all["升序"] += h1
                hits_all["按序"] += h2
                cnt = c1_ + c2_
                nums = Counter()
                for v, c in cnt.items():
                    for num in _numbers_for(s["attr"], v):
                        nums[num] += c
                for num, c in nums.items():
                    votes[s["ball"]][num] += c
                detail.append({"属性": s["attr"], "球位": f"第{s['ball']}球",
                               "匹配": "".join(seq), "触发行": len(s["lines"]),
                               "升序命中": h1, "按序命中": h2,
                               "倾向": "／".join(f"{v}×{c}" for v, c in cnt.most_common(3)) or "-"})

            # 三因子综合评分
            probs = {}
            for ball, vc in votes.items():
                tot_vote = sum(vc.values()) or 1
                ser = _ball_series(rows_up, ball) if rows_up else []
                omis, freq = _num_stats(ser) if ser else ({n: 0 for n in range(1, 50)}, Counter())
                max_omi = max(omis.values()) or 1
                max_freq = max(freq.values()) or 1
                scored = []
                for n, c in vc.items():
                    s1 = c / tot_vote
                    s2 = omis.get(n, 0) / max_omi
                    s3 = freq.get(n, 0) / max_freq
                    scored.append((n, s1 * 100, omis.get(n, 0), freq.get(n, 0),
                                   s1 * 0.5 + s2 * 0.3 + s3 * 0.2))
                scored.sort(key=lambda x: -x[4])
                probs[ball] = scored[:8]

            st.session_state["cc_detail"] = detail
            st.session_state["cc_probs"] = probs
            st.session_state["cc_hits"] = dict(hits_all)
            st.session_state["cc_period"] = sigs[0]["period"]

    detail = st.session_state.get("cc_detail")
    if not detail:
        return

    period = st.session_state.get("cc_period", "")
    hits = st.session_state.get("cc_hits") or {}
    st.markdown(f"#### 期号 {period}　｜　历史命中：升序 {hits.get('升序',0)} 次、"
                f"按序 {hits.get('按序',0)} 次")

    st.markdown("**【达标信号】**")
    st.dataframe(pd.DataFrame(detail), use_container_width=True, hide_index=True)

    probs = st.session_state.get("cc_probs") or {}
    st.markdown("**【各球位综合评分】**")
    if probs:
        rows = []
        for b in sorted(probs):
            for n, sv, omi, fr, sc in probs[b][:6]:
                rows.append({"球位": f"第{b}球", "号码": f"{n:02d}",
                             "信号占比": f"{sv:.0f}%", "遗漏期数": omi,
                             "近30期次数": fr, "综合分": round(sc, 3)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("综合分 = 信号占比×0.5 + 遗漏归一×0.3 + 热度归一×0.2")
    else:
        st.caption("本次没有可映射成号码的信号（生肖/五行类需人工判断）。")

    # ---------- 提示词 ----------
    lines = [f"期号 {period}", "", "【达标信号（程序已筛选）】"]
    for d in detail:
        lines.append(f"{d['属性']}｜{d['球位']}｜匹配 {d['匹配']}｜触发行 {d['触发行']} 条"
                     f"｜升序命中 {d['升序命中']}、按序命中 {d['按序命中']}｜倾向 {d['倾向']}")
    lines += ["", "【历史回测（升序+按序）】",
              f"合计命中：升序 {hits.get('升序',0)} 期、按序 {hits.get('按序',0)} 期。"]
    if probs:
        lines.append("各球位综合评分（信号 50% + 遗漏 30% + 热度 20%）：")
        for b in sorted(probs):
            seg = "　".join(f"{n:02d}(分{sc:.2f}/遗漏{omi}/热度{fr})"
                            for n, _sv, omi, fr, sc in probs[b][:6])
            lines.append(f"  第{b}球：{seg}")
    lines += ["", "【任务】基于以上统计，输出：",
              "1. 哪些信号互相印证、哪些冲突",
              "2. 每球位建议关注的号码及理由（只能从评分列表里选，不得编造）",
              "3. 整体一句话风险提示"]
    prompt = "\n".join(lines)

    with st.expander("查看/复制送给 AI 的内容", expanded=False):
        st.text_area("提示词", value=prompt, height=300, key="cc_prompt")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🤖 让 AI 总结", type="primary", use_container_width=True, key="cc_ai"):
            with st.spinner("AI 总结中…"):
                ans = call_ai(prompt, "你是严谨的数据分析助手。只依据给定数据作答，"
                                      "号码只能从给出的评分列表里选，禁止编造。")
            st.session_state["cc_answer"] = ans
    with b2:
        st.download_button("📥 下载统计与提示词", prompt.encode("utf-8-sig"),
                           file_name=f"计算中心_{period}.txt", mime="text/plain",
                           use_container_width=True, key="cc_dl")

    ans = st.session_state.get("cc_answer")
    if ans:
        st.divider()
        st.markdown("#### 🤖 AI 总结")
        st.text_area("结果", value=ans, height=460, key="cc_ans_box",
                     label_visibility="collapsed")
