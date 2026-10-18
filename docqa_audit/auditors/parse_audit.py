"""第一层：解析结果的验收。

输入是解析器（Docling / MinerU / Marker 之类）吐出来的 Markdown，不是 PDF 本身。
所以这一层不绑任何解析器，换工具不用改代码。

查的是解析阶段最常悄悄错的地方：
- 一张表里行列数不一致（合并单元格丢了、某行被切断）
- 表头有空列（列被拆错或者标题被当成数据）
- 整列空（解析器把内容漏进了别处）
- 行内空单元格比例过高（表格结构没认出来，退化成纯文本排布）
"""

import re

from .. import model

_TABLE_LINE = re.compile(r"^\s*\|")
_SEP_LINE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
_NUM = re.compile(r"\d+")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_blocks(lines):
    """把连续的 '|' 开头的行聚成一块，返回 [(起始行号, [行, ...]), ...]"""
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


def audit(text, source_name="parsed.md"):
    layer = model.LayerResult("解析层")
    lines = text.splitlines()
    blocks = _table_blocks(lines)

    if not blocks:
        layer.summary["表格数"] = 0
        layer.add(model.Finding(
            source_name, "没有识别到任何 Markdown 表格",
            model.WARN,
            "如果原文里本来有表，说明解析器把表格退化成纯文本了，这一层要人眼看一遍",
        ))
        return layer

    empty_ratio_limit = 0.4
    total_rows = 0

    for idx, block in enumerate(blocks, 1):
        start_no = block[0][0]
        rows = [(no, ln) for no, ln in block if not _SEP_LINE.match(ln)]
        if not rows:
            continue
        total_rows += len(rows)
        where = f"表{idx}（第{start_no}行起，{len(rows)}行）"

        widths = {no: len(_cells(ln)) for no, ln in rows}
        distinct = sorted(set(widths.values()))
        if len(distinct) > 1:
            bad = [no for no, w in widths.items() if w != max(distinct, key=list(widths.values()).count)]
            layer.add(model.Finding(
                where, f"列数不一致，出现 {distinct}，异常行：第 {', '.join(map(str, bad[:5]))} 行",
                model.BLOCKER,
                "多半是合并单元格丢了或某行被切断，这张表必须人工核对后才能用",
            ))

        header = _cells(rows[0][1])
        blank_header = [i + 1 for i, c in enumerate(header) if not c]
        if blank_header:
            layer.add(model.Finding(
                where, f"表头第 {', '.join(map(str, blank_header))} 列是空的",
                model.WARN,
                "空表头列后面填的东西对不上名，检索时也检索不到，建议解析器换参数重跑这一页",
            ))

        body = [_cells(ln) for _, ln in rows[1:]]
        if body:
            ncol = len(header)
            for col in range(ncol):
                values = [r[col] for r in body if col < len(r)]
                if values and all(not v for v in values):
                    layer.add(model.Finding(
                        where, f"第 {col + 1} 列整列为空（{len(values)} 行）",
                        model.WARN,
                        "这一列的内容可能被解析到别处了，检索时这块信息会缺",
                    ))
            empties = sum(1 for r in body for c in r if not c)
            cells = sum(len(r) for r in body)
            if cells and empties / cells > empty_ratio_limit:
                layer.add(model.Finding(
                    where, f"空格子占 {empties}/{cells}（{empties / cells:.0%}）",
                    model.WARN,
                    "结构可能没认出来，表格退化成按位置摆的字了，看原文对比一眼",
                ))

            # 以下三条是跑真实解析器输出才补上的。列数一样不代表内容对得上，
            # 表头被合成一格、行被切断、两列粘成一格，这些错列数检查一条都抓不到。
            merged_header = [h for h in header if re.search(r"\S\s+\S", h)]
            if merged_header:
                layer.add(model.Finding(
                    where, "表头疑似被合并成一格：" + "、".join(f"「{h}」" for h in merged_header[:3]),
                    model.WARN,
                    "表头列数比真实列数少，后面的数据会整体错位，检索时按列名找不到东西",
                ))

            seq = [r[0] for r in body if r]
            numeric = sum(1 for v in seq if _NUM.fullmatch(v))
            if len(seq) >= 3 and 0 < numeric < len(seq):
                bad_rows = [i + 2 for i, v in enumerate(seq) if v and not _NUM.fullmatch(v)]
                layer.add(model.Finding(
                    where, f"首列序号断行，第 {', '.join(map(str, bad_rows[:5]))} 行的首列不是序号："
                           + "、".join(f"「{v}」" for v in seq if v and not _NUM.fullmatch(v))[:60],
                    model.BLOCKER,
                    "一行被切成两行，下半截跑到下一行去了，这张表必须人看着重新对齐",
                ))

            glued = []
            for col in range(max(len(r) for r in body) if body else 0):
                lens = sorted(len(r[col]) for r in body if col < len(r) and r[col])
                if len(lens) < 2:
                    continue
                mid = lens[len(lens) // 2]
                if mid and lens[-1] > max(2.5 * mid, mid + 8):
                    glued.append(col + 1)
            if glued:
                layer.add(model.Finding(
                    where, f"第 {', '.join(map(str, glued))} 列出现长度异常的格子，疑似两列粘成一格",
                    model.WARN,
                    "粘住的格子里混着两个字段，取值时会取错，看一眼原图对一下",
                ))

    layer.summary["表格数"] = len(blocks)
    layer.summary["数据行"] = total_rows
    return layer
