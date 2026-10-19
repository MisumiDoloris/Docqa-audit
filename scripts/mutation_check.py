"""破坏实验：验证测试是不是真在测东西。

原理一句话：把代码里的关键判断故意改坏，测试必须变红。
改坏了测试还是绿的，说明那条测试是摆设，或者那段代码根本没被覆盖。

做法是复制一份原文件，替换指定片段，跑测试，无论结果如何都还原，
并用 sha256 核对还原是否成功。任何一步失败都会中止并报出来。

用法：
    .venv/bin/python scripts/mutation_check.py            # 全跑
    .venv/bin/python scripts/mutation_check.py --only M3  # 只跑一个

结论怎么看：
    被杀 = 这条测试有效，它抓得住这个错。
    存活 = 没有测试覆盖到这里，或者断言写得太松。
注意：存活不一定是测试坏，也可能是这个变异本身不等价于错误（见每条的备注）。
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")

# (编号, 文件, 原片段, 改坏成, 这一步在破坏什么)
MUTATIONS = [
    (
        "M1", "docqa_audit/auditors/parse_audit.py",
        '                model.BLOCKER,\n                "多半是合并单元格丢了或某行被切断',
        '                model.WARN,\n                "多半是合并单元格丢了或某行被切断',
        "列数不一致从「拦」降成「警」，正常应该拦住假数据",
    ),
    (
        "M2", "docqa_audit/auditors/parse_audit.py",
        "if len(seq) >= 3 and 0 < numeric < len(seq):",
        "if False and len(seq) >= 3:",
        "关掉首列序号断行检测，真实解析器的烂表应当被抓出来",
    ),
    (
        "M3", "docqa_audit/auditors/parse_audit.py",
        '                model.INFO,\n                "这列表头是空的',
        '                model.WARN,\n                "这列表头是空的',
        "表头空列从「记」改回「警」，空列只记不警的口径应当被锁住",
    ),
    (
        "M4", "docqa_audit/auditors/retrieval_audit.py",
        "rr_sum += 1.0 / first",
        "rr_sum += 1.0",
        "把 MRR 的倒数排位改成常数，指标算错",
    ),
    (
        "M5", "docqa_audit/auditors/retrieval_audit.py",
        "if d_mrr < 0 or d_hit < 0:",
        "if False:",
        "拆层对比时不再报「这一层在往后退」",
    ),
    (
        "M6", "docqa_audit/auditors/claim_audit.py",
        "def _has_anchor(src_compact, src_spaced, key, unit):\n    if not unit:",
        "def _has_anchor(src_compact, src_spaced, key, unit):\n    return True\n    if not unit:",
        "回源校验永远判通过，编造的数字再也拦不住",
    ),
    (
        "M7", "docqa_audit/auditors/claim_audit.py",
        "            \"年限表述\", \"原文里找不到：\" + \"、\".join(missing[\"年限\"][:5]),\n            model.BLOCKER,",
        "            \"年限表述\", \"原文里找不到：\" + \"、\".join(missing[\"年限\"][:5]),\n            model.WARN,",
        "年限虚报从「拦」降成「警」",
    ),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_tests():
    p = subprocess.run(
        [PY, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return p.returncode, (p.stderr or "") + (p.stdout or "")


def first_failing_test(output):
    for line in output.splitlines():
        line = line.strip()
        if line.startswith(("FAIL:", "ERROR:")):
            return line.split(":")[1].strip().split(" ")[0]
    return ""


def apply_mutation(rel_path, old, new):
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        return None, f"原片段出现 {text.count(old)} 次，无法唯一定位"
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只跑某个变异体，如 M3")
    args = ap.parse_args()

    if not Path(PY).exists():
        print(f"找不到虚拟环境解释器：{PY}")
        return 2

    base_code, base_out = run_tests()
    if base_code != 0:
        print("基线测试本来就不绿，破坏实验没有意义，先修测试。")
        print(base_out[-1500:])
        return 2
    print(f"基线：测试全绿（{base_out.strip().splitlines()[-1] if base_out.strip() else ''}）\n")

    rows = []
    for mid, rel, old, new, desc in MUTATIONS:
        if args.only and args.only != mid:
            continue
        path = ROOT / rel
        before = sha(path)
        backup = path.with_suffix(path.suffix + ".mutation_bak")
        shutil.copy2(path, backup)
        try:
            applied, err = apply_mutation(rel, old, new)
            if applied is None:
                rows.append((mid, desc, "无效变异", err, ""))
                continue
            code, out = run_tests()
            if code != 0:
                rows.append((mid, desc, "被杀", first_failing_test(out), ""))
            else:
                rows.append((mid, desc, "存活", "", "没有测试覆盖到这一处"))
        finally:
            shutil.copy2(backup, path)
            backup.unlink(missing_ok=True)
            after = sha(path)
            if before != after:
                print(f"!! 还原失败：{rel}（{mid}）请立刻用 git checkout 恢复")
                return 3

    print(f"{'编号':<5}{'结论':<8}{'抓住它的测试':<34}破坏了什么")
    print("-" * 110)
    for mid, desc, verdict, catcher, note in rows:
        print(f"{mid:<5}{verdict:<8}{(catcher or note or '-'):<34}{desc}")

    killed = sum(1 for r in rows if r[2] == "被杀")
    alive = sum(1 for r in rows if r[2] == "存活")
    bad = sum(1 for r in rows if r[2] == "无效变异")
    print(f"\n小计：被杀 {killed}，存活 {alive}，无效 {bad}，共 {len(rows)}")
    if alive:
        print("存活的要补测试，或者确认这个变异不等价于真实错误。")
    return 0 if alive == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
