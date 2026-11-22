# -*- coding: utf-8 -*-
"""生成 _zodiac_by_year.csv 与 _zodiac_attrs.csv（都很小）"""
import csv
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\666\共享\系统升级前备份\_data_mirror\升序全套.csv"
D = os.path.dirname(os.path.abspath(__file__))
OUT1 = os.path.join(D, "_zodiac_by_year.csv")
OUT2 = os.path.join(D, "_zodiac_attrs.csv")

PAIRS = [("生肖五行", 14), ("颜色肖", 15), ("物象", 17), ("方位", 25),
         ("福禄寿", 28), ("大小肖", 29), ("阴阳天地", 22)]

rows = list(csv.reader(open(SRC, encoding="utf-8-sig", errors="replace")))
zy = {}                     # (year, num) -> 生肖
zattr = defaultdict(dict)   # 生肖 -> {属性: 值}

for r in rows[2:]:
    if len(r) < 214:
        continue
    try:
        y = int(r[213])
    except Exception:
        continue
    for b in range(1, 8):
        base = 3 + (b - 1) * 30
        try:
            num = int((r[base].strip() + r[base + 1].strip()) or 0)
        except Exception:
            continue
        if not (1 <= num <= 49):
            continue
        z = r[base + 3].strip()
        if not z:
            continue
        zy[(y, num)] = z          # 同一年内应当一致，后写覆盖
        for name, off in PAIRS:
            v = r[base + off].strip()
            if v:
                zattr[z][name] = v

with open(OUT1, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["年份", "号码", "生肖"])
    for (y, n) in sorted(zy):
        w.writerow([y, n, zy[(y, n)]])

with open(OUT2, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["生肖"] + [n for n, _ in PAIRS])
    for z in sorted(zattr):
        w.writerow([z] + [zattr[z].get(n, "") for n, _ in PAIRS])

print("画像表：", len(zy), "条，", round(os.path.getsize(OUT1) / 1024, 1), "KB")
print("派生表：", len(zattr), "条，", round(os.path.getsize(OUT2) / 1024, 1), "KB")
print("示例：2026 年 1 号 =", zy.get((2026, 1)), "；2020 年 1 号 =", zy.get((2020, 1)))
