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
                model.INFO,
                "这列表头是空的，可能是原文档排版留白，也可能是解析丢了内容，对照原 PDF 或另一底座确认",
            ))

        body = [_cells(ln) for _, ln in rows[1:]]
        if body:
            ncol = len(header)
            for col in range(ncol):
                values = [r[col] for r in body if col < len(r)]
                if values and all(not v for v in values):
                    layer.add(model.Finding(
                        where, f"第 {col + 1} 列整列为空（{len(values)} 行）",
                        model.INFO,
                        "这一列全空，可能是原文档分隔列或合并单元格，也可能是解析丢了内容，对照确认",
                    ))
            empties = sum(1 for r in body for c in r if not c)
            cells = sum(len(r) for r in body)
            if cells and empties / cells > empty_ratio_limit:
                layer.add(model.Finding(
                    where, f"空格子占 {empties}/{cells}（{empties / cells:.0%}）",
                    model.INFO,
                    "这张表空格偏多，可能是原文档本就稀疏，也可能表格结构没认出来，对照原 PDF 看一眼",
                ))

            # 这一条是跑真实解析器输出才补上的。列数一样不代表内容对得上，
            # 一行被切成两行，列数检查一条都抓不到。两列粘成一格则由上面的
            # 「整列空」兜底，不需要单独再查长度。
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

    layer.summary["表格数"] = len(blocks)
    layer.summary["数据行"] = total_rows
    return layer
