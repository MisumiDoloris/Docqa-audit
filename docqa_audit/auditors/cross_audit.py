"""对比层：拿两个解析底座解同一份 PDF，比表头、比列数、比数据，抓单看一边看不出的错。

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
- 表头对得上但列数不同 → docling 多就拦（合并单元格或整列被吞），markitdown 多只记
- 表头对不上时不再报列数，同一个根因不报两遍
- docling 的数据里有型号、编号这类字母数字串，在整份 markitdown 输出里一个都找不到 → 警
  （这一层只查「在不在」，不判断数值对不对，改数字它抓不到）
"""

import re

from .. import model

_PAIR_FLOOR = 0.3      # 表头重合低于这个值，认作「没配上」，不硬比
_SEP_LINE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
_TABLE_LINE = re.compile(r"^\s*\|")
# 数据里的型号、编号：字母打头带数字，长度四个字符以上。纯数字太吵，不比。
# 字母部分允许只有一个字母——华为那批型号就是 S5735、S16700、AP4050 这种。
# 尾部不用 \w：Python 的 \w 认中文，型号后面紧跟汉字会被整串吞进来，
# 回原文就找不到，真型号被判成丢数据。
_DATA_TOKEN = re.compile(r"[A-Za-z]{1,}[-_]?\d[A-Za-z0-9_\-./]*")


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


def _md_block_shape(block):
    """一个 Markdown 表格块（可能只是碎片）的表头、列数、数据行数、数据文本。"""
    body = [(no, ln) for no, ln in block if not _SEP_LINE.match(ln)]
    if not body:
        return {"header": [], "cols": 0, "rows": 0, "text": ""}
    header = _cells(body[0][1])
    cols = max(len(_cells(ln)) for _no, ln in body)
    text = " ".join(" ".join(_cells(ln)) for _no, ln in body[1:])
    return {"header": header, "cols": cols, "rows": max(len(body) - 1, 0), "text": text}


def _is_data(hc):
    ne = [c for c in hc if c]
    if not ne:
        return False
    f = ne[0]
    return "支持" in f or "：" in f or ":" in f or re.match(r"^[A-Z]+[0-9]", f)


def reblock_markitdown_shapes(lines):
    """markitdown 碎片归位成逻辑表，每张表带上表头、列数、数据行数、数据文本。"""
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

    groups, seen = [], []
    for block in _table_blocks(merged):
        shape = _md_block_shape(block)
        ne = [c for c in shape["header"] if c]
        dup = any(ne == p for p in seen if p)
        # 规则二 / 三：空表头、数据行当表头、重复表头 → 续表，归前面。
        if groups and (len(ne) <= 2 or _is_data(shape["header"]) or dup):
            g = groups[-1]
            g["cols"] = max(g["cols"], shape["cols"])
            # 碎片当续表时整块都是数据行，表头已经在组里了，所以不减一。
            g["rows"] += shape["rows"] + 1
            g["text"] = (g["text"] + " " + shape["text"]).strip()
            continue
        groups.append(shape)
        seen.append(ne)
    return groups


def reblock_markitdown(lines):
    """兼容旧调用：只要表头。"""
    return [g["header"] for g in reblock_markitdown_shapes(lines)]


def _is_field_name(s):
    s = s.strip()
    return bool(s) and len(s) <= 12 and not re.search(r"\d", s)


def _same_field(a, b):
    """两个表头字段是不是同一列。

    名字长短不一是常态：docling 抄成「设备名称及规格型号」，markitdown 抄成
    「设备名称」，指的是同一列。严格相等会把这种情况报成「丢了字段 + 多出字段」，
    一次误拦两份都解析对的资料。

    但不能放太松：「CloudEngine」是「CloudEngine S16700-4」的前缀，把型号吃掉了，
    这两格不是同一列——真错正是 markitdown 把型号名丢了，认成同列就等于放过它。
    判据是前缀之外那截不含数字：含数字说明多出来的是型号、规格、尺寸这类实体值。
    """
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 3 or short not in long_:
        return False
    return not re.search(r"\d", long_[len(short):])


def _dl_table_shape(t):
    """docling 一张物理表的表头、列数、数据行数、数据文本。"""
    colh = [c for c in t["cells"] if c.get("column_header")]
    if colh:
        first = sorted((c for c in t["cells"] if c["row"][0] == 0),
                       key=lambda c: c["col"][0])
        hs = [c["text"] for c in first if c["text"].strip()]
    else:
        first = [c["text"] for c in t["cells"] if c["row"][0] == 0]
        if len(first) >= 2 and all(_is_field_name(x) for x in first):
            hs = first
        else:
            hs = []
    cols = t.get("num_cols") or max((c["col"][1] for c in t["cells"]), default=0)
    rows = t.get("num_rows") or max((c["row"][1] for c in t["cells"]), default=0)
    text = " ".join(str(c["text"]) for c in t["cells"]
                    if c["row"][0] >= 1 and str(c["text"]).strip())
    return {"header": hs, "cols": int(cols or 0), "rows": int(rows or 0), "text": text}


def reblock_docling_shapes(tables):
    """docling 归位：无表头、重复表头的表归前面，每张表带上形状。

    有 column_header 时，表头取「第一行的全部格」而不是只取标了
    column_header 的格——docling 会把左上角的 corner 格（column_header 和
    row_header 都是 false）和行标签列漏标，只取 column_header 就会丢掉它们，
    反过来把 markitdown 的正常表头误报成「多出」。
    """
    groups, seen = [], []
    for t in tables:
        shape = _dl_table_shape(t)
        hs = tuple(shape["header"])
        if (not hs or hs in seen) and groups:
            g = groups[-1]
            g["cols"] = max(g["cols"], shape["cols"])
            g["rows"] += shape["rows"]
            g["text"] = (g["text"] + " " + shape["text"]).strip()
            continue
        groups.append(shape)
        if hs:
            seen.append(hs)
    return groups


def reblock_docling(tables):
    """兼容旧调用：只要表头。"""
    return [g["header"] for g in reblock_docling_shapes(tables)]


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


def missing_data_tokens(docling_text, markitdown_text):
    """docling 数据里的型号/编号，在整份 markitdown 输出里找不到的。

    比整份输出而不是比配对上的那一张表：碎片归位差一点就误报，整份里
    找得到就说明数据没丢，只是位置不同。
    """
    md_norm = _norm(markitdown_text)
    out, seen = [], set()
    for tok in _DATA_TOKEN.findall(str(docling_text)):
        if len(tok) < 4:
            continue
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        if _norm(tok) not in md_norm:
            out.append(tok)
    return out


def audit(docling_tables, markitdown_text, source_name="对比层"):
    """两个底座的输出放一起比表头、列数、数据。

    docling_tables: scripts/export_docling_json.py 导出的 tables 列表
    markitdown_text: markitdown 解同一份 PDF 的 Markdown 全文
    """
    layer = model.LayerResult("对比层")
    md_shapes = reblock_markitdown_shapes(str(markitdown_text).splitlines())
    dl_shapes = reblock_docling_shapes(docling_tables or [])
    md_headers = [g["header"] for g in md_shapes]
    dl_headers = [g["header"] for g in dl_shapes]
    layer.summary["docling 逻辑表"] = len(dl_headers)
    layer.summary["markitdown 逻辑表"] = len(md_headers)

    if not dl_headers or not md_headers:
        missing_side = "docling" if not dl_headers else "markitdown"
        layer.status = model.INPUT_INVALID
        layer.note = f"{missing_side} 那一边没有可对比的表头"
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
    # 数据串的去处搜整份 markitdown 输出，不只是表里那几行：型号出现在正文段落里
    # 也算没丢。实测真数据里 LSH7MPUAX1C0 出现在表格外，只搜表格会报假警。
    md_all = str(markitdown_text)

    paired = 0
    cols_gap = 0
    skipped = 0
    for idx, d in enumerate(dl_headers, 1):
        if not d:
            skipped += 1
            continue
        if idx - 1 not in assigned:
            dshape = dl_shapes[idx - 1]
            layer.add(model.Finding(
                source_name,
                f"docling 逻辑表{idx}（{'、'.join(d)[:40]}）在 markitdown 那边没有对应的表",
                model.INFO,
                "一对一配对后剩下这张，可能 markitdown 整张没解出来，也可能被并进了别的碎片",
            ))
            # 整张表都没配上，表里的型号更没人查。丢整表比丢一列重，不能只记一笔就过去。
            missing = missing_data_tokens(dshape["text"], md_all)
            if missing:
                layer.add(model.Finding(
                    source_name,
                    f"逻辑表{idx} 整张在 markitdown 那边没有对应表，表里 {len(missing)} 个型号或编号"
                    "在整份输出里也找不到：" + "、".join(f"「{x}」" for x in missing[:5]),
                    model.WARN,
                    "整张表没解出来比丢一列更重。要么别用 markitdown 这份归档，要么人工把这张表补进去",
                ))
            continue
        best, score = assigned[idx - 1]
        m = md_headers[best]
        dshape = dl_shapes[idx - 1]
        mshape = md_shapes[best]
        paired += 1

        d_keys = {_norm(x): x for x in d if x}
        m_keys = {_norm(x): x for x in m if x}
        lost = [orig for k, orig in d_keys.items()
                if k not in m_keys and not any(_same_field(k, mk) for mk in m_keys)]
        extra = [orig for k, orig in m_keys.items()
                 if k not in d_keys and not any(_same_field(k, dk) for dk in d_keys)]

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

        # 列数：表头已经丢了的表不再报，同一个根因不报两遍。
        if not lost and dshape["cols"] and mshape["cols"]:
            if dshape["cols"] > mshape["cols"]:
                cols_gap += 1
                layer.add(model.Finding(
                    source_name,
                    f"逻辑表{idx}：docling 是 {dshape['cols']} 列，markitdown 只有 {mshape['cols']} 列",
                    model.BLOCKER,
                    "表头名字对得上但列数对不上，通常是合并单元格或整列被吞。"
                    "按定死口径，列数不一致直接拦",
                ))
            elif mshape["cols"] > dshape["cols"]:
                layer.add(model.Finding(
                    source_name,
                    f"逻辑表{idx}：markitdown 是 {mshape['cols']} 列，docling 只有 {dshape['cols']} 列",
                    model.INFO,
                    "markitdown 多出来的列可能是把行标签拆开算了，人工看一眼这张表",
                ))

        # 数据行数：只记。两个底座合并碎片的策略不同，行数本来就容易差。
        # docling 的 rows 含表头行，所以要减一才跟 markitdown 比。
        d_rows = max(dshape["rows"] - 1, 0)
        if d_rows > mshape["rows"]:
            layer.add(model.Finding(
                source_name,
                f"逻辑表{idx}：docling 数据 {d_rows} 行，markitdown 只有 {mshape['rows']} 行",
                model.INFO,
                "差几行可能只是碎片合并方式不同。看下面有没有具体型号丢了，那才是真丢",
            ))

        # 数据内容：型号、编号这类字母数字串，在整份 markitdown 输出里一个都找不到。
        missing = missing_data_tokens(dshape["text"], md_all)
        if missing:
            layer.add(model.Finding(
                source_name,
                f"逻辑表{idx}：数据里有 {len(missing)} 个型号或编号在 markitdown 输出里找不到："
                + "、".join(f"「{x}」" for x in missing[:5]),
                model.WARN,
                "这些串在 docling 的数据行里出现过，整份 markitdown 输出里都没有。"
                "可能是整行被丢，也可能是写法差（空格、单位符号）。人工核对一下",
            ))

    if skipped:
        layer.status = model.PARTIAL
        layer.note = f"{skipped} 张表的表头没认出来，没有比过"
        layer.add(model.Finding(
            source_name,
            f"{skipped} 张 docling 表的表头没认出来，这几张没有参与对比",
            model.WARN,
            "表头认不出来就没法比字段和列数，这几张等于没查。对照原 PDF 看表头是不是被合并成一行长名字了",
        ))

    layer.summary["配上"] = paired
    layer.summary["列数不一致"] = cols_gap
    return layer
