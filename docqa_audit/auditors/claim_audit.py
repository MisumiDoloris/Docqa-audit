"""第三层：生成内容的回源校验。

模型会编。规则不会。所以这一层不做语义判断，只做一件事：
把生成文本里的数字、编号、日期挑出来，逐个回原文找锚点，找不到就标出来。

这一段是从「招呼语防编造」那套机械校验锁里抽出来的，去掉业务、换成通用写法。

三类东西的危险程度不一样：
- 年限（N 年）最危险，凭空多一年就是造假级别的问题，直接拦
- 编号张冠李戴是最典型的幻觉，直接拦
- 数字要看，但单位写法不同也会误报，所以降一档，让人眼过

锚定规则（这一层最容易写错的两处，都已经踩过）：
1. 数字必须按边界匹配，还要带上单位。"5 台" 不能在 "550mm" 或 "3.5m3" 里找到锚点。
2. 做边界匹配的那份原文不能把空格删掉。删了空格，"1001" 和 "1台" 会粘成 "10011台"，
   边界就没了，本来对得上的数会被判成编造。所以这里维护两份原文：
   去空格的用来比编号与日期，留空格的用来比数字。
"""

import re

from .. import model

_DATE = re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?")
_CODE = re.compile(r"[A-Za-z]{1,6}[-_]?\d[\w\-./]{2,}")
_CODE_DIGIT_FIRST = re.compile(r"\d{2,}-[A-Za-z0-9]{2,}-?\d{2,}")
_NUM_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*([^\d\s]{0,3})")
_YEAR = re.compile(r"(\d+)\s*年(?:以上|多)?(?:经验|经历)?")

_UNITS = ("台", "个", "套", "件", "根", "米", "元", "万元", "%", "mm", "km", "kg", "m2", "m3",
          "mpa", "mω", "m", "h", "t", "吨", "年", "天", "页", "份", "箱", "组", "层", "次")

_FULLWIDTH = str.maketrans("０１２３４５６７８９．，：", "0123456789.,:")


def norm_compact(s):
    """去空格，用来比编号和日期这类整串。"""
    return re.sub(r"\s+", "", s.translate(_FULLWIDTH)).lower()


def norm_spaced(s):
    """留单个空格，用来给数字做边界匹配。"""
    return re.sub(r"\s+", " ", s.translate(_FULLWIDTH)).strip().lower()


def _unit_of(tail):
    t = re.sub(r"\s+", "", tail).lower()
    for u in sorted(_UNITS, key=len, reverse=True):
        if t.startswith(u):
            return u
    return ""


def _has_anchor(src_compact, src_spaced, key, unit):
    if not unit:
        if key in src_compact:
            return True
        # 没单位的数字也要按边界找一次，避免 "5" 命中 "550"
        return bool(re.search(r"(?<![\d.])" + re.escape(key) + r"(?![\d.])", src_spaced))
    pat = r"(?<![\d.])" + re.escape(key) + r"(?![\d.])"
    for m in re.finditer(pat, src_spaced):
        tail = src_spaced[m.end():m.end() + 4].replace(" ", "")
        if unit in tail:
            return True
    return False


def extract(text):
    """返回 [(类型, 原文片段, 关键词, 单位)]

    先把日期和编号从文本里挖掉，再从剩下的部分找数字，
    否则编号里的数字会被当成独立的数重复检查一遍，报告里全是噪声。
    """
    claims = []
    masked = text
    for m in _DATE.finditer(text):
        claims.append(("日期", m.group(0), norm_compact(m.group(0)), ""))
        masked = masked.replace(m.group(0), " " * len(m.group(0)))
    for pat in (_CODE, _CODE_DIGIT_FIRST):
        for m in pat.finditer(masked):
            claims.append(("编号", m.group(0), norm_compact(m.group(0)), ""))
            masked = masked.replace(m.group(0), " " * len(m.group(0)))

    for m in _YEAR.finditer(masked):
        claims.append(("年限", m.group(0), m.group(1), "年"))

    for m in _NUM_UNIT.finditer(masked):
        num, tail = m.group(1), m.group(2)
        unit = _unit_of(tail)
        # 没有单位的裸数字只收两位以上的，避免把序号、零碎数字全报出来
        if not unit and len(num.split(".")[0]) < 2:
            continue
        claims.append(("数字", m.group(0).strip(), num, unit))

    uniq, seen = [], set()
    for c in sorted(claims, key=lambda c: -len(c[1])):
        k = (c[0], c[2], c[3])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def audit(answer_text, source_text, source_name="原文"):
    layer = model.LayerResult("生成层")
    src_c, src_s = norm_compact(source_text), norm_spaced(source_text)
    claims = extract(answer_text)

    missing = {"年限": [], "日期": [], "编号": [], "数字": []}
    for kind, raw, key, unit in claims:
        if _has_anchor(src_c, src_s, key, unit):
            continue
        missing[kind].append(raw)

    layer.summary["检出"] = len(claims)
    layer.summary["回源成功"] = len(claims) - sum(len(v) for v in missing.values())

    if missing["年限"]:
        layer.add(model.Finding(
            "年限表述", "原文里找不到：" + "、".join(missing["年限"][:5]),
            model.BLOCKER,
            "年限最容易被追问也最容易被查穿，要么删掉，要么按原文核准再写",
        ))
    if missing["日期"]:
        layer.add(model.Finding(
            "日期回源", "原文里找不到：" + "、".join(missing["日期"][:5]),
            model.BLOCKER,
            "日期对不上会连带结论一起错，回原文核一遍",
        ))
    if missing["编号"]:
        layer.add(model.Finding(
            "编号回源", "原文里找不到：" + "、".join(missing["编号"][:8]),
            model.BLOCKER,
            "编号张冠李戴是最典型的幻觉，需要逐个人工比对",
        ))
    if missing["数字"]:
        layer.add(model.Finding(
            "数字回源 🔴", "原文里找不到：" + "、".join(missing["数字"][:8]),
            model.WARN,
            "标红放行：不拦整段，但这几处必须有人看过再发出去；单位写法不同也会误报，别一概当编造",
        ))

    if not layer.findings:
        layer.add(model.Finding(source_name, "全部数字、编号、日期都能回原文找到锚点", model.INFO, ""))
    return layer
