"""Run format-linter regression checks: python scripts/test_lint_md.py."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LINTER = Path(__file__).with_name('lint_md.py')


class FormatTests(unittest.TestCase):
    def lint(self, section, body, title='第 1 题'):
        text = '# 测试卷\n\n## 快速对答案\n1. 36\n\n### ' + section + '\n\n## ' + title + '\n\n' + body + '\n\n**【题型归类】** 归一归总\n'
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'sample.md'
            f.write_text(text, encoding='utf-8')
            return subprocess.run([sys.executable, '-X', 'utf8', str(LINTER), str(f), '--strict'], capture_output=True, text=True, encoding='utf-8')

    def ok(self, section, body, title='第 1 题'):
        r = self.lint(section, body, title)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def bad(self, section, body, message):
        r = self.lint(section, body)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(message, r.stdout)

    def test_fill_inline(self):
        self.ok('一、填空题', r'**36【解析】** 面积为 $12\times3=36$（平方厘米）。')

    def test_choice_inline(self):
        self.ok('二、选择题', '**C【解析】** 按比例计算，选C。')

    def test_fill_separated(self):
        self.bad('一、填空题', '**36**\n\n**【解析】** 按比例计算。', '答案须与【解析】同一行')

    def test_choice_separated_even_without_empty_line(self):
        self.bad('二、选择题', '**C**\n**【解析】** 按比例计算。', '答案须与【解析】同一行')

    def test_vertical_calculation(self):
        self.ok('三、计算题', '解：\n\n$3.6\\times(98+2)$  \n$=3.6\\times100$  \n$=360$')

    def test_vertical_equation(self):
        self.ok('三、解方程', '解：\n\n$3x=6$  \n$x=6\\div3$  \n$x=2$')

    def test_missing_hard_line_break(self):
        self.bad('三、计算题', '解：\n\n$3+3$\n$=6$', '行末保留两个空格')

    def test_calculation_table(self):
        self.bad('三、计算题', '解：\n\n| 等号 | 过程 |\n|---|---|\n| $=$ | $360$ |', '计算过程禁止使用表格')

    def test_html_calculation_table(self):
        self.bad('三、计算题', '解：\n<table><tr><td>360</td></tr></table>', '计算过程禁止使用表格')

    def test_calculation_code_block(self):
        self.bad('三、计算题', '解：\n```\n3+3=6\n```', '计算过程禁止放入代码块')

    def test_statistics_table_allowed(self):
        self.ok('四、解决问题', '解：统计如下。\n\n| 组别 | 人数 |\n|---|---|\n| A | 12 |\n\n答：共有12人。')

    def test_narrative_and_answer_units(self):
        self.ok('四、解答题', r'解：长12厘米、宽3厘米，面积为 $12\times3=36$（平方厘米）。' + '\n\n答：面积为36平方厘米。')

    def test_naked_formula_unit(self):
        self.bad('一、填空题', r'**36【解析】** 面积为 $12\times3=36$ 平方厘米。', '单位须置于公式外的全角括号')

    def test_naked_plain_unit(self):
        self.bad('一、填空题', '**36【解析】** 面积12×3=36平方厘米。', '单位未加全角括号')

    def test_each_result_needs_unit_brackets(self):
        self.bad('四、解答题', r'解：面积 $12\times3=36$（平方厘米），周长 $(12+3)\times2=30$ 厘米。', '单位须置于公式外的全角括号')

    def test_latex_unit_inside_result(self):
        self.bad('一、填空题', r'**36【解析】** $12\times3=36\mathrm{cm}^2$。', '单位须移到公式外')

    def test_percentage_ratio_angle_no_extra_unit(self):
        self.ok('二、选择题', r'**C【解析】** $1\div4=25\%$；$6:4=3:2$；$180^\circ\div2=90^\circ$。')

    def test_existing_forbidden_environment(self):
        self.bad('三、计算题', r'解：\begin{aligned}x=2\end{aligned}', '不允许 LaTeX 环境')

    def test_missing_taxonomy_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'sample.md'
            f.write_text('## 快速对答案\n\n### 一、填空\n## 第 1 题\n**6【解析】** 直接计算。', encoding='utf-8')
            r = subprocess.run([sys.executable, '-X', 'utf8', str(LINTER), str(f)], capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('缺少【题型归类】', r.stdout)


if __name__ == '__main__':
    unittest.main()
