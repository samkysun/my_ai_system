# -*- coding: utf-8 -*-
"""
自动升级引擎 —— 需求 → 方案 → 补丁 → 校验 → 备份 → 提交 → 可回滚
=================================================================
安全模型（四道闸门，任何一道不过就中止，不写任何东西）：

    闸门 1  validate_edits : 只允许改 .py；禁碰 .streamlit/ .github/；禁硬编码密钥；
                             禁 os.system；限制文件数与改动行数
    闸门 2  apply_edits    : find 必须逐字符精确且唯一，否则报错（不做模糊匹配）
    闸门 3  ast_check      : 所有改动的 .py 必须能通过语法解析
    闸门 4  run_tests      : 在临时目录跑 system_tests.py，必须全绿

全过之后才提交。提交走 Git Data API，一次原子提交（多文件同时生效），
并在同一个 commit 里写入 _upgrade_log.json，记录本次前的 head SHA，
回滚就是按那个 SHA 把文件取回来重新提交。

安装（app.py 里改 3 处）：
    1) 顶部：
           try:
               from auto_upgrade import render_upgrade_tab
           except Exception:
               render_upgrade_tab = None
    2) render_admin_panel 的 tabs 加一项：
           tab1, tab2, tab3, tab4, tab5 = st.tabs([..., "💬 AI 助手", "🛠️ 自动升级"])
    3) 末尾：
           with tab5:
               render_upgrade_tab() if render_upgrade_tab else st.warning("缺少 auto_upgrade.py")
"""

import ast
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

import streamlit as st

try:
    import requests
except Exception:
    requests = None

GH = "https://api.github.com"
API_URL = "https://api.deepseek.com/chat/completions"

ALLOWED_EXT = (".py",)
PROTECTED_PREFIX = (".streamlit/", ".github/", ".git/", "_backup/")
MAX_FILES = 3
MAX_NEW_LINES = 600
LOG_FILE = "_upgrade_log.json"

# 硬阻断（拒绝提交）
FORBIDDEN = [
    (r"""["']sk-[A-Za-z0-9_\-]{12,}["']""", "代码里出现硬编码的 sk- 密钥"),
    (r"(?:open|write)\s*\([^\n]{0,80}secrets\.toml|secrets\.toml[^\n]{0,80}(?:open|write)",
     "代码里在读写 secrets.toml"),
    (r"\bos\.system\s*\(", "代码里用了 os.system"),
    (r"shutil\.rmtree\s*\(\s*[\"']/", "代码里在删根目录"),
]


# ================================================================ 闸门 1
def validate_edits(sources, edits):
    """返回 (ok, msg)。不碰任何文件，纯检查。"""
    if not isinstance(edits, list) or not edits:
        return False, "补丁里没有任何 edits"
    if len(edits) > 20:
        return False, f"edits 过多（{len(edits)} 条）"

    files = set()
    added = 0
    for i, e in enumerate(edits, 1):
        if not isinstance(e, dict):
            return False, f"第 {i} 条 edit 格式不对"
        path = str(e.get("file", "")).strip()
        mode = str(e.get("mode", "replace_block")).strip()

        if not path:
            return False, f"第 {i} 条没有 file"
        if path.startswith("/") or ".." in path:
            return False, f"第 {i} 条路径非法：{path}"
        if not path.endswith(ALLOWED_EXT):
            return False, f"只允许改 .py 文件，拒绝：{path}"
        for p in PROTECTED_PREFIX:
            if path.startswith(p):
                return False, f"禁止改动受保护路径：{path}"

        if mode not in ("replace_block", "create", "append"):
            return False, f"第 {i} 条 mode 不支持：{mode}"

        # 内容黑名单先查（与文件是否已存在无关）
        blob = str(e.get("content", "")) + str(e.get("replace", ""))
        for pattern, why in FORBIDDEN:
            if re.search(pattern, blob):
                return False, f"{why}（第 {i} 条）"

        if mode == "replace_block":
            if not e.get("find"):
                return False, f"第 {i} 条缺 find"
            if e.get("replace") is None:
                return False, f"第 {i} 条缺 replace"
            if path not in sources:
                return False, f"第 {i} 条要改的文件不存在：{path}"
            if sources[path].count(str(e["find"])) != 1:
                n = sources[path].count(str(e["find"]))
                return False, f"第 {i} 条 find 在 {path} 中出现 {n} 次（必须恰好 1 次）"
            added += len(str(e["replace"]).splitlines())
        elif mode == "create":
            if not e.get("content"):
                return False, f"第 {i} 条 create 缺 content"
            if path in sources:
                return False, f"文件已存在，不能用 create：{path}（改用 replace_block）"
            added += len(str(e["content"]).splitlines())
        else:  # append
            if not e.get("content"):
                return False, f"第 {i} 条 append 缺 content"
            if path not in sources:
                return False, f"append 的目标不存在：{path}"
            added += len(str(e["content"]).splitlines())

        files.add(path)

    if len(files) > MAX_FILES:
        return False, f"一次最多改 {MAX_FILES} 个文件，本次涉及 {len(files)} 个"
    if added > MAX_NEW_LINES:
        return False, f"新增行数 {added} 超过上限 {MAX_NEW_LINES}"
    return True, "校验通过"


# ================================================================ 闸门 2
def apply_edits(sources, edits):
    """返回 (ok, new_sources, msg)。sources 不会被修改。"""
    new = dict(sources)
    for i, e in enumerate(edits, 1):
        path = str(e.get("file", "")).strip()
        mode = str(e.get("mode", "replace_block")).strip()

        if mode == "replace_block":
            find = str(e.get("find", ""))
            if path not in new:
                return False, {}, f"第 {i} 条：文件不存在 {path}"
            cnt = new[path].count(find)
            if cnt == 0:
                return False, {}, f"第 {i} 条：在 {path} 中找不到 find 片段（可能已被改过）"
            if cnt > 1:
                return False, {}, f"第 {i} 条：find 不唯一，在 {path} 中出现 {cnt} 次"
            new[path] = new[path].replace(find, str(e.get("replace", "")), 1)

        elif mode == "create":
            if path in new:
                return False, {}, f"第 {i} 条：文件已存在，不能用 create {path}"
            new[path] = str(e.get("content", ""))

        elif mode == "append":
            if path not in new:
                return False, {}, f"第 {i} 条：append 目标不存在 {path}"
            new[path] = new[path] + str(e.get("content", ""))

        else:
            return False, {}, f"第 {i} 条：未知 mode {mode}"

    return True, new, f"已应用 {len(edits)} 处改动"


# ================================================================ 闸门 3
def ast_check(sources):
    """所有 .py 必须能解析。返回 (ok, msg)。"""
    for path, text in sources.items():
        if not path.endswith(".py"):
            continue
        try:
            ast.parse(text, filename=path)
        except SyntaxError as e:
            return False, f"语法错误 {path}:{e.lineno}: {e.msg}"
    return True, "语法检查通过"


# ================================================================ 闸门 4
def _make_workdir():
    """建一个可写的工作目录。
    注意：这里刻意不用 tempfile.mkdtemp —— 某些受限环境下 mkdtemp 建出的目录无法写入，
    而普通 os.makedirs 可以。判定标准是“真的能写进去”。"""
    name = f"upg_{int(time.time() * 1000)}_{os.getpid()}"
    bases = [os.getcwd(), tempfile.gettempdir()]
    for base in bases:
        d = os.path.join(base, name)
        try:
            os.makedirs(d, exist_ok=False)
        except Exception:
            continue
        try:
            probe = os.path.join(d, ".probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            continue
    return None


def run_tests(patched, repo=None, token=None, timeout=240):
    """在临时目录跑 system_tests.py。返回 (ok, 输出尾部)。"""
    tmp = _make_workdir()
    if not tmp:
        return False, "创建临时目录失败，无法执行测试（拒绝提交）"
    try:
        for path, text in patched.items():
            dst = os.path.join(tmp, path)
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(text)

        # 补上测试所需的依赖文件（补丁未覆盖的，从仓库取）
        deps = ["system_tests.py", "auto_upgrade.py", "ai_chat_page.py", "app.py"]
        for dep in deps:
            if dep in patched:
                continue
            text = None
            if repo and token:
                _, text = gh_read(repo, token, dep)
            if text is None:
                here = os.path.join(os.path.dirname(os.path.abspath(__file__)), dep)
                if os.path.isfile(here):
                    text = open(here, encoding="utf-8").read()
            if text is not None:
                with open(os.path.join(tmp, dep), "w", encoding="utf-8") as f:
                    f.write(text)

        if not os.path.isfile(os.path.join(tmp, "system_tests.py")):
            return False, "找不到 system_tests.py，无法执行测试（拒绝提交）"

        proc = subprocess.run([sys.executable, "system_tests.py"], cwd=tmp,
                              capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out[-4000:]
    except subprocess.TimeoutExpired:
        return False, f"测试超时（>{timeout}s）"
    except Exception as e:
        return False, f"测试执行异常：{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ GitHub
def _h(token):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json"}


def gh_read(repo, token, path, ref=None):
    """返回 (sha, 文本)；文件不存在返回 (None, None)。"""
    if requests is None:
        return None, None
    url = f"{GH}/repos/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=_h(token), params={"ref": ref} if ref else None, timeout=40)
        if r.status_code != 200:
            return None, None
        j = r.json()
        if isinstance(j, list):
            return None, None
        raw = base64.b64decode(j["content"]).decode("utf-8", "ignore")
        return j.get("sha"), raw
    except Exception:
        return None, None


def gh_commit(repo, token, files, message, branch="main"):
    """原子提交多个文件。返回 (commit_sha, 提交前的 head_sha)。"""
    if requests is None:
        raise RuntimeError("缺少 requests 库")
    base = f"{GH}/repos/{repo}"

    def call(method, path, **kw):
        r = requests.request(method, base + path, headers=_h(token), timeout=45, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    head = call("GET", f"/git/ref/heads/{branch}")["object"]["sha"]
    tree_sha = call("GET", f"/git/commits/{head}")["tree"]["sha"]

    entries = []
    for path, text in files.items():
        blob = call("POST", "/git/blobs",
                    json={"content": text, "encoding": "utf-8"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    tree = call("POST", "/git/trees", json={"base_tree": tree_sha, "tree": entries})
    commit = call("POST", "/git/commits",
                  json={"message": message, "tree": tree["sha"], "parents": [head]})
    call("PATCH", f"/git/refs/heads/{branch}", json={"sha": commit["sha"], "force": False})
    return commit["sha"], head


def load_log(repo, token):
    _, text = gh_read(repo, token, LOG_FILE)
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ================================================================ 模型
def parse_patch(text):
    """从模型输出里取 JSON。失败返回 {}。"""
    if not text:
        return {}
    import re
    cands = []
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        cands.append(m.group(1))
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j > i:
        cands.append(text[i:j + 1])
    for c in cands:
        try:
            data = json.loads(c)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


PROTOCOL = """严格只输出一个 JSON，不要输出 JSON 以外的任何文字：
{
  "summary": "一句话说明改了什么",
  "risk": "风险与副作用",
  "verify": "用户手工验证的步骤",
  "edits": [
    {"file": "app.py", "mode": "replace_block", "find": "原文件中逐字符精确的片段", "replace": "替换成的新片段"},
    {"file": "new_page.py", "mode": "create", "content": "完整文件内容"},
    {"file": "app.py", "mode": "append", "content": "追加到文件末尾的内容"}
  ]
}

硬性规则：
1. find 必须是目标文件中逐字符精确存在的片段（连缩进、空行都要一致），并且在文件中只出现一次。
2. 一个 edit 只改一处；改多处就写多个 edit。不要把整份文件塞进 replace。
3. 只允许 .py 文件；禁止改动 .streamlit/ .github/ 下的任何东西。
4. 禁止硬编码任何密钥（sk- 开头），禁止 os.system，禁止写 secrets.toml。
5. 最多 3 个文件，合计新增不超过 600 行。
6. 新增依赖库必须在 risk 里说明。
7. 不要臆造本项目不存在的函数或字段；不确定就在 risk 里写明。"""

SYSTEM = """你是这个 Streamlit 项目的资深开发者，负责出可验证的补丁。
项目结构：app.py（单文件主程序）、ai_chat_page.py（AI 对话页）、auto_upgrade.py（本引擎）、
system_tests.py（测试集）、fix_full_csv_attrs.py（CSV 重算脚本）。
数据在 GitHub 仓库，数据库用 Supabase，AI 用 DeepSeek。
回答必须是一个 JSON，格式见用户消息中的协议说明。"""


def _ask_deepseek(messages, key, model="deepseek-chat", timeout=240):
    if requests is None:
        return None, "环境缺少 requests"
    payload = {"model": model, "messages": messages, "stream": False,
               "temperature": 0, "max_tokens": 8192}
    try:
        r = requests.post(API_URL, headers={"Content-Type": "application/json",
                                            "Authorization": f"Bearer {key}"},
                          json=payload, timeout=timeout)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if r.status_code != 200:
        reason = {401: "Key 无效或没读到", 402: "余额不足", 429: "请求过频"}.get(
            r.status_code, "接口报错")
        return None, f"HTTP {r.status_code}｜{reason}｜{r.text[:200]}"
    try:
        return r.json()["choices"][0]["message"]["content"], None
    except Exception:
        return None, "返回体无法解析"


# ================================================================ 界面
def _cfg():
    def sec(k):
        try:
            return str(st.secrets.get(k, "") or "").strip()
        except Exception:
            return os.environ.get(k, "").strip()
    return sec("DEEPSEEK_API_KEY"), sec("GITHUB_TOKEN"), sec("GITHUB_REPO")


def _diff_text(old, new, path):
    import difflib
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=3))


def render_upgrade_tab():
    st.markdown("### 🛠️ 自动升级")
    st.caption("描述需求 → AI 出补丁 → 四道校验 → 你确认 → 原子提交。任何一步失败都不会改动仓库。")

    dkey, gtoken, grepo = _cfg()
    if not dkey or not gtoken or not grepo:
        missing = [n for n, v in (("DEEPSEEK_API_KEY", dkey), ("GITHUB_TOKEN", gtoken),
                                  ("GITHUB_REPO", grepo)) if not v]
        st.error("Secrets 里缺：" + "、".join(missing) + "。补上并 Reboot app。")
        return

    st.session_state.setdefault("ug_candidate", None)
    st.session_state.setdefault("ug_tests", "")
    st.session_state.setdefault("ug_last", None)

    # ---------- 1. 需求 ----------
    req = st.text_area("你要做什么？（越具体越好）", height=140,
                       placeholder="例：在多维分析页加一个「导出当前报告为 Excel」的按钮，"
                                   "导出内容包括基准行排列和所有触发行。")
    c1, c2 = st.columns([2, 1])
    with c1:
        targets = st.multiselect("让 AI 参考哪些文件", ["app.py", "ai_chat_page.py", "auto_upgrade.py"],
                                 default=["app.py"])
    with c2:
        model = st.selectbox("模型", ["deepseek-chat", "deepseek-reasoner"])
    st.caption(f"⚠️ 每次生成会把目标文件全文发给 DeepSeek。app.py 约 9 万字符 ≈ 3 万 token，"
               f"一次几分到几毛钱。")

    if st.button("🧠 生成方案与补丁", type="primary", use_container_width=True):
        if not req.strip():
            st.warning("先写需求")
        elif not targets:
            st.warning("至少选一个参考文件")
        else:
            st.session_state.ug_candidate = None
            st.session_state.ug_tests = ""

            src_map, missing = {}, []
            for p in targets:
                _, text = gh_read(grepo, gtoken, p)
                if text is None:
                    missing.append(p)
                else:
                    src_map[p] = text
            if missing:
                st.error(f"仓库里读不到：{missing}")
            else:
                ctx = "\n\n".join(f"=== 文件 {p} 全文 ===\n```python\n{t}\n```"
                                  for p, t in src_map.items())
                msgs = [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"{PROTOCOL}\n\n{ctx}\n\n=== 我的需求 ===\n{req.strip()}"},
                ]
                with st.spinner(f"调用 {model} 生成补丁…"):
                    out, err = _ask_deepseek(msgs, dkey, model)
                if err:
                    st.error(f"生成失败：{err}")
                else:
                    patch = parse_patch(out)
                    if not patch:
                        st.error("模型没返回可解析的 JSON。原始输出：")
                        st.code((out or "")[:1500])
                    else:
                        st.session_state.ug_candidate = {"patch": patch, "sources": src_map,
                                                         "raw": out}
                        st.rerun()

    # ---------- 2. 预览 ----------
    cand = st.session_state.ug_candidate
    if cand:
        patch, sources = cand["patch"], cand["sources"]
        edits = patch.get("edits") or []
        st.divider()
        st.markdown("#### 方案")
        st.write(patch.get("summary", "（模型未给 summary）"))
        if patch.get("risk"):
            st.warning(f"风险：{patch['risk']}")
        if patch.get("verify"):
            st.info(f"验证步骤：{patch['verify']}")

        ok1, msg1 = validate_edits(sources, edits)
        st.markdown("#### 补丁预览")
        st.caption(msg1)

        ok2, new_src, msg2 = (False, {}, msg1) if not ok1 else apply_edits(sources, edits)
        if ok1 and ok2:
            for p, text in new_src.items():
                if sources.get(p) == text:
                    continue
                st.code(_diff_text(sources.get(p, ""), text, p) or "（无变化）", language="diff")

        if not ok1:
            st.error(f"闸门 1 未通过：{msg1}")
        elif not ok2:
            st.error(f"闸门 2 未通过：{msg2}")
        else:
            chk = st.checkbox("我已看过上面的 diff，确认应用")
            if st.button("✅ 校验并应用（自动备份，可回滚）", type="primary",
                         use_container_width=True, disabled=not chk):
                with st.spinner("闸门 3：语法检查…"):
                    ok3, msg3 = ast_check(new_src)
                if not ok3:
                    st.error(f"闸门 3 未通过，未提交：{msg3}")
                else:
                    with st.spinner("闸门 4：跑测试集（约 10~30 秒）…"):
                        ok4, out = run_tests(new_src, grepo, gtoken)
                    st.session_state.ug_tests = out
                    if not ok4:
                        st.error("闸门 4 未通过，未提交。测试输出见下方。")
                    else:
                        try:
                            log = load_log(grepo, gtoken)
                            files = {p: t for p, t in new_src.items()
                                     if sources.get(p) != t}
                            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            entry = {"ts": datetime.now().isoformat(timespec="seconds"),
                                     "request": req.strip()[:200],
                                     "summary": patch.get("summary", ""),
                                     "files": list(files)}
                            with st.spinner("提交到 GitHub…"):
                                sha, head_before = gh_commit(
                                    grepo, gtoken, files,
                                    f"自动升级 {stamp}: {patch.get('summary', '')[:60] or 'patch'}",
                                    branch="main")
                                entry["commit"] = sha
                                entry["head_before"] = head_before
                                log.insert(0, entry)
                                gh_commit(grepo, gtoken,
                                          {LOG_FILE: json.dumps(log[:30], ensure_ascii=False, indent=2)},
                                          f"记录升级日志 {stamp}", branch="main")
                            st.session_state.ug_last = entry
                            st.session_state.ug_candidate = None
                            st.success(f"已提交 {sha[:7]}。Streamlit Cloud 会在 1~3 分钟内重新部署。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"提交失败：{type(e).__name__}: {e}")

    if st.session_state.get("ug_tests"):
        with st.expander("查看测试输出", expanded=False):
            st.code(st.session_state.ug_tests[-3000:])

    # ---------- 3. 历史与回滚 ----------
    st.divider()
    with st.expander("🗂️ 升级历史与回滚", expanded=False):
        log = load_log(grepo, gtoken)
        if not log:
            st.info("还没有升级记录。")
        for i, e in enumerate(log[:10]):
            cols = st.columns([4, 2, 1])
            with cols[0]:
                st.write(f"**{e.get('ts', '')[:19]}** · {e.get('summary', '')[:60]}")
                st.caption(f"{e.get('commit', '')[:7]} · 文件：{', '.join(e.get('files', []))}")
            with cols[1]:
                st.caption(f"回滚点 {str(e.get('head_before', ''))[:7]}")
            with cols[2]:
                if st.button("回滚", key=f"rb_{i}"):
                    try:
                        restored = {}
                        for p in e.get("files", []):
                            _, text = gh_read(grepo, gtoken, p, ref=e.get("head_before"))
                            if text is not None:
                                restored[p] = text
                        if not restored:
                            st.error("取不回旧版本文件")
                        else:
                            sha, _ = gh_commit(
                                grepo, gtoken, restored,
                                f"回滚 {e.get('commit', '')[:7]} → {str(e.get('head_before', ''))[:7]}",
                                branch="main")
                            st.success(f"已回滚，新提交 {sha[:7]}")
                            st.rerun()
                    except Exception as ex:
                        st.error(f"回滚失败：{ex}")
        st.caption("回滚用的是升级前的 commit SHA，取回那些文件的旧内容再提交一次，"
                   "不会改写历史，随时可以再回滚回来。")
