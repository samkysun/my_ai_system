# -*- coding: utf-8 -*-
"""计算中心 v2
把各页面送上来的写板内容 → 解析信号 → 在【升序全套 + 按序全套】上分别回测
→ 按球位汇总号码概率 → 交给 AI 做总结。

原则：程序负责统计（可复核），AI 只负责总结（不筛选、不编造号码）。
"""
import re
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

# ---------- 波色表 ----------
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
    """属性取值 → 号码列表；无法映射返回 []"""
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


# ---------- 解析写板 ----------
_T_NEW = re.compile(r"=+\s*(\d{5,8})期(升序|按序)-(.+?)(\d)球\s*=+")
_T_OLD = re.compile(r"=+\s*(升序全套|按序全套)\s*-\s*(\d{5,8})\s*-\s*(.+?)\s*-\s*第(\d)球\s*=+")
_BASE = re.compile(r"【基准行排列】\(\d+行\):\s*(.+)")
_ITEM = re.compile(r"([A-Z]+)(\d+):([^,]+)")
_LINE = re.compile(
    r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+)行\)"
    r"[^\n]*?上:(.*?)\s*\(匹配:(.*?)\)\s*下:(.*?)(?:\s*\[|$)")


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
            mm = _LINE.search(ln)
            if mm:
                cur["lines"].append({"ball": int(mm.group(1)), "col": mm.group(2),
                                     "n": int(mm.group(5)), "match": mm.group(7)})
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
    """历史里找完全相同的连续序列，返回 (命中次数, {下一期取值: 次数})"""
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


def render(df_data, H):
    st.title("🧮 计算中心")
    st.caption("各页面送上来的写板 → 程序在【升序全套 + 按序全套】上回测 → "
               "按球位统计号码概率 → AI 只做总结。")

    load = H["load_excel_data"]
    call_ai = H["call_deepseek_api"]

    board = st.session_state.get("ai_board") or []
    if not board:
        st.info("看板里还没有内容。请先到「多维分析 / 深度联动 / 遗漏核算」点【📌 推送看板】。")
        return

    # ---------- 选择 ----------
    opts = [f"{i+1}. {e['source']} · {e['title']}" for i, e in enumerate(board)]
    c1, c2 = st.columns([4, 1])
    with c1:
        picks = st.multiselect("参与统计的写板（默认全选）", opts, default=opts, key="cc_picks")
    with c2:
        st.write(""); st.write("")
        go = st.button("🔎 统计并回测", type="primary", use_container_width=True, key="cc_go")

    if go:
        texts = [board[int(p.split(".")[0]) - 1]["text"] for p in picks]
        if not texts:
            st.warning("至少选一条")
            return
        with st.spinner("正在解析写板并回测两个文件…"):
            sigs = []
            for tx in texts:
                sigs += _parse_board(tx)
            if not sigs:
                st.error("没解析出信号，请确认写板是「全自动核算」格式。")
                return

            rows_up = load("升序全套.csv", None)
            rows_an = load("按序全套.csv", None)
            files = {"升序": rows_up or [], "按序": rows_an or []}

            detail, votes = [], defaultdict(Counter)
            total_hits = Counter()
            for s in sigs:
                if not s["lines"]:
                    continue
                col = s["lines"][0]["col"]
                n = len(s["lines"][0]["match"])
                seq = s["base"][:n]
                if not seq:
                    continue
                h_up, c_up = _backtest(files["升序"], col, seq)
                h_an, c_an = _backtest(files["按序"], col, seq)
                cnt = c_up + c_an
                total_hits["升序"] += h_up
                total_hits["按序"] += h_an
                top = cnt.most_common(3)
                nums = Counter()
                for v, c in cnt.items():
                    for num in _numbers_for(s["attr"], v):
                        nums[num] += c
                for num, c in nums.items():
                    votes[s["ball"]][num] += c
                detail.append({
                    "属性": s["attr"], "球位": f"第{s['ball']}球",
                    "匹配": "".join(seq), "触发行": len(s["lines"]),
                    "升序命中": h_up, "按序命中": h_an,
                    "下一期倾向": "／".join(f"{v}×{c}" for v, c in top) or "-",
                    "可映射号码": len(nums),
                })

            # 每个球位的概率
            probs = {}
            for ball, cnt in votes.items():
                tot = sum(cnt.values()) or 1
                probs[ball] = [(n, c, c / tot) for n, c in cnt.most_common(8)]

            st.session_state["cc_detail"] = detail
            st.session_state["cc_probs"] = probs
            st.session_state["cc_hits"] = dict(total_hits)
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

    st.markdown("**【各球位号码概率】**")
    probs = st.session_state.get("cc_probs") or {}
    if probs:
        order = sorted(probs.keys())
        rows = []
        for b in order:
            for n, c, p in probs[b][:6]:
                rows.append({"球位": f"第{b}球", "号码": f"{n:02d}",
                             "权重": c, "占比": f"{p*100:.1f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("权重 = 各信号回测中「下一期出现该号码」的累计次数；占比 = 该球位内归一化。")
    else:
        st.caption("本次没有可映射成号码的信号（生肖/五行类需人工判断）。")

    # ---------- 提示词 ----------
    lines = [f"期号 {period}", "",
             "【达标信号（已由程序筛选）】"]
    for d in detail:
        lines.append(f"{d['属性']}｜{d['球位']}｜匹配 {d['匹配']}｜触发行 {d['触发行']} 条"
                     f"｜升序命中 {d['升序命中']}、按序命中 {d['按序命中']}"
                     f"｜下一期倾向 {d['下一期倾向']}")
    lines += ["", "【历史回测（升序+按序两个文件合计）】",
              f"这些组合在历史上共命中 {hits.get('升序',0)} 期（升序）、"
              f"{hits.get('按序',0)} 期（按序）。"]
    if probs:
        lines.append("各球位号码概率（程序统计）：")
        for b in sorted(probs.keys()):
            seg = "　".join(f"{n:02d}({p*100:.0f}%)" for n, _c, p in probs[b][:6])
            lines.append(f"  第{b}球：{seg}")
    lines += ["", "【任务】基于以上已经统计好的结果，输出：",
              "1. 哪些信号互相印证、哪些冲突",
              "2. 每球位建议关注的号码及理由（只能从上面的概率列表里选，不得编造）",
              "3. 整体一句话风险提示"]
    prompt = "\n".join(lines)

    with st.expander("查看/复制送给 AI 的内容", expanded=False):
        st.text_area("提示词", value=prompt, height=300, key="cc_prompt")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🤖 让 AI 总结", type="primary", use_container_width=True, key="cc_ai"):
            with st.spinner("AI 总结中…"):
                ans = call_ai(prompt, "你是严谨的数据分析助手。只依据给定数据作答，"
                                      "号码只能从给出的概率列表里选，禁止编造。")
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
