"""run 主流程的端到端测试：对比层接进一条命令的报告里。"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docqa_audit import cli  # noqa: E402


def _cell(text, col, column_header=True, row_header=False):
    return {"text": text, "row": [0, 1], "col": [col, col + 1],
            "row_span": 1, "col_span": 1,
            "column_header": column_header, "row_header": row_header}


class RunWithCrossTest(unittest.TestCase):
    def _write_project(self):
        """搭一个只有 cross 段的小项目，形状取自华为彩页的真丢列。"""
        d = tempfile.mkdtemp()
        docling = {
            "n_tables": 1,
            "tables": [{
                "idx": 0, "num_rows": 2, "num_cols": 4,
                "cells": [
                    _cell("类别", 0, column_header=False, row_header=True),
                    _cell("业务特性", 1),
                    _cell("CloudEngine S16700-4", 2),
                    _cell("CloudEngine S16700-8", 3),
                ],
            }],
        }
        with open(os.path.join(d, "docling.json"), "w", encoding="utf-8") as f:
            json.dump(docling, f, ensure_ascii=False)
        with open(os.path.join(d, "markitdown.md"), "w", encoding="utf-8") as f:
            f.write("| 类别 | 业务特性 |\n| --- | --- |\n| 甲 | 乙 |\n")
        cfg = {
            "project": "对比层端到端测试",
            "cross": {"docling_json": "docling.json", "markitdown_md": "markitdown.md"},
            "out": "report.md",
        }
        cfg_path = os.path.join(d, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        return d, cfg_path

    def test_run_reports_cross_layer_and_catches_loss(self):
        d, cfg_path = self._write_project()
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.run(cfg_path)
        report = open(os.path.join(d, "report.md"), encoding="utf-8").read()

        self.assertEqual(rc, 1, "有 blocker 时退出码应是 1")
        self.assertIn("对比层", report)
        self.assertIn("S16700-4", report)
        self.assertIn("不可交付", report)


if __name__ == "__main__":
    unittest.main()
