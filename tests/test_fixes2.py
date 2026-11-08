"""第二批：审查员报的其余发现，逐条落成用例。

分两类：
- 前五条是「现在就会出错」的，跑出来应该红。
- 后三条（指标边界、碎片归位、字数阈值）实现是对的，只是没有用例守着。
"""

import json
import os
import tempfile
import unittest

from docqa_audit import model
from docqa_audit.auditors import claim_audit, cross_audit, parse_audit, retrieval_audit


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False), file=f)


def _make(chunk_rows, q_rows, rank_rows):
    d = tempfile.mkdtemp()
    ch, qs, rk = (os.path.join(d, n) for n in ("c.jsonl", "q.jsonl", "r.jsonl"))
    _write_jsonl(ch, chunk_rows)
    _write_jsonl(qs, q_rows)
    _write_jsonl(rk, rank_rows)
    return ch, qs, rk


CHUNKS = [{"id": 0, "text": "配电箱 3 台"}, {"id": 1, "text": "按钮箱 2 台"}]
QUESTIONS = [{"id": 1, "q": "配电箱几台", "gt_ids": [0]}, {"id": 2, "q": "按钮箱几台", "gt_ids": [1]}]


class BaselineOrderTest(unittest.TestCase):
    def test_baseline_is_not_decided_by_file_order(self):
        """同一对层，只把在文件里的先后顺序换一下，结论必须一样。"""
        a = _make(CHUNKS, QUESTIONS,
                  [{"qid": 1, "layer": "worse", "ids": [1, 0]},
                   {"qid": 2, "layer": "worse", "ids": [0, 1]},
                   {"qid": 1, "layer": "base", "ids": [0, 1]},
                   {"qid": 2, "layer": "base", "ids": [1, 0]}])
        b = _make(CHUNKS, QUESTIONS,
                  [{"qid": 1, "layer": "base", "ids": [0, 1]},
                   {"qid": 2, "layer": "base", "ids": [1, 0]},
                   {"qid": 1, "layer": "worse", "ids": [1, 0]},
                   {"qid": 2, "layer": "worse", "ids": [0, 1]}])
        va = retrieval_audit.audit(*a).verdict
        vb = retrieval_audit.audit(*b).verdict
        self.assertEqual(va, vb, "结论不许由排位文件的行序决定")
        self.assertEqual(va, "可交付，但有人要复核", "有一层在往后退，应当报出来")


class MissingQuestionTest(unittest.TestCase):
    def test_layer_that_skips_a_question_is_warned_not_blocked(self):
        """某层少给一题的排位，是「没取到」，不是「真的没检索到」。"""
        ch, qs, rk = _make(CHUNKS, QUESTIONS,
                           [{"qid": 1, "layer": "bm25", "ids": [0, 1]},
                            {"qid": 2, "layer": "bm25", "ids": [1, 0]},
                            {"qid": 1, "layer": "dense", "ids": [0, 1]}])
        l = retrieval_audit.audit(ch, qs, rk)
        self.assertEqual(l.count(model.BLOCKER), 0, [f.what for f in l.findings])
        self.assertGreaterEqual(l.count(model.WARN), 1)
        self.assertIn("未给题数", l.summary.get("dense", {}))


class UnitMismatchTest(unittest.TestCase):
    def test_number_exists_but_unit_differs(self):
        l = claim_audit.audit("配电箱 3 根。", "配电箱 3 台。")
        text = " ".join(f.what for f in l.findings)
        self.assertIn("单位", text)
        self.assertNotIn("原文里找不到", text)

    def test_advice_does_not_teach_user_to_dismiss_unit_errors(self):
        l = claim_audit.audit("配电箱 3 根。", "配电箱 3 台。")
        advice = " ".join(f.advice for f in l.findings)
        self.assertNotIn("别一概当编造", advice)


class TruncationTest(unittest.TestCase):
    def test_truncated_list_says_total_count(self):
        nums = "、".join(f"{i} 台" for i in range(1, 13))
        l = claim_audit.audit(nums, "原文里一个数都没有")
        text = " ".join(f.what for f in l.findings)
        self.assertIn("12", text, "12 处全错时必须写出总数，不能只列 8 个")


class ThresholdTest(unittest.TestCase):
    def test_min_chars_boundary(self):
        short = parse_audit.audit("字" * 49)
        long_ = parse_audit.audit("字" * 51)
        self.assertEqual(short.count(model.BLOCKER), 1, "49 字应当拦")
        self.assertEqual(long_.count(model.BLOCKER), 0, "51 字只该记警")


class MetricBoundaryTest(unittest.TestCase):
    def test_hit_at_1_counts_rank_one(self):
        ch, qs, rk = _make(CHUNKS, QUESTIONS,
                           [{"qid": 1, "layer": "x", "ids": [0, 1]},
                            {"qid": 2, "layer": "x", "ids": [1, 0]}])
        l = retrieval_audit.audit(ch, qs, rk)
        self.assertEqual(l.summary["x"]["hit@1"], 1.0)

    def test_mrr_denominator_counts_all_questions(self):
        """一题中一题漏，MRR 必须是 0.5，不能只按答对的题算。"""
        ch, qs, rk = _make(CHUNKS, QUESTIONS,
                           [{"qid": 1, "layer": "x", "ids": [0, 1]},
                            {"qid": 2, "layer": "x", "ids": [0]}])
        l = retrieval_audit.audit(ch, qs, rk)
        self.assertEqual(l.summary["x"]["MRR"], 0.5)


class ReblockTest(unittest.TestCase):
    def test_continuation_line_is_stitched_back(self):
        md = ("| 序号 | 名称 |\n| --- | --- |\n| 1 | 配电\n"
              "箱 |\n| 2 | 按钮箱 |\n")
        groups = cross_audit.reblock_markitdown_shapes(md.splitlines())
        self.assertEqual(len(groups), 1, "被切断的半行要拼回上一行")
        self.assertEqual(groups[0]["rows"], 2)

    def test_empty_header_fragment_merges_into_previous(self):
        md = ("| 序号 | 名称 |\n| --- | --- |\n| 1 | 甲 |\n\n"
              "|  | 备注 |\n| --- | --- |\n| 2 | 乙 |\n")
        groups = cross_audit.reblock_markitdown_shapes(md.splitlines())
        self.assertEqual(len(groups), 1, "只有一两格表头的碎片是续表")

    def test_duplicate_header_fragment_merges_into_previous(self):
        md = ("| 序号 | 名称 |\n| --- | --- |\n| 1 | 甲 |\n\n"
              "| 序号 | 名称 |\n| --- | --- |\n| 2 | 乙 |\n")
        groups = cross_audit.reblock_markitdown_shapes(md.splitlines())
        self.assertEqual(len(groups), 1, "重复的表头是续表")
