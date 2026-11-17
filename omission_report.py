# -*- coding: utf-8 -*-
"""
遗漏核算 —— 属性遗漏文本报告生成器
=====================================
职责：
  1. 根据当前属性给出“写入前N”的 +/- 数字框（范围随属性变化）
  2. 把一次性计算结果的前 N 名追加进文本报告（去重、不重复写入）
  3. 提供打印 / 保存 TXT / 清空
  4. 切换球号时自动清空

调用方式（在 omission_page.py 计算完成后）：
    from omission_report import render_omission_report
    render_omission_report(
        period="2026121",
        file_type="升序全套",
        ball_label="第1球",
        attr_name="生肖",
        ranked=[("鼠", 29), ("马", 28), ...],   # 已按次数降序排好
    )
"""

import base64
import html

import streamlit as st

# 属性 -> 可选上限（1..N）
ATTR_LIMITS = {
    "生肖": 12,
    "尾数": 10,
    "数字五行": 5,
    "生肖五行": 5,
    "尾五行": 5,
    "波色": 3,
    "波单双": 6,
    "门数": 5,
    "段数": 7,
    "数字合": 13,
    "单双组合": 4,
    "单双": 2,
    "单双笔": 2,
    "独合字": 2,
    "单双头": 2,
    "阴阳": 2,
    "家野": 2,
    "天地": 2,
    "阴阳天地": 4,
    "吉凶": 2,
    "男女": 2,
    "方位": 4,
    "3模": 3,
    "福禄寿": 3,
    "大小肖": 3,
    "颜色肖": 3,
    "四宝": 4,
    "物象": 4,
}

DEFAULT_LIMIT = 5


def _limit_for(attr_name):
    """属性对应的可选上限；未知属性给 12，避免框不可用。"""
    if not attr_name:
        return 12
    if attr_name in ATTR_LIMITS:
        return ATTR_LIMITS[attr_name]
    for key, val in ATTR_LIMITS.items():
        if key in attr_name:
            return val
    return 12


def _state_key(ball_label, attr_name):
    return f"omission_pick_{ball_label}_{attr_name}"


def _report_key(ball_label):
    return f"omission_report_{ball_label}"


def _clear_if_ball_changed(ball_label):
    """切换球号时清空报告与所有前N选择。"""
    last = st.session_state.get("omission_last_ball")
    if last != ball_label:
        st.session_state["omission_last_ball"] = ball_label
        for k in list(st.session_state.keys()):
            if k.startswith("omission_report_") or k.startswith("omission_pick_"):
                st.session_state.pop(k, None)


def _append_block(ball_label, header, lines):
    """把一段报告追加进当前球号的报告文本，已存在则跳过（去重）。"""
    key = _report_key(ball_label)
    current = st.session_state.get(key, "")
    block = header + "\n" + "\n".join(lines)
    if block in current:
        return False
    if current and not current.endswith("\n"):
        current += "\n"
    st.session_state[key] = current + block + "\n"
    return True


def render_omission_report(period, file_type, ball_label, attr_name, ranked):
    """
    period     : 期数，如 "2026121"
    file_type  : "升序全套" / "按序全套"
    ball_label : "第1球" ... "第7球"
    attr_name  : 属性名，如 "生肖"
    ranked     : [(标签, 次数), ...] 已按次数降序
    """
    if not attr_name or not ranked:
        return

    _clear_if_ball_changed(ball_label)

    limit = _limit_for(attr_name)
    skey = _state_key(ball_label, attr_name)
    if skey not in st.session_state:
        st.session_state[skey] = min(DEFAULT_LIMIT, limit)
    if st.session_state[skey] > limit:
        st.session_state[skey] = limit

    st.markdown("#### 写入前 N 名")
    st.number_input(
        f"{attr_name} 写入前几（1-{limit}）",
        min_value=1,
        max_value=limit,
        step=1,
        key=skey,
    )

    pick = int(st.session_state[skey])
    top = ranked[:pick]

    header = f"===================={period}期{file_type}，{ball_label}{attr_name}遗漏============="
    lines = []
    for label, cnt in top:
        text = str(label)
        if attr_name == "尾数" and not text.endswith("尾"):
            text = f"{text}尾"
        lines.append(f"{text}：{cnt}次")

    if st.button(f"➕ 写入{attr_name}前{pick}名", key=f"omission_write_{ball_label}_{attr_name}", use_container_width=True):
        if _append_block(ball_label, header, lines):
            st.success(f"已写入 {attr_name} 前 {pick} 名")
        else:
            st.info("该段内容已存在，未重复写入")

    report = st.session_state.get(_report_key(ball_label), "")
    if not report:
        st.info("暂无报告内容，点击上方按钮写入。")
        return

    st.markdown("#### 遗漏文本报告")
    escaped = html.escape(report).replace("\n", "<br>")
    st.markdown(
        f"<div style='background:#f8f9fa;border:1px solid #e9ecef;border-radius:10px;"
        f"padding:18px;font-family:Consolas,monospace;font-size:20px;line-height:2.0;"
        f"white-space:pre-wrap;word-wrap:break-word;max-height:480px;overflow-y:auto;'>"
        f"{escaped}</div>",
        unsafe_allow_html=True,
    )

    col_print, col_save, col_clear = st.columns(3)
    with col_print:
        b64 = base64.b64encode(
            ("<html><head><meta charset='utf-8'><style>body{font-family:Consolas,monospace;"
             "font-size:16px;line-height:1.9;padding:20px;}pre{white-space:pre-wrap;}"
             "</style></head><body><pre>" + html.escape(report) + "</pre></body></html>").encode("utf-8")
        ).decode("utf-8")
        st.markdown(
            f"<a href='data:text/html;base64,{b64}' target='_blank' "
            f"style='display:block;text-align:center;padding:10px;background:#0284c7;"
            f"color:#fff;border-radius:6px;text-decoration:none;font-weight:bold;'>🖨️ 打印报告</a>",
            unsafe_allow_html=True,
        )
    with col_save:
        st.download_button(
            "📥 保存TXT",
            data=report.encode("utf-8-sig"),
            file_name=f"遗漏_{ball_label}_{period}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"omission_dl_{ball_label}",
        )
    with col_clear:
        if st.button("🗑️ 清空报告", key=f"omission_clear_{ball_label}", use_container_width=True):
            st.session_state[_report_key(ball_label)] = ""
            st.rerun()
