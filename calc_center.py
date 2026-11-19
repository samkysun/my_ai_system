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


def render(df_data, H):
    st.title("🧮 计算中心")
    st.caption("全量查档：把看板里所有触发行拿到历史里查「之后开出了什么」，"
               "再叠加删除法/保留法/遗漏，最后交给 AI 总结。")

    load = H["load_excel_data"]
    call_ai = H["call_deepseek_api"]

    board = st.session_state.get("ai_board") or []
    if not board:
        st.info("看板里还没有内容。请先到「多维分析 / 深度联动 / 遗漏核算」点【📌 推送看板】。")
        return

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
        picks = st.multiselect("参与分析的内容（默认全选）", opts, default=opts, key="cc_picks")
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

        # 综合
        scores, table = {}, []
        cols_up = _ball_cols(rows_up) if rows_up else {}
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
            for n in cand:
                h_ = hs.get(n, 0) / th
                k_ = ks.get(n, 0) / tk
                l_ = kls.get(n, 0) / tl
                kk = cur.get(n, 0)
                ratio = (rr.get(kk, 0.0) / bc) if rr.get(kk) else 0.0
                adj = max(-1.0, min(1.0, ratio - 1.0)) if ratio else 0.0
                sc = 0.50 * h_ + 0.25 * k_ - 0.25 * l_ + 0.15 * adj
                arr.append((n, h_, k_, l_, kk, ratio, adj, sc))
            arr.sort(key=lambda x: -x[7])
            scores[b] = arr[:8]
            for it in arr[:6]:
                _ev = evid.get(b, {}).get(it[0], [])
                table.append({"球位": f"第{b}球", "号码": f"{it[0]:02d}",
                              "热度分": round(it[1], 3), "保留分": round(it[2], 2),
                              "杀分": round(it[3], 2), "当前遗漏": it[4],
                              "遗漏倍率": round(it[5], 2),
                              "命中形态": len(_ev),
                              "综合分": round(it[7], 3),
                              "证据": "；".join(f"{a}·{m}({h}次)" for a, m, h in
                                              sorted(_ev, key=lambda x: -x[2])[:2])})

        st.session_state["cc_scores"] = scores
        st.session_state["cc_table"] = table
        st.session_state["cc_patterns"] = pattern_rows
        st.session_state["cc_counts"] = (len(kill), len(uniq), len(keep))

    table = st.session_state.get("cc_table")
    if not table:
        return

    nk, nu, nkp = st.session_state.get("cc_counts", (0, 0, 0))
    st.markdown(f"#### 解析：触发行 {nk} 条　·　去重后形态 {nu} 个　·　保留类 {nkp} 条")

    st.markdown("**【各球位综合评分】**")
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    st.caption("综合分 = 热度×0.50 + 保留×0.25 − 杀×0.25 + 遗漏修正×0.15；"
               "形态权重已按命中次数收缩（命中少的打折）。")

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
        seg = "　".join(f"{n:02d}(分{sc:.2f})" for n, h_, k_, l_, kk, ratio, adj, sc
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

    ans = st.session_state.get("cc_answer")
    if ans:
        st.divider()
        st.markdown("#### 🤖 AI 总结")
        st.text_area("结果", value=ans, height=460, key="cc_ans_box",
                     label_visibility="collapsed")
