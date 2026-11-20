# -*- coding: utf-8 -*-
"""系统全量备份 / 恢复工具

用法：
  python backup_system.py            # 立即备份
  python backup_system.py --list     # 列出已有备份
  python backup_system.py --restore 20261120_134500   # 恢复到指定备份

备份内容：所有 .py .json .txt .csv .xlsx .bat 以及 .streamlit/secrets.toml
存放位置：<项目目录>/_backups/site_YYYYmmdd_HHMMSS.zip
保留策略：默认保留最近 30 份，更早的自动删除
"""
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE, "_backups")
KEEP = 30

INCLUDE_EXT = {".py", ".json", ".txt", ".bat", ".csv", ".xlsx", ".toml", ".md"}
SKIP_DIRS = {"_backups", "__pycache__", ".git", "_data"}


def collect_files():
    out = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in INCLUDE_EXT:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, BASE)
                out.append((full, rel))
    return out


def sha256(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def do_backup(tag=""):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"site_{stamp}{('_' + tag) if tag else ''}.zip"
    dst = os.path.join(BACKUP_DIR, name)

    files = collect_files()
    manifest = {"created": datetime.now().isoformat(timespec="seconds"),
                "file_count": len(files), "files": {}}
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, rel in files:
            try:
                z.write(full, rel)
                manifest["files"][rel] = {"size": os.path.getsize(full),
                                          "sha256": sha256(full)}
            except Exception as e:
                print(f"  跳过 {rel}: {e}")
        z.writestr("_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    size_mb = os.path.getsize(dst) / 1024 / 1024
    print(f"[OK] 备份完成：{dst}")
    print(f"   文件 {len(files)} 个，压缩包 {size_mb:.2f} MB")

    # 清理旧备份
    zips = sorted(f for f in os.listdir(BACKUP_DIR)
                  if f.startswith("site_") and f.endswith(".zip"))
    for old in zips[:-KEEP]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
            print(f"   已清理旧备份 {old}")
        except Exception:
            pass
    return dst


def do_list():
    if not os.path.isdir(BACKUP_DIR):
        print("还没有备份")
        return
    zips = sorted((f for f in os.listdir(BACKUP_DIR)
                   if f.startswith("site_") and f.endswith(".zip")), reverse=True)
    if not zips:
        print("还没有备份")
        return
    print(f"共 {len(zips)} 份备份（新→旧）：")
    for z in zips:
        p = os.path.join(BACKUP_DIR, z)
        print(f"  {z}   {os.path.getsize(p)/1024/1024:6.2f} MB   "
              f"{datetime.fromtimestamp(os.path.getmtime(p)):%Y-%m-%d %H:%M:%S}")


def do_restore(stamp):
    target = None
    for f in os.listdir(BACKUP_DIR):
        if f.endswith(".zip") and stamp in f:
            target = os.path.join(BACKUP_DIR, f)
            break
    if not target:
        print(f"找不到包含 {stamp} 的备份")
        return

    # 恢复前先给当前状态做一次备份
    print("恢复前先备份当前状态…")
    do_backup("prerestore")

    with zipfile.ZipFile(target) as z:
        names = [n for n in z.namelist() if n != "_MANIFEST.json"]
        for n in names:
            dest = os.path.join(BASE, n)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(n) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    print(f"[OK] 已恢复 {len(names)} 个文件（来自 {os.path.basename(target)}）")
    print("   请重启网站使改动生效")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        do_backup()
    elif args[0] == "--list":
        do_list()
    elif args[0] == "--restore":
        if len(args) < 2:
            print("用法：python backup_system.py --restore 20261120_134500")
        else:
            do_restore(args[1])
    else:
        do_backup("_".join(args))
