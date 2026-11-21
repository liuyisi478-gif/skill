"""Export editorial JSON to DOCX with native editable OMML. Python-docx + lxml.

Usage: python export_docx.py INPUT.json OUTPUT.docx
Only the documented elementary TeX subset is supported; unknown syntax fails.
Structural validation is automatic. Rendering and mathematical QA are separate.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree

NS = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
      "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SYMBOLS = {"times": "×", "div": "÷", "pi": "π", "parallel": "∥",
           "perp": "⊥", "triangle": "△", "angle": "∠", "circ": "°",
           "cdot": "·", "cdots": "⋯", "dots": "…", "%": "%",
           "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "neq": "≠"}


def node(tag, children=()):
    el = OxmlElement("m:" + tag)
    for child in children:
        el.append(child)
    return el


def math_run(text):
    r = node("r")
    t = node("t")
    t.text = text
    r.append(t)
    return r


class MathParser:
    """Strict recursive parser, not a regex-only TeX replacement."""
    def __init__(self, source):
        if not source.strip() or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f$\u4e00-\u9fff]", source):
            raise ValueError("Empty, Chinese, control character, or dollar in formula")
        self.s, self.i = source, 0

    def skip(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def argument(self):
        self.skip()
        if self.i == len(self.s):
            raise ValueError("Missing formula argument")
        if self.s[self.i] == "{":
            self.i += 1
            return self.sequence(group=True)
        return [self.atom()]

    def atom(self):
        self.skip()
        if self.i >= len(self.s):
            raise ValueError("Missing formula atom")
        ch = self.s[self.i]
        self.i += 1
        if ch in "}^_":
            raise ValueError("Unexpected formula token: " + ch)
        if ch == "{":
            return node("box", [node("e", self.sequence(group=True))])
        if ch == "\\":
            match = re.match(r"[A-Za-z]+|[^A-Za-z]", self.s[self.i:])
            if not match:
                raise ValueError("Incomplete TeX command")
            command = match.group(0)
            self.i += len(command)
            if command in ("frac", "dfrac"):
                numerator, denominator = self.argument(), self.argument()
                if not numerator or not denominator:
                    raise ValueError("Empty numerator or denominator")
                return node("f", [node("num", numerator), node("den", denominator)])
            if command in SYMBOLS:
                return math_run(SYMBOLS[command])
            if command in ("{", "}"):
                return math_run(command)
            raise ValueError("Unsupported TeX command: \\" + command)
        if ch not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+-−=:.(),[]/×÷π∥⊥△∠°·⋯…%<>≤≥≠":
            raise ValueError("Unsupported formula character: " + ch)
        return math_run(ch)

    def sequence(self, group=False):
        out = []
        while True:
            self.skip()
            if self.i == len(self.s):
                if group:
                    raise ValueError("Unclosed formula brace")
                return out
            ch = self.s[self.i]
            if ch == "}":
                if not group:
                    raise ValueError("Unmatched closing brace")
                self.i += 1
                return out
            if ch not in "_^":
                out.append(self.atom())
                continue
            if not out:
                raise ValueError("Script without base")
            self.i += 1
            script = self.argument()
            if not script:
                raise ValueError("Empty subscript or superscript")
            base = out.pop()
            tag = etree.QName(base).localname
            if tag in ("sSub", "sSup"):
                existing = "_" if tag == "sSub" else "^"
                if existing == ch:
                    raise ValueError("Duplicate subscript or superscript")
                prior = list(base.find(qn("m:sub" if existing == "_" else "m:sup")))
                content = list(base.find(qn("m:e")))
                sub, sup = (script, prior) if ch == "_" else (prior, script)
                out.append(node("sSubSup", [node("e", content), node("sub", sub), node("sup", sup)]))
            elif tag == "sSubSup":
                raise ValueError("Duplicate subscript or superscript")
            else:
                out.append(node("sSub" if ch == "_" else "sSup",
                                [node("e", [base]), node("sub" if ch == "_" else "sup", script)]))

    def parse(self):
        return node("oMath", self.sequence())


def rich(paragraph, source, expected, bold=False):
    """Append runs and OMML in source order; keep a canonical formula inventory."""
    i, start = 0, 0
    state = bold
    def text_run(text):
        if text:
            r = paragraph.add_run(text)
            r.bold = state
    while i < len(source):
        if source.startswith("**", i):
            text_run(source[start:i])
            state = not state
            i += 2
            start = i
        elif source[i] == "$":
            text_run(source[start:i])
            end = source.find("$", i + 1)
            if end < 0:
                raise ValueError("Unclosed dollar formula: " + source)
            formula = MathParser(source[i + 1:end]).parse()
            if state:
                for run in formula.findall(".//m:r", NS):
                    props = node("rPr")
                    style = node("sty")
                    style.set(qn("m:val"), "bi")
                    props.append(style)
                    run.insert(0, props)
            expected.append(deepcopy(formula))
            paragraph._p.append(formula)
            i = end + 1
            start = i
        else:
            i += 1
    text_run(source[start:])
    if state != bold:
        raise ValueError("Unclosed bold marker: " + source)


def set_borders(table):
    props = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement("w:" + edge)
        b.set(qn("w:val"), "nil" if edge == "insideV" else "single")
        b.set(qn("w:sz"), "8")
        b.set(qn("w:color"), "999999")
        borders.append(b)
    props.append(borders)
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def quick_answers(doc, data, expected):
    sections = [s for s in data["sections"] if s["kind"] in ("choice", "fill") and s["questions"]]
    if not sections:
        return
    p = doc.add_paragraph("快速对答案")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.runs[0].bold = True
    table = doc.add_table(rows=2, cols=1)
    table.autofit = False
    table.columns[0].width = Cm(17)
    set_borders(table)
    cell = table.cell(0, 0)
    for index, section in enumerate(sections):
        p = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        rich(p, "**" + section["label"] + "**　", expected)
        qs = section["questions"]
        nums = [q["number"] for q in qs]
        consecutive = all(re.fullmatch(r"\d+", n) for n in nums) and all(int(b) == int(a) + 1 for a, b in zip(nums, nums[1:]))
        compact = (section["kind"] == "choice" and consecutive
                   and all(not q.get("multiple") and re.fullmatch(r"[A-Z]", q.get("answer") or "") for q in qs))
        if compact:
            label = nums[0] if len(nums) == 1 else nums[0] + "～" + nums[-1]
            rich(p, "**" + label + "** " + "".join(q["answer"] for q in qs), expected)
        else:
            for j, question in enumerate(qs):
                if j:
                    p.add_run("　")
                rich(p, "**" + question["number"] + ".**\u00a0" + (question.get("answer") or "待核"), expected)
    default = "解答题请看“详解详析”" if any(s["kind"] == "solution" and s["questions"] for s in data["sections"]) else "各题解析请看“详解详析”"
    note = data.get("quick_note", default)
    if re.search(r"(?:[Pp]\s*\d|第?\s*\d+\s*页)", note):
        raise ValueError("Static quick-note page number is unverified; omit it or use a verified field workflow")
    rich(table.cell(1, 0).paragraphs[0], note, expected)


def validate_source(data):
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Missing document title")
    if not isinstance(data.get("sections"), list):
        raise ValueError("Missing sections")
    if data.get("mode", "student") not in ("student", "qa"):
        raise ValueError("mode must be student or qa")
    for section in data["sections"]:
        if section["kind"] not in ("choice", "fill", "calculation", "solution", "other"):
            raise ValueError("Unknown section kind")
        seen = set()
        for q in section["questions"]:
            number = q["number"]
            if not isinstance(number, str) or not number.strip() or number in seen:
                raise ValueError("Missing or duplicate question number within section")
            seen.add(number)
            if not isinstance(q.get("paragraphs"), list) or not q["paragraphs"]:
                raise ValueError("Question has no body")
            diagrams = question_diagrams(q)
            if q.get('diagram_required') and not diagrams:
                raise ValueError('Required solution diagram is missing for question ' + number)
            for diagram in diagrams:
                index = diagram['after_paragraph']
                if isinstance(index, bool) or not isinstance(index,int) or not -1 <= index < len(q['paragraphs']):
                    raise ValueError('Diagram insertion position is outside the question')
                width = diagram.get('width_cm', 10)
                if not isinstance(width,(int,float)) or not 2 <= width <= 17:
                    raise ValueError('Diagram width must be between 2 and 17 cm')
                if not diagram.get('path') or not isinstance(diagram['path'],str):
                    raise ValueError('Diagram image path is missing')
            answer = q.get("answer")
            if answer is not None and (not isinstance(answer, str) or not answer.strip()):
                raise ValueError("Answer must be a nonempty string or null")
            if answer and re.search(r"[;；]|\d\s*/\s*\d", answer):
                raise ValueError("Use spaces between blanks and native frac math for fractions")
            if data.get("mode") != "qa" and not q.get("taxonomy"):
                raise ValueError("Missing question taxonomy")
            if data.get("mode") != "qa" and answer is not None and section["kind"] in ("choice", "fill"):
                # The authoritative answer must be literally present immediately before analysis.
                body = "\n".join(q["paragraphs"])
                if answer + "【解析】" not in body:
                    raise ValueError("Body answer disagrees with authoritative answer or analysis is separated")
    tagged = {term.strip() for s in data["sections"] for q in s["questions"]
              for term in re.findall(r"〔新拟〕([^＋\n]+)", q.get("taxonomy", ""))}
    registered = {m["name"] for m in data.get("new_models", [])}
    if data.get("mode") != "qa" and tagged != registered:
        raise ValueError("New-model registrations do not match tagged taxonomy: " + str(tagged ^ registered))


def signature(element):
    # Prefixes, namespace declarations and Word-generated proofing attributes do not matter.
    return (element.tag, tuple(sorted(element.attrib.items())), element.text or "",
            tuple(signature(child) for child in element))


def question_diagrams(question):
    if question.get('figure') and question.get('diagrams'):
        raise ValueError('Use diagrams or legacy figure, not both')
    if question.get('figure'):
        return [{'path':question['figure'], 'caption':question.get('figure_caption',''),
                 'width_cm':question.get('figure_width_cm',6),
                 'after_paragraph':len(question['paragraphs'])-1}]
    diagrams=question.get('diagrams',[])
    if not isinstance(diagrams,list) or any(not isinstance(d,dict) for d in diagrams):
        raise ValueError('diagrams must be a list of objects')
    return [dict(d,after_paragraph=d.get('after_paragraph',0)) for d in diagrams]


def validate_docx(path, expected, expected_images=None):
    with ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError("DOCX ZIP integrity failed")
        for required in ("[Content_Types].xml", "_rels/.rels", "word/document.xml"):
            z.getinfo(required)
        for name in z.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                etree.fromstring(z.read(name))
        root = etree.fromstring(z.read("word/document.xml"))
        actual = root.findall(".//m:oMath", NS)
        drawings = root.findall('.//' + qn('w:drawing'))
        if expected_images is not None and len(drawings) != expected_images:
            raise ValueError('Embedded diagram count differs from source')
        relations = etree.fromstring(z.read('word/_rels/document.xml.rels'))
        rels = {r.get('Id'):r for r in relations}
        for drawing in drawings:
            blips=drawing.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
            if len(blips) != 1:
                raise ValueError('Unexpected diagram drawing structure')
            relation=rels.get(blips[0].get(qn('r:embed')))
            if relation is None or relation.get('TargetMode') == 'External':
                raise ValueError('Diagram must be embedded, not externally linked')
            target=relation.get('Target')
            from posixpath import normpath
            media=normpath('word/'+target)
            if not media.startswith('word/media/') or not z.read(media):
                raise ValueError('Embedded diagram image is missing')
        # Document body order is table first, then body, matching construction order.
        if [signature(x) for x in actual] != [signature(x) for x in expected]:
            raise ValueError("OMML inventory differs from the source formula inventory")
        for text in root.xpath("//w:t/text() | //m:t/text()", namespaces=NS):
            if "$" in text or re.search(r"\\[A-Za-z]+", text):
                raise ValueError("Unconverted formula markup in DOCX")
    Document(path)
    return {"formulas": len(actual), "fractions": len(root.findall(".//m:f", NS)),
            "subscripts": len(root.findall(".//m:sSub", NS)),
            "superscripts": len(root.findall(".//m:sSup", NS)), "diagrams":len(drawings)}


def export(data, output, base_dir=Path(".")):
    validate_source(data)
    doc = Document()
    # Templates may attach a decorative blue rule to Title. Strip inherited
    # paragraph borders as well as direct formatting before applying typography.
    for style in doc.styles:
        for border in style._element.findall('.//' + qn('w:pBdr')):
            border.getparent().remove(border)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin = section.right_margin = Cm(2)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
        style.font.color.rgb = RGBColor(0, 0, 0)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing = 1.25
    normal.paragraph_format.space_after = Pt(3)
    doc.styles["Title"].font.size = Pt(15)
    doc.styles["Heading 1"].font.size = Pt(12)
    doc.styles["Heading 2"].font.size = Pt(11)
    math_props = node("mathPr")
    math_font = node("mathFont")
    math_font.set(qn("m:val"), "Cambria Math")
    math_props.append(math_font)
    doc.settings._element.append(math_props)
    doc.add_paragraph(data["title"], "Title")
    expected = []
    image_count = 0

    def insert_diagram(diagram):
        nonlocal image_count
        image = Path(diagram['path'])
        image = image if image.is_absolute() else base_dir / image
        if not image.is_file():
            raise ValueError('Diagram image does not exist: ' + str(image))
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        shape = p.add_run().add_picture(str(image), width=Cm(diagram.get('width_cm',10)))
        shape._inline.docPr.set('descr',diagram.get('alt_text',diagram.get('caption','数学解答图')))
        p.paragraph_format.keep_together = True
        if diagram.get('caption'):
            p.paragraph_format.keep_with_next = True
            caption = doc.add_paragraph(diagram['caption'])
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        image_count += 1
    qa = data.get("mode") == "qa"
    if not qa:
        quick_answers(doc, data, expected)
        doc.add_heading("详解详析", level=1)
    for s in data["sections"]:
        doc.add_heading(s["label"], level=2)
        for question in s["questions"]:
            diagrams=question_diagrams(question)
            for diagram in diagrams:
                if diagram['after_paragraph'] == -1:
                    insert_diagram(diagram)
            for index, source in enumerate(question["paragraphs"]):
                p=doc.add_paragraph()
                rich(p, source, expected)
                attached=[d for d in diagrams if d['after_paragraph']==index]
                if attached:
                    p.paragraph_format.keep_with_next=True
                for diagram in attached:
                    insert_diagram(diagram)
            if not qa:
                p = doc.add_paragraph()
                rich(p, "**【题型归类】** " + question["taxonomy"], expected)
    if data.get("new_models") and not qa:
        doc.add_heading("新增知识点清单", level=1)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        for cell, text in zip(table.rows[0].cells, ("知识点", "判别特征", "出处", "建议归入")):
            cell.text = text
        for m in data["new_models"]:
            for cell, key in zip(table.add_row().cells, ("name", "feature", "source", "category")):
                rich(cell.paragraphs[0], m[key], expected)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never replace a prior final document with an unvalidated export.
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        candidate = Path(temp) / "candidate.docx"
        doc.save(candidate)
        stats = validate_docx(candidate, expected, image_count)
        candidate.replace(output)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8-sig"))
    stats = export(data, args.output, args.source.parent)
    print("结构检查通过；视觉检查须另行完成：" + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
