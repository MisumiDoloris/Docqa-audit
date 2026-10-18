"""回归测试。跑法：python3 -m unittest discover -s tests -v

三条底线各留一个用例。最后一条是这一层最容易写错的地方，
真实项目里踩过一次：原文里 "FCS2-1001" 与 "1台" 挨着，归一化把空格删了，
两个字符串粘成 "10011台"，边界没了，本来对得上的数被判成编造。
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docqa_audit import model  # noqa: E402
from docqa_audit.auditors import claim_audit, parse_audit, retrieval_audit  # noqa: E402


class ParseAuditTest(unittest.TestCase):
    def test_column_mismatch_is_blocker(self):
        md = (
            "| 序号 | 名称 | 数量 |\n| --- | --- | --- |\n"
            "| 1 | 配电箱 | 3台 |\n"
            "| 2 | 按钮箱 |\n"
        )
        layer = parse_audit.audit(md)
        self.assertEqual(layer.count(model.BLOCKER), 1)
        self.assertIn("列数不一致", layer.findings[0].what)

    def test_clean_table_passes(self):
        md = "| 序号 | 名称 | 数量 |\n| --- | --- | --- |\n| 1 | 配电箱 | 3台 |\n"
        layer = parse_audit.audit(md)
        self.assertEqual(layer.verdict, "通过")

    def test_mangled_table_from_real_parser(self):
        """真实跑 MarkItDown 解一份带表 PDF 的输出，原样搬进来。

        列数一致，但表头被合成一格、第一行被切成两行、有两列空着。
        只查列数的版本判它「能交付」，等于瞎了。
        """
        md = (
            "| 序号 名称 | 规格型号     | 数量          | 生产厂家 | 合格证编号     |\n"
            "| ----- | -------- | ----------- | ---- | --------- |\n"
            "| 1 配电箱 | AL-01    | 3台 示例电气有限公司 |      | DEMO-0001 |\n"
            "| 2 按钮箱 | A-05     | 1个 示例电气有限公司 |      | DEMO-0002 |\n"
            "| 3     | FCS-A-01 |             |      | DEMO-0003 |\n"
            "| 现场控制站 |          | 1台 示例自控有限公司 |      |           |\n"
        )
        layer = parse_audit.audit(md)
        self.assertEqual(layer.verdict, "不可交付")
        whats = " ".join(f.what for f in layer.findings)
        self.assertIn("序号断行", whats)
        self.assertIn("表头疑似被合并", whats)


class RetrievalAuditTest(unittest.TestCase):
    def _write(self, rows):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.close()
        return f.name

    def test_mrr_and_miss(self):
        chunks = self._write([{"id": 0, "text": "甲"}, {"id": 1, "text": "乙"}])
        questions = self._write([
            {"id": 1, "q": "一问", "gt_ids": [0]},
            {"id": 2, "q": "二问", "gt_ids": [1]},
        ])
        ranking = self._write([
            {"qid": 1, "layer": "base", "ids": [0, 1]},   # 排第 1 → 1.0
            {"qid": 2, "layer": "base", "ids": [0, 1]},   # 排第 2 → 0.5
        ])
        layer = retrieval_audit.audit(chunks, questions, ranking)
        self.assertEqual(layer.summary["base"]["MRR"], 0.75)
        self.assertEqual(layer.count(model.BLOCKER), 0)

    def test_missing_answer_block_is_blocker(self):
        chunks = self._write([{"id": 0, "text": "甲"}, {"id": 1, "text": "乙"}])
        questions = self._write([{"id": 1, "q": "一问", "gt_ids": [1]}])
        ranking = self._write([{"qid": 1, "layer": "base", "ids": [0]}])
        layer = retrieval_audit.audit(chunks, questions, ranking)
        self.assertEqual(layer.count(model.BLOCKER), 1)


class ClaimAuditTest(unittest.TestCase):
    SRC = "序号3 现场控制站 FCS2-1001 数量 1台。电缆 900 m 进场合格。"

    def test_fabricated_quantity_flagged(self):
        layer = claim_audit.audit("数量 5 台，进场合格。", "数量 3 台，进场合格。")
        self.assertIn("数字回源", layer.findings[0].where)
        self.assertIn("5", layer.findings[0].what)

    def test_true_quantity_not_flagged(self):
        layer = claim_audit.audit("数量 3 台。", "数量 3 台。")
        self.assertEqual(layer.verdict, "通过")

    def test_code_and_quantity_next_to_each_other(self):
        """回归：编号后面紧跟数量时不能误判，删空格会让边界消失。"""
        layer = claim_audit.audit("现场控制站 FCS2-1001，数量 1台。", self.SRC)
        self.assertEqual(layer.verdict, "通过")

    def test_year_overclaim_is_blocker(self):
        layer = claim_audit.audit("有 5 年经验。", "有 2 年经验。")
        self.assertEqual(layer.count(model.BLOCKER), 1)


if __name__ == "__main__":
    unittest.main()
