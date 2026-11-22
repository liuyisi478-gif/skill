"""SIMULATED stage submissions, not model-accuracy tests. Standard library only."""
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_run import Run, digest, equivalent, rational, read, write, check_statement
from build_review import build, validate, validate_bbox

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGoQAAAAASUVORK5CYII=')

CASES = [
    # id, scenario, independent, source final, steps, final classification
    ('Q1', 'both_correct', '5', '5', ['2+3=5'], 'none'),
    ('Q2', 'wrong_final', '5', '6', ['2+3=6'], 'confirmed'),
    ('Q3', 'correct_final_bad_step', '5', '5', ['2+3=6', '最终答案5'], 'confirmed'),
    ('Q4', 'wrong_AI_correct_source', '6', '5', ['2+3=5'], 'none'),
    ('Q5', 'decimal_fraction_symbol_unclear', '0.5', '5', ['数字不清'], 'suspected'),
    ('Q6', 'question_number_mismatch', '5', '5', [], 'suspected'),
    ('Q7', 'diagram_conflicts_with_stem', '12', '12', ['3×4=12'], 'confirmed'),
    ('Q8', 'ambiguous_stem', '5', '5', ['另一理解可能不同'], 'suspected'),
    ('Q9', 'cross_page_question', '5', '5', ['2+3=5'], 'none'),
    ('Q10', 'equivalent_forms', '2/4', '0.5', ['1/2=0.5'], 'none'),
]


class Fixture:
    def __init__(self, root, count=10):
        self.root = Path(root)
        self.cases = CASES[:count]
        docs = []
        for docid in ('body', 'answer'):
            pages = []
            for n in (1, 2):
                work_image = f'{docid}/pages/page-{n:04}.png'
                image = self.root / work_image
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_bytes(PNG)
                pages.append({'page': n, 'work_image': work_image, 'image': f'pages/{docid}/page-{n:04}.png',
                              'image_sha256': hashlib.sha256(PNG).hexdigest(), 'width': 600, 'height': 800})
            docs.append({'id': docid, 'label': docid, 'source_name': 'SIMULATED.pdf', 'source_sha256': docid,
                         'page_count': 2, 'pages': pages})
        write(self.root / 'manifest.json', {'version': 2, 'audit_required': True, 'documents': docs, 'page_count': 4})

    def target(self, doc='body', page=1):
        return {'document': doc, 'page': page, 'bbox': {'x': 0.1, 'y': 0.1, 'width': 0.8, 'height': 0.1}}

    def view(self, target):
        return dict(target, image_sha256=hashlib.sha256(PNG).hexdigest(), tool_ref='SIMULATED-no-real-vision-call')

    def inventory(self):
        rows = []
        for qid, scenario, ai, answer, steps, classification in self.cases:
            targets = [self.target()]
            if qid == 'Q9':
                targets.append(self.target(page=2))
            rows.append({'id': qid, 'status': 'uncertain' if qid in ('Q5', 'Q8') else 'ok',
                'uncertainties': [scenario] if qid in ('Q5', 'Q8') else [], 'section': '模拟', 'number': qid,
                'stem': scenario, 'type': '模拟测试', 'options': [], 'figures': ['标注3×5，题干3×4'] if qid == 'Q7' else [],
                'complex_figure': qid == 'Q7', 'targets': targets, 'views': [self.view(t) for t in targets]})
        return {'records': rows, 'pages': self.pages(rows, ('body',))}

    def pages(self, rows, docs=('body', 'answer')):
        pages = []
        for doc in docs:
            for n in (1, 2):
                ids = [r['id'] for r in rows if any(t['document'] == doc and t['page'] == n for t in r['targets'])
                       and r.get('match', 'matched') == 'matched']
                pages.append({'document': doc, 'page': n, 'printed_page': str(n), 'role': doc,
                    'question_ids': ids, 'anomalies': [], 'unmatched_answers': [],
                    'reason': 'SIMULATED empty page' if not ids else '', 'views': [self.view(self.target(doc, n))]})
        return pages

    def independent(self, case):
        qid, scenario, ai, answer, steps, classification = case
        return {'id': qid, 'status': 'ok', 'uncertainties': [], 'answer': [{'value': ai, 'unit': ''}],
                'reasoning': 'SIMULATED supplied reasoning: ' + ai,
                'body_checks': {key: '模拟检查依据' for key in ('language', 'conditions', 'figure', 'ambiguity', 'units')}}

    def answers(self):
        rows = []
        for qid, scenario, ai, answer, steps, classification in self.cases:
            rows.append({'id': qid, 'status': 'uncertain' if qid == 'Q6' else 'ok',
                'uncertainties': ['原题号Q60，不能可靠对应Q6'] if qid == 'Q6' else [],
                'match': 'ambiguous' if qid == 'Q6' else 'matched', 'match_reason': scenario,
                'answer_id': 'A-' + qid, 'answer_number': 'Q60' if qid == 'Q6' else qid,
                'source_answer': answer, 'source_steps': steps, 'answer': [{'value': answer, 'unit': ''}],
                'targets': [self.target('answer')], 'views': [self.view(self.target('answer'))]})
        return {'records': rows, 'pages': self.pages(rows)}

    def audit(self, case):
        qid, scenario, ai, answer, steps, classification = case
        return {'id': qid, 'status': 'uncertain' if qid == 'Q6' else 'ok',
            'uncertainties': ['无法匹配'] if qid == 'Q6' else [], 'reasoning': 'SIMULATED step review',
            'steps': [{'source': s, 'verdict': 'invalid' if s == '2+3=6' else 'valid', 'reason': '模拟原稿逐步验算'} for s in steps],
            'final_check': '模拟结果检查' if qid != 'Q6' else '', 'grade_check': '小学加法'}

    def issue(self, qid, classification):
        return {'questionId': qid, 'kind': classification, 'category': '模拟问题', 'title': '模拟测试批注',
                'detail': '模拟原文和证据', 'suggestion': '模拟修改建议', 'targets': [self.target(), self.target('answer')]}

    def comparison(self, case):
        qid, scenario, ai, answer, steps, classification = case
        return {'id': qid, 'status': 'ok', 'uncertainties': [], 'reasoning': scenario,
            'answer_vs_solution': '模拟比较', 'derivation': '模拟推导核查', 'conditions_vs_figure': '模拟图文核查',
            'review_reasons': [scenario] if classification != 'none' else [],
            'issues': [self.issue(qid, 'suspected')] if classification != 'none' else [], 'structure_review': []}

    def recheck(self, case):
        qid, scenario, ai, answer, steps, classification = case
        qs = Run(self.root).questions()
        targets = qs[qid]['targets'] + ([self.target('answer')] if qid != 'Q6' else [])
        return {'id': qid, 'status': 'ok', 'uncertainties': [], 'reasoning': scenario,
            'views': [self.view(t) for t in targets], 'verification': 'SIMULATED independent verification',
            'outcome': 'cleared' if classification == 'none' else 'manual' if classification == 'suspected' else 'confirmed',
            'corrected_independent_answer': [{'value': '5', 'unit': ''}] if qid == 'Q4' else None,
            'issues': [] if classification == 'none' else [self.issue(qid, classification)]}

    def submit(self, stage, result, ids=None):
        run = Run(self.root)
        packet = run.packet(stage, ids)
        path = self.root / 'result.json'
        write(path, result)
        run.commit(self.root / 'packets' / (packet['token'] + '.json'), path)
        return packet

    def through(self, stage):
        self.submit('inventory', self.inventory())
        if stage == 'inventory': return
        for i in range(0, len(self.cases), 4):
            batch = self.cases[i:i+4]
            self.submit('independent', {'records': [self.independent(c) for c in batch]}, [c[0] for c in batch])
        if stage == 'independent': return
        self.submit('answer_inventory', self.answers())
        if stage == 'answer_inventory': return
        for i in range(0, len(self.cases), 4):
            batch = self.cases[i:i+4]
            self.submit('answer_audit', {'records': [self.audit(c) for c in batch]}, [c[0] for c in batch])
        if stage == 'answer_audit': return
        for i in range(0, len(self.cases), 4):
            batch = self.cases[i:i+4]
            self.submit('comparison', {'records': [self.comparison(c) for c in batch]}, [c[0] for c in batch])
        if stage == 'comparison': return
        for case in self.cases:
            if Run(self.root).risk(case[0]):
                self.submit('recheck', {'records': [self.recheck(case)]}, [case[0]])


class AuditTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / 'work'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.f = Fixture(Path(self.temp.name) / 'run')

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_equivalence_and_unknown(self):
        def answer(value, unit=''): return [{'value': value, 'unit': unit}]
        for a, b in [('2/4','0.5'), ('1/3+1/6','50%'), ('０.１＋0.2','0.3'), ('−2×3','-6')]:
            self.assertEqual(equivalent(answer(a), answer(b)), 'equal')
        self.assertEqual(equivalent(answer('2'), answer('3')), 'different')
        self.assertEqual(equivalent(answer('1','m'), answer('100','cm')), 'unknown')
        self.assertEqual(equivalent(answer('x+1'), answer('1+x')), 'unknown')
        for expression in ["__import__('os')", '2**1000000', '1/0', '9'*1300, '1e999999999999']:
            with self.assertRaises((ValueError, SyntaxError, ZeroDivisionError)):
                rational(expression)

    def test_inventory_cannot_skip_page_or_cross_page(self):
        for mutate in ('page', 'cross', 'view'):
            result = self.f.inventory()
            if mutate == 'page': result['pages'].pop()
            elif mutate == 'cross': result['pages'][1]['question_ids'] = []
            else: result['records'][0]['views'] = []
            with self.assertRaises(ValueError): self.f.submit('inventory', result)

    def test_program_finds_bad_middle_link_even_if_final_correct(self):
        self.assertEqual(check_statement('2+3=6=5')['result'], 'invalid')
        self.assertEqual(check_statement('1/2+1/4=0.75=3/4')['result'], 'valid')
        self.assertEqual(check_statement('约为0.3')['result'], 'unknown')
        self.f.through('answer_inventory')
        row = self.f.audit(CASES[2])
        for step in row['steps']: step['verdict'] = 'valid'  # Deliberately wrong model verdict.
        self.f.submit('answer_audit', {'records': [row]}, ['Q3'])
        self.assertIn('program_arithmetic_error', Run(self.f.root).risk('Q3'))

    def test_answer_not_visible_before_independent(self):
        self.f.through('inventory')
        with self.assertRaises(ValueError): Run(self.f.root).packet('answer_inventory')
        packet = Run(self.f.root).packet('independent', ['Q1'])
        self.assertNotIn('answer_inventory', packet)
        self.assertNotIn('documents', packet)

    def test_cannot_overwrite_or_omit_question_in_batch(self):
        self.f.through('inventory')
        with self.assertRaises(ValueError): self.f.submit('independent', {'records': [self.f.independent(CASES[0])]}, ['Q1', 'Q2'])
        self.f.submit('independent', {'records': [self.f.independent(CASES[0])]}, ['Q1'])
        with self.assertRaises(ValueError): Run(self.f.root).packet('independent', ['Q1'])
        with self.assertRaises(ValueError): Run(self.f.root).packet('independent', ['Q2']*6)

    def test_answer_audit_packet_isolated(self):
        self.f.through('answer_inventory')
        packet = Run(self.f.root).packet('answer_audit', ['Q4'])
        self.assertNotIn('independent', packet)
        self.assertNotIn('numeric_comparison', packet)
        self.assertEqual(packet['answer_inventory'][0]['answer'][0]['value'], '5')

    def test_cannot_skip_intermediate_step(self):
        self.f.through('answer_inventory')
        row = self.f.audit(CASES[2]); row['steps'].pop(0)
        with self.assertRaises(ValueError): self.f.submit('answer_audit', {'records': [row]}, ['Q3'])

    def test_snapshot_and_receipt_tampering_detected(self):
        self.f.through('independent')
        path = self.f.root / 'independent_answers.json'
        data = read(path); data['records'][0]['answer'][0]['value'] = '999'; write(path, data)
        with self.assertRaises(ValueError): Run(self.f.root)
        run = Run(self.f.root, verify_snapshots=False)
        write(path, run.snapshot('independent'))
        Run(self.f.root)
        receipt = self.f.root / run.state['receipts'][0]['result']
        value = read(receipt); value['records'][0]['stem'] = 'tampered'; write(receipt, value)
        with self.assertRaises(ValueError): Run(self.f.root, verify_snapshots=False)

    def test_input_change_rejects_old_run(self):
        self.f.through('inventory')
        path = self.f.root / 'manifest.json'
        m = read(path); m['documents'][0]['source_sha256'] = 'different'; write(path, m)
        with self.assertRaises(ValueError): Run(self.f.root)

    def test_rendered_image_change_rejects_old_run(self):
        self.f.through('inventory')
        (self.f.root / 'body/pages/page-0001.png').write_bytes(b'changed')
        with self.assertRaises(ValueError): Run(self.f.root)

    def test_duplicate_source_numbers_are_structure_findings(self):
        result = self.f.inventory()
        result['records'][1]['number'] = 'Q1'
        self.f.submit('inventory', result)
        self.assertTrue(any(f['id'].startswith('duplicate:') for f in Run(self.f.root).structure_findings()))

    def test_incomplete_export_is_explicit_draft(self):
        self.f.through('inventory')
        with self.assertRaises(ValueError): Run(self.f.root).export()
        review = Run(self.f.root).export(draft=True)
        self.assertEqual(len(review['issues']), 10)
        self.assertTrue(all(i['category'] == '检查未完成' for i in review['issues']))
        self.assertEqual(Run(self.f.root).coverage()['processed'], 0)

    def test_ten_scenarios_end_to_end_simulated(self):
        self.f.through('recheck')
        run = Run(self.f.root)
        review = run.export()
        confirmed = {i['questionId'] for i in review['issues'] if i['kind'] == 'confirmed'}
        suspected = {i['questionId'] for i in review['issues'] if i['kind'] == 'suspected'}
        self.assertEqual(confirmed, {'Q2', 'Q3', 'Q7'})
        self.assertEqual(suspected, {'Q5', 'Q6', 'Q8'})
        self.assertEqual(run.coverage()['processed'], 10)
        self.assertEqual(run.mapped('independent')['Q4']['answer'][0]['value'], '6')
        self.assertEqual(len(run.questions()['Q9']['targets']), 2)
        output = self.f.root.parent / 'html'
        deliverable = self.f.root.parent / 'delivered' / '校对稿.html'
        build(self.f.root, self.f.root / 'review.json', output, ROOT, deliverable)
        html = (output / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(deliverable.read_bytes(), (output / 'index.html').read_bytes())
        self.assertEqual([p.name for p in deliverable.parent.iterdir()], ['校对稿.html'])
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('"concise_answers":', html)
        self.assertIn('"independent_answers":', html)
        # Builder must not allow edited review JSON to bypass receipts.
        review['issues'] = []; write(self.f.root / 'forged.json', review)
        with self.assertRaises(ValueError): build(self.f.root, self.f.root / 'forged.json', output, ROOT)

    def test_no_red_before_recheck(self):
        self.f.through('answer_audit')
        row = self.f.comparison(CASES[1]); row['issues'][0]['kind'] = 'confirmed'
        with self.assertRaises(ValueError): self.f.submit('comparison', {'records': [row]}, ['Q2'])

    def test_failed_solve_remains_incomplete(self):
        self.f = Fixture(self.f.root, count=1)
        self.f.through('inventory')
        row = self.f.independent(CASES[0]); row.update(status='failed', uncertainties=['看不清'], answer=[])
        self.f.submit('independent', {'records': [row]}, ['Q1'])
        self.f.submit('answer_inventory', self.f.answers())
        self.f.submit('answer_audit', {'records': [self.f.audit(CASES[0])]}, ['Q1'])
        self.f.submit('comparison', {'records': [self.f.comparison(CASES[0])]}, ['Q1'])
        row = self.f.recheck(CASES[0]); row.update(outcome='manual')
        self.f.submit('recheck', {'records': [row]}, ['Q1'])
        self.assertFalse(Run(self.f.root).coverage()['records'][0]['complete'])
        with self.assertRaises(ValueError): Run(self.f.root).export()
        with self.assertRaises(ValueError): Run(self.f.root).packet('independent', ['Q1'])

    def test_retry_only_failed_before_downstream_and_preserve_attempt(self):
        self.f.through('inventory')
        row = self.f.independent(CASES[0]); row.update(status='failed', uncertainties=['临时识别失败'], answer=[])
        self.f.submit('independent', {'records': [row]}, ['Q1'])
        self.f.submit('independent', {'records': [self.f.independent(CASES[0])]}, ['Q1'])
        run = Run(self.f.root)
        self.assertEqual(len(run.rows('independent')), 1)
        self.assertEqual(run.mapped('independent')['Q1']['status'], 'ok')
        self.assertEqual(len([r for r in run.state['receipts'] if r['stage'] == 'independent']), 2)
        with self.assertRaises(ValueError): run.packet('independent', ['Q1'])

    def test_body_only_does_not_require_pointless_conflict_recheck(self):
        self.f = Fixture(self.f.root, count=1)
        path = self.f.root / 'manifest.json'
        manifest = read(path); manifest['documents'] = manifest['documents'][:1]; manifest['page_count'] = 2; write(path, manifest)
        self.f.through('independent')
        row = {'id': 'Q1', 'status': 'ok', 'uncertainties': [], 'match': 'not_supplied',
               'match_reason': '只提供正文', 'targets': [self.f.target()]}
        self.f.submit('answer_inventory', {'records': [row], 'pages': self.f.pages([], ('body',))})
        audit = {'id': 'Q1', 'status': 'ok', 'uncertainties': [], 'reasoning': '不适用：无答案', 'steps': []}
        self.f.submit('answer_audit', {'records': [audit]}, ['Q1'])
        self.f.submit('comparison', {'records': [self.f.comparison(CASES[0])]}, ['Q1'])
        run = Run(self.f.root)
        self.assertFalse(run.risk('Q1'))
        self.assertEqual(run.export()['issues'], [])
        self.assertFalse(run.coverage()['records'][0]['answer_checked'])
        self.assertEqual(run.coverage()['records'][0]['steps_mode'], 'not_available')

    def test_bbox_finite_and_same_page_multiple_regions(self):
        for bad in (float('nan'), float('inf')):
            with self.assertRaises(ValueError): validate_bbox(dict(x=bad, y=0, width=.1, height=.1), 1, 1)
        issue = self.f.issue('Q1', 'suspected')
        second = self.f.target(); second['bbox']['y'] = .4
        issue['targets'] = [self.f.target(), second]; issue['id'] = 1
        self.assertEqual(len(validate(Run(self.f.root).manifest, {'issues': [issue]})), 1)

    def test_structure_inverse_review_cannot_be_skipped(self):
        self.f = Fixture(self.f.root, count=1)
        result = self.f.inventory(); result['pages'][0]['anomalies'] = ['疑似跳号']
        self.f.submit('inventory', result)
        self.f.submit('independent', {'records': [self.f.independent(CASES[0])]}, ['Q1'])
        self.f.submit('answer_inventory', self.f.answers())
        self.f.submit('answer_audit', {'records': [self.f.audit(CASES[0])]}, ['Q1'])
        with self.assertRaises(ValueError): self.f.submit('comparison', {'records': [self.f.comparison(CASES[0])]}, ['Q1'])

    def test_legacy_review_preserves_unknown_coverage(self):
        path = self.f.root / 'manifest.json'
        m = read(path); m.pop('audit_required'); write(path, m)
        review = {'issues': [dict(self.f.issue('Q1', 'suggestion'), id=1)]}
        write(self.f.root / 'review.json', review)
        output = self.f.root.parent / 'legacy'
        build(self.f.root, self.f.root / 'review.json', output, ROOT)
        self.assertIn('"coverage":null', (output / 'review-data.js').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
