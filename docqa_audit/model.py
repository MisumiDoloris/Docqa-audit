"""三层验收的公共数据结构。

设计上只有三样东西：一条发现（Finding）、一层的结论（LayerResult）、一份报告。
不给总分。分数会让人误以为九十分就能用，而这里要回答的是能不能交付。
"""

from dataclasses import dataclass, field

BLOCKER = "blocker"   # 不可交付
WARN = "warn"         # 可交付，但有需要人看的地方
INFO = "info"         # 记录，不影响判断

SEVERITY_LABEL = {BLOCKER: "拦", WARN: "警", INFO: "记"}


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

    def add(self, finding: Finding):
        self.findings.append(finding)
        return self

    def count(self, severity):
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def verdict(self):
        if self.count(BLOCKER):
            return "不可交付"
        if self.count(WARN):
            return "可交付，但有人要复核"
        return "通过"

    def sorted_findings(self):
        order = {BLOCKER: 0, WARN: 1, INFO: 2}
        return sorted(self.findings, key=lambda f: order.get(f.severity, 9))
