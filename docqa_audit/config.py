"""读配置。路径一律相对配置文件所在目录，换机器不用改路径。"""

import json
import os


def load(path):
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    base = os.path.dirname(path)

    def resolve(p):
        return p if not p or os.path.isabs(p) else os.path.join(base, p)

    cfg = {"project": raw.get("project", ""), "base": base, "out": resolve(raw.get("out", "report.md"))}
    for section in ("parse", "retrieval", "claims"):
        if section in raw:
            cfg[section] = {k: resolve(v) if isinstance(v, str) else v for k, v in raw[section].items()}
    return cfg
