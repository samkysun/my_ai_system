# -*- coding: utf-8 -*-
"""计算中心 v4 —— 按你的语义区分三种来源

① 写板（全自动核算）= 删除法：某属性算出的行数越大 → 越要杀（该值对应的号码扣分）
② 深度联动      = 保留法：算出的生肖/尾数/门数等 → 保留（对应号码加分）
③ 遗漏          = 修正：用历史数据算出「当前遗漏为 K 期的号码，下一期出现率」，
                   与基准（区间均分）比较，>1 加分，<1 减分

最终分数 = 保留分 - 杀分 + 遗漏修正（可调权重）
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
        target = re.sub(r"[肖号尾]$", "", v)
        out = [n for n, z in (zmap.get(attr) or {}).items()
               if re.sub(r"[肖号尾]$", "", str(z)) == target]
    elif attr == "波单双":
        w = next((x for x in ("红波", "蓝波", "绿波") if v.startswith(x)), "")
        parity = "单" if "单" in v else ("双" if "双" in v else "")
        out = [n for n in range(1, 50)
               if _wave(n) == w and (n % 2 == 1) == (parity == "单")]
    return out


# ---------------- 解析 ----------------
_AUTO_T = re.compile(r"=+\s*(\d{5,8})期(升序|按序)-(.+?)(\d)球\s*=+")
_LINK_T = re.compile(r"=+\s*(升序|按序)(.+?)\s*\d?码?联动分析\s*=+")
_LINE_AUTO = re.compile(
    r"触发行：(\d)球\([A-Z]+\)[^\n]*?\((\d+)行\)[^\n]*?下:(.*?)(?:\s*\[|$)")
_LINE_LINK = re.compile(r"^第(\d)球[:：]\s*(.+?)(?:\||$)")


def _split_blocks(text):
    blocks, cur = [], None
    for ln in str(text).splitlines():
        if ln.startswith("=========") or ln.startswith("=========="):
            cur = {"head": ln, "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)
    return blocks


def parse_signals(text):
    """返回两类：kill(删除法，来自自动核算) / keep(保留法，来自深度联动)"""
    out = []
    for b in _split_blocks(text):
        head = b["head"]
        m = _AUTO_T.search(head)
        if m:
            period, order, attr, ball = m.group(1), m.group(2), m.group(3).strip(), int(m.group(4))
            for ln in b["lines"]:
                mm = _LINE_AUTO.search(ln)
                if mm:
                    out.append({"kind": "kill", "period": period, "order": order,
                                "attr": attr, "ball": int(mm.group(1)),
                                "value": mm.group(3).strip(),
                                "weight": int(mm.group(2))})
            continue
        m = _LINK_T.search(head)
        if m:
            order, mode = m.group(1), m.group(2).strip()
            for ln in b["lines"]:
                mm = _LINE_LINK.search(ln.strip())
                if mm:
                    ball = int(mm.group(1))
                    seg = mm.group(2)
                    seg = seg.split("杀(")[0]
                    vals = [v.strip() for v in re.split(r"[,，、]", seg) if v.strip()]
                    for v in vals:
                        v2 = re.sub(r"[✔✓\s]", "", v)
                        if v2:
                            out.append({"kind": "keep", "order": order,
                                        "attr": mode, "ball": ball,
                                        "value": v2, "weight": 1})
    return out


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


def _ball_series(rows, ball):
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


def _build_maps(rows, year):
    """从当年数据里推导 号码 -> 各属性值 的映射"""
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
    """统计：某号码连续 K 期未出时，下一期出现的经验概率 -> {K: P}"""
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


def _current_omission(series):
    """当前每个号码的遗漏期数（0 = 最新一期刚出）"""
    out = {}
    for n in range(1, 50):
        idx = len(series)
        for i, v in enumerate(series):
            if v == n:
                idx = i
                break
        out[n] = idx
    return out


def render(df_data, H):
    st.title("🧮 计算中心")
    st.caption("写板=删除法（行数越大越要杀）｜深度联动=保留法（算出的保留）"
               "｜遗漏=按历史出现率修正。程序算分，AI 只做总结。")

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
        rows_up = load("升序全套.csv", None) or []
        rows_an = load("按序全套.csv", None) or []

        with st.spinner("解析写板 + 计算遗漏出现率…"):
            sigs = []
            for tx in texts:
                sigs += parse_signals(tx)
            if not sigs:
                st.error("没解析出信号，请确认写板格式。")
                return

            # 从当年数据推导 号码->生肖/五行 映射
            _year = ""
            try:
                _r = rows_up[2]
                _year = f"{_r[213]}{_r[0]}{_r[1]}{_r[2]}"[:4]
            except Exception:
                pass
            zmap = _build_maps(rows_up, _year)

            keep_s, kill_s = defaultdict(Counter), defaultdict(Counter)
            n_keep = n_kill = 0
            for s in sigs:
                nums = _numbers_for(s["attr"], s["value"], zmap)
                if not nums:
                    continue
                ball = s["ball"]
                if s["kind"] == "keep":
                    for n in nums:
                        keep_s[ball][n] += s["weight"]
                    n_keep += 1
                else:
                    for n in nums:
                        kill_s[ball][n] += s["weight"]
                    n_kill += 1

            # 遗漏修正
            rates, base_rate = {}, {}
            for b in range(1, 8):
                ser = _ball_series(rows_up, b) if rows_up else []
                if not ser:
                    continue
                r, _stat = _omission_rates(ser)
                rates[b] = r
                lo, hi = _RANGE.get(b, (1, 49))
                base_rate[b] = 1.0 / max(1, len([n for n in range(lo, hi + 1)]))

            st.session_state["cc_counts"] = (n_keep, n_kill)
            st.session_state["cc_scores"] = self_scores = {}
            table = []
            for b in range(1, 8):
                ks, kls = keep_s.get(b, Counter()), kill_s.get(b, Counter())
                tk = sum(ks.values()) or 1
                tl = sum(kls.values()) or 1
                ser = _ball_series(rows_up, b) if rows_up else []
                cur = _current_omission(ser) if ser else {}
                r = rates.get(b, {})
                lo, hi = _RANGE.get(b, (1, 49))
                cand = set(ks) | set(kls)
                scored = []
                for n in cand:
                    kp = ks.get(n, 0) / tk            # 0~1 保留分
                    kl = kls.get(n, 0) / tl           # 0~1 杀分
                    k = cur.get(n, len(ser) or 0)
                    pr = r.get(k, 0.0)
                    bc = base_rate.get(b, 0.02) or 0.02
                    ratio = (pr / bc) if pr else 0.0  # 遗漏修正倍率
                    adj = max(-1.0, min(1.0, ratio - 1.0))
                    score = kp - kl + 0.3 * adj
                    scored.append((n, kp, kl, k, pr, bc, ratio, score))
                scored.sort(key=lambda x: -x[7])
                self_scores[b] = scored[:8]
                for it in scored[:6]:
                    table.append({"球位": f"第{b}球", "号码": f"{it[0]:02d}",
                                  "保留分": round(it[1], 2), "杀分": round(it[2], 2),
                                  "当前遗漏": it[3], "该遗漏历史出现率": f"{it[4]*100:.1f}%",
                                  "基准": f"{it[5]*100:.1f}%",
                                  "遗漏倍率": round(it[6], 2),
                                  "综合分": round(it[7], 3)})
            st.session_state["cc_table"] = table

    table = st.session_state.get("cc_table")
    if not table:
        return

    n_keep, n_kill = st.session_state.get("cc_counts", (0, 0))
    st.markdown(f"#### 解析结果：保留类信号 {n_keep} 条　·　删除类信号 {n_kill} 条")

    st.markdown("**【各球位综合评分】**")
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    st.caption("综合分 = 保留分 − 杀分 + 0.3×(遗漏倍率−1)；"
               "遗漏倍率 = 该遗漏期数的历史出现率 ÷ 区间均分。")

    # 提示词
    lines = ["【本页统计口径】",
             "写板（全自动核算）= 删除法：行数越大越倾向于杀；",
             "深度联动 = 保留法：算出的值就是保留；",
             "遗漏修正 = 该遗漏期数的历史出现率 ÷ 区间均分（>1 加分，<1 减分）。",
             "", "【各球位综合评分（程序算出）】"]
    for b in sorted(st.session_state.get("cc_scores", {})):
        seg = "　".join(f"{n:02d}(分{sc:.2f}/遗漏{k}/倍率{ratio:.2f})"
                        for n, kp, kl, k, pr, bc, ratio, sc
                        in st.session_state["cc_scores"][b][:6])
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
                                      "号码只能从评分列表里选，禁止编造。")
            st.session_state["cc_answer"] = ans
    with b2:
        st.download_button("📥 下载统计与提示词", prompt.encode("utf-8-sig"),
                           file_name="计算中心_统计.txt", mime="text/plain",
                           use_container_width=True, key="cc_dl")

    ans = st.session_state.get("cc_answer")
    if ans:
        st.divider()
        st.markdown("#### 🤖 AI 总结")
        st.text_area("结果", value=ans, height=460, key="cc_ans_box",
                     label_visibility="collapsed")
