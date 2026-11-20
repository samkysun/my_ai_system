# -*- coding: utf-8 -*-
"""组合联动（严格还原 Excel「组合联动分析」）
   · 输入 3 个数字 → 找「同一行 7 球中同时包含这 3 个号」的历史行（触发行）
   · 对每个触发行，取上一行（上期）的 7 个号
   · 统计上期号码出现频次（= 综合数字汇总）
   · 六选三 → 20 组批量跑，输出每组结果
"""
import csv
import re
from collections import Counter

import pandas as pd
import streamlit as st

_INDEX = "_index.csv"
TAGS = ["DE", "FG", "HI", "JK", "LM", "NO", "PQ"]


def _num(v):
    try:
        return int(float(str(v).strip()))
    except Exception:
        return 0


def _parse_zong(rows):
    """总数据表：索引18=期数，19~25=1球~7球（旧->新排序）"""
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
            v = str(r[19 + k]).strip()
            if v == "" or v.lower() == "nan":
                nums.append(0)
                continue
            try:
                nums.append(int(float(v)))
            except Exception:
                ok = False
                break
        if not ok or not any(nums[:6]):
            continue
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def _parse_index(rows):
    out = []
    for r in rows[1:]:
        if len(r) < 15:
            continue
        p = str(r[0]).strip()
        if not p:
            continue
        nums = [_num(r[1 + k]) for k in range(7)]
        if not any(nums[:6]):
            continue
        out.append((p, nums))
    out.sort(key=lambda x: x[0])
    return out


def _combos3(nums6):
    """6 选 3 → 20 组"""
    out = []
    for i in range(4):
        for j in range(i + 1, 5):
            for k in range(j + 1, 6):
                out.append((nums6[i], nums6[j], nums6[k]))
    return out


def _combos_from(pool, clean=True):
    """从给定号码池里选 3 个组合，可选去重"""
    seen = set()
    out = []
    n = len(pool)
    for i in range(n - 2):
        for j in range(i + 1, n - 1):
            for k in range(j + 1, n):
                cmb = tuple(sorted((pool[i], pool[j], pool[k])))
                if clean:
                    if cmb in seen:
                        continue
                    seen.add(cmb)
                out.append(cmb)
    return out


def analyze_combo(data, combo):
    """严格还原 组合联动分析：
       返回 dict：triggers=[(期号, nums, 上期期号, 上期nums)], 综合数字 Counter, 明细行"""
    s = set(combo)
    triggers = []
    for i, (p, nums) in enumerate(data):
        if s.issubset(set(nums)):
            if i >= 1:
                prev_p, prev_nums = data[i - 1]
                triggers.append((p, nums, prev_p, prev_nums))
    counter = Counter()
    detail = []
    for tp, tn, pp, pn in triggers:
        for v in pn:
            if v:
                counter[v] += 1
        detail.append((tp, tn, pp, pn))
    return {"triggers": triggers, "counter": counter, "detail": detail}


def _line(nums):
    return " ".join(f"{v:02d}" if v else "空" for v in nums)


def render(df_data, H):
    st.title("🧩 组合联动")
    st.caption("还原 Excel「组合联动分析」：3 个数字 → 找同时出现它们的历史行 → "
               "统计这些行的上一期号码（综合数字）频次。")

    # ---------- 数据 ----------
    data = []
    _load = H.get("load_excel_data")
    if _load:
        try:
            with st.spinner("读取总数据表…"):
                data = _parse_zong(_load("总数据.xlsx", "总数据表") or [])
        except Exception:
            data = []
    if not data:
        try:
            with open(_INDEX, encoding="utf-8-sig", errors="replace") as f:
                data = _parse_index(list(csv.reader(f)))
        except Exception:
            data = []
    if not data:
        st.error("读不到数据")
        return
    st.caption(f"数据源：总数据表　共 {len(data)} 期（{data[0][0]} ~ {data[-1][0]}）")

    # ---------- 输入 ----------
    st.markdown("### 一、输入")
    c1, c2 = st.columns([2, 2])
    with c1:
        mode = st.radio("方式", ["直接输入 3 个数字", "单套：6 个平码 → 20 组",
                                "多套：7 个号（含特码）→ 35 组"],
                        key="cb_mode")
    per_list = [p for p, _ in reversed(data)]
    combos = []
    with c2:
        if mode.startswith("直接"):
            txt = st.text_input("3 个数字（逗号分隔）", value="45,47,41", key="cb_three")
            three = [int(x) for x in re.findall(r"\d+", txt)][:3]
            combos = [tuple(sorted(three))] if len(three) == 3 else []
        else:
            pick = st.selectbox("选一期", per_list, index=0, key="cb_period")
            row = dict(data).get(pick, [0] * 7)
            if mode.startswith("单套"):
                cur = row[:6]
                st.caption(f"{pick} 期平码：{_line(cur)}")
                combos = _combos3(cur)
            else:
                cur = row[:7]
                st.caption(f"{pick} 期 7 个号（含特码）：{_line(cur)}")
                if st.checkbox("替换其中一位后再组合", value=False, key="cb_rep2"):
                    r1, r2 = st.columns(2)
                    with r1:
                        pos = st.selectbox("替换第几球", [1, 2, 3, 4, 5, 6, 7],
                                           index=0, key="cb_pos2") - 1
                    with r2:
                        newnum = st.number_input("替换成", 1, 49, 7, 1, key="cb_num2")
                    cur = list(cur)
                    cur[pos] = int(newnum)
                    st.caption(f"替换后：{_line(cur)}")
                combos = _combos_from(cur, clean=True)

    if not combos:
        st.warning("请输入 3 个数字")
        return

    if st.button("▶ 开始分析", type="primary", key="cb_run"):
        st.session_state["cb_go"] = True

    if not st.session_state.get("cb_go"):
        st.info("点「开始分析」")
        return

    # ---------- 单组：完整报告 ----------
    if len(combos) == 1:
        cmb = combos[0]
        r = analyze_combo(data, cmb)
        st.markdown(f"### 二、★3数字「{','.join(f'{x:02d}' for x in cmb)}」"
                    f" 同行触发 → 上一期7对联动分析★")
        _uniq = {tuple(pn) for _, _, _, pn in r['detail']}
        st.markdown(f"条件：同一行 7 对中同时出现 "
                    f"{'、'.join(f'{x:02d}' for x in cmb)}　｜　共找到 "
                    f"**{len(r['triggers'])}** 处　｜　导入行数 "
                    f"**{len(_uniq)}**")
        if not r["triggers"]:
            st.warning("无匹配")
            return
        lines = ["【一、触发明细】"]
        for tp, tn, pp, pn in r["detail"][:60]:
            lines.append(f"触发行 {tp}：{_line(tn)}")
            lines.append(f"　↓ 上期行 {pp}：{_line(pn)}")
        lines.append("")
        lines.append("【二、上一期7对联动数字综合频次统计】")
        for num, cnt in r["counter"].most_common(10):
            lines.append(f"　{num:02d}　出现 {cnt} 次")
        txt = "\n".join(lines)
        st.code(txt, language=None)
        st.download_button("📥 下载报告", txt.encode("utf-8-sig"),
                           file_name=f"组合联动_{'-'.join(map(str,cmb))}.txt",
                           mime="text/plain", key="cb_dl1")
        return

    # ---------- 批量 ----------
    st.markdown(f"### 二、{len(combos)} 组批量分析")
    rows_t = []
    all_counter = Counter()
    detail_map = {}
    for idx, cmb in enumerate(combos, 1):
        r = analyze_combo(data, cmb)
        detail_map[idx] = r
        for k, v in r["counter"].items():
            all_counter[k] += v
        top = "、".join(f"{n:02d}({c})" for n, c in r["counter"].most_common(10))
        rows_t.append({
            "序": idx,
            "组合": ",".join(f"{n:02d}" for n in cmb),
            "触发处数": len(r["triggers"]),
            "综合数字前10（次数）": top or "—",
        })
    st.dataframe(pd.DataFrame(rows_t), use_container_width=True, hide_index=True)

    _all_uniq = set()
    for idx, r in detail_map.items():
        for _tp, _tn, _pp, _pn in r["detail"]:
            _all_uniq.add(tuple(_pn))
    st.markdown(f"### 三、{len(combos)} 组总汇总　"
                f"（总共触发 **{len(_all_uniq)}** 期）")
    rows_s = [{"号码": f"{n:02d}", "累计次数": c}
              for n, c in all_counter.most_common(10)]
    st.dataframe(pd.DataFrame(rows_s), use_container_width=True, hide_index=True)

    _n_uniq = len({tuple(pn) for r0 in detail_map.values()
                  for _, _, _, pn in r0["detail"]})
    txt = [f"========== 组合联动 批量（{len(combos)} 组）==========",
           f"总共触发 {_n_uniq} 期",
           f"号码：{' '.join(f'{n:02d}' for n in combos and combos[0])} 等", ""]
    for idx, cmb in enumerate(combos, 1):
        r = detail_map[idx]
        txt.append(f"{idx:>2}. 组合 {','.join(f'{n:02d}' for n in cmb)}"
                   f"　触发 {len(r['triggers'])} 处")
        for n, c in r["counter"].most_common(10):
            txt.append(f"　　　{n:02d} × {c}")
        txt.append("")
    txt.append("【总汇总】")
    for n, c in all_counter.most_common(10):
        txt.append(f"　{n:02d} 累计 {c} 次")
    s = "\n".join(txt)
    st.code(s, language=None)
    st.download_button("📥 下载全部", s.encode("utf-8-sig"),
                       file_name="组合联动_批量.txt", mime="text/plain", key="cb_dl2")

    # ---------- 四、中奖结果核对 ----------
    st.markdown("### 四、中奖结果核对")
    st.caption("取汇总前 7 个数字作参照，比对某一期的 6 个平码与特码（同 Excel「中奖结果」）。")
    _top7 = [n for n, _ in all_counter.most_common(7)]
    _c1, _c2 = st.columns([2, 2])
    with _c1:
        _chk = st.selectbox("核对哪一期", per_list, index=0, key="cb_chk")
    with _c2:
        st.write(f"参照（前7）：{' '.join(f'{n:02d}' for n in _top7)}")

    _row = dict(data).get(_chk)
    if _row:
        _flat = [v for v in _row[:6] if v]
        _special = _row[6] if len(_row) > 6 else 0
        _hits = sorted({v for v in _flat if v in _top7})
        _z = bool(_special and _special in _top7)
        _lines = [f"核对期号：{_chk}",
                  f"该期平码：{' '.join(f'{v:02d}' for v in _flat)}"
                  f"　特码：{_special:02d}",
                  f"参照数字：{' '.join(f'{n:02d}' for n in _top7)}", ""]
        if not _hits and not _z:
            _lines.append("本期无中任何数字")
        else:
            if _hits:
                _lines.append(f"平码命中 {len(_hits)} 个："
                              + " ".join(f"{v:02d}" for v in _hits))
            if _z:
                _lines.append(f"特码命中：{_special:02d}")
        st.code("\n".join(_lines), language=None)
