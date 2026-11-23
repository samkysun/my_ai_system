# -*- coding: utf-8 -*-
"""
🎡 轮盘预测系统（欧式轮盘 0~36）
------------------------------------------------------------------
· 输入每次开奖号码，自动累计、自动核算
· 统计：尾数遗漏、生肖遗漏、姐妹码遗漏、轮盘相邻遗漏
· 触发阈值：尾数 20 期、生肖 15 期、姐妹码 15 期、相邻 15 期（达标进重点）
· 输出：最多 15 个候选号码，分重点 / 次重点 / 次要
· 记录存 GitHub 文件 roulette_history.json
------------------------------------------------------------------
"""
import json
import os
import re
import time
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

# 轮盘物理排列（顺时针）
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
         10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
POS = {n: i for i, n in enumerate(WHEEL)}

ZODIAC = ["马", "蛇", "龙", "兔", "虎", "牛", "鼠", "猪", "狗", "鸡", "猴", "羊"]
SX_WX = {"马": "火", "蛇": "火", "龙": "土", "兔": "木", "虎": "木", "牛": "土",
         "鼠": "水", "猪": "水", "狗": "土", "鸡": "金", "猴": "金", "羊": "土"}
SX_YYTD = {"马": "阴天", "蛇": "阴地", "龙": "阴天", "兔": "阳天", "虎": "阳地",
           "牛": "阳天", "鼠": "阴地", "猪": "阴天", "狗": "阴地", "鸡": "阳地",
           "猴": "阳天", "羊": "阳地"}
SX_WX_OBJ = {"马": "家臣", "蛇": "美女", "龙": "君王", "兔": "美女", "虎": "君王",
             "牛": "家臣", "鼠": "恶人", "猪": "家臣", "狗": "家臣", "鸡": "美女",
             "猴": "恶人", "羊": "美女"}
TAIL_WX = ["土", "水", "火", "木", "金", "土", "水", "火", "木", "金"]  # 尾0~9
SIBAO = ["画"] + ["书", "琴", "书", "琴", "书", "棋", "棋", "画", "棋", "琴",
                  "画", "画", "书", "琴", "书", "琴", "书", "棋", "棋", "画",
                  "棋", "琴", "画", "画", "书", "琴", "书", "琴", "书", "棋",
                  "棋", "画", "棋", "琴", "画", "画", "书"]  # 0~36

TH_TAIL, TH_ZODIAC, TH_SISTER, TH_ADJ = 20, 15, 15, 15
MAX_PICK = 10
REC_N = 4

HIST_FILE = "roulette_history.json"


# ============================================================
# 属性
# ============================================================
def zodiac_of(n):
    return ZODIAC[(n - 1) % 12] if n > 0 else "羊"


def attrs_of(n):
    z = zodiac_of(n)
    return {
        "生肖": z,
        "尾数": str(n % 10),
        "四宝": SIBAO[n] if 0 <= n <= 36 else "",
        "物象": SX_WX_OBJ.get(z, ""),
        "五行尾": TAIL_WX[n % 10],
        "生肖五行": SX_WX.get(z, ""),
        "阴阳天地": SX_YYTD.get(z, ""),
        "波单双": "绿波双数" if n == 0 else _color(n),
    }


def _color(n):
    """波色：按轮盘常见配色（红/黑/绿），这里沿用红蓝绿三色标记"""
    red = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    if n == 0:
        return "绿波"
    return "红波" + ("单数" if n % 2 else "双数") if n in red else \
           "蓝波" + ("单数" if n % 2 else "双数")


def sister(n):
    """姐妹码：左右相邻数字（按数字顺序，0~36 循环）"""
    return [(n - 1) % 37, (n + 1) % 37]


def wheel_neighbors(n):
    """轮盘物理相邻（左右）"""
    i = POS[n]
    return [WHEEL[(i - 1) % 37], WHEEL[(i + 1) % 37]]


# ============================================================
# 存储（GitHub 文件，失败则仅本次会话）
# ============================================================
def _gh(loader):
    try:
        return loader["gh"]
    except Exception:
        return None


def load_history(loader):
    if "_roulette_hist" in st.session_state:
        return st.session_state["_roulette_hist"]
    data = []
    fn = loader.get("gh_read")
    if fn:
        try:
            raw = fn(HIST_FILE)
            if raw:
                obj = json.loads(raw)
                data = [int(x) for x in obj.get("draws", []) if 0 <= int(x) <= 36]
                st.session_state["_roulette_pending"] = [
                    int(x) for x in obj.get("pending", []) if 0 <= int(x) <= 36]
                st.session_state["_roulette_marks"] = [
                    int(x) for x in obj.get("dealer_marks", [])]
                _dl = obj.get("dealers", []) or []
                if not _dl and obj.get("dealer_marks"):
                    _dl = [{"start": int(x), "name": ""}
                           for x in obj.get("dealer_marks", [])]
                st.session_state["_roulette_dealers"] = [
                    {"start": int(d0.get("start", 0)),
                     "name": str(d0.get("name", "") or "")}
                    for d0 in _dl if isinstance(d0, dict)]
                st.session_state["_roulette_dealer"] = str(
                    obj.get("dealer_name", "") or "")
        except Exception:
            data = []
    st.session_state["_roulette_hist"] = data
    return data


def save_history(loader, draws, pending=None):
    st.session_state["_roulette_hist"] = list(draws)
    if pending is not None:
        st.session_state["_roulette_pending"] = list(pending)
    fn = loader.get("gh_write")
    if not fn:
        return False
    _payload = json.dumps({"draws": draws,
                                  "pending": st.session_state.get(
                                      "_roulette_pending", []),
                                  "dealer_marks": st.session_state.get(
                                      "_roulette_marks", []),
                                  "dealers": st.session_state.get(
                                      "_roulette_dealers", []),
                                  "dealer_name": st.session_state.get(
                                      "_roulette_dealer", "")},
                             ensure_ascii=False)

    def _bg():
        try:
            fn(HIST_FILE, _payload, "轮盘记录更新")
        except Exception:
            pass

    try:
        import threading
        threading.Thread(target=_bg, daemon=True).start()
        return True
    except Exception:
        try:
            _bg()
            return True
        except Exception:
            return False


# ============================================================
# 遗漏计算
# ============================================================
def segment_start():
    """当前荷官从第几期开始（索引）"""
    dl = st.session_state.get("_roulette_dealers", []) or []
    if dl:
        return int(dl[-1].get("start", 0))
    marks = st.session_state.get("_roulette_marks", []) or []
    return int(marks[-1]) if marks else 0


def dealer_segments(draws):
    """返回 [(名称, 起始索引, 号码列表)]"""
    dl = st.session_state.get("_roulette_dealers", []) or []
    if not dl:
        return [("（未记录）", 0, list(draws))] if draws else []
    out = []
    for i, d0 in enumerate(dl):
        s0 = int(d0.get("start", 0))
        e0 = int(dl[i + 1]["start"]) if i + 1 < len(dl) else len(draws)
        out.append((d0.get("name") or f"荷官{i+1}", s0, list(draws[s0:e0])))
    return out


def current_segment(draws):
    s = segment_start()
    return draws[s:] if s < len(draws) else []


def omissions(draws):
    """各维度遗漏期数（都按「上一次出现到现在」计算）"""
    n = len(draws)
    last = {}

    for i, x in enumerate(draws):
        a = attrs_of(x)
        last[("尾", a["尾数"])] = i
        last[("肖", a["生肖"])] = i
        last[("号", x)] = i

    def gap(key):
        return n - (last.get(key, -1) + 1) if key in last else n

    out = {
        "尾数": {str(t): gap(("尾", str(t))) for t in range(10)},
        "生肖": {z: gap(("肖", z)) for z in ZODIAC},
        "号码": {x: gap(("号", x)) for x in range(37)},
    }
    return out


# ============================================================
# 生成候选
# ============================================================
def event_gaps(draws):
    """姐妹码 / 轮盘相邻 的连续未出期数（事件型，出现即清零）"""
    n = len(draws)
    last_sis = last_adj = -1
    sis_hits = adj_hits = 0
    for i in range(1, n):
        prev, cur = draws[i - 1], draws[i]
        if cur in sister(prev):
            last_sis = i
            sis_hits += 1
        if cur in wheel_neighbors(prev):
            last_adj = i
            adj_hits += 1
    # 当前连续未出期数
    gap_sis = n - 1 - last_sis if last_sis >= 0 else max(0, n - 1)
    gap_adj = n - 1 - last_adj if last_adj >= 0 else max(0, n - 1)
    return gap_sis, gap_adj, sis_hits, adj_hits


RULE_ATTRS = ["尾数", "生肖", "四宝", "物象", "五行尾", "生肖五行",
              "阴阳天地", "波单双"]
RULE_THRESHOLDS = [10, 15, 20, 25, 30]
RULE_MIN_N = 25          # 最少样本
RULE_MIN_LIFT = 0.01     # 最少提升 1 个百分点


def _attr_val(n, key):
    return attrs_of(n)[key]


RULE_MEM_FILE = "roulette_rules_memory.json"


def rule_key(r):
    return f"{r['类型']}|{r['属性']}|{r.get('取值','')}"


def load_rule_memory(loader):
    try:
        fn = loader.get("gh_read")
        if not fn:
            return {}
        raw = fn(RULE_MEM_FILE)
        if raw:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {}


def save_rule_memory(loader, mem):
    try:
        fn = loader.get("gh_write")
        if not fn:
            return False
        _txt = json.dumps(mem, ensure_ascii=False)

        def _bg():
            try:
                fn(RULE_MEM_FILE, _txt, "轮盘规则记忆更新")
            except Exception:
                pass

        import threading
        threading.Thread(target=_bg, daemon=True).start()
        return True
    except Exception:
        return False


def merge_rule_memory(mem, rules):
    """把本轮学到的规则累计进记忆：次数累加、命中累加"""
    for r in rules:
        k = rule_key(r)
        old = mem.get(k, {"n": 0, "hit": 0, "seen": 0})
        old["n"] = int(old.get("n", 0)) + int(r["样本"])
        old["hit"] = int(old.get("hit", 0)) + int(r["命中"])
        old["seen"] = int(old.get("seen", 0)) + 1
        old["lift"] = round(float(r["lift"]), 4)
        mem[k] = old
    return mem


def memory_factor(mem, r):
    """长期命中率 vs 当前 lift 的校正系数（0.5~1.5）"""
    m = mem.get(rule_key(r))
    if not m or int(m.get("n", 0)) < 30:
        return 1.0
    long_rate = int(m["hit"]) / max(1, int(m["n"]))
    now_rate = r["命中率"]
    if now_rate <= 0:
        return 1.0
    ratio = long_rate / now_rate
    return max(0.5, min(1.5, ratio))


def learn_rules(draws, lookback=800):
    """自动发现并验证多族规则"""
    hist = draws[-lookback:]
    n = len(hist)
    if n < 40:
        return []
    min_n = max(4, min(RULE_MIN_N, n // 6))
    _THS = ([5, 8] + list(RULE_THRESHOLDS)) if n < 150 else RULE_THRESHOLDS
    rules = []

    # ---------- 族1：遗漏型（属性值遗漏达阈值 → 下期开出） ----------
    for key in RULE_ATTRS:
        vals = sorted({_attr_val(x, key) for x in hist})
        for v in vals:
            total_hits = sum(1 for x in hist if _attr_val(x, key) == v)
            if total_hits < 5:
                continue
            base = total_hits / n
            last = -1
            for T in _THS:
                events = hits = 0
                last = -1
                for i in range(1, n):
                    gap = i - last - 1
                    if gap >= T and last >= 0:
                        events += 1
                        if _attr_val(hist[i], key) == v:
                            hits += 1
                    if _attr_val(hist[i], key) == v:
                        last = i
                if events < min_n:
                    continue
                rate = hits / events
                lift = rate - base
                if lift >= RULE_MIN_LIFT:
                    rules.append({"类型": "遗漏", "属性": key, "取值": v,
                                  "条件": f"遗漏≥{T}", "阈值": T,
                                  "样本": events, "命中": hits,
                                  "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族2：转移型（上期属性=a → 下期=b） ----------
    for key in RULE_ATTRS:
        vals = sorted({_attr_val(x, key) for x in hist})
        base_map = {v: sum(1 for x in hist if _attr_val(x, key) == v) / n
                    for v in vals}
        trans = {}
        for i in range(1, n):
            a, b = _attr_val(hist[i - 1], key), _attr_val(hist[i], key)
            trans.setdefault(a, {}).setdefault(b, 0)
            trans[a][b] += 1
        for a, m in trans.items():
            tot = sum(m.values())
            if tot < min_n:
                continue
            for b, c in m.items():
                rate = c / tot
                lift = rate - base_map.get(b, 0)
                if lift >= RULE_MIN_LIFT * 1.5:
                    rules.append({"类型": "转移", "属性": key, "取值": b,
                                  "条件": f"上期{a}", "阈值": 0,
                                  "样本": tot, "命中": c,
                                  "命中率": rate, "基线": base_map.get(b, 0),
                                  "lift": lift})

    # ---------- 族3：热频型（近20期出现≥k次 → 下期再出） ----------
    for k in (2, 3, 4):
        events = hits = 0
        for i in range(20, n):
            recent = hist[i - 20:i]
            hot = {x for x in recent if recent.count(x) >= k}
            if not hot:
                continue
            events += len(hot)
            hits += len(hot & {hist[i]})
        if events >= min_n * 2:
            base = 1 / 37
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "热频", "属性": "号码", "取值": f"≥{k}次",
                              "条件": "近20期", "阈值": k,
                              "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族4：姐妹事件型（连续未出≥T → 下期出现姐妹） ----------
    for T in (10, 15, 20, 25):
        events = hits = 0
        gap = 0
        for i in range(1, n):
            prev = hist[i - 1]
            if gap >= T:
                events += 1
                if hist[i] in sister(prev):
                    hits += 1
            if hist[i] in sister(prev):
                gap = 0
            else:
                gap += 1
        if events >= min_n:
            base = 2 / 37
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "姐妹", "属性": "姐妹码",
                              "取值": "相邻号码", "条件": f"连续未出≥{T}",
                              "阈值": T, "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族5：重号型（上期出现的号码，下期再出） ----------
    for num in range(37):
        events = hits = 0
        for i in range(1, n):
            if hist[i - 1] == num:
                events += 1
                if hist[i] == num:
                    hits += 1
        if events >= min_n:
            base = 1 / 37
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "重号", "属性": "号码", "取值": str(num),
                              "条件": f"上期出{num}", "阈值": 0,
                              "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族6：尾数连型（上期某尾数，下期同尾再出） ----------
    for tl in range(10):
        events = hits = 0
        for i in range(1, n):
            if hist[i - 1] % 10 == tl:
                events += 1
                if hist[i] % 10 == tl:
                    hits += 1
        if events >= min_n:
            base = sum(1 for x in hist if x % 10 == tl) / n
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "尾连", "属性": "尾数", "取值": str(tl),
                              "条件": f"上期{tl}尾", "阈值": 0,
                              "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族7：号码遗漏带（号码遗漏落区间后的命中） ----------
    for num in range(37):
        pos = [i for i, x in enumerate(hist) if x == num]
        if len(pos) < 4:
            continue
        base = len(pos) / n
        for lo, hi in ((10, 14), (15, 19), (20, 29), (30, 49), (50, 99)):
            events = hits = 0
            last = -1
            for i in range(1, n):
                gap = i - last - 1
                if last >= 0 and lo <= gap <= hi:
                    events += 1
                    if hist[i] == num:
                        hits += 1
                if hist[i] == num:
                    last = i
            if events >= min_n:
                rate = hits / events
                lift = rate - base
                if lift >= RULE_MIN_LIFT:
                    rules.append({"类型": "号遗漏", "属性": "号码",
                                  "取值": str(num),
                                  "条件": f"遗漏{lo}~{hi}", "阈值": lo,
                                  "样本": events, "命中": hits,
                                  "命中率": rate, "基线": base,
                                  "lift": lift})

    # ---------- 族8：号码段型 ----------
    segs = [(0, 9), (10, 19), (20, 29), (30, 36)]
    for lo, hi in segs:
        events = hits = 0
        last = -1
        for i in range(1, n):
            gap = i - last - 1
            if last >= 0 and gap >= 15:
                events += 1
                if lo <= hist[i] <= hi:
                    hits += 1
            if lo <= hist[i] <= hi:
                last = i
        if events >= min_n:
            base = sum(1 for x in hist if lo <= x <= hi) / n
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "号码段", "属性": "区间",
                              "取值": f"{lo}-{hi}", "条件": "遗漏≥15",
                              "阈值": lo, "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族9：大小型 ----------
    for name2, pred in (("小", lambda x: x <= 18), ("大", lambda x: x >= 19)):
        events = hits = 0
        last = -1
        for i in range(1, n):
            gap = i - last - 1
            if last >= 0 and gap >= 10:
                events += 1
                if pred(hist[i]):
                    hits += 1
            if pred(hist[i]):
                last = i
        if events >= min_n:
            base = sum(1 for x in hist if pred(x)) / n
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "大小", "属性": "大小", "取值": name2,
                              "条件": "遗漏≥10", "阈值": 10,
                              "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族10：奇偶型 ----------
    for name2, pred in (("奇", lambda x: x % 2 == 1),
                        ("偶", lambda x: x % 2 == 0)):
        events = hits = 0
        last = -1
        for i in range(1, n):
            gap = i - last - 1
            if last >= 0 and gap >= 10:
                events += 1
                if pred(hist[i]):
                    hits += 1
            if pred(hist[i]):
                last = i
        if events >= min_n:
            base = sum(1 for x in hist if pred(x)) / n
            rate = hits / events
            lift = rate - base
            if lift >= RULE_MIN_LIFT:
                rules.append({"类型": "奇偶", "属性": "奇偶", "取值": name2,
                              "条件": "遗漏≥10", "阈值": 10,
                              "样本": events, "命中": hits,
                              "命中率": rate, "基线": base, "lift": lift})

    # ---------- 族11：两期序列型（前两期属性组合 → 下期） ----------
    for key in RULE_ATTRS:
        seq = [_attr_val(x, key) for x in hist]
        base_map = {}
        for v in set(seq):
            base_map[v] = seq.count(v) / n
        pat = {}
        for i in range(2, n):
            pat.setdefault((seq[i - 2], seq[i - 1]), {}).setdefault(seq[i], 0)
            pat[(seq[i - 2], seq[i - 1])][seq[i]] += 1
        for (a1, a2), m in pat.items():
            tot = sum(m.values())
            if tot < min_n:
                continue
            for b, c in m.items():
                rate = c / tot
                lift = rate - base_map.get(b, 0)
                if lift >= RULE_MIN_LIFT * 2:
                    rules.append({"类型": "序列", "属性": key, "取值": b,
                                  "条件": f"{a1}→{a2}", "阈值": 0,
                                  "样本": tot, "命中": c,
                                  "命中率": rate,
                                  "基线": base_map.get(b, 0), "lift": lift})

    # ---------- 族12：双属性交集（两个属性同时遗漏达标）----------
    _k1 = "尾数"
    _k2 = "生肖"
    for tl in range(10):
        _tgap = 0
        for x in reversed(hist):
            if x % 10 == tl:
                break
            _tgap += 1
        else:
            _tgap = n
        if _tgap < 20:
            continue
        for sxv in {_attr_val(x, _k2) for x in range(37)}:
            _sgap = 0
            for x in reversed(hist):
                if _attr_val(x, _k2) == sxv:
                    break
                _sgap += 1
            else:
                _sgap = n
            if _sgap < 15:
                continue
            _targets = [x for x in range(37)
                        if x % 10 == tl and _attr_val(x, _k2) == sxv]
            if not _targets:
                continue
            _ev = sum(1 for i in range(1, n)
                      if hist[i] in _targets)
            _base = _ev / n
            if _base <= 0:
                continue
            _rate = _ev / n
            rules.append({"类型": "双属性", "属性": f"{tl}尾+{sxv}",
                          "取值": "、".join(str(v) for v in _targets[:4]),
                          "条件": f"尾缺{_tgap}/肖缺{_sgap}", "阈值": 20,
                          "样本": n, "命中": _ev,
                          "命中率": _rate, "基线": _base,
                          "lift": 0.0})

    # ---------- 族13：轮盘扇区（相邻 6 格一段）----------
    for seg_i in range(6):
        seg_nums = set(WHEEL[seg_i * 6:(seg_i + 1) * 6])
        if not seg_nums:
            continue
        _g = 0
        for x in reversed(hist):
            if x in seg_nums:
                break
            _g += 1
        else:
            _g = n
        if _g >= 12:
            _base = sum(1 for x in hist if x in seg_nums) / n
            rules.append({"类型": "扇区", "属性": "轮盘扇区",
                          "取值": f"第{seg_i+1}段",
                          "条件": f"遗漏{_g}", "阈值": 12,
                          "样本": n, "命中": sum(1 for x in hist
                                                 if x in seg_nums),
                          "命中率": _base, "基线": _base,
                          "lift": 0.0})

    rules.sort(key=lambda x: -x["lift"])
    return rules


_RULE_CACHE = {}


def learn_rules_cached(draws, lookback=800):
    """按历史签名缓存，避免每次重算"""
    try:
        _dl = st.session_state.get("_roulette_dealers", []) or []
        _dlsig = tuple((int(d0.get("start", 0)), str(d0.get("name", "")))
                       for d0 in _dl if isinstance(d0, dict))
        sig = (len(draws), lookback,
               tuple(draws[-6:]) if len(draws) >= 6 else tuple(draws),
               _dlsig)
    except Exception:
        return learn_rules(draws, lookback)
    hit = _RULE_CACHE.get(sig)
    if hit is not None:
        return hit
    rules = learn_rules(draws, lookback)
    if len(_RULE_CACHE) > 32:
        _RULE_CACHE.clear()
    _RULE_CACHE[sig] = rules
    return rules


def apply_rules(draws, rules, om, mem=None):
    """按当前状态激活规则，给号码打分（可用记忆校正权重）"""
    from collections import Counter
    score = Counter()
    hitcnt = Counter()
    active = []
    last_draw = draws[-1] if draws else None
    for r in rules:
        key, v, typ = r["属性"], r["取值"], r["类型"]
        hit = False
        if typ == "遗漏":
            g = 0
            for x in reversed(draws):
                if _attr_val(x, key) == v:
                    break
                g += 1
            else:
                g = len(draws)
            hit = g >= r["阈值"]
        elif typ == "转移":
            if last_draw is not None and _attr_val(last_draw, key) == \
                    r["条件"].replace("上期", ""):
                hit = True
        elif typ == "热频":
            recent = draws[-20:]
            k = r["阈值"]
            for num in range(37):
                if recent.count(num) >= k:
                    score[num] += max(0.5, r["lift"] * 100)
            hit = False
        elif typ == "重号":
            hit = (last_draw is not None and str(last_draw) == v)
        elif typ == "尾连":
            hit = (last_draw is not None and str(last_draw % 10) == v)
        elif typ == "号遗漏":
            g = 0
            for x in reversed(draws):
                if x == int(v):
                    break
                g += 1
            else:
                g = len(draws)
            cond = r["条件"]
            try:
                band = cond.replace("遗漏", "").split("~")
                lo, hi = int(band[0]), int(band[1])
            except Exception:
                lo, hi = 0, 999
            hit = lo <= g <= hi
        elif typ == "号码段":
            seg = r["取值"].split("-")
            g = 0
            for x in reversed(draws):
                if int(seg[0]) <= x <= int(seg[1]):
                    break
                g += 1
            else:
                g = len(draws)
            hit = g >= 15
        elif typ == "大小":
            pred = (lambda x: x <= 18) if r["取值"] == "小" else (lambda x: x >= 19)
            g = 0
            for x in reversed(draws):
                if pred(x):
                    break
                g += 1
            else:
                g = len(draws)
            hit = g >= 10
        elif typ == "奇偶":
            pred = (lambda x: x % 2 == 1) if r["取值"] == "奇" else \
                   (lambda x: x % 2 == 0)
            g = 0
            for x in reversed(draws):
                if pred(x):
                    break
                g += 1
            else:
                g = len(draws)
            hit = g >= 10
        elif typ == "序列":
            if len(draws) >= 2:
                a1 = _attr_val(draws[-2], key)
                a2 = _attr_val(draws[-1], key)
                hit = (r["条件"] == f"{a1}→{a2}")
            else:
                hit = False
        elif typ == "姐妹":
            gap = 0
            for i in range(len(draws) - 1, 0, -1):
                if draws[i] in sister(draws[i - 1]):
                    break
                gap += 1
            hit = gap >= r["阈值"]
        if not hit:
            continue
        active.append((r, 0))
        w = max(0.5, r["lift"] * 100)
        if mem:
            w *= memory_factor(mem, r)
        if typ in ("遗漏", "转移"):
            for num in range(37):
                if _attr_val(num, key) == v:
                    score[num] += w
                    hitcnt[num] += 1
        elif typ == "重号" and last_draw is not None:
            score[int(v)] += w
            hitcnt[int(v)] += 1
        elif typ == "尾连" and last_draw is not None:
            for num in range(37):
                if str(num % 10) == v:
                    score[num] += w
                    hitcnt[num] += 1
        elif typ == "号遗漏":
            score[int(v)] += w
            hitcnt[int(v)] += 1
        elif typ == "号码段":
            lo2, hi2 = [int(z) for z in r["取值"].split("-")]
            for num in range(lo2, hi2 + 1):
                score[num] += w
        elif typ == "大小":
            lo2, hi2 = (0, 18) if r["取值"] == "小" else (19, 36)
            for num in range(lo2, hi2 + 1):
                score[num] += w
        elif typ == "奇偶":
            want = 1 if r["取值"] == "奇" else 0
            for num in range(37):
                if num % 2 == want:
                    score[num] += w
        elif typ == "序列":
            for num in range(37):
                if _attr_val(num, key) == v:
                    score[num] += w
                    hitcnt[num] += 1
        elif typ == "姐妹" and last_draw is not None:
            for num in sister(last_draw):
                score[num] += w
    return score, active, hitcnt


FEATS = ["遗漏", "尾遗漏", "肖遗漏", "肖五行遗漏", "物象遗漏", "尾五行遗漏",
         "阴阳天地遗漏", "波单双遗漏", "近20频", "近50频", "姐妹", "轮盘邻"]


def _feat_vec(draws, t, n):
    """只用 draws[:t+1] 计算号码 n 的特征"""
    hist = draws[:t + 1]
    a = attrs_of(n)
    out = []

    def gap_of(pred):
        for k in range(len(hist) - 1, -1, -1):
            if pred(hist[k]):
                return len(hist) - 1 - k
        return len(hist)

    out.append(gap_of(lambda x: x == n))
    out.append(gap_of(lambda x: x % 10 == n % 10))
    out.append(gap_of(lambda x: zodiac_of(x) == a["生肖"]))
    out.append(gap_of(lambda x: SX_WX.get(zodiac_of(x)) == a["生肖五行"]))
    out.append(gap_of(lambda x: SX_WX_OBJ.get(zodiac_of(x)) == a["物象"]))
    out.append(gap_of(lambda x: TAIL_WX[x % 10] == a["五行尾"]))
    out.append(gap_of(lambda x: SX_YYTD.get(zodiac_of(x)) == a["阴阳天地"]))
    out.append(gap_of(lambda x: attrs_of(x)["波单双"] == a["波单双"]))
    out.append(sum(1 for x in hist[-20:] if x == n))
    out.append(sum(1 for x in hist[-50:] if x == n))
    out.append(1.0 if n in sister(hist[-1]) else 0.0)
    out.append(1.0 if n in wheel_neighbors(hist[-1]) else 0.0)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def _learn_weights(_sig, _n):
    return None


def learn_weights(draws):
    """用历史数据学习各因子权重（皮尔逊相关系数，仅取正向）"""
    lo = max(60, len(draws) - 400)
    rows, labels = [], []
    for t in range(lo, len(draws) - 1):
        nxt = draws[t + 1]
        for n in range(37):
            rows.append(_feat_vec(draws, t, n))
            labels.append(1.0 if n == nxt else 0.0)
    if len(rows) < 120:
        return None
    k = len(FEATS)
    m = len(rows)
    means = [sum(r[i] for r in rows) / m for i in range(k)]
    sds = []
    for i in range(k):
        v = sum((r[i] - means[i]) ** 2 for r in rows) / m
        sds.append(v ** 0.5 or 1.0)
    lab_m = sum(labels) / m
    w = []
    for i in range(k):
        cov = sum((rows[j][i] - means[i]) * (labels[j] - lab_m)
                  for j in range(m)) / m
        corr = cov / (sds[i] * (lab_m * (1 - lab_m)) ** 0.5 or 1)
        w.append(max(0.0, corr))
    s = sum(w) or 1
    w = [x / s for x in w]
    return {FEATS[i]: w[i] for i in range(k)}


def smart_top3(draws):
    """综合自学习权重，给出 3 码"""
    if len(draws) < 40:
        return None, None
    w = learn_weights(draws)
    if not w:
        w = dict()
        w["遗漏"] = 1.0
    t = len(draws) - 1
    rows = [_feat_vec(draws, t, n) for n in range(37)]
    k = len(FEATS)
    means = [sum(r[i] for r in rows) / 37 for i in range(k)]
    sds = []
    for i in range(k):
        v = sum((r[i] - means[i]) ** 2 for r in rows) / 37
        sds.append(v ** 0.5 or 1.0)
    scored = []
    for n in range(37):
        z = 0.0
        for i, f in enumerate(FEATS):
            z += w.get(f, 0.0) * ((rows[n][i] - means[i]) / sds[i] if sds[i] else 0)
        scored.append((n, z, rows[n]))
    scored.sort(key=lambda x: -x[1])
    top = scored[:REC_N]
    total = sum(abs(x[1]) for x in scored) or 1
    out = [(n, z, z / total) for n, z, _ in top]
    return out, w


def build_candidates(draws, rec_nums=None):
    om = omissions(draws)
    if not draws:
        return om, [], []

    last_no = draws[-1]
    alerts = []

    hot_tails = [(t, g) for t, g in om["尾数"].items() if g >= TH_TAIL]
    hot_tails.sort(key=lambda x: -x[1])
    if hot_tails:
        alerts.append(("尾数", [f"{t}尾({g}期)" for t, g in hot_tails]))
    hot_z = [(z, g) for z, g in om["生肖"].items() if g >= TH_ZODIAC]
    hot_z.sort(key=lambda x: -x[1])
    if hot_z:
        alerts.append(("生肖", [f"{z}({g}期)" for z, g in hot_z]))

    sis = sister(last_no)
    adj = wheel_neighbors(last_no)
    sis_gap, adj_gap, sis_hits, adj_hits = event_gaps(draws)
    if sis_gap >= TH_SISTER:
        alerts.append(("姐妹码", [str(s) for s in sis] +
                       [f"（连续 {sis_gap} 期未出）"]))
    if adj_gap >= TH_ADJ:
        alerts.append(("轮盘相邻", [str(a) for a in adj] +
                       [f"（连续 {adj_gap} 期未出）"]))

    # 每个号码累计"命中条件数"
    score = Counter()
    why = defaultdict(list)

    def add(num, tag, w=1):
        if 0 <= num <= 36:
            score[num] += w
            why[num].append(tag)

    # 尾数只提醒，不写入候选

    # 其它属性遗漏加权（生肖不入候选，姐妹/相邻只提醒）
    _extra = [("四宝", "四宝"), ("物象", "物象"), ("五行尾", "五行尾"),
              ("生肖五行", "生肖五行"), ("阴阳天地", "阴阳天地"),
              ("波单双", "波单双")]
    for _name, _key in _extra:
        _gaps = {}
        for _v in {attrs_of(x)[_key] for x in range(37)}:
            _g = 0
            for _x in reversed(draws):
                if attrs_of(_x)[_key] == _v:
                    break
                _g += 1
            else:
                _g = len(draws)
            _gaps[_v] = _g
        for _v, _g in _gaps.items():
            if _g >= TH_ZODIAC:
                for _num in range(1, 37):          # 0 号特殊：不参与属性加权
                    if attrs_of(_num)[_key] == _v:
                        add(_num, f"{_name}{_v}", 1)
    # 生肖遗漏号码不再写入候选（按要求）
    # 姐妹码只提醒，不写入候选
    # 轮盘相邻只提醒，不写入候选

    # 属性重复加权：同号码命中多个不同属性条件
    _pend = [int(x) for x in st.session_state.get("_roulette_pending", [])
             if 0 <= int(x) <= 36]
    _rec = [int(x) for x in (rec_nums or [])][:REC_N]
    for _p in _pend:
        if _p not in _rec:
            _rec.append(_p)
    _rec = _rec[:max(REC_N, REC_N + len(_pend))]
    _rest = sorted(((n, s) for n, s in score.items() if n not in _rec),
                   key=lambda x: (-x[1], x[0]))
    _strong = [(n, s) for n, s in _rest if s >= 2]
    _weak = [(n, s) for n, s in _rest if s < 2]
    ranked = [(n, score.get(n, 0)) for n in _rec]
    # 0 号按出现次数权衡：超过 40 次开始推荐
    # 自学习规则得分
    _rules = learn_rules_cached(draws)
    _rscore, _active, _rhit = apply_rules(
        draws, _rules, om,
        st.session_state.get("_roulette_rules_mem"))
    try:
        st.session_state["_roulette_rhit"] = dict(_rhit)
    except Exception:
        pass
    for _n, _s in _rscore.items():
        if _s > 0:
            add(int(_n), "规则", int(round(_s)))

    _zgap = om["号码"].get(0, 0)
    if _zgap >= 40 and 0 not in _rec:
        ranked.append((0, 99))
        why[0].append(f"0号·尾0·遗漏{_zgap}期")
    _seen = {n for n, _ in ranked}
    for n, s in _strong + _weak:
        if len(ranked) >= MAX_PICK:
            break
        if n not in _seen:
            ranked.append((n, s))
            _seen.add(n)
    ranked = ranked[:MAX_PICK]
    levels = []
    if ranked:
        top = ranked[0][1]
        for num, sc in ranked:
            tags = set(why[num])
            if num in _rec:
                lv = "推荐"
            elif num == 0 and 0 in why and any("0号已出" in w for w in why[0]):
                lv = "重点"
            elif tags & {"姐妹", "轮盘邻"}:
                lv = "重点"
            elif sc >= top and sc >= 3:
                lv = "重点"
            elif sc >= max(2, top - 1):
                lv = "次重点"
            else:
                lv = "次要"
            levels.append((num, sc, lv, why[num]))
    return om, alerts, levels


# ============================================================
# 页面
# ============================================================
def render(df_data, H):
    st.title("🎡 轮盘预测系统（欧式 0~36）")
    st.caption("输入每期开奖号码，自动统计遗漏并给出候选号码（≤10 个）。")

    draws = load_history(H)
    if "_roulette_rules_mem" not in st.session_state:
        st.session_state["_roulette_rules_mem"] = load_rule_memory(H)

    _d1, _d2, _d3 = st.columns([1, 1, 2])
    with _d1:
        _known = sorted({d0.get("name", "").strip()
                         for d0 in st.session_state.get("_roulette_dealers", [])
                         if d0.get("name", "").strip()})
        _opts = _known + ["（手动输入）"] if _known else ["（手动输入）"]
        _cur_name = st.session_state.get("_roulette_dealer", "")
        _idx = _opts.index(_cur_name) if _cur_name in _opts else len(_opts) - 1
        _sel = st.selectbox("当前荷官", _opts, index=_idx, key="rou_dealer_sel")
        if _sel == "（手动输入）":
            _dealer = st.text_input("输入荷官代号", value=_cur_name,
                                    key="rou_dealer_name")
        else:
            _dealer = _sel
        if _dealer != _cur_name:
            st.session_state["_roulette_dealer"] = _dealer
    with _d2:
        if st.button("🔄 换荷官（重新统计）", key="rou_new_dealer"):
            _marks = list(st.session_state.get("_roulette_marks", []))
            _marks.append(len(draws))
            st.session_state["_roulette_marks"] = _marks
            _dl2 = list(st.session_state.get("_roulette_dealers", []))
            _dl2.append({"start": len(draws),
                         "name": st.session_state.get("_roulette_dealer", "")})
            st.session_state["_roulette_dealers"] = _dl2
            save_history(H, draws)
            st.success("已标记换荷官，统计从本期重新开始")
            st.rerun()
    with _d3:
        _seg = current_segment(draws)
        st.caption(f"全场 {len(draws)} 期｜"
                   f"本荷官 {len(_seg)} 期"
                   + (f"｜换过 {len(st.session_state.get('_roulette_marks', []))} 次"
                      if st.session_state.get("_roulette_marks") else ""))

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        num = st.number_input("本期开奖号码", 0, 36, 0, 1, key="rou_num")
    with c2:
        if st.button("➕ 添加", use_container_width=True, key="rou_add"):
            draws = draws + [int(num)]
            _pend = [x for x in st.session_state.get("_roulette_pending", [])
                     if x != int(num)]
            st.session_state["_roulette_pending"] = _pend
            ok = save_history(H, draws, _pend)
            try:
                _rules2 = learn_rules_cached(draws)
                _mem2 = st.session_state.get("_roulette_rules_mem") or {}
                _mem2 = merge_rule_memory(_mem2, _rules2)
                st.session_state["_roulette_rules_mem"] = _mem2
                save_rule_memory(H, _mem2)
            except Exception:
                pass
            st.success(f"已记录 {num}" + ("" if ok else "（仅本次会话）"))
            st.rerun()
    with c3:
        st.caption(f"已记录 {len(draws)} 期" +
                   (f"｜最新 {draws[-1]}" if draws else ""))

    if draws:
        with st.expander("📜 历史记录", expanded=False):
            df = pd.DataFrame({"序号": list(range(1, len(draws) + 1)),
                               "号码": draws})
            st.dataframe(df.tail(50), use_container_width=True, hide_index=True)
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("↩️ 删除最后一期", key="rou_del"):
                    save_history(H, draws[:-1])
                    st.rerun()
            with cc2:
                if st.button("🗑 清空全部", key="rou_clear"):
                    save_history(H, [])
                    st.rerun()

    if not draws:
        st.info("先输入并添加几期开奖号码")
        return

    _seg_draws = current_segment(draws)
    _use_seg = len(_seg_draws) >= 40
    _calc = _seg_draws if _use_seg else draws
    if _seg_draws:
        if _use_seg:
            st.caption(f"📊 统计范围：本荷官 {len(_seg_draws)} 期"
                       f"（换荷官后重新计算）")
        else:
            st.caption(f"📊 本荷官仅 {len(_seg_draws)} 期（<40），暂用全场数据")

    _top3, _w = smart_top3(_calc)
    _rec = [n for n, _, _ in _top3] if _top3 else []
    om, alerts, levels = build_candidates(_calc, _rec)
    _rhit = st.session_state.get("_roulette_rhit", {}) or {}
    last_no = draws[-1]
    _sg, _ag, _sh, _ah = event_gaps(draws)
    _zgap2 = om["号码"].get(0, 0)
    _ztip = ("已达 40 期门槛，自动推荐" if _zgap2 >= 40
             else f"未达 40 期（还差 {40 - _zgap2} 期）")
    st.caption(f"0 号：当前遗漏 {_zgap2} 期｜{_ztip}")
    st.markdown(f"**上期号码：{last_no}**　"
                f"姐妹码 {sister(last_no)}（连续 {_sg} 期未出）　"
                f"轮盘相邻 {wheel_neighbors(last_no)}（连续 {_ag} 期未出）")

    st.markdown("### 🚨 提醒下注")
    if not alerts:
        st.caption("暂无达到阈值的项目")
    for kind, vals in alerts:
        st.warning(f"{kind} 遗漏达标：{'、'.join(vals)}")

    st.markdown("### 🎯 候选号码（最多 10 个）")
    if not levels:
        st.caption("暂无候选（说明所有属性都没到阈值）")
    else:
        rows = []
        for num, sc, lv, wh in levels:
            a = attrs_of(num)
            _rc = int(_rhit.get(num, 0))
            if _rc >= 3:
                _judge = "🔥 极可能开"
            elif _rc == 2:
                _judge = "⭐ 较可能"
            elif _rc == 1:
                _judge = "○ 留意"
            else:
                _judge = ""
            rows.append({"等级": lv, "号码": num, "判断": _judge, "得分": sc,
                         "遗漏": om["号码"].get(num, 0),
                         "命中条件": "、".join(sorted(set(wh))),
                         "尾数": a["尾数"], "生肖": a["生肖"],
                         "四宝": a["四宝"], "物象": a["物象"],
                         "五行尾": a["五行尾"], "生肖五行": a["生肖五行"],
                         "阴阳天地": a["阴阳天地"], "波单双": a["波单双"]})
        _hot = [r2["号码"] for r2 in rows if "极可能" in str(r2["判断"])]
        _mid = [r2["号码"] for r2 in rows if "较可能" in str(r2["判断"])]
        if _hot:
            st.success("🔥 极可能开出：" + "、".join(f"{v:02d}" for v in _hot)
                       + "（" + str(len(_hot)) + " 个号码同时命中多条规则）")
        elif _mid:
            st.info("⭐ 较可能：" + "、".join(f"{v:02d}" for v in _mid))
        else:
            st.caption("本期没有规则共振的号码（无高置信提示）")
        dfc = pd.DataFrame(rows)
        st.dataframe(dfc, use_container_width=True, hide_index=True)
        st.download_button("📥 下载候选",
                           dfc.to_csv(index=False).encode("utf-8-sig"),
                           file_name="轮盘候选.csv", mime="text/csv",
                           key="rou_dl")

    st.markdown("### 🧠 系统推荐 4 码（已并入上方候选）")
    if not _top3:
        st.caption(f"历史仅 {len(draws)} 期，需 40 期以上才能学习权重")
    else:
        _rows3 = []
        for num, sc, share in _top3:
            a = attrs_of(num)
            _rows3.append({"号码": num, "综合得分": round(sc, 3),
                           "占比": f"{share*100:.1f}%",
                           "尾数": a["尾数"], "生肖": a["生肖"],
                           "四宝": a["四宝"], "物象": a["物象"],
                           "五行尾": a["五行尾"],
                           "生肖五行": a["生肖五行"],
                           "阴阳天地": a["阴阳天地"],
                           "波单双": a["波单双"]})
        st.dataframe(pd.DataFrame(_rows3), use_container_width=True,
                     hide_index=True)
        if _w:
            with st.expander("⚙ 系统学到的因子权重", expanded=False):
                st.dataframe(pd.DataFrame(
                    [{"因子": k, "权重": round(v, 4)}
                     for k, v in sorted(_w.items(), key=lambda x: -x[1])]),
                    use_container_width=True, hide_index=True)

    with st.expander("📊 遗漏明细", expanded=False):
        t0, t1, t2 = st.tabs(["号码", "尾数", "生肖"])
        with t0:
            st.dataframe(pd.DataFrame(
                [{"号码": k, "遗漏": v} for k, v in om["号码"].items()]),
                use_container_width=True, hide_index=True)
        with t1:
            st.dataframe(pd.DataFrame(
                [{"尾数": k, "遗漏": v} for k, v in om["尾数"].items()]),
                use_container_width=True, hide_index=True)
        with t2:
            st.dataframe(pd.DataFrame(
                [{"生肖": k, "遗漏": v} for k, v in om["生肖"].items()]),
                use_container_width=True, hide_index=True)

    st.markdown("### 🧪 系统自学习规则（自动验证）")
    _rules = learn_rules(draws)
    if not _rules:
        st.caption("历史数据不足，或暂无通过验证的规则")
    else:
        _rdf = pd.DataFrame(
            [{"类型": r["类型"], "属性": r["属性"], "取值": r["取值"],
              "条件": r["条件"],
              "样本": r["样本"], "命中": r["命中"],
              "命中率": f"{r['命中率']*100:.1f}%",
              "基线": f"{r['基线']*100:.1f}%",
              "提升": f"{r['lift']*100:+.1f}pp"} for r in _rules[:15]])
        st.dataframe(_rdf, use_container_width=True, hide_index=True)
        st.caption(f"共 {len(_rules)} 条规则通过验证（50 期起开始学习，"
                   f"样本门槛随期数自动调整，提升≥{RULE_MIN_LIFT*100:.0f}pp）")

    # ---------- 各荷官对比 ----------
    st.divider()
    st.markdown("### 👤 各荷官偏好分析")
    _segs = dealer_segments(draws)
    if len(_segs) <= 1:
        st.caption("还没有换过荷官；点上方「🔄 换荷官」后可对比。")
    else:
        _cur_start = segment_start()
        _rows_d = []
        for _nm, _st0, _nums in _segs:
            if not _nums:
                continue
            _n0 = len(_nums)
            _c0 = Counter(_nums)

            def _pref(fn):
                c = Counter(fn(x) for x in _nums)
                v, k = c.most_common(1)[0]
                return f"{v} {k/_n0*100:.0f}%"

            _bal = _pref(lambda x: "红波" if x in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36} else ("绿" if x == 0 else "蓝波"))
            _oddeven = _pref(lambda x: "双" if x % 2 == 0 else "单")
            _big = _pref(lambda x: "大(19-36)" if x >= 19 else "小(0-18)")
            _seg = _pref(lambda x: f"{x//10*10}-{x//10*10+9}" if x < 30 else "30-36")
            _tail = _pref(lambda x: f"{x%10}尾")
            _sector = _pref(lambda x: f"第{POS[x]//6+1}段")
            _zod = _pref(lambda x: zodiac_of(x))
            _sis = sum(1 for i2 in range(1, len(_nums))
                       if _nums[i2] in sister(_nums[i2 - 1]))
            _adj = sum(1 for i2 in range(1, len(_nums))
                       if _nums[i2] in wheel_neighbors(_nums[i2 - 1]))
            _sis_pct = _sis / max(1, len(_nums) - 1)
            _adj_pct = _adj / max(1, len(_nums) - 1)
            _top3 = "、".join(f"{v:02d}" for v, _ in _c0.most_common(3))
            _rows_d.append({
                "荷官": _nm,
                "期数": _n0,
                "波色偏好": _bal,
                "单双": _oddeven,
                "大小": _big,
                "号码段": _seg,
                "尾数": _tail,
                "轮盘扇区": _sector,
                "生肖偏好": _zod,
                "姐妹码": f"{_sis_pct*100:.0f}%",
                "轮盘相邻": f"{_adj_pct*100:.0f}%",
                "最热号码": _top3,
                "当前": "✅" if _st0 == _cur_start else "",
            })
        st.dataframe(pd.DataFrame(_rows_d), use_container_width=True,
                     hide_index=True)

        # 选择查看哪位荷官
        _names = [n0 for n0, _s0, _v0 in _segs if _v0]
        _view = st.selectbox("查看荷官详情", _names,
                             index=len(_names) - 1, key="rou_view_dealer")
        _vnums = next((v0 for n0, _s0, v0 in _segs if n0 == _view), [])
        if len(_vnums) >= 10:
            st.markdown(f"**{_view} 的偏好明细（{len(_vnums)} 期）**")
            _n1 = len(_vnums)
            _c1d = Counter(
                "红波" if x in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
                else ("绿(0)" if x == 0 else "蓝波") for x in _vnums)
            _c2d = Counter("单" if x % 2 else "双" for x in _vnums)
            _c3d = Counter("大(19-36)" if x >= 19 else "小(0-18)"
                           for x in _vnums)
            _c4d = Counter(f"{x%10}尾" for x in _vnums)
            _c5d = Counter(f"第{POS[x]//6+1}段" for x in _vnums)
            _dd = []
            _c6d = Counter(zodiac_of(x) for x in _vnums)
            _c7d = Counter("与上期姐妹" if _vnums[i2] in sister(_vnums[i2-1])
                           else "非姐妹" for i2 in range(1, len(_vnums)))
            _c8d = Counter("与上期轮盘相邻"
                           if _vnums[i2] in wheel_neighbors(_vnums[i2-1])
                           else "非相邻" for i2 in range(1, len(_vnums)))
            for _title, _cc in (("波色", _c1d), ("单双", _c2d),
                                ("大小", _c3d), ("尾数", _c4d),
                                ("轮盘扇区", _c5d), ("生肖", _c6d),
                                ("姐妹码", _c7d), ("轮盘相邻", _c8d)):
                _txt = "、".join(f"{v}{k/_n1*100:.0f}%"
                                for v, k in _cc.most_common(3))
                _dd.append({"维度": _title, "分布": _txt})
            st.dataframe(pd.DataFrame(_dd), use_container_width=True,
                         hide_index=True)
        st.caption("说明：百分比 = 该类型在本荷官全部开奖中的占比；"
                   "样本少时仅供参考。")
