"""第二层：检索的验收。

关键一条：端到端答对了不算数，要看标准答案块排在第几。
标准答案块由人定，脚本只负责打分，不给模型酌情的机会。

输入两个文件：
- chunks.jsonl   {"id": 0, "text": "..."}
- questions.jsonl {"id": 1, "q": "...", "gt_ids": [2]}

排位有两个来源：
- 有 ranking.jsonl 就用真的（{"qid":1, "layer":"bm25", "ids":[...]}），可以按 layer 分组拆层
- 没有就用内置的关键词重叠打分，当基线跑，报告里会标成「内置基线」
"""

import json
import re

from .. import model

_WS = re.compile(r"\s+")


def norm(s):
    return _WS.sub("", s).lower()


def tokenize(t):
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", norm(t)))


def baseline_rank(q, chunks, k=10):
    """内置基线：Jaccard 重叠。故意做得很朴素，跑起来能看出问题就行。"""
    qt = tokenize(q)
    scored = []
    for c in chunks:
        ct = tokenize(c["text"])
        scored.append((len(qt & ct) / max(1, len(qt | ct)), c["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [cid for _, cid in scored[:k]]


def _load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def audit(chunks_path, questions_path, ranking_path=None, ks=(1, 3, 5), ranking_rows=None):
    layer = model.LayerResult("检索层")
    chunks = _load_jsonl(chunks_path)
    questions = _load_jsonl(questions_path)

    layer.summary["切块数"] = len(chunks)
    layer.summary["题数"] = len(questions)

    by_id = {c["id"]: c for c in chunks}
    rankings = {}
    if ranking_rows:
        for row in ranking_rows:
            rankings.setdefault(row.get("layer", "default"), {})[row["qid"]] = row["ids"]
    elif ranking_path:
        for row in _load_jsonl(ranking_path):
            rankings.setdefault(row.get("layer", "default"), {})[row["qid"]] = row["ids"]

    if not rankings:
        rankings = {}
        for q in questions:
            rankings.setdefault("内置基线", {})[q["id"]] = baseline_rank(q["q"], chunks)

    for layer_name, per_q in rankings.items():
        hit = {k: 0 for k in ks}
        rr_sum = 0.0
        missed = []
        for q in questions:
            ids = per_q.get(q["id"], [])
            first = None
            for rank, cid in enumerate(ids, 1):
                if cid in q["gt_ids"]:
                    first = rank
                    break
            if first is None:
                missed.append(q["id"])
                continue
            rr_sum += 1.0 / first
            for k in ks:
                if first <= k:
                    hit[k] += 1
        n = max(1, len(questions))
        layer.summary[layer_name] = {
            **{f"hit@{k}": round(hit[k] / n, 3) for k in ks},
            "MRR": round(rr_sum / n, 3),
            "未命中题数": len(missed),
        }
        if missed:
            layer.add(model.Finding(
                f"{layer_name}｜题 {', '.join(map(str, missed[:8]))}",
                f"{len(missed)} 道题前 10 名里找不到标准答案块",
                model.BLOCKER,
                "先看这几题的原文块有没有进库、切块有没有把答案切断，别急着改提示词",
            ))

    # 口径：不看绝对值，只看相对变化。
    # 检索质量的绝对线没有行业基准，定一条线就是编数，所以这里只报改动前后的差。
    names = list(rankings)
    if len(names) > 1:
        base = names[0]
        base_mrr = layer.summary[base]["MRR"]
        base_hit = layer.summary[base].get("hit@1", 0)
        for name in names[1:]:
            m = layer.summary[name]
            d_mrr = round(m["MRR"] - base_mrr, 3)
            d_hit = round(m.get("hit@1", 0) - base_hit, 3)
            layer.summary[name]["相对" + base] = f"MRR {d_mrr:+.3f} / hit@1 {d_hit:+.3f}"
            if d_mrr < 0 or d_hit < 0:
                layer.add(model.Finding(
                    f"{name} 相比 {base}",
                    f"MRR {d_mrr:+.3f}，hit@1 {d_hit:+.3f}，这一层在往后退",
                    model.WARN,
                    "改动前后一定要各留一份排位再比，只看绝对值比不出东西",
                ))
            else:
                layer.add(model.Finding(
                    f"{name} 相比 {base}",
                    f"MRR {d_mrr:+.3f}，hit@1 {d_hit:+.3f}",
                    model.INFO,
                    "",
                ))
        layer.add(model.Finding(
            "拆层对比",
            f"基线取 {base}，其余层只报相对变化",
            model.INFO,
            "",
        ))
    return layer
