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
        except Exception:
            data = []
    st.session_state["_roulette_hist"] = data
    return data


def save_history(loader, draws):
    st.session_state["_roulette_hist"] = list(draws)
    fn = loader.get("gh_write")
    if not fn:
        return False
    try:
        fn(HIST_FILE, json.dumps({"draws": draws}, ensure_ascii=False),
           "轮盘记录更新")
        return True
    except Exception:
        return False


# ============================================================
# 遗漏计算
# ============================================================
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
    if len(rows) < 200:
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
    if len(draws) < 80:
        return None, None
    w = learn_weights(draws)
    if not w:
        return None, None
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
            z += w[f] * ((rows[n][i] - means[i]) / sds[i] if sds[i] else 0)
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

    for t in hot_tails:
        for num in range(37):
            if str(num % 10) == t:
                add(num, f"尾{t}")

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
                for _num in range(37):
                    if attrs_of(_num)[_key] == _v:
                        add(_num, f"{_name}{_v}", 1)
    # 生肖遗漏号码不再写入候选（按要求）
    # 姐妹码只提醒，不写入候选
    # 轮盘相邻只提醒，不写入候选

    # 属性重复加权：同号码命中多个不同属性条件
    _rec = [int(x) for x in (rec_nums or [])][:REC_N]
    _rest = sorted(((n, s) for n, s in score.items() if n not in _rec),
                   key=lambda x: (-x[1], x[0]))
    _strong = [(n, s) for n, s in _rest if s >= 2]
    _weak = [(n, s) for n, s in _rest if s < 2]
    ranked = [(n, score.get(n, 0)) for n in _rec]
    for n, s in _strong + _weak:
        if len(ranked) >= MAX_PICK:
            break
        if n not in _rec:
            ranked.append((n, s))
    ranked = ranked[:MAX_PICK]
    levels = []
    if ranked:
        top = ranked[0][1]
        for num, sc in ranked:
            tags = set(why[num])
            if num in _rec:
                lv = "推荐"
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

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        num = st.number_input("本期开奖号码", 0, 36, 0, 1, key="rou_num")
    with c2:
        if st.button("➕ 添加", use_container_width=True, key="rou_add"):
            draws = draws + [int(num)]
            ok = save_history(H, draws)
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

    _top3, _w = smart_top3(draws)
    _rec = [n for n, _, _ in _top3] if _top3 else []
    om, alerts, levels = build_candidates(draws, _rec)
    last_no = draws[-1]
    _sg, _ag, _sh, _ah = event_gaps(draws)
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
            rows.append({"等级": lv, "号码": num, "得分": sc,
                         "命中条件": "、".join(sorted(set(wh))),
                         "尾数": a["尾数"], "生肖": a["生肖"],
                         "四宝": a["四宝"], "物象": a["物象"],
                         "五行尾": a["五行尾"], "生肖五行": a["生肖五行"],
                         "阴阳天地": a["阴阳天地"], "波单双": a["波单双"]})
        dfc = pd.DataFrame(rows)
        st.dataframe(dfc, use_container_width=True, hide_index=True)
        st.download_button("📥 下载候选",
                           dfc.to_csv(index=False).encode("utf-8-sig"),
                           file_name="轮盘候选.csv", mime="text/csv",
                           key="rou_dl")

    st.markdown("### 🧠 系统推荐 4 码（已并入上方候选）")
    if not _top3:
        st.caption("历史数据不足（建议 80 期以上），暂不推荐")
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
