"""对比层雏形：两个底座解同一份 PDF，表头摆一起对，抓丢字段。

用法：
    python scripts/compare_headers.py \
        --docling-json /path/docling_tables.json \
        --markitdown-md /path/parsed_markitdown.md \
        --out /path/compare_report.html

docling 的 JSON 由 scripts/export_docling_json.py 导出。

已知局限（今晚实测）：配对是多对一，碎片归位还没做，所以同一张表可能被报好几次。
这个脚本只负责把差异摆出来给人看，不做最终判定。
"""

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from docqa_audit.auditors import parse_audit  # noqa: E402


def docling_headers(path):
    data = json.load(open(path, encoding="utf-8"))
    out = []
    for t in data["tables"]:
        hs = [c["text"] for c in t["cells"] if c["column_header"] and c["text"].strip()]
        out.append(hs)
    return out


def markitdown_headers(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    out = []
    for block in parse_audit._table_blocks(lines):
        rows = [(no, ln) for no, ln in block if not parse_audit._SEP_LINE.match(ln)]
        if not rows:
            continue
        header = [c.strip() for c in rows[0][1].strip().strip("|").split("|")]
        out.append([c for c in header if c])
    return out


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

    dh = docling_headers(args.docling_json)
    mh = markitdown_headers(args.markitdown_md)

    body = []
    for i, d in enumerate(dh):
        if not d:
            body.append('<div class="pair skip">docling 表%d：无列表头，跳过</div>' % i)
            continue
        best = max(range(len(mh)), key=lambda j: overlap(d, mh[j]))
        score = overlap(d, mh[best])
        if score < 0.3:
            body.append('<div class="pair nopair">docling 表%d：%s —— 未配对（最高 %.2f）</div>'
                        % (i, esc(d), score))
            continue
        m = mh[best]
        only_d = [x for x in d if x not in m]
        only_m = [x for x in m if x not in d]
        d_html = "、".join(
            '<span class="%s">%s</span>' % ("lost" if x in only_d else "ok", esc(x))
            for x in d
        )
        m_html = "、".join(
            '<span class="%s">%s</span>' % ("extra" if x in only_m else "ok", esc(x))
            for x in m
        )
        body.append(
            '<div class="pair">'
            '<div class="head">docling 表%d ↔ markitdown 表%d（相似 %.2f）</div>'
            '<div class="row"><span class="tag">docling</span>%s</div>'
            '<div class="row"><span class="tag">markitdown</span>%s</div>'
            "</div>" % (i, best, score, d_html, m_html)
        )

    doc = (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "body{background:#1a1a1f;color:#d8d8e0;font-family:sans-serif;margin:24px}"
        ".pair{border:1px solid #3a3a44;border-radius:6px;padding:10px 14px;margin:10px 0;background:#222228}"
        ".pair.skip,.pair.nopair{color:#888}"
        ".head{font-weight:bold;margin-bottom:6px;color:#8ab4f8}"
        ".row{margin:4px 0;font-size:14px}"
        ".tag{display:inline-block;width:88px;color:#777}"
        ".lost{color:#ff6b6b;font-weight:bold}"
        ".extra{color:#e0b84c}"
        ".ok{color:#c8c8d0}"
        "h2{color:#d8d8e0}"
        ".legend{color:#888;font-size:13px;margin-bottom:16px}"
        "</style></head><body><h2>表头对比</h2>"
        '<div class="legend">红=markitdown 疑似丢失，黄=markitdown 疑似多出。多对一已知，归位未做。</div>'
        + "".join(body)
        + "</body></html>"
    )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("docling %d 张，markitdown %d 张，已写入 %s" % (len(dh), len(mh), args.out))


if __name__ == "__main__":
    main()
