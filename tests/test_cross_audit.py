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

    def test_corner_cell_counts_as_header(self):
        """docling 把左上角格标成既非列头也非行头（corner），不能丢。

        真数据里 docling 的「交换机功能」这格 column_header=false、row_header=false，
        但它是表头第一列。漏了它，会把 markitdown 的正常表头误报成「多出」。
        两边表头明明一样，不许报一条记。
        """
        docling = [{
            "idx": 0, "num_rows": 2, "num_cols": 4,
            "cells": [
                _cell("交换机功能", 0, 0, column_header=False, row_header=False),
                _cell("N1基本软件", 0, 1),
                _cell("N1基础包", 0, 2),
                _cell("N1高级包", 0, 3),
            ],
        }]
        md = (
            "| 交换机功能 | N1基本软件 | N1基础包 | N1高级包 |\n| --- | --- | --- | --- |\n"
            "| 甲 | 乙 | 丙 | 丁 |\n"
        )
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.verdict, "通过")
        self.assertEqual(layer.count(model.INFO), 0)

    def test_column_gap_with_same_headers_is_blocker(self):
        """表头名字一样但列数差着（合并单元格、整列被吞），按口径直接拦。

        docling 的 num_cols 是网格列数，表头因为合并单元格只出 2 个名字；
        markitdown 那边 2 列。表头比不出差，列数一比就出来了。
        """
        docling = [{
            "idx": 0, "num_rows": 2, "num_cols": 5,
            "cells": [_cell("项目", 0, 0), _cell("规格", 0, 1, column_header=True),
                      _cell("3 台", 1, 0)],
        }]
        md = "| 项目 | 规格 |\n| --- | --- |\n| 3 台 | 见上 |\n"
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.count(model.BLOCKER), 1)
        self.assertIn("5 列", layer.findings[0].what)
        self.assertIn("2 列", layer.findings[0].what)

    def test_lost_model_number_in_data_is_warn(self):
        """数据行里的型号在整份 markitdown 输出里找不到，要报警。

        表头一样、列数一样，只有数据丢了。这种情况前面几项判据全绿，
        只有拿数据里的字母数字串去全文找才抓得到。
        """
        docling = [{
            "idx": 0, "num_rows": 2, "num_cols": 2,
            "cells": [_cell("型号", 0, 0), _cell("数量", 0, 1),
                      _cell("S5735-L24T4X", 1, 0), _cell("3 台", 1, 1)],
        }]
        md = "| 型号 | 数量 |\n| --- | --- |\n| S5735-L24T4S | 3 台 |\n"
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.count(model.BLOCKER), 0)
        warns = [f.what for f in layer.findings if f.severity == model.WARN]
        self.assertTrue(any("S5735-L24T4X" in w for w in warns), warns)

    def test_model_number_found_elsewhere_is_not_warned(self):
        """型号出现在文档别的表里就不算丢，别报假警。

        碎片归位差一点就会把同一条数据算到别的表上，所以比的是整份输出。
        """
        docling = [{
            "idx": 0, "num_rows": 2, "num_cols": 2,
            "cells": [_cell("型号", 0, 0), _cell("数量", 0, 1),
                      _cell("S5735-L24T4X", 1, 0), _cell("3 台", 1, 1)],
        }]
        md = (
            "| 型号 | 数量 |\n| --- | --- |\n| 见下表 | 3 台 |\n\n"
            "| 硬件型号 | 说明 |\n| --- | --- |\n| S5735-L24T4X | 见规格 |\n"
        )
        layer = cross_audit.audit(docling, md)
        warns = [f.what for f in layer.findings if f.severity == model.WARN]
        self.assertFalse(any("S5735-L24T4X" in w for w in warns), warns)

    def test_model_number_outside_tables_is_not_warned(self):
        """型号只出现在正文段落里也算没丢。

        真数据上踩过：LSH7MPUAX1C0 在 markitdown 输出里出现三次，全在表格外的
        段落里。只搜表格块会报假警，所以这一项比的是整份输出。
        """
        docling = [{
            "idx": 0, "num_rows": 2, "num_cols": 2,
            "cells": [_cell("编码", 0, 0), _cell("说明", 0, 1),
                      _cell("LSH7MPUAX1C0", 1, 0), _cell("主控板", 1, 1)],
        }]
        md = (
            "| 编码 | 说明 |\n| --- | --- |\n| 见正文 | 主控板 |\n\n"
            "上表这块主控板对应 LSH7MPUAX1C0，另见附录。\n"
        )
        layer = cross_audit.audit(docling, md)
        warns = [f.what for f in layer.findings if f.severity == model.WARN]
        self.assertFalse(any("LSH7MPUAX1C0" in w for w in warns), warns)

    def test_data_row_gap_is_record_only(self):
        """数据行数不同只记，不拦也不警。碎片合并策略不同本来就会差行。"""
        docling = [{
            "idx": 0, "num_rows": 6, "num_cols": 2,
            "cells": [_cell("项目", 0, 0), _cell("规格", 0, 1),
                      _cell("甲", 1, 0), _cell("乙", 2, 0)],
        }]
        md = "| 项目 | 规格 |\n| --- | --- |\n| 甲 | 见上 |\n"
        layer = cross_audit.audit(docling, md)
        self.assertEqual(layer.count(model.BLOCKER), 0)
        self.assertEqual(layer.count(model.WARN), 0)
        self.assertGreaterEqual(layer.count(model.INFO), 1)


if __name__ == "__main__":
    unittest.main()
