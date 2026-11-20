# -*- coding: utf-8 -*-
"""生成精简索引 _index.csv（期号 + 升序7球 + 按序7球）
   数据文件 11MB → 索引约 200KB，页面加载从几十秒降到 1~2 秒
"""
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
MIRROR = r"D:\666\共享\系统升级前备份\_data_mirror"
OUT = os.path.join(BASE, "_index.csv")


def find(name):
    for p in (os.path.join(BASE, name), os.path.join(MIRROR, name)):
        if os.path.exists(p):
            return p
    return None


def load(name):
    p = find(name)
    if not p:
        return []
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        return list(csv.reader(f))


def parse(rows):
    out = {}
    rowsno = {}
    for _i, r in enumerate(rows[2:], start=3):
        if len(r) < 214:
            continue
        p = f"{r[213]}{r[0]}{r[1]}{r[2]}".strip()
        if not p:
            continue
        nums = []
        for b in range(1, 8):
            i10 = 3 + (b - 1) * 30
            try:
                nums.append(int((r[i10].strip() + r[i10 + 1].strip()) or 0))
            except Exception:
                nums.append(0)
        out[p] = nums
        rowsno.setdefault(p, _i)
    return out, rowsno


up, rno_up = parse(load("升序全套.csv"))
an, rno_an = parse(load("按序全套.csv"))
periods = sorted(set(up) | set(an))
print(f"升序 {len(up)} 期，按序 {len(an)} 期，合并 {len(periods)} 期")

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["期号"] + [f"升{b}" for b in range(1, 8)]
               + [f"按{b}" for b in range(1, 8)] + ["升序行号", "按序行号"])
    for p in periods:
        u = up.get(p, [0] * 7)
        a = an.get(p, [0] * 7)
        w.writerow([p] + u + a + [rno_up.get(p, ""), rno_an.get(p, "")])

size = os.path.getsize(OUT) / 1024
print(f"已生成 {OUT}　{size:.0f} KB　{len(periods)} 行")
