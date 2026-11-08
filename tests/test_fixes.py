"""判据修复的回归用例 + 四条原本零覆盖的 BLOCKER 判据。

2026-11-08 三个独立审查员报出来、我自己复现过的错，每条一个用例。
前七条是「现在就是错的」，后四条是「实现是对的但没有任何测试守着」。
"""

import unittest

from docqa_audit import model
from docqa_audit.auditors import claim_audit, cross_audit, parse_audit


def _cl(t, r, c, header=True):
    return dict(text=t, row=[r, r + 1], col=[c, c + 1],
                column_header=header, row_header=False)


class FalseAlarmTest(unittest.TestCase):
    """真误拦：好资料被判不可交付。"""

    def test_total_row_is_not_sequence_break(self):
        md = ("| 序号 | 名称 | 金额 |\n| --- | --- | --- |\n"
              "| 1 | 配电箱 | 300 |\n| 2 | 按钮箱 | 200 |\n| 合计 |  | 500 |\n")
        self.assertEqual(parse_audit.audit(md).count(model.BLOCKER), 0)

    def test_header_substring_is_the_same_field(self):
        dl = [dict(num_rows=2, num_cols=2,
                   cells=[_cl("设备名称及规格型号", 0, 0), _cl("数量", 0, 1),
                          _cl("AL-01", 1, 0), _cl("3", 1, 1)])]
        md = "| 设备名称 | 数量 |\n| --- | --- |\n| AL-01 | 3 |\n"
        self.assertEqual(cross_audit.audit(dl, md).count(model.BLOCKER), 0)

    def test_escaped_pipe_is_not_column_mismatch(self):
        pipe = "\\|"
        md = ("| 序号 | 名称 | 备注 |\n| --- | --- | --- |\n"
              f"| 1 | 配电箱 | 规格{pipe}型号见附页 |\n| 2 | 按钮箱 | 无 |\n")
        self.assertEqual(parse_audit.audit(md).count(model.BLOCKER), 0)

    def test_code_regex_does_not_swallow_chinese(self):
        l = claim_audit.audit("S5735-L24T4X交换机共 3 台。", "交换机S5735-L24T4X，共 3 台。")
        self.assertEqual(l.count(model.BLOCKER), 0)

    def test_short_table_without_numeric_column_is_not_blocked(self):
        md = ("| 项目 | 描述 |\n| --- | --- |\n"
              "| 基本功能 | 二层转发 |\n| 高级功能 | 三层转发 |\n| 扩展 | 堆叠 |\n")
        self.assertEqual(parse_audit.audit(md).count(model.BLOCKER), 0)


class MissedErrorTest(unittest.TestCase):
    """真漏放：错的东西被放过去。"""

    def test_number_1500_is_not_found_inside_15000(self):
        l = claim_audit.audit("共1500", "共15000")
        self.assertEqual(l.count(model.WARN), 1)
        self.assertEqual(l.count(model.BLOCKER), 0)

    def test_dropped_whole_table_is_warned(self):
        dl = [dict(num_rows=2, num_cols=2,
                   cells=[_cl("型号", 0, 0), _cl("数量", 0, 1),
                          _cl("S5735-L24T4X", 1, 0), _cl("3 台", 1, 1)]),
              dict(num_rows=2, num_cols=2,
                   cells=[_cl("板卡", 0, 0), _cl("编码", 0, 1),
                          _cl("主控板", 1, 0), _cl("LSH7MPUAX1C0", 1, 1)])]
        md = "| 型号 | 数量 |\n| --- | --- |\n| S5735-L24T4X | 3 台 |\n"
        self.assertGreaterEqual(cross_audit.audit(dl, md).count(model.WARN), 1)

    def test_table_count_gap_says_it_out_loud(self):
        dl = [_cl("型号", 0, 0), _cl("数量", 0, 1)]
        tables = [dict(num_rows=2, num_cols=2,
                       cells=[_cl("型号", 0, 0), _cl("数量", 0, 1),
                              _cl("A1", 1, 0), _cl("3", 1, 1)]),
                  dict(num_rows=2, num_cols=2,
                       cells=[_cl("板卡", 0, 0), _cl("编码", 0, 1),
                              _cl("主控板", 1, 0), _cl("B2", 1, 1)])]
        md = "| 型号 | 数量 |\n| --- | --- |\n| A1 | 3 |\n"
        text = " ".join(f.what for f in cross_audit.audit(tables, md).findings)
        self.assertIn("张数不同", text)


class ZeroCoverageTest(unittest.TestCase):
    """实现是对的，但没有任何测试守着。改坏了 27 个用例照样全绿。"""

    def test_fabricated_code_is_blocker(self):
        l = claim_audit.audit("型号 FCS2-1001，数量 3 台。", "型号 FCS9-9999，数量 3 台。")
        self.assertEqual(l.count(model.BLOCKER), 1)

    def test_fabricated_date_is_blocker(self):
        l = claim_audit.audit("合同签订于 2026-10-19。", "合同签订于 2025-10-19。")
        self.assertEqual(l.count(model.BLOCKER), 1)

    def test_sequence_break_requires_a_numeric_column(self):
        # 首列一个数字都没有的表，不该被判「序号断行」
        md = ("| 项目 | 描述 |\n| --- | --- |\n"
              "| 甲 | 一 |\n| 乙 | 二 |\n| 丙 | 三 |\n")
        self.assertEqual(parse_audit.audit(md).count(model.BLOCKER), 0)

    def test_parse_summary_counts_data_rows_without_header(self):
        md = ("| 序号 | 名称 |\n| --- | --- |\n| 1 | 甲 |\n| 2 | 乙 |\n")
        self.assertEqual(parse_audit.audit(md).summary["数据行"], 2)
