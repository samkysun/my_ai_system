# -*- coding: utf-8 -*-
"""
🎡 轮盘预测系统（欧式轮盘 0~36）
------------------------------------------------------------------
· 输入每次开奖号码，自动累计、自动核算
· 统计：尾数遗漏、生肖遗漏、姐妹码遗漏、轮盘相邻遗漏
· 触发阈值：尾数 20 期、生肖 15 期、姐妹码 20 期、相邻 20 期
· 输出：最多 12 个候选号码，分重点 / 次重点 / 次要
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

TH_TAIL, TH_ZODIAC, TH_SISTER, TH_ADJ = 20, 15, 20, 20
MAX_PICK = 12

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
    """返回各维度的遗漏期数"""
    n = len(draws)
    last = {}

    def upd(key, i):
        last[key] = i

    for i, x in enumerate(draws):
        a = attrs_of(x)
        upd(("尾", a["尾数"]), i)
        upd(("肖", a["生肖"]), i)
        for s in sister(x):
            upd(("姐", s), i)
        for w in wheel_neighbors(x):
            upd(("邻", w), i)

    def gap(key):
        return n - (last.get(key, -1) + 1) if key in last else n

    out = {
        "尾数": {str(t): gap(("尾", str(t))) for t in range(10)},
        "生肖": {z: gap(("肖", z)) for z in ZODIAC},
        "姐妹码": {str(x): gap(("姐", x)) for x in range(37)},
        "相邻码": {str(x): gap(("邻", x)) for x in range(37)},
    }
    return out


# ============================================================
# 生成候选
# ============================================================
def build_candidates(draws):
    om = omissions(draws)
    if not draws:
        return om, [], []

    last_no = draws[-1]
    alerts = []

    hot_tails = [t for t, g in om["尾数"].items() if g >= TH_TAIL]
    if hot_tails:
        alerts.append(("尾数", hot_tails))
    hot_z = [z for z, g in om["生肖"].items() if g >= TH_ZODIAC]
    if hot_z:
        alerts.append(("生肖", hot_z))

    sis = sister(last_no)
    sis_gap = min(om["姐妹码"].get(str(s), 0) for s in sis)
    if sis_gap >= TH_SISTER:
        alerts.append(("姐妹码", [str(s) for s in sis]))

    adj = wheel_neighbors(last_no)
    adj_gap = min(om["相邻码"].get(str(a), 0) for a in adj)
    if adj_gap >= TH_ADJ:
        alerts.append(("轮盘相邻", [str(a) for a in adj]))

    # 每个号码累计"命中条件数"
    score = Counter()
    why = defaultdict(list)

    def add(num, tag):
        if 0 <= num <= 36:
            score[num] += 1
            why[num].append(tag)

    for t in hot_tails:
        for num in range(37):
            if str(num % 10) == t:
                add(num, f"尾{t}")
    for z in hot_z:
        for num in range(37):
            if zodiac_of(num) == z:
                add(num, f"肖{z}")
    if sis_gap >= TH_SISTER:
        for s in sis:
            add(s, "姐妹")
    if adj_gap >= TH_ADJ:
        for a in adj:
            add(a, "轮盘邻")

    # 属性重复加权：同号码命中多个不同属性条件
    ranked = sorted(score.items(), key=lambda x: (-x[1], x[0]))[:MAX_PICK]
    levels = []
    if ranked:
        top = ranked[0][1]
        for num, sc in ranked:
            if sc >= top and sc >= 3:
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
    st.caption("输入每期开奖号码，自动统计遗漏并给出候选号码（≤12 个）。")

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

    om, alerts, levels = build_candidates(draws)
    last_no = draws[-1]
    st.markdown(f"**上期号码：{last_no}**　"
                f"姐妹码 {sister(last_no)}　"
                f"轮盘相邻 {wheel_neighbors(last_no)}")

    st.markdown("### 🚨 提醒下注")
    if not alerts:
        st.caption("暂无达到阈值的项目")
    for kind, vals in alerts:
        st.warning(f"{kind} 遗漏达标：{'、'.join(vals)}")

    st.markdown("### 🎯 候选号码（最多 12 个）")
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

    with st.expander("📊 遗漏明细", expanded=False):
        t1, t2 = st.tabs(["尾数", "生肖"])
        with t1:
            st.dataframe(pd.DataFrame(
                [{"尾数": k, "遗漏": v} for k, v in om["尾数"].items()]),
                use_container_width=True, hide_index=True)
        with t2:
            st.dataframe(pd.DataFrame(
                [{"生肖": k, "遗漏": v} for k, v in om["生肖"].items()]),
                use_container_width=True, hide_index=True)
