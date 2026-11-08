"""三层验收的公共数据结构。

设计上只有三样东西：一条发现（Finding）、一层的结论（LayerResult）、一份报告。
不给总分。分数会让人误以为九十分就能用，而这里要回答的是能不能交付。
"""

from dataclasses import dataclass, field

BLOCKER = "blocker"   # 不可交付
WARN = "warn"         # 可交付，但有需要人看的地方
INFO = "info"         # 记录，不影响判断

SEVERITY_LABEL = {BLOCKER: "拦", WARN: "警", INFO: "记"}

# 每层的状态。四档，用来区分「查过没问题」「没检查」「没取到」。
# 少了这四档，三种完全不同的情况在报告里长得一样，签收的人分不出来。
CHECKED = "已检查"          # 有输入、跑完了
PARTIAL = "已检查（部分跳过）"  # 跑了，但有东西没比成
INPUT_INVALID = "输入无效"   # 配了，但文件空、解析出 0 行、题集为空
NOT_RUN = "未运行"          # 配置里没有这一段


@dataclass
class Finding:
    """一条发现。where 指位置，what 指发现了什么，advice 指该怎么办。"""

    where: str
    what: str
    severity: str = WARN
    advice: str = ""

    def as_row(self):
        return f"| {SEVERITY_LABEL.get(self.severity, self.severity)} | {self.where} | {self.what} | {self.advice} |"


@dataclass
class LayerResult:
    name: str
    summary: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    status: str = CHECKED
    note: str = ""

    def add(self, finding: Finding):
        self.findings.append(finding)
        return self

    def count(self, severity):
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def verdict(self):
        # 状态优先于发现：没跑的层不给自己下结论。
        # 但有拦的层仍然照报「不可交付」——拦比「无法判定」重，不能因为输入不全就把已经抓到的错降级。
        if self.status == NOT_RUN:
            return "—"
        if self.count(BLOCKER):
            return "不可交付"
        if self.status == INPUT_INVALID:
            return "无法判定"
        if self.count(WARN):
            return "可交付，但有人要复核"
        return "通过"

    def sorted_findings(self):
        order = {BLOCKER: 0, WARN: 1, INFO: 2}
        return sorted(self.findings, key=lambda f: order.get(f.severity, 9))
