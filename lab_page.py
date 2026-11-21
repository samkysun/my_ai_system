# -*- coding: utf-8 -*-
"""
🔬 研究中心（实验沙盒）
------------------------------------------------------------------
· 所有实验都在这里做，不影响正式页面
· 每做完一个实验，可保存到看板（source 统一为「研究所」）
· 一键清空：删掉本页所有实验数据（看板里 source=研究所 的条目）
· 想彻底恢复原状：删除本文件 + 去掉菜单一行即可（没有任何其它依赖）
------------------------------------------------------------------
"""
import itertools
import time
from collections import Counter
from datetime import datetime

import pandas as pd
import streamlit as st

SRC_TAG = "研究中心"


# =====================================================================
# 通用：载入号码数据
# =====================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def _load_index6(_loader):
    """期号 + 6 个平码（升序）"""
    rows = _loader("_index6.csv", None)
    out = []
    if not rows:
        return out
    for r in rows[1:]:
        if len(r) < 7:
            continue
        p = str(r[0]).strip()
        try:
            nums = tuple(int(float(r[1 + k] or 0)) for k in range(6))
        except Exception:
            continue
        if p and all(nums):
            out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _load_attr(_loader):
    rows = _loader("_attr_map.csv", None)
    out = {}
    if not rows:
        return out
    hdr = [str(x).strip() for x in rows[0]]
    for r in rows[1:]:
        if not r or not str(r[0]).strip().isdigit():
            continue
        out[int(float(r[0]))] = {hdr[i]: str(r[i]).strip()
                                 for i in range(1, min(len(hdr), len(r)))}
    return out


def _num_of(cond, amap):
    """把杀号条件翻译成号码"""
    it = (cond or "").strip()
    if not it or not amap:
        return []
    if it.endswith("尾") and it[:-1].isdigit():
        return [n for n, a in amap.items() if a.get("尾数") == it[:-1]]
    if it.endswith("合"):
        return [n for n, a in amap.items() if a.get("数字合") == it]
    if it.endswith("段"):
        return [n for n, a in amap.items() if a.get("段数") == it]
    if it.endswith("门"):
        return [n for n, a in amap.items() if a.get("门数") == it]
    if it.endswith("号"):
        return [n for n, a in amap.items() if a.get("数字五行") == it[:-1]]
    if it.endswith("肖"):
        if it[:-1] in "金木水火土":
            return [n for n, a in amap.items() if a.get("生肖五行") == it[:-1]]
        return [n for n, a in amap.items() if a.get("生肖") == it[:-1]]
    if "波" in it:
        return [n for n, a in amap.items() if a.get("波单双") == it]
    return []


def _range_of(order, ball):
    UP = {1: (1, 20), 2: (2, 25), 3: (3, 30), 4: (4, 40),
          5: (15, 48), 6: (25, 49)}
    if order == "升序":
        return UP.get(int(ball), (1, 49))
    return (1, 49)


# =====================================================================
# 实验 A：单条件杀号回测
# =====================================================================
def _exp_single_kill(loader):
    st.markdown("#### 实验 A：单条件杀号回测")
    st.caption("输入一个杀号条件，统计历史上下期该球位是否真的避开了这些号。")

    c1, c2, c3 = st.columns(3)
    with c1:
        cond = st.text_input("杀号条件", "木肖", key="lab_a_cond",
                             placeholder="木肖 / 5尾 / 06合 / 3段")
    with c2:
        order = st.selectbox("排序", ["升序", "按序"], key="lab_a_order")
    with c3:
        ball = st.number_input("球位", 1, 6, 1, 1, key="lab_a_ball")

    c4, c5 = st.columns(2)
    with c4:
        year_from = st.text_input("起始年份", "2023", key="lab_a_year")
    with c5:
        mode = st.selectbox("判定口径",
                            ["被杀号的号码一个都没出", "被杀号的号码全没出(严格)",
                             "只看第一个被杀号"], key="lab_a_mode")

    if not st.button("▶ 运行实验 A", key="lab_a_run"):
        return

    data = _load_index6(loader)
    amap = _load_attr(loader)
    if not data or not amap:
        st.error("缺少 _index6.csv 或 _attr_map.csv")
        return

    nums = [n for n in _num_of(cond, amap)
            if _range_of(order, ball)[0] <= n <= _range_of(order, ball)[1]]
    if not nums:
        st.warning("这个条件在所选球位的区间里没有对应号码")
        return

    trial = hit = 0
    detail = []
    for period, balls in data:
        if period[:4] < year_from:
            continue
        draw = set(balls)
        if not (draw & set(nums)):
            continue
        trial += 1
        appeared = draw & set(nums)
        ok = (len(appeared) == 0) if mode.startswith("被杀号的号码一个都没出") else True
        if mode == "只看第一个被杀号":
            ok = nums[0] not in draw
        if ok:
            hit += 1
        detail.append((period, sorted(appeared)))

    if not trial:
        st.warning("样本为 0")
        return

    rate = hit / trial
    st.metric("杀中率", f"{rate*100:.2f}%", f"{trial} 期样本")
    st.caption(f"被杀号码：{' '.join(f'{n:02d}' for n in nums)}")
    st.dataframe(pd.DataFrame(
        [{"期号": p, "实际开出": " ".join(f"{x:02d}" for x in a)}
         for p, a in detail[-30:]]), use_container_width=True, hide_index=True)

    _save(loader, f"实验A {cond} {order}{ball}球 {year_from}+",
          f"条件 {cond}｜{order}第{ball}球｜{year_from} 年起\n"
          f"被杀号码 {' '.join(f'{n:02d}' for n in nums)}\n"
          f"样本 {trial} 期，杀中 {hit} 期，杀中率 {rate*100:.2f}%")


# =====================================================================
# 实验 B：组合池命中率
# =====================================================================
def _exp_pool(loader):
    st.markdown("#### 实验 B：三码组合池命中率")
    st.caption("从历史里找出出现 ≥N 次的组合，看下一期命中的比例。")

    c1, c2, c3 = st.columns(3)
    with c1:
        minc = st.number_input("组合最少出现次数", 1, 10, 2, 1, key="lab_b_minc")
    with c2:
        year_from = st.text_input("起始年份", "2023", key="lab_b_year")
    with c3:
        limit = st.number_input("回测期数上限", 50, 3000, 300, 50, key="lab_b_limit")

    if not st.button("▶ 运行实验 B", key="lab_b_run"):
        return

    data = _load_index6(loader)
    if len(data) < 100:
        st.error("数据不足")
        return

    sets = [frozenset(b) for _, b in data]
    start = max(50, len(data) - int(limit))
    tot_pool = tot_hit = draws = win_draws = 0
    for i in range(start, len(data)):
        if data[i][0][:4] < year_from:
            continue
        seed = list(itertools.combinations(sorted(data[i - 1][1]), 3))
        seed_sets = [frozenset(c) for c in seed]
        cnt = Counter()
        for j in range(i - 1):
            if any(s.issubset(sets[j]) for s in seed_sets) and j + 1 < i - 1:
                for c in itertools.combinations(sorted(data[j + 1][1]), 3):
                    cnt[c] += 1
        pool = [c for c, n in cnt.items() if n >= int(minc)]
        if not pool:
            continue
        draws += 1
        tot_pool += len(pool)
        hit = sum(1 for c in pool if all(v in sets[i] for v in c))
        tot_hit += hit
        if hit:
            win_draws += 1

    if not draws:
        st.warning("没有样本")
        return

    st.metric("单注命中率", f"{tot_hit/tot_pool*100:.4f}%",
              f"{tot_hit} 命中 / {tot_pool} 注")
    st.metric("有命中的期数", f"{win_draws/draws*100:.2f}%", f"{draws} 期")
    st.caption(f"理论单注命中率 0.1086%（1/921）")
    _save(loader, f"实验B 组合池 ≥{minc}次 {year_from}+",
          f"组合池 ≥{minc} 次｜{year_from} 年起｜{draws} 期\n"
          f"平均每期 {tot_pool/draws:.1f} 注\n"
          f"单注命中率 {tot_hit/tot_pool*100:.4f}%（理论 0.1086%）\n"
          f"有命中 {win_draws} 期（{win_draws/draws*100:.2f}%）")


# =====================================================================
# 保存 / 清理
# =====================================================================
def _save(loader, title, text):
    fn = loader.get("board_add")
    if not fn:
        return
    if st.button(f"📌 保存实验结果到看板", key=f"lab_save_{abs(hash(title))%99999}"):
        try:
            fn(SRC_TAG, title, text)
            st.success("已保存到看板（来源：研究中心）")
        except Exception as e:
            st.warning(f"保存失败：{e}")


def _cleanup(loader):
    st.markdown("#### 🧹 清空研究中心数据")
    st.caption("只删除看板里来源为「研究中心」的条目，不影响其它页面的数据。")
    if not st.session_state.get("username") == st.secrets.get("ADMIN_USERNAME", "admin"):
        st.info("仅管理员可清空")
        return
    if st.button("🗑 清空研究中心全部数据", type="secondary", key="lab_clear"):
        ok = 0
        try:
            client = loader["supabase"]()
            if client:
                res = (client.table("ai_board").delete()
                       .eq("source", SRC_TAG).execute())
                ok = len(res.data or [])
        except Exception as e:
            st.warning(f"清空失败：{e}")
        st.session_state.pop("ai_board", None)
        st.success(f"已清理 {ok} 条（看板数据已重新载入）")
        time.sleep(0.6)
        st.rerun()

    st.divider()
    st.markdown("**想要彻底移除这个页面？**")
    st.code("1. 删除 lab_page.py\n2. 删掉 app.py 菜单里的 \"🧪 研究所\" 与分支\n"
            "3. 清空上面数据", language=None)


# =====================================================================
# 页面入口
# =====================================================================
def render(df_data, H):
    st.title("🔬 研究中心（实验沙盒）")
    st.caption("在这里试各种公式，不满意就一键清空；确认可用再迁到正式页面。")

    tab1, tab2, tab3 = st.tabs(["实验A 单条件杀号", "实验B 组合池", "清理"])
    with tab1:
        _exp_single_kill(H)
    with tab2:
        _exp_pool(H)
    with tab3:
        _cleanup(H)

    st.divider()
    st.caption(f"本页所有实验数据统一存入看板的「{SRC_TAG}」来源，便于一键清除。")
