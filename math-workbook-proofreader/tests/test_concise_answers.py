"""Visible answers use reviewed corrections while original receipts stay immutable."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_review import concise_answers


class FakeRun:
    def questions(self):
        return {qid: {'targets': [{'document': 'body', 'page': 1, 'bbox': None}]}
                for qid in ('corrected', 'manual', 'missing', 'ordinary')}

    def mapped(self, stage):
        answer = lambda v: [{'value': v, 'unit': ''}]
        if stage == 'independent':
            return {'corrected': {'status': 'ok', 'answer': answer('4')},
                    'manual': {'status': 'uncertain', 'answer': answer('6')},
                    'ordinary': {'status': 'ok', 'answer': answer('1/2')}}
        return {'corrected': {'status': 'ok', 'outcome': 'cleared', 'corrected_independent_answer': answer('3')},
                'manual': {'status': 'ok', 'outcome': 'manual', 'corrected_independent_answer': answer('7')}}


class ConciseTests(unittest.TestCase):
    def test_correction_and_incomplete_remain_distinguishable(self):
        run = FakeRun()
        rows = {r['id']: r for r in concise_answers(run)}
        self.assertEqual(rows['corrected']['answer'][0]['value'], '3')
        self.assertTrue(rows['corrected']['corrected'])
        self.assertEqual(run.mapped('independent')['corrected']['answer'][0]['value'], '4')
        self.assertEqual(rows['manual']['answer'][0]['value'], '6')
        self.assertEqual(rows['manual']['status'], 'pending')
        self.assertEqual(rows['missing']['status'], 'missing')
        self.assertEqual(rows['ordinary']['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
