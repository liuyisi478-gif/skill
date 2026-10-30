"""解析 Markdown 交付前的格式检查（仅标准库），对齐《超详解解析要求》。

用法：
    python lint_md.py 解析.md
    python lint_md.py 解析.md --strict     # WARN 也算失败

检查项（ERROR）：
    块级公式 $$ / \\[ / \\begin{}
    $ 不配对
    丙档命令与符号
    模糊词：显然 / 易得 / 大概 / 可能 / 不难看出 / 同理可得
    泄漏进交付文件的质检字段：题干复原 / 置信 / 验算方式
    选择/填空缺【解析】；计算/解答误加【解析】
    解答题缺「解：」（计算题不要求「解：」或【解析】）
    每题缺【题型归类】
    【思路分析】【题图分析】出现在【解析】之后
    【易错警示】【一题多解】出现在【解析】之前
    填空/选择的答案与【解析】分行；算式结果单位未加括号
    计算题用 Markdown/HTML 表格或代码块承载过程
    每题正文首段缺题号或题号不一致；客观题答案部分使用分号
    已有快速答案节却未采用表式；快速填空答案使用分号
WARN：
    公式与中文之间缺空格；公式内含中文；缺"快速对答案"节
    知识点不在词表中且未标〔新拟〕
    题型归类超过 4 个
    用了〔新拟〕但没有"新增知识点清单"节
"""

import os
import re
import sys

errors = []
warns = []

FORBIDDEN_CMDS = [r"\equiv", r"\binom", r"\sin", r"\cos", r"\tan", r"\log",
                  r"\begin{cases}", r"\begin{equation}", r"\begin{aligned}"]
VAGUE = ["显然", "易得", "大概", "不难看出", "同理可得", "易证"]
VAGUE_WARN = ["可能"]  # 题干与答案中可能出现，只提示
LEAK = ["题干复原", "【置信】", "高置信", "建议复核", "验算方式"]
FULLWIDTH = "，。；：（）【】、！？"
PRE_ANSWER = ["【思路分析】", "【题图分析】"]
POST_ANSWER = ["【易错警示】", "【一题多解】"]
TITLE_RE = re.compile(r"^##\s+")
# 匹配结果后常用单位；纯数、比、百分数、倍数和角度符号不强加括号。
UNIT_RE = (r"(?:(?:平方|立方)?(?:千米|分米|厘米|毫米|米)(?:[/／](?:小时|分钟|秒|时|分))?"
           r"|千克|毫克|克|吨|毫升|升|元|角|分(?!数|之一)|人|个|本|件|根|双|张|天|年|月|小时|分钟|秒)")

NEW_TAG = "〔新拟〕"
TAXONOMY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "references", "model_taxonomy.md")

# 同一模型的不同叫法，归到词表里的标准名
ALIAS = {
    "余数问题": "余数与同余",
    "同余": "余数与同余",
    "递推数列": "递推与数列建模",
    "最值构造": "最值问题（构造）",
    "最值": "最值问题（构造）",
    "平均数": "平均数问题",
    "火车过桥问题": "火车过桥",
    "构造与论证": "最值·构造下界",
}


def load_vocab():
    """从 model_taxonomy.md 的表格首列读出全部模型名，含"标准名/基名"两套。"""
    full, base = set(), set()
    try:
        with open(TAXONOMY, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s.startswith("|"):
                    continue
                cells = [c.strip() for c in s.strip("|").split("|")]
                if len(cells) < 2 or not cells[0] or cells[0] == "模型":
                    continue
                if set(cells[0]) <= set("-: "):
                    continue
                full.add(cells[0])
                base.add(base_name(cells[0]))
    except OSError:
        pass
    return full, base


def base_name(name):
    """«环形跑道（追及）» → «环形跑道»；«巧算·凑整» → «巧算»。"""
    return re.split(r"[·（(]", name)[0].strip()


def split_terms(raw):
    """按顶层「＋」「、」拆分知识点，括号内的连接符不拆。"""
    raw = raw.strip().lstrip("*").strip()
    parts, buf, depth = [], "", 0
    for ch in raw:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if ch in "＋+、" and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)

    out = []
    for piece in parts:
        piece = piece.strip()
        if not piece:
            continue
        is_new = NEW_TAG in piece
        piece = piece.replace(NEW_TAG, "").strip().strip("*· ")
        if piece:
            out.append((piece, is_new))
    return out


def check_taxonomy(joined, start, new_terms):
    m = re.search(r"【题型归类】\*{0,2}\s*(.+)", joined)
    if not m:
        return
    terms = split_terms(m.group(1).split("\n")[0])
    if len(terms) > 4:
        add(warns, start, "【题型归类】写了 %d 个知识点，建议不超过 4 个" % len(terms))
    for name, is_new in terms:
        if is_new:
            new_terms.append((start, name))
            continue
        if name in VOCAB_FULL or name in VOCAB_BASE or base_name(name) in VOCAB_BASE:
            continue
        if name in ALIAS or base_name(name) in ALIAS:
            continue
        add(warns, start, "知识点「%s」不在词表：若属新增，请写成 %s%s 并在文末登记"
            % (name, NEW_TAG, name))


VOCAB_FULL, VOCAB_BASE = load_vocab()



def add(bucket, ln, msg):
    bucket.append((ln, msg))


def scan_lines(lines):
    kinds = section_kinds(lines)
    for i, s in enumerate(lines, 1):
        if "$$" in s:
            add(errors, i, "块级公式 $$ 禁止使用，改为行内 $...$")
        if re.search(r"\\\[|\\\]", s):
            add(errors, i, "块级公式 \\[ \\] 禁止使用，改为行内 $...$")
        if re.search(r"\\begin\{", s):
            add(errors, i, "不允许 LaTeX 环境（\\begin{...}）")
        for cmd in FORBIDDEN_CMDS:
            if cmd in s:
                add(errors, i, "出现丙档/禁用命令：%s" % cmd)
        for w in VAGUE:
            if w in s:
                add(errors, i, "出现模糊词：%s" % w)
        for w in VAGUE_WARN:
            if w in s:
                add(warns, i, "含「%s」，确认不是模棱两可的表述" % w)
        for w in LEAK:
            if w in s:
                add(errors, i, "交付文件泄漏质检字段：%s" % w)
        if s.count("$") % 2 == 1:
            add(errors, i, "$ 个数为奇数，行内公式未闭合")
        for m in re.finditer(r"\$([^$]*)\$", s):
            body = m.group(1)
            if any(ch in FULLWIDTH for ch in body):
                add(errors, i, "公式内含全角标点：%s" % body)
            if re.search(r"[\u4e00-\u9fff]", body):
                add(warns, i, "公式内含中文：%s" % body)
            if "=" in body and re.match(r"\s*" + UNIT_RE, s[m.end():]):
                add(errors, i, "算式结果单位须置于公式外的全角括号中，如 $12\\times3=36$（平方厘米）")
            if "=" in body and re.search(r"\\(?:mathrm|text)\{(?:cm|mm|km|m|kg|g|ml|L|min|s)\}(?:\s*\^\s*(?:\{[23]\}|[23]))?\s*$", body):
                add(errors, i, "算式结果的单位须移到公式外并加全角括号")
        if re.search(r"(?:=|＝)\s*[+-]?\d+(?:\.\d+)?\s*" + UNIT_RE, re.sub(r"\$[^$]*\$", "", s)):
            add(errors, i, "算式结果后的单位未加全角括号")
        if re.search(r"[\u4e00-\u9fff]\$", s) or re.search(r"\$[\u4e00-\u9fff]", s):
            add(warns, i, "公式与中文之间建议留一个半角空格")
        # 标准脱式及方程允许用单美元符号独立逐行，不因此产生警告。
        formula_line = r"\s*\$[^$]+\$(?:（[^）]+）)?\s*"
        if (kinds.get(i) == "calculation" and i < len(lines)
                and re.fullmatch(formula_line, s)
                and re.fullmatch(formula_line, lines[i])
                and not s.endswith("  ")):
            add(errors, i, "连续脱式行须在行末保留两个空格，确保Markdown实际逐行显示")


def split_blocks(lines):
    blocks, cur, start = [], [], 1
    for i, s in enumerate(lines, 1):
        if TITLE_RE.match(s):
            if cur:
                blocks.append((start, cur))
            cur, start = [s], i
        else:
            cur.append(s)
    if cur:
        blocks.append((start, cur))
    return blocks


def section_kinds(lines):
    """记录每行所属题型；统计/应用题表格不按计算题表格误判。"""
    kinds, current, section = {}, "", ""
    for i, line in enumerate(lines, 1):
        if re.match(r"^##\s+第\s*\d+", line):
            # 下一大题恢复章级题型，不继承上一题小题的“计算”状态。
            current = section
        heading = re.match(r"^#{1,6}\s+(?!第\s*\d)(.+)", line)
        if heading:
            text = heading.group(1)
            if re.search(r"填空|选择", text):
                current = "objective"
            elif re.search(r"计算|口算|求值|解方程|脱式|简算|简便运算", text):
                current = "calculation"
            elif re.search(r"解答|解决问题", text):
                current = "solution"
            elif re.search(r"判断|操作|实践|统计|知识点清单|快速对答案|详解详析", text):
                current = ""
            if not re.match(r"[（(]\d+[）)]", text):
                section = current
        kinds[i] = current
    return kinds


def check_blocks(lines, new_terms):
    kinds = section_kinds(lines)
    for start, block in split_blocks(lines):
        if not TITLE_RE.match(block[0] or ""):
            continue
        title = block[0]
        if not re.match(r"^##\s+第\s*\d+", title.strip()):
            continue
        joined = "\n".join(block)
        is_kousuan = "口算" in title
        is_jieda = "解：" in joined  # 解答题用「解：」，计算题可直接写脱式。
        kind = kinds.get(start, "")
        if re.search(r"填空|选择", title):
            kind = "objective"
        elif re.search(r"计算|口算|求值|解方程|脱式|简算|简便运算", title):
            kind = "calculation"
        elif re.search(r"解答|解决问题", title):
            kind = "solution"
        # 解答题大章中的纯计算大题，也允许没有“解：”的直接脱式。
        if kind == "solution" and not is_jieda and re.search(
                r"^#{3,6}\s+.*(?:计算|求值|解方程|脱式|简算|简便运算)", joined, re.M):
            kind = "calculation"

        number = re.match(r"^##\s+第\s*(\d+)", title.strip()).group(1)
        # 跳过结构标题和空行，检查首个正文段，而非只检查独立的题目标题。
        first = next(((offset, line) for offset, line in enumerate(block[1:], 1)
                      if line.strip() and not re.match(r"^#{1,6}\s", line)), None)
        if first:
            offset, line = first
            visible = line.replace("**", "").strip()
            label = re.match(r"\s*(\d+)\s*\.\s*(\S.*)", visible)
            if not label:
                add(errors, start + offset, "每题正文首段须以题号.开头，并与首个栏目或答案同行")
            elif int(label.group(1)) != int(number):
                add(errors, start + offset, "正文题号与第%s题标题不一致" % number)

        if kind == "objective" and "【解析】" in joined and not is_jieda:
            for offset, line in enumerate(block):
                if "【解析】" in line:
                    prefix = line.split("【解析】", 1)[0].strip("* \t")
                    prefix = re.sub(r"^\d+\s*\.\s*", "", prefix).strip("* \t")
                    if not prefix:
                        add(errors, start + offset, "填空题、选择题答案须与【解析】同一行、同一段紧接排写")
                    if re.search(r"[;；]", re.sub(r"\\[;,]", "", prefix)):
                        add(errors, start + offset, "多空答案用空格隔开，答案部分不要使用分号")
                    break

        if kind == "calculation" and not is_kousuan:
            process = joined.split("【题型归类】", 1)[0]
            if re.search(r"^\s*\|", process, re.M) or re.search(r"<table\b", process, re.I):
                add(errors, start, "计算过程禁止使用表格，改为普通逐行脱式")
            if re.search(r"^\s*(?:```|~~~)", process, re.M):
                add(errors, start, "计算过程禁止放入代码块，改为普通逐行脱式")

        has_analysis = "【解析】" in joined
        if (kind in ("calculation", "solution") or is_jieda or is_kousuan) and has_analysis:
            add(errors, start, "计算题和解答题不加【解析】；只在原题型内容最前面加题号")
        if kind == "objective" and not has_analysis and "【题目核查】" not in joined:
            add(errors, start, "选择题、填空题缺少【解析】栏目")
        if kind == "solution" and not is_jieda and "【题目核查】" not in joined:
            add(errors, start, "解答题应以「解：」写过程，不改用【解析】")
        if "【题型归类】" not in joined:
            add(errors, start, "缺少【题型归类】栏目")
        else:
            check_taxonomy(joined, start, new_terms)

        idx = {}
        for kw in PRE_ANSWER + POST_ANSWER + ["【解析】", "解：", "答："]:
            pos = joined.find(kw)
            if pos >= 0:
                idx[kw] = pos
        # 答案锚点：填空题/选择题看【解析】，解答题看「答：」
        anchor_pre = idx.get("【解析】", idx.get("答："))
        anchor_post = idx.get("【解析】", idx.get("解："))
        if anchor_pre is not None:
            for kw in PRE_ANSWER:
                if kw in idx and idx[kw] > anchor_pre:
                    add(errors, start, "%s 应放在答案之前" % kw)
        if anchor_post is not None:
            for kw in POST_ANSWER:
                if kw in idx and idx[kw] < anchor_post:
                    add(errors, start, "%s 应放在答案之后" % kw)


def check_quick_answers(lines):
    """快速对答案采用表式；只查该节，不误判详解中的解释分号。"""
    for start, line in enumerate(lines):
        if not re.match(r"^#{1,6}\s+快速对答案\s*$", line):
            continue
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^#{1,6}\s", lines[i])), len(lines))
        body = lines[start + 1:end]
        joined = "\n".join(body)
        markdown_table = any(re.match(r"\s*\|?\s*:?-+:?\s*\|", s) for s in body)
        html_table = re.search(r"<table\b", joined, re.I)
        if not markdown_table and not html_table:
            add(errors, start + 1, "快速对答案须直接采用表格排写")
        # 填空行可用<br>换行，仍在同一Markdown物理行；HTML按行元素识别。
        rows = re.findall(r"<tr\b[^>]*>.*?</tr>", joined, re.I | re.S) if html_table else body
        for row in rows:
            if "填空" in row and re.search(r"[;；]", re.sub(r"&(?:#\d+|#x[0-9a-f]+|[a-z]+);|\\[;,]", "", row, flags=re.I)):
                add(errors, start + 1, "快速答案表中多空答案用空格隔开，不用分号")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    if not args:
        print("用法：python lint_md.py <file.md> [--strict]")
        return 2
    path = args[0]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()

    scan_lines(lines)
    new_terms = []
    check_blocks(lines, new_terms)
    check_quick_answers(lines)

    if "快速对答案" not in text:
        add(warns, 0, "缺少「快速对答案」汇总节（如客户不需要可忽略）")
    if new_terms and "新增知识点清单" not in text:
        add(warns, 0, "本题卷标了 %d 处%s，文末缺少「新增知识点清单」汇总节"
            % (len(new_terms), NEW_TAG))
    if not new_terms and "新增知识点清单" in text:
        add(warns, 0, "有「新增知识点清单」但正文未出现%s，二者应一致" % NEW_TAG)

    for ln, msg in sorted(errors, key=lambda x: x[0]):
        print("ERROR  行%-5s %s" % (ln or "-", msg))
    for ln, msg in sorted(warns, key=lambda x: x[0]):
        print("WARN   行%-5s %s" % (ln or "-", msg))
    print("-" * 56)
    if new_terms:
        print("〔新拟〕知识点 %d 处：%s" % (
            len(new_terms),
            "、".join("%s(行%s)" % (n, l) for l, n in new_terms)))
    print("错误 %d 项，警告 %d 项" % (len(errors), len(warns)))
    if errors or (strict and warns):
        print("结果：不通过（ERROR 必须清零才能交付）")
        return 1
    print("结果：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
