"""状态机的口径：报告必须分得清「查过没问题」「没检查」「没取到」。

2026-11-08 加。起因是三个独立审查员都指出同一个根子：
空的输入、没配的层、跳过没比的表，全都在报告里变成「通过」。
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from docqa_audit import model, report
from docqa_audit.auditors import cross_audit, parse_audit, retrieval_audit
from docqa_audit.cli import run as cli_run


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False), file=f)


class LayerStatusTest(unittest.TestCase):
    def test_input_invalid_layer_says_unable_to_judge(self):
        l = model.LayerResult("检索层")
        l.status = model.INPUT_INVALID
        l.note = "排位文件 0 行"
        self.assertEqual(l.verdict, "无法判定")

    def test_not_run_layer_does_not_claim_pass(self):
        l = model.LayerResult("对比层")
        l.status = model.NOT_RUN
        self.assertEqual(l.verdict, "—")


class OverallVerdictTest(unittest.TestCase):
    def test_overall_is_unfinished_when_a_layer_did_not_run(self):
        ok = model.LayerResult("解析层")
        miss = model.LayerResult("对比层")
        miss.status = model.NOT_RUN
        text = report.render([ok, miss])
        self.assertIn("未完成验收", text)
        self.assertIn("对比层", text)

    def test_overall_is_pass_only_when_every_layer_checked(self):
        text = report.render([model.LayerResult("解析层")])
        self.assertIn("结论：通过", text)
        self.assertNotIn("未完成", text)

    def test_blocker_still_wins_over_unfinished(self):
        bad = model.LayerResult("解析层")
        bad.add(model.Finding("表1", "列数不一致", model.BLOCKER))
        miss = model.LayerResult("对比层")
        miss.status = model.NOT_RUN
        self.assertIn("不能交付", report.render([bad, miss]))

    def test_report_row_carries_status_and_note(self):
        l = model.LayerResult("对比层")
        l.status = model.INPUT_INVALID
        l.note = "markitdown.md 是空的"
        text = report.render([l])
        self.assertIn("输入无效", text)
        self.assertIn("markitdown.md 是空的", text)


class EmptyInputTest(unittest.TestCase):
    def test_empty_table_is_input_invalid(self):
        l = parse_audit.audit("|  |  |\n| --- | --- |\n|  |  |\n")
        self.assertEqual(l.status, model.INPUT_INVALID)

    def test_cross_with_one_side_empty_is_input_invalid(self):
        l = cross_audit.audit([], "| 型号 | 数量 |\n| --- | --- |\n| S5735 | 3 台 |\n")
        self.assertEqual(l.status, model.INPUT_INVALID)
        self.assertNotEqual(l.verdict, "通过")

    def test_single_table_with_long_header_is_not_silently_skipped(self):
        """表头一格超过旧门槛（6 字）时，这张表要么比过，要么明说没比，不许静默跳过还说通过。"""
        cl = lambda t, r, c: dict(text=t, row=[r, r + 1], col=[c, c + 1],
                                  column_header=False, row_header=False)
        dl = [dict(num_rows=2, num_cols=2,
                   cells=[cl("设备名称及规格型号", 0, 0), cl("数量", 0, 1),
                          cl("AL-01", 1, 0), cl("3", 1, 1)])]
        md = "| 设备名称 | 数量 |\n| --- | --- |\n| AL-01 | 3 |\n"
        l = cross_audit.audit(dl, md)
        if l.verdict == "通过":
            self.assertGreaterEqual(l.summary.get("配上", 0), 1, "说通过就必须真比过")
        else:
            self.assertIn(l.status, (model.INPUT_INVALID, model.PARTIAL))

    def test_empty_ranking_file_is_not_silently_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            ch = os.path.join(d, "chunks.jsonl")
            qs = os.path.join(d, "questions.jsonl")
            rk = os.path.join(d, "ranking.jsonl")
            _write_jsonl(ch, [{"id": 0, "text": "配电箱 3 台"}, {"id": 1, "text": "按钮箱 2 台"}])
            _write_jsonl(qs, [{"id": 1, "q": "配电箱几台", "gt_ids": [0]}])
            with open(rk, "w"):
                pass
            l = retrieval_audit.audit(ch, qs, rk)
            self.assertEqual(l.status, model.INPUT_INVALID)
            self.assertNotEqual(l.verdict, "通过")


class CliNotRunTest(unittest.TestCase):
    def test_layer_missing_from_config_is_marked_not_run(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, "parsed.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write("| 序号 | 名称 |\n| --- | --- |\n| 1 | 配电箱 |\n")
            out = os.path.join(d, "report.md")
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"project": "t", "parse": {"file": "parsed.md"}, "out": "report.md"},
                          f, ensure_ascii=False)
            with redirect_stdout(io.StringIO()):
                cli_run(cfg)
            with open(out, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("未完成验收", text)
            self.assertIn("检索层", text)
            self.assertIn("未运行", text)
            self.assertIn("对比层", text)
