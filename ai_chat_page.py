# -*- coding: utf-8 -*-
"""
AI 开发助手 —— 嵌在后台管理页里的 DeepSeek 对话窗口
====================================================
功能：
    * 多轮对话，历史存在 session_state
    * 模型可切换：deepseek-chat（快）/ deepseek-reasoner（慢，带思考过程）
    * 可勾选「附带源码」，把 app.py 全文一起发给 AI
    * 常用问题一键发送、清空对话、导出 TXT
    * 报错显示 HTTP 状态码 + 中文原因

安装（在 app.py 里改 3 处）：
    1) 顶部 import 区加：
           from ai_chat_page import render_ai_chat
    2) render_admin_panel() 里的 tabs 改成 4 个：
           tab1, tab2, tab3, tab4 = st.tabs(
               ["👑 用户 VIP 授权", "📝 数据录入与同步", "☁️ 云端数据流转", "💬 AI 助手"])
    3) 该函数末尾（最后一个 with 块之后）加：
           with tab4: render_ai_chat()
    另外：ai_chat_page.py 必须与 app.py 同目录，并一起提交到仓库。

Key 从 st.secrets 读 DEEPSEEK_API_KEY，只存在于服务端，不会下发到浏览器。
"""

import os
import sys
import time
from datetime import datetime

import streamlit as st

try:
    import requests
except Exception:
    requests = None

API_URL = "https://api.deepseek.com/chat/completions"

MODELS = {
    "deepseek-chat": "deepseek-chat · 快（日常问答、改代码）",
    "deepseek-reasoner": "deepseek-reasoner · 慢（复杂推理，附带思考过程）",
}

DEFAULT_SYSTEM = """你是「智能数据分析系统」的开发助手，帮主人排查问题、修改功能、写代码。

系统架构（你需要记住）：
- 前端：Streamlit 单文件应用 app.py，侧边栏导航，分 主控台 / 多维分析 / 深度联动 / AI推演 / 后台管理。
- 数据：GitHub 仓库里存 升序源文件.xlsx、按序源文件.xlsx（只有期号 + 7 个号码）；
  派生出 总数据.xlsx 与 升序全套.csv / 按序全套.csv（后者 214 列，含 7 球 × 28 个属性）。
- 数据库：Supabase。users 表存 username / password(sha256) / is_vip；rules 表存 1-49 号权威属性。
- AI：DeepSeek chat completions，用于按排杀条件筛选号码。
- 关键函数：calculate_all_attributes、build_rule_database、extract_numbers、call_deepseek_api、
  calculate_linkage、render_multi_analysis、render_console、render_admin_panel。
- 重要约定：全套 CSV 列布局为「期号 3 列 + 7 个球位 × 30 列 + 年份」，每个球位 30 列依次是
  十位、个位、28 个属性。

回答要求：
1. 给可直接运行的代码，不要伪代码；说明改在哪个函数、哪一行附近。
2. 指出风险与副作用（影响已生成的 CSV、缓存失效、需要 Reboot 等）。
3. 不确定就明说不确定，不要编造 API 或字段名。
4. 简体中文，简洁，不写客套话。"""

# 一键发送的完整问题（不依赖用户补充内容）
QUICK_ASKS = [
    "检查 app.py 里有没有已废弃或即将废弃的 Streamlit API，列出并给出现代写法。",
    "这个系统现在最容易静默出错（不报错但结果错）的地方是哪几处？按风险排序。",
    "给出 3 个能明显提升「多维分析」速度的具体改动，说明改哪里。",
    "帮我写一条 SQL：把 rules 表里 22 号的合数改成 04合，并验证结果。",
]


# ----------------------------------------------------------------- 工具
def _get_key():
    key = ""
    try:
        key = str(st.secrets.get("DEEPSEEK_API_KEY", "") or "").strip()
    except Exception:
        key = ""
    if not key:
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    return key


def _explain(status, body):
    tail = (body or "").strip().replace("\n", " ")[:300]
    table = {
        400: "报文格式被拒（检查 model 名与 messages 结构）",
        401: "Key 无效或为空：Secrets 里没读到 DEEPSEEK_API_KEY，或改完没有 Reboot app",
        402: "该账号余额不足",
        403: "无权限",
        422: "参数非法",
        429: "请求太频繁，等几秒再发",
        500: "DeepSeek 服务端错误",
        502: "网关错误",
        503: "服务繁忙",
    }
    return f"HTTP {status}｜{table.get(status, '未知错误')}｜{tail}"


def _load_source():
    """尽量拿到 app.py 全文。找不到返回 ("", "")。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = ["app.py", os.path.join(here, "app.py")]
    if len(sys.argv) > 0 and str(sys.argv[0]).endswith(".py"):
        candidates.append(sys.argv[0])
    for p in candidates:
        try:
            if p and os.path.isfile(p):
                return open(p, encoding="utf-8", errors="ignore").read(), p
        except Exception:
            continue
    return "", ""


def _ask(messages, model, timeout, max_tokens):
    if requests is None:
        return "请求失败：当前环境缺少 requests 库"
    key = _get_key()
    if not key:
        return ("请求失败：没有读到 DEEPSEEK_API_KEY。\n"
                "请在 Streamlit Secrets 里配置，改完必须 Reboot app。")
    if not key.startswith("sk-"):
        return f"请求失败：DEEPSEEK_API_KEY 格式异常（应以 sk- 开头，当前长度 {len(key)}）"

    payload = {"model": model, "messages": messages, "stream": False,
               "max_tokens": max_tokens, "temperature": 0.3}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}

    last = ""
    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
        except Exception as e:
            last = f"运行错误：{type(e).__name__}: {e}"
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return last

        if r.status_code == 200:
            try:
                msg = r.json()["choices"][0]["message"]
                out = (msg.get("content") or "").strip()
                reason = (msg.get("reasoning_content") or "").strip()
                if reason:
                    out = f"**【思考过程】**\n\n{reason}\n\n---\n\n**【回答】**\n\n{out}"
                return out or "（模型返回了空内容）"
            except Exception:
                return f"请求失败：返回体无法解析｜{r.text[:300]}"

        last = _explain(r.status_code, r.text)
        if r.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        return f"请求失败：{last}"
    return f"请求失败：{last}"


SUMMARY_SYS = """你是需求整理助手。把一段对话整理成一份可直接交给开发者执行的「改动需求」。
只输出需求本身：不要写代码，不要客套，不要解释你在做什么，不要复述对话。"""


def _summarize_for_upgrade(history, model, timeout=120):
    """把聊天记录浓缩成一份规范需求，供「自动升级」使用。"""
    lines = []
    for m in history[-16:]:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        who = "我" if m.get("role") == "user" else "助手"
        lines.append(f"{who}：{content[:800]}")
    convo = "\n\n".join(lines)
    if not convo:
        return ""

    prompt = (f"对话如下：\n\n{convo}\n\n"
              "请输出一份改动需求，包含：\n"
              "1. 目标（一句话，说清改成什么样）\n"
              "2. 涉及文件与函数\n"
              "3. 具体改动点（分条，写明位置、触发条件、期望效果）\n"
              "4. 验收方式（怎么确认改好了）\n"
              "5. 不要做的事（边界，避免误伤其它功能）\n"
              "6. 待确认问题：对话里没说清、需要主人拍板的地方，逐条列出；没有就写「无」。\n"
              "严禁自己猜测补全模糊需求——拿不准就放进第 6 条。")

    out = _ask([{"role": "system", "content": SUMMARY_SYS},
                {"role": "user", "content": prompt}], model, timeout, 1500)
    if (not out) or out.startswith("请求失败") or out.startswith("运行错误"):
        # 兜底：把我问过的话拼成一份粗略需求，至少不丢内容
        return "\n".join(f"- {(m.get('content') or '').strip()}"
                         for m in history
                         if m.get("role") == "user" and (m.get("content") or "").strip())
    return out.strip()


# ----------------------------------------------------------------- 页面
def render_ai_chat(entry="tab"):
    """entry='tab' 嵌在标签页里（紧凑）；'page' 独占一页。"""
    st.session_state.setdefault("chat_history", [])

    if entry != "tab":
        st.title("💬 AI 开发助手")
        st.caption("基于 DeepSeek。Key 只在服务端，不会下发到浏览器。")

    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    with c1:
        model = st.selectbox("模型", list(MODELS), index=0,
                             format_func=lambda k: MODELS[k])
    with c2:
        with_source = st.checkbox("附带源码", value=False,
                                  help="把 app.py 全文一起发给 AI；更准，但每次消耗更多 token")
    with c3:
        timeout = st.number_input("超时(秒)", min_value=30, max_value=600, value=180, step=30)
    with c4:
        st.write("")
        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    # ---------------- 历史 ----------------
    if not st.session_state.chat_history:
        st.info("还没有对话。点下面的常用问题，或直接在输入框里提问。")
    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("meta"):
                st.caption(m["meta"])

    # ---------------- 发送 ----------------
    def _send(text):
        text = (text or "").strip()
        if not text:
            return

        system = DEFAULT_SYSTEM
        meta_src = ""
        if with_source:
            src, path = _load_source()
            if src:
                if len(src) > 120000:
                    src = src[:120000] + "\n\n……（源码过长，已截断）"
                system += f"\n\n以下是当前 app.py 完整源码（只读参考，不要整段复述）：\n```python\n{src}\n```"
                meta_src = f"附带源码 {os.path.basename(path) or 'app.py'}（{len(src)} 字符）"
            else:
                meta_src = "勾选了附带源码，但没找到 app.py"

        st.session_state.chat_history.append({"role": "user", "content": text})
        with st.chat_message("user"):
            st.markdown(text)

        msgs = [{"role": "system", "content": system}]
        for m in st.session_state.chat_history[-20:]:
            msgs.append({"role": m["role"], "content": m["content"]})

        with st.chat_message("assistant"):
            t0 = time.time()
            with st.spinner(f"调用 {model} …"):
                reply = _ask(msgs, model, int(timeout), 8192)
            cost = time.time() - t0
            if reply.startswith("请求失败") or reply.startswith("运行错误"):
                st.error(reply)
            else:
                st.markdown(reply)
            meta = f"耗时 {cost:.1f}s · {model}" + (f" · {meta_src}" if meta_src else "")
            st.caption(meta)

        st.session_state.chat_history.append(
            {"role": "assistant", "content": reply, "meta": meta})
        st.rerun()

    # ---------------- 快捷提问 ----------------
    st.markdown("**常用问题**（点一下直接发送）")
    _labels = ["查废弃API", "静默出错点", "分析提速", "写 SQL"]
    qcols = st.columns(len(QUICK_ASKS))
    for i, q in enumerate(QUICK_ASKS):
        with qcols[i]:
            if st.button(_labels[i] if i < len(_labels) else f"问题{i+1}",
                         key=f"quick_{i}", use_container_width=True, help=q):
                _send(q)

    # ---------------- 输入框（chat_input 提交后自动清空） ----------------
    prompt = st.chat_input("问点什么…（Enter 发送，Shift+Enter 换行）")
    if prompt:
        _send(prompt)

    # ---------------- 交接给「自动升级」（两阶段：草稿 → 你确认 → 才发送） ----------------
    if st.session_state.chat_history:
        st.markdown("**交接给自动升级**")
        if st.button("➡️ 把这次对话整理成「改动需求」草稿", use_container_width=True,
                     help="只生成草稿给你审，不会自动发给自动升级页"):
            with st.spinner("正在整理需求…"):
                spec = _summarize_for_upgrade(st.session_state.chat_history, model, int(timeout))
            st.session_state["_ug_spec_draft"] = spec
            st.session_state["_spec_ver"] = st.session_state.get("_spec_ver", 0) + 1
            st.rerun()

    draft = st.session_state.get("_ug_spec_draft")
    if draft:
        ver = st.session_state.get("_spec_ver", 0)
        st.markdown("#### 需求草稿 —— 确认后才会发给「🛠️ 自动升级」")
        edited = st.text_area("需求草稿（可以直接改）", value=draft, height=280,
                              key=f"spec_edit_{ver}",
                              help="这就是将来发送给自动升级的需求原文。哪里不对就在这里改。")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("✅ 确认，发送到自动升级", type="primary", use_container_width=True):
                st.session_state["ug_req"] = (edited or "").strip()
                st.session_state["_ug_from_chat"] = True
                st.session_state.pop("_ug_spec_draft", None)
                st.success("已发送。切到「🛠️ 自动升级」标签，需求框里就是这份文本。")
                st.rerun()
        with b2:
            if st.button("🔄 重新整理", use_container_width=True):
                with st.spinner("重新整理中…"):
                    spec = _summarize_for_upgrade(st.session_state.chat_history, model, int(timeout))
                st.session_state["_ug_spec_draft"] = spec
                st.session_state["_spec_ver"] = ver + 1
                st.rerun()
        with b3:
            if st.button("🗑 丢弃草稿", use_container_width=True):
                st.session_state.pop("_ug_spec_draft", None)
                st.rerun()

    # ---------------- 导出 ----------------
    if st.session_state.chat_history:
        lines = [f"# AI 开发助手对话记录  {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
        for m in st.session_state.chat_history:
            lines.append(f"## {'我' if m['role'] == 'user' else 'AI'}")
            lines.append(m["content"])
            if m.get("meta"):
                lines.append(f"> {m['meta']}")
            lines.append("")
        st.download_button("📥 导出对话 (TXT)", "\n".join(lines).encode("utf-8-sig"),
                           file_name=f"AI对话_{datetime.now():%Y%m%d_%H%M}.txt",
                           mime="text/plain", use_container_width=True)


if __name__ == "__main__":
    render_ai_chat(entry="page")
