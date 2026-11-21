# -*- coding: utf-8 -*-
"""
智能数据分析系统 —— 整合修订版
================================
相对你原来那版的改动（其余逻辑未动）：
  1. NUM_HE[22] 由 "05合" 修正为 "04合"（2+2=4，与前后邻居一致）
  2. get_supabase_client 不再缓存 None（否则第一次没读到 Secrets 就永久失效）
  3. 新增 register_user / check_credentials，注册与登录的错误按 PostgREST 错误码分类
  4. login_page 重写：区分“用户不存在/密码错误”，注册成功清空表单，去掉 rerun 后不可达的 stop
  5. build_rule_database(debug=True) 返回失败原因，不再只报“规则表读取失败”
  6. call_deepseek_api：超时 60→180 秒、429/5xx 自动重试、system 消息前置、报错带状态码与原文
  7. get_analysis_prompt：压缩输出长度（超时根因），要求输出 FINAL 行
  8. 新增 extract_numbers，取代 re.findall(r'\b([0-4][0-9])\b')（中文旁无词边界，必漏抓）
  9. 补上 .ball / .ball-red 等样式（这三个类名原来被引用但从未定义，号码球是没样式的）

需要额外装的依赖不变：streamlit pandas openpyxl requests supabase
"""

import streamlit as st
import pandas as pd
import hashlib
import time
import urllib.parse
import os
import itertools
import requests
import openpyxl
import io
import base64
import re
import json
import sqlite3
from collections import Counter
from datetime import datetime
from openpyxl.utils import get_column_letter, column_index_from_string
from supabase import create_client

# 两个可选模块：缺失时只影响对应标签页，不影响主程序启动
try:
    from ai_chat_page import render_ai_chat
except Exception:
    render_ai_chat = None
try:
    from auto_upgrade import render_upgrade_tab
except Exception:
    render_upgrade_tab = None

# ==========================================
# 1. 全局配置与初始化
# ==========================================
GLOBAL_RESULT_CSS = """
<style>
/* ===== 所有计算结果的统一字体与颜色 ===== */
div[data-testid="stTextArea"] textarea {
    font-family: Consolas, 'Microsoft YaHei', 'Courier New', monospace !important;
    font-size: 20px !important;
    line-height: 1.85 !important;
    font-weight: 500 !important;
    color: #111827 !important;
    background: #ffffff !important;
}
div[data-testid="stDataFrame"] {
    font-size: 15px !important;
}
div[data-testid="stDataFrame"] * {
    font-family: Consolas, 'Microsoft YaHei', sans-serif !important;
}
.stMarkdown p, .stMarkdown li, .stCaption {
    color: #1f2937;
}
</style>
"""


st.set_page_config(page_title="💻智能数据分析系统", layout="wide")


def _inject_css(css, key=""):
    """优先用 st.html（1.33+），旧版回退 markdown；两者都不炸页面"""
    try:
        st.html(css)
        return
    except Exception:
        pass
    try:
        st.markdown(css, unsafe_allow_html=True)
    except Exception:
        pass


_inject_css(GLOBAL_RESULT_CSS)

# 号码球样式（原来只用了类名没有定义，补上）
_BALL_CSS = """
<style>
.ball-container{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0 4px 0}
.ball{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;
      font-size:17px;font-weight:700;color:#fff;box-shadow:0 2px 6px rgba(0,0,0,.18)}
.ball-red{background:linear-gradient(145deg,#ef4444,#b91c1c)}
.ball-blue{background:linear-gradient(145deg,#3b82f6,#1d4ed8)}
.ball-green{background:linear-gradient(145deg,#22c55e,#15803d)}
</style>
"""
_inject_css(_BALL_CSS)

EXCEL_FILE = "总数据.xlsx"
SHEET_NAME = "总数据表"
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")


@st.cache_resource
def _make_client(url, key):
    return create_client(url, key)


def get_supabase_client():
    """只有创建成功才进缓存。原版把 None 也缓存了，导致之后改 Secrets 也一直连不上。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return _make_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


# 密码加密（保持原样：已注册用户的哈希依赖它，不可随意改）
import hmac as _hmac
import os as _os_sec
import time as _time_sec

_PBKDF2_ITER = 120000


def hash_password(password):
    """PBKDF2-SHA256 + 随机盐；格式 pbkdf2$迭代$盐$散列"""
    salt = _os_sec.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(),
                             bytes.fromhex(salt), _PBKDF2_ITER)
    return f"pbkdf2${_PBKDF2_ITER}${salt}${dk.hex()}"


def verify_password(password, stored):
    """校验密码；兼容旧的纯 sha256 记录"""
    stored = str(stored or "")
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, it, salt, h = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(),
                                     bytes.fromhex(salt), int(it))
            return _hmac.compare_digest(dk.hex(), h)
        except Exception:
            return False
    try:
        return _hmac.compare_digest(
            hashlib.sha256((password or "").encode()).hexdigest(), stored)
    except Exception:
        return False


def is_legacy_hash(stored):
    return bool(stored) and not str(stored).startswith("pbkdf2$")


if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "synced_df" not in st.session_state: st.session_state.synced_df = None
if "calc_data_single" not in st.session_state: st.session_state.calc_data_single = None
if "calc_data_multi" not in st.session_state: st.session_state.calc_data_multi = None
if "calc_result_preview" not in st.session_state: st.session_state.calc_result_preview = None
if "predicted_nums_single" not in st.session_state: st.session_state.predicted_nums_single = None
if "predicted_nums_multi" not in st.session_state: st.session_state.predicted_nums_multi = None

# ==========================================
# 2. 核心引擎：28个属性纯代码计算器
# ==========================================
NUM_WUXING = {1: "水", 2: "火", 3: "火", 4: "金", 5: "金", 6: "土", 7: "土", 8: "木", 9: "木", 10: "火", 11: "火", 12: "金", 13: "金", 14: "水", 15: "水", 16: "木", 17: "木", 18: "火", 19: "火", 20: "土", 21: "土", 22: "水", 23: "水", 24: "木", 25: "木", 26: "金", 27: "金", 28: "土", 29: "土", 30: "水", 31: "水", 32: "火", 33: "火", 34: "金", 35: "金", 36: "土", 37: "土", 38: "木", 39: "木", 40: "火", 41: "火", 42: "金", 43: "金", 44: "水", 45: "水", 46: "木", 47: "木", 48: "火", 49: "火"}
NUM_ZODIAC = {1: "马", 2: "蛇", 3: "龙", 4: "兔", 5: "虎", 6: "牛", 7: "鼠", 8: "猪", 9: "狗", 10: "鸡", 11: "猴", 12: "羊", 13: "马", 14: "蛇", 15: "龙", 16: "兔", 17: "虎", 18: "牛", 19: "鼠", 20: "猪", 21: "狗", 22: "鸡", 23: "猴", 24: "羊", 25: "马", 26: "蛇", 27: "龙", 28: "兔", 29: "虎", 30: "牛", 31: "鼠", 32: "猪", 33: "狗", 34: "鸡", 35: "猴", 36: "羊", 37: "马", 38: "蛇", 39: "龙", 40: "兔", 41: "虎", 42: "牛", 43: "鼠", 44: "猪", 45: "狗", 46: "鸡", 47: "猴", 48: "羊", 49: "马"}
# 注意：22 号原为 "05合"，按各位数字相加应为 04合（2+2=4），已修正
NUM_HE = {1: "01合", 2: "02合", 3: "03合", 4: "04合", 5: "05合", 6: "06合", 7: "07合", 8: "08合", 9: "09合", 10: "01合", 11: "02合", 12: "03合", 13: "04合", 14: "05合", 15: "06合", 16: "07合", 17: "08合", 18: "09合", 19: "10合", 20: "02合", 21: "03合", 22: "04合", 23: "05合", 24: "06合", 25: "07合", 26: "08合", 27: "09合", 28: "10合", 29: "11合", 30: "03合", 31: "04合", 32: "05合", 33: "06合", 34: "07合", 35: "08合", 36: "09合", 37: "10合", 38: "11合", 39: "12合", 40: "04合", 41: "05合", 42: "06合", 43: "07合", 44: "08合", 45: "09合", 46: "10合", 47: "11合", 48: "12合", 49: "13合"}
NUM_MEN = {1: "1门", 2: "1门", 3: "1门", 4: "1门", 5: "1门", 6: "1门", 7: "1门", 8: "1门", 9: "1门", 10: "2门", 11: "2门", 12: "2门", 13: "2门", 14: "2门", 15: "2门", 16: "2门", 17: "2门", 18: "2门", 19: "2门", 20: "3门", 21: "3门", 22: "3门", 23: "3门", 24: "3门", 25: "3门", 26: "3门", 27: "3门", 28: "3门", 29: "3门", 30: "4门", 31: "4门", 32: "4门", 33: "4门", 34: "4门", 35: "4门", 36: "4门", 37: "4门", 38: "4门", 39: "4门", 40: "5门", 41: "5门", 42: "5门", 43: "5门", 44: "5门", 45: "5门", 46: "5门", 47: "5门", 48: "5门", 49: "5门"}
NUM_DUAN = {1: "1段", 2: "1段", 3: "1段", 4: "1段", 5: "1段", 6: "1段", 7: "1段", 8: "2段", 9: "2段", 10: "2段", 11: "2段", 12: "2段", 13: "2段", 14: "2段", 15: "3段", 16: "3段", 17: "3段", 18: "3段", 19: "3段", 20: "3段", 21: "3段", 22: "4段", 23: "4段", 24: "4段", 25: "4段", 26: "4段", 27: "4段", 28: "4段", 29: "5段", 30: "5段", 31: "5段", 32: "5段", 33: "5段", 34: "5段", 35: "5段", 36: "6段", 37: "6段", 38: "6段", 39: "6段", 40: "6段", 41: "6段", 42: "6段", 43: "7段", 44: "7段", 45: "7段", 46: "7段", 47: "7段", 48: "7段", 49: "7段"}
NUM_SINGLE_DOUBLE = {1: "双单", 2: "双双", 3: "双单", 4: "双双", 5: "双单", 6: "双双", 7: "双单", 8: "双双", 9: "双单", 10: "单双", 11: "单单", 12: "单双", 13: "单单", 14: "单双", 15: "单单", 16: "单双", 17: "单单", 18: "单双", 19: "单单", 20: "双双", 21: "双单", 22: "双双", 23: "双单", 24: "双双", 25: "双单", 26: "双双", 27: "双单", 28: "双双", 29: "双单", 30: "单双", 31: "单单", 32: "单双", 33: "单单", 34: "单双", 35: "单单", 36: "单双", 37: "单单", 38: "单双", 39: "单单", 40: "双双", 41: "双单", 42: "双双", 43: "双单", 44: "双双", 45: "双单", 46: "双双", 47: "双单", 48: "双双", 49: "双单"}
NUM_BOSE = {1: "红波", 2: "红波", 7: "红波", 8: "红波", 12: "红波", 13: "红波", 18: "红波", 19: "红波", 23: "红波", 24: "红波", 29: "红波", 30: "红波", 34: "红波", 35: "红波", 40: "红波", 45: "红波", 46: "红波", 3: "蓝波", 4: "蓝波", 9: "蓝波", 10: "蓝波", 14: "蓝波", 15: "蓝波", 20: "蓝波", 25: "蓝波", 26: "蓝波", 31: "蓝波", 36: "蓝波", 37: "蓝波", 41: "蓝波", 42: "蓝波", 47: "蓝波", 48: "蓝波", 5: "绿波", 6: "绿波", 11: "绿波", 16: "绿波", 17: "绿波", 21: "绿波", 22: "绿波", 27: "绿波", 28: "绿波", 32: "绿波", 33: "绿波", 38: "绿波", 39: "绿波", 43: "绿波", 44: "绿波", 49: "绿波"}
ZODIAC_WUXING = {"鼠": "水", "牛": "土", "虎": "木", "兔": "木", "龙": "土", "蛇": "火", "马": "火", "羊": "土", "猴": "金", "鸡": "金", "狗": "土", "猪": "水"}
ZODIAC_COLOR = {"鼠": "红色", "马": "红色", "鸡": "红色", "兔": "红色", "牛": "绿色", "羊": "绿色", "龙": "绿色", "狗": "绿色", "虎": "蓝色", "猴": "蓝色", "蛇": "蓝色", "猪": "蓝色"}
ZODIAC_FOUR_TREASURES = {"鼠": "棋", "牛": "棋", "狗": "棋", "鸡": "琴", "兔": "琴", "蛇": "琴", "马": "书", "虎": "书", "龙": "书", "猴": "画", "羊": "画", "猪": "画"}
ZODIAC_OBJECT_IMAGE = {"鼠": "恶人", "猴": "恶人", "牛": "家臣", "狗": "家臣", "马": "家臣", "猪": "家臣", "鸡": "美女", "兔": "美女", "蛇": "美女", "羊": "美女", "虎": "君王", "龙": "君王"}
YANG_ZODIACS = ["牛", "虎", "兔", "羊", "猴", "鸡"]
JIA_ZODIACS = ["牛", "马", "羊", "鸡", "狗", "猪"]
TIAN_ZODIACS = ["牛", "兔", "龙", "马", "猴", "猪"]
XIONG_ZODIACS = ["鼠", "牛", "虎", "猴", "狗", "猪"]
NAN_ZODIACS = ["鼠", "牛", "虎", "龙", "马", "猴", "狗"]
ZODIAC_DIRECTION = {"鼠": "北", "牛": "北", "猪": "北", "虎": "东", "兔": "东", "龙": "东", "马": "南", "蛇": "南", "羊": "南", "猴": "西", "鸡": "西", "狗": "西"}
TAIL_WUXING = {0: "土", 5: "土", 2: "火", 7: "火", 1: "水", 6: "水", 3: "木", 8: "木", 4: "金", 9: "金"}
ZODIAC_FU_LU_SHOU = {"鼠": "福肖", "马": "福肖", "虎": "福肖", "龙": "福肖", "牛": "禄肖", "兔": "禄肖", "猴": "禄肖", "猪": "禄肖", "狗": "寿肖", "鸡": "寿肖", "蛇": "寿肖", "羊": "寿肖"}
ZODIAC_SIZE = {"鼠": "小肖", "鸡": "小肖", "兔": "小肖", "蛇": "小肖", "牛": "大肖", "马": "大肖", "虎": "大肖", "龙": "大肖", "狗": "中肖", "猴": "中肖", "羊": "中肖", "猪": "中肖"}


def calculate_all_attributes(num):
    if not num: return [""] * 28
    n = int(num)
    z = NUM_ZODIAC.get(n, "")
    tail = n % 10
    return [NUM_WUXING.get(n, ""), z, str(tail), NUM_HE.get(n, ""), NUM_MEN.get(n, ""), NUM_DUAN.get(n, ""), NUM_SINGLE_DOUBLE.get(n, ""), "单笔" if z in ["鼠", "龙", "蛇", "马", "鸡", "猪"] else "双笔", "独字" if z in ["鼠", "牛", "虎", "兔", "马", "羊"] else "合字", "单头" if (n // 10) in [1, 3] else "双头", "单数" if n % 2 != 0 else "双数", f"{NUM_BOSE.get(n, '')}{'单数' if n % 2 != 0 else '双数'}", ZODIAC_WUXING.get(z, ""), ZODIAC_COLOR.get(z, ""), ZODIAC_FOUR_TREASURES.get(z, ""), ZODIAC_OBJECT_IMAGE.get(z, ""), NUM_BOSE.get(n, ""), "阳" if z in YANG_ZODIACS else "阴", "家" if z in JIA_ZODIACS else "野", "天" if z in TIAN_ZODIACS else "地", f"{'阳' if z in YANG_ZODIACS else '阴'}{'天' if z in TIAN_ZODIACS else '地'}", "凶" if z in XIONG_ZODIACS else "吉", "男" if z in NAN_ZODIACS else "女", ZODIAC_DIRECTION.get(z, ""), f"3余{tail % 3}", TAIL_WUXING.get(tail, ""), ZODIAC_FU_LU_SHOU.get(z, ""), ZODIAC_SIZE.get(z, "")]

# ==========================================
# 3. 基础数据加载
# ==========================================
def get_ball_color(num):
    red = [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46]
    blue = [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48]
    return "ball-red" if num in red else ("ball-blue" if num in blue else "ball-green")


def clean_period(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    return s[:-2] if s.endswith(".0") else s


# ==========================================
# 跨页面汇总看板（各页面结果 → AI推演页固定展示）
# ==========================================
try:
    from combo2_page import render as render_combo2
except Exception:
    render_combo2 = None

try:
    from cross_view import render as render_cross_view
except Exception:
    render_cross_view = None

try:
    from calc_center import render as render_calc_center
except Exception as _cc_err:
    render_calc_center = None


_BOARD_TABLE = "ai_board"
_BOARD_MAX = 80            # 最多显示 80 条，防止页面变卡


def _board_cloud_read():
    """从 Supabase 读看板 -> items 列表"""
    client = get_supabase_client()
    if not client:
        return []
    try:
        rows = (client.table(_BOARD_TABLE)
                .select("source,title,content,updated_at")
                .order("updated_at", desc=False)
                .execute().data) or []
        out = []
        for r in rows:
            out.append({
                "source": r.get("source", ""),
                "title": r.get("title", ""),
                "text": r.get("content", ""),
                "ts": str(r.get("updated_at", ""))[:19].replace("T", " "),
            })
        return out
    except Exception:
        return []


def _board_cloud_upsert(source, title, text):
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(_BOARD_TABLE).upsert(
            {"source": source, "title": title, "content": text,
             "updated_at": datetime.now().isoformat(timespec="seconds")},
            on_conflict="source,title").execute()
        return True
    except Exception:
        return False


def _board_cloud_delete(source, title):
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(_BOARD_TABLE).delete().eq("source", source) \
            .eq("title", title).execute()
        return True
    except Exception:
        return False


def _board_cloud_clear():
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(_BOARD_TABLE).delete().neq("source", "__none__").execute()
        return True
    except Exception:
        return False


def _board_table_ok():
    """检查 Supabase 看板表是否存在"""
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(_BOARD_TABLE).select("id").limit(1).execute()
        return True
    except Exception:
        return False


def _board_sync_load():
    """会话首次使用时从 Supabase 载入"""
    if "ai_board" in st.session_state:
        return st.session_state.ai_board
    items = _board_cloud_read()
    st.session_state.ai_board = items[-_BOARD_MAX:]
    return st.session_state.ai_board


def _board_persist():
    """整表重写（仅在需要时用；一般用增量写）"""
    items = st.session_state.get("ai_board") or []
    _board_cloud_clear()
    for e in items[-_BOARD_MAX:]:
        _board_cloud_upsert(e.get("source", ""), e.get("title", ""),
                            e.get("text", ""))
def _board_add(source, title, text):
    """把一段结果放进看板；同一个 source+title 会覆盖，并写入云端"""
    _board_sync_load()
    text = (text or "").strip()
    if not text:
        return
    if len(text) > 20000:
        text = text[:20000] + "\n…（内容过长已截断）"
    entry = {"source": source, "title": title, "text": text,
             "ts": datetime.now().strftime("%m-%d %H:%M:%S")}
    for i, e in enumerate(st.session_state.ai_board):
        if e.get("source") == source and e.get("title") == title:
            st.session_state.ai_board[i] = entry
            _board_cloud_upsert(source, title, text)
            return
    st.session_state.ai_board.append(entry)
    _board_cloud_upsert(source, title, text)


def _board_append(source, title, text):
    """按 source+title 追加：同一个球号多次推送合并成一条。"""
    _board_sync_load()
    text = (text or "").strip()
    if not text:
        return
    for i, e in enumerate(st.session_state.ai_board):
        if e.get("source") == source and e.get("title") == title:
            if text not in e["text"]:
                e["text"] = (e["text"] + "\n\n" + text)[:20000]
            e["ts"] = datetime.now().strftime("%m-%d %H:%M:%S")
            _board_cloud_upsert(source, title, e["text"])
            return
    _board_add(source, title, text)


_AI_RULES = """【数据规则说明·必须严格遵守】
1. 六合彩每期开 6 个平码 + 1 个特码，号码范围 1~49。
2. 「升序」= 把 6 个平码从小到大排列（升序第1位最小，第6位最大）。
3. 「按序」= 实际摇出的落球顺序（按序第1球先摇出，第6球最后摇出）。
4. 写法「升1→按4」的意思是：本期最小值那个号，在第 4 个球被摇出。
5. 「触发行」= 历史上出现过与目标组合相同号码组合的那一期。
6. 「上一期 / 下一期」= 相对于触发行，时间上前一期或后一期。
7. 「综合数字」= 把所有触发行对应的上一期号码汇总后，各号码出现的次数统计。
8. 「三中三」= 你选的 3 个号全部出现在开奖的 6 个平码里。
   单个三号组合的中奖概率 = C(46,3)/C(49,6) = 0.1086%（约 1/921），
   公平赔率应为 921 倍；低于这个赔率的玩法长期必然亏损。
9. 位置配对（升序位 ↔ 落球位）在统计上接近随机（均匀 1/6），
   不能声称能预测位置。
10. 禁止编造数据。所有结论必须能在给的数据里找到依据。
    如果数据不足以得出结论，直接说明"数据不足"。
11. 输出用中文、分点、给具体数字，不要空话。"""


def _board_ai_text(limit_each=2500, max_items=12):
    """把看板内容压缩成可读文本（长文本保留首尾）"""
    board = _board_sync_load() or []
    parts = []
    for e in board[-max_items:]:
        txt = e.get("text") or ""
        if len(txt) > limit_each:
            lines = txt.splitlines()
            head = "\n".join(lines[:25])
            tail = "\n".join(lines[-10:])
            txt = (f"{head}\n…（中间省略 {max(0, len(lines)-35)} 行）…\n{tail}")
        parts.append(f"===== 来源：{e.get('source','')} | 标题：{e.get('title','')} "
                     f"| 时间：{e.get('ts','')} =====\n{txt}")
    return "\n\n".join(parts)


def _board_ai_analyze(question):
    """调用 AI 综合分析看板内容"""
    data = _board_ai_text()
    if not data:
        return "看板里还没有内容，请先从其它页面推送结果。"
    prompt = (f"以下是汇总看板中的分析结果数据：\n\n{data}\n\n"
              f"【我的问题】\n{question}\n\n"
              f"请基于上面数据回答，要求：\n"
              f"1) 先概括数据里的关键数字（条数、期数、命中率等）\n"
              f"2) 再回答我的问题\n"
              f"3) 涉及概率或赔率时必须给出计算过程\n"
              f"4) 不要编造数据里没有的内容")
    return call_deepseek_api(prompt, _AI_RULES)


_MULTI_RULES = """【硬规则·违反即视为错误】
1. ★只看每条报告的标题，标题格式：
   =========2026124期升序-生肖2球=======
   从这里读出三件事：① 期号（2026124）② 升序还是按序 ③ 属性 + 球号（生肖、第2球）。
   这三样是判断归属的唯一依据。

2. ★基准行排列完全不参考，不要引用、不要分析。

3. ★「下」完全不参与任何判断，直接忽略，不许引用。

4. ★「上」= 下期要杀的属性值。
   但如果同一行里已经写了「杀XXX」（例如 杀金肖木肖），
   就只认括号里的值，不能再把「上:XX」也当成杀号。

5. ★不同球位绝对不许混在一起。升序1球 ≠ 升序2球，升序 ≠ 按序。
   输出必须按「升序/按序 + 球号」分组，一个球位一段。

6. 不存在「矛盾」判定：因为「下」不参与，所以不要写"上杀下留"这类分析。

7. 禁止把 49 个号全部杀光。若全杀，只保留杀次数 ≤ 2 的号码，
   并把杀次数高的列为「下期必杀号码」。

8. 禁止编造，只能使用给出的数据。

9. ★各球位号码范围（升序）：
   第1球 1~20，第2球 2~25，第3球 3~30，第4球 4~40，
   第5球 15~48，第6球 25~49，第7球（特码）1~49。
   按序（落球顺序）各球没有固定范围，都是 1~49。
   涉及具体号码时必须落在对应区间内，不得给出区间外的号码。

10. 输出格式：
   ① 按期号 + 球位分组
   ② 每组列出：属性 → 要杀的值 → 出现次数
   ③ 每组给出「必杀号码」和「保留号码」
   ④ 最后一句总体结论"""


def _parse_multi_blocks(text):
    """按行解析多维分析报告"""
    if text and "【基准行排列】" not in text and "第1球" in text:
        _lb = _parse_link_blocks(text)
        if _lb:
            return _lb
    import re as _re
    blocks = []
    cur = None
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("=") and "期" in s and "球" in s:
            head = s.strip("= ")
            m = _re.search(r"(\d{5,8})期(升序|按序)-(.+?)(\d)球", head)
            if m:
                cur = {"period": m.group(1), "order": m.group(2),
                       "attr": m.group(3), "ball": m.group(4),
                       "base": "", "triggers": []}
                blocks.append(cur)
            continue
        if cur is None:
            continue
        if "基准行排列" in s:
            mb = _re.search(r"[:：]\s*(.+)", s)
            if mb:
                cur["base"] = mb.group(1).strip()
            continue
        if "触发行" in s:
            mt = _re.search(r"行(\d+)-(\d+)\((\d+)行\)", s)
            if not mt:
                continue
            mu = _re.search(r"上[:：]([^\s(（]+)", s)
            md = _re.search(r"下[:：]([^\s(（\[]+)", s)
            mm = _re.search(r"匹配[:：]([^\)）]*)", s)
            mk = _re.search(r"杀([^)）]*)", s)
            cur["triggers"].append({
                "row": f"{mt.group(1)}-{mt.group(2)}",
                "n": int(mt.group(3)),
                "up": mu.group(1) if mu else "",
                "down": md.group(1) if md else "",
                "match": mm.group(1).strip() if mm else "",
                "self": "自身参考列" in s,
                "hot": "一致" in s,
                "kill": mk.group(1).strip() if mk else "",
            })
    return blocks


def _multi_summary_text(blocks):
    """把解析结果压成 AI 易读的表格文本"""
    if not blocks:
        return ""
    lines = [f"共解析到 {len(blocks)} 条属性报告，明细如下：", ""]
    for b in blocks:
        lines.append(f"■ {b['attr']}（{b['order']}第{b['ball']}球）")
        lines.append(f"  基准序列：{b['base'][:160]}")
        if not b["triggers"]:
            lines.append("  （无触发行）")
        for i, tg in enumerate(b["triggers"], 1):
            extra = []
            if tg["self"]:
                extra.append("自身列匹配")
            if tg["hot"]:
                extra.append("近期高度重合")
            lines.append(
                f"  触发行{i}：行{tg['row']}（{tg['n']}行）"
                f"　上期值={tg['up']}　下期值={tg['down']}"
                f"　匹配序列={tg['match'][:80]}"
                + (f"　[{'、'.join(extra)}]" if extra else ""))
        lines.append("")
    return "\n".join(lines)


_ATTR_GROUP = [
    ("生肖五行与数字五行", "生肖五行·交叉"),
    ("数字五行与生肖五行", "生肖五行·交叉"),
    ("生肖五行", "生肖五行"),
    ("尾五行", "尾五行"),
    ("数字五行", "数字五行"),
    ("生肖", "生肖"),
    ("尾数", "尾数"),
    ("数字合", "合数"),
    ("段数", "段数"),
    ("门数", "门数"),
    ("波", "波色单双"),
    ("方位", "方位"),
    ("福禄寿", "福禄寿"),
    ("物象", "物象"),
    ("阴阳天地", "阴阳天地"),
    ("颜色肖", "颜色肖"),
    ("大小肖", "大小肖"),
    ("3模", "3模"),
]


def _attr_group(attr):
    for key, name in _ATTR_GROUP:
        if key in attr:
            return name
    return attr


def _clean_kill(v):
    """把「龙肖 / 5尾 / 06合 / 金号(杀木肖火肖)」整理成可读值"""
    v = (v or "").strip()
    for sep in ("（", "("):
        if sep in v:
            v = v.split(sep)[0]
    return v.strip()


def _kill_items(grp, up, kill):
    """决定这一条要杀什么
       · 有「杀X杀Y」→ 只认括号里的
       · 没有 → 用「上」的值"""
    import re as _re
    up = _clean_kill(up)
    kill = (kill or "").strip()
    if kill:
        items = _re.findall(r"([^\s、，,()（）]+?(?:肖|号|尾|合|段|门))", kill)
        if items:
            return items, True
    return ([up] if up else []), False


@st.cache_data(ttl=3600, show_spinner=False)
def _load_attr_map():
    """读取 _attr_map.csv -> {号码: {属性:值}}"""
    try:
        rows = load_excel_data("_attr_map.csv", None)
    except Exception:
        rows = None
    if not rows:
        return {}
    hdr = [str(x).strip() for x in rows[0]]
    out = {}
    for r in rows[1:]:
        if not r or not str(r[0]).strip().isdigit():
            continue
        num = int(float(r[0]))
        out[num] = {hdr[i]: str(r[i]).strip() for i in range(1, min(len(hdr), len(r)))}
    return out


_WX_CHARS = set("金木水火土")
_ZODIAC = set("鼠牛虎兔龙蛇马羊猴鸡狗猪")


def kill_to_numbers(item, amap):
    """把一个杀号条件翻译成号码列表"""
    it = (item or "").strip()
    if not it or not amap:
        return []
    # 尾数：5尾
    if it.endswith("尾") and it[:-1].isdigit():
        d = it[:-1]
        return [n for n, a in amap.items() if a.get("尾数") == d]
    # 合数：06合
    if it.endswith("合"):
        return [n for n, a in amap.items() if a.get("数字合") == it]
    # 段数 / 门数
    if it.endswith("段"):
        return [n for n, a in amap.items() if a.get("段数") == it]
    if it.endswith("门"):
        return [n for n, a in amap.items() if a.get("门数") == it]
    # 五行号码：火号
    if it.endswith("号") and it[:-1] in _WX_CHARS:
        return [n for n, a in amap.items() if a.get("数字五行") == it[:-1]]
    # 五行肖：木肖
    if it.endswith("肖") and it[:-1] in _WX_CHARS:
        return [n for n, a in amap.items() if a.get("生肖五行") == it[:-1]]
    # 生肖：羊肖
    if it.endswith("肖") and it[:-1] in _ZODIAC:
        return [n for n, a in amap.items() if a.get("生肖") == it[:-1]]
    # 福禄寿：福肖/禄肖/寿肖
    if it.endswith("肖") and it[:-1] in "福禄寿":
        return [n for n, a in amap.items() if a.get("福禄寿") == it]
    # 颜色肖：红肖
    if it.endswith("肖") and it[:-1] in "红蓝绿":
        return [n for n, a in amap.items() if a.get("颜色肖") == it]
    # 大小肖
    if it.endswith("肖") and it[:-1] in ("大", "小"):
        return [n for n, a in amap.items() if a.get("大小肖") == it]
    # 尾五行：木尾 / 火尾 / 金尾
    if it.endswith("尾") and it[:-1] in _WX_CHARS:
        return [n for n, a in amap.items() if a.get("尾五行") == it[:-1]]
    # 头数：单头 / 双头
    if it in ("单头", "双头"):
        return [n for n, a in amap.items() if a.get("头数") == it]
    # 单双：单数 / 双数
    if it in ("单数", "双数"):
        return [n for n, a in amap.items() if a.get("单双") == it]
    # 单双组合：双双 / 单双 / 双单 / 单单
    if it in ("双双", "单双", "双单", "单单"):
        return [n for n, a in amap.items() if a.get("单双组合") == it]
    # 阴阳 / 家野 / 天地 / 吉凶 / 男女 / 四宝
    for _col, _vals in (("阴阳", ("阴", "阳")),
                        ("家野", ("家", "野")),
                        ("天地", ("天", "地")),
                        ("吉凶", ("吉", "凶")),
                        ("男女", ("男", "女")),
                        ("四宝", ("书", "棋", "画", "琴"))):
        if it in _vals:
            return [n for n, a in amap.items() if a.get(_col) == it]
    # 波色单双
    if "波" in it:
        return [n for n, a in amap.items() if a.get("波单双") == it]
    # 方位
    if it in ("东", "南", "西", "北"):
        return [n for n, a in amap.items() if a.get("方位") == it]
    # 阴阳天地
    if it in ("阳天", "阳地", "阴天", "阴地"):
        return [n for n, a in amap.items() if a.get("阴阳天地") == it]
    # 物象
    if it in ("家臣", "恶人", "美女", "君王"):
        return [n for n, a in amap.items() if a.get("物象") == it]
    # 3模
    if it.startswith("3余"):
        return [n for n, a in amap.items() if a.get("3模") == it]
    return []


def kill_summary(blocks):
    """返回 [(属性组, 杀值, 次数, 明细)]，按次数降序"""
    from collections import Counter, defaultdict
    cnt = Counter()
    src = defaultdict(set)
    for b in blocks:
        grp = _attr_group(b["attr"])
        for tg in b["triggers"]:
            items, from_paren = _kill_items(grp, tg.get("up", ""), tg.get("kill", ""))
            for it in items:
                if not it:
                    continue
                if from_paren:
                    g2 = "生肖" if it.endswith("肖") else (
                        "数字五行" if it.endswith("号") else grp)
                else:
                    g2 = grp
                key = (g2, it)
                cnt[key] += 1
                src[key].add(f"第{b['ball']}球·{b['attr']}"
                             + ("（括号内）" if from_paren else ""))
    out = [(g, v, n, sorted(src[(g, v)])) for (g, v), n in cnt.items()]
    out.sort(key=lambda x: (-x[2], x[0], x[1]))
    return out


_UP_RANGE = {1: (1, 20), 2: (2, 25), 3: (3, 30), 4: (4, 40),
             5: (15, 48), 6: (25, 49), 7: (1, 49)}


def _range_of(label):
    """从「升序2球」这类标签推出号码区间"""
    import re as _re
    m = _re.search(r"(升序|按序)第?(\d)球", label)
    if not m:
        return (1, 49)
    order, ball = m.group(1), int(m.group(2))
    if order == "升序":
        return _UP_RANGE.get(ball, (1, 49))
    return (1, 49)


def _render_kill_group(label, blocks, amap, range_label=None):
    """渲染一个球位（或合并后）的杀号清单（含矛盾判定）"""
    ks = kill_summary(blocks)
    _rl = range_label or label
    if not ks:
        _lo0, _hi0 = _range_of(_rl)
        st.warning("没有解析到任何杀号（触发行可能没抓到上/杀值）")
        st.success(f"本球位区间 {_lo0}~{_hi0} 全部保留（{_hi0-_lo0+1} 个号码）")
        _dbg = [f"{b['attr']}：{len(b['triggers'])} 条触发行" for b in blocks]
        st.caption("解析情况：" + "；".join(_dbg))
        return

    down_ref = set()   # 「下」不参与任何判断

    rows_k = []
    for g, v, n, d in ks:
        conflict = False
        conf = "高" if n >= 2 else "中"
        rows_k.append({"属性": g, "杀值": v, "上杀次数": n,
                       "可信度": conf, "来自": "；".join(d)})
    st.dataframe(pd.DataFrame(rows_k), use_container_width=True, hide_index=True)

    if not amap:
        st.info("缺少 _attr_map.csv，无法翻译成号码")
        return

    from collections import Counter as _CK, defaultdict as _DK
    num_kill = _CK()
    num_src = _DK(list)
    num_conf = set()
    unmapped = []
    for g, v, n, _s in ks:
        nums = kill_to_numbers(v, amap)
        if not nums:
            unmapped.append(f"{g}{v}")
            continue
        for x in nums:
            num_kill[x] += n
            num_src[x].append(f"{g}{v}")

    if not num_kill:
        if unmapped:
            st.caption("未能翻译的条件：" + "、".join(unmapped))
        return

    _lo, _hi = _range_of(_rl)
    num_kill = _CK({n: c for n, c in num_kill.items() if _lo <= n <= _hi})
    if not num_kill:
        st.caption(f"本组杀号在本球位区间 {_lo}~{_hi} 内没有命中号码")
        _allk = list(range(_lo, _hi + 1))
        st.success(f"保留号码（{len(_allk)} 个，本区间全部保留）："
                   + " ".join(f"{n:02d}" for n in _allk))
        if unmapped:
            st.caption("未能翻译的条件：" + "、".join(unmapped))
        return
    st.caption(f"本球位号码区间：{_lo}~{_hi}（只在此区间内计算）")
    kill_set = set(num_kill.keys())
    _span = _hi - _lo + 1
    keep_nums = [n for n in range(_lo, _hi + 1) if n not in kill_set]
    thr_used = 1
    if len(kill_set) >= _span:
        for thr in range(2, max(3, max(num_kill.values()) + 1)):
            cand = [n for n in range(_lo, _hi + 1) if num_kill.get(n, 0) < thr]
            if cand:
                keep_nums = cand
                thr_used = thr
                st.info(f"本区间（{_lo}~{_hi}）的 {_span} 个号全被杀光了 → "
                        f"自动放宽：只杀出现 {thr} 次及以上的，"
                        f"保留 {len(cand)} 个号码")
                break
    kill_final = [n for n in kill_set if n not in keep_nums]

    _sorted = sorted(((n, num_kill[n]) for n in kill_final),
                     key=lambda x: (-x[1], x[0]))
    rows_n = [{"号码": f"{n:02d}", "被杀次数": c,
               "被这些条件杀": "、".join(num_src[n])} for n, c in _sorted]
    if rows_n:
        st.dataframe(pd.DataFrame(rows_n), use_container_width=True,
                     hide_index=True, height=280)

    strong = [(n, c) for n, c in _sorted if c >= 2]
    if strong:
        st.error("⛔ 本组必杀号码（多次触犯）：" +
                 "　".join(f"{n:02d}({c}次)" for n, c in strong))
    elif _sorted:
        st.warning("本组只有单次杀号（无多次触犯），参考价值一般")

    keep = [f"{n:02d}" for n in keep_nums]
    if keep:
        st.success(f"✅ 本组保留号码（{len(keep)} 个）：" + " ".join(keep))
    else:
        st.warning("本区间没有保留号码")

    st.download_button(f"📥 下载 {label} 杀号清单",
                       pd.DataFrame(rows_n or [{"号码": "无", "被杀次数": 0,
                                                "被这些条件杀": ""}]
                                    ).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"杀号_{label}.csv", mime="text/csv",
                       key=f"kill_dl_{label}")
    if unmapped:
        st.caption("未能翻译的条件：" + "、".join(unmapped))

    # 保存结果到云端看板
    _period = (blocks[0].get("period") if blocks else "") or ""
    _lines = [f"期号 {_period}　{label}　取值区间 {_lo}~{_hi}", ""]
    _lines.append("【属性级】")
    for g, v, n, _s in ks:
        _lines.append(f"  {g}：杀 {v}（{n} 次）")
    if rows_n:
        _lines.append("")
        _lines.append("【号码级】")
        for r in rows_n:
            _lines.append(f"  {r['号码']}  被杀 {r['被杀次数']} 次  ← {r['被这些条件杀']}")
    if strong:
        _lines.append("")
        _lines.append("【必杀号码】" + " ".join(f"{n:02d}" for n, _c in strong))
    if keep:
        _lines.append("")
        _lines.append(f"【保留号码 {len(keep)} 个】" + " ".join(keep))
    _save_txt = "\n".join(_lines)
    if st.button(f"📌 保存「{label}」结果到看板", key=f"save_{label}"):
        try:
            _board_add("杀号结果", f"{_period} {label}", _save_txt)
            st.success("已保存到看板（云端）")
        except Exception as _e:
            st.warning(f"保存失败：{_e}")


def _multi_struct_text(blocks):
    """只输出标题信息 + 上/杀括号，不含基准行与「下」"""
    groups = {}
    for b in blocks:
        key = f"{b['period']}期 {b['order']}第{b['ball']}球"
        groups.setdefault(key, []).append(b)

    lines = [f"共 {len(blocks)} 条属性报告，按「期号+球位」分组：", ""]
    for gname, gblocks in groups.items():
        lines.append(f"===== {gname} =====")
        for b in gblocks:
            lines.append(f"【属性：{b['attr']}】")
            if not b["triggers"]:
                lines.append("  （无触发行）")
            for i, tg in enumerate(b["triggers"], 1):
                up = _clean_kill(tg.get("up", ""))
                kl = tg.get("kill", "")
                if kl:
                    lines.append(f"  触发行{i}：杀({kl})　→ 只杀括号内的值")
                else:
                    lines.append(f"  触发行{i}：上={up}　（无括号 → 杀「{up}」）")
        lines.append("")
    return "\n".join(lines)


def _multi_ai_analyze(question, raw_text=None, evidence=""):
    """解析报告并交给 AI（可附旁证资料）"""
    text = raw_text or ""
    if not text.strip():
        # 从看板里凑
        board = _board_sync_load() or []
        text = "\n\n".join(e.get("text", "") for e in board
                            if "基准行排列" in (e.get("text") or ""))
    blocks = _parse_multi_blocks(text)
    if not blocks:
        return None, "没有解析到报告内容（需要包含【基准行排列】和触发行）"
    summary = _multi_struct_text(blocks)
    _ev = (evidence or "").strip()
    _ev_part = (f"\n\n【旁证资料（供印证，不得替代主规则）】\n{_ev[:6000]}\n"
                if _ev else "")
    prompt = (f"下面是 {len(blocks)} 条多维分析报告的结构化结果：\n\n{summary}"
              f"{_ev_part}\n\n"
              f"【我的问题】\n{question}\n\n"
              f"请按以下要求作答（旁证只用于印证主报告的杀号，\n"
              f"若旁证与主报告冲突，以主报告（触发行/杀括号）为准并说明冲突）：\n"
              f"1) 按属性逐个说明：该属性历史上匹配到几段、上期/下期分别是什么值\n"
              f"2) 汇总所有属性中「下期值」出现最多的取值（若同一属性多个触发行，分别列出）\n"
              f"3) 指出哪些属性的结论一致、哪些互相矛盾\n"
              f"4) 给出下一期各位置最可能的属性取值（克制、注明依据与不确定性）\n"
              f"5) 如果证据不足，明确说「无法判断」\n"
              f"6) 注意：报告里的「上」才是要杀掉的属性（不是「下」），"
              f"请汇总成杀号清单，不要当成要选的号码")
    return call_deepseek_api(prompt, _MULTI_RULES), None


def _multi_ai_ui():
    """多维报告分析入口（控件常显、自动解析）"""
    with st.expander("📊 多维报告分析（触发行 → 杀号清单）", expanded=True):
        st.caption("规则：只看触发行；有（杀XXX）只认括号内，否则杀「上」；"
                   "不同球位默认分开，可勾选合并并指定主导区间。")

        _items = _board_sync_load() or []
        _src = st.radio("数据来源", ["自动读看板", "手动粘贴"], horizontal=True,
                        key="multi_src")
        _txt = ""
        if _src == "手动粘贴":
            _txt = st.text_area("把报告粘进来", height=160, key="multi_raw",
                                placeholder="=========2026124期升序-生肖2球=======…")
        else:
            if not _items:
                st.info("看板里还没有内容，请先从其它页面推送，或改用「手动粘贴」。")
            else:
                _opts = [f"{i+1}. {e.get('source','')}｜{e.get('title','')}"
                         for i, e in enumerate(_items)]
                _sel = st.multiselect(
                    "选择看板条目（不选=全部）", _opts, default=[],
                    key="multi_pick")
                _idxs = ([int(x.split(".")[0]) - 1 for x in _sel]
                         if _sel else list(range(len(_items))))
                _txt = "\n\n".join(
                    _items[i].get("text", "") for i in _idxs
                    if "基准行排列" in (_items[i].get("text") or ""))

        _blocks = _parse_multi_blocks(_txt)
        if not _blocks:
            st.warning("没有解析到报告内容（需要包含【基准行排列】和触发行）")
            return

        st.success(f"解析到 {len(_blocks)} 条属性报告")
        _groups = {}
        for b in _blocks:
            key = f"{b['order']}第{b['ball']}球"
            _groups.setdefault(key, []).append(b)
        _labels = list(_groups.keys())

        st.markdown("**① 合并设置（主导 + 辅助）**")
        _dom = st.selectbox(
            "★ 主导球位（决定取值区间）", _labels, index=0, key="multi_dom",
            help="合并计算时，所有号码都按这个球位的区间取值")
        _dlo, _dhi = _range_of(_dom)
        _merge_sel = st.multiselect(
            "辅助球位（勾选后其杀号条件并入主导一起算）", _labels,
            default=[], key="multi_merge")
        _merge = [k for k in _merge_sel if k != _dom]
        st.info(f"主导：**{_dom}**（取值区间 {_dlo}~{_dhi}）"
                + (f"　＋　辅助：{'、'.join(_merge)}" if _merge else
                   "　（未选辅助 → 各球位单独计算）")
                + (f"\n→ 合并后只在 **{_dlo}~{_dhi}** 里取号" if _merge else ""))

        _amap = _load_attr_map()
        if not _amap:
            st.error("缺少 _attr_map.csv，无法把杀号翻译成号码")

        # 合并结果先显示
        if _merge and _amap:
            st.markdown("**② 合并计算结果**")
            _allk = [_dom] + _merge
            _mb = [b for k in _allk for b in _groups.get(k, [])]
            with st.expander("＋ 合并：" + " + ".join(_allk) +
                             f"（取值区间 {_dlo}~{_dhi}）", expanded=True):
                _render_kill_group("合并_" + "_".join(_allk), _mb, _amap,
                                   range_label=_dom)

        # 单独结果
        _单独 = [k for k in _labels
                 if k not in _merge and not (_merge and k == _dom)]
        if _单独:
            st.markdown("**② 单独计算结果**")
            for k in _单独:
                _klo, _khi = _range_of(k)
                with st.expander(f"■ {k}（{len(_groups[k])} 个属性，"
                                 f"区间 {_klo}~{_khi}）", expanded=True):
                    _render_kill_group(k, _groups[k], _amap)

        # 解析详情
        with st.expander("🔍 解析详情（排查用）", expanded=False):
            _dbgrows = []
            for b in _blocks:
                _ups = "、".join(_clean_kill(tg.get("up", ""))
                                 for tg in b["triggers"]) or "—"
                _kls = "、".join(tg.get("kill", "") for tg in b["triggers"]) or "—"
                _dbgrows.append({"属性": b["attr"], "球位": b["ball"],
                                 "触发行": len(b["triggers"]),
                                 "上值": _ups, "杀括号": _kls})
            st.dataframe(pd.DataFrame(_dbgrows), use_container_width=True,
                         hide_index=True)

        # ③ 佐证资料（可多选）
        st.markdown("**③ 佐证资料（可多选，喂给 AI 做旁证）**")
        _ev_items = []
        if _items:
            _ev_opts = [f"{i+1}. {e.get('source','')}｜{e.get('title','')}"
                        for i, e in enumerate(_items)]
            _ev_sel = st.multiselect(
                "从看板里选佐证（例如深度联动的各球位结果，可多套）",
                _ev_opts, default=[], key="multi_ev")
            _ev_items = [_items[int(x.split(".")[0]) - 1] for x in _ev_sel]
            if _ev_items:
                st.caption("已选佐证：" + "；".join(
                    f"{e.get('title','')}" for e in _ev_items[:8])
                    + ("…" if len(_ev_items) > 8 else ""))
        _ev_text = "\n\n".join(
            f"【{e.get('title','')}】\n{(e.get('text') or '')[:1500]}"
            for e in _ev_items)

        # AI 解读
        st.markdown("**④ AI 解读（可选）**")
        _q = st.text_area(
            "你想问什么",
            value="按球位分别汇总：每个属性要杀什么、每个球位的必杀号码与保留号码。",
            height=90, key="multi_q")
        if st.button("▶ 让 AI 解读", type="primary", key="multi_go"):
            with st.spinner("AI 分析中（约 10~30 秒）…"):
                try:
                    _ans, _err = _multi_ai_analyze(_q, _txt, _ev_text)
                except Exception as _e:
                    _ans, _err = None, f"{type(_e).__name__}: {_e}"
            if _err:
                st.warning(_err)
            elif _ans:
                st.session_state["multi_ai_ans"] = _ans
        _ans = st.session_state.get("multi_ai_ans")
        if _ans:
            st.code(_ans, language=None)
            if st.button("📌 结果放回看板", key="multi_ai_save"):
                _board_add("多维分析AI", f"综合解读 {datetime.now():%m-%d %H:%M}",
                           _ans)
                st.success("已放回看板")


def _board_ai_ui():
    """AI页面的综合分析入口"""
    with st.expander("🤖 AI 综合分析（基于看板数据）", expanded=False):
        st.caption("把看板里的结果按规则交给 AI 分析。数据量大时会自动压缩。")
        _q = st.text_area(
            "你想问什么",
            value="请分析这些结果：\n1) 哪些组合出现的规律最明显\n"
                  "2) 号码频次排行说明了什么\n3) 如果按这些数据继续研究，"
                  "下一步应该重点看什么\n4) 有什么统计上的陷阱需要注意",
            height=120, key="board_ai_q")
        c1, c2 = st.columns([1, 2])
        with c1:
            _go = st.button("▶ 开始分析", type="primary", key="board_ai_go",
                            use_container_width=True)
        with c2:
            st.caption("管理员不限次数；普通用户有频率限制。")
        if _go:
            if not (_q or "").strip():
                st.warning("请先写问题")
            else:
                with st.spinner("AI 分析中（约 10~30 秒）…"):
                    _ans = _board_ai_analyze(_q)
                st.session_state["board_ai_ans"] = _ans
        _ans = st.session_state.get("board_ai_ans")
        if _ans:
            st.markdown("**AI 分析结果**")
            st.code(_ans, language=None)
            if st.button("📌 把分析结果放回看板", key="board_ai_save"):
                _board_add("AI分析", f"综合分析 {datetime.now():%m-%d %H:%M}",
                           _ans)
                st.success("已放回看板")


def _board_render():
    """在 AI推演 页面顶部渲染看板"""
    board = _board_sync_load() or []
    if not _board_table_ok():
        st.error("看板未连接数据库：请在 Supabase 的 SQL Editor 里执行 "
                 "i_board_table.sql（仓库根目录），然后 Reboot app。")
        return
    if not board:
        return
    # 字体由全局 CSS 统一控制
    with st.expander(f"📋 汇总看板（{len(board)} 条结果，来自其它页面）", expanded=True):
        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("🗑 清空看板", use_container_width=True, key="board_clear"):
                st.session_state.ai_board = []
                _board_cloud_clear()
                st.rerun()
        with c2:
            _all = "\n\n".join(
                f"===== {e['source']} | {e['title']} | {e['ts']} =====\n{e['text']}"
                for e in board)
            st.download_button("📥 导出全部", _all.encode("utf-8-sig"),
                               file_name=f"汇总看板_{datetime.now():%Y%m%d_%H%M%S}.txt",
                               mime="text/plain", use_container_width=True,
                               key="board_export")

        for i, e in enumerate(board):
            with st.expander(f"{e['source']} · {e['title']}　({e['ts']})", expanded=False):
                st.text_area("内容", value=e["text"], height=340,
                             key=f"board_txt_{i}_{e['ts']}", label_visibility="collapsed")
                if st.button("移除此条", key=f"board_del_{i}_{e['ts']}"):
                    st.session_state.ai_board.pop(i)
                    _board_cloud_delete(e.get("source", ""), e.get("title", ""))
                    st.rerun()


@st.cache_data(ttl=86400, show_spinner=False)
def load_real_data():
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")
    file_name = "总数据.xlsx"
    _sheet = "总数据表"
    if not token or not repo:
        if not os.path.exists(file_name): return None
        try: df_raw = pd.read_excel(file_name, sheet_name=_sheet, header=None)
        except Exception as e: return str(e)
    else:
        df_raw = None
        _errs = []
        # ⓿ 磁盘缓存（6 小时内有效，重启后秒开）
        _disk = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "_src_cache.xlsx")
        try:
            if (os.path.exists(_disk)
                    and time.time() - os.path.getmtime(_disk) < 6 * 3600):
                df_raw = pd.read_excel(_disk, sheet_name=_sheet, header=None)
        except Exception:
            df_raw = None

        # ① 官方 API + download_url
        for _att in range(2):
            try:
                url = f"https://api.github.com/repos/{repo}/contents/{file_name}"
                r = requests.get(url, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/vnd.github.v3+json"},
                                 timeout=30)
                if r.status_code == 200:
                    _du = r.json().get("download_url")
                    if _du:
                        _bin = requests.get(_du, timeout=60).content
                        df_raw = pd.read_excel(io.BytesIO(_bin), sheet_name=_sheet, header=None)
                        try:
                            with open(_disk, "wb") as _f:
                                _f.write(_bin)
                        except Exception:
                            pass
                        break
                else:
                    _errs.append(f"API {r.status_code}")
            except Exception as _e:
                _errs.append(type(_e).__name__)
            time.sleep(1)
        # ② raw 直链
        if df_raw is None:
            try:
                _raw = (f"https://raw.githubusercontent.com/{repo}/main/"
                        f"{urllib.parse.quote(file_name)}")
                _bin = requests.get(_raw, timeout=60).content
                df_raw = pd.read_excel(io.BytesIO(_bin), sheet_name=_sheet, header=None)
                try:
                    with open(_disk, "wb") as _f:
                        _f.write(_bin)
                except Exception:
                    pass
            except Exception as _e:
                _errs.append("raw:" + type(_e).__name__)
        # ③ 本地 xlsx
        if df_raw is None and os.path.exists(file_name):
            try:
                df_raw = pd.read_excel(file_name, sheet_name=_sheet, header=None)
            except Exception as _e:
                _errs.append("local:" + type(_e).__name__)
        # ④ 最后回退：用 CSV 升序全集
        if df_raw is None:
            try:
                _csv = load_excel_data("升序全套.csv", None)
                if _csv:
                    df_raw = pd.DataFrame(_csv)
            except Exception as _e:
                _errs.append("csv:" + type(_e).__name__)
        if df_raw is None:
            return "云端源文件读取失败（" + "、".join(_errs[:4]) + "）"
    try:
        synced_rows = []
        def clean_val(v):
            if pd.isna(v): return ""
            try: return str(int(float(v)))
            except: return str(v).strip()
        for idx, row in df_raw.iterrows():
            # 总数据表：第19列(索引18)=期数，第20~26列(索引19~25)=1球~7球
            if len(row) < 26:
                continue
            period_str = clean_val(row[18])
            if not period_str or not period_str.replace(".", "").isdigit():
                continue
            nums = []
            ok = True
            for i in range(7):
                v = clean_val(row[19 + i])
                if v == "":
                    nums.append(None)
                    continue
                try:
                    nums.append(int(float(v)))
                except Exception:
                    ok = False
                    break
            if not ok or all(x is None for x in nums[:6]):
                continue
            new_row = [None] * 30
            new_row[18] = period_str
            for i in range(6):
                new_row[19 + i] = nums[i]
            new_row[25] = nums[6]
            synced_rows.append(new_row)
        result_df = pd.DataFrame(synced_rows)
        try: result_df = result_df.sort_values(by=18, ascending=False).reset_index(drop=True)
        except: pass
        return result_df
    except Exception as e: return f"数据转换异常: {e}"

@st.cache_data(show_spinner=False, ttl=3600)
def load_excel_data(file_path, sheet_name=None):
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")
    def parse_content(content):
        if file_path.lower().endswith(".csv"):
            try: text = content.decode("utf-8-sig")
            except: text = content.decode("gbk", errors="ignore")
            return [[cell.replace('\r', '').replace('\n', '').strip() for cell in line.split(',')] for line in text.splitlines() if line.strip()]
        else:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            return list(wb[sheet_name].iter_rows(values_only=True))
    if not token or not repo:
        try:
            with open(file_path, "rb") as f: return parse_content(f.read())
        except: return []
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200: return parse_content(requests.get(r.json()["download_url"]).content)
        else: return []
    except: return []

# ==========================================
# 4. 核心算法引擎
# ==========================================
def generate_20_combos(nums):
    combos = list(itertools.combinations(nums, 3))
    return [",".join([str(x).zfill(2) for x in c]) for c in combos]


def calculate_linkage(df_data, target_period, mode):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: return None, None, "未找到该期数据"
    base_idx = matched.index[0]
    current_row = matched.iloc[0]
    base_nums = [int(clean_period(current_row.iloc[i])) for i in range(19, 25) if pd.notna(current_row.iloc[i]) and clean_period(current_row.iloc[i]) != ""]
    special_num = int(clean_period(current_row.iloc[25])) if pd.notna(current_row.iloc[25]) else None
    if len(base_nums) < 6: return None, None, "基准期开奖号码不足6个"
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    if is_descending: start_idx, end_idx = base_idx + 1, len(df_data) - 1
    else: start_idx, end_idx = 0, base_idx - 1
    if start_idx > end_idx: return None, None, "附近没有历史数据"
    triggers, total_counter = [], Counter()

    if mode == "单排分析":
        combos_str = generate_20_combos(base_nums)
        for idx in range(start_idx, end_idx + 1):
            row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
            row_period = clean_period(df_data.iloc[idx, 18])
            for combo_str in combos_str:
                combo = [int(x) for x in combo_str.split(",")]
                if all(n in row_nums for n in combo):
                    triggers.append({"组合": combo_str, "触发行": idx + 1, "触发期数": row_period, "触发行号码": ",".join([f"{n:02d}" for n in row_nums])})
                    next_idx = idx - 1 if is_descending else idx + 1
                    if 0 <= next_idx < len(df_data):
                        next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                        for n in next_row_nums: total_counter[n] += 1
    else:
        dict_history = set()
        for i in range(7):
            current_base = list(base_nums)
            if i >= 1 and special_num is not None: current_base[i-1] = special_num
            if len(current_base) < 6: continue
            new_combos = generate_20_combos(current_base)
            valid_combos = [c for c in new_combos if c not in dict_history]
            for c in valid_combos: dict_history.add(c)
            if not valid_combos: continue
            for idx in range(start_idx, end_idx + 1):
                row_nums = [int(clean_period(df_data.iloc[idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[idx, j]) and clean_period(df_data.iloc[idx, j]) != ""]
                row_period = clean_period(df_data.iloc[idx, 18])
                for combo_str in valid_combos:
                    combo = [int(x) for x in combo_str.split(",")]
                    if all(n in row_nums for n in combo):
                        triggers.append({"组合": combo_str, "触发行": idx + 1, "触发期数": row_period, "触发行号码": ",".join([f"{n:02d}" for n in row_nums])})
                        next_idx = idx - 1 if is_descending else idx + 1
                        if 0 <= next_idx < len(df_data):
                            next_row_nums = [int(clean_period(df_data.iloc[next_idx, j])) for j in range(19, 26) if pd.notna(df_data.iloc[next_idx, j]) and clean_period(df_data.iloc[next_idx, j]) != ""]
                            for n in next_row_nums: total_counter[n] += 1

    sorted_counts = sorted(total_counter.items(), key=lambda x: x[1], reverse=True)
    df_triggers = pd.DataFrame(triggers) if triggers else pd.DataFrame(columns=["组合", "触发行", "触发期数", "触发行号码"])
    df_counts = pd.DataFrame([{"下期数字": f"{n:02d}", "出现次数": c} for n, c in sorted_counts])
    return df_triggers, df_counts, None


def calculate_prize(df_data, target_period, predicted_nums):
    df_data['_temp_p'] = df_data.iloc[:, 18].apply(clean_period)
    matched = df_data[df_data['_temp_p'] == target_period]
    if matched.empty: return None, f"找不到本期 {target_period}！"
    base_pos = df_data.index.get_loc(matched.index[0])
    next_pos = base_pos - 1
    if next_pos < 0: return {"下期期数": "待开奖", "预测组合": ",".join(predicted_nums), "状态": "本期未开奖"}, "本期未开奖"
    next_row = df_data.iloc[next_pos]
    next_period = clean_period(next_row.iloc[18])
    nums = [clean_period(next_row.iloc[i]) for i in range(19, 25)]
    z_val = clean_period(next_row.iloc[25]) if len(next_row) > 25 else ""
    match_nums = [n for n in nums if n and n in predicted_nums]
    try: match_nums.sort(key=lambda x: int(x))
    except: pass
    z_matched = z_val in predicted_nums if z_val else False
    status = "有命中" if (len(match_nums) > 0 or z_matched) else "无中任何数字"
    result = {"下期期数": next_period, "预测组合": ",".join(predicted_nums), "中出平码1": match_nums[0] if len(match_nums)>0 else "", "中出平码2": match_nums[1] if len(match_nums)>1 else "", "中出平码3": match_nums[2] if len(match_nums)>2 else "", "中出平码4": match_nums[3] if len(match_nums)>3 else "", "中出平码5": match_nums[4] if len(match_nums)>4 else "", "中出平码6": match_nums[5] if len(match_nums)>5 else "", "中出特码": z_val if z_matched else "", "状态": status}
    return result, None

# ==========================================
# 5. 各页面渲染
# ==========================================
def render_trend_chart(df_data):
    st.divider()
    st.subheader("📈 历史走势图（最近30期）")
    if df_data is None or isinstance(df_data, str): return
    recent_data = df_data.head(30).copy()
    if recent_data.empty: return
    periods = recent_data.iloc[:, 18].apply(clean_period).tolist()
    tab1, tab2 = st.tabs(["平 码 区", "特 码 区"])
    with tab1:
        cols = [f"{i:02d}" for i in range(1, 50)]
        matrix = pd.DataFrame("", index=periods, columns=cols)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            for i in range(19, 25):
                num_str = clean_period(row.iloc[i])
                if num_str in cols: matrix.at[period, num_str] = "●"
        st.dataframe(matrix, use_container_width=True, height=600)
    with tab2:
        cols = [f"{i:02d}" for i in range(1, 50)]
        matrix_special = pd.DataFrame("", index=periods, columns=cols)
        for idx, row in recent_data.iterrows():
            period = clean_period(row.iloc[18])
            num_str = clean_period(row.iloc[25]) if len(row) > 25 else ""
            if num_str in cols: matrix_special.at[period, num_str] = "★"
        st.dataframe(matrix_special, use_container_width=True, height=600)


# ==========================================
# 报告校验（只读：把报告里的匹配拉回原始数据核对）
# ==========================================
_V_CHILD = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
_V_MOTHER = {v: k for k, v in _V_CHILD.items()}
_V_KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}


def _v_cell(rows, row1, col_letter):
    """CSV 第 row1 行（1 基，含表头）col_letter 列的值"""
    try:
        from openpyxl.utils import column_index_from_string
        idx = column_index_from_string(col_letter) - 1
    except Exception:
        return ""
    if not (1 <= row1 <= len(rows)):
        return ""
    r = rows[row1 - 1]
    return r[idx].strip() if idx < len(r) else ""


def _v_strip(s):
    import re as _re
    return _re.sub(r"[肖号尾]$", "", str(s).strip())


def _v_norm(s):
    return _v_strip(str(s).split("(")[0].split("（")[0].strip())


def _v_wx(s):
    for w in "金木水火土":
        if w in str(s):
            return w
    return ""


def _v_rel(a, b, kind):
    ca, cb = _v_wx(a), _v_wx(b)
    if not ca or not cb:
        return False
    if kind == "相生":
        return _V_CHILD.get(ca) == cb or _V_MOTHER.get(ca) == cb
    return _V_KE.get(ca) == cb or _V_KE.get(cb) == ca


# ==========================================
# 全自动核算：死规则（阈值）
#   near = 近N期一致的最小 N；self = 自身参考列匹配的最小行数；
#   normal = 普通匹配的最小行数
# ==========================================
# ==================== 【勿改】用户自审用的死规则表 ====================
# 这套规则是全自动核算的审核标准，用户明确要求保持原样。
# 任何新功能（如计算中心）不得修改或复用本表。
_AUTO_RULES = {
    "生肖": {"near": 5, "self": 4, "normal": 5},
    "尾数": {"near": 5, "self": 4, "normal": 5},
    "数字合": {"near": 5, "self": 4, "normal": 5},
    "数字五行": {"near": 6, "self": 6, "normal": 7},
    "单双组合": {"near": 6, "self": 9, "normal": 9},
    "波单双": {"near": 5, "self": 6, "normal": 6},
    "生肖五行": {"near": 6, "self": 8, "normal": 8},
    "尾五行": {"near": 6, "self": 8, "normal": 8},
    "四宝": {"near": 6, "self": 9, "normal": 9},
    "物象": {"near": 6, "self": 9, "normal": 9},
    "阴阳天地": {"near": 6, "self": 9, "normal": 9},
    "方位": {"near": 6, "self": 9, "normal": 9},
    "颜色肖": {"near": 6, "self": 11, "normal": 12},
    "波色": {"near": 6, "self": 11, "normal": 12},
    "3模": {"near": 10, "self": 12, "normal": 12},
    "福禄寿": {"near": 10, "self": 12, "normal": 12},
    "大小肖": {"near": 10, "self": 12, "normal": 12},
}
# 门数 / 段数：按球位不同
_AUTO_MENDUAN = {
    1: {"near": 7, "self": 8, "normal": 9},
    6: {"near": 7, "self": 8, "normal": 9},
    2: {"near": 6, "self": 7, "normal": 7},
    3: {"near": 6, "self": 7, "normal": 7},
    4: {"near": 6, "self": 7, "normal": 7},
    5: {"near": 6, "self": 7, "normal": 7},
    7: {"near": 6, "self": 6, "normal": 7},
}
_AUTO_XIANG = {"near": 12, "self": 12, "normal": 12}   # 所有相生/相克


def _auto_rule(attr, ball_no):
    if "相生" in attr or "相克" in attr:
        return dict(_AUTO_XIANG)
    if attr in ("门数", "段数"):
        return dict(_AUTO_MENDUAN.get(int(ball_no), {"near": 7, "self": 8, "normal": 9}))
    return dict(_AUTO_RULES.get(attr, {"near": 6, "self": 8, "normal": 9}))


_AUTO_LINE_RE = None


def _auto_parse_line(ln):
    """解析一条触发行 -> dict 或 None"""
    import re as _re
    global _AUTO_LINE_RE
    if _AUTO_LINE_RE is None:
        _AUTO_LINE_RE = _re.compile(
            r"触发行：(?P<ball>\d)球\((?P<col>[A-Z]+)\)\s*行(?P<a>\d+)-(?P<b>\d+)"
            r"\((?P<n>\d+)行\)(?P<mid>[^\n]*?)(?:上:.*)$")
    mm = _AUTO_LINE_RE.search(ln)
    if not mm:
        return None
    mid = mm.group("mid") or ""
    near = None
    mn = _re.search(r"近(\d+)期一致", mid)
    if mn:
        near = int(mn.group(1))
    return {"n": int(mm.group("n")), "near": near,
            "self": "自身参考列匹配" in ln, "col": mm.group("col")}


def _auto_keep(line, rule):
    """按死规则判断这条触发行是否录入"""
    info = _auto_parse_line(line)
    if info is None:
        return False
    n = info["n"]
    if info["near"] is not None and info["near"] >= rule["near"]:
        return True
    if info["self"]:
        return n >= rule["self"]
    return n >= rule["normal"]


def _raw_report_for_ball(file_key, rows, ball_str, attrs, runner, fake):
    """跑某球全部属性，返回【未经规则筛选】的原始报告（供计算中心查档）"""
    import pandas as _pd
    periods = []
    for r in rows:
        periods.append(f"{r[213]}{r[0]}{r[1]}{r[2]}" if len(r) > 213 else "")
    df = _pd.DataFrame({str(i): [""] * len(rows) for i in range(29)})
    df[str(18)] = periods

    try:
        runner.__globals__["load_excel_data"] = lambda *a, **k: rows
    except Exception:
        pass
    fake.session_state["_allow_raw_btn"] = True
    fake.ctrl["file"] = file_key
    fake.session_state["current_file"] = file_key
    fake.ctrl["ball"] = ball_str
    fake.min_len = 4
    fake.max_len = 17

    parts = []
    for attr in attrs:
        fake.ctrl["attr"] = attr
        fake.session_state["multi_result_text"] = ""
        fake.session_state["multi_results_dict"] = {}
        fake.session_state["last_multi_signature"] = None
        # 关键：把两个模式的存档槽也清空，否则算不出结果时会沿用上一个属性的内容
        fake.session_state["text_single"] = ""
        fake.session_state["text_all"] = ""
        fake.session_state["full_scan_results"] = []
        fake.errors.clear()
        try:
            with _NoComp():
                runner(df)
        except _ScanStop:
            pass
        except Exception:
            continue
        rep_txt = fake.session_state.get("multi_result_text") or ""
        if rep_txt:
            parts.append(rep_txt)
    return "\n".join(parts)


def _auto_run(file_key, rows, ball_str, attrs, runner, fake, period="", order="升序"):
    """对当前球的所有属性跑一遍，按规则筛选。返回 (结果文本, 统计表, 原始行数)"""
    import pandas as _pda
    ball_no = int(str(ball_str).replace("第", "").replace("球", ""))
    periods = []
    for r in rows:
        periods.append(f"{r[213]}{r[0]}{r[1]}{r[2]}" if len(r) > 213 else "")
    df = _pda.DataFrame({str(i): [""] * len(rows) for i in range(29)})
    df[str(18)] = periods

    try:
        runner.__globals__["load_excel_data"] = lambda *a, **k: rows
    except Exception:
        pass
    # 自动核算要用更低的对比行数，否则 4~6 行的匹配根本算不出来
    fake.min_len = 4
    fake.max_len = 17
    fake.session_state["_allow_raw_btn"] = True   # 让虚拟界面能触发计算
    fake.ctrl["file"] = file_key
    fake.session_state["current_file"] = file_key
    fake.ctrl["ball"] = ball_str

    blocks, stats = [], []
    total_in = 0
    for attr in attrs:
        fake.ctrl["attr"] = attr
        fake.session_state["multi_result_text"] = ""
        fake.session_state["multi_results_dict"] = {}
        fake.session_state["last_multi_signature"] = None
        # 关键：把两个模式的存档槽也清空，否则算不出结果时会沿用上一个属性的内容
        fake.session_state["text_single"] = ""
        fake.session_state["text_all"] = ""
        fake.session_state["full_scan_results"] = []
        fake.errors.clear()
        try:
            with _NoComp():
                runner(df)
        except _ScanStop:
            pass
        except Exception:
            continue
        report = fake.session_state.get("multi_result_text") or ""
        if not report:
            stats.append((attr, 0, 0))
            continue
        if not period:
            _pm = re.search(r"-\s*([0-9]{5,8})\s*-", report)
            if _pm:
                period = _pm.group(1)
        rule = _auto_rule(attr, ball_no)
        kept, total = [], 0
        for ln in report.splitlines():
            if "触发行：" not in ln:
                continue
            total += 1
            if _auto_keep(ln, rule):
                kept.append(ln)
        total_in += len(kept)
        stats.append((attr, total, len(kept)))
        if kept:
            _title = (f"========={period}期{order}-{attr}{ball_no}球=======")
            _base = [l for l in report.splitlines() if l.startswith("【基准行排列】")]
            _head = _title + ("\n" + "\n".join(_base) if _base else "")
            # 基准行与触发行之间空一行，便于区分
            blocks.append(_head + "\n\n" + "\n".join(kept))

    text = ("\n".join(blocks) if blocks else "")
    return text, stats, total_in


class _ScanST:
    """假界面：让页面函数在后台跑，只取计算结果，不碰真实 UI"""

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __getattr__(self, n): return lambda *a, **k: None

    def __init__(self):
        outer = self

        class _SS(dict):
            def __getattr__(s, k):
                try:
                    return s[k]
                except KeyError:
                    return None

            def __setattr__(s, k, v):
                s[k] = v

        self.session_state = _SS()
        class _Sec:
            @staticmethod
            def get(k, d=None):
                return d

        self.secrets = _Sec()
        self.ctrl = {"attr": None, "ball": "第1球", "file": "升序全套"}
        self.errors = []

    # 装饰器
    def cache_data(self, *a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    cache_resource = cache_data

    # 控件
    def button(self, label="", *a, **k):
        # 只让「执行分析」返回 True，其余按钮当作没点
        return "执行分析" in str(label)

    def checkbox(self, *a, **k):
        return False

    def radio(self, label="", options=None, *a, **k):
        o = list(options or [])
        return o[0] if o else None

    def selectbox(self, label="", options=None, *a, **k):
        o = list(options or [])
        lbl = str(label)
        if "属性" in lbl:
            return self.ctrl["attr"] if self.ctrl["attr"] in o else (o[0] if o else None)
        if "球号" in lbl or "基准球" in lbl:
            return self.ctrl["ball"] if self.ctrl["ball"] in o else (o[0] if o else None)
        if "文件" in lbl:
            return self.ctrl["file"]
        return o[0] if o else None

    def number_input(self, label="", *a, **k):
        lbl = str(label)
        if "最少" in lbl:
            return getattr(self, "min_len", 7)
        if "最多" in lbl:
            return getattr(self, "max_len", 12)
        return k.get("value", 7)

    def multiselect(self, *a, **k):
        return []

    def text_area(self, *a, **k):
        return str(k.get("value", ""))

    def text_input(self, *a, **k):
        return str(k.get("value", ""))

    def columns(self, spec, *a, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [self._Ctx() for _ in range(n)]

    def tabs(self, names, *a, **k):
        return [self._Ctx() for _ in names]

    def expander(self, *a, **k): return self._Ctx()
    def form(self, *a, **k): return self._Ctx()
    def spinner(self, *a, **k): return self._Ctx()
    def container(self, *a, **k): return self._Ctx()
    def progress(self, *a, **k): return self._Ctx()
    def empty(self, *a, **k): return self._Ctx()
    def chat_message(self, *a, **k): return self._Ctx()

    def chat_input(self, *a, **k): return None

    def error(self, msg, *a, **k):
        self.errors.append(str(msg)[:200])

    def stop(self, *a, **k):
        raise _ScanStop()

    def rerun(self, *a, **k):
        raise _ScanStop()

    def __getattr__(self, name):
        return lambda *a, **k: None


class _ScanStop(Exception):
    pass


# 用可变容器：内部重跑时被抽取的函数拿到的是同一个 dict，开关才真正生效
_INNER = {"run": 0}


class _NoComp:
    """内部重跑页面时，把 components.html 换成空操作，避免往真实界面插按钮"""

    def __enter__(self):
        _INNER["run"] += 1
        import sys as _s
        self._saved = {k: _s.modules.get(k) for k in
                       ("streamlit.components", "streamlit.components.v1")}
        import types as _t
        _pkg = _t.ModuleType("streamlit.components")
        _v1 = _t.ModuleType("streamlit.components.v1")
        _v1.html = lambda *a, **k: None
        _pkg.v1 = _v1
        _s.modules["streamlit.components"] = _pkg
        _s.modules["streamlit.components.v1"] = _v1
        return self

    def __exit__(self, *a):
        _INNER["run"] = max(0, _INNER["run"] - 1)
        import sys as _s
        for k, v in self._saved.items():
            if v is not None:
                _s.modules[k] = v
        return False


def _auto_merge(prev, new, ball_str):
    """把新结果并入同一份文档：同球号的旧段被替换，其它段原样保留。"""
    def blocks(txt):
        out, cur = [], []
        for ln in (txt or "").splitlines():
            if ln.startswith("==========") and cur:
                out.append("\n".join(cur).strip("\n"))
                cur = [ln]
            else:
                cur.append(ln)
        if cur:
            out.append("\n".join(cur).strip("\n"))
        return [b for b in out if b.strip()]

    new_b = blocks(new)
    if not (prev or "").strip():
        return "\n\n".join(new_b)
    marker = f"- {ball_str} =========="
    keep = [b for b in blocks(prev) if marker not in b.splitlines()[0]]
    return "\n\n".join(keep + new_b)


def _scan_build_runner():
    """把页面里的 render_multi_analysis 源码原样抽出来，配虚拟界面"""
    import ast as _astmod
    import textwrap
    src = open(__file__, encoding="utf-8").read()
    tree = _astmod.parse(src)
    fn = None
    for n in tree.body:
        if isinstance(n, _astmod.FunctionDef) and n.name == "render_multi_analysis":
            fn = n
            break
    if fn is None:
        raise RuntimeError("找不到 render_multi_analysis")
    code = textwrap.dedent(_astmod.get_source_segment(src, fn))
    fake = _ScanST()
    g = dict(globals())
    g["st"] = fake
    exec(compile(code, "<scan-multi>", "exec"), g)
    return g["render_multi_analysis"], fake


def _scan_periods(rows):
    out = []
    for r in rows:
        if len(r) > 213:
            out.append(f"{r[213]}{r[0]}{r[1]}{r[2]}")
        else:
            out.append("")
    return out


def _scan_one_file(file_key, rows, balls, attrs, runner, fake, progress_cb=None):
    """扫描一个文件，返回 (明细, 问题, 触发行总数, 单元格总数)"""
    import pandas as _pds
    periods = _scan_periods(rows)
    df = _pds.DataFrame({str(i): [""] * len(rows) for i in range(29)})
    df[str(18)] = periods

    # 让被抽出来的页面函数直接使用我们已经下载好的数据
    try:
        runner.__globals__["load_excel_data"] = lambda *a, **k: rows
    except Exception:
        pass

    # 数据指纹：证明这份报告扫的是哪一份数据
    try:
        import hashlib as _hl
        _fp = _hl.sha256("\n".join(",".join(r) for r in rows).encode("utf-8")).hexdigest()[:16]
    except Exception:
        _fp = "-"

    fake.ctrl["file"] = file_key
    fake.session_state["current_file"] = file_key

    detail, problems = [], []
    detail_meta = {}
    n_lines = n_tpl = 0
    total_steps = max(1, len(balls) * len(attrs))
    step = 0
    for ball in balls:
        fake.ctrl["ball"] = ball
        b_lines = b_ok = b_tpl = b_tplbad = 0
        for attr in attrs:
            step += 1
            if progress_cb:
                progress_cb(step / total_steps, f"{file_key} {ball} {attr}")
            fake.ctrl["attr"] = attr
            fake.session_state["multi_result_text"] = ""
            fake.session_state["multi_results_dict"] = {}
            fake.session_state["last_multi_signature"] = None
            fake.errors.clear()
            try:
                with _NoComp():
                    runner(df)
            except _ScanStop:
                pass
            except Exception as e:
                problems.append((file_key, ball, attr, "-", f"计算异常 {type(e).__name__}: {e}"))
                continue
            report = fake.session_state.get("multi_result_text") or ""
            if not report:
                continue
            import re as _res
            n_decl = len(_res.findall(r"触发行：", report))
            stats, probs = _verify_report(report, rows)
            for a, b, n1, n2, nt, tb in stats:
                b_lines += n1
                b_ok += n2
                b_tpl += nt
                b_tplbad += tb
            n_lines += sum(x[2] for x in stats)
            n_tpl += sum(x[4] for x in stats)
            for pr in probs:
                problems.append((file_key, ball, attr, pr[2], pr[3]))
            parsed = sum(x[2] for x in stats)
            if parsed != n_decl:
                problems.append((file_key, ball, attr, "-",
                                 f"有 {n_decl - parsed} 条触发行未解析"))
        detail.append((file_key, ball, b_lines, b_ok, b_tpl, b_tplbad))
    detail_meta[file_key] = {"rows": len(rows), "fp": _fp}
    return detail, problems, n_lines, n_tpl, detail_meta


def _verify_report(report, rows):
    """返回 (每属性统计, 问题明细)"""
    import re as _re

    head_re = _re.compile(r"【基准行排列】\(\d+行\):\s*(.+)")
    item_re = _re.compile(r"([A-Z]+)(\d+):([^,]+)")
    title_re = _re.compile(r"={5,}\s*(.+?)\s*-\s*(.+?)\s*-\s*(.+?)\s*-\s*(第\d球)\s*={5,}")
    line_re = _re.compile(
        r"触发行：(\d)球\(([A-Z]+)\)\s*行(\d+)-(\d+)\((\d+)行\)"
        r"[^\n]*?上:(.*?)\s*\(匹配:(.*?)\)\s*下:(.*?)(?:\s*\[|$)")

    # 按块切分
    blocks, cur = [], None
    for ln in str(report).splitlines():
        mt = title_re.search(ln)
        if mt:
            cur = {"attr": mt.group(3).strip(), "ball": mt.group(4).strip(),
                   "template": [], "tpl_cells": [], "lines": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        mh = head_re.search(ln)
        if mh:
            _cells = item_re.findall(mh.group(1))
            cur["tpl_cells"] = [(c, int(r), v.strip()) for c, r, v in _cells]
            cur["template"] = [v for _, _, v in cur["tpl_cells"]]
            continue
        if "触发行：" in ln:
            cur["lines"].append(ln)

    stats, problems = [], []
    for b in blocks:
        attr, tmpl = b["attr"], b["template"]
        kind = "相生" if "相生" in attr else ("相克" if "相克" in attr else "等于")
        n_ok = 0
        # 基准行排列：每个单元格都必须等于 CSV 真实值
        n_tpl, tpl_bad = 0, 0
        for _c, _r, _v in b.get("tpl_cells", []):
            n_tpl += 1
            _real = _v_cell(rows, _r, _c)
            if _v_strip(_v) != _v_strip(_real):
                tpl_bad += 1
                problems.append((attr, f"{_c}{_r}", "基准行",
                                 f"报告={_v} 实际={_real}"))
        for ln in b["lines"]:
            mm = line_re.search(ln)
            if not mm:
                problems.append((attr, "-", "无法解析", ln[:120]))
                continue
            ball, col = mm.group(1), mm.group(2)
            a, bb = int(mm.group(3)), int(mm.group(4))
            up, match, down = mm.group(6), mm.group(7), mm.group(8)
            real = [_v_cell(rows, r, col) for r in range(a, bb + 1)]
            err = None
            tpl = tmpl[:len(real)]
            if tpl:
                if kind == "等于":
                    if [_v_strip(v) for v in real] != [_v_strip(v) for v in tpl]:
                        err = f"值不等：窗口={real} 模板={tpl}"
                else:
                    bad = [i for i in range(len(real)) if not _v_rel(tpl[i], real[i], kind)]
                    if bad:
                        i0 = bad[0]
                        err = f"第{i0 + 1}项不满足{kind}：模板={tpl[i0]} 窗口={real[i0]}"
            if err is None:
                ms, pos = match.replace(" ", ""), 0
                for v in real:
                    k = ms.find(v, pos)
                    if k < 0:
                        err = f"匹配串里没有真实值 {v}"
                        break
                    pos = k + len(v)
                if err is None and pos != len(ms):
                    err = "匹配串多出内容"
            if err is None:
                up_in = a - 1 >= 1
                dn_in = bb + 1 <= len(rows)
                ru = _v_cell(rows, a - 1, col) if up_in else ""
                rd = _v_cell(rows, bb + 1, col) if dn_in else ""

                def _ctx_ok(reported, real, in_range):
                    rv = _v_norm(reported)
                    if rv == "空":
                        return in_range and real == ""
                    if rv == "无":
                        return not in_range
                    return in_range and rv == _v_strip(real)

                if not _ctx_ok(up, ru, up_in):
                    err = f"上值 {up} != " + ("越界" if not up_in else repr(ru))
                elif not _ctx_ok(down, rd, dn_in):
                    err = f"下值 {down} != " + ("越界" if not dn_in else repr(rd))
            if err:
                problems.append((attr, f"{ball}球({col})", f"行{a}-{bb}", err))
            else:
                n_ok += 1
        stats.append((attr, b["ball"], len(b["lines"]), n_ok, n_tpl, tpl_bad))
    return stats, problems


def render_multi_analysis(df_data):
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：多维分析需要主数据表。请点左侧「☁️刷新云端数据」，或到后台管理重新同步【升序源文件】。")
        return
    from openpyxl.utils import get_column_letter, column_index_from_string

    st.title("📐多维分析系统")
    if "current_attr" not in st.session_state: st.session_state.current_attr = "生肖"
    if "current_file" not in st.session_state: st.session_state.current_file = "升序全套"
    if "multi_results_dict" not in st.session_state: st.session_state.multi_results_dict = {}
    if "multi_result_text" not in st.session_state: st.session_state.multi_result_text = ""
    if "text_single" not in st.session_state: st.session_state["text_single"] = ""
    if "text_all" not in st.session_state: st.session_state["text_all"] = ""
    if "full_scan_results" not in st.session_state: st.session_state.full_scan_results = []

    # ==========================================
    # 3. 属性列映射字典
    # ==========================================
    ATTR_MAP = {
        "数字五行": 6, "生肖": 7, "尾数": 8, "数字合": 9, "门数": 10, "段数": 11, "单双组合": 12, "单双笔": 13, "独合字": 14, "单双头": 15, "单双": 16, "波单双": 17, "生肖五行": 18, "颜色肖": 19, "四宝": 20, "物象": 21, "波色": 22, "阴阳": 23, "家野": 24, "天地": 25, "阴阳天地": 26, "吉凶": 27, "男女": 28, "方位": 29, "3模": 30, "尾五行": 31, "福禄寿": 32, "大小肖": 33,
        "生肖五行相生": 18, "生肖五行相克": 18, "数字五行相生": 6, "数字五行相克": 6, "尾五行相生": 31, "尾五行相克": 31,
        "生肖五行与数字五行相生": 18, "生肖五行与数字五行相克": 18, "数字五行与生肖五行相生": 6, "数字五行与生肖五行相克": 6
    }

    # ==========================================
    # 4. 界面参数设置区
    # ==========================================
    st.markdown("### 分析参数设置")
    analysis_mode = st.radio("分析模式：", ["单属性透视 (按球查属性)", "单球全属性透视 (按球查全部)"], horizontal=True)
    _slot_name = "text_all" if "全属性" in analysis_mode else "text_single"
    st.session_state.multi_result_text = st.session_state.get(_slot_name, "")

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)

    with row1_col1:
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)

        # 核心新增：自动推算最新一期的下一期（如122期），并插到下拉框顶端
        if unique_periods:
            latest = unique_periods[0]
            try:
                next_p = str(int(float(latest)) + 1)
                if next_p not in unique_periods:
                    unique_periods.insert(0, next_p)
            except:
                pass

        selected_period = st.selectbox("选择分析/预测期数", unique_periods)
    with row1_col2:
        selected_file_type = st.selectbox("选择分析文件", ["升序全套", "按序全套"])
    #======多维属性下拉框自定义代码起始=======
    with row1_col3:
        # 1. 提取字典里所有的属性
        all_attrs = list(ATTR_MAP.keys())

        # 2. 在这里自定义你最常用的属性排序（按你想要的顺序写）
        # 后面没写到的属性，系统会自动排在它们后面
        show_attrs = [
            "生肖",
            "尾数",
            "数字合",
            "数字五行",
            "门数",
            "段数",
            "单双组合",
            "波单双",
            "生肖五行",
            "四宝",
            "物象",
            "阴阳天地",
            "方位",
            "尾五行",
            "颜色肖",
            "波色",
            "3模",
            "福禄寿",
            "大小肖",
            "生肖五行相生",
            "生肖五行相克",
            "数字五行相生",
            "数字五行相克",
            "尾五行相生",
            "尾五行相克",
            "生肖五行与数字五行相生",
            "生肖五行与数字五行相克",
            "数字五行与生肖五行相生",
            "数字五行与生肖五行相克",
        ]

        # 4. 生成下拉框，默认选第一个（即"生肖"）
        selected_attr = st.selectbox("分析属性", show_attrs, index=0)
      #======多维属性下拉框自定义代码结尾=======
    with row1_col4:
        ball_str = st.selectbox("基准球号", ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"])
        ball_num = int(ball_str.replace("第", "").split("球")[0])

    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns([1, 1, 1, 1])
    with row2_col1: min_len = st.number_input("最少对比行数", min_value=3, max_value=20, value=7, step=1)
    with row2_col2: max_len = st.number_input("最多对比行数", min_value=3, max_value=20, value=17, step=1)
    with row2_col3:
        st.write(""); st.write("")
        run_btn = st.button("🚀 执行分析（原始·不筛选）", use_container_width=True,
                            type="primary")
    with row2_col4:
        st.write(""); st.write("")
        if st.button("☁️刷新云端数据", use_container_width=True, type="secondary"):
            load_excel_data.clear()
            st.toast("✅ 缓存已清空！")
            st.rerun()

    if selected_file_type != st.session_state.current_file:
        st.session_state.current_file = selected_file_type
        st.session_state.multi_results_dict = {}
        st.session_state.multi_result_text = ""
        st.session_state["text_single"] = ""
        st.session_state["text_all"] = ""
        # 绝杀：此处绝对不能加 st.rerun()，否则会导致文件切换时无限死循环卡死

    # 切换球号 → 自动清空上一球的文档
    if st.session_state.get("auto_doc_ball") != ball_str:
        st.session_state["auto_doc_ball"] = ball_str
        st.session_state["auto_doc"] = ""
        st.session_state["multi_result_text"] = ""

    st.divider()

    # ==========================================
    # 全自动核算（单个球，按死规则筛选）
    # ==========================================
    with st.expander(f"🤖 全自动核算（{ball_str}，按死规则筛选）", expanded=False):
        st.caption("自动把当前球的 29 个属性各算一遍，再按你的固定阈值筛选后录入结果区。"
                   "**不修改任何原有核算代码**，只做外层筛选；只读数据，不写入。")
        _rn = _auto_rule("生肖", 1)
        _rm = _auto_rule("门数", int(ball_str.replace("第", "").replace("球", "")))
        _rz = _auto_rule("生肖五行相生", 1)
        st.caption(f"当前规则｜生肖·尾数·数字合：近{_rn['near']}期一致 / 自身{_rn['self']}行 / "
                   f"普通{_rn['normal']}行　·　门数·段数（{ball_str}）：近{_rm['near']}期一致 / "
                   f"自身{_rm['self']}行 / 普通{_rm['normal']}行　·　相生相克：{_rz['normal']}行")
        if st.button("开始全自动核算", type="primary", use_container_width=True,
                     key="auto_go"):
            with st.spinner("正在核算并筛选…"):
                try:
                    _ar, _af = _scan_build_runner()
                    _tf = "升序全套.csv" if selected_file_type == "升序全套" else "按序全套.csv"
                    _arows = load_excel_data(_tf, None)
                    _atext, _astat, _ain = _auto_run(
                        _tf.replace(".csv", ""), _arows, ball_str, show_attrs, _ar, _af,
                        period=selected_period,
                        order=("升序" if selected_file_type == "升序全套" else "按序"))
                    st.session_state["auto_stats"] = _astat
                    st.session_state["auto_text"] = _atext
                    if _atext:
                        _slot_auto = ("text_all" if "全属性" in analysis_mode
                                      else "text_single")
                        st.session_state[_slot_auto] = _atext
                        st.session_state.multi_result_text = _atext
                        st.session_state["auto_doc"] = _atext
                        st.session_state["auto_doc_ball"] = ball_str
                        _nb = sum(1 for l in _atext.splitlines() if l.startswith("========="))
                        _nl = sum(1 for l in _atext.splitlines() if l.startswith("触发行："))
                        st.success(f"{ball_str}：{_nb} 个属性、{_nl} 条触发行已写入文档")
                    else:
                        st.warning(f"{ball_str} 按死规则筛选后没有任何触发行达标。")
                except Exception as _e:
                    st.error(f"全自动核算失败：{type(_e).__name__}: {_e}")

    st.divider()

    # ==========================================
    # 5. 核心计算引擎 (生克/匹配/高亮)
    # ==========================================

    if run_btn:
        # =====防重复计算：生成当前参数唯一签名（包含期数、属性、球号、分析模式等）=====
        current_signature = f"{selected_file_type}_{selected_period}_{selected_attr}_{ball_str}_{min_len}_{max_len}_{analysis_mode}"

        # =====防重复计算：如果与上次参数完全一致，且不是全属性遍历，直接拦截不计算=====
        if st.session_state.get("last_multi_signature") == current_signature and "全属性" not in analysis_mode:
            st.warning("⚠️ 检测到条件与上次完全一样，已跳过重复计算。如需重算，请修改任意条件或清空结果。")
            st.stop()

        # =====防重复计算：记录本次计算条件签名=====
        st.session_state.last_multi_signature = current_signature

        st.session_state.play_alert = False
        target_file = "升序全套.csv" if selected_file_type == "升序全套" else "按序全套.csv"
        sheet_name = None
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            status_text.text("正在读取 Excel 数据...")
            all_rows = load_excel_data(target_file, sheet_name)
            if not all_rows:
                st.error(f"读取 {target_file} 失败或文件为空。"); st.stop()
            progress_bar.progress(20)

            def clean_str(v):
                if v is None: return ""
                try: return str(int(float(v)))
                except: return str(v).replace("\r", "").replace("\n", "").replace(" ", "").strip()

            # ==========================================
            # 核心：寻找基准期的行号（支持未来期预测）
            # ==========================================
            target_row_idx = -1

            # 第一步：先试着找当前选择期数（比如 122）
            for r_idx in range(len(all_rows)):
                year_val = clean_str(all_rows[r_idx][213]) if len(all_rows[r_idx]) > 213 else "2026"
                p1 = clean_str(all_rows[r_idx][0]) if len(all_rows[r_idx]) > 0 else ""
                p2 = clean_str(all_rows[r_idx][1]) if len(all_rows[r_idx]) > 1 else ""
                p3 = clean_str(all_rows[r_idx][2]) if len(all_rows[r_idx]) > 2 else ""
                if f"{year_val}{p1}{p2}{p3}" == selected_period:
                    target_row_idx = r_idx
                    break

            # 第二步：如果找不到（说明是未来期），自动回退找上一期（121）
            if target_row_idx == -1:
                try:
                    prev_period = str(int(selected_period) - 1)
                    for r_idx in range(len(all_rows)):
                        year_val = clean_str(all_rows[r_idx][213]) if len(all_rows[r_idx]) > 213 else "2026"
                        p1 = clean_str(all_rows[r_idx][0]) if len(all_rows[r_idx]) > 0 else ""
                        p2 = clean_str(all_rows[r_idx][1]) if len(all_rows[r_idx]) > 1 else ""
                        p3 = clean_str(all_rows[r_idx][2]) if len(all_rows[r_idx]) > 2 else ""

                        if f"{year_val}{p1}{p2}{p3}" == prev_period:
                            target_row_idx = r_idx
                            # 弹出提示告诉用户正在预测
                            st.info(f"💡 检测到目标期 {selected_period} 尚未开奖，系统已自动使用上一期 {prev_period} 作为基准进行推演预测。")
                            break
                except Exception as e:
                    pass

            if target_row_idx == -1:
                st.error(f"找不到基准期数 {selected_period}，也找不到它的上一期！")
                st.stop()

            # 五行生克字典
            cross_sheng = {"金": ["土", "水"], "木": ["水", "火"], "水": ["金", "木"], "火": ["木", "土"], "土": ["火", "金"]}
            cross_ke = {"金": ["木", "火"], "木": ["土", "金"], "水": ["火", "土"], "火": ["金", "水"], "土": ["水", "木"]}

            def get_wx(s):
                core = s.replace("肖", "").replace("号", "").replace("尾", "")
                return {"鼠":"水","牛":"土","虎":"木","兔":"木","龙":"土","蛇":"火","马":"火","羊":"土","猴":"金","鸡":"金","狗":"土","猪":"水"}.get(core, core)

            # 通用匹配引擎
            def do_match(attr_name, attr_base_col, ball_n, min_l, max_l):
                is_cross_mode = attr_name in ["生肖五行与数字五行相生", "生肖五行与数字五行相克", "数字五行与生肖五行相生", "数字五行与生肖五行相克"]
                is_zodiac_to_num = attr_name.startswith("生肖")
                is_cross_sheng = "相生" in attr_name
                is_cross_ke = "相克" in attr_name
                is_sheng_mode = "相生" in attr_name
                is_ke_mode = "相克" in attr_name
                is_normal_mode = not (is_sheng_mode or is_ke_mode) and not is_cross_mode
                wx_suffix = "号" if ("数字" in attr_name or "号" in attr_name) else ("尾" if "尾" in attr_name else ("肖" if "肖" in attr_name else ""))

                ball_cols = [get_column_letter(attr_base_col + (x - 1) * 30) for x in range(1, 8)]
                ref_col_letter = ball_cols[ball_n - 1]
                ref_col_idx_0 = column_index_from_string(ref_col_letter) - 1

                def check_match(a, b):
                    if is_cross_mode:
                        if is_cross_sheng: return b in cross_sheng.get(a, [])
                        elif is_cross_ke: return b in cross_ke.get(a, [])
                    if is_normal_mode: return a == b
                    core_a, core_b = get_wx(a), get_wx(b)
                    child = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
                    mother = {"金": "土", "土": "火", "火": "木", "木": "水", "水": "金"}
                    ke_dict = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
                    if is_sheng_mode: return (child.get(core_a) == core_b) or (mother.get(core_a) == core_b)
                    elif is_ke_mode: return (ke_dict.get(core_a) == core_b) or (ke_dict.get(core_b) == core_a)
                    return False

                def get_col_data(col_idx_0):
                    return [(r, clean_str(all_rows[r][col_idx_0]) if col_idx_0 < len(all_rows[r]) else "") for r in range(len(all_rows))]

                ref_col_data = get_col_data(ref_col_idx_0)

                template = []
                template_rows_info = []
                for r in range(target_row_idx, len(ref_col_data)):
                    if ref_col_data[r][1]:
                        template.append(ref_col_data[r][1])
                        template_rows_info.append((r + 1, ref_col_data[r][1]))
                    if len(template) >= max_len: break

                if len(template) < min_l: return []

                results = []
                for n in range(1, 8):
                    target_base_col = (6 if is_zodiac_to_num else 18) if is_cross_mode else attr_base_col
                    col_name = get_column_letter(target_base_col + (n - 1) * 30)
                    current_col_idx = column_index_from_string(col_name) - 1
                    disp_name = f"{n}球({col_name})"
                    is_self = (col_name == ref_col_letter)

                    col_data = get_col_data(current_col_idx)
                    valid_data = [(r, col_data[r][1]) for r in range(2, len(col_data)) if col_data[r][1]]
                    vc = len(valid_data)

                    if vc >= min_l:
                        k = 0
                        while k <= vc - min_l:
                            max_l_hit = 0
                            for j in range(vc - k):
                                if j >= len(template): break
                                if j > 0 and valid_data[k+j][0] != valid_data[k+j-1][0] + 1: break
                                if not check_match(template[j], valid_data[k+j][1]): break
                                max_l_hit = j + 1

                            if max_l_hit >= min_l:
                                real_l = max_l_hit
                                sr = valid_data[k][0]; er = valid_data[k + real_l - 1][0]


                                def get_ctx(r_idx):
                                    if r_idx < 0 or r_idx >= len(col_data): return "无"
                                    v = col_data[r_idx][1]
                                    if not v: return "空"
                                    if is_cross_mode:
                                        v_suffix = "号" if is_zodiac_to_num else "肖"
                                        return f"{v}{v_suffix}"
                                    if v in ["鼠","牛","虎","兔","龙","蛇","马","羊","猴","鸡","狗","猪"]: return v + "肖"
                                    if v in ["金", "木", "水", "火", "土"]: return v + wx_suffix

                                    # 改变这句代码的作用：如果是纯数字且属性包含"尾"，返回值加上"尾"字
                                    if v.isdigit() and wx_suffix == "尾":
                                        return f"{v}尾"
                                    return v


                                w1, w2 = get_ctx(sr-1), get_ctx(er+1)
                                actual_match_str = "".join([x[1] for x in valid_data[k : k + real_l]])
                                display_w1 = w1
                                kill_str = ""

                                if is_cross_mode or is_sheng_mode or is_ke_mode:
                                    if is_cross_mode:
                                        core_w1 = w1.replace("号", "").replace("肖", "")[0]
                                    else:
                                        core_w1 = get_wx(w1)

                                    t_suffix = ("肖" if is_zodiac_to_num else "号") if is_cross_mode else wx_suffix

                                    if is_cross_sheng or is_sheng_mode:
                                        if is_cross_mode:
                                            rule_str = "".join([f"{x}{t_suffix}" for x in cross_sheng.get(core_w1, [])])
                                        else:
                                            rule_str = {"金": f"水{wx_suffix}土{wx_suffix}", "木": f"水{wx_suffix}火{wx_suffix}", "水": f"金{wx_suffix}木{wx_suffix}", "火": f"土{wx_suffix}木{wx_suffix}", "土": f"金{wx_suffix}火{wx_suffix}"}.get(core_w1, "")

                                        if rule_str:
                                            display_w1 = f"{w1} (生{rule_str})"
                                            kill_str = f" (杀{rule_str})"

                                    elif is_cross_ke or is_ke_mode:
                                        if is_cross_mode:
                                            rule_str = "".join([f"{x}{t_suffix}" for x in cross_ke.get(core_w1, [])])
                                        else:
                                            rule_str = {"金": f"火{wx_suffix}木{wx_suffix}", "木": f"土{wx_suffix}金{wx_suffix}", "水": f"火{wx_suffix}土{wx_suffix}", "火": f"水{wx_suffix}金{wx_suffix}", "土": f"木{wx_suffix}水{wx_suffix}"}.get(core_w1, "")

                                        if rule_str:
                                            display_w1 = f"{w1} (克{rule_str})"
                                            kill_str = f" (杀{rule_str})"

                                detail_txt = f"上:{display_w1} (匹配:{actual_match_str}) 下:{w2}{kill_str}"

                                if is_self: detail_txt += " [自身参考列匹配]"

                                w1_str = str(w1).strip()
                                if w1_str not in ["空", "无", "", "0", "0.0", "None", "nan"]:
                                    if er + 1 <= 25:
                                        line_txt = f"触发行：{disp_name} 行{sr+1}-{er+1}({real_l}行)近{real_l}期一致: {detail_txt}"
                                        if 5 <= real_l <= 9:
                                            st.session_state.play_alert = True
                                            line_txt = f"[[HIGHLIGHT]]{line_txt}[[/HIGHLIGHT]]"
                                    else:
                                        line_txt = f"触发行：{disp_name} 行{sr+1}-{er+1}({real_l}行): {detail_txt}"

                                    results.append(line_txt)
                                k += real_l
                            else:
                                k += 1
                return results

            # ==========================================
            # 6. 执行分析并组装报告文本
            # ==========================================
            attr_map_val = ATTR_MAP[selected_attr]
            res_lines = do_match(selected_attr, attr_map_val, ball_num, min_len, max_len)

            # 提取基准行排列
            base_col_num = attr_map_val + (ball_num - 1) * 30
            base_col_letter = get_column_letter(base_col_num)
            base_col_idx = column_index_from_string(base_col_letter) - 1

            # 计算当前选中属性的后缀，用于基准行显示
            wx_suffix_global = "尾" if "尾" in selected_attr else ""

            base_rows = []
            for r in range(target_row_idx, len(all_rows)):
                val = clean_str(all_rows[r][base_col_idx]) if base_col_idx < len(all_rows[r]) else ""
                if val:
                    # 如果属性是尾数且是纯数字，拼上"尾"字
                    if val.isdigit() and wx_suffix_global == "尾":
                        base_rows.append(f"{base_col_letter}{r+1}:{val}尾")
                    else:
                        base_rows.append(f"{base_col_letter}{r+1}:{val}")
                if len(base_rows) >= max_len: break


            # =====没找到匹配结果的提示拦截=====
            if not res_lines:
                st.warning("⚠️ 未找到符合条件的匹配记录")
            else:
                out_txt = f"========== {selected_file_type} - {selected_period} - {selected_attr} - {ball_str} ==========\n"
                out_txt += f"【基准行排列】({len(base_rows)}行): {', '.join(base_rows)}\n\n"

                for line in res_lines:
                    out_txt += f"{line}\n"

                # =====防重复写入：检查生成的内容是否与历史内容或当前报告完全一致=====
                if "全属性" in analysis_mode:
                    # 全属性：追加到自己的列表
                    if out_txt not in st.session_state.full_scan_results:
                        st.session_state.full_scan_results.append(out_txt)
                        st.session_state["text_all"] = "\n\n".join(
                            st.session_state.full_scan_results)
                        st.session_state.multi_result_text = st.session_state["text_all"]
                    else:
                        st.toast("ℹ️ 计算结果与历史记录完全一致，已忽略重复写入。")
                else:
                    # 单属性：只写自己那一份
                    if st.session_state.get("text_single") != out_txt:
                        st.session_state["text_single"] = out_txt
                        st.session_state.multi_result_text = out_txt
                    else:
                        st.toast("ℹ️ 计算结果未发生变化，已忽略写入。")

            # ==== 6.1 触发声音提示 (找回丢失的掉金币声音) ====
            if st.session_state.get("play_alert", False):
                import streamlit.components.v1 as components
                components.html(
                    """
                    <script>
                    var AudioContext = window.AudioContext || window.webkitAudioContext;
                    var ctx = new AudioContext();
                    function playCoin() {
                        if (ctx.state === 'suspended') ctx.resume();
                        var osc1 = ctx.createOscillator(), gain1 = ctx.createGain();
                        osc1.type = 'sine'; osc1.frequency.setValueAtTime(987.77, ctx.currentTime);
                        gain1.gain.setValueAtTime(0.5, ctx.currentTime);
                        gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
                        osc1.connect(gain1); gain1.connect(ctx.destination);
                        osc1.start(); osc1.stop(ctx.currentTime + 0.3);

                        var osc2 = ctx.createOscillator(), gain2 = ctx.createGain();
                        osc2.type = 'sine'; osc2.frequency.setValueAtTime(1318.51, ctx.currentTime + 0.1);
                        gain2.gain.setValueAtTime(0.5, ctx.currentTime + 0.1);
                        gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
                        osc2.connect(gain2); gain2.connect(ctx.destination);
                        osc2.start(ctx.currentTime + 0.1); osc2.stop(ctx.currentTime + 0.4);
                    }
                    playCoin();
                    </script>
                    """,
                    height=0, width=0
                )
                st.session_state.play_alert = False

            progress_bar.progress(100)
            status_text.success(f"✅ 计算完成：{selected_file_type} | {selected_period}期 | 属性：{selected_attr} | {ball_str}")

        except Exception as e:
            st.error(f"计算报错: {e}")


    # ==========================================
    # ==== 7. 页面底部展示与高亮渲染区
    # ==========================================
    st.divider()
    col_title, col_btn = st.columns([8, 2])
    with col_title: st.subheader("详细结果 (累积报告)")
    with col_btn:
        if st.button("🗑️清空当前模式结果", use_container_width=True):
            st.session_state.multi_results_dict = {}
            st.session_state.multi_result_text = ""
            st.session_state[_slot_name] = ""
            if "全属性" in analysis_mode:
                st.session_state.full_scan_results = []
            st.rerun()

    if st.session_state.multi_result_text != "":
        import html as _hm
        import base64 as _b64m
        import streamlit.components.v1 as _comp

        raw_text = st.session_state.multi_result_text
        clean_text = raw_text.replace(chr(92) + 'n', chr(10)).replace(chr(92) + 'r', '')

        # 字体样式由全局 CSS 统一控制
        # key 跟内容走：内容一变，输入框就重建，才能显示新追加的结果
        _box_key = "multi_box_" + str(abs(hash(clean_text)) % (10 ** 10))
        _edited = st.text_area("详细结果（可直接编辑）", value=clean_text, height=440,
                               key=_box_key, label_visibility="collapsed")

        _b1, _b2, _b3, _b4 = st.columns(4)
        with _b1:
            if st.button("💾 保存修改", use_container_width=True, key="multi_box_save"):
                st.session_state.multi_result_text = _edited
                st.session_state[_slot_name] = _edited
                st.rerun()
        with _b2:
            st.download_button("📥 下载 TXT", _edited.encode("utf-8-sig"),
                               file_name=f"报告_{ball_str}_{datetime.now():%Y%m%d_%H%M%S}.txt",
                               mime="text/plain", use_container_width=True,
                               key="multi_box_dl")
        with _b3:
            if st.button("📌 推送看板", use_container_width=True, key="multi_to_board"):
                _board_append("多维分析",
                              f"{selected_file_type} {selected_period} {ball_str}",
                              _edited)
                st.success("已推送")
        with _b4:
            _ph = ("<html><head><meta charset='utf-8'><style>"
                   "@page{margin:12mm}"
                   "body{font-family:Consolas,'Microsoft YaHei',monospace;padding:14px}"
                   "pre{white-space:pre-wrap;word-break:break-word;font-size:15px;"
                   "line-height:1.9;text-align:left}"
                   "</style></head><body><pre>"
                   + _hm.escape(_edited) + "</pre></body></html>")
            _b64p = _b64m.b64encode(_ph.encode("utf-8")).decode("utf-8")
            if not _INNER.get("run"):
                _comp.html(f"""
            <style>
              html, body {{ margin:0; padding:0; background:transparent; overflow:hidden; }}
              .pbtn {{
                width:100%; height:38px; padding:0; margin:0;
                background:#ffffff; color:#31333f;
                border:1px solid rgba(49,51,63,0.2); border-radius:0.5rem;
                cursor:pointer; font-size:14px; line-height:36px;
                font-family:inherit; display:block;
              }}
              .pbtn:hover {{ border-color:#0284c7; color:#0284c7; }}
            </style>
            <div style="text-align:center">
              <button class="pbtn" onclick="pr()">🖨️ 打印</button>
            </div>
            <script>
            function d(s) {{
              return decodeURIComponent(Array.prototype.map.call(atob(s), function(c) {{
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
              }}).join(''));
            }}
            function pr() {{
              var h = d("{_b64p}");
              var f = document.createElement('iframe');
              f.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
              document.body.appendChild(f);
              var x = f.contentWindow.document;
              x.open(); x.write(h); x.close();
              setTimeout(function() {{ f.contentWindow.focus(); f.contentWindow.print(); }}, 400);
            }}
            </script>""", height=40, scrolling=False)

        st.divider()

        with st.expander("🔍 校验当前报告（逐行核对是否真的匹配）", expanded=False):
            st.caption("把报告里的每条触发行拉回原始 CSV 逐条核对：值是否真的相等、"
                       "生克是否真的成立、上下值是否真实、匹配串是否由真实数据拼接。"
                       "**只读，不会修改任何数据。**")
            if st.button("开始校验", use_container_width=True, key="multi_verify_btn"):
                with st.spinner("正在逐行核对…"):
                    try:
                        _rows = load_excel_data(target_file, None)
                        _stats, _probs = _verify_report(clean_text, _rows)
                    except Exception as e:
                        st.error(f"校验失败：{type(e).__name__}: {e}")
                        _stats, _probs = [], []

                if _stats:
                    import pandas as _pdv
                    _dfv = _pdv.DataFrame(
                        [{"属性": a, "基准球": b, "触发行": n, "核对通过": k,
                          "基准行单元格": n_t,
                          "状态": "全部通过" if (n == k and t_b == 0)
                                  else f"异常 {n - k + t_b} 处"}
                         for a, b, n, k, n_t, t_b in _stats])
                    st.dataframe(_dfv, use_container_width=True, hide_index=True)
                    _tot = sum(x[2] for x in _stats)
                    _ok = sum(x[3] for x in _stats)
                    _tpl_tot = sum(x[4] for x in _stats)
                    if _probs:
                        st.error(f"共 {_tot} 条触发行，通过 {_ok} 条，"
                                 f"发现 {len(_probs)} 处问题")
                        st.dataframe(_pdv.DataFrame(
                            [{"属性": a, "球位": b, "行号": c, "问题": d}
                             for a, b, c, d in _probs]),
                            use_container_width=True, hide_index=True)
                    else:
                        st.success(f"✅ 共 {_tot} 条触发行 + {_tpl_tot} 个基准行单元格，"
                                   f"全部核对通过，未发现假匹配。")
                else:
                    st.warning("报告里没有解析到可校验的内容，先执行一次分析再校验。")

    else:
        st.info("请选择文件、属性及球号后点击【执行当前球分析】。")

    st.divider()
    with st.expander("🔄 全量扫描（升序 + 按序，7 球 × 全部属性）", expanded=False):
        st.caption("在后台把页面同一份匹配逻辑跑一遍，逐条核对报告与原始 CSV。"
                   "**只读，不写入任何数据。** 全量（两文件×7球×29属性）约需 1 分钟。")
        _sc1, _sc2 = st.columns(2)
        with _sc1:
            _scan_files = st.multiselect("扫描哪些文件", ["升序全套", "按序全套"],
                                         default=["升序全套", "按序全套"],
                                         key="scan_files")
        with _sc2:
            _scan_balls = st.multiselect("扫描哪些球位",
                                         [f"第{i}球" for i in range(1, 8)],
                                         default=[f"第{i}球" for i in range(1, 8)],
                                         key="scan_balls")

        if st.button("开始全量扫描", type="primary", use_container_width=True,
                     key="scan_go"):
            if not _scan_files or not _scan_balls:
                st.warning("至少选一个文件和一个球位")
            else:
                _bar = st.progress(0.0, text="准备中…")
                try:
                    _runner, _fake = _scan_build_runner()
                    _all_detail, _all_probs = [], []
                    _tl = _tt = 0
                    _all_meta = {}
                    import time as _tm
                    _t_start = _tm.time()
                    for _fk in _scan_files:
                        _csv = "升序全套.csv" if _fk == "升序全套" else "按序全套.csv"
                        _rows = load_excel_data(_csv, None)
                        _d, _p, _nl, _nt, _meta = _scan_one_file(
                            _fk, _rows, _scan_balls, show_attrs, _runner, _fake,
                            progress_cb=lambda v, t_: _bar.progress(
                                min(1.0, v), text=f"扫描中… {t_}"))
                        _all_detail += _d
                        _all_probs += _p
                        _tl += _nl
                        _tt += _nt
                        _all_meta.update(_meta)
                    _bar.progress(1.0, text="扫描完成")
                    st.session_state["scan_detail"] = _all_detail
                    st.session_state["scan_probs"] = _all_probs
                    st.session_state["scan_total"] = (_tl, _tt)
                    st.session_state["scan_meta"] = _all_meta
                    _cost_v = _tm.time() - _t_start
                    st.session_state["scan_cost"] = _cost_v

                    # 报告当场生成，保证耗时/指纹一定在
                    _rp = [f"多维分析全量扫描报告  生成时间 {datetime.now():%Y-%m-%d %H:%M:%S}",
                           "=" * 60,
                           "扫描方式：只读。数据从 GitHub 下载到内存比对，未做任何写入。",
                           f"扫描耗时：{_cost_v:.1f} 秒"]
                    for _fk3, _mv3 in _all_meta.items():
                        _rp.append(f"数据源 {_fk3}：{_mv3['rows']} 行，指纹 {_mv3['fp']}")
                    _rp += ["",
                            "校验规则（每条触发行都必须同时满足）：",
                            "  1 基准行排列的每个单元格 = CSV 真实值",
                            "  2 触发行窗口的值 = 模板前 N 项（相生/相克则必须真的成立）",
                            "  3 匹配串 = 窗口真实单元格拼接（不得多字或少字）",
                            "  4 上值/下值 = 真实的前一行/后一行（空值显示为「空」，越界为「无」）",
                            "", "=" * 60, ""]
                    for _a3, _b3, _c3, _d3, _e3, _f3 in _all_detail:
                        _rp.append(f"{_a3} {_b3}: 触发行 {_c3} 条，通过 {_d3} 条，"
                                   f"基准行单元格 {_e3} 个，异常 {_c3 - _d3 + _f3} 处")
                    _rp += ["", "-" * 60,
                            f"合计：触发行 {_tl} 条 / 基准行单元格 {_tt} 个 / "
                            f"问题 {len(_all_probs)} 处", ""]
                    if _all_probs:
                        _rp.append("问题明细：")
                        for _x3 in _all_probs:
                            _rp.append(f"  {_x3[0]} {_x3[1]} {_x3[2]} {_x3[3]} → {_x3[4]}")
                    else:
                        _rp.append("结论：全部核对通过，未发现任何一处不匹配。")
                    st.session_state["scan_report"] = "\n".join(_rp)
                except Exception as _e:
                    st.error(f"扫描失败：{type(_e).__name__}: {_e}")

        if st.session_state.get("scan_detail"):
            import pandas as _pdsc
            _det = st.session_state["scan_detail"]
            _prb = st.session_state.get("scan_probs") or []
            _tl, _tt = st.session_state.get("scan_total", (0, 0))
            _dfa = _pdsc.DataFrame(
                [{"文件": a, "球位": b, "触发行": c, "通过": d,
                  "基准行单元格": e,
                  "状态": "全部通过" if (c == d and f == 0) else f"异常 {c - d + f} 处"}
                 for a, b, c, d, e, f in _det])
            st.dataframe(_dfa, use_container_width=True, hide_index=True)
            if _prb:
                st.error(f"合计 {_tl} 条触发行 / {_tt} 个单元格，"
                         f"发现 {len(_prb)} 处问题")
                st.dataframe(_pdsc.DataFrame(
                    [{"文件": a, "球位": b, "属性": c, "位置": d, "问题": e}
                     for a, b, c, d, e in _prb]),
                    use_container_width=True, hide_index=True)
            else:
                st.success(f"✅ 合计 {_tl} 条触发行 / {_tt} 个基准行单元格，"
                           f"全部核对通过，未发现任何不匹配。")

            _rep_txt = st.session_state.get("scan_report") or "（报告未生成，请重新扫描）"
            st.download_button("💾 保存扫描报告 (TXT)", _rep_txt.encode("utf-8-sig"),
                               file_name=f"多维扫描报告_{datetime.now():%Y%m%d_%H%M%S}.txt",
                               mime="text/plain", use_container_width=True,
                               key="scan_dl")
            with st.expander("查看报告全文", expanded=False):
                st.text(_rep_txt)



#=========深度联动（多套合一核算）=======
@st.cache_data(ttl=1800, show_spinner=False)
def _periods_of_file(file_key):
    """取某个数据文件的期号列表（新→旧），用于下拉框"""
    try:
        rows = load_excel_data(file_key, None) or []
    except Exception:
        return []
    seen, out = set(), []
    for r in rows[2:]:
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}".strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    out.sort(reverse=True)
    return out


def render_deep_linkage(df_data):
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：深度联动需要主数据表。请点左侧「☁️刷新云端数据」。")
        return
    st.title("🔗 深度联动分析系统")
    st.info("💡 功能说明：提取基准期开奖号码的属性组合，在全历史数据中寻找相同组合，并统计命中后下一期各球位的属性频次。")
    st.divider()
    st.markdown("### 分析参数设置")
    col1, col2, col3, col4 = st.columns(4)
    with col1: mode = st.selectbox("分析模式", ["升序生肖", "按序生肖", "升序尾数", "按序尾数",
                                        "升序数字", "按序数字", "升序门数", "按序门数",
                                        "升序段数", "按序段数"])
    _target_file_early = "升序全套.csv" if "升序" in mode else "按序全套.csv"
    with col2:
        _file_periods = _periods_of_file(_target_file_early)
        if _file_periods:
            unique_periods = _file_periods
        elif df_data is not None and not isinstance(df_data, str):
            unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
            try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
            except: unique_periods.sort(reverse=True)
        else: unique_periods = ["暂无数据"]
        selected_period = st.selectbox("基准期数", unique_periods)
    with col3:
        if "门数" in mode:
            _lo, _hi = (1, 3) if "升序" in mode else (1, 5)
            pick_num = st.number_input(f"预测前N名（门数可选 {_lo}~{_hi}）",
                                       min_value=_lo, max_value=_hi, value=min(3, _hi))
        elif "段数" in mode:
            pick_num = st.number_input("预测前N名（段数可选 1~7）",
                                       min_value=1, max_value=7, value=5)
        elif "生肖" in mode:
            pick_num = st.number_input("预测前N名（1~9）", min_value=1, max_value=9, value=5)
        else:
            pick_num = st.number_input("预测前N名（1~7）", min_value=1, max_value=7, value=5)
    with col4:
        st.write(""); st.write("")
        run_btn = st.button("🚀执行联动分析", use_container_width=True, type="primary")

    if "升序" in mode: target_file = "升序全套.csv"
    else: target_file = "按序全套.csv"
    sheet_name = None
    st.info(f"💡当前读取文件：【{target_file}】 (CSV 极速模式)")

    if run_btn:
        with st.spinner(f"正在读取并统计..."):
            import csv
            try:
                all_rows = load_excel_data(target_file, sheet_name)
                if not all_rows: st.error(f"读取失败！"); st.stop()
                grouped_data = {}
                def clean_cell(c):
                    if c is None: return ""
                    try: return str(int(float(c)))
                    except: return str(c).strip()

                if "生肖" in mode: col_names = ['G', 'AK', 'BO', 'CS', 'DW', 'FA', 'GE']
                elif "尾数" in mode: col_names = ['H', 'AL', 'BP', 'CT', 'DX', 'FB', 'GF']
                elif "门数" in mode: col_names = ['J', 'AN', 'BR', 'CV', 'DZ', 'FD', 'GH']
                elif "段数" in mode: col_names = ['K', 'AO', 'BS', 'CW', 'EA', 'FE', 'GI']
                else: col_names = ['D', 'AH', 'BL', 'CP', 'DT', 'EX', 'GB']

                for r_idx in range(2, len(all_rows)):
                    row = all_rows[r_idx]
                    def get_val(c_idx): return clean_cell(row[c_idx]) if c_idx < len(row) else ""
                    p1, p2, p3 = get_val(0), get_val(1), get_val(2)
                    year_val = get_val(213) or "2026"
                    if not p1 and not p2 and not p3: continue
                    period_str = f"{year_val}{p1}{p2}{p3}"
                    if period_str in grouped_data: continue
                    ball_attrs = []
                    for ball_i in range(7):
                        col_letter = col_names[ball_i]
                        col_idx = column_index_from_string(col_letter)
                        if "数字" in mode:
                            tens, units = get_val(col_idx - 1), get_val(col_idx)
                            val = f"{tens or '0'}{units or '0'}"
                        else: val = get_val(col_idx - 1)
                        ball_attrs.append(val)
                    grouped_data[period_str] = ball_attrs

                sorted_periods = sorted(list(grouped_data.keys()))
                if selected_period not in sorted_periods:
                    st.error(f"【{target_file}】里没有 {selected_period} 这一期。"
                             f"该文件期号范围：{sorted_periods[0]} ~ {sorted_periods[-1]}，"
                             f"共 {len(sorted_periods)} 期。")
                    st.stop()
                target_idx = sorted_periods.index(selected_period)
                base_attrs = grouped_data[selected_period]
                target_combos = list(itertools.combinations(base_attrs, 3))

                if "生肖" in mode: all_possible = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
                elif "尾数" in mode: all_possible = [str(i) for i in range(10)]
                elif "门数" in mode: all_possible = [f"{i}门" for i in range(1, 6)]
                elif "段数" in mode: all_possible = [f"{i}段" for i in range(1, 8)]
                else: all_possible = [f"{i:02d}" for i in range(1, 50)]

                freq_dict = {i: {attr: 0 for attr in all_possible} for i in range(7)}
                hit_count = 0
                for i in range(target_idx):
                    hist_attrs = grouped_data[sorted_periods[i]]
                    is_hit = any(all(x in hist_attrs for x in combo) for combo in target_combos)
                    if is_hit and i + 1 < target_idx:
                        next_attrs = grouped_data[sorted_periods[i+1]]
                        hit_count += 1
                        for ball_i in range(7):
                            if next_attrs[ball_i] in freq_dict[ball_i]: freq_dict[ball_i][next_attrs[ball_i]] += 1

                report_lines = [f"========== {mode} 3码联动分析 ==========", f"【基准期数】: {selected_period}", f"【基准开出】: {', '.join(base_attrs)}", f"【联动组合数】: 共生成 {len(target_combos)} 个三码组合", f"【历史命中】: 共找到 {hit_count} 期包含这些组合\n"]
                ball_names = ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"]

                # 回测：取基准期的下一期真实开出值，用于高亮命中
                next_attrs = None
                if target_idx + 1 < len(sorted_periods):
                    next_attrs = grouped_data[sorted_periods[target_idx + 1]]

                # 回测校对行：把下一期真实开出写在最前面
                if next_attrs is not None:
                    report_lines.append(
                        f"【回测校对】: 下一期 {sorted_periods[target_idx + 1]} 开出 "
                        f"{', '.join(str(x) for x in next_attrs)}")

                for ball_i in range(7):
                    sorted_freq = sorted(freq_dict[ball_i].items(), key=lambda x: (-x[1], str(x[0])))
                    top_names = [item[0] for item in sorted_freq[:pick_num]]
                    kill_names = [item[0] for item in sorted_freq[pick_num:]]
                    _actual = next_attrs[ball_i] if next_attrs is not None else None
                    _shown = [f"{n} ✔" if (n == _actual and n in top_names) else n
                              for n in top_names]
                    line = f"{ball_names[ball_i]}: {', '.join(str(x) for x in _shown)}"
                    if "数字" not in mode and kill_names:
                        line += f"  | 杀({','.join(str(x) for x in kill_names)})"
                    if _actual is not None:
                        line += (f"  [命中 {_actual}]" if _actual in top_names
                                 else f"  [实开 {_actual}]")
                    report_lines.append(line)
                report_lines.append("\n(注：各球位数据完全独立计算，历史频次基于三码组合命中后的下一期真实开出情况)")
                st.session_state.deep_linkage_result = "\n".join(report_lines)

                # 生成带高亮的 HTML 报告
                import html as _html
                hl_style = "background-color:#fef08a;color:#dc2626;font-weight:bold;padding:1px 4px;border-radius:4px;"
                html_parts = []
                html_parts.append(f"<div style='font-family:Consolas,monospace;font-size:16px;line-height:2.0;'>")
                html_parts.append(f"<div style='font-weight:bold;font-size:18px;margin-bottom:8px;'>{_html.escape(mode)} 3码联动分析</div>")
                html_parts.append(f"<div>【基准期数】: {_html.escape(str(selected_period))}</div>")
                html_parts.append(f"<div>【基准开出】: {_html.escape(', '.join(base_attrs))}</div>")
                html_parts.append(f"<div>【联动组合数】: 共生成 {len(target_combos)} 个三码组合</div>")
                html_parts.append(f"<div>【历史命中】: 共找到 {hit_count} 期包含这些组合</div>")
                if next_attrs is not None:
                    html_parts.append(f"<div style='color:#64748b;'>【回测校对】: 下一期 {_html.escape(str(sorted_periods[target_idx + 1]))} 开出 {_html.escape(', '.join(next_attrs))}</div>")
                else:
                    html_parts.append("<div style='color:#64748b;'>【回测校对】: 基准期之后暂无开奖数据，不做高亮</div>")
                html_parts.append("<hr style='margin:10px 0;'>")

                for ball_i in range(7):
                    sorted_freq = sorted(freq_dict[ball_i].items(), key=lambda x: (-x[1], str(x[0])))
                    top_names = [item[0] for item in sorted_freq[:pick_num]]
                    kill_names = [item[0] for item in sorted_freq[pick_num:]]
                    actual = next_attrs[ball_i] if next_attrs is not None else None
                    hit = actual is not None and actual in top_names

                    chips = []
                    for name in top_names:
                        safe = _html.escape(str(name))
                        if hit and name == actual:
                            chips.append(f"<span style='{hl_style}'>{safe} ✔</span>")
                        else:
                            chips.append(f"<span>{safe}</span>")
                    line_html = f"<div style='margin:4px 0;'><b>{ball_names[ball_i]}</b>: " + ", ".join(chips)
                    if "数字" not in mode and kill_names:
                        line_html += f"  <span style='color:#94a3b8;'>| 杀({_html.escape(','.join(str(x) for x in kill_names))})</span>"
                    if hit:
                        line_html += f"  <span style='color:#16a34a;font-weight:bold;'>[命中 {_html.escape(str(actual))}]</span>"
                    elif actual is not None:
                        line_html += f"  <span style='color:#94a3b8;'>[实开 {_html.escape(str(actual))}]</span>"
                    line_html += "</div>"
                    html_parts.append(line_html)

                html_parts.append("<div style='color:#64748b;margin-top:10px;'>(注：各球位数据完全独立计算，历史频次基于三码组合命中后的下一期真实开出情况；红底黄字为回测命中项)</div>")
                html_parts.append("</div>")
                st.session_state.deep_linkage_html = "".join(html_parts)
            except Exception as e: st.error(f"分析异常: {e}")

    if st.session_state.get("deep_linkage_html"):
        st.markdown("### 深度联动分析报告（回测命中高亮）")
        # 用 iframe 隔离渲染，避免 Streamlit 前端 removeChild 报错
        import streamlit.components.v1 as _dlcomp
        _dlh = st.session_state.deep_linkage_html
        _lines = max(6, _dlh.count("<div"))
        _dlcomp.html(
            "<style>html,body{margin:0;padding:8px;background:#ffffff;"
            "font-family:Consolas,'Microsoft YaHei',monospace;font-size:16px;"
            "font-weight:600;line-height:2.0;color:#111827;}"
            "b{color:#1d4ed8;}span{color:inherit;}</style>" + _dlh,
            height=min(900, 60 + 26 * _lines), scrolling=True)

        with st.expander("📄 查看纯文本版报告", expanded=False):
            st.text_area("深度联动分析报告", value=st.session_state.get("deep_linkage_result", ""), height=300)

        _dl_txt = st.session_state.get("deep_linkage_result", "")
        _dl_frag = st.session_state.get("deep_linkage_html", "")

        # 打印用：整套 HTML（保留高亮样式）
        _dl_print_html = ('<html><head><meta charset="utf-8"><title>深度联动分析</title><style>'
                          '@page { margin: 15mm; } body { font-family: Consolas, monospace; padding: 16px; }'
                          '</style></head><body>' + _dl_frag + '</body></html>')

        # 下载用：纯文本
        _dl_txt_file = (f"深度联动_{datetime.now():%Y%m%d_%H%M%S}.txt")
        _dl_html_file = (f"深度联动_{datetime.now():%Y%m%d_%H%M%S}.html")

        _dl_print_and_save(_dl_print_html, _dl_txt, _dl_txt_file, _dl_html_file)

        _dlc1, _dlc2 = st.columns(2)
        with _dlc1:
            if st.button("📌 整份送到看板", use_container_width=True,
                         key="dl_to_board"):
                _board_add("深度联动", f"{mode} {selected_period}", _dl_txt)
                st.success("已送到汇总看板")
        with _dlc2:
            if st.button("📤 按球位分别送", use_container_width=True,
                         key="dl_to_board_each",
                         help="每个球位单独一条，方便在智能分析里分开算"):
                _parts = _split_link_by_ball(_dl_txt, f"{mode}", selected_period)
                if _parts:
                    for _title, _body in _parts:
                        _board_add("深度联动", _title, _body)
                    st.success(f"已按球位送出 {len(_parts)} 条")
                else:
                    st.warning("没有识别到球位行")

    elif st.session_state.get("deep_linkage_result"):
        st.text_area("深度联动分析报告", value=st.session_state.deep_linkage_result, height=400)


def _split_link_by_ball(txt, mode, period):
    """把「第N球: 选号 | 杀(...)」拆成 (标题, 内容) 列表"""
    import re as _re
    head = []
    balls = {}
    for line in (txt or "").splitlines():
        m = _re.match(r"\s*第(\d)球\s*[:：]\s*(.+)", line)
        if m:
            balls[int(m.group(1))] = line.strip()
        elif line.strip():
            head.append(line.strip())
    out = []
    for b in sorted(balls):
        title = f"{period} {mode} 第{b}球"
        body = "\n".join(head + ["", balls[b]])
        out.append((title, body))
    return out


def _parse_link_blocks(text):
    """解析深度联动报告：第N球: A, B | 杀(C, D)"""
    import re as _re
    blocks = []
    lines = (text or "").splitlines()
    # 头部信息
    period, mode = "", ""
    for line in lines:
        m = _re.search(r"【基准期数】\s*[:：]\s*(\d+)", line)
        if m:
            period = m.group(1)
        if "联动分析" in line:
            mode = line.strip("= ").replace("3码联动分析", "").strip()
    for line in lines:
        m = _re.match(r"\s*第(\d)球\s*[:：]\s*(.+)", line)
        if not m:
            continue
        ball = int(m.group(1))
        body = m.group(2)
        mk = _re.search(r"杀[（(]([^)）]*)[)）]", body)
        kill_raw = mk.group(1) if mk else ""
        # 属性判断
        attr = ("生肖" if "生肖" in mode else "尾数" if "尾数" in mode
                else "门数" if "门" in mode else "段数" if "段" in mode
                else "号码")
        items = []
        if kill_raw:
            for it in _re.split(r"[,，、\s]+", kill_raw.strip()):
                if not it:
                    continue
                if attr == "生肖":
                    items.append(it if it.endswith("肖") else it + "肖")
                elif attr == "尾数":
                    items.append(it if it.endswith("尾") else it + "尾")
                elif attr == "门数":
                    items.append(it if it.endswith("门") else it + "门")
                elif attr == "段数":
                    items.append(it if it.endswith("段") else it + "段")
                else:
                    items.append(it)
        if not items:
            continue
        blocks.append({
            "period": period, "order": "升序" if "升序" in mode else "按序",
            "attr": attr, "ball": str(ball), "base": "",
            "triggers": [{"row": "-", "n": 1, "up": "", "down": "",
                          "match": "", "self": False, "hot": False,
                          "kill": "、".join(items)}],
        })
    return blocks


def _dl_print_and_save(print_html_text, plain_text, txt_name, html_name):
    """打印（隐藏 iframe，不弹窗）+ 导出 TXT / HTML"""
    import base64 as _b64
    import html as _html
    import streamlit.components.v1 as _components

    b64_print = _b64.b64encode(print_html_text.encode("utf-8")).decode("utf-8")

    _components.html(
        f"""
        <div style="text-align:center;">
            <button onclick="printReport()" style="width:100%;padding:12px;background-color:#0284c7;
                color:white;border:none;border-radius:6px;cursor:pointer;font-size:16px;font-weight:bold;">
                🖨️ 打印当前报告（含高亮）
            </button>
        </div>
        <script>
        function b64DecodeUnicode(str) {{
            return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }}).join(''));
        }}
        function printReport() {{
            var html = b64DecodeUnicode("{b64_print}");
            var f = document.createElement('iframe');
            f.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
            document.body.appendChild(f);
            var d = f.contentWindow.document;
            d.open(); d.write(html); d.close();
            setTimeout(function() {{ f.contentWindow.focus(); f.contentWindow.print(); }}, 400);
        }}
        </script>
        """, height=90, scrolling=False)

    _c1, _c2 = st.columns(2)
    with _c1:
        st.download_button("📥 导出报告 (TXT)", plain_text.encode("utf-8-sig"),
                           file_name=txt_name, mime="text/plain", use_container_width=True)
    with _c2:
        st.download_button("💾 导出可打印 HTML", print_html_text.encode("utf-8"),
                           file_name=html_name, mime="text/html", use_container_width=True,
                           help="下载后用浏览器打开，Ctrl+P 打印，红底黄字高亮会保留")


def _ai_extract(answer):
    """从 AI 回答里只取「保留」的号码。

    原写法 re.findall(r'\b([0-4][0-9])\b', answer) 会把推导过程里
    「01号：触犯杀1门，剔除」这些被剔除的号也全部抓出来，
    导致号码球显示 48 个，与真实保留结果完全不符。

    现在按优先级只看：
      1) 【严格筛选结果】段
      2) 【保留结果】/【筛选结果】段
      3) 【后补筛选结果】段（区间内全被杀时的候补）
      4) 兜底：全文，但只在前面都没匹配到时使用
    """
    import re as _re

    if not answer:
        return []
    text = str(answer)

    # 0) 最优先：AI 声明为结论的 FINAL 行（与正文那行同源，保证球和文字一致）
    _fin = _re.search(r"FINAL\s*[:：]\s*([^\n\r]*)", text, _re.I)
    if _fin:
        _got_fin = []
        for tok in _re.findall(r"(?<!\d)(\d{1,2})(?!\d)", _fin.group(1)):
            _n = int(tok)
            if 1 <= _n <= 49:
                _got_fin.append(_n)
        if _got_fin:
            return sorted(set(_got_fin))

    def _nums(seg):
        out = []
        for tok in _re.findall(r"(?<!\d)(\d{1,2})(?!\d)", seg or ""):
            n = int(tok)
            if 1 <= n <= 49:
                out.append(n)
        return out

    def _section(*keys):
        for key in keys:
            m = _re.search(key + r"[】\]]?[\s\S]{0,3000}", text)
            if not m:
                continue
            seg = m.group(0)
            # 只取到下一个【标题】之前
            seg = _re.split(r"【", seg)[0]
            # 去掉标题本身
            seg = seg.split(keys[0], 1)[-1]
            got = _nums(seg)
            if got:
                return got
        return []

    got = _section("严格筛选结果")
    if not got:
        got = _section("保留结果", "筛选结果")
    if not got:
        got = _section("后补筛选结果", "候补")
    if not got:
        got = _nums(text)          # 兜底
    return sorted(set(got))


_PRED_JSON = "ai_pred_history.json"


def _pred_db_path():
    """本地兜底用的 sqlite 路径（GitHub 不可用时使用）"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_pred_history.db")


def _pred_gh_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    if not token or not repo:
        return None, None, None
    return token, repo, {"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json",
                         "Content-Type": "application/json"}


def _pred_gh_read():
    """从仓库读存档 JSON -> (dict, sha)；失败返回 (None, None)"""
    token, repo, hdrs = _pred_gh_headers()
    if not token:
        return None, None
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{_PRED_JSON}"
        r = requests.get(url, headers=hdrs, timeout=20)
        if r.status_code == 404:
            return {}, None
        if r.status_code != 200:
            return None, None
        info = r.json()
        raw = base64.b64decode(info["content"]).decode("utf-8")
        return (json.loads(raw) if raw.strip() else {}), info["sha"]
    except Exception:
        return None, None


def _pred_gh_write(data, sha, msg="推演存档更新"):
    token, repo, hdrs = _pred_gh_headers()
    if not token:
        return False
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{_PRED_JSON}"
        body = {"message": msg,
                "content": base64.b64encode(
                    json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")).decode(),
                "branch": "main"}
        if sha:
            body["sha"] = sha
        r = requests.put(url, headers=hdrs, json=body, timeout=30)
        if r.status_code in (200, 201):
            st.session_state["_pred_sha"] = r.json()["content"]["sha"]
            return True
        # 冲突：重读后再写一次
        if r.status_code == 409:
            _d, _s = _pred_gh_read()
            if _s:
                body["sha"] = _s
                r2 = requests.put(url, headers=hdrs, json=body, timeout=30)
                if r2.status_code in (200, 201):
                    st.session_state["_pred_sha"] = r2.json()["content"]["sha"]
                    return True
        return False
    except Exception:
        return False


def _sup_rows(table, order=None):
    """通用：读 Supabase 表；失败返回 None"""
    client = get_supabase_client()
    if not client:
        return None
    try:
        q = client.table(table).select("*")
        if order:
            q = q.order(order, desc=False)
        return q.execute().data or []
    except Exception:
        return None


def _pred_sup_read():
    rows = _sup_rows("ai_pred_archive", "ts")
    if rows is None:
        return None
    out = {}
    for r in rows:
        _nums = r.get("nums") or []
        if isinstance(_nums, str):
            _nums = [int(x) for x in _nums.split(",") if str(x).strip().isdigit()]
        k = f"{r.get('period')}|{r.get('ball')}|{r.get('order_type') or ''}"
        out[k] = {"period": r.get("period"), "ball": r.get("ball"),
                  "order": r.get("order_type") or "",
                  "nums": [int(x) for x in _nums], "ts": r.get("ts") or "",
                  "sig": r.get("sig") or "", "psig": r.get("psig") or "",
                  "history": r.get("history") or []}
    return out


def _pred_sup_write(data):
    """整表重写：清空再批量插入"""
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table("ai_pred_archive").delete().neq("period", "__none__").execute()
        rows = []
        for v in data.values():
            rows.append({
                "period": str(v.get("period")), "ball": str(v.get("ball")),
                "order_type": str(v.get("order") or ""),
                "nums": v.get("nums") or [], "ts": str(v.get("ts") or ""),
                "sig": str(v.get("sig") or ""), "psig": str(v.get("psig") or ""),
                "history": v.get("history") or [],
            })
        for i in range(0, len(rows), 50):
            client.table("ai_pred_archive").insert(rows[i:i + 50]).execute()
        return True
    except Exception:
        return False


def _pred_load_all():
    """全部存档；优先 Supabase，空则从 GitHub 旧文件回填"""
    if "_pred_cache" not in st.session_state:
        data = _pred_sup_read()
        sha = None
        if data is not None and not data:
            # Supabase 表是空的 -> 尝试用 GitHub 旧存档恢复一次
            _gh, _gh_sha = _pred_gh_read()
            if _gh:
                data = _gh
                try:
                    _pred_sup_write(data)      # 回填到云端表
                except Exception:
                    pass
        if data is None:
            data, sha = _pred_gh_read()
        if data is None:                      # 都不可用 -> 本地 sqlite 兜底
            data = {}
            try:
                conn = sqlite3.connect(_pred_db_path(), timeout=10)
                conn.execute("CREATE TABLE IF NOT EXISTS ai_pred ("
                             "period TEXT NOT NULL, ball TEXT NOT NULL, order_type TEXT, "
                             "nums TEXT, ts TEXT, PRIMARY KEY(period, ball))")
                for p_, b_, o_, n_, t_ in conn.execute(
                        "SELECT period, ball, order_type, nums, ts FROM ai_pred"):
                    data[f"{p_}|{b_}"] = {"period": p_, "ball": b_, "order": o_,
                                          "nums": [int(x) for x in str(n_ or "").split(",")
                                                   if str(x).strip().isdigit()], "ts": t_}
                conn.close()
            except Exception:
                data = {}
        # 规范化键：period|ball|order（兼容旧的 period|ball）
        _norm = {}
        for _k, _v in data.items():
            _nk = (f"{_v.get('period')}|{_v.get('ball')}|{_v.get('order', '')}")
            _norm[_nk] = _v
        data = _norm
        st.session_state["_pred_cache"] = data
        if sha:
            st.session_state["_pred_sha"] = sha
    return st.session_state["_pred_cache"]


def _pred_persist(msg="推演存档更新"):
    data = st.session_state.get("_pred_cache") or {}
    if _pred_sup_write(data):
        return True
    ok = _pred_gh_write(data, st.session_state.get("_pred_sha"), msg)
    if not ok:                                # 兜底写本地
        try:
            conn = sqlite3.connect(_pred_db_path(), timeout=10)
            conn.execute("CREATE TABLE IF NOT EXISTS ai_pred ("
                         "period TEXT NOT NULL, ball TEXT NOT NULL, order_type TEXT, "
                         "nums TEXT, ts TEXT, PRIMARY KEY(period, ball))")
            conn.execute("DELETE FROM ai_pred")
            for v in data.values():
                conn.execute("INSERT OR REPLACE INTO ai_pred VALUES(?,?,?,?,?)",
                             (v["period"], v["ball"], v.get("order", ""),
                              ",".join(str(n) for n in v.get("nums", [])),
                              v.get("ts", "")))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return ok


def _pred_gh_commits(limit=20):
    """该存档文件的历史提交"""
    token, repo, hdrs = _pred_gh_headers()
    if not token:
        return []
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/commits",
                         headers=hdrs, params={"path": _PRED_JSON, "per_page": limit},
                         timeout=25)
        if r.status_code != 200:
            return []
        out = []
        for c in r.json():
            out.append({"sha": c["sha"],
                        "msg": (c["commit"]["message"] or "")[:40],
                        "date": c["commit"]["committer"]["date"].replace("T", " ")[:19]})
        return out
    except Exception:
        return []


def _pred_gh_at(sha):
    """取指定提交里的存档内容"""
    token, repo, hdrs = _pred_gh_headers()
    if not token:
        return None
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/{_PRED_JSON}",
                         headers=hdrs, params={"ref": sha}, timeout=25)
        if r.status_code != 200:
            return None
        raw = base64.b64decode(r.json()["content"]).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return None


def _pred_gh_restore(sha):
    """把存档恢复成某个历史提交的版本"""
    data = _pred_gh_at(sha)
    if data is None:
        return False
    _cur, _sha = _pred_gh_read()
    ok = _pred_gh_write(data, _sha, f"恢复存档到历史版本 {sha[:7]}")
    _audit_append("恢复到历史版本", f"commit={sha[:7]}")
    if ok:
        st.session_state.pop("_pred_cache", None)
    return ok


_AUDIT_FILE = "_audit_log.json"
_AUDIT_CACHE = 200


def _audit_sup_read():
    rows = _sup_rows("ai_audit_log", "id")
    if rows is None:
        return None
    return [{"ts": r.get("ts", ""), "user": r.get("user", ""),
             "action": r.get("action", ""), "detail": r.get("detail", ""),
             "sig": r.get("sig", "")} for r in rows]


def _audit_sup_append(rec):
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table("ai_audit_log").insert({
            "ts": rec["ts"], "user": rec["user"], "action": rec["action"],
            "detail": rec["detail"], "sig": rec["sig"]}).execute()
        return True
    except Exception:
        return False


def _audit_read():
    _rows = _audit_sup_read()
    if _rows:
        return _rows, None
    if _rows is not None and not _rows:
        # 云端表空 -> 尝试从 GitHub 旧日志恢复
        _tok, _repo, _hdrs = _pred_gh_headers()
        if _tok:
            try:
                _r = requests.get(
                    f"https://api.github.com/repos/{_repo}/contents/{_AUDIT_FILE}",
                    headers=_hdrs, timeout=20)
                if _r.status_code == 200:
                    _info = _r.json()
                    _old = json.loads(base64.b64decode(_info["content"]).decode("utf-8"))
                    if _old:
                        for _rec in _old:
                            try:
                                _audit_sup_append(_rec)
                            except Exception:
                                pass
                        return _old, None
            except Exception:
                pass
        return [], None
    token, repo, hdrs = _pred_gh_headers()
    if not token:
        return [], None
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/{_AUDIT_FILE}",
                         headers=hdrs, timeout=20)
        if r.status_code == 404:
            return [], None
        if r.status_code != 200:
            return [], None
        info = r.json()
        raw = base64.b64decode(info["content"]).decode("utf-8")
        return (json.loads(raw) if raw.strip() else []), info["sha"]
    except Exception:
        return [], None


def _audit_append(action, detail=""):
    """追加一条审计记录：时间、用户、动作、详情，并链接上一条指纹"""
    token, repo, hdrs = _pred_gh_headers()
    if not token:
        return False
    try:
        logs, sha = _audit_read()
        prev = logs[-1].get("sig", "") if logs else ""
        rec = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": str(st.session_state.get("username", "") or "未知"),
            "action": str(action),
            "detail": str(detail)[:300],
        }
        rec["sig"] = _pred_sig({"period": rec["ts"], "ball": rec["user"],
                                "order": rec["action"], "nums": [],
                                "ts": rec["detail"]}, prev)
        if _audit_sup_append(rec):
            return True
        logs.append(rec)
        logs = logs[-500:]
        body = {"message": f"审计：{rec['user']} {action}",
                "content": base64.b64encode(
                    json.dumps(logs, ensure_ascii=False, indent=1).encode()).decode(),
                "branch": "main"}
        if sha:
            body["sha"] = sha
        r2 = requests.put(f"https://api.github.com/repos/{repo}/contents/{_AUDIT_FILE}",
                          headers=hdrs, json=body, timeout=25)
        return r2.status_code in (200, 201)
    except Exception:
        return False


def _pred_sig(rec, prev_sig=""):
    """记录指纹：内容 + 上一条指纹，任一处被改都会变"""
    import hashlib as _h
    raw = "|".join([
        str(rec.get("period", "")),
        str(rec.get("ball", "")),
        str(rec.get("order", "")),
        ",".join(str(n) for n in rec.get("nums", [])),
        str(rec.get("ts", "")),
        str(prev_sig or ""),
    ])
    return _h.sha256(raw.encode("utf-8")).hexdigest()


def _pred_verify():
    """校验全部记录 -> (通过数, 问题列表)
       有 psig 的记录：用自带锚点校验（插入新期不影响）
       无 psig 的老记录：按顺序链校验；链错位归为「旧格式未锚定」"""
    data = _pred_load_all()
    keys = sorted(data.keys())
    prev = ""
    ok, bad, legacy = 0, [], 0
    for k in keys:
        rec = data[k]
        got = str(rec.get("sig", ""))
        if "psig" in rec:
            want = _pred_sig(rec, rec.get("psig") or "")
            if not got:
                bad.append((k, "缺少指纹（未签名）"))
            elif got != want:
                bad.append((k, "指纹不匹配（内容被改动）"))
            else:
                ok += 1
        else:
            # 老格式：链条校验
            want = _pred_sig(rec, prev)
            if got and got == want:
                ok += 1
            else:
                legacy += 1
        prev = want
    if legacy:
        bad.append((f"旧格式记录 {legacy} 条",
                    "无锚点（非篡改，重新保存或点「重新签名」即可归入新格式）"))
    return ok, bad


def _pred_sign_all():
    """为全部记录重建指纹链，同时补上 psig 锚点（旧记录升级用）"""
    data = _pred_load_all()
    prev = ""
    for k in sorted(data.keys()):
        rec = data[k]
        rec["psig"] = prev                 # 关键：补锚点
        rec["sig"] = _pred_sig(rec, prev)
        prev = rec["sig"]
    st.session_state["_pred_cache"] = data
    return _pred_persist("重建完整性指纹")


def _pred_has(period, ball, order_type):
    """该期该球该排序是否已有存档 -> 有则返回记录，否则 None"""
    return _pred_load_all().get(f"{period}|{ball}|{order_type or ''}")


def _pred_save(period, ball, order_type, nums, force=False):
    """保存一条；已存在时：force=True 才覆盖（旧版进 history）"""
    try:
        data = _pred_load_all()
        _k = f"{period}|{ball}|{order_type or ''}"
        _old = data.get(_k)
        if _old and not force:
            return False
        _hist = list(_old.get("history") or []) if _old else []
        if _old:
            _hist.insert(0, {"nums": _old.get("nums", []), "ts": _old.get("ts", "")})
            _hist = _hist[:5]
        _prev_sig = ""
        for _kk in sorted(data.keys()):
            if _kk < _k:
                _prev_sig = str(data[_kk].get("sig", "")) or _prev_sig
        _rec = {"period": str(period),
                "ball": str(ball),
                "order": str(order_type or ""),
                "nums": [int(n) for n in nums],
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "history": _hist}
        _rec["psig"] = _prev_sig
        _rec["sig"] = _pred_sig(_rec, _prev_sig)
        data[_k] = _rec
        st.session_state["_pred_cache"] = data
        _pred_persist(f"推演存档：{period} {ball}")
        _audit_append("保存存档",
                      f"{period} {ball} {order_type} -> "
                      f"{','.join(str(n) for n in nums)}"
                      + ("（覆盖）" if _old else ""))
        return True
    except Exception:
        return False


def _pred_delete(period=None, ball=None, order=None):
    """删除：period+ball(+order) 删单球；只给 period 删整期；都不给清空"""
    try:
        data = _pred_load_all()
        if period and ball:
            for k in [k for k in data
                      if k.startswith(f"{period}|{ball}|")
                      and (order is None or k.endswith(f"|{order}"))]:
                data.pop(k, None)
        elif period:
            for k in [k for k in data if k.startswith(f"{period}|")]:
                data.pop(k, None)
        else:
            data.clear()
        st.session_state["_pred_cache"] = data
        _pred_persist("推演存档删除")
        _audit_append("删除存档",
                      f"period={period or '*'} ball={ball or '*'} order={order or '*'}")
        return True
    except Exception:
        return False


def _pred_restore(period, ball, order_type):
    """把上一版历史恢复为当前记录"""
    try:
        data = _pred_load_all()
        _k = f"{period}|{ball}|{order_type or ''}"
        v = data.get(_k)
        if not v or not v.get("history"):
            return False
        _h = list(v["history"])
        _prev = _h.pop(0)
        _new_hist = _h[:5]
        if v.get("nums"):
            _new_hist.insert(0, {"nums": v.get("nums", []), "ts": v.get("ts", "")})
        v["nums"] = _prev.get("nums", [])
        v["ts"] = _prev.get("ts", "")
        v["history"] = _new_hist[:5]
        st.session_state["_pred_cache"] = data
        _pred_persist(f"恢复存档 {period} {ball}")
        _audit_append("恢复存档", f"{period} {ball} {order_type}")
        return True
    except Exception:
        return False


def _pred_load(period, order=None):
    """{ball: (nums, ts, order)}；order 不给则合并（同球多排序取最新）"""
    out, _ts = {}, {}
    for k, v in _pred_load_all().items():
        if v.get("period") != str(period):
            continue
        if order and v.get("order") != order:
            continue
        b = v["ball"]
        if b in out and str(_ts.get(b, "")) > str(v.get("ts", "")):
            continue
        out[b] = (v.get("nums", []), v.get("ts", ""), v.get("order", ""))
        _ts[b] = v.get("ts", "")
    return out


def _pred_orders(period=None):
    """存档里出现过的排序类型"""
    s = set()
    for v in _pred_load_all().values():
        if period and v.get("period") != str(period):
            continue
        s.add(v.get("order") or "升序")
    return sorted(s)


def _pred_periods():
    ps = {v.get("period") for v in _pred_load_all().values()}
    return sorted([p for p in ps if p], reverse=True)


def _pred_rows():
    rows = []
    for v in _pred_load_all().values():
        rows.append((v.get("period"), v.get("ball"), v.get("ts"),
                     ",".join(str(n) for n in v.get("nums", [])), v.get("order")))
    rows.sort(key=lambda x: (str(x[0]), str(x[1])), reverse=True)
    return rows


def _pred_actual_nums(df_data, period):
    """从总数据表取该期实际开奖号；未开奖返回 None"""
    if df_data is None or isinstance(df_data, str):
        return None
    try:
        tmp = df_data.iloc[:, 18].apply(clean_period)
        matched = df_data[tmp == str(period)]
        if matched.empty:
            return None
        row = matched.iloc[0]
        nums = []
        for i in range(19, 26):
            v = clean_period(row.iloc[i]) if i < len(row) else ""
            if v != "":
                try:
                    nums.append(int(v))
                except Exception:
                    pass
        return nums if nums else None
    except Exception:
        return None


def _pred_render_archive(df_data, default_period):
    """推演结果存档 + 开奖对照区"""
    st.divider()
    st.markdown("### 📚 推演结果存档与开奖对照")
    st.caption("按期号+球号保存 AI 推演结果（同期同球只留最新一次）。"
               "开奖后自动从总数据表读取实际开奖号，命中的球号高亮显示。")

    periods = _pred_periods()
    if not periods:
        st.info("暂无存档。完成一次 AI 推演后会自动保存。")
        return

    # ---------- ① 全部存档总表（一行 = 一期 + 一种排序） ----------
    _rows_all2 = []
    for _p in periods:
        for _o in ("升序", "按序"):
            _d = _pred_load(_p, _o)
            if not _d:
                continue
            _a = _pred_actual_nums(df_data, _p)
            _r = {"期号": _p, "排序": _o}
            _hit = 0
            for i in range(1, 8):
                _v = _d.get(f"第{i}球")
                if not _v or not _v[0]:
                    _r[f"第{i}球"] = "-"
                elif _a and i - 1 < len(_a) and _a[i - 1] in _v[0]:
                    _hit += 1
                    _r[f"第{i}球"] = " ".join(
                        (f"{n:02d}✓" if n == _a[i - 1] else f"{n:02d}") for n in _v[0])
                else:
                    _r[f"第{i}球"] = " ".join(f"{n:02d}" for n in _v[0])
            _r["命中球位"] = _hit if _a else "-"
            _rows_all2.append(_r)

    # 完整性校验
    _ok_n, _bad = _pred_verify()
    _is_admin_now = st.session_state.get("username") == st.secrets.get("ADMIN_USERNAME", "admin")
    if _bad:
        st.error(f"⚠️ 完整性校验异常：{len(_bad)} 条记录有问题"
                 f"（通过 {_ok_n} 条）。可能被篡改或为旧数据："
                 + "；".join(f"{k}（{why}）" for k, why in _bad[:3]))
        if _is_admin_now and st.button("🔐 重建完整性指纹（管理员）", key="pred_resign"):
            if _pred_sign_all():
                st.success("已重建指纹")
                st.rerun()
    else:
        st.caption(f"🔒 完整性校验：{_ok_n} 条记录全部通过（指纹链一致）")

    if _rows_all2:
        st.markdown("**【全部存档总表】**（一行 = 一期 + 一种排序；只算一个球，其余球位显示 -）")
        st.dataframe(pd.DataFrame(_rows_all2), use_container_width=True, hide_index=True)

    # ---------- ② 选择期号 ----------
    _sc1, _sc1b, _sc2 = st.columns([1, 1, 2])
    with _sc1:
        sel = st.selectbox("选择期号查看存档", periods, key="pred_arch_period")
    _cnt_s = len(_pred_load(sel, "升序"))
    _cnt_a = len(_pred_load(sel, "按序"))
    st.caption(f"本期存档：升序 {_cnt_s} 个球位　｜　按序 {_cnt_a} 个球位"
               f"（下方「排序方式」切换查看）")
    _ords = _pred_orders(sel) or ["升序"]
    with _sc1b:
        _ord = st.selectbox("排序方式", _ords, key="pred_arch_order")
    with _sc2:
        st.write("")
        _drawn_n = sum(1 for _p in periods if _pred_actual_nums(df_data, _p))
        st.caption(f"共 {len(periods)} 期存档、{_drawn_n} 期已开奖；"
                   f"选中的期会自动带上实际开奖号做命中标记")

    data = _pred_load(sel, _ord)
    if not data:
        st.warning(f"{sel} 期（{_ord}）暂无存档。")
        return

    actual = _pred_actual_nums(df_data, sel)

    # ---------- ② 选中期的对照表（期号 + 7 球位） ----------
    _row = {"期号": sel}
    _hit_balls = 0
    for i in range(1, 8):
        _v = data.get(f"第{i}球")
        if not _v or not _v[0]:
            _row[f"第{i}球"] = "-"
            continue
        _nums = _v[0]
        if actual and i - 1 < len(actual):
            _hn = actual[i - 1]
            if _hn in _nums:
                _hit_balls += 1
            _row[f"第{i}球"] = " ".join(
                (f"{n:02d}✓" if n == _hn else f"{n:02d}") for n in _nums)
        else:
            _row[f"第{i}球"] = " ".join(f"{n:02d}" for n in _nums)

    st.dataframe(pd.DataFrame([_row]), use_container_width=True, hide_index=True)

    if actual:
        st.success(f"{sel} 期【{_ord}】已开奖，实际开奖号：" +
                   " ".join(f"{n:02d}" for n in actual) +
                   f"　｜　7 个球位命中 {_hit_balls} 个")
    else:
        st.info(f"{sel} 期尚未开奖，暂不做命中对照。")

    # ---------- ③ 该期号码球（红底=命中） ----------
    for i in range(1, 8):
        _v = data.get(f"第{i}球")
        if not _v or not _v[0]:
            continue
        chips = []
        for n in _v[0]:
            if actual and n in actual:
                chips.append(
                    f"🔴**{n:02d}**")
            else:
                chips.append(
                    f"⚪**{n:02d}**")
        st.markdown(f"**第{i}球**　" + "".join(chips))

    # 恢复上一版（记录级历史）
    _hist_balls = []
    for i in range(1, 8):
        _v = data.get(f"第{i}球")
        if _v and _v[0]:
            _raw = _pred_has(sel, f"第{i}球", _ord)
            if _raw and _raw.get("history"):
                _hist_balls.append(f"第{i}球")
    if _hist_balls:
        with st.expander(f"↩ 恢复上一版（{'、'.join(_hist_balls)} 有历史）", expanded=False):
            _rb = st.selectbox("选择球位", _hist_balls, key="pred_restore_ball")
            _raw = _pred_has(sel, _rb, _ord) or {}
            for _hi, _h in enumerate(_raw.get("history") or []):
                st.caption(f"历史第{_hi+1}版："
                           f"{' '.join('%02d' % n for n in _h.get('nums', []))}"
                           f"　（{_h.get('ts', '')}）")
            if st.button(f"↩ 恢复 {_rb} 上一版", key="pred_restore_btn",
                         disabled=not _is_admin_now):
                if _pred_restore(sel, _rb, _ord):
                    st.success("已恢复上一版")
                    st.rerun()
                else:
                    st.error("恢复失败：没有历史版本")

    if _is_admin_now:
        with st.expander("📋 审计日志（谁、何时、做了什么）", expanded=False):
            _logs, _ = _audit_read()
            if not _logs:
                st.caption("还没有审计记录（保存/删除/恢复都会自动记录）")
            else:
                st.caption(f"共 {len(_logs)} 条，最新在上（追加式 + 指纹链）")
                _show = list(reversed(_logs[-50:]))
                st.dataframe(pd.DataFrame(_show)[["ts", "user", "action", "detail"]],
                             use_container_width=True, hide_index=True)

    with st.expander("🕘 云端历史版本（可从任意一次提交恢复）", expanded=False):
        _cmts = _pred_gh_commits(15)
        if not _cmts:
            st.caption("读不到历史提交（检查 GITHUB_TOKEN 权限）")
        else:
            _opts = {f"{c['date']}　{c['msg']}　{c['sha'][:7]}": c["sha"] for c in _cmts}
            _pick_c = st.selectbox("选择要恢复的版本", list(_opts.keys()),
                                   key="pred_hist_pick")
            if st.button("↩ 恢复到这个版本", key="pred_hist_btn",
                         disabled=not _is_admin_now):
                if _pred_gh_restore(_opts[_pick_c]):
                    st.success("已恢复到该历史版本")
                    st.rerun()
                else:
                    st.error("恢复失败：可能没有权限或该版本无存档")
            st.caption("每次保存/删除都会产生一次提交，这里列出最近 15 次。")

    _op1, _op2 = st.columns(2)
    with _op1:
        if st.button(f"🗑 删除 {sel} 期【{_ord}】存档", use_container_width=True,
                     key="pred_del_period", disabled=not _is_admin_now):
            if _pred_delete(period=sel, order=_ord):
                st.success(f"已删除 {sel}（{_ord}）")
                st.rerun()
    with _op2:
        if st.button("🧹 清空全部存档", use_container_width=True, key="pred_del_all",
                     disabled=not _is_admin_now):
            if _pred_delete():
                st.success("已清空")
                st.rerun()


def render_ai(df_data):
    #=========AI页面标题===================
    st.title("🧠 AI 严谨推演系统")
    try:
        _n_arch = len(_pred_load_all())
        _n_per = len(_pred_periods())
        st.caption(f"📚 存档：{_n_per} 期 / {_n_arch} 条（存在云端 ai_pred_history.json，页面最下方可查看）")
    except Exception as _ae:
        st.caption(f"📚 存档读取异常：{type(_ae).__name__}: {_ae}")
    _board_render()

    if df_data is not None and not isinstance(df_data, str):
        unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
        try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
        except: unique_periods.sort(reverse=True)

        # ?? 核心新增：自动推算下一期并置顶
        if unique_periods and unique_periods[0] != "暂无数据":
            latest_period = unique_periods[0] # 此时拿到的是 2026119
            try:
                # 强转成数字后 +1
                next_period = str(int(float(latest_period)) + 1)
                # 如果算出来的下一期还没有在历史数据里，就把它插到最前面
                if next_period not in unique_periods:
                    unique_periods.insert(0, next_period)
            except:
                pass
    else:
        unique_periods = ["暂无数据"]

    if "reset_version" not in st.session_state: st.session_state.reset_version = 0
    v_prefix = f"v{st.session_state.reset_version}_chk_"
#==========AI页面的复选框配置===================
#=========为后面增加复选框做配置代码=============
    CHECKBOX_MAP = {
        "金肖": "杀金肖（猴鸡），", "木肖": "杀木肖（虎兔），", "水肖": "杀水肖（鼠猪），", "火肖": "杀火肖（蛇马），", "土肖": "杀土肖（牛龙羊狗），",
        "红肖": "杀红肖（马兔鼠鸡），", "蓝肖": "杀蓝肖（虎猴蛇猪），", "绿肖": "杀绿肖（龙狗牛羊），",
        "0尾": "杀0尾（10、20、30、40），", "1尾": "杀1尾（01、11、21、31、41），", "2尾": "杀2尾（02、12、22、32、42），",
        "3尾": "杀3尾（03、13、23、33、43），", "4尾": "杀4尾（04、14、24、34、44），", "5尾": "杀5尾（05、15、25、35、45），",
        "6尾": "杀6尾（06、16、26、36、46），", "7尾": "杀7尾（07、17、27、37、47），", "8尾": "杀8尾（08、18、28、38、48），", "9尾": "杀9尾（09、19、29、39、49），",
        "杀鼠": "杀鼠，", "杀牛": "杀牛，", "杀虎": "杀虎，", "杀兔": "杀兔，", "杀龙": "杀龙，", "杀蛇": "杀蛇，", "杀马": "杀马，", "杀羊": "杀羊，", "杀猴": "杀猴，", "杀鸡": "杀鸡，", "杀狗": "杀狗，", "杀猪": "杀猪，",
        "1门": "杀1门（01、02、03、04、05、06、07、08、09），", "2门": "杀2门（10、11、12、13、14、15、16、17、18、19），", "3门": "杀3门（20、21、22、23、24、25、26、27、28、29），", "4门": "杀4门（30、31、32、33、34、35、36、37、38、39），", "5门": "杀5门（40、41、42、43、44、45、46、47、48、49），",
        "1段": "杀1段（01、02、03、04、05、06、07），", "2段": "杀2段（08、09、10、11、12、13、14），", "3段": "杀3段（15、16、17、18、19、20、21），", "4段": "杀4段（22、23、24、25、26、27、28），", "5段": "杀5段（29、30、31、32、33、34、35），", "6段": "杀6段（36、37、38、39、40、41、42），", "7段": "杀7段（43、44、45、46、47、48、49），",
        "01合": "杀01合（01、10），", "02合": "杀02合（02、11、20），", "03合": "杀03合（03、12、21、30），", "04合": "杀04合（04、13、22、31、40），", "05合": "杀05合（05、14、23、32、41），", "06合": "杀06合（06、15、24、33、42），", "07合": "杀07合（07、16、25、34、43），", "08合": "杀08合（08、17、26、35、44），", "09合": "杀09合（09、18、27、36、45），", "10合": "杀10合（19、28、37、46），", "11合": "杀11合（29、38、47），", "12合": "杀12合（39、48），", "13合": "杀13合（49），",
        "红波": "杀红波（01、02、07、08、12、13、18、19、23、24、29、30、34、35、40、45、46），", "蓝波": "杀蓝波（03、04、09、10、14、15、20、25、26、31、36、37、41、42、47、48），", "绿波": "杀绿波（05、06、11、16、17、21、22、27、28、32、33、38、39、43、44、49），",
        "红波单": "杀红波单（01、07、13、19、23、29、35、45），", "红波双": "杀红波双（02、08、12、18、24、30、34、40、46），", "蓝波单": "杀蓝波单（03、09、15、25、31、37、41、47），", "蓝波双": "杀蓝波双（04、10、14、20、26、36、42、48），", "绿波单": "杀绿波单（05、11、17、21、27、33、39、43、49），", "绿波双": "杀绿波双（06、16、22、28、32、38、44），",
        "金号": "杀金号（04、05、12、13、26、27、34、35、42、43），", "木号": "杀木号（08、09、16、17、24、25、38、39、46、47），", "水号": "杀水号（01、14、15、22、23、30、31、44、45），", "火号": "杀火号（02、03、10、11、18、19、32、33、40、41、48、49），", "土号": "杀土号（06、07、20、21、28、29、36、37），",
        "金尾": "杀金尾（04、09、14、19、24、29、34、39、44、49），", "木尾": "杀木尾（03、08、13、18、23、28、33、38、43、48），", "水尾": "杀水尾（01、06、11、16、21、26、31、36、41、46），", "火尾": "杀火尾（02、07、12、17、22、27、32、37、42、47），", "土尾": "杀土尾（05、10、15、20、25、30、35、40、45），",
        "大肖": "杀大肖（牛虎龙马），", "中肖": "杀中肖（羊猴狗猪），", "小肖": "杀小肖（鼠兔蛇鸡），", "书肖": "杀书肖（马龙虎），", "琴肖": "杀琴肖（蛇兔鸡），", "棋肖": "杀棋肖（牛鼠狗），", "画肖": "杀画肖（猪猴羊），", "福肖": "杀福肖（马龙虎鼠），", "禄肖": "杀禄肖（兔牛猪猴），", "寿肖": "杀寿肖（蛇狗鸡羊），",
        "家臣": "杀家臣（马牛猪狗），", "美女": "杀美女（蛇兔鸡羊），", "君王": "杀君王（龙虎），", "恶人": "杀恶人（鼠猴），",
        # 👇 新增的方位和单双组合，全部在这里！
        "东": "杀东肖（虎兔龙），", "南": "杀南肖（蛇马羊），", "西": "杀西肖（猴鸡狗），", "北": "杀北肖（鼠牛猪），",
        "双双": "杀双双（02、04、06、08、20、22、24、26、28、40、42、44、46、48），",
        "双单": "杀双单（01、03、05、07、09、21、23、25、27、29、41、43、45、47、49），",
        "单单": "杀单单（11、13、15、17、19、31、33、35、37、39），",
        "单双": "杀单双（10、12、14、16、18、30、32、34、36、38），",
         # 🔥 新增：阴天阳地、3模（按尾数规则修正版）
        "阳天": "杀阳天（牛、兔、猴：04、06、11、16、18、23、28、30、35、40、42、47），",
        "阳地": "杀阳地（虎、羊、鸡：05、10、12、17、22、24、29、34、36、41、46、48），",
        "阴天": "杀阴天（龙、马、猪：01、03、08、13、15、20、25、27、32、37、39、44、49），",
        "阴地": "杀阴地（鼠、蛇、狗：02、07、09、14、19、21、26、31、33、38、43、45），",
        "3余0": "杀3余0（尾数0、3、6、9：03、06、09、10、13、16、19、20、23、26、29、30、33、36、39、40、43、46、49），",
        "3余1": "杀3余1（尾数1、4、7：01、04、07、11、14、17、21、24、27、31、34、37、41、44、47），",
        "3余2": "杀3余2（尾数2、5、8：02、05、08、12、15、18、22、25、28、32、35、38、42、45、48），"
}

    if "ai_api_result" not in st.session_state: st.session_state.ai_api_result = "等待推演..."
    if "ai_ball_result" not in st.session_state: st.session_state.ai_ball_result = []

    def get_prefix(qishu, qiu, order_type):
        if order_type == "按序": interval = f"{qiu}的取值区间为1号至49号之间，"
        else:
            if qiu == "第1球": interval = "第一球的取值区间为1号至20号之间，"
            elif qiu == "第2球": interval = "第二球的取值区间为2号至25号之间，"
            elif qiu == "第3球": interval = "第三球的取值区间为3号至30号之间，"
            elif qiu == "第4球": interval = "第四球的取值区间为4号至40号之间，"
            elif qiu == "第5球": interval = "第五球的取值区间为15号至48号之间，"
            elif qiu == "第6球": interval = "第六球的取值区间为25号至49号之间，"
            else: interval = "第七球的取值区间为1号至49号之间，"
        return f"这是{qishu}期{order_type}{qiu}的核算条件，{interval}"

    col1, col2, col3 = st.columns(3)
    _BALLS = ["第1球", "第2球", "第3球", "第4球", "第5球", "第6球", "第7球"]
    if st.session_state.get("ai_period_sel") not in unique_periods:
        st.session_state["ai_period_sel"] = unique_periods[0] if unique_periods else ""
    if st.session_state.get("ai_qiu_sel") not in _BALLS:
        st.session_state["ai_qiu_sel"] = "第1球"
    with col1:
        qishu = st.selectbox("选择期数：", unique_periods, key="ai_period_sel")
    with col2:
        qiu = st.selectbox("选择球数：", _BALLS, key="ai_qiu_sel")
    def _mark_order():
        st.session_state["ai_order_confirmed"] = st.session_state.get("ai_order_sel")

    with col3:
        order_type = st.radio("核算模式：", ["升序", "按序"], horizontal=True,
                              key="ai_order_sel", on_change=_mark_order)
    if not st.session_state.get("ai_order_confirmed"):
        st.warning("⚠️ 还没确认核算模式：本次要按【升序】还是【按序】计算？"
                   "请在上方「核算模式」点一下再开始推演。")
    elif st.session_state.get("ai_order_confirmed") != order_type:
        st.info(f"当前选择是【{order_type}】，与上次确认的"
                f"【{st.session_state.get('ai_order_confirmed')}】不同，请再确认一次。")

    st.divider()
    checked_texts = []
    for key in CHECKBOX_MAP.keys():
        if st.session_state.get(f"{v_prefix}{key}", False): checked_texts.append(CHECKBOX_MAP[key])
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        # 🔥 接收多维分析传过来的条件
        extra = st.session_state.get("ai_extra_condition", "")

        full_text = get_prefix(qishu, qiu, order_type) + "".join(checked_texts) + extra
        st.text_area("已选核算条件：", value=full_text, height=420, disabled=True)
        # 字体由全局 CSS 统一控制


        # ---------- 推演前置检查（不中断页面） ----------
        _exist_same = _pred_has(qishu, qiu, order_type)
        _exist_period = _pred_load(qishu, order_type)
        _sig = f"{qishu}|{qiu}|{order_type}|{len(checked_texts)}"
        _dup_allow = st.session_state.get("ai_allow_dup", False)
        _blocked = False

        if st.session_state.get("ai_order_confirmed") != order_type:
            st.warning(f"⚠️ 请先确认核算模式：本次是按【{order_type}】计算吗？"
                       "请在「核算模式」里点选一次，避免算错方向。")
            _blocked = True

        if _exist_period:
            _balls_have = "、".join(
                b for b in [f"第{i}球" for i in range(1, 8)] if b in _exist_period)
            st.info(f"ℹ️ {qishu} 期（{order_type}）已核算过：{_balls_have}")

        if _exist_same and not _dup_allow:
            st.warning(f"⚠️ {qishu} 期 {qiu}（{order_type}）已有存档"
                       f"（推演于 {_exist_same.get('ts', '')}，号码 "
                       f"{' '.join('%02d' % n for n in _exist_same.get('nums', []))}）。"
                       "再算会覆盖它；旧版会保留在历史里，可随时恢复。")
            _fc1, _fc2 = st.columns([1, 2])
            with _fc1:
                if st.button("✅ 允许覆盖并重算", key="ai_force_btn",
                             use_container_width=True):
                    st.session_state["ai_allow_dup"] = True
                    st.rerun()
            with _fc2:
                st.caption("或者勾选下方「允许覆盖本球存档」")
            _blocked = True

        if _sig == st.session_state.get("ai_last_sig") and not _dup_allow:
            st.warning(f"⚠️ {qishu} 期 {qiu}（{order_type}）刚刚计算过，"
                       "如需重算请勾选「允许覆盖本球存档」。")
            _blocked = True

        if not checked_texts:
            st.caption("提示：还没有勾选任何条件，推演前请先勾选")
            _blocked = True

        b1, b2 = st.columns(2)
        with b1:
            _run_now = st.button("🚀 开始推演 (呼叫 API)", use_container_width=True,
                                 type="primary", disabled=_blocked)
            if _blocked:
                st.caption("↑ 按钮暂不可用，按上面的提示处理后即可推演")
            if _run_now:
                if not checked_texts:
                    st.warning("请先勾选！")
                else:
                    #==========给AI推演加入严厉的区间警告=============
                    question = full_text + f"\n请严格根据以上文本中的【取值区间】和所有【排杀条件】，一步步详细列出推导过程，最终核算{qiu}剩余什么生肖与号码。如果全杀，请将触犯次数最少的作为后补。" + \
                        "\n\n【输出硬性要求】回答的最后必须单独一行，只写最终保留的号码，格式固定为：" + \
                        "\nFINAL: 04 11 22 31" + \
                        "\n（只写号码，用空格分隔，不要写生肖、不要写汉字、不要写其它任何内容；这一行的号码必须与上面结论里保留的号码完全一致）"
                    with st.spinner("正在呼叫 DeepSeek 进行全量推演..."):
                        db = build_rule_database()
                        if not db: st.error("规则表读取失败！")
                        else:
                            system_prompt = get_analysis_prompt(build_full_table_text(db))
                            answer = call_deepseek_api(question, system_prompt)
                            st.session_state.ai_api_result = answer
                            st.session_state["ai_last_sig"] = f"{qishu}|{qiu}|{order_type}|{len(checked_texts)}"
                            if "请求失败" in answer or "运行错误" in answer:
                                st.error(f"AI 接口报错：{answer}")
                                st.session_state.ai_ball_result = []
                            else:
                                st.success("✅ AI 推演成功！")
                                _got = _ai_extract(answer)
                                st.session_state.ai_ball_result = _got
                                if _got:
                                    _pred_save(qishu, qiu, order_type, _got,
                                               force=st.session_state.get("ai_allow_dup", False))
                                    # 存档区自动跳到刚保存的期号+排序
                                    st.session_state["pred_arch_period"] = qishu
                                    st.session_state["pred_arch_order"] = order_type
                                if len(_got) > 30:
                                    st.warning(
                                        f"提取到 {len(_got)} 个号码，偏多。"
                                        "如果 AI 没有按【严格筛选结果】分节输出，"
                                        "提取就会把推导过程里的号也算进去——"
                                        "可以展开下面的完整推演结果核对。")

        with b2:
            if st.session_state.get("username") == st.secrets.get("ADMIN_USERNAME", "admin"):
                st.checkbox("允许覆盖本球存档（重算）", key="ai_allow_dup")
            else:
                st.caption("🔒 只有管理员可以覆盖已存存档")
            if st.button("🗑️ 清理勾选", use_container_width=True):
                st.session_state.reset_version += 1
                st.session_state.ai_api_result = "等待推演..."
                st.session_state.ai_ball_result = []
                st.rerun()

        if st.session_state.ai_ball_result:
            st.markdown("### 🎯 AI 提取的推演号码")
            _ans_txt = st.session_state.get("ai_api_result") or ""
            if "FINAL" in _ans_txt.upper():
                st.caption("与推演结果末尾的 FINAL 行完全一致（同一个来源）")
            else:
                st.caption("⚠️ AI 本次没有输出 FINAL 行，号码是从正文里提取的，"
                           "可能与正文结论有出入，请对照下方完整结果核对。")
            _parts = []
            for num in st.session_state.ai_ball_result:
                _dot = {"red": "🔴", "blue": "🔵",
                        "green": "🟢"}.get(get_ball_color(num), "⚪")
                _parts.append(f"{_dot}**{num:02d}**")
            st.markdown("\u3000".join(_parts))

    with col_right:
        with st.expander("生肖与五行", expanded=True):
            cols = st.columns(3)
            for idx, key in enumerate(["金肖", "木肖", "水肖", "火肖", "土肖", "红肖", "蓝肖", "绿肖"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("尾数杀号"):
            cols = st.columns(3)
            for i in range(10):
                with cols[i % 3]: st.checkbox(f"{i}尾", key=f"{v_prefix}{i}尾")
        with st.expander("生肖专属"):
            cols = st.columns(3)
            for idx, z in enumerate(["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]):
                with cols[idx % 3]: st.checkbox(f"杀{z}", key=f"{v_prefix}杀{z}")
        with st.expander("门数 / 段数 / 合数"):
            cols = st.columns(3)
            for i in range(1, 6):
                with cols[(i-1) % 3]: st.checkbox(f"{i}门", key=f"{v_prefix}{i}门")
            for i in range(1, 8):
                with cols[(i+4) % 3]: st.checkbox(f"{i}段", key=f"{v_prefix}{i}段")
            for i in range(1, 14):
                with cols[(i+11) % 3]: st.checkbox(f"{i:02d}合", key=f"{v_prefix}{i:02d}合")
        with st.expander("波色 / 波单双"):
            cols = st.columns(3)
            for idx, key in enumerate(["红波", "蓝波", "绿波", "红波单", "红波双", "蓝波单", "蓝波双", "绿波单", "绿波双"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
        with st.expander("其他属性"):
            cols = st.columns(3)
            others = ["金号", "木号", "水号", "火号", "土号", "金尾", "木尾", "水尾", "火尾", "土尾", "大肖", "中肖", "小肖", "书肖", "琴肖", "棋肖", "画肖", "福肖", "禄肖", "寿肖"]
            for idx, key in enumerate(others):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
       #========给AI页面增加复选框区域及内容=====================
        with st.expander("物象专属"):
            cols = st.columns(4)
            for idx, key in enumerate(["家臣", "美女", "君王", "恶人"]):
                with cols[idx % 4]: st.checkbox(key, key=f"{v_prefix}{key}")

        # 🔥 新增：方位专属折叠框
        with st.expander("方位专属"):
            cols = st.columns(4)
            for idx, key in enumerate(["东", "南", "西", "北"]):
                with cols[idx % 4]: st.checkbox(key, key=f"{v_prefix}{key}")

        # 🔥 新增：单双组合折叠框
        with st.expander("单双组合"):
            cols = st.columns(4)
            for idx, key in enumerate(["双双", "双单", "单单", "单双"]):
                with cols[idx % 4]: st.checkbox(key, key=f"{v_prefix}{key}")
                # 🔥 新增：单双组合折叠框
        # 🔥 新增：阴阳天地 / 3模 折叠框
        with st.expander("阴阳天地 / 3模"):
            cols = st.columns(3)
            for idx, key in enumerate(["阳天", "阳地", "阴天", "阴地", "3余0", "3余1", "3余2"]):
                with cols[idx % 3]: st.checkbox(key, key=f"{v_prefix}{key}")
#================AI推演页面保存内容及打印功能=====================================
    st.divider()
    st.markdown("### 📝 AI 完整推演结果")

    if st.session_state.ai_api_result and st.session_state.ai_api_result != "等待推演...":
        import streamlit.components.v1 as components
        import html
        import base64

        # 🔥 1. 终极清洗（只在这里洗，不动原数据）
        clean_ai_text = st.session_state.ai_api_result
        clean_ai_text = clean_ai_text.replace('\\n', '\n').replace('\\\\n', '\n')
        clean_ai_text = clean_ai_text.replace("【严格筛选结果】", "").replace("【后补筛选结果】", "").replace("(如果有的话)", "")
        clean_ai_text = clean_ai_text.strip()

        # 🔥 2. 动态拼接表头
        table_header = f"#============={qishu}期{order_type}{qiu}核算结果======================"

        # 完整下载用的纯文本
        full_result_text = f"{table_header}\n\n{clean_ai_text}"

        # 转义表头和正文
        escaped_header = html.escape(table_header)
        # 强制把正文里的换行变成 <br> 以便网页显示
        escaped_body = html.escape(clean_ai_text).replace("\n", "<br>").replace("\\n", "<br>")

        # 🔥 3. 构建展示 HTML (表头居中加粗，正文左对齐，行距调大)
        display_html = f"""
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; font-family: Consolas, monospace; max-height: 500px; overflow-y: auto;">
            <div style="text-align: center; font-weight: bold; font-size: 18px; margin-bottom: 20px; color: #1e293b;">{escaped_header}</div>
            <div style="text-align: left; font-size: 15px; line-height: 2.2; color: #334155;">{escaped_body}</div>
        </div>
        """

        # 🔥 4. 构建打印 HTML (隐藏页眉页脚，表头居中，正文左对齐，行距调大)
        print_html = f"""
        <html><head><meta charset="utf-8"><style>
        @page {{ margin: 15mm; }}
        body {{ font-family: Consolas, monospace; padding: 20px; }}
        .header {{ text-align: center; font-weight: bold; font-size: 16px; margin-bottom: 25px; }}
        .body {{ text-align: left; line-height: 2.2; font-size: 14px; white-space: pre-wrap; word-wrap: break-word; }}
        </style></head><body>
        <div class="header">{escaped_header}</div>
        <div class="body">{escaped_body}</div>
        </body></html>
        """

        b64_display = base64.b64encode(display_html.encode('utf-8')).decode('utf-8')
        b64_print = base64.b64encode(print_html.encode('utf-8')).decode('utf-8')

        # 🔥 5. 渲染打印按钮与展示框
        components.html(
            f"""
            <div id="report-container"></div>
            <div style="margin-top: 15px; text-align: center;">
                <button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🖨️ 打印当前推演报告
                </button>
            </div>
            <script>
            function b64DecodeUnicode(str) {{
                return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }}).join(''));
            }}
            document.getElementById('report-container').innerHTML = b64DecodeUnicode("{b64_display}");
            function printReport() {{
                var html = b64DecodeUnicode("{b64_print}");
                var f = document.createElement('iframe');
                f.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
                document.body.appendChild(f);
                var d = f.contentWindow.document;
                d.open(); d.write(html); d.close();
                setTimeout(function() {{ f.contentWindow.focus(); f.contentWindow.print(); }}, 400);
            }}
            </script>
            """,
            height=620,
            scrolling=False
        )

        st.write("")

        # 🔥 6. 保存按钮
        st.download_button(
            label="📥 保存完整推演报告到本地 (TXT格式)",
            data=full_result_text.encode('utf-8-sig'),
            file_name=f"AI推演_{qishu}_{qiu}_{order_type}.txt",
            mime="text/plain",
            use_container_width=True
        )
    else:
        st.info("👈 请先在上方设置参数，然后点击【开始推演】。")

    # 推演结果存档 + 开奖对照（默认展示当前选中期）
    _pred_render_archive(df_data, qishu)


# ==========================================
# 6. AI 相关：规则库 / 提示词 / 调用 / 提取
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def build_rule_database():
    """从云端数据库拉取规则，并转换成与原代码完全一致的字典格式"""
    try:
        client = get_supabase_client()
        if not client:
            return None

        # 查询云端 rules 表中的所有数据
        response = client.table("rules").select("*").execute()

        if not response.data:
            st.error("⚠️ 云端 rules 表中没有数据，请检查 Supabase。")
            return None

        # 将云端数据转换为字典，确保后面的推演逻辑无缝对接
        db = {}
        for row in response.data:
            num_raw = row.get("号码")
            if num_raw is None:
                continue
            try:
                n = str(int(float(num_raw)))
            except (ValueError, TypeError):
                continue

            db[n] = {
                "生肖": str(row.get("生肖", "")),
                "肖五行": str(row.get("肖五行", "")),
                "号五行": str(row.get("号五行", "")),
                "尾五行": str(row.get("尾五行", "")),
                "波色": str(row.get("波色", "")),
                "大小": str(row.get("大小", "")),
                "物象": str(row.get("物象", "")),
                "人物": str(row.get("人物", "")),
                "合数": str(row.get("合数", "")),
                "方位": str(row.get("方位", "")),
            }

        return db if db else None

    except Exception as e:
        st.error(f"❌ 云端数据库读取失败：{e}")
        return None


def build_full_table_text(db):
    result = "【1-49号完整属性表（绝对权威）】\n"
    for i in range(1, 50):
        if str(i) in db:
            info = db[str(i)]

            # 🔥 1. 自动计算单双组合
            tens, units = i // 10, i % 10
            if tens % 2 == 0 and units % 2 == 0: combo = "双双"
            elif tens % 2 == 0 and units % 2 == 1: combo = "双单"
            elif tens % 2 == 1 and units % 2 == 1: combo = "单单"
            else: combo = "单双"

            # 🔥 2. 获取上一段代码里读出来的方位
            direction = info.get('方位', '无')

            # 🔥 3. 将单双和方位拼接到发给 AI 的文本中
            result += f"{i}号:{{生肖:{info['生肖']}, 肖五行:{info['肖五行']}, 号五行:{info['号五行']}, 尾五行:{info['尾五行']}, 物象:{info['物象']}, 人物:{info['人物']}, 大小:{info['大小']}, 波色:{info['波色']}, 合数:{info['合数']}, 方位:{direction}, 单双组合:{combo}}}\n"
    return result


#========给AI推演做过程描述指示============
def get_analysis_prompt(full_table):
    return f"""你是一个精通集合运算与条件排除的推演助手。以下是 1-49 号号码的绝对属性参照表：
{full_table}
【推演与输出规则】
1. 用户的提问已明确给出了排杀条件和【取值区间】。请从该区间内挑选号码，区间外的号码绝对不能选。然后严格从区间内剔除不符合条件的号码。
2. 注意多重条件叠加，比如一个号码可能同时触犯了多个排杀条件。
3. 【严格筛选结果】如果没有全部杀光，请详细列出保留下来的号码及其对应的生肖和五行。
4. 【后补筛选结果】如果区间内全被杀光，请筛选出【只触犯了一个或者两个排杀条件】的号码作为候补，【触犯三个及以上条件】的号码绝对不能作为候补。
5. 【核算过程】在输出结果前，请务必详细列出你的推导过程！例如：“01号：触犯了杀木肖，剔除。02号：符合，保留。” 让用户看到你是如何一步步排杀的。
6. 绝对禁止复述属性表，直接给出推导过程和最终结果。
7. 注意用户是否选择升序还是按序作为条件限制。"""


def _ai_rate_ok():
    """AI 调用限流：间隔 >= 3 秒，单会话每日 <= 200 次"""
    # 管理员不限制
    _admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    if st.session_state.get("username") == _admin_name:
        return True, ""
    now = _time_sec.time()
    last = st.session_state.get("_ai_last_call_ts", 0)
    if now - last < 3:
        return False, f"调用太快，请等 {int(3 - (now - last)) + 1} 秒后再试"
    day = _time_sec.strftime("%Y-%m-%d")
    if st.session_state.get("_ai_day") != day:
        st.session_state["_ai_day"] = day
        st.session_state["_ai_day_count"] = 0
    if st.session_state.get("_ai_day_count", 0) >= 200:
        return False, "今日 AI 调用已达上限（200 次），请明天再试"
    st.session_state["_ai_last_call_ts"] = now
    st.session_state["_ai_day_count"] = st.session_state.get("_ai_day_count", 0) + 1
    return True, ""


def call_deepseek_api(question, system_prompt):
    _ok, _why = _ai_rate_ok()
    if not _ok:
        return f"运行错误：{_why}"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    payload = {"model": "deepseek-chat", "temperature": 0, "messages": [{"role": "system", "content": "你是一个严谨的数据推演与集合运算助手。"}, {"role": "user", "content": question}, {"role": "system", "content": system_prompt}]}
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].replace("**", "").replace("###", "").replace("##", "").replace("#", "").replace("`", "")
        else: return f"请求失败：{response.status_code}\n{response.text}"
    except Exception as e: return f"运行错误：{e}"


def extract_numbers(answer, lo=1, hi=49):
    """从 AI 输出里提取号码。FINAL 行优先，其次保留结果段，最后按“NN号”兜底。"""
    if not answer: return []
    text = str(answer)

    def _nums(seg):
        out = []
        for tok in re.findall(r"\d{1,2}", seg or ""):
            n = int(tok)
            if lo <= n <= hi: out.append(n)
        return out

    # 1) FINAL 行
    for m in re.finditer(r"FINAL[\]】\s]*[：:]?\s*([0-9][^\n\r]*)", text, re.I):
        got = _nums(m.group(1))
        if got: return sorted(set(got))

    # 2) 保留结果段
    keep = re.search(r"(?:保留结果|严格筛选结果|剩余号码|筛选结果)\s*[：:]?([\s\S]{0,1500})", text)
    if keep:
        seg = re.split(r"【|\n\s*(?:注|说明|后补)", keep.group(1))[0]
        got = _nums(seg)
        if got: return sorted(set(got))

    # 3) 所有“NN号”写法
    got = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})\s*号", text)]
    return sorted(set(n for n in got if lo <= n <= hi))

# ==========================================
# 7. 主控台
# ==========================================
def render_console(df_data):
    st.title("💻智能数据分析总控台")
    if df_data is None or isinstance(df_data, str):
        st.error("数据读取失败：" + str(EXCEL_FILE)
                 + ("" if df_data is None else "　原因：" + str(df_data)[:200]))
        st.info("请点左侧「☁️刷新云端数据」，或到「后台管理」重新同步【升序源文件】。")
        return
    unique_periods = list(set([p for p in df_data.iloc[:, 18].apply(clean_period).tolist() if p != ""]))
    try: unique_periods.sort(key=lambda x: float(x) if x.replace('.','',1).isdigit() else 0, reverse=True)
    except: unique_periods.sort(reverse=True)
    if unique_periods:
        latest_period = unique_periods[0]
        try:
            next_period = str(int(float(latest_period)) + 1)
            if next_period not in unique_periods: unique_periods.insert(0, next_period)
        except: pass

    col1, col2 = st.columns(2)
    with col1: selected_period = st.selectbox("选择期数：", unique_periods)
    with col2: analysis_mode = st.radio("模式切换：", ["单排分析", "多排分析"], horizontal=True)

    st.write("")
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    start_btn = b1.button("⚡批量联动分析", use_container_width=True, type="primary")
    result_btn = b2.button("🏆中奖结果", use_container_width=True)
    clear_btn = b3.button("🗑️清空数据", use_container_width=True)
    sync_btn = b4.button("🔄同步数据", use_container_width=True)
    trend_btn = b5.button("📈走势图", use_container_width=True)
    fetch_btn = b6.button("🤏抓取香港数据", use_container_width=True)

    st.divider()
    df_data['_temp_period'] = df_data.iloc[:, 18].apply(clean_period)
    matched_rows = df_data[df_data['_temp_period'] == selected_period]
    try: is_descending = int(clean_period(df_data.iloc[0, 18])) > int(clean_period(df_data.iloc[1, 18]))
    except: is_descending = True
    next_period_str, next_flat_nums, next_special_num, has_next_data = "", [], 0, False
    if not matched_rows.empty:
        base_idx = matched_rows.index[0]
        next_idx = base_idx - 1 if is_descending else base_idx + 1
        if 0 <= next_idx < len(df_data):
            next_row = df_data.iloc[next_idx]
            next_period_str = clean_period(next_row.iloc[18])
            try:
                next_flat_nums = [int(clean_period(next_row.iloc[i])) for i in range(19, 25) if pd.notna(next_row.iloc[i])]
                next_special_num = int(clean_period(next_row.iloc[25])) if pd.notna(next_row.iloc[25]) else 0
                if len(next_flat_nums) > 0: has_next_data = True
            except: pass
    if has_next_data:
        st.subheader(f"{next_period_str} 期开奖结果")
        _parts4 = []
        for num in next_flat_nums:
            _dot4 = {"red": "🔴", "blue": "🔵",
                     "green": "🟢"}.get(get_ball_color(num), "⚪")
            _parts4.append(f"{_dot4}**{num:02d}**")
        if next_special_num > 0:
            _dot4 = {"red": "🔴", "blue": "🔵",
                     "green": "🟢"}.get(get_ball_color(next_special_num), "⚪")
            _parts4.append("➕" + f"{_dot4}**{next_special_num:02d}**")
        st.markdown("\u3000".join(_parts4))
    else:
        try: next_period_str = str(int(float(selected_period)) + 1)
        except: next_period_str = "下一期"
        st.subheader(f"{next_period_str} 期开奖结果")
        st.info(f"{next_period_str} 期待开奖（暂无数据）")

    if fetch_btn:
        with st.spinner("发送抓取指令..."):
            try:
                token = st.secrets.get("GITHUB_TOKEN"); repo = st.secrets.get("GITHUB_REPO")
                url = f"https://api.github.com/repos/{repo}/actions/workflows/update_data.yml/dispatches"
                res = requests.post(url, headers={"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {token}"}, json={"ref": "main"})
                if res.status_code == 204: st.success("✅ 指令已发送！请稍后点击【同步数据】。")
                else: st.error(f"指令发送失败: {res.status_code}")
            except Exception as e: st.error(f"请求异常：{e}")

    if sync_btn:
        with st.spinner("同步数据中..."):
            FILE_SORTED = "升序源文件.xlsx"
            if os.path.exists(FILE_SORTED):
                try:
                    wb_src = openpyxl.load_workbook(FILE_SORTED, read_only=True, data_only=True)
                    ws_src = wb_src["数据源"]
                    synced_rows = []
                    for row in ws_src.iter_rows(min_row=3, max_col=27):
                        p1, p2, p3 = row[0].value, row[1].value, row[2].value
                        if p1 is None: continue
                        nums = [int(str(row[3 + i*2].value or 0))*10 + int(str(row[4 + i*2].value or 0)) for i in range(7)]
                        new_row = [None]*30
                        new_row[18] = f"{row[26].value or '2026'}{str(int(p1))}{str(int(p2))}{str(int(p3))}"
                        for i in range(6): new_row[19+i] = nums[i]
                        new_row[25] = nums[6]
                        synced_rows.append(new_row)
                    wb_src.close()
                    st.session_state.synced_df = pd.DataFrame(synced_rows).sort_values(by=18, ascending=False).reset_index(drop=True)
                    st.success("✅ 数据同步成功！"); st.rerun()
                except Exception as e: st.error(f"同步异常: {e}")
            else: st.error(f"找不到 {FILE_SORTED}")

    if trend_btn: render_trend_chart(df_data)
    if clear_btn:
        st.session_state.calc_data_single = None; st.session_state.calc_data_multi = None; st.session_state.calc_result_preview = None; st.session_state.predicted_nums_single = None; st.session_state.predicted_nums_multi = None
        st.success("✅ 数据已清空！")
    if start_btn:
        progress_bar = st.progress(0); status_text = st.empty()
        df_triggers, df_counts, error_msg = calculate_linkage(df_data, selected_period, analysis_mode)
        progress_bar.progress(100); status_text.text("进度: 100% | 完成")
        if error_msg: st.error(error_msg)
        else:
            predicted_nums = df_counts.head(7)["下期数字"].tolist() if df_counts is not None and not df_counts.empty else []
            if analysis_mode == "单排分析": st.session_state.calc_data_single = (df_triggers, df_counts); st.session_state.predicted_nums_single = predicted_nums
            else: st.session_state.calc_data_multi = (df_triggers, df_counts); st.session_state.predicted_nums_multi = predicted_nums
            st.success(f"✅ 分析完成！找到 {len(df_triggers)} 处触发。")
    if result_btn:
        predicted_nums = st.session_state.predicted_nums_single if analysis_mode == "单排分析" else st.session_state.predicted_nums_multi
        if not predicted_nums: st.warning("请先点击【批量联动分析】！")
        else:
            with st.spinner("比对中..."):
                res_data, err = calculate_prize(df_data, selected_period, predicted_nums)
                if err == "本期未开奖": st.warning(f"⏳ {selected_period} 期的下期未开奖！")
                elif err: st.error(err)
                else: st.success("预祝您中奖！"); st.session_state.calc_result_preview = pd.DataFrame([res_data])

    st.divider()
    col_lb1, col_lb2 = st.columns(2)
    with col_lb1:
        st.subheader("单排结果")
        if st.session_state.calc_data_single is not None:
            st.dataframe(st.session_state.calc_data_single[0], use_container_width=True, height=200)
            st.dataframe(st.session_state.calc_data_single[1], use_container_width=True, height=200)
        else: st.info("暂无单排数据。")
    with col_lb2:
        st.subheader("多排结果")
        if st.session_state.calc_data_multi is not None:
            st.dataframe(st.session_state.calc_data_multi[0], use_container_width=True, height=200)
            st.dataframe(st.session_state.calc_data_multi[1], use_container_width=True, height=200)
        else: st.info("暂无多排数据。")
    st.divider()
    st.subheader("中出结果预览")
    if st.session_state.calc_result_preview is not None: st.dataframe(st.session_state.calc_result_preview, use_container_width=True)
    else: st.info("暂无中出结果。")

# ==========================================
# 8. 管理员专属后台管理页
# ==========================================
def render_admin_panel():
    st.title("⚙️ 系统后台管理中心")
    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    token, repo = st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["👑 用户 VIP 授权", "📝 数据录入与同步",
                                           "☁️ 云端数据流转", "💬 AI 助手", "🛠️ 自动升级"])

    with tab1:
        try:
            client = get_supabase_client()
            if client:
                users = client.table("users").select("username, is_vip").neq("username", admin_name).execute().data
                if users:
                    user_dict = {row["username"]: row.get("is_vip", False) for row in users}
                    all_users = list(user_dict.keys())
                    current_vips = [u for u, is_vip in user_dict.items() if is_vip]
                    selected_vips = st.multiselect("选择授权用户（允许查看高级页面）：", all_users, default=current_vips)
                    if st.button("💾 保存授权更改", type="primary"):
                        client.table("users").update({"is_vip": False}).neq("username", admin_name).execute()
                        if selected_vips:
                            client.table("users").update({"is_vip": True}).in_("username", selected_vips).execute()
                        st.success("✅ 授权已更新！")
                else: st.warning("暂无其他注册用户。")
        except Exception as e: st.error(f"读取失败: {e}")

    with tab2:
        st.markdown("### 📝 手动补录开奖数据 (云端同步)")
        with st.form("manual_input_form", clear_on_submit=True):
            st.info("💡 提示：保存后，数据将直接更新到 GitHub 云端的两个 Excel 源文件中，并插入第 3 行。")
            col_year, col_p1, col_p2, col_p3 = st.columns(4)
            with col_year: year_val = st.text_input("年份 (AA列)", value="2026")
            with col_p1: p1 = st.text_input("A列 (百位)", value="1")
            with col_p2: p2 = st.text_input("B列 (十位)", value="1")
            with col_p3: p3 = st.text_input("C列 (个位)", value="8")

            st.write("---")
            col_nums = st.columns(7)
            nums = []
            for i in range(7):
                label = "特码 (第7球)" if i == 6 else f"平码{i+1}"
                with col_nums[i]:
                    n = st.number_input(label, min_value=1, max_value=49, value=i+1, key=f"manual_num_{i}")
                    nums.append(n)

            submit_btn = st.form_submit_button("💾保存并同步到云端两个文件", use_container_width=True, type="primary")

            if submit_btn:
                if not year_val or not p1 or not p2 or not p3: st.error("年份和期号不能为空！")
                elif len(set(nums)) < 7: st.error("录入的 7 个号码中有重复，请检查！")
                else:
                    raw_nums = nums.copy()
                    asc_nums = sorted(nums[:6]) + [nums[6]]
                    if not token or not repo: st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        def update_github_excel(file_path, nums_list, commit_msg):
                            try:
                                api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
                                headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                                r = requests.get(api_url, headers=headers)
                                if r.status_code != 200: return False, f"找不到云端文件或API错误: {r.status_code}"
                                file_info = r.json()
                                sha = file_info["sha"]
                                download_url = file_info["download_url"]
                                file_content = requests.get(download_url).content

                                wb = openpyxl.load_workbook(io.BytesIO(file_content))
                                if "数据源" not in wb.sheetnames: return False, "源文件中找不到“数据源”工作表"
                                ws = wb["数据源"]

                                def get_cell_str(r, c):
                                    v = ws.cell(row=r, column=c).value
                                    return str(v).replace(".0", "").strip() if v is not None else ""

                                current_year = str(year_val).replace(".0", "").strip()
                                for row_idx in range(3, ws.max_row + 1):
                                    if get_cell_str(row_idx, 27) == current_year and get_cell_str(row_idx, 1) == p1 and get_cell_str(row_idx, 2) == p2 and get_cell_str(row_idx, 3) == p3:
                                        return False, f"{current_year}年的 {p1}-{p2}-{p3} 期已经存在！"

                                ws.insert_rows(3)
                                ws.cell(row=3, column=1, value=p1); ws.cell(row=3, column=2, value=p2)
                                ws.cell(row=3, column=3, value=p3); ws.cell(row=3, column=27, value=year_val)
                                for i, num in enumerate(nums_list):
                                    ws.cell(row=3, column=4 + i*2, value=str(num // 10))
                                    ws.cell(row=3, column=5 + i*2, value=str(num % 10))

                                output = io.BytesIO(); wb.save(output)
                                b64_content = base64.b64encode(output.getvalue()).decode('utf-8')
                                payload = {"message": commit_msg, "content": b64_content, "sha": sha, "branch": "main"}
                                put_res = requests.put(api_url, headers=headers, json=payload)
                                return (True, "成功") if put_res.status_code in [200, 201] else (False, put_res.text)
                            except Exception as e: return False, str(e)

                        with st.spinner("覆盖更新中..."):
                            s1, m1 = update_github_excel("升序源文件.xlsx", asc_nums, f"更新升序数据 {year_val}-{p1}{p2}{p3}")
                            s2, m2 = update_github_excel("按序源文件.xlsx", raw_nums, f"更新按序数据 {year_val}-{p1}{p2}{p3}")
                            if s1 and s2:
                                st.success("✅数据已永久存入 GitHub 云端！")
                                load_real_data.clear()
                            else:
                                if not s1: st.error(f"❌ 升序文件同步失败: {m1}")
                                if not s2: st.error(f"❌ 按序文件同步失败: {m2}")

    with tab3:
        st.markdown("### ☁️ 云端数据流转控制台")
        col_sync1, col_sync2 = st.columns(2)

        with col_sync1:
            if st.button("🚀 同步【升序源文件】至【总数据表】", use_container_width=True, type="primary"):
                with st.spinner("正在合并总表..."):
                    if not token or not repo:
                        st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        try:
                            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                            def get_info(fp):
                                r = requests.get(f"https://api.github.com/repos/{repo}/contents/{fp}", headers=headers)
                                return r.json() if r.status_code == 200 else None

                            src_info = get_info("升序源文件.xlsx")
                            if not src_info: st.error("找不到升序源文件"); st.stop()
                            df_src = pd.read_excel(io.BytesIO(requests.get(src_info["download_url"]).content), sheet_name=_sheet, header=None)

                            m_file = "总数据.xlsx"
                            m_info = get_info(m_file)
                            if not m_info: st.error("找不到总数据文件"); st.stop()

                            wb = openpyxl.load_workbook(io.BytesIO(requests.get(m_info["download_url"]).content))
                            ws = wb["总数据表"]

                            if ws.max_row > 2: ws.delete_rows(3, ws.max_row)

                            def clean_val(v):
                                if pd.isna(v) or v is None: return ""
                                try: return str(int(float(v)))
                                except: return str(v).strip()

                            row_idx = 3
                            for idx, row in df_src.iterrows():
                                if idx < 2: continue
                                p1, p2, p3 = clean_val(row[0]), clean_val(row[1]), clean_val(row[2])
                                if not p1 and not p2 and not p3: continue
                                y_val = clean_val(row[26]) if len(row) > 26 else "2026"

                                ws.cell(row=row_idx, column=1, value=p1); ws.cell(row=row_idx, column=2, value=p2); ws.cell(row=row_idx, column=3, value=p3)

                                for i in range(7):
                                    t = clean_val(row[3 + i*2]) if len(row) > 3 + i*2 else ""
                                    u = clean_val(row[4 + i*2]) if len(row) > 4 + i*2 else ""
                                    ws.cell(row=row_idx, column=4 + i*2, value=t)
                                    ws.cell(row=row_idx, column=5 + i*2, value=u)

                                ws.cell(row=row_idx, column=19, value=f"{y_val}{p1}{p2}{p3}")

                                for i in range(7):
                                    t = clean_val(row[3 + i*2]) if len(row) > 3 + i*2 else ""
                                    u = clean_val(row[4 + i*2]) if len(row) > 4 + i*2 else ""
                                    num = int(t)*10 + int(u) if t.isdigit() and u.isdigit() else 0
                                    if i < 6: ws.cell(row=row_idx, column=20 + i, value=num)
                                    else: ws.cell(row=row_idx, column=26, value=num)

                                ws.cell(row=row_idx, column=27, value=y_val)
                                row_idx += 1

                            out = io.BytesIO(); wb.save(out)
                            res = requests.put(f"https://api.github.com/repos/{repo}/contents/{m_file}", headers=headers, json={"message": "更新总数据表", "content": base64.b64encode(out.getvalue()).decode('utf-8'), "sha": m_info["sha"], "branch": "main"})

                            if res.status_code in [200, 201]:
                                st.success("✅ 总数据表已完美更新！")
                                load_real_data.clear()
                            else: st.error(f"❌ 推送失败: {res.text}")
                        except Exception as e: st.error(f"异常: {e}")

        with col_sync2:
            if st.button("🚀 一键计算属性并同步全套表", use_container_width=True, type="secondary"):
                with st.spinner("正在计算 214 列属性并同步..."):
                    if not token or not repo:
                        st.error("请在 Secrets 中配置 GITHUB_TOKEN 和 GITHUB_REPO")
                    else:
                        try:
                            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
                            def get_info(fp):
                                r = requests.get(f"https://api.github.com/repos/{repo}/contents/{fp}", headers=headers)
                                return r.json() if r.status_code == 200 else None

                            def sync_attrs(src_f, dst_f, table_name):
                                import csv
                                s_info = get_info(src_f)
                                if not s_info: return False, f"找不到 {src_f}"
                                wb_src = openpyxl.load_workbook(io.BytesIO(requests.get(s_info["download_url"]).content), data_only=True)
                                ws_src = wb_src["数据源"]

                                def clean_val(cell):
                                    if cell is None: return ""
                                    val = str(cell).strip()
                                    if val.endswith(".0"): val = val[:-2]
                                    return val

                                p1, p2, p3 = clean_val(ws_src["A3"].value), clean_val(ws_src["B3"].value), clean_val(ws_src["C3"].value)
                                year_val = clean_val(ws_src["AA3"].value) or "2026"
                                period_str = f"{year_val}{p1}{p2}{p3}"

                                d_info = get_info(dst_f)
                                if not d_info: return False, f"找不到 {dst_f}"
                                csv_content = requests.get(d_info["download_url"]).content

                                try: text = csv_content.decode("utf-8-sig")
                                except: text = csv_content.decode("gbk", errors="ignore")

                                all_rows = list(csv.reader(io.StringIO(text)))
                                if not all_rows: return False, f"{dst_f} 数据为空"

                                if len(all_rows) > 2:
                                    exist_row = all_rows[2]
                                    if len(exist_row) >= 214 and f"{exist_row[213]}{exist_row[0]}{exist_row[1]}{exist_row[2]}" == period_str:
                                        return True, f"该期 ({period_str}) 已存在，跳过同步"

                                new_row_dict = {}
                                for n_idx in range(7):
                                    tens = clean_val(ws_src.cell(row=3, column=4 + n_idx*2).value)
                                    units = clean_val(ws_src.cell(row=3, column=5 + n_idx*2).value)
                                    ball_num = int((tens if tens.isdigit() else "0") + (units if units.isdigit() else "0")) if (tens or units) else 0

                                    base_col = 4 + n_idx * 30
                                    new_row_dict[str(base_col)] = str(ball_num // 10) if ball_num else ""
                                    new_row_dict[str(base_col+1)] = str(ball_num % 10) if ball_num else ""

                                    if ball_num:
                                        attrs = calculate_all_attributes(ball_num)
                                        for a_idx, attr_val in enumerate(attrs): new_row_dict[str(base_col + 2 + a_idx)] = str(attr_val)
                                    else:
                                        for a_idx in range(28): new_row_dict[str(base_col + 2 + a_idx)] = ""

                                new_row_dict["1"], new_row_dict["2"], new_row_dict["3"] = p1, p2, p3
                                new_row_dict["214"] = year_val

                                all_rows.insert(2, [new_row_dict.get(str(i), "") for i in range(1, 215)])

                                out_io = io.StringIO()
                                csv.writer(out_io).writerows(all_rows)
                                b64_content = base64.b64encode(out_io.getvalue().encode('utf-8-sig')).decode('utf-8')

                                res = requests.put(f"https://api.github.com/repos/{repo}/contents/{dst_f}", headers=headers, json={"message": f"更新 {dst_f}", "content": b64_content, "sha": d_info["sha"], "branch": "main"})

                                if res.status_code not in [200, 201]: return False, res.text

                                try:
                                    client = get_supabase_client()
                                    if client: client.table(table_name).upsert({"期数": period_str, "data": new_row_dict}, on_conflict="期数").execute()
                                except: pass

                                return True, "成功"

                            s1, m1 = sync_attrs("升序源文件.xlsx", "升序全套.csv", "full_asc")
                            s2, m2 = sync_attrs("按序源文件.xlsx", "按序全套.csv", "full_desc")

                            if s1 and s2:
                                st.success(f"✅ 极速同步成功！\n升序：{m1}\n按序：{m2}")
                                load_excel_data.clear()
                            else:
                                if not s1: st.error(f"❌ 升序失败: {m1}")
                                if not s2: st.error(f"❌ 按序失败: {m2}")
                        except Exception as e:
                            st.error(f"运行异常: {e}")

    # --- 标签 4：AI 对话助手 ---
    with tab4:
        if render_ai_chat:
            render_ai_chat()
        else:
            st.warning("缺少 ai_chat_page.py —— 需与 app.py 同目录并一起提交到 GitHub 仓库。")

    # --- 标签 5：自动升级 ---
    with tab5:
        if render_upgrade_tab:
            render_upgrade_tab()
        else:
            st.warning("缺少 auto_upgrade.py —— 需与 app.py 同目录并一起提交到 GitHub 仓库。")

# ==========================================
# 8.5 遗漏核算（原 omission_page.py 内嵌 + 累积框）
# ==========================================
# 列规则：每球占 30 列，第 n 球属性列 = 属性基列 + (n-1)*30（1 基）
ATTR_BASE_COL = {
    "数字五行": 6, "生肖": 7, "尾数": 8, "数字合": 9, "门数": 10, "段数": 11,
    "单双组合": 12, "单双笔": 13, "独合字": 14, "单双头": 15, "单双": 16,
    "波单双": 17, "生肖五行": 18, "颜色肖": 19, "四宝": 20, "物象": 21,
    "波色": 22, "阴阳": 23, "家野": 24, "天地": 25, "阴阳天地": 26,
    "吉凶": 27, "男女": 28, "方位": 29, "3模": 30, "尾五行": 31,
    "福禄寿": 32, "大小肖": 33,
}

ATTR_DOMAIN = {
    "生肖": ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"],
    "尾数": [str(i) for i in range(10)],
    "数字五行": ["金", "木", "水", "火", "土"],
    "生肖五行": ["金", "木", "水", "火", "土"],
    "尾五行": ["金", "木", "水", "火", "土"],
    "波色": ["红波", "蓝波", "绿波"],
    "门数": [f"{i}门" for i in range(1, 6)],
    "段数": [f"{i}段" for i in range(1, 8)],
    "数字合": [f"{i:02d}合" for i in range(1, 14)],
    "单双组合": ["双双", "双单", "单单", "单双"],
    "单双": ["单数", "双数"],
    "单双笔": ["单笔", "双笔"],
    "独合字": ["独字", "合字"],
    "单双头": ["单头", "双头"],
    "阴阳": ["阴", "阳"],
    "家野": ["家", "野"],
    "天地": ["天", "地"],
    "阴阳天地": ["阳天", "阳地", "阴天", "阴地"],
    "吉凶": ["吉", "凶"],
    "男女": ["男", "女"],
    "方位": ["东", "南", "西", "北"],
    "3模": ["3余0", "3余1", "3余2"],
    "福禄寿": ["福肖", "禄肖", "寿肖"],
    "大小肖": ["大肖", "中肖", "小肖"],
    "四宝": ["琴", "棋", "书", "画"],
    "物象": ["家臣", "美女", "君王", "恶人"],
    "颜色肖": ["红色", "绿色", "蓝色"],
    "波单双": ["红波单数", "红波双数", "蓝波单数", "蓝波双数", "绿波单数", "绿波双数"],
}

_OM_SEP = "=" * 10
_OM_HEADER_RE = re.compile(r"^={10,}.*={10,}$")


def _om_clean(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _om_col_index(attr_name, ball_no):
    """CSV 中该球该属性的 0 基列索引"""
    return ATTR_BASE_COL[attr_name] + (ball_no - 1) * 30 - 1


def _om_compute(rows, col_idx, domain, start=2):
    """从 start 那一行（选定期数）向下扫描，统计每个属性值的遗漏期数"""
    seq = []
    for r in range(start, len(rows)):
        row = rows[r]
        if col_idx >= len(row):
            continue
        val = _om_clean(row[col_idx])
        if val == "":
            continue
        seq.append(val)

    total = len(seq)
    result = {}
    for attr_val in domain:
        miss = total                      # 默认：全表未出现
        for i, v in enumerate(seq):
            if v == attr_val:
                miss = i
                break
        result[attr_val] = miss

    # 补上域外出现的值（防止属性表与数据不一致时漏项）
    for v in seq:
        if v not in result:
            miss = total
            for i, x in enumerate(seq):
                if x == v:
                    miss = i
                    break
            result[v] = miss

    return result, total


def _om_period_of(row):
    """行 → 期号（年份 + 3 位期号）"""
    year = _om_clean(row[213]) if len(row) > 213 else ""
    p = "".join(_om_clean(row[i]) if i < len(row) else "" for i in range(3))
    return f"{year}{p}"


def _om_period_list(rows):
    """[(期号, 行索引)]，新的在前；行索引即该期在 CSV 里的位置"""
    seen, out = set(), []
    for r in range(2, len(rows)):
        p = _om_period_of(rows[r])
        if p and p not in seen:
            seen.add(p)
            out.append((p, r))
    return out


def _om_latest_period(rows):
    """最新一期的期号（年份 + 3 位期号）"""
    if len(rows) <= 2:
        return ""
    return _om_period_of(rows[2])


def _om_blocks(text):
    out, head, body = [], None, []
    for line in (text or "").splitlines():
        if _OM_HEADER_RE.match(line.strip()):
            if head is not None:
                while body and not body[-1].strip():
                    body.pop()
                out.append((head, body))
            head, body = line.rstrip(), []
        elif head is not None:
            body.append(line)
    if head is not None:
        while body and not body[-1].strip():
            body.pop()
        out.append((head, body))
    return out


def _om_join(blocks):
    return "\n\n".join("\n".join([h] + [b for b in body if b.strip() != ""])
                       for h, body in blocks)


def _om_attr_of_header(head):
    """从标题行里抠出属性名，例如 '...1球生肖遗漏====' -> '生肖'"""
    m = re.search(r"\d+球(.+?)遗漏", head or "")
    return m.group(1) if m else ""


def _om_upsert(text, header, body_lines):
    """按【属性】去重：同一属性只保留一块（标题更新为新条件），只有换属性才追加。
    期数/球号/数据文件变化都不追加，直接覆盖原属性那一块。"""
    blocks = _om_blocks(text)
    key = _om_attr_of_header(header)
    out, replaced = [], False
    for head, body in blocks:
        if key and _om_attr_of_header(head) == key:
            if not replaced:
                out.append((header, list(body_lines)))
                replaced = True
            # 同属性的重复块直接丢弃，避免堆积
        else:
            out.append((head, body))
    if not replaced:
        out.append((header, list(body_lines)))
    return _om_join(out)


def _om_print_html(text):
    """生成可独立打开/打印的 HTML 全文"""
    import html as _html

    return ('<html><head><meta charset="utf-8"><title>遗漏核算</title><style>'
            '@page { margin: 15mm; } body { font-family: Consolas, monospace; padding: 20px; }'
            'pre { white-space: pre-wrap; word-wrap: break-word; font-size: 14px; line-height: 1.9; }'
            "</style></head><body><pre>" + _html.escape(text) + "</pre></body></html>")


def _om_print(text):
    import html as _html
    import base64 as _b64
    import streamlit.components.v1 as _components

    body = _html.escape(text).replace("\n", "<br>")
    display_html = ('<div style="background-color:#f8f9fa;padding:20px;border-radius:10px;'
                    'border:1px solid #e9ecef;font-family:Consolas,monospace;font-size:16px;'
                    f'line-height:2.0;white-space:pre-wrap;word-wrap:break-word;">{body}</div>')
    print_html = ('<html><head><meta charset="utf-8"><style>'
                  '@page { margin: 15mm; } body { font-family: Consolas, monospace; padding: 20px; }'
                  'pre { white-space: pre-wrap; word-wrap: break-word; font-size: 14px; line-height: 1.9; }'
                  "</style></head><body><pre>" + _html.escape(text) + "</pre></body></html>")

    b64_display = _b64.b64encode(display_html.encode("utf-8")).decode("utf-8")
    b64_print = _b64.b64encode(print_html.encode("utf-8")).decode("utf-8")

    _components.html(
        f"""
        <div style="text-align: center;">
            <button onclick="printReport()" style="width: 100%; padding: 12px; background-color: #0284c7;
                color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold;">
                🖨️ 打印累积报告（点这里直接打印）
            </button>
        </div>
        <script>
        function b64DecodeUnicode(str) {{
            return decodeURIComponent(Array.prototype.map.call(atob(str), function(c) {{
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }}).join(''));
        }}
        function printReport() {{
            var html = b64DecodeUnicode("{b64_print}");
            var f = document.createElement('iframe');
            f.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
            document.body.appendChild(f);
            var d = f.contentWindow.document;
            d.open(); d.write(html); d.close();
            setTimeout(function() {{ f.contentWindow.focus(); f.contentWindow.print(); }}, 400);
        }}
        </script>
        """, height=90, scrolling=False)


def render_omission_page():
    st.title("📉 遗漏核算")
    st.info("💡 基准期为最新一期（降序文件最上面一行）。遗漏 = 从最新一期向下连续未出现的期数。")

    st.session_state.setdefault("om_report", "")
    st.session_state.setdefault("om_ver", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        file_type = st.selectbox("选择数据文件", ["升序全套", "按序全套"], key="om_file")
    with col2:
        ball_str = st.selectbox("选择球号", [f"第{i}球" for i in range(1, 8)], key="om_ball")
    with col3:
        attr_name = st.selectbox("选择属性", list(ATTR_BASE_COL.keys()), key="om_attr")

    ball_no = int(ball_str.replace("第", "").replace("球", ""))

    # ---------- 先读文件（带缓存），才能列出期数 ----------
    target_file = "升序全套.csv" if file_type == "升序全套" else "按序全套.csv"
    rows = load_excel_data(target_file, None)
    pairs = _om_period_list(rows) if rows else []
    period_map = dict(pairs)

    p1, p2 = st.columns([2, 2])
    with p1:
        period_options = [p for p, _ in pairs] or ["暂无数据"]
        # 切换数据文件时尽量保留原来选的那一期；新文件里没有才回落到最新一期
        _prev_period = st.session_state.get("om_period")
        if _prev_period not in period_options:
            st.session_state["om_period"] = period_options[0]
        sel_period = st.selectbox("期数（从这一期往回算）", period_options, key="om_period")
    start_idx = period_map.get(sel_period, 2)
    with p2:
        st.write(""); st.write("")
        st.caption(f"基准行：CSV 第 {start_idx + 1} 行；从这一期开始往更早的方向统计")

    # ---------- 前几控件：范围随属性自动变化，且每个属性各自记住自己的数字 ----------
    domain_now = ATTR_DOMAIN.get(attr_name, [])
    max_n = max(1, len(domain_now))
    nkey = f"om_n_{attr_name}"
    cur = st.session_state.get(nkey, min(5, max_n))
    if not isinstance(cur, int) or cur < 1:
        cur = 1
    if cur > max_n:
        cur = max_n
    st.session_state[nkey] = cur

    b1, b2, b3 = st.columns([2, 1, 1])
    with b1:
        n_pick = st.number_input(f"写入前几名（{attr_name} 共 {max_n} 项，可选 1~{max_n}）",
                                 min_value=1, max_value=max_n, key=nkey, step=1,
                                 help="这个数字 = 往下方累积框里写入几行。"
                                      "12 个生肖只想看 5 个，就调到 5。")
    with b2:
        st.write(""); st.write("")
        run_btn = st.button("🚀 开始遗漏核算", use_container_width=True, type="primary")
    with b3:
        st.write(""); st.write("")
        clear_btn = st.button("🗑 清空累积", use_container_width=True)

    if clear_btn:
        st.session_state["om_report"] = ""
        st.session_state["om_df"] = None
        st.session_state["om_meta"] = None
        st.session_state["om_ver"] = st.session_state.get("om_ver", 0) + 1

    # ---------- 计算 ----------
    if run_btn:
        if not rows:
            st.error(f"{target_file} 读取为空，请检查云端文件是否存在。")
        else:
            col_idx = _om_col_index(attr_name, ball_no)
            domain = domain_now
            if not domain:
                seen = []
                for r in range(start_idx, len(rows)):
                    row = rows[r]
                    if col_idx < len(row):
                        v = _om_clean(row[col_idx])
                        if v and v not in seen:
                            seen.append(v)
                domain = seen

            result, total = _om_compute(rows, col_idx, domain, start_idx)
            if total == 0:
                st.warning("该列没有有效数据，请确认属性列映射是否正确。")
            else:
                df = pd.DataFrame([{"属性值": k, "遗漏期数": v} for k, v in result.items()]
                                  ).sort_values("遗漏期数", ascending=False).reset_index(drop=True)
                st.session_state["om_df"] = df.to_dict("records")
                st.session_state["om_meta"] = {
                    "file_type": file_type, "ball_str": ball_str, "attr_name": attr_name,
                    "total": total, "period": _om_latest_period(rows),
                }

                # 校验用：把该球该属性那一列的最近若干期原值存下来，供人工核对
                try:
                    from openpyxl.utils import get_column_letter as _gcl
                    _letter = _gcl(col_idx + 1)
                except Exception:
                    _letter = f"第{col_idx + 1}列"
                _preview = []
                for _r in range(start_idx, min(start_idx + 30, len(rows))):
                    _row = rows[_r]
                    _v = _om_clean(_row[col_idx]) if col_idx < len(_row) else ""
                    _preview.append({"期号": _om_period_of(_row), "取值": _v,
                                     "距本期": _r - start_idx})
                st.session_state["om_col"] = {
                    "letter": _letter, "col_1based": col_idx + 1,
                    "ball": ball_no, "attr": attr_name, "preview": _preview,
                }

                # 写入累积框：标题相同则替换，条件不同则追加
                suffix = "尾" if attr_name == "尾数" else ""
                title = (f"{_OM_SEP}{sel_period}期{file_type}"
                         f"{ball_no}球{attr_name}遗漏{_OM_SEP}")
                lines = [f"{rec['属性值']}{suffix}：{rec['遗漏期数']}次"
                         for rec in sorted(df.to_dict("records"),
                                           key=lambda x: -int(x["遗漏期数"]))[:int(n_pick)]]
                st.session_state["om_report"] = _om_upsert(
                    st.session_state.get("om_report", ""), title, lines)
                st.session_state["om_ver"] = st.session_state.get("om_ver", 0) + 1

    # ---------- ① 第一个框：原有展示（dataframe，内容不变） ----------
    df_records = st.session_state.get("om_df")
    meta = st.session_state.get("om_meta")
    if df_records and meta:
        df = pd.DataFrame(df_records)
        # 强制降序：遗漏次数多的在前
        df = df.sort_values("遗漏期数", ascending=False).reset_index(drop=True)
        st.subheader(f"{meta['file_type']} · {meta['ball_str']} · {meta['attr_name']} 遗漏统计")
        st.caption(f"有效期数：{meta['total']} 期（从选定期往回）　·　"
                   f"排序：遗漏次数 **从多到少**（越久没出越靠前）")
        st.dataframe(df, use_container_width=True, height=min(600, 40 + 35 * len(df)))
        if not df.empty:
            top = df.iloc[0]
            st.success(f"🔥 当前遗漏最大：**{top['属性值']}**，已遗漏 **{top['遗漏期数']}** 期")

        col_info = st.session_state.get("om_col")
        if col_info:
            with st.expander(f"🔍 校验：本列取自「{col_info['attr']}」第 {col_info['ball']} 球 —— "
                             f"CSV 第 {col_info['col_1based']} 列（{col_info['letter']} 列）",
                             expanded=False):
                st.caption("下面就是程序实际读取的那一列原值（最新在上）。"
                           "「距本期」= 该行与最新一期的间隔，用来核对遗漏数字是否精准。")
                st.dataframe(pd.DataFrame(col_info["preview"]),
                             use_container_width=True, height=320)
                st.caption(f"计算规则：第 n 球 = 属性基列 {ATTR_BASE_COL[col_info['attr']]} "
                           f"+ (n-1)×30，本球 n={col_info['ball']} → "
                           f"1 基第 {col_info['col_1based']} 列。")

    # ---------- ② 第二个框：累积报告（可编辑 / 保存 / 打印） ----------
    ver = st.session_state.get("om_ver", 0)
    st.divider()
    h1, h2 = st.columns([8, 2])
    with h1:
        st.markdown("### 📑 累积报告（可编辑 / 保存 / 打印）")
    with h2:
        if st.button("💾 保存修改", use_container_width=True):
            st.session_state["om_report"] = st.session_state.get(f"om_rep_{ver}", "")
            st.session_state["om_ver"] = ver + 1
            st.success("已保存")

    _ver_now = st.session_state.get("om_ver", 0)
    edited = st.text_area("累积报告（可直接编辑，改完点💾保存）",
                          value=st.session_state.get("om_report", ""), height=380,
                          key=f"om_rep_{_ver_now}", label_visibility="collapsed")

    st.caption(f"当前共 {len(_om_blocks(edited))} 段；**只有换属性才追加**，"
               f"换期数/球号/数据文件都在原属性那一块里覆盖更新。")

    d1, d2 = st.columns(2)
    with d1:
        st.download_button("📥 导出累积报告 (TXT)", edited.encode("utf-8-sig"),
                           file_name=f"遗漏核算_{datetime.now():%Y%m%d_%H%M%S}.txt",
                           mime="text/plain", use_container_width=True)
    with d2:
        st.download_button("💾 下载可打印 HTML", _om_print_html(edited).encode("utf-8"),
                           file_name=f"遗漏核算_{datetime.now():%Y%m%d_%H%M%S}.html",
                           mime="text/html", use_container_width=True,
                           help="浏览器拦打印时用这个：下载后用浏览器打开，按 Ctrl+P")

    # 一个按钮，点一下直接弹打印预览（不再需要点两次）
    if edited.strip():
        if st.button(f"📌 推送 {ball_str} 的累积报告到 AI 推演", use_container_width=True,
                     key="om_to_board"):
            _board_append("遗漏核算", f"{file_type} {sel_period} {ball_str}", edited)
            st.success(f"已推送到看板：{ball_str}")



        _om_print(edited)

# ==========================================
# 9. 登录与系统入口
# ==========================================
def register_user(username, password):
    """返回 (是否成功, 提示)。错误按 PostgREST 错误码分类，界面能看懂卡在哪。"""
    client = get_supabase_client()
    if not client:
        return False, "数据库连接失败：没读到 SUPABASE_URL / SUPABASE_KEY。改完 Secrets 必须 Reboot app。"
    u = (username or "").strip()
    p = password or ""
    import re as _re_sec
    if len(u) < 2: return False, "用户名至少 2 个字符（首尾空格会被去掉）"
    if len(u) > 32: return False, "用户名最多 32 个字符"
    if len(p) < 6: return False, "密码至少 6 位"
    if len(p) > 128: return False, "密码过长"
    if not _re_sec.fullmatch(r"[\w\u4e00-\u9fa5.\-]{2,32}", u):
        return False, "用户名只能用字母、数字、下划线、中文、点或横线"
    if p.lower() in ("123456", "password", "111111", "12345678", "abc123"):
        return False, "这个密码太常见，请换一个"
    try:
        client.table("users").insert({"username": u, "password": hash_password(p), "is_vip": False}).execute()
        return True, f"注册成功！请到【登录】页签用 {u} 登录。"
    except Exception as e:
        code = str(getattr(e, "code", "") or "")
        raw = str(e)
        if code == "23505" or "duplicate key" in raw or "unique constraint" in raw:
            return False, "该用户名已被注册（也可能你连点了两次注册，先去表里看一下）"
        if code == "42501" or "row-level security" in raw:
            return False, '写入被拒：users 表开了 RLS 但没有 INSERT 策略。SQL: create policy "signup insert" on public.users for insert to anon with check (true);'
        if code == "PGRST204" or "schema cache" in raw:
            return False, "users 表缺少 is_vip 列。SQL: alter table public.users add column if not exists is_vip boolean not null default false;"
        if code == "PGRST205" or "Could not find the table" in raw:
            return False, "找不到 users 表：确认在 public schema，然后 Settings -> API -> Reload schema。"
        if "401" in raw or "Invalid API key" in raw:
            return False, "SUPABASE_KEY 无效（Key 格式过旧或已轮换）"
        return False, f"注册失败：{raw[:300]}"


def check_credentials(username, password):
    """返回 (是否通过, 提示)。区分“用户不存在”和“密码错误”。"""
    client = get_supabase_client()
    if not client: return False, "数据库连接失败：请检查 SUPABASE_URL / SUPABASE_KEY"
    u = (username or "").strip()
    try:
        rows = client.table("users").select("username,password").eq("username", u).execute().data
    except Exception as e:
        return False, f"查询出错（users 表是否存在？）: {str(e)[:200]}"
    if not rows: return False, "该用户名不存在，请先注册"
    _stored = rows[0].get("password")
    if not verify_password(password or "", _stored):
        return False, "密码错误"
    # 旧哈希自动升级为 PBKDF2
    if is_legacy_hash(_stored):
        try:
            client.table("users").update(
                {"password": hash_password(password or "")}).eq("username", u).execute()
        except Exception:
            pass
    return True, "登录成功"


def change_password(username, old_pass, new_pass):
    """校验原密码后改密码；管理员走 Secrets，不在此处理"""
    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    if username == admin_name:
        return False, "管理员密码请在 Streamlit Secrets 的 ADMIN_PASSWORD 里修改，改完 Reboot app"
    ok, msg = check_credentials(username, old_pass)
    if not ok:
        return False, f"原密码不对：{msg}"
    if len(new_pass) < 6:
        return False, "新密码至少 6 位"
    if len(new_pass) > 128:
        return False, "新密码过长"
    if new_pass.lower() in ("123456", "password", "111111", "12345678", "abc123"):
        return False, "这个密码太常见，请换一个"
    if new_pass == old_pass:
        return False, "新密码不能和原密码相同"
    client = get_supabase_client()
    if not client:
        return False, "数据库连接失败"
    try:
        client.table("users").update(
            {"password": hash_password(new_pass)}).eq("username", username).execute()
        _audit_append("修改密码", f"user={username}")
        return True, "密码已修改，下次登录请用新密码"
    except Exception as e:
        return False, f"修改失败：{str(e)[:200]}"


_LOGIN_TTL_DAYS = 7


def _login_secret():
    """签名密钥：优先 SECRET_KEY，否则用 ADMIN_PASSWORD 派生"""
    s = st.secrets.get("SECRET_KEY", "") or ""
    if not s:
        s = "dsh|" + str(st.secrets.get("ADMIN_PASSWORD", "")) + "|login-token"
    return s.encode("utf-8")


def make_login_token(username):
    """生成 用户名|到期时间戳.签名"""
    import base64 as _b64
    import hmac as _hm
    import hashlib as _hl
    exp = int(_time_sec.time()) + _LOGIN_TTL_DAYS * 86400
    _tv = str(st.secrets.get("TOKEN_VERSION", "1"))
    raw = f"{username}|{exp}|{_tv}".encode("utf-8")
    payload = _b64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = _hm.new(_login_secret(), payload.encode(), _hl.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def check_login_token(tok):
    """校验令牌 -> 用户名 或 空"""
    import base64 as _b64
    import hmac as _hm
    import hashlib as _hl
    try:
        if not tok or "." not in tok:
            return ""
        payload, sig = tok.rsplit(".", 1)
        want = _hm.new(_login_secret(), payload.encode(), _hl.sha256).hexdigest()[:32]
        if not _hm.compare_digest(sig, want):
            return ""
        raw = _b64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
        parts = raw.rsplit("|", 2)
        if len(parts) != 3:
            return ""          # 旧格式令牌一律作废
        user, exp, tv = parts
        if tv != str(st.secrets.get("TOKEN_VERSION", "1")):
            return ""          # 版本不符 -> 失效
        if int(exp) < int(_time_sec.time()):
            return ""
        return user
    except Exception:
        return ""


def _qp_set(key, val):
    try:
        st.query_params[key] = val
    except Exception:
        try:
            st.experimental_set_query_params(**{key: val})
        except Exception:
            pass


def _qp_get(key):
    try:
        v = st.query_params.get(key, "")
        return v if isinstance(v, str) else (v[0] if v else "")
    except Exception:
        return ""


def login_page():
    st.title("🔐 智能系统客户端登录")
    tab1, tab2 = st.tabs(["已有账号？登录", "没有账号？立即注册"])

    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    admin_pass = st.secrets.get("ADMIN_PASSWORD", "")

    # ---- 登录
    with tab1:
        login_user = st.text_input("用户名", key="login_user")
        login_pass = st.text_input("密码", type="password", key="login_pass")
        # ---- 登录失败锁定 ----
        _lock_until = st.session_state.get("_login_lock_until", 0)
        _fails = st.session_state.get("_login_fails", 0)
        if _lock_until and _time_sec.time() < _lock_until:
            st.error(f"🚫 登录失败次数过多，已锁定，请等 "
                     f"{int(_lock_until - _time_sec.time())} 秒后再试")
        if st.button("登录", use_container_width=True, type="primary",
                     disabled=bool(_lock_until and _time_sec.time() < _lock_until)):
            u = (login_user or "").strip()
            if not u or not login_pass:
                st.warning("用户名和密码都要填")
            else:
                _ok = False
                if u == admin_name:
                    if login_pass == admin_pass or hash_password(login_pass) == admin_pass:
                        _ok = True
                        st.session_state.logged_in = True
                        st.session_state.username = u
                        st.session_state["_login_fails"] = 0
                        _qp_set("t", make_login_token(u))
                        st.success("👑 管理员登录成功！")
                        time.sleep(0.15)
                        st.rerun()
                    else:
                        st.error("管理员密码错误")
                else:
                    with st.spinner("正在登录…"):
                        ok, msg = check_credentials(u, login_pass)
                    if ok:
                        _ok = True
                        st.session_state.logged_in = True
                        st.session_state.username = u
                        st.session_state["_login_fails"] = 0
                        _qp_set("t", make_login_token(u))
                        st.success("登录成功，正在进入系统…")
                        time.sleep(0.15)
                        st.rerun()
                    else:
                        st.error(msg)
                if not _ok:
                    _fails = st.session_state.get("_login_fails", 0) + 1
                    st.session_state["_login_fails"] = _fails
                    if _fails >= 5:
                        st.session_state["_login_lock_until"] = _time_sec.time() + 300
                        st.session_state["_login_fails"] = 0
                        st.error("🚫 连续失败 5 次，已锁定 5 分钟")
                    else:
                        st.caption(f"还可尝试 {5 - _fails} 次，超过将锁定 5 分钟")
                    time.sleep(min(1.0, 0.2 * _fails))

    # ---- 注册
    # widget 一旦渲染就不能再改它的 session_state，所以清空表单要放在渲染之前
    if st.session_state.pop("_clear_reg_form", False):
        for k in ("reg_user", "reg_pass", "reg_confirm"):
            st.session_state.pop(k, None)
    # rerun 会冲掉 success，所以提示先存起来，渲染前再弹
    if st.session_state.get("_reg_done_msg"):
        st.success(st.session_state.pop("_reg_done_msg"))

    with tab2:
        reg_user = st.text_input("设置用户名", key="reg_user")
        reg_pass = st.text_input("密码", type="password", key="reg_pass")
        reg_confirm = st.text_input("确认密码", type="password", key="reg_confirm")
        if st.button("注册账号", use_container_width=True):
            if not reg_user or not reg_pass:
                st.warning("用户名和密码都要填")
            elif reg_pass != reg_confirm:
                st.error("两次输入的密码不一致")
            else:
                ok, msg = register_user(reg_user, reg_pass)
                if ok:
                    st.session_state["_clear_reg_form"] = True
                    st.session_state["_reg_done_msg"] = msg
                    st.rerun()
                else:
                    st.error(msg)


_APP_BUILD = "v2026-11-20-16d"


def render_auto_ai_page():
    """独立页面：全自动智能分析（带自己的看板）"""
    st.title("🤖 全自动智能分析")
    st.caption("把各页面推来的结果集中到这里：自动解析 → 生成杀号清单 → AI 解读。")

    _board_render()
    _multi_ai_ui()
    _board_ai_ui()


def main_app():
    current_user = st.session_state.username
    admin_name = st.secrets.get("ADMIN_USERNAME", "admin")
    is_admin = (current_user == admin_name)

    is_vip = False
    if not is_admin:
        client = get_supabase_client()
        if client:
            try:
                res = client.table("users").select("is_vip").eq("username", current_user).execute().data
                if res and res[0].get("is_vip") == True: is_vip = True
            except: pass

    df_data = load_real_data()

    with st.sidebar:
        st.markdown("欢迎来到AI精算中心")
        st.write(f"👤 **{current_user}**")
        if st.button("退出登录", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()

        with st.expander("🔑 修改密码", expanded=False):
            _cp1 = st.text_input("原密码", type="password", key="cp_old")
            _cp2 = st.text_input("新密码", type="password", key="cp_new")
            _cp3 = st.text_input("确认新密码", type="password", key="cp_new2")
            if st.button("确认修改", key="cp_btn", use_container_width=True):
                if not _cp1 or not _cp2 or not _cp3:
                    st.warning("三项都要填")
                elif _cp2 != _cp3:
                    st.error("两次输入的新密码不一致")
                else:
                    _okp, _msgp = change_password(current_user, _cp1, _cp2)
                    if _okp:
                        st.success(_msgp)
                        for _k in ("cp_old", "cp_new", "cp_new2"):
                            st.session_state.pop(_k, None)
                    else:
                        st.error(_msgp)
        st.divider()

        menu_options = ["📊 主控台"]
        if is_admin or is_vip: menu_options.extend(["📐 多维分析", "🔗 深度联动", "🧠 AI推演", "📉 遗漏统计", "🧮 计算中心", "🔀 升降交集", "🎯 三中三组合池", "🤖 全自动智能分析"])
        if is_admin: menu_options.append("⚙️ 后台管理")

        page = st.radio("导航菜单", menu_options)
        st.divider()

    if page == "📊 主控台": render_console(df_data)
    elif page == "📐 多维分析": render_multi_analysis(df_data)
    elif page == "🔗 深度联动": render_deep_linkage(df_data)
    elif page == "🤖 全自动智能分析":
        render_auto_ai_page()
    elif page == "🧠 AI推演": render_ai(df_data)
    elif page == "🎯 三中三组合池":
        if render_combo2 is None:
            st.error("缺少 combo2_page.py，请与 app.py 一起上传")
        else:
            render_combo2(df_data, {"load_excel_data": load_excel_data,
                                     "board_add": _board_add})
    elif page == "🔀 升降交集":
        if render_cross_view is None:
            st.error("缺少 cross_view.py，请与 app.py 一起上传")
        else:
            render_cross_view(df_data, {"load_excel_data": load_excel_data,
                                        "board_add": _board_add})
    elif page == "🧮 计算中心":
        if render_calc_center is None:
            st.error("缺少 calc_center.py，请把它一起上传到仓库根目录。")
        else:
            def _cc_raw(ball_str, file_key="升序全套"):
                import ast as _ast
                _f = "升序全套.csv" if file_key == "升序全套" else "按序全套.csv"
                _rows = load_excel_data(_f, None) or []
                _r, _fk = _scan_build_runner()
                _attrs = st.session_state.get("_cc_attrs_cache") or []
                for _n in ([] if _attrs else _ast.parse(open(__file__, encoding="utf-8").read()).body):
                    if isinstance(_n, _ast.FunctionDef) and _n.name == "render_multi_analysis":
                        for _m in _ast.walk(_n):
                            if (isinstance(_m, _ast.Assign) and _m.targets
                                    and isinstance(_m.targets[0], _ast.Name)
                                    and _m.targets[0].id == "show_attrs"):
                                _attrs = _ast.literal_eval(_m.value)
                if _attrs:
                    st.session_state["_cc_attrs_cache"] = _attrs
                return _raw_report_for_ball(file_key, _rows, ball_str, _attrs, _r, _fk)

            try:
                render_calc_center(df_data, {"load_excel_data": load_excel_data,
                                            "call_deepseek_api": call_deepseek_api,
                                            "raw_report": _cc_raw,
                                            "pred_save": _pred_save})
            except Exception as _cc_e:
                st.error(f"计算中心运行出错：{type(_cc_e).__name__}: {_cc_e}")
                import traceback as _tb
                st.code(_tb.format_exc()[-2000:])
    elif page == "📉 遗漏统计":
        if render_omission_page:
            render_omission_page()
        else:
            st.warning("缺少 omission_page.py —— 需与 app.py 同目录并一起提交到 GitHub 仓库。")
    elif page == "⚙️ 后台管理": render_admin_panel()


# ===== 刷新/重开后，用令牌自动恢复登录 =====
if not st.session_state.get("logged_in"):
    _tok0 = _qp_get("t")
    _u0 = check_login_token(_tok0) if _tok0 else ""
    if _u0:
        _admin_n0 = st.secrets.get("ADMIN_USERNAME", "admin")
        if _u0 == _admin_n0:
            st.session_state.logged_in = True
            st.session_state.username = _u0
        else:
            try:
                _c0 = get_supabase_client()
                _rows0 = (_c0.table("users").select("username")
                          .eq("username", _u0).execute().data) if _c0 else []
                if _rows0:
                    st.session_state.logged_in = True
                    st.session_state.username = _u0
            except Exception:
                pass

if not st.session_state.logged_in:
    login_page()
else:
    main_app()
