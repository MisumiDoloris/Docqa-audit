"""把三层结果拼成一份报告。

报告只回答一个问题：这份东西能不能交付；如果不能，是哪一层、哪一处。
不给总分。总分是糊人的，端到端九十分的东西可能每一层都有硬伤。
"""

from . import model


def render(layers, title="验收报告", meta=None):
    meta = meta or {}
    out = [f"# {title}", ""]

    for k, v in meta.items():
        out.append(f"- {k}：{v}")
    if meta:
        out.append("")

    blockers = sum(l.count(model.BLOCKER) for l in layers)
    warns = sum(l.count(model.WARN) for l in layers)
    overall = "不能交付" if blockers else ("能交付，但有要人看的地方" if warns else "通过")
    out += [
        f"**结论：{overall}**（拦 {blockers} 条，警 {warns} 条）",
        "",
        "| 层 | 结论 | 拦 | 警 | 摘要 |",
        "| --- | --- | --- | --- | --- |",
    ]
    def _fmt(v):
        if isinstance(v, dict):
            return " / ".join(f"{k} {x}" for k, x in v.items())
        return str(v)

    for l in layers:
        summary = "；".join(f"{k} {_fmt(v)}" for k, v in l.summary.items()) or "—"
        out.append(
            f"| {l.name} | {l.verdict} | {l.count(model.BLOCKER)} | {l.count(model.WARN)} | {summary} |"
        )
    out.append("")

    for l in layers:
        out += [f"## {l.name}", "", f"结论：**{l.verdict}**", ""]
        items = l.sorted_findings()
        if not items:
            out += ["没有发现问题。", ""]
            continue
        out += ["| 级别 | 位置 | 发现 | 建议 |", "| --- | --- | --- | --- |"]
        for f in items:
            out.append(f.as_row())
        out.append("")

    out += [
        "---",
        "",
        "口径说明。这份报告不打分，只判能不能交付。",
        "端到端答对不算通过，三层各自要过。标准答案块由人定，判卷由脚本做，不让模型给自己酌情。",
    ]
    return "\n".join(out) + "\n"
