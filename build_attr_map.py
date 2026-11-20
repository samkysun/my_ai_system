# -*- coding: utf-8 -*-
"""生成 _attr_map.csv：1~49 号对应的所有属性（取最近年份）"""
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\666\共享\系统升级前备份\_data_mirror\升序全套.csv"
OUT = r"D:\666\共享\网站本地运行\_attr_map.csv"

# 1-based 列号（表头顺序）
COLS = {                     # 块内 0 基偏移（块起点 = 3 + 30*(球-1)）
    "数字五行": 2,    "生肖": 3,      "尾数": 4,    "数字合": 5,
    "门数": 6,        "段数": 7,      "单双组合": 8,
    "头数": 11,       "单双": 12,     "波单双": 13,
    "生肖五行": 14,   "颜色肖": 15,   "四宝": 16,
    "物象": 17,       "波色": 18,     "阴阳": 19,
    "家野": 20,       "天地": 21,     "阴阳天地": 22,
    "吉凶": 23,       "男女": 24,     "方位": 25,
    "3模": 26,        "尾五行": 27,   "福禄寿": 28,
    "大小肖": 29,
}

rows = list(csv.reader(open(SRC, encoding="utf-8-sig", errors="replace")))
print("源行数:", len(rows))

best = {}      # num -> (period, attrs)
for r in rows[2:]:
    if len(r) < 214:
        continue
    period = f"{r[213]}{r[0]}{r[1]}{r[2]}".strip()
    if not period:
        continue
    for b in range(1, 8):
        base = 3 + (b - 1) * 30
        try:
            num = int((r[base].strip() + r[base + 1].strip()) or 0)
        except Exception:
            continue
        if not (1 <= num <= 49):
            continue
        attrs = {}
        for k, c1 in COLS.items():
            idx = base + c1
            attrs[k] = r[idx].strip() if idx < len(r) else ""
        old = best.get(num)
        if old is None or period > old[0]:
            best[num] = (period, attrs)

print("覆盖号码数:", len(best))
missing = [n for n in range(1, 50) if n not in best]
if missing:
    print("缺失号码:", missing)

fields = ["号码"] + list(COLS.keys())
with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(fields)
    for n in range(1, 50):
        if n in best:
            a = best[n][1]
            w.writerow([n] + [a[k] for k in COLS])
        else:
            w.writerow([n] + [""] * len(COLS))

print("已生成", OUT, round(os.path.getsize(OUT) / 1024, 1), "KB")
for n in (1, 7, 12, 25, 49):
    if n in best:
        print("  ", n, {k: best[n][1][k] for k in ("zodiac", "tail", "he", "wx", "men", "duan")})
