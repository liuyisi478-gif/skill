"""Real PDF smoke tests. Small explicitly synthetic PDFs generated with stdlib only."""
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_pdf import prepare
from audit_run import read


def synthetic_pdf(path, scanned=False):
    # For image-only PDF use a literal two-pixel gray image, no hidden text layer.
    stream = b'q 200 0 0 200 50 450 cm /Im0 Do Q' if scanned else b'BT /F1 18 Tf 50 700 Td (SIMULATED Q1: 2 + 3 = ?) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> /XObject << /Im0 6 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Type /XObject /Subtype /Image /Width 2 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 2 >>\nstream\n\x00\xff\nendstream']
    result = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result)); result += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(result)
    result += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]: result += f'{offset:010} 00000 n \n'.encode()
    result += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    path.write_bytes(result)


@unittest.skipUnless(shutil.which('pdftoppm'), 'Poppler unavailable')
class PrepareTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / 'work'; scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def test_real_render_resume_and_input_change(self):
        pdf = self.root / 'SIMULATED.pdf'; synthetic_pdf(pdf)
        work = self.root / 'prepared'
        prepare(pdf, None, work, 1)
        manifest = read(work / 'manifest.json')
        page = work / manifest['documents'][0]['pages'][0]['work_image']
        stamp = page.stat().st_mtime_ns
        prepare(pdf, None, work, 1)
        self.assertEqual(stamp, page.stat().st_mtime_ns)
        self.assertTrue(manifest['audit_required'])
        self.assertFalse(manifest['documents'][0]['pages'][0]['likely_scanned'])
        pdf.write_bytes(pdf.read_bytes() + b'\n% changed')
        with self.assertRaises(ValueError): prepare(pdf, None, work, 1)

    def test_image_only_page_is_not_skipped(self):
        pdf = self.root / 'SIMULATED-SCAN.pdf'; synthetic_pdf(pdf, scanned=True)
        work = self.root / 'prepared'; prepare(pdf, None, work, 1)
        manifest = read(work / 'manifest.json')
        page = manifest['documents'][0]['pages'][0]
        self.assertTrue(page['likely_scanned'])
        self.assertEqual(page['extracted_characters'], 0)
        image = work / page['work_image']
        self.assertTrue(image.is_file())
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), page['image_sha256'])


if __name__ == '__main__': unittest.main()
