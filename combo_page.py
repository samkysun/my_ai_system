# -*- coding: utf-8 -*-
"""组合联动（按 Excel「六选三组合」逻辑搬到网页）
   · 取 6 个号码 → 生成 C(6,3)=20 组
   · 每组去历史里找同时出现这 3 个号的期数
   · 统计其余号码出现次数，输出清单（可复制/打印）
   · 支持「七套替换」：用替换号替换某一位置后再生成
"""
import csv
import itertools
from collections import Counter

import pandas as pd
import streamlit as st

_INDEX = "_index.csv"


@st.cache_data(ttl=1800, show_spinner=False)
def _load_rows(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return list(csv.reader(f))


def _parse_index(rows):
    """返回 [(期号, [7 个升序号])] 旧->新"""
    out = []
    for r in rows[1:]:
        if len(r) < 15:
            continue
        p = str(r[0]).strip()
        if not p:
            continue
        try:
            nums = [int(float(r[1 + k] or 0)) for k in range(7)]
        except Exception:
            continue
        if not any(nums[:6]):
            continue
        out.append((p, nums))
    return out


def _parse_zong(rows):
    """总数据表：索引18=期数，索引19~25=1球~7球"""
    out = []
    if not rows:
        return out
    for r in rows[2:]:
        if len(r) < 26:
            continue
        p = str(r[18]).strip()
        if not p or p.lower() == "nan" or not p.replace(".", "").isdigit():
            continue
        nums = []
        ok = True
        for k in range(7):
            try:
                nums.append(int(float(str(r[19 + k]).strip())))
            except Exception:
                ok = False
                break
        if not ok or not any(nums[:6]):
            continue
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def _combos3(nums6):
    """6 个号里选 3 个 → 20 组（与 Excel 顺序一致）"""
    out = []
    for i in range(4):
        for j in range(i + 1, 5):
            for k in range(j + 1, 6):
                out.append((nums6[i], nums6[j], nums6[k]))
    return out


def _scan(history, combo):
    """找同时包含这 3 个号的历史期"""
    hit_periods = []
    rest = Counter()
    s = set(combo)
    for p, nums in history:
        if s.issubset(set(nums[:6])):
            hit_periods.append(p)
            for v in nums[:6]:
                if v not in s:
                    rest[v] += 1
    return hit_periods, rest


def render(df_data, H):
    st.title("🧩 组合联动")
    st.caption("按 Excel「六选三组合」的逻辑：6 个号选出 20 组三号组合，"
               "逐组去历史里找同时出现这 3 个号的期数，并统计其余号码出现次数。")

    # 优先用【总数据.xlsx → 总数据表】（与 Excel 一致）
    data = []
    _load = H.get("load_excel_data")
    if _load:
        try:
            with st.spinner("读取总数据表…"):
                zrows = _load("总数据.xlsx", "总数据表") or []
            data = _parse_zong(zrows)
        except Exception as e:
            st.warning(f"总数据表读取失败：{type(e).__name__}")
            data = []
    if not data:
        try:
            data = _parse_index(_load_rows(_INDEX))
        except Exception:
            data = []
    if not data:
        st.error("读不到数据（总数据表与 _index.csv 都失败）")
        return
    st.caption(f"数据源：总数据表　共 {len(data)} 期"
               f"（{data[0][0]} ~ {data[-1][0]}）")

    st.markdown("### 一、输入 6 个号码")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        mode = st.radio("取号方式", ["按历史期号", "手动输入"], key="cb_mode")
    per_list = [p for p, _ in reversed(data)]
    with c2:
        if mode == "按历史期号":
            pick = st.selectbox("选一期（自动填入该期 6 个平码）", per_list,
                                index=0, key="cb_period")
            cur = dict(data).get(pick, [0] * 7)[:6]
            st.caption(f"{pick} 期：{' '.join(f'{n:02d}' for n in cur)}")
        else:
            txt = st.text_input("输入 6 个号码，用逗号或空格分隔",
                                value="01,02,03,04,05,06", key="cb_manual")
            cur = []
            import re as _re
            for x in _re.findall(r"\d+", txt):
                cur.append(int(x))
            cur = cur[:6]
    with c3:
        replace_on = st.checkbox("七套替换模式", value=False, key="cb_rep")

    if len(cur) < 6:
        st.warning("需要 6 个号码")
        return
    if len(set(cur)) < 6:
        st.warning("号码有重复，请检查")
        return

    base = list(cur)
    repl_mode = False
    repl_pos = 0
    repl_num = 0
    if replace_on:
        r1, r2 = st.columns(2)
        with r1:
            repl_pos = st.selectbox("替换第几球", [1, 2, 3, 4, 5, 6], index=0,
                                    key="cb_pos") - 1
        with r2:
            repl_num = st.number_input("替换成哪个号码", 1, 49, 7, 1, key="cb_num")
        base[repl_pos] = int(repl_num)
        repl_mode = True

    st.markdown(f"**当前 6 个号码**：{' '.join(f'{n:02d}' for n in base)}"
                + (f"　（第{repl_pos+1}球已替换为 {int(repl_num):02d}）"
                   if repl_mode else ""))

    if st.button("▶ 开始分析", type="primary", key="cb_run"):
        st.session_state["cb_go"] = True

    if not st.session_state.get("cb_go"):
        st.info("点「开始分析」生成 20 组组合并统计")
        return

    combos = _combos3(base)
    st.markdown(f"### 二、20 组三号组合（共 {len(combos)} 组）")

    show_all = {}
    for idx, cmb in enumerate(combos, 1):
        hp, rest = _scan(data, cmb)
        show_all[idx] = (cmb, hp, rest)

    rows_t = []
    for idx, (cmb, hp, rest) in show_all.items():
        top = "、".join(f"{n:02d}({c})" for n, c in rest.most_common(8))
        rows_t.append({
            "序": idx,
            "组合": ",".join(f"{n:02d}" for n in cmb),
            "出现期数": len(hp),
            "其余号码（次数）": top or "—",
        })
    st.dataframe(pd.DataFrame(rows_t), use_container_width=True, hide_index=True)

    # 明细文本（可复制 / 打印）
    st.markdown("### 三、明细清单")
    lines = [f"========== 组合联动 ==========",
             f"号码：{' '.join(f'{n:02d}' for n in base)}", ""]
    for idx, (cmb, hp, rest) in show_all.items():
        lines.append(f"{idx:>2}. 组合 {','.join(f'{n:02d}' for n in cmb)}"
                     f"　出现 {len(hp)} 期")
        if hp:
            lines.append("　　最近出现：" + "、".join(hp[-5:]))
            lines.append("　　其余号码：" +
                         "　".join(f"{n:02d}×{c}" for n, c in rest.most_common(10)))
        lines.append("")
    txt = "\n".join(lines)
    st.code(txt, language=None)
    st.download_button("📥 下载清单", txt.encode("utf-8-sig"),
                       file_name="组合联动.txt", mime="text/plain",
                       key="cb_dl")
