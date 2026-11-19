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
HISTORY_FILE = "_upgrade_history.json"   # 完整留档：需求原文 + 方案 + 补丁
LOG_FILE = "_upgrade_log.json"           # 旧版短日志，仅作向后兼容读取
HISTORY_MAX = 40                         # 最多保留多少条
HISTORY_MAX_CHARS = 900_000              # 超过这个大小就裁剪最老条目的补丁

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


def gh_recent_commits(repo, token, limit=8):
    """只读列出最近提交。返回 [(sha, 首行消息, 时间)]，失败返回 []。"""
    if requests is None:
        return []
    try:
        r = requests.get(f"{GH}/repos/{repo}/commits", headers=_h(token),
                         params={"per_page": limit}, timeout=30)
        if r.status_code != 200:
            return []
        out = []
        for c in r.json():
            msg = (c.get("commit", {}).get("message") or "").splitlines()[0]
            date = (c.get("commit", {}).get("author", {}) or {}).get("date", "")
            out.append((c.get("sha", ""), msg, date))
        return out
    except Exception:
        return []


def gh_revert_commit(repo, token, sha, branch="main"):
    """把某个提交改过的文件恢复到它的父提交，生成一个新提交（不改写历史）。
    返回 (新提交 sha, 恢复的文件列表)。"""
    if requests is None:
        raise RuntimeError("缺少 requests 库")
    r = requests.get(f"{GH}/repos/{repo}/commits/{sha}", headers=_h(token), timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"读取提交失败 {r.status_code}: {r.text[:200]}")
    detail = r.json()

    parents = detail.get("parents") or []
    if not parents:
        raise RuntimeError("这是首个提交，没有父提交可回滚")
    parent = parents[0]["sha"]

    names = [f.get("filename") for f in (detail.get("files") or [])
             if f.get("filename") and f.get("status") != "removed"]
    if not names:
        raise RuntimeError("这个提交里没有可恢复的文件")

    restore = {}
    for p in names:
        _, text = gh_read(repo, token, p, ref=parent)
        if text is not None:
            restore[p] = text
    if not restore:
        raise RuntimeError("取不到父提交里的文件内容")

    new_sha, _ = gh_commit(repo, token, restore,
                           f"回滚 {sha[:7]} → {parent[:7]}", branch=branch)
    return new_sha, list(restore)


def gh_commit(repo, token, files, message, branch="main"):
    """原子提交多个文件。返回 (commit_sha, 提交前的 head_sha)。

    注意：tree 条目里的 sha 必须是 blobs 接口真正返回的 40 位十六进制串。
    早前版本直接取 blob["sha"]，一旦上游返回异常体就会把空值塞进 tree，
    GitHub 报 422 Invalid tree info。这里逐项校验，并准备了内联 content 的回退。
    """
    if requests is None:
        raise RuntimeError("缺少 requests 库")
    base = f"{GH}/repos/{repo}"

    def call(method, path, **kw):
        r = requests.request(method, base + path, headers=_h(token), timeout=60, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except Exception:
            raise RuntimeError(f"{method} {path} 返回非 JSON: {r.text[:200]}")

    def _sha_of(obj, what):
        sha = obj.get("sha") if isinstance(obj, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise RuntimeError(f"{what} 没有返回有效 sha，实际返回：{str(obj)[:300]}")
        return sha

    head = _sha_of(call("GET", f"/git/ref/heads/{branch}").get("object", {}), "ref/heads")
    tree_sha = _sha_of(call("GET", f"/git/commits/{head}").get("tree", {}), "commits.tree")

    entries = []
    for path, text in files.items():
        blob = call("POST", "/git/blobs", json={"content": text, "encoding": "utf-8"})
        entries.append({"path": path, "mode": "100644", "type": "blob",
                        "sha": _sha_of(blob, f"blob({path})")})

    def _tree_error(kind, exc):
        detail = json.dumps({"base_tree": tree_sha, "tree": entries if kind == "sha" else
                             [{"path": p, "mode": "100644", "type": "blob",
                               "content_len": len(t)} for p, t in files.items()]},
                            ensure_ascii=False)[:600]
        return RuntimeError(f"{exc}\n\n发送内容：{detail}")

    try:
        tree = call("POST", "/git/trees", json={"base_tree": tree_sha, "tree": entries})
    except RuntimeError as e:
        if "422" not in str(e):
            raise
        # 回退 1：内联 content，避免 blob 引用
        inline = [{"path": p, "mode": "100644", "type": "blob", "content": t}
                  for p, t in files.items()]
        try:
            tree = call("POST", "/git/trees", json={"base_tree": tree_sha, "tree": inline})
        except RuntimeError as e2:
            # 回退 2：单文件时改走 Contents API（一次 PUT 一个文件，最稳）
            if len(files) == 1:
                path, text = next(iter(files.items()))
                old_sha, _ = gh_read(repo, token, path)
                body = {"message": message, "content": base64.b64encode(
                    text.encode("utf-8")).decode("utf-8"), "branch": branch}
                if old_sha:
                    body["sha"] = old_sha
                r = requests.put(f"{base}/contents/{path}",
                                 headers=_h(token), json=body, timeout=60)
                if r.status_code in (200, 201):
                    sha = (r.json().get("commit") or {}).get("sha", "")
                    return sha, head
                raise _tree_error("sha", f"{e}\n回退内容内联仍失败：{e2}\n"
                                         f"Contents API 也失败 {r.status_code}: {r.text[:300]}")
            raise _tree_error("sha", f"{e}\n回退内容内联仍失败：{e2}")

    commit = call("POST", "/git/commits",
                  json={"message": message, "tree": _sha_of(tree, "trees"),
                        "parents": [head]})
    call("PATCH", f"/git/refs/heads/{branch}",
         json={"sha": _sha_of(commit, "commits"), "force": False})
    return commit["sha"], head


def gh_selftest(repo, token, branch="main"):
    """只读自检：走到 blob 为止，不建 tree、不建 commit、不改任何引用。
    用来在提交前暴露权限/接口问题。返回逐行日志。"""
    log = []
    if requests is None:
        return ["缺少 requests 库"]
    base = f"{GH}/repos/{repo}"

    def probe(method, path, **kw):
        try:
            r = requests.request(method, base + path, headers=_h(token), timeout=30, **kw)
        except Exception as e:
            log.append(f"{method} {path} -> 异常 {type(e).__name__}: {e}")
            return None
        body = r.text[:200].replace("\n", " ")
        log.append(f"{method} {path} -> {r.status_code} {body if r.status_code >= 300 else ''}".rstrip())
        try:
            return r.json()
        except Exception:
            return None

    ref = probe("GET", f"/git/ref/heads/{branch}")
    head = (ref or {}).get("object", {}).get("sha")
    if not head:
        log.append("→ 取不到分支 head，后面的检查无法进行（分支名是否为 main？）")
        return log

    commit = probe("GET", f"/git/commits/{head}")
    if not (commit or {}).get("tree", {}).get("sha"):
        log.append("→ 取不到 commit 的 tree")
    else:
        log.append(f"→ head={head[:7]} tree={commit['tree']['sha'][:7]}")

    blob = probe("POST", "/git/blobs", json={"content": "selftest", "encoding": "utf-8"})
    sha = (blob or {}).get("sha")
    if not (sha and re.fullmatch(r"[0-9a-f]{40,64}", sha)):
        log.append("→ blob 创建失败：token 缺少 Contents: write，或该仓库未授权")
        return log
    log.append(f"→ blob 创建成功 {sha[:7]}")

    # 再试建一个游离 tree（不提交、不改引用，GitHub 会自行回收）
    commit2 = commit or {}
    base_tree = (commit2.get("tree") or {}).get("sha")
    tree = probe("POST", "/git/trees", json={
        "base_tree": base_tree,
        "tree": [{"path": "_selftest_probe.txt", "mode": "100644", "type": "blob", "sha": sha}],
    })
    if (tree or {}).get("sha"):
        log.append(f"→ tree 创建成功 {tree['sha'][:7]}（提交链路可用）")
    else:
        log.append("→ tree 创建失败：把上面那行 422 的返回体贴给我，我按返回体修")
    return log


def _read_json_list(repo, token, path):
    _, text = gh_read(repo, token, path)
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_history(repo, token):
    """读取完整升级历史。优先新文件，没有则回落到旧日志（字段较少）。"""
    data = _read_json_list(repo, token, HISTORY_FILE)
    if data:
        return data
    return _read_json_list(repo, token, LOG_FILE)


def load_log(repo, token):
    """兼容旧调用名。"""
    return load_history(repo, token)


def save_history(repo, token, entries, message=None):
    """写入升级历史。自动裁剪到 HISTORY_MAX 条、并在过大时丢弃最老条目的补丁内容。"""
    entries = list(entries)[:HISTORY_MAX]
    payload = json.dumps(entries, ensure_ascii=False, indent=1)
    if len(payload) > HISTORY_MAX_CHARS:
        # 从最老的开始削减补丁体积，保留需求原文与摘要（那才是最有用的）
        for e in reversed(entries):
            if e.get("edits"):
                e["edits_note"] = f"补丁内容已裁剪以控制文件体积（原 {len(e['edits'])} 条）"
                e["edits"] = []
                payload = json.dumps(entries, ensure_ascii=False, indent=1)
                if len(payload) <= HISTORY_MAX_CHARS:
                    break
    return gh_commit(repo, token, {HISTORY_FILE: payload},
                     message or "更新升级历史", branch="main")


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
项目结构：app.py（主程序，含主控台/多维分析/深度联动/AI推演/遗漏核算/后台管理）、
ai_chat_page.py（AI 对话页）、auto_upgrade.py（本引擎）、system_tests.py（测试集）、
fix_full_csv_attrs.py（CSV 重算脚本）。
数据在 GitHub 仓库，数据库用 Supabase，AI 用 DeepSeek。
回答必须是一个 JSON，格式见用户消息中的协议说明。"""

CHAT_SYSTEM = """你是这个 Streamlit 项目的资深开发助手。现在是【需求确认阶段】，还没有开始改代码。

你的任务：和主人把需求聊清楚，避免他描述不完整、你理解偏差。

每次回复必须包含：
1. **我的理解**：用一两句话复述他想要的结果（具体到页面、按钮、行为）。
2. **需要你确认**：列出 1~3 个关键问题（例如放在哪个位置、导出什么格式、边界情况怎么处理）。
3. **我打算怎么改**：说明会动哪个函数、大概改几行、有没有副作用（会不会影响已有功能、要不要清缓存）。
4. 如果信息已经够清楚，就明确说「需求已清楚，可以生成补丁了」，不要再硬凑问题。

硬性要求：
- 这一阶段**绝对不要输出代码、不要输出 JSON、不要输出补丁**。
- 不要臆测他没说的事；不确定就问他。
- 简体中文，简短，别写客套话，别复述他的原话。"""


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


# ================================================================ 本机文件模式
def _app_dir():
    """正在被 Streamlit 运行的脚本所在目录"""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        p = getattr(ctx, "main_script_path", None) if ctx else None
        if p:
            return os.path.dirname(os.path.abspath(p))
    except Exception:
        pass
    try:
        import sys
        if sys.argv and str(sys.argv[0]).endswith(".py"):
            return os.path.dirname(os.path.abspath(sys.argv[0]))
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


def local_available():
    """本机模式是否可用：目录存在且可写"""
    d = _app_dir()
    if not os.path.isdir(d):
        return False, d, "目录不存在"
    try:
        probe = os.path.join(d, "_write_probe.tmp")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True, d, ""
    except Exception as e:
        return False, d, f"{type(e).__name__}: {e}"


def local_read(name):
    """读本机文件，返回文本或 None"""
    p = os.path.join(_app_dir(), name)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def local_write(files, stamp):
    """写本机文件，先备份成 .bak_<时间>。返回 (成功文件, 失败信息)"""
    d = _app_dir()
    done, errs = [], []
    for name, text in files.items():
        p = os.path.join(d, name)
        try:
            if os.path.exists(p):
                bak = f"{p}.bak_{stamp}"
                if not os.path.exists(bak):
                    with open(p, "rb") as src, open(bak, "wb") as dst:
                        dst.write(src.read())
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, p)
            done.append(name)
        except Exception as e:
            errs.append(f"{name}: {type(e).__name__}: {e}")
    return done, errs


def local_load_history():
    try:
        p = os.path.join(_app_dir(), HISTORY_FILE)
        if not os.path.exists(p):
            return []
        import json as _json
        with open(p, encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def local_save_history(entries):
    import json as _json
    p = os.path.join(_app_dir(), HISTORY_FILE)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(_json.dumps(list(entries)[:HISTORY_MAX], ensure_ascii=False, indent=1))


def _diff_text(old, new, path):
    import difflib
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=3))


def render_upgrade_tab():
    st.markdown("### 🛠️ 自动升级")
    st.caption("先和 AI 聊清楚（可多轮）→ 你确认 → 生成补丁 → 四道校验 → 原子提交。"
               "任何一步失败都不会改动仓库。")

    dkey, gtoken, grepo = _cfg()
    _local_ok, _local_dir, _local_err = local_available()
    _gh_ok = bool(gtoken and grepo)

    if not dkey:
        st.error("Secrets 里缺 DEEPSEEK_API_KEY。补上并 Reboot app。")
        return
    if not (_gh_ok or _local_ok):
        st.error(f"既读不到 GitHub 仓库（缺 GITHUB_TOKEN/GITHUB_REPO），"
                 f"本机目录也不可写：{_local_err}")
        return

    st.session_state.setdefault("ug_candidate", None)
    st.session_state.setdefault("ug_tests", "")
    st.session_state.setdefault("ug_last", None)
    st.session_state.setdefault("ug_selftest", [])
    st.session_state.setdefault("ug_chat", [])

    # ---------- 0. 写入位置 ----------
    mode_opts = []
    if _local_ok:
        mode_opts.append("本机文件")
    if _gh_ok:
        mode_opts.append("GitHub 仓库")
    default_mode = "本机文件" if _local_ok else "GitHub 仓库"
    mode = st.radio("写入位置", mode_opts, index=mode_opts.index(default_mode),
                    horizontal=True, key="ug_mode",
                    help="本机文件：直接改你电脑上的 app.py，改完网页自动重载，不用上传。"
                         "GitHub 仓库：提交到云端，用户能看到，但每次要等 1~3 分钟部署。")
    if mode == "本机文件":
        st.caption(f"📁 将写入：`{_local_dir}`（每次先自动备份成 `.bak_时间`，可回滚）")
    else:
        st.caption(f"☁️ 将提交到：`{grepo}`（走四道闸门 + 原子提交）")

    # ---------- 0.1 连接自检（仅 GitHub 模式） ----------
    if mode == "GitHub 仓库":
        sc1, sc2 = st.columns([1, 4])
        with sc1:
            if st.button("🔍 连接自检", use_container_width=True,
                         help="只读检查分支、commit、blob 写权限。不会创建提交，不改任何文件。"):
                st.session_state.ug_selftest = gh_selftest(grepo, gtoken)
        with sc2:
            if st.session_state.ug_selftest:
                st.caption("自检结果（最后一行决定能不能提交）")
        if st.session_state.ug_selftest:
            with st.expander("自检详细日志", expanded=True):
                st.code("\n".join(st.session_state.ug_selftest), language="text")

    # ---------- 1. 参考文件与模型 ----------
    c1, c2 = st.columns([2, 1])
    with c1:
        targets = st.multiselect("让 AI 参考哪些文件", ["app.py", "ai_chat_page.py", "auto_upgrade.py"],
                                 default=["app.py"])
    with c2:
        model = st.selectbox("模型", ["deepseek-chat", "deepseek-reasoner"])

    # ---------- 2. 先聊清楚（多轮对话） ----------
    st.markdown("#### ① 先说清楚（可多轮）")
    st.caption("它先复述理解、指出歧义、给方案；你说「可以」之后再生成补丁。这样能避免一次做错。")

    for _m in st.session_state.ug_chat:
        with st.chat_message(_m["role"]):
            st.markdown(_m["content"])

    cc1, cc2 = st.columns([1, 4])
    with cc1:
        if st.button("🗑 清空对话", use_container_width=True):
            st.session_state.ug_chat = []
            st.rerun()
    with cc2:
        n_chat = len(st.session_state.ug_chat)
        st.caption(f"当前 {n_chat} 条消息" + ("（可以直接生成补丁了）" if n_chat >= 2 else ""))

    prompt = st.chat_input("说说你想改什么…（Enter 发送）")
    if prompt:
        st.session_state.ug_chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        _msgs = [{"role": "system", "content": CHAT_SYSTEM}] + \
                st.session_state.ug_chat[-16:]
        with st.chat_message("assistant"):
            with st.spinner("思考中…"):
                _out, _err = _ask_deepseek(_msgs, dkey, model)
            if _err:
                st.error(f"接口报错：{_err}")
                _out = f"（接口出错：{_err}）"
            else:
                st.markdown(_out)
        st.session_state.ug_chat.append({"role": "assistant", "content": _out})
        st.rerun()

    # ---------- 3. 生成补丁 ----------
    st.markdown("#### ② 确认无误，生成补丁")
    if st.session_state.pop("_ug_from_chat", False):
        st.success("✅ 需求已从「💬 AI 助手」带入，可以直接生成，也可以先改。")

    req = st.text_area("补充说明（可选；主要需求来自上面的对话）", height=90, key="ug_req",
                       placeholder="例：另外记得把导出按钮放在表格下方、靠右。")

    _conv = "\n".join(f"{'我' if m['role'] == 'user' else '助手'}：{m['content']}"
                      for m in st.session_state.ug_chat)
    full_req = (_conv + (("\n\n补充说明：" + req.strip()) if req.strip() else "")).strip()

    st.caption(f"⚠️ 生成时会把目标文件全文 + 上面的对话一起发给 DeepSeek。"
               f"app.py 约 13 万字符 ≈ 4 万 token，一次几分到几毛钱。")

    if st.button("🧠 生成方案与补丁", type="primary", use_container_width=True):
        if not full_req:
            st.warning("先在上面聊两句，或在补充说明里写要求")
        elif not targets:
            st.warning("至少选一个参考文件")
        else:
            st.session_state.ug_candidate = None
            st.session_state.ug_tests = ""

            src_map, missing = {}, []
            for p in targets:
                if mode == "本机文件":
                    text = local_read(p)
                else:
                    _, text = gh_read(grepo, gtoken, p)
                if text is None:
                    missing.append(p)
                else:
                    src_map[p] = text
            if missing:
                where = "本机目录" if mode == "本机文件" else "仓库里"
                st.error(f"{where}读不到：{missing}")
            else:
                ctx = "\n\n".join(f"=== 文件 {p} 全文 ===\n```python\n{t}\n```"
                                  for p, t in src_map.items())
                msgs = [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"{PROTOCOL}\n\n{ctx}\n\n"
                                                f"=== 我和你的沟通记录 ===\n{full_req}"},
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
        st.info("⚠️ 下面只是预览，**还没有写入仓库**。必须勾选确认并点「校验并应用」才会提交。")

        st.markdown("#### ① 方案")
        st.write(patch.get("summary") or "（模型未给 summary）")
        if patch.get("risk"):
            st.warning(f"风险：{patch['risk']}")
        if patch.get("verify"):
            st.info(f"验证步骤：{patch['verify']}")

        # 闸门 1 / 2
        ok1, msg1 = validate_edits(sources, edits)
        ok2, new_src, msg2 = (False, {}, msg1) if not ok1 else apply_edits(sources, edits)

        changed = {}
        if ok1 and ok2:
            changed = {p: t for p, t in new_src.items() if sources.get(p) != t}

        added = removed = 0
        import difflib
        for p, t in changed.items():
            old = (sources.get(p) or "").splitlines()
            new = t.splitlines()
            for line in difflib.unified_diff(old, new, lineterm="", n=0):
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1

        st.markdown("#### ② 闸门检查")
        g = st.columns(4)
        with g[0]:
            st.metric("改动的文件", len(changed))
        with g[1]:
            st.metric("新增行", added)
        with g[2]:
            st.metric("删除行", removed)
        with g[3]:
            st.metric("edits 条数", len(edits))

        st.markdown("#### ③ 补丁预览")
        if not ok1:
            st.error(f"闸门 1（规则校验）未通过：{msg1}")
            if "出现 0 次" in msg1:
                st.caption(
                    "含义：模型给出的 `find` 片段在文件里找不到原文（它没有逐字符照抄，"
                    "常发生在缩进、引号或中文标点上）。补丁被拒绝，什么都没改。\n\n"
                    "办法：展开下面「查看模型原始输出」，把它的 find 和真实代码对比；"
                    "或者把需求写得更具体（指明函数名和要改的那一行），重新生成。")
        elif not ok2:
            st.error(f"闸门 2（补丁应用）未通过：{msg2}")
        elif not changed:
            st.warning(
                "模型返回的补丁**没有产生任何实际变化**（`find` 与 `replace` 内容相同，"
                "或改动被原地替换回去了）。这通常是需求太笼统或模型偷懒。\n\n"
                "建议：把需求写得更具体（要改哪个函数、在哪一行附近、加什么），再重新生成。")
        else:
            st.caption(f"闸门 1、2 通过：{msg2}")
            for p, text in changed.items():
                st.markdown(f"**{p}**")
                st.code(_diff_text(sources.get(p, ""), text, p) or "（无变化）", language="diff")

        if cand.get("raw"):
            with st.expander("查看模型原始输出（排查用）", expanded=False):
                st.code((cand["raw"] or "")[:4000])

        if ok1 and ok2 and changed:
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
                        files = {p: t for p, t in new_src.items() if sources.get(p) != t}
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        entry = {
                            "ts": datetime.now().isoformat(timespec="seconds"),
                            "request": full_req,                  # 对话+补充说明全文
                            "summary": patch.get("summary", ""),
                            "risk": patch.get("risk", ""),
                            "verify": patch.get("verify", ""),
                            "edits": edits,                          # 补丁本体，可重放
                            "files": list(files),
                        }

                        # 第一步：落盘 / 提交。只有这一步失败才算应用失败。
                        if mode == "本机文件":
                            done, errs = local_write(files, stamp)
                            if errs:
                                st.error("❌ 写入本机失败：\n" + "\n".join(errs))
                            else:
                                try:
                                    hist = local_load_history()
                                    entry["commit"] = f"local_{stamp}"
                                    entry["head_before"] = ""
                                    hist.insert(0, entry)
                                    local_save_history(hist)
                                except Exception as e2:
                                    st.warning(f"已写入本机，但历史存档失败：{e2}")

                                st.session_state.ug_last = entry
                                st.session_state.ug_candidate = None
                                st.success(f"✅ 已写入本机：{', '.join(done)}\n\n"
                                           f"备份：同名文件 + `.bak_{stamp}`\n\n"
                                           f"Streamlit 会自动重载；没反应就在网页右上角点一次 **Rerun**。")
                                st.rerun()
                        else:
                            sha = None
                            try:
                                with st.spinner("提交代码到 GitHub…"):
                                    sha, head_before = gh_commit(
                                        grepo, gtoken, files,
                                        f"自动升级 {stamp}: {patch.get('summary', '')[:60] or 'patch'}",
                                        branch="main")
                                entry["commit"] = sha
                                entry["head_before"] = head_before
                            except Exception as e:
                                st.error(f"❌ 代码提交失败，仓库未改动：{type(e).__name__}: {e}")

                            if sha:
                                # 第二步：存档。失败只警告，绝不影响已成功的提交。
                                try:
                                    hist = load_history(grepo, gtoken)
                                    hist.insert(0, entry)
                                    save_history(grepo, gtoken, hist, f"记录升级历史 {stamp}")
                                except Exception as e2:
                                    st.warning(f"代码已提交成功，但存档失败（不影响使用）："
                                               f"{type(e2).__name__}: {str(e2)[:200]}")

                                st.session_state.ug_last = entry
                                st.session_state.ug_candidate = None
                                st.success(f"✅ 已提交 {sha[:7]}。Streamlit Cloud 会在 1~3 分钟内重新部署。"
                                           f"\n\n改动文件：{', '.join(files)}")
                                st.rerun()

    if st.session_state.get("ug_tests"):
        with st.expander("查看测试输出", expanded=False):
            st.code(st.session_state.ug_tests[-3000:])

    # ---------- 3. 历史与回滚 ----------
    st.divider()
    with st.expander("🗂️ 升级历史与回滚", expanded=False):
        hist = local_load_history() if mode == "本机文件" else load_history(grepo, gtoken)
        if not hist:
            _where = "本机目录" if mode == "本机文件" else "仓库"
            st.info(f"还没有升级记录。每次成功应用后，需求原文与补丁都会存档到{_where}的 "
                    f"`{HISTORY_FILE}`。")
        else:
            hc1, hc2 = st.columns([1, 3])
            with hc1:
                st.download_button(
                    "📥 导出全部历史 (JSON)",
                    json.dumps(hist, ensure_ascii=False, indent=2).encode("utf-8-sig"),
                    file_name=f"升级历史_{datetime.now():%Y%m%d}.json",
                    mime="application/json", use_container_width=True)
            with hc2:
                st.caption(f"共 {len(hist)} 条。每条都保存了需求原文和补丁，回滚后可以直接填回或重放，"
                           f"不用重新写、不用再花钱生成。")

        for i, e in enumerate(hist[:10]):
            ts = str(e.get("ts", ""))[:19].replace("T", " ")
            title = f"{ts} · {str(e.get('summary', ''))[:50] or '（无摘要）'}"
            with st.expander(title, expanded=False):
                if e.get("files"):
                    st.caption(f"文件：{', '.join(e['files'])}　·　提交 "
                               f"{str(e.get('commit', ''))[:7]}　·　回滚点 "
                               f"{str(e.get('head_before', ''))[:7]}")
                st.markdown("**需求原文**")
                if e.get("request"):
                    st.text_area("需求", value=e["request"], height=170,
                                 key=f"hist_req_{i}", label_visibility="collapsed")
                else:
                    st.caption("（这条是旧版记录，没有保存需求原文）")

                if e.get("risk") or e.get("verify"):
                    with st.expander("风险 / 验收", expanded=False):
                        if e.get("risk"): st.write(f"风险：{e['risk']}")
                        if e.get("verify"): st.write(f"验收：{e['verify']}")

                if e.get("edits_note"):
                    st.caption(e["edits_note"])

                a1, a2, a3 = st.columns(3)
                with a1:
                    if st.button("📋 填回需求框", key=f"fill_{i}", use_container_width=True):
                        st.session_state["ug_req"] = e.get("request", "")
                        st.session_state["_ug_from_chat"] = True
                        st.success("已填入上方需求框，可直接修改后重新生成。")
                        st.rerun()
                with a2:
                    if st.button("♻️ 重放这份补丁", key=f"replay_{i}", use_container_width=True,
                                 help="用存档里的补丁直接重新应用，不调用 AI，不花钱"):
                        ed = e.get("edits") or []
                        if not ed:
                            st.error("这条记录没有保存补丁内容，只能填回需求重新生成。")
                        else:
                            src_map = {}
                            for p in e.get("files", []):
                                t = (local_read(p) if mode == "本机文件"
                                     else gh_read(grepo, gtoken, p)[1])
                                if t is not None:
                                    src_map[p] = t
                            ok1, m1 = validate_edits(src_map, ed)
                            ok2, ns, m2 = (False, {}, m1) if not ok1 else apply_edits(src_map, ed)
                            if not (ok1 and ok2):
                                st.error(f"无法重放：{m1 if not ok1 else m2}\n\n"
                                         "多半是文件已改动，`find` 对不上了。用「填回需求框」重新生成更稳妥。")
                            else:
                                ok3, m3 = ast_check(ns)
                                if not ok3:
                                    st.error(f"语法检查未通过：{m3}")
                                else:
                                    with st.spinner("跑测试集…"):
                                        ok4, out = run_tests(ns, grepo, gtoken)
                                    if not ok4:
                                        st.error("测试未通过，未提交。")
                                        st.code(out[-1500:])
                                    else:
                                        files = {p: t for p, t in ns.items()
                                                 if src_map.get(p) != t}
                                        try:
                                            sha, _ = gh_commit(
                                                grepo, gtoken, files,
                                                f"重放升级 {datetime.now():%Y%m%d_%H%M%S}: "
                                                f"{str(e.get('summary', ''))[:50]}",
                                                branch="main")
                                            st.success(f"已重放，提交 {sha[:7]}")
                                            st.rerun()
                                        except Exception as ex:
                                            st.error(f"提交失败：{ex}")
                with a3:
                    st.download_button(
                        "⬇ 导出本条", json.dumps(e, ensure_ascii=False, indent=2).encode("utf-8-sig"),
                        file_name=f"升级记录_{ts.replace(':', '').replace('-', '').replace(' ', '_')}.json",
                        mime="application/json", use_container_width=True,
                        key=f"dl_{i}")

                if e.get("head_before"):
                    if st.button("↩️ 直接回滚到这次升级之前", key=f"rb_{i}", use_container_width=True):
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
                                    f"回滚 {str(e.get('commit', ''))[:7]} → "
                                    f"{str(e.get('head_before', ''))[:7]}", branch="main")
                                st.success(f"已回滚，新提交 {sha[:7]}")
                                st.rerun()
                        except Exception as ex:
                            st.error(f"回滚失败：{ex}")

        st.caption("回滚用的是升级前的 commit SHA，取回那些文件的旧内容再提交一次，"
                   "不会改写历史，随时可以再回滚回来。")

        st.markdown("---")
        if mode == "本机文件":
            st.markdown("**本机模式：用备份回滚**")
            st.caption("每次写入都会生成 `文件名.bak_时间`。要退回某版：先关掉网站，"
                       "把那个 .bak_xxx 改名回原文件名。")
            _baks = []
            try:
                import glob as _glob
                _baks = sorted(_glob.glob(os.path.join(_local_dir, "*.bak_*")), reverse=True)[:12]
            except Exception:
                pass
            if _baks:
                st.code("\n".join(os.path.basename(b) for b in _baks), language="text")
            else:
                st.caption("（还没有备份文件）")
        st.markdown("**最近提交（直接从 GitHub 读，不依赖存档文件）**")
        st.caption("存档写失败时，用这里回滚。回滚 = 把该提交改过的文件恢复到它的上一个版本。")
        recent = gh_recent_commits(grepo, gtoken, 8)
        if not recent:
            st.info("读不到提交列表（可能是 token 没有读权限）。")
        for i, (sha, msg, date) in enumerate(recent):
            cols = st.columns([5, 2, 1])
            with cols[0]:
                st.write(f"`{sha[:7]}` {msg[:70]}")
                st.caption(date[:19].replace("T", " "))
            with cols[1]:
                st.caption("")
            with cols[2]:
                if st.button("回滚此提交", key=f"revert_{i}"):
                    try:
                        with st.spinner("正在恢复上一个版本…"):
                            new_sha, names = gh_revert_commit(grepo, gtoken, sha)
                        st.success(f"已回滚，新提交 {new_sha[:7]}；恢复文件：{', '.join(names)}")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"回滚失败：{ex}")
