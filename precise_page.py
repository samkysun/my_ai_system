# -*- coding: utf-8 -*-
"""独立页面：精准选号（数字合融合）"""
import streamlit as st

import lab_page


def render(df_data, loader):
    st.markdown("## 🎯 精准选号（数字合融合）")
    st.caption("独立页：先看各球位有效性结论，再选球位与号码个数，"
               "给出建议号码并回测真实命中率。")
    lab_page._exp_precise(loader)
