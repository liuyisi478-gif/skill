#!/usr/bin/env python3
"""File-backed, append-only stage receipts. No model calls; evidence is inspectable, not proof of cognition."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import operator
import re
import time
import uuid
from fractions import Fraction
from pathlib import Path

STAGES = ('inventory', 'independent', 'answer_inventory', 'answer_audit', 'comparison', 'recheck')
FILES = dict(zip(STAGES, ('questions.json', 'independent_answers.json', 'answer_questions.json',
                         'answer_audit.json', 'comparisons.json', 'rechecks.json')))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rational(expression):
    """Bounded arithmetic AST, exact decimals; unsupported syntax is UNKNOWN, never eval()."""
    require(isinstance(expression, str) and 0 < len(expression) <= 200, '算式长度无效')
    expression = expression.translate(str.maketrans('０１２３４５６７８９＋－×÷−（）：', '0123456789+-*/-():')).strip()
    if expression.endswith('%'):
        return rational(expression[:-1]) / 100
    tree = ast.parse(expression, mode='eval')
    require(sum(1 for _ in ast.walk(tree)) <= 80, '算式过于复杂')

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(expression, node)
            exponent = re.search(r'[eE]([+-]?\d+)$', literal)
            require(exponent is None or (len(exponent[1]) <= 5 and abs(int(exponent[1])) <= 1000), '指数过大')
            result = Fraction(literal)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            result = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                      ast.Div: operator.truediv}[type(node.op)](visit(node.left), visit(node.right))
        else:
            raise ValueError('仅支持常数和加减乘除；单位、变量、带分数和集合需人工规范化')
        require(result.numerator.bit_length() < 4096 and result.denominator.bit_length() < 4096, '数值过大')
        return result
    return visit(tree.body)


def equivalent(left, right):
    """Typed ordered answers: [{value:'1/2',unit:'米'}]. No guessing unit conversions or order."""
    if not isinstance(left, list) or not isinstance(right, list) or not left or not right:
        return 'unknown'
    if len(left) != len(right):
        return 'different'
    unknown = False
    for a, b in zip(left, right):
        if not isinstance(a, dict) or not isinstance(b, dict) or a.get('unit') != b.get('unit'):
            unknown = True
            continue
        try:
            if rational(a.get('value')) != rational(b.get('value')):
                return 'different'
        except (ValueError, TypeError, SyntaxError, ZeroDivisionError, OverflowError):
            unknown = True
    return 'unknown' if unknown else 'equal'


def check_statement(source):
    """Conservative verification of pure numeric equalities, including every link of a chain."""
    if not isinstance(source, str) or len(source) > 1000:
        return {'source': source, 'result': 'unknown'}
    pieces = source.replace('＝', '=').split('=')
    if not 2 <= len(pieces) <= 10:
        return {'source': source, 'result': 'unknown'}
    try:
        values = [rational(piece) for piece in pieces]
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError):
        return {'source': source, 'result': 'unknown'}
    return {'source': source, 'result': 'valid' if all(v == values[0] for v in values) else 'invalid',
            'values': [str(v) for v in values]}


class Run:
    def __init__(self, root, verify_snapshots=True):
        self.root = Path(root)
        self.manifest = read(self.root / 'manifest.json')
        self.fingerprint = digest(self.manifest)
        for doc in self.manifest['documents']:
            require([p['page'] for p in doc['pages']] == list(range(1, doc['page_count'] + 1)), 'manifest 存在漏页或重复页')
            for page in doc['pages']:
                image = self.root / page['work_image']
                require(image.is_file(), '缺少完整页面图像：' + str(image))
                if page.get('image_sha256'):
                    require(hashlib.sha256(image.read_bytes()).hexdigest() == page['image_sha256'], '完整页面图像被修改，请新建工作目录')
        path = self.root / 'audit-state.json'
        self.state = read(path) if path.exists() else {'version': 1, 'manifest_hash': self.fingerprint, 'receipts': []}
        require(self.state['manifest_hash'] == self.fingerprint, '输入或渲染已变化，请使用新的工作目录；旧记录不得沿用')
        self.cache = {}
        # Receipts are authoritative; public JSON snapshots must never silently change.
        for receipt in self.state['receipts']:
            require(digest(read(self.root / receipt['result'])) == receipt['hash'], '阶段原始结果被修改：' + receipt['result'])
        for stage, name in FILES.items() if verify_snapshots else ():
            if self.rows(stage):
                require((self.root / name).exists() and read(self.root / name) == self.snapshot(stage),
                        name + ' 与封存记录不一致；不得在看答案后修改独立答案')

    def rows(self, stage):
        if stage in self.cache:
            return self.cache[stage]
        rows = []
        for receipt in self.state['receipts']:
            if receipt['stage'] == stage:
                rows.extend(read(self.root / receipt['result'])['records'])
        # A failed record may be retried before any downstream consumption; raw attempts remain immutable.
        latest = {r['id']: r for r in rows}
        self.cache[stage] = list(latest.values())
        return self.cache[stage]

    def snapshot(self, stage):
        return {'version': 1, 'manifest_hash': self.fingerprint, 'records': self.rows(stage)}

    def mapped(self, stage):
        return {row['id']: row for row in self.rows(stage)}

    def targets(self, targets):
        from build_review import validate_bbox
        require(isinstance(targets, list) and targets, '必须保留原稿位置')
        docs = {d['id']: d for d in self.manifest['documents']}
        for target in targets:
            doc = docs.get(target.get('document'))
            require(doc is not None and type(target.get('page')) is int and 1 <= target['page'] <= doc['page_count'], '原稿文档/页码无效')
            require('bbox' in target, '原稿区域必须包含 bbox，不能定位时为 null')
            validate_bbox(target['bbox'], 0, 0)

    def views(self, views, targets):
        require(isinstance(views, list) and views, '缺少原图查看证据')
        required = {(t['document'], t['page']) for t in targets}
        seen = set()
        for view in views:
            self.targets([dict(view, bbox=view.get('bbox'))])
            doc = next(d for d in self.manifest['documents'] if d['id'] == view['document'])
            page = doc['pages'][view['page'] - 1]
            path = self.root / page['work_image']
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == view.get('image_sha256'), '查看证据图片指纹不符')
            require(bool(view.get('tool_ref')), '必须记录实际图像查看工具调用引用；不能仅生成图片')
            seen.add((view['document'], view['page']))
        require(required <= seen, '存在未回看原图的题目页面')

    def questions(self):
        return self.mapped('inventory')

    def available(self, stage, qid):
        previous = self.mapped(stage).get(qid)
        if not previous:
            return True
        if previous['status'] != 'failed':
            return False
        return not any(qid in self.mapped(later) for later in STAGES[STAGES.index(stage) + 1:])

    def packet(self, stage, ids=None):
        require(stage in STAGES, '未知阶段')
        qs = self.questions()
        existing = self.mapped(stage)
        if stage == 'inventory':
            require(not existing, '清单已封存；识别修订放入 recheck，重新分题请开新目录')
            ids = []
        elif stage == 'answer_inventory':
            require(qs and set(qs) == set(self.mapped('independent')), '必须先保存全部正文独立解题记录（可明确失败）')
            require(not existing, '答案清单已封存')
            ids = []
        else:
            require(qs, '先完成正文清单')
            ids = ids or [qid for qid in qs if self.available(stage, qid)][:4]
            require(1 <= len(ids) <= 5 and len(set(ids)) == len(ids), '每批 1-5 题，通常 3-5 题；复杂题单独')
            require(all(qid in qs and self.available(stage, qid) for qid in ids), '未知题号、阶段已成功或失败结果已被下游使用')
            for qid in ids:
                dependencies = {'independent': (), 'answer_audit': ('independent', 'answer_inventory'),
                                'comparison': ('independent', 'answer_audit'), 'recheck': ('comparison',)}[stage]
                for dep in dependencies:
                    require(qid in self.mapped(dep), f'{qid} 缺少前置阶段 {dep}')
        packet = {'version': 1, 'token': uuid.uuid4().hex, 'stage': stage, 'ids': ids,
                  'manifest_hash': self.fingerprint, 'ledger_hash': digest(self.state), 'started': time.time()}
        if stage == 'inventory':
            # Mixed PDF: entire file is potentially answer-bearing; agent must identify body range first.
            packet['documents'] = [d for d in self.manifest['documents'] if d['id'] == 'body']
        elif stage == 'answer_inventory':
            packet['questions'] = list(qs.values())
            packet['documents'] = self.manifest['documents']
        else:
            packet['questions'] = [qs[qid] for qid in ids]
            for dep in {'independent': (), 'answer_audit': ('answer_inventory',),
                        'comparison': ('independent', 'answer_inventory', 'answer_audit'),
                        'recheck': ('independent', 'answer_inventory', 'answer_audit', 'comparison')}[stage]:
                packet[dep] = [r for r in self.rows(dep) if r['id'] in ids]
            if stage == 'answer_audit':
                packet['program_checks'] = {qid: [check_statement(s) for s in self.mapped('answer_inventory')[qid].get('source_steps', [])]
                                            for qid in ids}
            if stage == 'comparison':
                packet['numeric_comparison'] = {qid: equivalent(self.mapped('independent')[qid].get('answer'),
                    self.mapped('answer_inventory')[qid].get('answer')) for qid in ids}
                packet['structure_findings'] = self.structure_findings() if next(iter(qs)) in ids else []
        # Independent and answer-audit packets deliberately exclude each other's conclusions.
        write(self.root / 'packets' / (packet['token'] + '.json'), packet)
        return packet

    def structure_findings(self):
        findings = []
        numbers = {}
        for q in self.rows('inventory'):
            numbers.setdefault((q.get('section'), q.get('number')), []).append(q['id'])
        for (section, number), ids in numbers.items():
            if len(ids) > 1:
                target = self.questions()[ids[0]]['targets'][0]
                findings.append({'id': 'duplicate:' + digest([section, number]), 'source': {'section': section,
                    'number': number, 'ids': ids}, 'document': target['document'], 'page': target['page']})
        for receipt in self.state['receipts']:
            if receipt['stage'] not in ('inventory', 'answer_inventory'):
                continue
            for page in read(self.root / receipt['result']).get('pages', []):
                for key in ('anomalies', 'unmatched_answers'):
                    for index, value in enumerate(page.get(key, [])):
                        findings.append({'id': f"{receipt['stage']}:{page['document']}:{page['page']}:{key}:{index}",
                                         'source': value, 'document': page['document'], 'page': page['page']})
        return findings

    def validate_result(self, packet, result):
        stage = packet['stage']
        rows = result.get('records')
        require(isinstance(rows, list) and rows, 'records 不能为空')
        ids = [r.get('id') for r in rows]
        require(all(isinstance(x, str) and x for x in ids) and len(ids) == len(set(ids)), '记录 id 无效或重复')
        require(all(self.available(stage, qid) for qid in ids), '不可覆盖已成功或下游已使用的结果')
        if stage not in ('inventory', 'answer_inventory'):
            require(set(ids) == set(packet['ids']), '本批有漏题、多题或题号错配')
        for r in rows:
            require(r.get('status') in ('ok', 'uncertain', 'failed'), 'status 必须为 ok/uncertain/failed')
            require(isinstance(r.get('uncertainties'), list), '必须记录 uncertainties（可空）')
            require(r['status'] == 'ok' or bool(r['uncertainties']), '失败或疑难必须说明原因')
            if stage in ('inventory', 'answer_inventory'):
                self.targets(r.get('targets'))
                if stage == 'inventory':
                    for key in ('number', 'section', 'stem', 'type', 'options', 'figures'):
                        require(key in r, '题目清单缺少 ' + key)
                    require(isinstance(r['stem'], str) and r['stem'].strip() and
                            isinstance(r['options'], list) and isinstance(r['figures'], list), '题干/选项/图形格式无效')
                    require(all(t['document'] == 'body' for t in r['targets']), '正文清单不可含答案文档')
                    self.views(r.get('views'), r['targets'])
                else:
                    require(r.get('match') in ('matched', 'unpaired', 'ambiguous', 'not_supplied'), '必须记录配对状态')
                    require(bool(r.get('match_reason')), '缺少配对依据/未配对原因')
                    if r['match'] == 'matched':
                        require(bool(r.get('answer_id')) and bool(r.get('answer_number')), '缺少答案原题号/唯一标识')
                        require(bool(r.get('source_answer')) and isinstance(r.get('source_steps'), list), '缺少答案原文/逐步转写')
                        self.views(r.get('views'), r['targets'])
            else:
                require(bool(r.get('reasoning')), '必须保存可核验的过程/失败原因')
                if stage == 'independent':
                    require(isinstance(r.get('body_checks'), dict) and
                            all(isinstance(r['body_checks'].get(k), str) and r['body_checks'][k].strip() for k in ('language', 'conditions', 'figure', 'ambiguity', 'units')),
                            '正文检查必须逐项记录判断依据；不适用时写原因')
                    require(r['status'] != 'ok' or bool(r.get('answer')), '成功解题缺少答案')
                if stage == 'answer_audit':
                    source = self.mapped('answer_inventory')[r['id']]
                    steps = r.get('steps')
                    require(isinstance(steps, list), '缺少逐步核查')
                    if source['match'] == 'matched':
                        require(len(steps) == len(source['source_steps']), '原稿步骤数量与核查数量不同')
                        require(all(s.get('source') == text and s.get('verdict') in ('valid', 'invalid', 'uncertain') and s.get('reason')
                                    for s, text in zip(steps, source['source_steps'])), '步骤转写/判断/依据缺失')
                        require(bool(r.get('final_check')) and bool(r.get('grade_check')), '缺少最终答案/年级方法核查')
                    elif source['match'] != 'not_supplied':
                        require(r['status'] != 'ok', '未匹配答案不能声称已检查原稿')
                if stage in ('comparison', 'recheck'):
                    require(isinstance(r.get('issues'), list), '必须显式保存 issues（可空）')
                    if stage == 'comparison':
                        require(all(r.get(k) for k in ('answer_vs_solution', 'derivation', 'conditions_vs_figure')), '三方核验维度缺失')
                        if r['id'] == next(iter(self.questions())):
                            findings = packet.get('structure_findings', [])
                            checks = r.get('structure_review', [])
                            require(isinstance(checks, list) and len(checks) == len(findings) and
                                    {c.get('id') for c in checks} == {f['id'] for f in findings} and
                                    all(c.get('reason') and c.get('outcome') in ('cleared', 'manual', 'error') for c in checks),
                                    '结构逆查遗漏：逐条处理跳号、跨页异常和孤立答案')
                    if stage == 'recheck':
                        require(r.get('outcome') in ('confirmed', 'cleared', 'manual'), '复核结论无效')
                        self.views(r.get('views'), self.questions()[r['id']]['targets'] +
                                   (self.mapped('answer_inventory')[r['id']]['targets'] if self.mapped('answer_inventory')[r['id']]['match'] == 'matched' else []))
                        require(bool(r.get('verification')), '复核必须记录新验算/另一思路或无法核实原因')
                    for issue in r.get('issues', []):
                        require(issue.get('questionId') == r['id'], '批注 questionId 必须对应稳定 id')
                        self.targets(issue.get('targets'))
                        if issue.get('kind') == 'confirmed':
                            require(stage == 'recheck' and r.get('outcome') == 'confirmed' and issue.get('detail'), '红色错误必须有重点复核证据')
                    from build_review import validate
                    validate(self.manifest, {'issues': [dict(issue, id=i) for i, issue in enumerate(r['issues'], 1)]})
            if stage in ('independent', 'answer_inventory') and (stage == 'independent' or r.get('match') == 'matched'):
                require(isinstance(r.get('answer'), list) and all(isinstance(a, dict) and isinstance(a.get('value'), str)
                            and isinstance(a.get('unit'), str) for a in r['answer']), '答案必须是 value/unit 字符串数组')
        if stage == 'inventory':
            self.validate_pages(result.get('pages'), {'body'}, set(ids))
        elif stage == 'answer_inventory':
            require(set(ids) == set(self.questions()), '每道正文题必须有配对/未配对记录')
            self.validate_pages(result.get('pages'), {d['id'] for d in self.manifest['documents']}, set(ids), answer=True)
            matched = [r['answer_id'] for r in rows if r['match'] == 'matched']
            require(len(matched) == len(set(matched)), '同一答案被重复配对；共享解析应拆为可定位子项')
            if any(r['match'] == 'not_supplied' for r in rows):
                require(not any(d['id'] == 'answer' for d in self.manifest['documents']) and
                        not any(p['role'] in ('answer', 'mixed') for p in result['pages']) and not matched,
                        '已有答案文档/答案页不能标为未提供答案；应标漏答或无法匹配')

    def validate_pages(self, pages, docs, ids, answer=False):
        require(isinstance(pages, list), '缺少逐页清点记录')
        expected = {(d['id'], p['page']) for d in self.manifest['documents'] if d['id'] in docs for p in d['pages']}
        actual = [(p.get('document'), p.get('page')) for p in pages]
        require(len(actual) == len(set(actual)) and set(actual) == expected, '逐页记录存在漏页/重复页')
        for p in pages:
            require(p.get('role') in ('body', 'answer', 'mixed', 'front', 'blank'), '缺少页面角色')
            require(isinstance(p.get('question_ids'), list) and set(p['question_ids']) <= ids, '页面题号清单无效')
            require(isinstance(p.get('anomalies'), list), '必须记录跳号、重复号、断题、印刷页码缺失等异常（可空）')
            require(bool(p['question_ids']) or bool(p.get('reason')), '无题页必须说明原因')
            self.views(p.get('views'), [dict(p, bbox=None)])
        # Both directions: catches omitted cross-page continuation in page ledger.
        # Result records are validated separately; cross references checked at commit below.

    def commit(self, packet_path, result_path):
        packet = read(packet_path)
        original = self.root / 'packets' / (packet['token'] + '.json')
        require(original.is_file() and read(original) == packet, '任务包不属于本次运行')
        require(packet['manifest_hash'] == self.fingerprint and packet['ledger_hash'] == digest(self.state), '任务包已过期；重新生成，不重复已完成题')
        result = read(result_path)
        self.validate_result(packet, result)
        stage = packet['stage']
        if stage == 'answer_audit':
            for row in result['records']:
                row['program_checks'] = [check_statement(s) for s in self.mapped('answer_inventory')[row['id']].get('source_steps', [])]
        if stage in ('inventory', 'answer_inventory'):
            pages = {(p['document'], p['page']): p for p in result['pages']}
            for r in result['records']:
                if stage == 'answer_inventory' and r['match'] != 'matched':
                    continue
                expected = {(t['document'], t['page']) for t in r['targets']}
                actual = {key for key, p in pages.items() if r['id'] in p['question_ids']}
                require(expected == actual, '逐题位置与逐页题号清单不一致（包括跨页）')
        relative = 'receipts/' + packet['token'] + '.json'
        write(self.root / relative, result)
        self.state['receipts'].append({'stage': stage, 'ids': [r['id'] for r in result['records']],
            'result': relative, 'hash': digest(result), 'packet': packet['token'],
            'finished': time.time(), 'elapsed_seconds': round(time.time() - packet['started'], 3),
            'usage': result.get('usage')})
        self.cache.pop(stage, None)
        write(self.root / 'audit-state.json', self.state)
        write(self.root / FILES[stage], self.snapshot(stage))
        write(self.root / 'coverage.json', self.coverage())

    def risk(self, qid):
        q = self.questions()[qid]
        ind = self.mapped('independent').get(qid, {})
        ans = self.mapped('answer_inventory').get(qid, {})
        audit = self.mapped('answer_audit').get(qid, {})
        comp = self.mapped('comparison').get(qid, {})
        no_answer = ans.get('match') == 'not_supplied'
        reasons = []
        for label, row in (('recognition', q), ('solve', ind), ('match', ans), ('audit', audit), ('comparison', comp)):
            if row.get('status') != 'ok' or row.get('uncertainties'):
                reasons.append(label)
        if ans.get('match') != 'matched' and not no_answer:
            reasons.append('unpaired')
        if q.get('complex_figure'):
            reasons.append('complex_figure')
        if not no_answer and equivalent(ind.get('answer'), ans.get('answer')) != 'equal':
            reasons.append('answer_conflict_or_unknown')
        if any(s.get('verdict') != 'valid' for s in audit.get('steps', [])):
            reasons.append('step_error')
        if any(c.get('result') == 'invalid' for c in audit.get('program_checks', [])):
            reasons.append('program_arithmetic_error')
        if any(i.get('kind') != 'suggestion' for i in comp.get('issues', [])) or comp.get('review_reasons'):
            reasons.append('findings')
        if any(c.get('outcome') != 'cleared' for c in comp.get('structure_review', [])):
            reasons.append('structure')
        return reasons

    def coverage(self):
        records = []
        for qid, q in self.questions().items():
            rows = {s: self.mapped(s).get(qid, {}) for s in STAGES[1:]}
            risk = self.risk(qid)
            recheck = rows['recheck']
            complete = all(rows[s] for s in ('independent', 'answer_inventory', 'answer_audit', 'comparison'))
            if risk:
                complete = complete and bool(recheck)
            # Failed work remains incomplete even if a reviewer supplies a manual annotation.
            complete = bool(complete and q['status'] != 'failed' and all(rows[s].get('status') != 'failed' for s in ('independent', 'answer_audit', 'comparison'))
                            and recheck.get('status') != 'failed')
            issues = recheck.get('issues', rows['comparison'].get('issues', []))
            records.append({'id': qid, 'targets': q['targets'], 'recognized': q['status'] == 'ok',
                'answer_matched': rows['answer_inventory'].get('match') == 'matched',
                'independent_solved': rows['independent'].get('status') == 'ok',
                'answer_checked': rows['answer_inventory'].get('match') == 'matched' and bool(rows['answer_audit'].get('final_check')) and rows['answer_audit'].get('status') != 'failed',
                'steps_checked': 'steps' in rows['answer_audit'] and rows['answer_inventory'].get('match') == 'matched' and rows['answer_audit'].get('status') != 'failed',
                'steps_mode': ('not_available' if rows['answer_inventory'].get('match') != 'matched' else
                               'final_only' if rows['answer_inventory'].get('source_steps') == [] else 'stepwise'),
                'doubts': risk, 'annotated': bool(issues), 'complete': complete,
                'manual_review': bool(risk and (not recheck or recheck.get('outcome') == 'manual')),
                'missing': [s for s in ('independent', 'answer_inventory', 'answer_audit', 'comparison') if not rows[s]],
                'status': 'incomplete' if not complete else ('manual' if risk and recheck.get('outcome') == 'manual' else 'checked'),
                'note': '；'.join(risk)})
        return {'version': 1, 'manifest_hash': self.fingerprint, 'total': len(records),
                'processed': sum(r['complete'] for r in records), 'records': records,
                'receipt_count': len(self.state['receipts'])}

    def export(self, draft=False):
        coverage = self.coverage()
        require(coverage['total'] > 0, '没有题目清单')
        require(draft or coverage['processed'] == coverage['total'], '仍有未完成题；用 --draft 输出明确标记的阶段稿')
        issues = []
        for qid in self.questions():
            row = self.mapped('recheck').get(qid, self.mapped('comparison').get(qid, {}))
            issues.extend(row.get('issues', []))
        for row in coverage['records']:
            if (not row['complete'] or row['manual_review']) and not any(i.get('questionId') == row['id'] and i.get('kind') == 'suspected' for i in issues):
                issues.append({'kind': 'suspected', 'category': '检查未完成' if not row['complete'] else '待人工复核',
                    'questionId': row['id'], 'title': '本题检查未完成' if not row['complete'] else '本题仍需人工复核',
                    'detail': row['note'] or '缺少阶段结果', 'suggestion': '回看原稿并补齐核查记录', 'targets': row['targets']})
        for index, issue in enumerate(issues, 1):
            issue['id'] = index
        review = {'document': {'title': '数学教辅校对稿' + ('（阶段稿）' if draft else '')},
                  'audit_version': 1, 'draft': draft, 'issues': issues}
        write(self.root / 'coverage.json', coverage)
        write(self.root / 'review.json', review)
        return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('packet')
    p.add_argument('stage', choices=STAGES)
    p.add_argument('--ids', nargs='+')
    p = subs.add_parser('commit')
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--result', type=Path, required=True)
    p = subs.add_parser('export')
    p.add_argument('--draft', action='store_true')
    subs.add_parser('status')
    subs.add_parser('repair')
    p = subs.add_parser('calc')
    p.add_argument('expression')
    args = parser.parse_args()
    try:
        run = Run(args.work_dir, verify_snapshots=args.command != 'repair')
        if args.command == 'packet':
            packet = run.packet(args.stage, args.ids)
            print(run.root / 'packets' / (packet['token'] + '.json'))
        elif args.command == 'commit':
            run.commit(args.packet, args.result)
            print(json.dumps(run.coverage(), ensure_ascii=False))
        elif args.command == 'calc':
            result = {'expression': args.expression, 'value': str(rational(args.expression)), 'time': time.time()}
            with (run.root / 'calculations.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(result, ensure_ascii=False) + '\n')
            print(json.dumps(result, ensure_ascii=False))
        elif args.command == 'repair':
            for stage, name in FILES.items():
                if run.rows(stage):
                    write(run.root / name, run.snapshot(stage))
            write(run.root / 'coverage.json', run.coverage())
            print('已按有效收据恢复派生快照，未改写收据。')
        elif args.command == 'export':
            run.export(args.draft)
            print(run.root / 'review.json')
        else:
            print(json.dumps(run.coverage(), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, SyntaxError, ZeroDivisionError) as exc:
        parser.exit(1, f'校验失败：{exc}\n')


if __name__ == '__main__':
    main()
