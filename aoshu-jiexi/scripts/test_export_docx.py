"""Behavioral DOCX and formula regression tests; no renderer is assumed."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from lxml import etree

from export_docx import export, MathParser, NS, validate_docx


def question(number='1', answer='C'):
    return {'number': number, 'answer': answer,
            'paragraphs': ['**' + number + '. ' + answer + '【解析】** ' + r'$12\div4=3$。'],
            'taxonomy': '归一归总'}


def source(kind='choice', qs=None):
    return {'title': '试验卷解析', 'sections': [{'label': '三、' + ('选择题' if kind == 'choice' else '填空题'),
            'kind': kind, 'questions': qs or [question()]}]}


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'out.docx'

    def xml(self):
        with ZipFile(self.path) as z:
            return etree.fromstring(z.read('word/document.xml'))

    def test_roundtrip_native_fraction_and_subscripts(self):
        answer = r'$\frac{9}{4}$'
        data = source('fill', [question(answer=answer)])
        data['sections'][0]['questions'][0]['paragraphs'] = [r'**1. $\frac{9}{4}$【解析】** $S_{BCD}=3^2\div4=\frac{9}{4}$。']
        stats = export(data, self.path)
        self.assertEqual(stats['formulas'], 3)
        self.assertEqual(stats['fractions'], 3)
        root = self.xml()
        frac = root.find('.//m:f', NS)
        self.assertEqual(''.join(frac.find('m:num', NS).itertext()), '9')
        self.assertEqual(''.join(frac.find('m:den', NS).itertext()), '4')
        self.assertTrue(root.findall('.//m:sSub', NS))
        self.assertTrue(root.findall('.//m:sSup', NS))
        self.assertFalse(any('$' in t for t in root.xpath('//w:t/text()', namespaces=NS)))
        self.assertEqual(len(Document(self.path).tables), 1)
        self.assertFalse(Document(self.path).styles['Title']._element.findall('.//' + '{' + NS['w'] + '}pBdr'))

    def test_one_frame_with_major_and_minor_numbers(self):
        export(source(qs=[question('6', 'A'), question('7', 'D')]), self.path)
        doc = Document(self.path)
        table = doc.tables[0]
        self.assertEqual(len(table.columns), 1)
        self.assertEqual(len(table.rows), 2)
        self.assertIn('三、选择题', table.cell(0, 0).text)
        self.assertIn('6～7 AD', table.cell(0, 0).text)
        self.assertNotIn('填空', table.cell(0, 0).text)
        self.assertNotIn('第 6 题', '\n'.join(p.text for p in doc.paragraphs))

    def test_nonconsecutive_choice_has_explicit_numbers(self):
        export(source(qs=[question('2', 'A'), question('4', 'D')]), self.path)
        text = Document(self.path).tables[0].cell(0, 0).text
        self.assertIn('2.', text)
        self.assertIn('4.', text)
        self.assertNotIn('～', text)

    def test_multiple_choice_has_explicit_numbers(self):
        q = question(answer='AC')
        q['multiple'] = True
        export(source(qs=[q]), self.path)
        self.assertIn('1.', Document(self.path).tables[0].cell(0, 0).text)

    def test_no_objective_omits_whole_quick_table(self):
        data = source('solution')
        data['sections'][0]['questions'][0]['paragraphs'] = [r'1. 解：$12\div4=3$（本）。', '答：3本。']
        export(data, self.path)
        doc = Document(self.path)
        self.assertEqual(len(doc.tables), 0)
        self.assertNotIn('快速对答案', '\n'.join(p.text for p in doc.paragraphs))

    def test_duplicate_minor_numbers_allowed_across_sections(self):
        data = source()
        fill = deepcopy(data['sections'][0])
        fill.update(label='五、填空题', kind='fill')
        fill['questions'] = [question(answer='3')]
        data['sections'].append(fill)
        export(data, self.path)
        text = Document(self.path).tables[0].cell(0, 0).text
        self.assertIn('三、选择题', text)
        self.assertIn('五、填空题', text)

    def test_duplicate_number_within_section_rejected(self):
        with self.assertRaises(ValueError):
            export(source(qs=[question(), question()]), self.path)

    def test_disagreeing_body_answer_rejected(self):
        data = source()
        data['sections'][0]['questions'][0]['answer'] = 'D'
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            export(data, self.path)

    def test_unknown_math_preserves_existing_output(self):
        self.path.write_bytes(b'existing')
        data = source()
        data['sections'][0]['questions'][0]['paragraphs'].append(r'$\unsupported{4}$')
        with self.assertRaises(ValueError):
            export(data, self.path)
        self.assertEqual(self.path.read_bytes(), b'existing')

    def test_native_nested_fraction_and_combined_scripts(self):
        root = MathParser(r'\frac{1}{\frac{2}{3}}+S_{ABC}^2').parse()
        self.assertEqual(len(root.findall('.//m:f', NS)), 2)
        self.assertEqual(len(root.findall('.//m:sSubSup', NS)), 1)

    def test_malformed_formulas_fail(self):
        for formula in ('', r'\frac{1}', r'\frac{}{2}', r'a_{b', r'a}}', r'^2', r'x_1_2', r'\sqrt{4}', '中文'):
            with self.subTest(formula=formula), self.assertRaises(ValueError):
                MathParser(formula).parse()

    def test_unclosed_inline_math_fails(self):
        data = source()
        data['sections'][0]['questions'][0]['paragraphs'].append('遗漏 $1+2')
        with self.assertRaises(ValueError):
            export(data, self.path)

    def test_static_page_number_rejected(self):
        data = source()
        data['quick_note'] = '解答题请看详解 P66'
        with self.assertRaises(ValueError):
            export(data, self.path)

    def test_unresolved_answer_is_not_invented(self):
        data = source()
        data['sections'][0]['questions'][0].update(answer=None, paragraphs=['**1.【题目核查】** 选项不清，需补图。'])
        export(data, self.path)
        self.assertIn('待核', Document(self.path).tables[0].cell(0, 0).text)

    def test_quality_document_has_no_student_extras(self):
        data = source()
        data['mode'] = 'qa'
        export(data, self.path)
        doc = Document(self.path)
        self.assertEqual(len(doc.tables), 0)
        self.assertNotIn('【题型归类】', '\n'.join(p.text for p in doc.paragraphs))

    def test_modified_math_detected_after_packaging(self):
        export(source(), self.path)
        root = self.xml()
        expected = [deepcopy(e) for e in root.findall('.//m:oMath', NS)]
        root.find('.//m:t', NS).text = '9'
        with ZipFile(self.path) as z:
            entries = {name: z.read(name) for name in z.namelist()}
        entries['word/document.xml'] = etree.tostring(root)
        with ZipFile(self.path, 'w', ZIP_DEFLATED) as z:
            for name, content in entries.items():
                z.writestr(name, content)
        with self.assertRaisesRegex(ValueError, 'inventory'):
            validate_docx(self.path, expected)


if __name__ == '__main__':
    unittest.main()
