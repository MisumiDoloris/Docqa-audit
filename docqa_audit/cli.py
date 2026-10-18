"""命令行入口。

一条命令跑完三层，出一份 Markdown 报告：

    python3 -m docqa_audit run --config demo/config.json

配置里哪一层没写就跳过哪一层，方便只验一层。
"""

import argparse
import sys

from . import config as cfg_mod
from . import report as report_mod
from .auditors import claim_audit, parse_audit, retrieval_audit


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run(config_path):
    cfg = cfg_mod.load(config_path)
    layers = []

    if "parse" in cfg:
        layers.append(parse_audit.audit(_read(cfg["parse"]["file"]), cfg["parse"]["file"].rsplit("/", 1)[-1]))

    if "retrieval" in cfg:
        r = cfg["retrieval"]
        layers.append(retrieval_audit.audit(
            r["chunks"], r["questions"], r.get("ranking"),
            ks=tuple(r.get("ks", (1, 3, 5))),
        ))

    if "claims" in cfg:
        c = cfg["claims"]
        layers.append(claim_audit.audit(_read(c["answer"]), _read(c["source"])))

    if not layers:
        print("配置里没有可跑的层，检查 parse / retrieval / claims 三段", file=sys.stderr)
        return 2

    text = report_mod.render(layers, title="验收报告", meta={
        "项目": cfg["project"],
        "配置文件": config_path,
    })
    with open(cfg["out"], "w", encoding="utf-8") as f:
        f.write(text)

    print(text)
    print(f"\n[已写入] {cfg['out']}")
    return 0 if not any(l.count("blocker") for l in layers) else 1


def convert(pdf_path, out_path, tool="markitdown"):
    """调一个底座把 PDF 转成 Markdown，落盘后直接喂给解析层。"""
    if tool == "docling":
        from .adapters import docling_adapter as adapter
    elif tool == "markitdown":
        from .adapters import markitdown_adapter as adapter
    else:
        raise SystemExit(f"不认识这个底座：{tool}（可选 docling / markitdown）")

    md = adapter.convert_to_markdown(pdf_path, out_path)
    print(f"[已写入] {out_path}（{len(md)} 字）")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="docqa-audit", description="中文文档问答的三层验收")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="跑一次验收，出报告")
    p_run.add_argument("--config", required=True, help="配置文件路径")

    p_cv = sub.add_parser("convert", help="调底座把 PDF 转成 Markdown")
    p_cv.add_argument("--pdf", required=True)
    p_cv.add_argument("--out", required=True)
    p_cv.add_argument("--tool", default="markitdown", choices=["markitdown", "docling"],
                      help="用哪个底座解析，默认 markitdown（快、纯 python、无 OCR）")

    args = ap.parse_args(argv)
    if args.cmd == "run":
        return run(args.config)
    if args.cmd == "convert":
        return convert(args.pdf, args.out, args.tool)
    return 2


if __name__ == "__main__":
    sys.exit(main())
