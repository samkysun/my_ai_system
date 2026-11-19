# -*- coding: utf-8 -*-
"""计算中心：把各页面送来的写板内容 → 解析信号 → 历史回测 → 候选号码 → AI 解读。

设计原则：
  · 程序负责算（确定、可复核）
  · AI 只负责综合解读（不参与筛选）
"""
import re
from collections import Counter

import pandas as pd
import streamlit as st

# ---------- 号码映射表 ----------
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
    """把一个属性取值映射成号码列表；无法映射返回 []"""
    v = str(value).strip()
    v = re.sub(r"[肖号尾]$", "", v)
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
            out = [n for n in range(lo, hi + 1)]
    elif attr == "段数":
        t = re.sub(r"\D", "", v)
        if t:
            lo = (int(t) - 1) * 7 + 1
            out = [n for n in range(lo, min(lo + 6, 49) + 1)]
    elif attr == "波色":
        out = [n for n in range(1, 50) if _wave(n) == v]
    elif attr == "波单双":
        w = next((x for x in ("红波", "蓝波", "绿波") if v.startswith(x)), "")
        parity = "单" if "单" in v else ("双" if "双" in v else "")
        out = [n for n in range(1, 50)
               if _wave(n) == w and (n % 2 == 1) == (parity == "单")]
    return out


# ---------- 解析写板 ----------
_TITLE_NEW = re.compile(r"=+\s*(\d{5,8})期(升序|按序)-(.+?)(\d)球\s*=+")
_TITLE_OLD = re.compile(r"=+\s*(升序全套|按序全套)\s*-\s*(\d{5,8})\s*-\s*(.+?)\s*-\s*第(\d)球\s*=+")
_BASE = re.compile(r"【基准行排列】\(\d+行\):\s*(.+)")
_ITEM = re.compile(r"([A-Z]+)(\d+):([^,]+)")
_LINE = re.compile(
    r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+)行\)"
    r"[^\n]*?上:(.*?)\s*\(匹配:(.*?)\)\s*下:(.*?)(?:\s*\[|$)")


def _parse_board(text):
    """把写板文本解析成信号列表"""
    sigs, cur = [], None
    for ln in str(text).splitlines():
        m = _TITLE_NEW.search(ln) or _TITLE_OLD.search(ln)
        if m:
            g = m.groups()
            if len(g) == 4 and g[0] and g[0][:1].isdigit():
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
                cur["lines"].append({
                    "ball": int(mm.group(1)), "col": mm.group(2),
                    "a": int(mm.group(3)), "b": int(mm.group(4)),
                    "n": int(mm.group(5)), "match": mm.group(7),
                    "self": "自身参考列匹配" in ln,
                })
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


def _backtest(rows, col, seq, tail=60):
    """在历史里找相同序列，统计命中次数与下一期取值分布"""
    hits = 0
    nxt = Counter()
    n = len(seq)
    if n == 0:
        return 0, []
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
    return hits, nxt.most_common(tail)


def render(df_data, H):
    """H: 由 app.py 传入的辅助函数字典"""
    st.title("🧮 计算中心")
    st.caption("把各页面送上来的写板内容，先用程序筛选+回测，再交给 AI 做综合解读。"
               "**程序算、AI 说**，两边各司其职。")

    load_excel_data = H["load_excel_data"]
    call_ai = H["call_deepseek_api"]

    board = st.session_state.get("ai_board") or []
    if not board:
        st.info("看板里还没有内容。请先到「多维分析 / 深度联动 / 遗漏核算」点【📌 推送看板】。")
        return

    c1, c2 = st.columns([3, 1])
    with c1:
        picks = st.multiselect(
            "选择要分析的写板内容（可多选，按顺序合并）",
            options=[f"{e['source']} · {e['title']}" for e in board],
            default=[f"{board[-1]['source']} · {board[-1]['title']}"],
            key="cc_picks")
    with c2:
        st.write(""); st.write("")
        run = st.button("🔎 解析并回测", type="primary", use_container_width=True,
                        key="cc_run")

    idx_map = {f"{e['source']} · {e['title']}": i for i, e in enumerate(board)}
    chosen = [board[idx_map[p]]["text"] for p in picks if p in idx_map]

    if run:
        if not chosen:
            st.warning("至少选一条写板内容")
        else:
            text = "\n".join(chosen)
            sigs = _parse_board(text)
            if not sigs:
                st.error("没能从选中的内容里解析出信号。请确认是「全自动核算」的格式。")
                st.code(text[:600])
                return
            order = sigs[0]["order"]
            period = sigs[0]["period"]
            fname = "升序全套.csv" if order == "升序" else "按序全套.csv"
            rows = load_excel_data(fname, None)

            out_rows, vote = [], Counter()
            for s in sigs:
                seq = s["base"][:len(s["lines"][0]["match"])] if s["lines"] else []
                if not seq:
                    continue
                col = s["lines"][0]["col"] if s["lines"] else ""
                hits, top = _backtest(rows, col, seq)
                top_txt = "／".join(f"{v}×{c}" for v, c in top[:3]) or "-"
                nums = []
                for v, _c in top[:3]:
                    nums += _numbers_for(s["attr"], v)
                for n in set(nums):
                    vote[n] += 1
                out_rows.append({
                    "属性": s["attr"], "球位": f"第{s['ball']}球",
                    "匹配": "".join(seq), "触发行": len(s["lines"]),
                    "历史命中": hits, "下一期倾向": top_txt,
                })
            st.session_state["cc_signals"] = out_rows
            st.session_state["cc_period"] = period
            st.session_state["cc_order"] = order
            st.session_state["cc_votes"] = vote.most_common()

    sigs_tbl = st.session_state.get("cc_signals")
    if not sigs_tbl:
        return

    period = st.session_state.get("cc_period", "")
    order = st.session_state.get("cc_order", "")
    st.markdown(f"#### 期号 {period}｜{order}")
    st.markdown("**【达标信号】**")
    st.dataframe(pd.DataFrame(sigs_tbl), use_container_width=True, hide_index=True)

    votes = st.session_state.get("cc_votes") or []
    cand = [n for n, v in votes if v >= 2][:10] or [n for n, _v in votes[:6]]
    st.markdown("**【候选号码】**")
    if cand:
        st.markdown(" ".join(f"`{n:02d}`" for n in cand))
        st.caption("按「多个信号共同指向」排序，票数越高越靠前。")
    else:
        st.caption("本次没有能映射成号码的信号（如生肖/五行类），需人工判断。")

    # ---- 组装提示词 ----
    lines = [f"期号 {period}｜{order}", "", "【达标信号】"]
    for r in sigs_tbl:
        lines.append(f"{r['属性']}：{r['匹配']}｜触发行 {r['触发行']} 条｜"
                     f"历史同型命中 {r['历史命中']} 次｜下一期倾向 {r['下一期倾向']}")
    lines += ["", "【候选号码】", " ".join(f"{n:02d}" for n in cand) or "（无）", "",
              "【任务】基于以上已经筛好的结果，给出：",
              "1. 哪些信号互相印证、哪些冲突",
              "2. 建议关注的 5 个号码及理由（必须来自候选集合）",
              "3. 一句话风险提示"]
    prompt = "\n".join(lines)

    with st.expander("查看/复制送给 AI 的内容", expanded=False):
        st.text_area("提示词", value=prompt, height=260, key="cc_prompt")

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("🤖 让 AI 解读", type="primary", use_container_width=True, key="cc_ai"):
            with st.spinner("AI 解读中…"):
                ans = call_ai(prompt, "你是严谨的数据分析助手。只依据给定数据作答，不得编造号码。")
            st.session_state["cc_answer"] = ans
    with b2:
        st.download_button("📥 下载提示词", prompt.encode("utf-8-sig"),
                           file_name=f"计算中心_{period}_{order}.txt",
                           mime="text/plain", use_container_width=True, key="cc_dl")

    ans = st.session_state.get("cc_answer")
    if ans:
        st.divider()
        st.markdown("#### 🤖 AI 解读")
        st.text_area("结果", value=ans, height=420, key="cc_ans_box",
                     label_visibility="collapsed")
