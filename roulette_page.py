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
    """页面数据每次访问从 0 开始，不读取上次会话的历史"""
    if "_roulette_hist" not in st.session_state:
        st.session_state["_roulette_hist"] = []
        st.session_state.setdefault("_roulette_pending", [])
        st.session_state.setdefault("_roulette_marks", [])
        st.session_state.setdefault("_roulette_dealers", [])
    return st.session_state["_roulette_hist"]


def save_history(loader, draws, pending=None):
    """只更新页面（会话内），不再上传到云端"""
    st.session_state["_roulette_hist"] = list(draws)
    if pending is not None:
        st.session_state["_roulette_pending"] = list(pending)
    return True


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
    merged = {}
    order = []
    for i, d0 in enumerate(dl):
        s0 = int(d0.get("start", 0))
        e0 = int(dl[i + 1]["start"]) if i + 1 < len(dl) else len(draws)
        nm = _norm_name(d0.get("name")) or f"荷官{i+1}"
        if nm not in merged:
            merged[nm] = {"start": s0, "nums": []}
            order.append(nm)
        merged[nm]["nums"].extend(draws[s0:e0])
    return [(nm, merged[nm]["start"], merged[nm]["nums"]) for nm in order]


def current_segment(draws):
    s = segment_start()
    return draws[s:] if s < len(draws) else []


PROFILE_FILE = "roulette_profiles.json"


def _norm_name(s):
    """去掉所有空白与不可见字符，返回规范名字"""
    import re as _re
    if s is None:
        return ""
    s = str(s).replace("\u3000", "").replace("\xa0", "")
    try:
        import unicodedata as _ud
        s = _ud.normalize("NFKC", s)
    except Exception:
        pass
    return _re.sub(r"\s+", "", s).strip()


def _merge_profile(dst, src):
    dst["spins"] = int(dst.get("spins", 0)) + int(src.get("spins", 0))
    for f in ("sister", "adj", "big", "odd", "red"):
        dst[f] = int(dst.get(f, 0)) + int(src.get(f, 0))
    for f in ("nums", "zod"):
        d0 = dst.setdefault(f, {})
        for k2, v2 in (src.get(f) or {}).items():
            d0[k2] = int(d0.get(k2, 0)) + int(v2)
    seq = dst.setdefault("seq", [])
    seq.extend(int(x) for x in (src.get("seq") or []))
    del seq[:-300]
    return dst


def normalize_profiles(prof, changed=None):
    """统一为「官:名字」，合并同名（去空格），丢弃旧台号键"""
    if not isinstance(prof, dict):
        return {}, True
    out = {}
    dirty = False
    for k, v in prof.items():
        if not isinstance(v, dict):
            dirty = True
            continue
        _kstr = str(k)
        if _kstr.startswith("官:"):
            _rawname = _kstr[2:]
        elif "官:" in _kstr:          # 旧组合键 台:T|官:X → 取荷官名
            _rawname = _kstr.split("官:", 1)[1]
            dirty = True
        elif _kstr.startswith("台:"):
            continue                  # 纯台号档案，无可归属荷官
        else:
            _rawname = _kstr
            dirty = True
        name = _norm_name(_rawname)
        if not name:
            dirty = True
            continue
        nk = "官:" + name
        if nk in out:
            _merge_profile(out[nk], v)
            dirty = True
        else:
            out[nk] = v
    return out, dirty


KNOWN_FILE = "roulette_dealers.json"


def load_known_names(loader):
    try:
        fn = loader.get("gh_read")
        if not fn:
            return []
        raw = fn(KNOWN_FILE)
        if raw:
            obj = json.loads(raw)
            if isinstance(obj, list):
                return [_norm_name(x) for x in obj if _norm_name(x)]
    except Exception:
        pass
    return []


def save_known_names(loader, names):
    try:
        fn = loader.get("gh_write")
        if not fn:
            return False
        fn(KNOWN_FILE, json.dumps(sorted(set(names)), ensure_ascii=False),
           "荷官名单更新")
        return True
    except Exception:
        return False


def load_profiles(loader):
    try:
        fn = loader.get("gh_read")
        if not fn:
            return {}
        raw = fn(PROFILE_FILE)
        if raw:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                obj, _dirty = normalize_profiles(obj)
                if _dirty:
                    save_profiles(loader, obj)
                return obj
    except Exception:
        pass
    return {}


def save_profiles(loader, prof):
    try:
        fn = loader.get("gh_write")
        if not fn:
            return False
        txt = json.dumps(prof, ensure_ascii=False)
        fn(PROFILE_FILE, txt, "轮盘档案更新")
        return True
    except Exception:
        return False


def _blank_profile():
    return {"spins": 0, "nums": {}, "sister": 0, "adj": 0,
            "big": 0, "odd": 0, "red": 0, "zod": {}}


def record_spin(prof, keys, num, prev=None):
    for k in keys:
        if not k:
            continue
        p0 = prof.setdefault(k, _blank_profile())
        p0["spins"] = int(p0.get("spins", 0)) + 1
        _seq = p0.setdefault("seq", [])
        _seq.append(int(num))
        if len(_seq) > 300:
            del _seq[:-300]
        nm = p0.setdefault("nums", {})
        nm[str(num)] = int(nm.get(str(num), 0)) + 1
        if int(num) >= 19:
            p0["big"] = int(p0.get("big", 0)) + 1
        if int(num) % 2 == 1:
            p0["odd"] = int(p0.get("odd", 0)) + 1
        if int(num) != 0 and int(num) in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}:
            p0["red"] = int(p0.get("red", 0)) + 1
        zd = p0.setdefault("zod", {})
        z = zodiac_of(int(num))
        zd[z] = int(zd.get(z, 0)) + 1
        if prev is not None:
            if int(num) in sister(int(prev)):
                p0["sister"] = int(p0.get("sister", 0)) + 1
            if int(num) in wheel_neighbors(int(prev)):
                p0["adj"] = int(p0.get("adj", 0)) + 1
    return prof


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


def frequency_candidates(profile, top_n=MAX_PICK):
    """只用长期频率（百分比）出候选；不依赖遗漏与近期序列"""
    nums = profile.get("nums", {}) if profile else {}
    spins = int(profile.get("spins", 0)) if profile else 0
    if not nums or spins <= 0:
        return []
    expect = spins / 37.0
    rows = []
    for k, v in nums.items():
        try:
            n = int(k)
            c = int(v)
        except Exception:
            continue
        dev = c / expect - 1.0 if expect else 0.0
        rows.append((n, c, dev))
    rows.sort(key=lambda x: (-x[2], -x[1]))
    out = []
    for n, c, dev in rows[:top_n]:
        pct = c / spins * 100
        if dev >= 0.35:
            lv = "🔥 明显偏多"
        elif dev >= 0.15:
            lv = "⭐ 略偏多"
        elif dev <= -0.35:
            lv = "❄ 明显偏少"
        else:
            lv = "○ 正常"
        out.append((n, round(dev, 3), lv, f"出现{c}次·{pct:.1f}%（理论2.7%）"))
    return out


def build_candidates(draws, rec_nums=None, extra_bonus=None):
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
    # 自学习规则得分（必须先算，再排序）
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

    if extra_bonus:
        for _n, _w in extra_bonus.items():
            try:
                add(int(_n), "台/官倾向", float(_w))
            except Exception:
                pass

    _rest = sorted(((n, s) for n, s in score.items() if n not in _rec),
                   key=lambda x: (-x[1], x[0]))
    _strong = [(n, s) for n, s in _rest if s >= 2]
    _weak = [(n, s) for n, s in _rest if s < 2]
    ranked = [(n, score.get(n, 0)) for n in _rec]

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
    if "_roulette_profiles" not in st.session_state:
        st.session_state["_roulette_profiles"] = load_profiles(H)
    if "_roulette_known_names" not in st.session_state:
        st.session_state["_roulette_known_names"] = load_known_names(H)

    _d1, _d2, _d3 = st.columns([1, 1, 2])
    with _d1:
        # 已知荷官（云端名单 + 档案 + 本次会话）
        _known = set(st.session_state.get("_roulette_known_names", []) or [])
        for _d0 in st.session_state.get("_roulette_dealers", []) or []:
            _nmx = _norm_name(_d0.get("name"))
            if _nmx:
                _known.add(_nmx)
        for _k0 in (st.session_state.get("_roulette_profiles") or {}).keys():
            if str(_k0).startswith("官:"):
                _nmx = _norm_name(str(_k0)[2:])
                if _nmx:
                    _known.add(_nmx)
        _known = sorted(_known)
        _cur_name = _norm_name(st.session_state.get("_roulette_dealer"))

        _supports_new = False
        try:
            import inspect as _insp
            _supports_new = ("accept_new_options" in
                             _insp.signature(st.selectbox).parameters)
        except Exception:
            _supports_new = False

        if _supports_new:
            _idx0 = _known.index(_cur_name) if _cur_name in _known else 0
            _dealer = st.selectbox(
                "荷官（输入关键字筛选历史名字；没有就整段输入新名字）",
                _known, index=_idx0, key="rou_dealer_one",
                accept_new_options=True,
                placeholder="例：输入「黄」会显示 黄东东、黄小小；"
                            "没有就输入全名")
            _dealer = _norm_name(_dealer)
        else:
            _opts = _known + ["➕ 新增荷官"]
            _idx = _opts.index(_cur_name) if _cur_name in _opts else len(_opts) - 1
            _sel = st.selectbox("选择荷官（点开可直接输入名字筛选）", _opts,
                                index=_idx, key="rou_dealer_sel")
            if _sel == "➕ 新增荷官":
                _dealer = _norm_name(st.text_input("输入荷官全名", value="",
                                                   key="rou_dealer_name"))
            else:
                _dealer = _sel

        if _dealer:
            st.session_state["_roulette_dealer"] = _dealer
            _kn = set(st.session_state.get("_roulette_known_names", []) or [])
            if _dealer not in _kn:
                _kn.add(_dealer)
                st.session_state["_roulette_known_names"] = sorted(_kn)
                try:
                    save_known_names(H, sorted(_kn))
                except Exception:
                    pass

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
            _okp = False
            try:
                _prof3 = st.session_state.get("_roulette_profiles") or load_profiles(H)
                st.session_state["_roulette_profiles"] = _prof3
                _okp = save_profiles(H, _prof3)
                save_known_names(H, st.session_state.get(
                    "_roulette_known_names", []) or [])
            except Exception:
                _okp = False
            st.success("已标记换荷官，统计从本期重新开始" +
                       ("｜档案已自动保存到云端" if _okp
                        else "｜档案保存失败（网络或权限）"))
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
            try:
                _prof = load_profiles(H)
                _prev = draws[-2] if len(draws) >= 2 else None
                _dlr = _norm_name(st.session_state.get("_roulette_dealer", ""))
                _keys = ["官:" + _dlr] if _dlr else []
                if not _keys:
                    st.warning("还没有选择荷官：本次只记录号码，不写档案")
                record_spin(_prof, _keys, int(num), _prev)
                st.session_state["_roulette_profiles"] = _prof
                if _keys and not save_profiles(H, _prof):
                    st.warning("档案写入云端失败（稍后可点底部按钮重试）")
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
        _dlr0 = st.session_state.get("_roulette_dealer", "")
        _pf0 = (st.session_state.get("_roulette_profiles") or {}).get("官:" + _dlr0) \
            if _dlr0 else None
        if _pf0 and int(_pf0.get("spins", 0)) >= 40:
            st.markdown(f"### ☁ 云端档案：{_dlr0}"
                        f"（{int(_pf0.get('spins', 0))} 期）")
            _sp0 = int(_pf0["spins"])
            _nm0 = sorted(((int(a), b) for a, b in _pf0.get("nums", {}).items()),
                          key=lambda x: -x[1])[:10]
            st.dataframe(pd.DataFrame(
                [{"排名": i + 1, "号码": f"{a}", "出现": b,
                  "占比": f"{b/_sp0*100:.1f}%"} for i, (a, b) in enumerate(_nm0)]),
                use_container_width=True, hide_index=True)
            st.caption(
                f"大号 {_pf0.get('big',0)/_sp0*100:.0f}%｜"
                f"单数 {_pf0.get('odd',0)/_sp0*100:.0f}%｜"
                f"红波 {_pf0.get('red',0)/_sp0*100:.0f}%｜"
                f"姐妹 {_pf0.get('sister',0)/max(1,_sp0-1)*100:.0f}%｜"
                f"相邻 {_pf0.get('adj',0)/max(1,_sp0-1)*100:.0f}%")
            _seq0 = [int(x) for x in (_pf0.get("seq") or [])][-300:]
            st.markdown("### 🎯 候选号码（依据该荷官的云端规则）")
            if len(_seq0) >= 40:
                st.caption(f"用云端保存的 {len(_seq0)} 期开奖序列，"
                           f"重新学习该荷官的规则后给出候选。")
                _top0, _ = smart_top3(_seq0)
                _rec0 = [n for n, _, _ in _top0] if _top0 else []
                _om0, _al0, _lv0 = build_candidates(_seq0, _rec0)
                if _al0:
                    st.markdown("**该荷官的达标项（基于其历史序列）**")
                    for _k1, _v1 in _al0:
                        st.warning(f"{_k1}：{'、'.join(_v1)}")
                _rows0 = []
                _rhit0 = st.session_state.get("_roulette_rhit") or {}
                for _n0, _s0, _lv0b, _wh0 in _lv0:
                    _a0 = attrs_of(_n0)
                    _rc0 = int(_rhit0.get(_n0, 0))
                    _j0 = ("🔥 极可能开" if _rc0 >= 3 else
                           "⭐ 较可能" if _rc0 == 2 else
                           "○ 留意" if _rc0 == 1 else "")
                    _rows0.append({"等级": _lv0b, "号码": _n0, "判断": _j0,
                                   "得分": round(_s0, 2),
                                   "命中条件": "、".join(sorted(set(_wh0))),
                                   "尾数": _a0["尾数"], "生肖": _a0["生肖"]})
                st.dataframe(pd.DataFrame(_rows0), use_container_width=True,
                             hide_index=True)
                if _lv0:
                    _rc0m = {r0["号码"]: int(_rhit0.get(r0["号码"], 0))
                             for r0 in _rows0}
                    _hot0 = sorted([v0 for v0 in _rc0m if _rc0m[v0] >= 3],
                                   key=lambda v0: -_rc0m[v0])[:3]
                    if _hot0:
                        st.success("🔥 极可能开出：" +
                                   "、".join(f"{v0}" for v in _hot0))
            else:
                _fr0 = frequency_candidates(_pf0)
                if _fr0:
                    st.caption("该荷官云端序列还不足 40 期，暂不出候选：")
                    st.dataframe(pd.DataFrame(
                        [{"号码": _n0, "判断": _lv0,
                          "偏离": f"{_dev0*100:+.0f}%", "说明": _why0}
                         for _n0, _dev0, _lv0, _why0 in _fr0]),
                        use_container_width=True, hide_index=True)
                else:
                    st.info("该荷官档案样本还太少，继续录入即可。")
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

    # ---- 读取云端档案，展示台/荷官特点 ----
    _prof = st.session_state.get("_roulette_profiles")
    if _prof is None:
        _prof = load_profiles(H)
        st.session_state["_roulette_profiles"] = _prof
    _dlr_now = st.session_state.get("_roulette_dealer", "")
    _prof_use = _prof.get("官:" + _dlr_now) if _dlr_now else None

    _bonus = {}
    if _prof_use and int(_prof_use.get("spins", 0)) >= 30:
        _sp = int(_prof_use["spins"])
        _nm3 = sorted(((int(a), b) for a, b in _prof_use.get("nums", {}).items()),
                      key=lambda x: -x[1])[:6]
        _zd3 = sorted(_prof_use.get("zod", {}).items(), key=lambda x: -x[1])[:2]
        _who = _dlr_now
        st.info(
            f"☁ 云端档案｜{_who} 累计 {_sp} 期："
            f"热号 {'、'.join(f'{a}' for a, _ in _nm3)}｜"
            f"生肖 {'、'.join(f'{a}{b/_sp*100:.0f}%' for a, b in _zd3)}｜"
            f"大号 {_prof_use.get('big',0)/_sp*100:.0f}%｜"
            f"姐妹 {_prof_use.get('sister',0)/max(1,_sp-1)*100:.0f}%｜"
            f"相邻 {_prof_use.get('adj',0)/max(1,_sp-1)*100:.0f}%")
        _use_bonus = st.checkbox(
            "把这个台/荷官的历史倾向计入候选（轻度加权）", value=False,
            key="rou_use_bonus")
        if _use_bonus:
            for _a, _b2 in _nm3:
                _bonus[_a] = 0.5

    # ---- 冷启动：本地不足 40 期但云端有该荷官档案 ----
    _cold = False
    _cloud_seq = []
    if _prof_use:
        _cloud_seq = [int(x) for x in (_prof_use.get("seq") or [])][-300:]
    if len(_cloud_seq) >= 40:
        # 有档案时：用云端序列（含历史）作为主统计源
        _calc = _cloud_seq
        _cold = len(draws) < 40
        if not _cold:
            st.caption(f"☁ 参考云端「{_dlr_now}」档案 {len(_cloud_seq)} 期"
                       f"（本地 {len(draws)} 期已包含在内）")
        _sp = int(_prof_use["spins"])
        _cnt = {int(k): v for k, v in _prof_use.get("nums", {}).items()}
        _expect = _sp / 37.0
        _hot = sorted(_cnt.items(), key=lambda x: -x[1])[:10]
        for _n, _c in _hot:
            _bonus[_n] = round(min(3.0, max(0.3, (_c / _expect - 1) * 1.5)), 2)
        st.success(f"☁ 冷启动：使用云端「{_dlr_now}」档案"
                   f"（累计 {_sp} 期，最近序列 {len(_cloud_seq)} 期）"
                   f"——系统已用它的历史序列学习规则")
        _sis_rate = _prof_use.get("sister", 0) / max(1, _sp - 1)
        _adj_rate = _prof_use.get("adj", 0) / max(1, _sp - 1)
        if _sis_rate >= 0.08:
            st.warning(f"该荷官姐妹码偏高（{_sis_rate*100:.0f}%，理论 5.4%）")
        if _adj_rate >= 0.08:
            st.warning(f"该荷官轮盘相邻偏高（{_adj_rate*100:.0f}%，理论 5.4%）")

    if len(_calc) < 40:
        _pf_fb = (st.session_state.get("_roulette_profiles") or {}).get(
            "官:" + _norm_name(st.session_state.get("_roulette_dealer")))
        if _pf_fb and int(_pf_fb.get("spins", 0)) >= 40:
            _fr1 = frequency_candidates(_pf_fb)
            if _fr1:
                st.success(f"☁ 该荷官云端档案 {int(_pf_fb.get('spins',0))} 期"
                           f"（缺完整序列）→ 按长期频率出候选")
                st.markdown("### 🎯 候选号码（依据荷官长期频率）")
                st.dataframe(pd.DataFrame(
                    [{"号码": a, "判断": b, "偏离": f"{c*100:+.0f}%",
                      "说明": d} for a, c, b, d in _fr1]),
                    use_container_width=True, hide_index=True)
                return
        st.warning(f"📉 当前可用数据仅 {len(_calc)} 期（不足 40 期），"
                   f"暂不给出候选号码。请继续录入或换一位有档案的荷官。")
        return

    _top3, _w = smart_top3(_calc)
    _rec = [n for n, _, _ in _top3] if _top3 else []
    if _cold and not _rec:
        _rec = [n for n, _ in sorted(_bonus.items(), key=lambda x: -x[1])[:REC_N]]
    om, alerts, levels = build_candidates(_calc, _rec, extra_bonus=_bonus)
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

    # ---- 荷官状态说明 ----
    _dlr_s = _norm_name(st.session_state.get("_roulette_dealer"))
    if _dlr_s:
        _pf_s = (st.session_state.get("_roulette_profiles") or {}).get(
            "官:" + _dlr_s)
        _seq_s = [int(x) for x in ((_pf_s or {}).get("seq") or [])]
        if _seq_s and len(_seq_s) >= 40:
            _tot_s = int((_pf_s or {}).get("spins", 0))
            st.success(f"✅ 已更换为「{_dlr_s}」荷官｜累计摇珠 {_tot_s} 次"
                       f"（可用序列 {len(_seq_s)} 期）→ 即刻按他的规则出候选")
        elif _seq_s:
            st.warning(f"🆕「{_dlr_s}」荷官累计 {int((_pf_s or {}).get('spins',0))} 次"
                       f"（序列 {len(_seq_s)} 期，不足 40），"
                       f"样本偏少，候选仅供参考")
        else:
            st.warning(f"🆕 新荷官「{_dlr_s}」｜暂无历史规则，"
                       f"满 40 期才出规则候选")
    else:
        st.info("尚未选择荷官：候选只按本页数据计算")

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
        _rcmap = {r2["号码"]: int(_rhit.get(r2["号码"], 0)) for r2 in rows}
        _hot_all = sorted([r2["号码"] for r2 in rows
                           if _rcmap.get(r2["号码"], 0) >= 3],
                          key=lambda v: -_rcmap.get(v, 0))
        _hot = _hot_all[:3]
        _mid = [r2["号码"] for r2 in rows
                if "较可能" in str(r2["判断"])]
        if _hot:
            _extra = len(_hot_all) - len(_hot)
            st.success("🔥 极可能开出：" + "、".join(f"{v}" for v in _hot)
                       + (f"（另有 {_extra} 个也命中多条规则，见下表）"
                          if _extra > 0 else "（最高置信）"))
        elif _mid:
            st.info("⭐ 较可能：" + "、".join(f"{v}" for v in _mid))
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

    # 按名字合并（同一荷官多次上钟也合成一行）
    _by_name = {}
    for _nm, _st0, _nums in _segs:
        if not _nums:
            continue
        _k0 = _norm_name(_nm) or "未命名"
        _by_name.setdefault(_k0, []).extend(_nums)

    if not _by_name:
        st.caption("还没有录满一期的荷官记录。")
    else:
        _cur_name0 = _norm_name(st.session_state.get("_roulette_dealer"))
        _profs_all = st.session_state.get("_roulette_profiles") or {}
        _rows_d = []
        for _nm, _nums in sorted(_by_name.items(), key=lambda x: -len(x[1])):
            _pf = _profs_all.get("官:" + _nm) or {}
            _sp_local = len(_nums)
            _sp_cloud = int(_pf.get("spins", 0))
            _sp = max(_sp_local, _sp_cloud)
            if _sp <= 0:
                continue

            # 计数优先用云端（更全），否则用本地
            if _sp_cloud >= _sp_local and _pf.get("nums"):
                _cnt = {int(k): int(v) for k, v in _pf["nums"].items() if k.isdigit()}
                _zcnt = dict(_pf.get("zod") or {})
                _sis = int(_pf.get("sister", 0))
                _adj = int(_pf.get("adj", 0))
                _red = int(_pf.get("red", 0))
                _odd = int(_pf.get("odd", 0))
                _big = int(_pf.get("big", 0))
            else:
                _cnt = dict(Counter(_nums))
                _zcnt = dict(Counter(zodiac_of(x) for x in _nums))
                _sis = sum(1 for i2 in range(1, len(_nums))
                           if _nums[i2] in sister(_nums[i2 - 1]))
                _adj = sum(1 for i2 in range(1, len(_nums))
                           if _nums[i2] in wheel_neighbors(_nums[i2 - 1]))
                _red = sum(1 for x in _nums
                           if x in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36})
                _odd = sum(1 for x in _nums if x % 2)
                _big = sum(1 for x in _nums if x >= 19)

            _tot = sum(_cnt.values()) or 1

            def _pct(c):
                return f"{c / _tot * 100:.0f}%"

            _bal_red = _red
            _bal_blue = _tot - _red - _cnt.get(0, 0)
            _bal_lst = [("红波", _bal_red), ("蓝波", _bal_blue),
                        ("绿(0)", _cnt.get(0, 0))]
            _bal = max(_bal_lst, key=lambda x: x[1])
            _big_s = "大(19-36)" if _big * 2 >= _tot else "小(0-18)"
            _odd_s = "单" if _odd * 2 >= _tot else "双"

            _segc = {}
            _tailc = {}
            _secc = {}
            for _n2, _c2 in _cnt.items():
                _segc[f"{_n2//10*10}-{_n2//10*10+9}" if _n2 < 30 else "30-36"] = \
                    _segc.get(f"{_n2//10*10}-{_n2//10*10+9}" if _n2 < 30 else "30-36", 0) + _c2
                _tailc[f"{_n2%10}尾"] = _tailc.get(f"{_n2%10}尾", 0) + _c2
                _sk = f"第{POS[_n2]//6+1}段"
                _secc[_sk] = _secc.get(_sk, 0) + _c2
            _seg_best = max(_segc.items(), key=lambda x: x[1]) if _segc else ("—", 0)
            _tail_best = max(_tailc.items(), key=lambda x: x[1]) if _tailc else ("—", 0)
            _sec_best = max(_secc.items(), key=lambda x: x[1]) if _secc else ("—", 0)
            _zod_best = max(_zcnt.items(), key=lambda x: x[1]) if _zcnt else ("—", 0)
            _top3 = "、".join(f"{v}" for v, _ in
                              sorted(_cnt.items(), key=lambda x: -x[1])[:3])

            _rows_d.append({
                "荷官": _nm,
                "本场期数": _sp_local,
                "累计摇珠": _sp_cloud or _sp_local,
                "采用期数": _sp,
                "波色偏好": f"{_bal[0]} {_pct(_bal[1])}",
                "单双": f"{_odd_s} {_pct(_odd if _odd_s == '单' else _tot - _odd)}",
                "大小": f"{_big_s} {_pct(_big if _big_s.startswith('大') else _tot - _big)}",
                "号码段": f"{_seg_best[0]} {_pct(_seg_best[1])}",
                "尾数": f"{_tail_best[0]} {_pct(_tail_best[1])}",
                "轮盘扇区": f"{_sec_best[0]} {_pct(_sec_best[1])}",
                "生肖偏好": f"{_zod_best[0]} {_pct(_zod_best[1])}",
                "姐妹码": f"{_sis/max(1,_sp-1)*100:.0f}%",
                "轮盘相邻": f"{_adj/max(1,_sp-1)*100:.0f}%",
                "最热号码": _top3,
                "当前": "✅" if _nm == _cur_name0 else "",
            })
        # 选择查看某位荷官（去重）
        _names = sorted(_by_name.keys())
        _view = st.selectbox("查看荷官详情", _names, index=0,
                             key="rou_view_dealer")
        _vnums = _by_name.get(_view, [])
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
            _c6d = Counter(zodiac_of(x) for x in _vnums)
            _c7d = Counter("与上期姐妹" if _vnums[i2] in sister(_vnums[i2-1])
                           else "非姐妹" for i2 in range(1, len(_vnums)))
            _c8d = Counter("与上期轮盘相邻"
                           if _vnums[i2] in wheel_neighbors(_vnums[i2-1])
                           else "非相邻" for i2 in range(1, len(_vnums)))
            _dd = []
            for _title, _cc in (("波色", _c1d), ("单双", _c2d),
                                ("大小", _c3d), ("尾数", _c4d),
                                ("轮盘扇区", _c5d), ("生肖", _c6d),
                                ("姐妹码", _c7d), ("轮盘相邻", _c8d)):
                _txt = "、".join(f"{v}{k/_n1*100:.0f}%"
                                for v, k in _cc.most_common(3))
                _dd.append({"维度": _title, "分布": _txt})
            st.dataframe(pd.DataFrame(_dd), use_container_width=True,
                         hide_index=True)
        st.caption("说明：同一荷官多次上钟已合并为一行；样本少时仅供参考。")

    # ---------- 云端记忆档案 ----------
    st.divider()
    st.markdown("### ☁ 云端记忆档案（不参与推荐，仅用于识别）")
    _prof2 = st.session_state.get("_roulette_profiles")
    if not _prof2:
        _prof2 = load_profiles(H)
        st.session_state["_roulette_profiles"] = _prof2
    # 显示前再按名字合并一次，确保绝不出现同名
    _merged = {}
    for _k, _v in (_prof2 or {}).items():
        if not isinstance(_v, dict) or not str(_k).startswith("官:"):
            continue
        _nmx = _norm_name(str(_k)[2:])
        if not _nmx:
            continue
        _nkx = "官:" + _nmx
        if _nkx in _merged:
            _merge_profile(_merged[_nkx], _v)
        else:
            _merged[_nkx] = dict(_v)
    _prof2 = _merged
    st.session_state["_roulette_profiles"] = _prof2

    if not _prof2:
        st.caption("云端还没有档案；每录入一期会自动累积（清空页面数据也不影响）。")
    else:
        _prows = []
        for _k, _v in _prof2.items():
            _sp = int(_v.get("spins", 0))
            if not _sp:
                continue
            _nm2 = sorted(((int(a), b) for a, b in _v.get("nums", {}).items()),
                          key=lambda x: -x[1])[:3]
            _zod2 = sorted(_v.get("zod", {}).items(), key=lambda x: -x[1])[:2]
            _prows.append({
                "荷官": str(_k)[2:],
                "累计期数": _sp,
                "可用序列": len(_v.get("seq", []) or []),
                "最热号码": "、".join(f"{a}" for a, _ in _nm2),
                "最热生肖": "、".join(f"{a}{b/_sp*100:.0f}%" for a, b in _zod2),
                "大号%": f"{_v.get('big',0)/_sp*100:.0f}%",
                "单数%": f"{_v.get('odd',0)/_sp*100:.0f}%",
                "红波%": f"{_v.get('red',0)/_sp*100:.0f}%",
                "姐妹%": f"{_v.get('sister',0)/max(1,_sp-1)*100:.0f}%",
                "相邻%": f"{_v.get('adj',0)/max(1,_sp-1)*100:.0f}%",
            })
        if _prows:
            st.dataframe(pd.DataFrame(_prows), use_container_width=True,
                         hide_index=True)
            _del_names = [str(r0["荷官"]) for r0 in _prows]
            _dc1, _dc2 = st.columns([2, 1])
            with _dc1:
                _del_pick = st.selectbox("选择要删除档案的荷官", _del_names,
                                         key="rou_prof_del")
            with _dc2:
                _del_ok = st.checkbox("确认删除", key="rou_prof_del_ok")
            if st.button("🗑 删除该荷官档案", key="rou_prof_del_btn"):
                if not _del_ok:
                    st.warning("请先勾选「确认删除」")
                else:
                    _np = dict(_prof2)
                    _np.pop("官:" + _del_pick, None)
                    st.session_state["_roulette_profiles"] = _np
                    if save_profiles(H, _np):
                        _kn2 = [x for x in (st.session_state.get(
                            "_roulette_known_names") or []) if x != _del_pick]
                        st.session_state["_roulette_known_names"] = _kn2
                        try:
                            save_known_names(H, _kn2)
                        except Exception:
                            pass
                        st.success(f"已删除「{_del_pick}」的云端档案")
                        st.rerun()
                    else:
                        st.error("删除失败：云端写入失败")

            st.caption("档案只用于识别台/荷官的长期倾向，"
                       "当前推荐仍只看页面上录入的数据。")
        else:
            st.caption("档案为空")
