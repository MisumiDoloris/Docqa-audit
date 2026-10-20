"""对比层（底座互检）的回归测试。

为什么要这一层：单看一个底座的输出，有些错是看不出来的。
markitdown 把第二层表头（型号名）当成数据行，它自己的 Markdown 长得
跟「排版留白」一模一样，解析层分不清。只有拿两个底座解同一份 PDF、
把表头对齐比一遍，才看得出谁丢了字段。

用例里的表头形状取自 2026-10-19 跑华为 17 页彩页的实测输出，不是编的。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docqa_audit import model  # noqa: E402
from docqa_audit.auditors import cross_audit  # noqa: E402


def _cell(text, row=0, col=0, column_header=True, row_header=False):
    return {
        "text": text,
        "row": [row, row + 1],
        "col": [col, col + 1],
        "row_span": 1,
        "col_span": 1,
        "column_header": column_header,
        "row_header": row_header,
    }


class CrossAuditTest(unittest.TestCase):
    def test_lost_header_field_is_blocker(self):
        """docling 认出了型号名当表头，markitdown 把它当数据行丢了。

        这张表的「列」在 markitdown 那边少了两列，人工拿它的输出归档
        会丢掉型号区分，必须拦。
        """
        docling = [{
            "idx": 0, "num_rows": 3, "num_cols": 4,
            "cells": [
                _cell("类别", 0, 0, column_header=False, row_header=True),
                _cell("业务特性", 0, 1),
                _cell("CloudEngine S16700-4", 0, 2),
                _cell("CloudEngine S16700-8", 0, 3),
            ],
        }]
        md = (
            "| 类别 | 业务特性 |\n| --- | --- |\n"
            "| 交换机功能 | 二层基本功能 |\n"
        )
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.count(model.BLOCKER), 1)
        self.assertIn("S16700-4", layer.findings[0].what)

    def test_matching_headers_pass(self):
        """两边表头一样，这一层不许报拦。"""
        docling = [{
            "idx": 0, "num_rows": 2, "num_cols": 2,
            "cells": [_cell("模块", 0, 0), _cell("描述", 0, 1)],
        }]
        md = "| 模块 | 描述 |\n| --- | --- |\n| N1基础包 | 二层功能 |\n"
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.verdict, "通过")
        self.assertEqual(layer.count(model.BLOCKER), 0)

    def test_table_count_gap_is_record_only(self):
        """张数不同只记一笔。两个底座合并碎片的策略本来就不同，不是错。"""
        docling = [
            {"idx": 0, "num_rows": 2, "num_cols": 2,
             "cells": [_cell("模块", 0, 0), _cell("描述", 0, 1)]},
            {"idx": 1, "num_rows": 2, "num_cols": 2,
             "cells": [_cell("接口", 0, 0), _cell("数量", 0, 1)]},
        ]
        md = "| 模块 | 描述 |\n| --- | --- |\n| N1基础包 | 二层功能 |\n"
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.verdict, "通过")
        self.assertGreaterEqual(layer.count(model.INFO), 1)

    def test_misaligned_tables_do_not_fake_a_blocker(self):
        """两个底座的表顺序错开、各自还多一张对方没有的表时，不许硬配出假拦。

        形状照抄华为彩页的实测结果：docling 5 张、markitdown 5 张，顺序错开，
        docling 那侧多一张「项目|描述」的技术指标表。旧版逐张取最近邻、允许
        重复配对，会把这张多出来的表硬塞给 markitdown 的第 4 张（重合 1/3），
        造出一条根本不存在的「markitdown 少了『描述』」。真错只有一处：
        markitdown 把两个型号名丢了。误拦比漏拦更难解释。
        """
        def dtab(cells):
            return {"idx": 0, "num_rows": 2, "num_cols": len(cells),
                    "cells": [_cell(c, 0, i) for i, c in enumerate(cells)]}

        docling = [
            dtab(["N1基本软件", "N1基础包", "N1高级包"]),
            dtab(["类别", "业务特性", "CloudEngine S16700-4", "CloudEngine S16700-8"]),
            dtab(["项目", "CloudEngine S16700-4", "CloudEngine S16700-8"]),
            dtab(["模块概述", "描述", "支持版本"]),
            dtab(["项目", "描述"]),
        ]
        md = (
            "| License 授权 |\n| --- |\n| 甲 |\n\n"
            "| 交换机功能 | N1基本软件 | N1基础包 | N1高级包 |\n| --- | --- | --- | --- |\n"
            "| 甲 | 乙 | 丙 | 丁 |\n\n"
            "| 类别 | 业务特性 | CloudEngine | CloudEngine |\n| --- | --- | --- | --- |\n"
            "| 甲 | 乙 | 丙 | 丁 |\n\n"
            "| 项目 | CloudEngine S16700-4 | CloudEngine S16700-8 |\n| --- | --- | --- |\n"
            "| 甲 | 乙 | 丙 |\n\n"
            "| 模块概述 | 描述 | 支持版本 |\n| --- | --- | --- |\n"
            "| 甲 | 乙 | 丙 |\n"
        )
        layer = cross_audit.audit(docling, md)
        blockers = [f.what for f in layer.findings if f.severity == model.BLOCKER]
        self.assertEqual(len(blockers), 1, blockers)
        self.assertIn("S16700-4", blockers[0])


if __name__ == "__main__":
    unittest.main()
