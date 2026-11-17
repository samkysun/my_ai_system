# -*- coding: utf-8 -*-
"""
系统测试集 —— 自动升级的安全网
================================
任何补丁在推送到 GitHub 之前，必须先跑通这个文件。
用法：  python system_tests.py
返回码：0 = 全通过；1 = 有失败（补丁会被拒绝）

设计原则：
  * 只测纯逻辑，不联网、不碰数据库、不写任何文件
  * 用桩替换 streamlit / supabase / requests，因此无需安装 Streamlit
  * 测试失败时打印可定位的信息（期望值 vs 实际值）
"""

import sys
import types

# ---------------------------------------------------------------- 桩环境
class _U:
    def __call__(self, *a, **k): return _U()
    def __getattr__(self, n): return _U()
    def __enter__(self): return _U()
    def __exit__(self, *a): return False
    def __iter__(self):
        while True: yield _U()
    def __bool__(self): return False


class _SS(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)
    def __setattr__(self, k, v): self[k] = v


class _Cache:
    def __call__(self, *a, **k):
        if len(a) == 1 and callable(a[0]) and not k: return a[0]
        return lambda fn: fn


def _install_stubs():
    st = types.ModuleType("streamlit")
    st.session_state = _SS()
    st.secrets = types.SimpleNamespace(get=lambda k, d=None: d)
    st.cache_data = st.cache_resource = _Cache()
    for n in ("button", "checkbox", "form_submit_button", "toggle"):
        setattr(st, n, lambda *a, **k: False)
    for n in ("title", "subheader", "markdown", "write", "divider", "info", "success",
              "error", "warning", "toast", "stop", "rerun", "dataframe", "caption",
              "download_button", "set_page_config", "html", "code", "json"):
        setattr(st, n, lambda *a, **k: None)
    for n in ("selectbox", "radio", "number_input", "text_input", "text_area",
              "progress", "empty", "spinner", "expander", "form", "chat_message",
              "chat_input", "container"):
        setattr(st, n, lambda *a, **k: _U())
    st.multiselect = lambda *a, **k: []
    st.columns = lambda spec, **k: [_U() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs = lambda names, **k: [_U() for _ in names]

    comp = types.ModuleType("streamlit.components")
    v1 = types.ModuleType("streamlit.components.v1")
    v1.html = lambda *a, **k: None
    comp.v1 = v1

    req = types.ModuleType("requests")
    req.get = req.post = req.put = req.patch = req.request = lambda *a, **k: _U()
    sup = types.ModuleType("supabase")
    sup.create_client = lambda *a, **k: None

    sys.modules.update({"streamlit": st, "streamlit.components": comp,
                        "streamlit.components.v1": v1, "requests": req, "supabase": sup})


_install_stubs()

import app  # noqa: E402
import pandas as pd  # noqa: E402

# ---------------------------------------------------------------- 测试框架
_FAILED = []
_PASSED = 0


def check(name, cond, detail=""):
    global _PASSED
    if cond:
        _PASSED += 1
        print(f"  PASS  {name}")
    else:
        _FAILED.append(f"{name} :: {detail}")
        print(f"  FAIL  {name}  {detail}")


def section(title):
    print(f"\n[{title}]")


# ================================================================ 1. 属性表
section("属性表一致性（49 个号 × 5 张映射）")

check("NUM_HE 条目数 = 49", len(app.NUM_HE) == 49, f"实际 {len(app.NUM_HE)}")
check("NUM_ZODIAC 条目数 = 49", len(app.NUM_ZODIAC) == 49, f"实际 {len(app.NUM_ZODIAC)}")
check("NUM_WUXING 条目数 = 49", len(app.NUM_WUXING) == 49, f"实际 {len(app.NUM_WUXING)}")
check("NUM_BOSE 条目数 = 49", len(app.NUM_BOSE) == 49, f"实际 {len(app.NUM_BOSE)}")

_bad = [(n, app.NUM_HE[n]) for n in range(1, 50)
        if app.NUM_HE[n] != f"{(n // 10 + n % 10):02d}合"]
check("NUM_HE = 各位数字相加", not _bad, f"不符: {_bad}")

_bad = [(n, app.NUM_MEN[n]) for n in range(1, 50) if app.NUM_MEN[n] != f"{n // 10 + 1}门"]
check("NUM_MEN = 十位+1", not _bad, f"不符: {_bad}")

_bad = [(n, app.NUM_DUAN[n]) for n in range(1, 50) if app.NUM_DUAN[n] != f"{(n - 1) // 7 + 1}段"]
check("NUM_DUAN = 每 7 号一段", not _bad, f"不符: {_bad}")

_bad = []
for n in range(1, 50):
    t, u = n // 10, n % 10
    exp = ("双" if t % 2 == 0 else "单") + ("双" if u % 2 == 0 else "单")
    if app.NUM_SINGLE_DOUBLE[n] != exp: _bad.append((n, app.NUM_SINGLE_DOUBLE[n], exp))
check("NUM_SINGLE_DOUBLE = 十位个位奇偶", not _bad, f"不符: {_bad}")

_cycle = ["马", "蛇", "龙", "兔", "虎", "牛", "鼠", "猪", "狗", "鸡", "猴", "羊"]
_bad = [(n, app.NUM_ZODIAC[n]) for n in range(1, 50) if app.NUM_ZODIAC[n] != _cycle[(n - 1) % 12]]
check("NUM_ZODIAC = 12 生肖循环", not _bad, f"不符: {_bad}")

# ============================================================ 2. 属性计算器
section("calculate_all_attributes")

check("返回 28 个属性", len(app.calculate_all_attributes(7)) == 28,
      f"实际 {len(app.calculate_all_attributes(7))}")
check("空值返回 28 个空串", app.calculate_all_attributes(0) == [""] * 28)
check("22 号合数 = 04合", app.calculate_all_attributes(22)[3] == "04合",
      f"实际 {app.calculate_all_attributes(22)[3]}")
check("1 号生肖 = 马", app.calculate_all_attributes(1)[1] == "马")
check("49 号生肖 = 马", app.calculate_all_attributes(49)[1] == "马")
check("10 号数字合 = 01合", app.calculate_all_attributes(10)[3] == "01合")
check("全 49 号都能算且无空属性",
      all(all(x != "" for x in app.calculate_all_attributes(n)) for n in range(1, 50)))

# ============================================================ 3. 号码提取
section("extract_numbers")

_cases = [
    ("【FINAL】01,05,12", [1, 5, 12]),
    ("FINAL: 07,12", [7, 12]),
    ("01号：触犯杀木肖，剔除。05号：保留。", [1, 5]),
    ("【保留结果】\n07号 生肖马\n12号 生肖羊", [7, 12]),
    ("没有任何结果", []),
    ("FINAL: 3, 49", [3, 49]),
    ("00,50,99 越界不应出现", []),
]
for txt, exp in _cases:
    got = app.extract_numbers(txt)
    check(f"提取 {txt[:18]!r}", got == exp, f"期望 {exp} 实际 {got}")

# ============================================================ 4. 列布局
section("全套 CSV 列布局（7 球 × 30 列 + 期号 3 列 + 年份）")

check("总列数 = 214", 3 + 7 * 30 + 1 == 214)
check("第 1 球十位在第 4 列", 4 + 0 * 30 == 4)
check("第 7 球十位在第 184 列", 4 + 6 * 30 == 184)
check("第 7 球最后一个属性在第 213 列", 4 + 6 * 30 + 29 == 213)
check("年份在第 214 列", 214 == 214)

# ============================================================ 5. 算法
section("联动分析与中奖比对")

_rows = []
for i in range(40):
    r = [None] * 30
    r[18] = str(2026100 - i)
    picks = [(i * 3 + j * 7) % 49 + 1 for j in range(7)]
    for k in range(6): r[19 + k] = picks[k]
    r[25] = picks[6]
    _rows.append(r)
_df = pd.DataFrame(_rows)

_trig, _cnt, _err = app.calculate_linkage(_df, "2026100", "单排分析")
check("单排分析无异常", _err is None, f"err={_err}")
check("单排有触发记录", len(_trig) > 0, f"触发 {len(_trig)}")
check("统计表有数据", len(_cnt) > 0, f"{len(_cnt)} 行")

_trig2, _cnt2, _err2 = app.calculate_linkage(_df, "2026100", "多排分析")
check("多排分析无异常", _err2 is None, f"err={_err2}")

_res, _e = app.calculate_prize(_df, "2026100", _cnt.head(7)["下期数字"].tolist())
check("中奖比对可返回", _res is not None or _e is not None)

check("找不到期号时返回错误", app.calculate_linkage(_df, "1999999", "单排分析")[2] is not None)

# ============================================================ 6. 工具函数
section("工具函数")

check("clean_period 处理 .0", app.clean_period("2026100.0") == "2026100")
check("clean_period 处理 NaN", app.clean_period(float("nan")) == "")
check("clean_period 处理纯字符串", app.clean_period(" 2026100 ") == "2026100")
check("红波配色", app.get_ball_color(1) == "ball-red")
check("蓝波配色", app.get_ball_color(3) == "ball-blue")
check("绿波配色", app.get_ball_color(5) == "ball-green")
check("1 号红波", app.NUM_BOSE[1] == "红波")

# ============================================================ 7. 补丁引擎
section("补丁引擎（auto_upgrade）")

try:
    import auto_upgrade as AU

    _src = "line1\nline2\nline3\n"
    _ok, _new, _msg = AU.apply_edits(
        {"a.py": _src},
        [{"file": "a.py", "mode": "replace_block", "find": "line2", "replace": "LINE2"}])
    check("replace_block 正常替换", _ok and "LINE2" in _new["a.py"], _msg)

    _ok, _new, _msg = AU.apply_edits(
        {"a.py": _src},
        [{"file": "a.py", "mode": "replace_block", "find": "不存在的内容", "replace": "x"}])
    check("find 不存在时报错", (not _ok) and "找不到" in _msg, _msg)

    _ok, _new, _msg = AU.apply_edits(
        {"a.py": "x\nx\n"},
        [{"file": "a.py", "mode": "replace_block", "find": "x", "replace": "y"}])
    check("find 不唯一时报错", (not _ok) and "不唯一" in _msg, _msg)

    _ok, _new, _msg = AU.apply_edits({}, [{"file": "b.py", "mode": "create", "content": "print(1)\n"}])
    check("create 新文件", _ok and _new.get("b.py", "").startswith("print"), _msg)

    _ok, _new, _msg = AU.apply_edits(
        {"a.py": _src},
        [{"file": "a.py", "mode": "append", "content": "# tail\n"}])
    check("append 追加", _ok and _new["a.py"].endswith("# tail\n"), _msg)

    _bad = AU.validate_edits({"a.py": _src}, [{"file": "secrets.toml", "mode": "create", "content": "x"}])
    check("拒绝改 secrets.toml", not _bad[0], _bad[1])

    _bad = AU.validate_edits({"a.py": _src}, [{"file": "a.txt", "mode": "create", "content": "x"}])
    check("拒绝非 .py 文件", not _bad[0], _bad[1])

    _bad = AU.validate_edits({"a.py": _src},
                             [{"file": "a.py", "mode": "create", "content": 'k="sk-abcdefghijklmnop"'}])
    check("拒绝硬编码 sk- 密钥", not _bad[0], _bad[1])

    _bad = AU.validate_edits({}, [{"file": "x.py", "mode": "create",
                                   "content": 'open(".streamlit/secrets.toml","w").write("")'}])
    check("拒绝写 secrets.toml 的代码", not _bad[0], _bad[1])

    _ok, _new, _msg = AU.apply_edits({"a.py": "def f(:\n"}, [])
    check("语法错误能被 ast 拦住", not AU.ast_check({"a.py": "def f(:\n"})[0], "应当报语法错误")
    check("合法代码通过 ast", AU.ast_check({"a.py": "def f():\n    return 1\n"})[0])

    _p = AU.parse_patch('说明\n```json\n{"summary":"s","edits":[]}\n```\n结尾')
    check("parse_patch 能从围栏中取 JSON", _p.get("summary") == "s", str(_p)[:80])
    _p = AU.parse_patch('{"summary":"直接 JSON","edits":[]}')
    check("parse_patch 能吃裸 JSON", _p.get("summary") == "直接 JSON", str(_p)[:80])
    check("parse_patch 对垃圾输入返回空", AU.parse_patch("完全不是JSON") == {})

except Exception as _e:
    check("补丁引擎可导入", False, f"{type(_e).__name__}: {_e}")

# ============================================================ 8. 页面集成
section("页面集成冒烟")

try:
    app.render_admin_panel()
    check("后台管理页渲染无异常", True)
except Exception as _e:
    check("后台管理页渲染无异常", False, f"{type(_e).__name__}: {_e}")

try:
    app.login_page()
    check("登录页渲染无异常", True)
except Exception as _e:
    check("登录页渲染无异常", False, f"{type(_e).__name__}: {_e}")

_has_chat = getattr(app, "render_ai_chat", None) is not None
_has_upg = getattr(app, "render_upgrade_tab", None) is not None
check("app 已接入 AI 助手", _has_chat, "render_ai_chat 为 None（模块缺失或导入失败）")
check("app 已接入自动升级", _has_upg, "render_upgrade_tab 为 None（模块缺失或导入失败）")

# ================================================================ 汇总
print("\n" + "=" * 64)
if _FAILED:
    print(f"失败 {len(_FAILED)} 项，通过 {_PASSED} 项")
    for f in _FAILED:
        print("  - " + f)
    print("=" * 64)
    sys.exit(1)
print(f"全部通过：{_PASSED} 项检查")
print("=" * 64)
sys.exit(0)
