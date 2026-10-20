"""对比层：拿两个解析底座解同一份 PDF，比表头，抓单看一边看不出的错。

为什么要这一层：有些错在单个底座的输出里长得跟「正常排版」一样。
markitdown 把第二层表头（型号名 S16700-4/8）当成数据行，它自己的
Markdown 看不出异常；docling 把型号名认成表头。两边一对比，谁丢了
列就露出来了。2026-10-19 在华为 17 页彩页上第一次抓到。

两条定死的做法：
1. 先归位再对比。两个底座都会把一张逻辑表碎成好几块，不归位直接比
   等于拿碎片对碎片。
2. 表级比，不做文档级去重比。文档级去重会把局部丢失抹平——型号名在
   硬件规格表里解析对了，去重后差集为 0，业务特性表那处的丢失就没了。

判据：
- docling 有、markitdown 没有的表头字段 → 拦（那几列在 markitdown 的输出里不存在）
- markitdown 有、docling 没有的 → 只记（可能是 docling 归位漏了，也可能是口径差）
- 两边逻辑表张数不同 → 只记（碎片合并策略不同，不是错）
"""

import re

from .. import model

_PAIR_FLOOR = 0.3      # 表头重合低于这个值，认作「没配上」，不硬比
_SEP_LINE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
_TABLE_LINE = re.compile(r"^\s*\|")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_blocks(lines):
    """把连续的 '|' 开头的行聚成块。返回 [(起始行号, 行文本), ...] 的列表。"""
    blocks, cur = [], []
    for no, line in enumerate(lines, 1):
        if _TABLE_LINE.match(line):
            cur.append((no, line))
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def reblock_markitdown(lines):
    """markitdown 碎片归位成逻辑表，返回每张逻辑表的表头（非空 cell）。"""
    is_table = [ln.strip().startswith("|") for ln in lines]

    # 规则一：续行切断。夹在两个表格行中间的普通文本，拼回上一行。
    merged = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s and not s.startswith("|") and i > 0 and is_table[i - 1] and i + 1 < len(lines) and is_table[i + 1]:
            if merged:
                merged[-1] = merged[-1].rstrip() + " " + s
        else:
            merged.append(lines[i])
        i += 1

    def header(block):
        rows = [(no, ln) for no, ln in block if not _SEP_LINE.match(ln)]
        if not rows:
            return []
        return _cells(rows[0][1])

    def is_data(hc):
        ne = [c for c in hc if c]
        if not ne:
            return False
        f = ne[0]
        return "支持" in f or "：" in f or ":" in f or re.match(r"^[A-Z]+[0-9]", f)

    groups, seen = [], []
    for block in _table_blocks(merged):
        hc = header(block)
        ne = [c for c in hc if c]
        dup = any(ne == p for p in seen if p)
        # 规则二 / 三：空表头、数据行当表头、重复表头 → 续表，归前面。
        if groups and (len(ne) <= 2 or is_data(hc) or dup):
            continue
        groups.append(ne)
        seen.append(ne)
    return groups


def _is_field_name(s):
    s = s.strip()
    return bool(s) and len(s) <= 6 and not re.search(r"\d", s)


def reblock_docling(tables):
    """docling 归位：无表头、重复表头的表归前面，返回每张逻辑表的表头。"""
    groups, seen = [], []
    for t in tables:
        hs = tuple(c["text"] for c in t["cells"] if c["column_header"])
        if not hs:
            first = [c["text"] for c in t["cells"] if c["row"][0] == 0]
            if len(first) >= 2 and all(_is_field_name(x) for x in first):
                hs = tuple(first)
        if not hs and groups:
            continue
        if hs and hs in seen:
            continue
        groups.append(list(hs))
        if hs:
            seen.append(hs)
    return groups


def _norm(s):
    return re.sub(r"\s+", "", str(s)).lower()


def overlap(a, b):
    sa, sb = {_norm(x) for x in a if x}, {_norm(x) for x in b if x}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def pair_tables(dl_headers, md_headers, floor=_PAIR_FLOOR):
    """一对一配对：所有组合按重合度降序贪心分配，每张表只用一次。

    返回 {docling 下标: (markitdown 下标, 重合度)}。
    不这么配会出假拦：docling 多出来的那张表和 markitdown 某张只重合
    三分之一，逐张取最近邻就把它硬塞过去，报出根本不存在的丢列。
    """
    scored = []
    for i, d in enumerate(dl_headers):
        if not d:
            continue
        for j, m in enumerate(md_headers):
            scored.append((overlap(d, m), i, j))
    scored.sort(reverse=True)

    assigned, used_md = {}, set()
    for score, i, j in scored:
        if i in assigned or j in used_md:
            continue
        if score < floor:
            break
        assigned[i] = (j, score)
        used_md.add(j)
    return assigned


def audit(docling_tables, markitdown_text, source_name="对比层"):
    """两个底座的输出放一起比表头。

    docling_tables: scripts/export_docling_json.py 导出的 tables 列表
    markitdown_text: markitdown 解同一份 PDF 的 Markdown 全文
    """
    layer = model.LayerResult("对比层")
    md_headers = reblock_markitdown(str(markitdown_text).splitlines())
    dl_headers = reblock_docling(docling_tables or [])
    layer.summary["docling 逻辑表"] = len(dl_headers)
    layer.summary["markitdown 逻辑表"] = len(md_headers)

    if not dl_headers or not md_headers:
        layer.add(model.Finding(
            source_name, "有一边的输出里没有可对比的表头",
            model.WARN,
            "两个底座都要有输出才能比。缺的那一边要么没跑，要么整份文档都没解出表",
        ))
        return layer

    if len(dl_headers) != len(md_headers):
        layer.add(model.Finding(
            source_name,
            f"逻辑表张数不同：docling {len(dl_headers)} 张，markitdown {len(md_headers)} 张",
            model.INFO,
            "两个底座合并碎片的策略不同，张数不一样本身不是错，看下面逐张的字段差异",
        ))

    # 配对必须一对一，理由见 pair_tables。
    assigned = pair_tables(dl_headers, md_headers)

    paired = 0
    for idx, d in enumerate(dl_headers, 1):
        if not d:
            continue
        if idx - 1 not in assigned:
            layer.add(model.Finding(
                source_name,
                f"docling 逻辑表{idx}（{'、'.join(d)[:40]}）在 markitdown 那边没有对应的表",
                model.INFO,
                "一对一配对后剩下这张，可能 markitdown 整张没解出来，也可能被并进了别的碎片",
            ))
            continue
        best, score = assigned[idx - 1]
        m = md_headers[best]
        paired += 1

        d_keys = {_norm(x): x for x in d if x}
        m_keys = {_norm(x): x for x in m if x}
        lost = [orig for k, orig in d_keys.items() if k not in m_keys]
        extra = [orig for k, orig in m_keys.items() if k not in d_keys]

        if lost:
            layer.add(model.Finding(
                source_name,
                f"逻辑表{idx}：markitdown 少了 {len(lost)} 个表头字段："
                + "、".join(f"「{x}」" for x in lost[:6]),
                model.BLOCKER,
                "同一份 PDF 里 docling 认出了这些列、markitdown 没有。用 markitdown 那份归档会丢列",
            ))
        if extra:
            layer.add(model.Finding(
                source_name,
                f"逻辑表{idx}：markitdown 多出 {len(extra)} 个表头字段："
                + "、".join(f"「{x}」" for x in extra[:6]),
                model.INFO,
                "可能是 docling 归位时把表头漏掉了，也可能是两个底座对表头行的判断口径不同，人工看一眼",
            ))

    layer.summary["配上"] = paired
    return layer
