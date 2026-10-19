"""对比层雏形 v2：先归位，再对比。

markitdown 的输出是碎片（续行切断、页眉切断），先归位成逻辑表；
docling 也有碎片（无表头、跨页重复表头），同样归位；然后两边表头对比，
抓出某个底座丢字段、错列。

用法：
    python scripts/compare_headers.py \
        --docling-json /path/docling_tables.json \
        --markitdown-md /path/parsed_markitdown.md \
        --out /path/compare_report.html

docling 的 JSON 由 scripts/export_docling_json.py 导出。

归位规则来自 2026-10-19 晚对华为彩页的实测，三条：
1. 续行切断：一行数据被折成两半，下半截是普通文本夹在两个表格行中间，拼回上一行。
2. 空表头：表头非空不超过两格的，是续表，归到前面。
3. 数据行表头 / 重复表头：表头首格是数据（支持/冒号/编号）或与前面重复的，是续表。
"""

import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from docqa_audit.auditors import parse_audit  # noqa: E402


def reblock_markitdown(lines):
    """markitdown 碎片归位成逻辑表，返回每张逻辑表的表头（非空 cell 列表）。"""
    is_table = [ln.strip().startswith("|") for ln in lines]

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
        rows = [(no, ln) for no, ln in block if not parse_audit._SEP_LINE.match(ln)]
        if not rows:
            return []
        return [c.strip() for c in rows[0][1].strip().strip("|").split("|")]

    def is_data(hc):
        ne = [c for c in hc if c]
        if not ne:
            return False
        f = ne[0]
        return "支持" in f or "：" in f or ":" in f or re.match(r"^[A-Z]+[0-9]", f)

    groups = []
    seen = []
    for block in parse_audit._table_blocks(merged):
        hc = header(block)
        ne = [c for c in hc if c]
        dup = any(ne == p for p in seen if p)
        if groups and (len(ne) <= 2 or is_data(hc) or dup):
            continue
        groups.append(ne)
        seen.append(ne)
    return groups


def _is_field_name(s):
    s = s.strip()
    return bool(s) and len(s) <= 6 and not re.search(r"\d", s)


def reblock_docling(tables):
    """docling 归位：无表头、重复表头的表归前面，返回每张逻辑表的表头。

    docling 有时不把明显的字段名行标成 column_header（实测模块表的
    「模块概述|描述|支持版本」就没标）。补一条：第一行有多个格子且都是
    短名词（无数字），也当作表头。
    """
    groups = []
    seen = []
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


def overlap(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0
    return len(sa & sb) / max(len(sa), len(sb))


def esc(s):
    return html.escape(str(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docling-json", required=True)
    ap.add_argument("--markitdown-md", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    md_headers = reblock_markitdown(open(args.markitdown_md, encoding="utf-8").read().splitlines())
    dl_headers = reblock_docling(json.load(open(args.docling_json, encoding="utf-8"))["tables"])

    rows = []
    for i, d in enumerate(dl_headers):
        if not d:
            continue
        best = max(range(len(md_headers)), key=lambda j: overlap(d, md_headers[j]))
        m = md_headers[best]
        only_d = [x for x in d if x not in m]
        only_m = [x for x in m if x not in d]
        d_html = "、".join(
            '<span class="%s">%s</span>' % ("lost" if x in only_d else "ok", esc(x)) for x in d
        )
        m_html = "、".join(
            '<span class="%s">%s</span>' % ("extra" if x in only_m else "ok", esc(x)) for x in m
        )
        rows.append(
            '<div class="pair">'
            '<div class="head">docling 逻辑表%d ↔ markitdown 逻辑表%d（相似 %.2f）</div>'
            '<div class="row"><span class="tag">docling</span>%s</div>'
            '<div class="row"><span class="tag">markitdown</span>%s</div>'
            "</div>" % (i, best, overlap(d, m), d_html, m_html)
        )

    doc = (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "body{background:#1a1a1f;color:#d8d8e0;font-family:sans-serif;margin:24px}"
        ".pair{border:1px solid #3a3a44;border-radius:6px;padding:10px 14px;margin:10px 0;background:#222228}"
        ".head{font-weight:bold;margin-bottom:6px;color:#8ab4f8}"
        ".row{margin:4px 0;font-size:14px}"
        ".tag{display:inline-block;width:92px;color:#777}"
        ".lost{color:#ff6b6b;font-weight:bold}"
        ".extra{color:#e0b84c}"
        ".ok{color:#c8c8d0}"
        ".legend{color:#888;font-size:13px;margin-bottom:16px}"
        "</style></head><body><h2>表头对比（归位后）</h2>"
        '<div class="legend">markitdown %d 张逻辑表，docling %d 张逻辑表。红=markitdown 疑似丢失，黄=疑似多出。</div>'
        % (len(md_headers), len(dl_headers))
        + "".join(rows)
        + "</body></html>"
    )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)

    print("markitdown 归位 %d 张，docling 归位 %d 张" % (len(md_headers), len(dl_headers)))
    print("已写入", args.out)


if __name__ == "__main__":
    main()
