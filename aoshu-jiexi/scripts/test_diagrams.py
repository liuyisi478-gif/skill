from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image
from docx import Document
from lxml import etree

from draw_math_diagram import render, SVG
from export_docx import export, validate_docx, NS
from test_export_docx import source


class DiagramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/'diagram.png'
        self.docx = self.root/'out.docx'
        self.scene = {'size':[400,300], 'scale':2,
                      'points':{'A':[40,220], 'B':[360,220], 'C':[200,60]},
                      'items':[{'type':'polygon','points':['A','B','C']},
                               {'type':'line','from':'C','to':[200,220],'dash':[8,5]},
                               {'type':'label','at':[200,30],'text':'C','anchor':'center'}],
                      'constraints':[{'type':'perpendicular','points':['A','B','C',[200,220]]}]}

    def test_png_and_vector_source_preserve_geometry(self):
        stats=render(self.scene,self.image)
        self.assertEqual(stats['constraints_checked'],1)
        with Image.open(self.image) as image:
            self.assertEqual(image.size,(800,600))
        svg=ET.parse(self.image.with_suffix('.svg')).getroot()
        lines=svg.findall('{'+SVG+'}line')
        self.assertEqual(len(lines),4)
        auxiliary=lines[-1]
        self.assertEqual((auxiliary.get('x1'),auxiliary.get('y1'),auxiliary.get('x2'),auxiliary.get('y2')),('200','60','200','220'))
        self.assertEqual(auxiliary.get('stroke-dasharray'),'8,5')

    def test_incorrect_geometric_constraint_rejected(self):
        self.scene['constraints']=[{'type':'on_segment','points':['C','A','B']}]
        with self.assertRaisesRegex(ValueError,'constraint failed'):
            render(self.scene,self.image)
        self.assertFalse(self.image.exists())

    def test_clipped_labels_rejected(self):
        self.scene['items']=[{'type':'label','at':[395,30],'text':'标签在边界外'}]
        with self.assertRaisesRegex(ValueError,'clipped'):
            render(self.scene,self.image)

    def test_formula_screenshots_cannot_be_hidden_in_labels(self):
        self.scene['items']=[{'type':'label','at':[80,30],'text':r'$\frac{1}{2}$'}]
        with self.assertRaisesRegex(ValueError,'editable formulas'):
            render(self.scene,self.image)

    def test_unknown_primitive_and_missing_point_rejected(self):
        self.scene['items']=[{'type':'mystery'}]
        with self.assertRaises(ValueError):
            render(self.scene,self.image)
        self.scene['items']=[{'type':'line','from':'A','to':'missing'}]
        with self.assertRaises(KeyError):
            render(self.scene,self.image)

    def test_missing_required_diagram_blocks_export(self):
        data=source()
        data['sections'][0]['questions'][0]['diagram_required']=True
        with self.assertRaisesRegex(ValueError,'Required solution diagram'):
            export(data,self.docx)

    def test_multiple_diagrams_embedded_at_the_correct_steps(self):
        render(self.scene,self.image)
        data=source()
        q=data['sections'][0]['questions'][0]
        q['paragraphs'].append('图后的第二步。')
        q['diagram_required']=True
        q['diagrams']=[{'path':self.image.name,'caption':'第一图','after_paragraph':0},
                       {'path':self.image.name,'caption':'第二图','after_paragraph':1,'width_cm':8}]
        stats=export(data,self.docx,self.root)
        self.assertEqual(stats['diagrams'],2)
        doc=Document(self.docx)
        text=[p.text if not p._p.findall('.//{'+NS['w']+'}drawing') else '[IMAGE]' for p in doc.paragraphs]
        self.assertLess(text.index('第一图'),text.index('图后的第二步。'))
        self.assertLess(text.index('图后的第二步。'),text.index('第二图'))
        self.assertEqual(len(doc.inline_shapes),2)
        intro=next(p for p in doc.paragraphs if '【解析】' in p.text)
        self.assertTrue(intro.paragraph_format.keep_with_next)
        self.assertEqual(stats['formulas'],1)

    def test_missing_image_preserves_prior_output(self):
        self.docx.write_bytes(b'existing')
        data=source()
        data['sections'][0]['questions'][0]['diagrams']=[{'path':'missing.png'}]
        with self.assertRaisesRegex(ValueError,'does not exist'):
            export(data,self.docx,self.root)
        self.assertEqual(self.docx.read_bytes(),b'existing')

    def test_invalid_placement_and_width_rejected(self):
        for diagram in ({'path':'x.png','after_paragraph':8}, {'path':'x.png','width_cm':18}):
            data=source()
            data['sections'][0]['questions'][0]['diagrams']=[diagram]
            with self.assertRaises(ValueError):
                export(data,self.docx)

    def test_legacy_figure_still_embedded(self):
        render(self.scene,self.image)
        data=source()
        data['sections'][0]['questions'][0].update(figure=str(self.image),figure_caption='原字段图')
        self.assertEqual(export(data,self.docx)['diagrams'],1)

    def test_missing_packaged_media_detected(self):
        render(self.scene,self.image)
        data=source()
        data['sections'][0]['questions'][0]['diagrams']=[{'path':str(self.image)}]
        export(data,self.docx)
        with ZipFile(self.docx) as z:
            root=etree.fromstring(z.read('word/document.xml'))
            expected=[deepcopy(e) for e in root.findall('.//m:oMath',NS)]
            entries={n:z.read(n) for n in z.namelist() if not n.startswith('word/media/')}
        with ZipFile(self.docx,'w',ZIP_DEFLATED) as z:
            for n,content in entries.items():
                z.writestr(n,content)
        with self.assertRaises((ValueError,KeyError)):
            validate_docx(self.docx,expected,1)


if __name__=='__main__':
    unittest.main()
