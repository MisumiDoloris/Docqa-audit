"""把各层结果拼成一份报告。

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
    infos = sum(l.count(model.INFO) for l in layers)
    # 没跑完的层单独算一档：拦优先，其次未完成，再看警。
    # 少了这一档，配置里漏掉一层就会照出「通过」，签收的人看不出缺了两层。
    gaps = [l.name for l in layers if l.status in (model.NOT_RUN, model.INPUT_INVALID)]
    if blockers:
        overall = "不能交付"
    elif gaps:
        overall = "未完成验收"
    elif warns:
        overall = "能交付，但有要人看的地方"
    else:
        overall = "通过"
    out.append(f"**结论：{overall}**（拦 {blockers} 条，警 {warns} 条，记 {infos} 条）")
    if gaps:
        out.append("")
        out.append(f"本次没有跑完的层：{'、'.join(gaps)}。四层没跑齐，不算通过。")
    out += [
        "",
        "| 层 | 状态 | 结论 | 拦 | 警 | 记 | 摘要 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    def _fmt(v):
        if isinstance(v, dict):
            return " / ".join(f"{k} {x}" for k, x in v.items())
        return str(v)

    for l in layers:
        summary = "；".join(f"{k} {_fmt(v)}" for k, v in l.summary.items()) or "—"
        status = l.status + (f"｜{l.note}" if l.note else "")
        out.append(
            f"| {l.name} | {status} | {l.verdict} | {l.count(model.BLOCKER)} | {l.count(model.WARN)} | {l.count(model.INFO)} | {summary} |"
        )
    out.append("")

    for l in layers:
        out += [f"## {l.name}", "", f"状态：{l.status}" + (f"（{l.note}）" if l.note else ""),
                "", f"结论：**{l.verdict}**", ""]
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
        "端到端答对不算通过，每一层各自要过。标准答案块由人定，判卷由脚本做，不让模型给自己酌情。",
    ]
    return "\n".join(out) + "\n"
