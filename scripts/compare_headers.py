"""对比层的人看版：把两个底座的表头、列数、数据并排摆出来，出 HTML。

归位、配对、判定规则都在 docqa_audit/auditors/cross_audit.py，这个脚本只负责
排版。判据改一处就够，不会出现「命令行报的和报告里写的不一样」。

用法：
    python scripts/compare_headers.py \
        --docling-json /path/docling_tables.json \
        --markitdown-md /path/parsed_markitdown.md \
        --out /path/compare_report.html

docling 的 JSON 由 scripts/export_docling_json.py 导出。
"""

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from docqa_audit.auditors import cross_audit  # noqa: E402


def esc(s):
    return html.escape(str(s))


STYLE = (
    "body{background:#1a1a1f;color:#d8d8e0;font-family:sans-serif;margin:24px}"
    ".pair{border:1px solid #3a3a44;border-radius:6px;padding:10px 14px;margin:10px 0;background:#222228}"
    ".head{font-weight:bold;margin-bottom:6px;color:#8ab4f8}"
    ".shape{color:#777;font-weight:normal;margin-left:8px}"
    ".row{margin:4px 0;font-size:14px}"
    ".tag{display:inline-block;width:92px;color:#777}"
    ".lost{color:#ff6b6b;font-weight:bold}"
    ".extra{color:#e0b84c}"
    ".ok{color:#c8c8d0}"
    ".data{color:#e0b84c;font-size:13px;margin-top:6px}"
    ".legend{color:#888;font-size:13px;margin-bottom:16px}"
    ".miss{color:#9a9aa6;font-size:13px;margin:6px 0}"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docling-json", required=True)
    ap.add_argument("--markitdown-md", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    md_text = open(args.markitdown_md, encoding="utf-8").read()
    md_shapes = cross_audit.reblock_markitdown_shapes(md_text.splitlines())
    dl_shapes = cross_audit.reblock_docling_shapes(
        json.load(open(args.docling_json, encoding="utf-8"))["tables"]
    )
    md_headers = [g["header"] for g in md_shapes]
    dl_headers = [g["header"] for g in dl_shapes]
    assigned = cross_audit.pair_tables(dl_headers, md_headers)
    md_all = " ".join(g["text"] for g in md_shapes)

    blocks = []
    for i, d in enumerate(dl_headers, 1):
        if not d:
            continue
        if i - 1 not in assigned:
            blocks.append(
                '<div class="miss">docling 逻辑表%d（%s）在 markitdown 那边没有对应的表</div>'
                % (i, esc("、".join(d)))
            )
            continue
        j, score = assigned[i - 1]
        m = md_headers[j]
        ds, ms = dl_shapes[i - 1], md_shapes[j]
        d_keys = {cross_audit._norm(x) for x in d if x}
        m_keys = {cross_audit._norm(x) for x in m if x}
        d_html = "、".join(
            '<span class="%s">%s</span>' % ("lost" if cross_audit._norm(x) not in m_keys else "ok", esc(x))
            for x in d
        )
        m_html = "、".join(
            '<span class="%s">%s</span>' % ("extra" if cross_audit._norm(x) not in d_keys else "ok", esc(x))
            for x in m
        )

        shape = "docling %d 列 %d 行 · markitdown %d 列 %d 行" % (
            ds["cols"], max(ds["rows"] - 1, 0), ms["cols"], ms["rows"],
        )
        extra_html = ""
        if not [x for x in d if cross_audit._norm(x) not in m_keys]:
            if ds["cols"] > ms["cols"] and ms["cols"]:
                extra_html += '<div class="data">列数不一致：docling %d 列，markitdown %d 列（拦）</div>' % (
                    ds["cols"], ms["cols"],
                )
            missing = cross_audit.missing_data_tokens(ds["text"], md_all)
            if missing:
                extra_html += '<div class="data">数据里这些型号在 markitdown 全文找不到：%s</div>' % esc(
                    "、".join(missing[:6])
                )

        blocks.append(
            '<div class="pair">'
            '<div class="head">docling 逻辑表%d ↔ markitdown 逻辑表%d（表头相似 %.2f）'
            '<span class="shape">%s</span></div>'
            '<div class="row"><span class="tag">docling</span>%s</div>'
            '<div class="row"><span class="tag">markitdown</span>%s</div>'
            "%s</div>" % (i, j + 1, score, shape, d_html, m_html, extra_html)
        )

    doc = (
        '<!doctype html><html><head><meta charset="utf-8"><style>' + STYLE + "</style></head><body>"
        "<h2>表头 · 列数 · 数据对比（归位后，一对一配对）</h2>"
        '<div class="legend">markitdown 归位 %d 张逻辑表，docling 归位 %d 张，配上 %d 对。'
        "红=markitdown 疑似丢失的字段，黄=markitdown 多出的字段或数据里找不到的型号。"
        "行数只做参考，两个底座合并碎片的策略不同，差几行不算错。</div>"
        % (len(md_headers), len(dl_headers), len(assigned))
        + "".join(blocks)
        + "</body></html>"
    )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)

    print("markitdown 归位 %d 张，docling 归位 %d 张，配上 %d 对"
          % (len(md_headers), len(dl_headers), len(assigned)))
    print("已写入", args.out)


if __name__ == "__main__":
    main()
