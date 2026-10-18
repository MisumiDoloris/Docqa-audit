"""检索底座：真正的 BM25，替掉之前那个词重叠兜底。

中文没有空格，BM25 需要先切词才能用。这里不引分词库，用「汉字二元组」当词：
「合格证编号」切成 合格/格证/证编/编号 四个二元组。
这个做法糙但稳，零依赖，中文召回够用；缺点是它认不出「合格证」是一个词，
同义改写（合格证书 → 合格证明）就丢分了。要更好就接 jieba 或自己的词表，
接口不用改，换 tokenize 就行。

用法：
    python3 -m docqa_audit rank --chunks demo/chunks/chunks.jsonl \
        --questions demo/questions/questions.jsonl --out demo/retrieval/bm25.jsonl
"""

import json
import re

_ZH = re.compile(r"[\u4e00-\u9fff]+")
_EN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    """中文按字二元组切，英文数字按整串。故意不引分词库。"""
    t = text.lower()
    tokens = _EN.findall(t)
    for seg in _ZH.findall(t):
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return tokens


def available():
    try:
        import rank_bm25  # noqa: F401
        return True
    except Exception:
        return False


def rank(chunks, questions, k=10, layer="bm25"):
    """返回 [{"qid":.., "layer":.., "ids":[..]}]，格式跟 ranking.jsonl 一致。"""
    try:
        from rank_bm25 import BM25Okapi
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("没装 rank_bm25。装法：.venv/bin/pip install rank_bm25") from exc

    corpus = [tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    ids = [c["id"] for c in chunks]

    rows = []
    for q in questions:
        scores = bm25.get_scores(tokenize(q["q"]))
        order = sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))[:k]
        rows.append({"qid": q["id"], "layer": layer, "ids": [ids[i] for i in order]})
    return rows


def write_ranking(chunks_path, questions_path, out_path, k=10, layer="bm25"):
    def load(p):
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    rows = rank(load(chunks_path), load(questions_path), k=k, layer=layer)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows
