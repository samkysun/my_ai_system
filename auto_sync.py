# -*- coding: utf-8 -*-
"""自动同步：本地文件一改动就推送到 GitHub（云端永远是最新的）
   用法：python auto_sync.py          （跟随启动脚本后台运行）
         python auto_sync.py --once   （只同步一次）
"""
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(APP_DIR, ".streamlit", "secrets.toml")
STATE = os.path.join(APP_DIR, "_auto_sync_state.json")
LOG = os.path.join(APP_DIR, "auto_sync.log")
BRANCH = "main"
INTERVAL = 15

WATCH = ["app.py", "calc_center.py", "ai_chat_page.py", "omission_page.py",
         "requirements.txt"]


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_secrets():
    if not os.path.exists(SECRETS):
        return None, None
    raw = open(SECRETS, encoding="utf-8").read()
    import re
    def get(k):
        m = re.search(rf'^\s*{k}\s*=\s*"([^"]*)"', raw, re.M)
        return m.group(1).strip() if m else ""
    return get("GITHUB_TOKEN"), get("GITHUB_REPO")


TOKEN, REPO = read_secrets()
if not TOKEN or not REPO:
    log("[X] secrets.toml 里没有 GITHUB_TOKEN / GITHUB_REPO，无法同步")
    sys.exit(1)

HDR = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
       "Content-Type": "application/json"}


def api(method, path, body=None):
    url = "https://api.github.com" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HDR, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def remote_sha(name):
    s, info = api("GET", f"/repos/{REPO}/contents/{name}?ref={BRANCH}")
    if s == 200:
        return info["sha"], base64.b64decode(info["content"])
    return None, None


def push(name, path):
    data = open(path, "rb").read()
    sha, remote = remote_sha(name)
    if remote is not None and remote == data:
        return False
    body = {"message": f"自动同步 {name} {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "content": base64.b64encode(data).decode(), "branch": BRANCH}
    if sha:
        body["sha"] = sha
    s, res = api("PUT", f"/repos/{REPO}/contents/{name}", body)
    if s in (200, 201):
        log(f"[OK] 已同步 {name} -> 提交 {res['commit']['sha'][:7]}")
        return True
    log(f"[X] 同步 {name} 失败 {s}: {str(res)[:150]}")
    return False


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    try:
        json.dump(st, open(STATE, "w", encoding="utf-8"))
    except Exception:
        pass


def signature(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return ""


def sync_once(state):
    changed = 0
    for name in WATCH:
        path = os.path.join(APP_DIR, name)
        if not os.path.exists(path):
            continue
        sig = signature(path)
        if state.get(name) == sig:
            continue
        if push(name, path):
            state[name] = sig
            changed += 1
        else:
            # 即使内容相同也要记住，避免每轮重复比对
            if sig:
                state[name] = sig
    save_state(state)
    return changed


def main():
    once = "--once" in sys.argv
    log(f"自动同步启动｜仓库 {REPO}｜监控 {len(WATCH)} 个文件｜间隔 {INTERVAL}s")
    state = load_state()
    if sync_once(state):
        log("首次同步完成")
    if once:
        log("单次同步结束")
        return
    while True:
        time.sleep(INTERVAL)
        try:
            n = sync_once(state)
            if n:
                log(f"检测到 {n} 个文件更新，已推送")
        except Exception as e:
            log(f"[!] 同步异常：{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
