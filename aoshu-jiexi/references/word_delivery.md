# 可编辑公式的Word交付

最终解析、质检均为docx，Markdown/JSON是工作源稿，不默认交付。数学表达使用Word原生OMML（m:oMath）；普通斜杠分数、截图、PNG或残留LaTeX不满足可编辑上下分式要求。

## 导出工具

`scripts/export_docx.py INPUT.json OUTPUT.docx` 使用python-docx、lxml，内置严格初等公式子集转换器。通过工作区依赖工具定位当前Python。未知语法会报错，不丢符号、不降级为图片。它不是完整LaTeX引擎，超出支持范围时改用经验证的其他原生OMML路径。

JSON示例：

```json
{
  "title": "示范卷解析",
  "sections": [{
    "label": "二、填空题",
    "kind": "fill",
    "questions": [{
      "number": "6",
      "answer": "$\\frac{9}{4}$",
      "paragraphs": ["**6. $\\frac{9}{4}$【解析】** 每份为 $9\\div4=\\frac{9}{4}$。"],
      "taxonomy": "归一归总"
    }]
  }]
}
```

- kind为choice/fill/calculation/solution/other。number保留原卷小题号，同一大题不重复，不同大题可重号。
- answer是核定答案字符串，数学用`$...$`；多空用空格，存疑用null（卷头显示待核）。多选加`"multiple": true`，卷头逐题编号。
- paragraphs为正文段落列表，作者按format_spec写题号/栏目。段内换行是真正换行；仅支持`**加粗**`与`$公式$`，不支持其他Markdown语法。
- taxonomy写具体模型。有新拟则顶层new_models为列表，每项name/feature/source/category，对应卷末登记。
- 可选figure为相对JSON目录或绝对图像路径，figure_caption为图注；题图的字母和点位须正确，不用该字段装公式截图。
- 可选quick_note只作详解提示；工具拒绝静态页码，默认不带页码。确需页码时用经更新核对的交叉引用或独立排版流程。
- 顶层`"mode": "qa"`可输出质检：不加快速表、不加题型归类、不加“详解详析”。段落自行填完整质检内容。

支持数字、拉丁变量、基本运算、括号、frac/dfrac、上下标及组合、times/div/pi/parallel/perp/triangle/angle/circ/cdot/cdots/dots/%等命令。未知命令、未闭合美元符号/花括号和非法控制字符会终止导出。源码中的Unicode数学运算符也可用；不能把中文说明塞在公式里。

## 验收顺序

1. 先按selfcheck验数学和表达，导出不证明解答正确。
2. 检查ZIP、必需包部件、全部XML解析、Document重开；源公式与实际OMML数量一致。工具按生成前后的公式结构签名核对，防止丢公式或顺序变化。
3. 对照源稿查分子分母、上下标、运算符、括号及项序；分数必须是m:f，不能只看OMML总数。无LaTeX命令或美元符号泄漏。
4. 优先用documents技能和load_workspace_dependencies定位可用渲染器。使用LibreOffice时遵守该技能的运行时选择要求，不静默改用用户桌面版本。也可用已验证的Word/WPS把本任务新文档导出PDF，再生成逐页图；不影响用户已有文档。
5. 逐页看最终版的表框/换行、题号与答案、分式/上下标、脱式、图文关系和分页；每次内容或布局改动后重新渲染。
6. 无渲染器时写明具体限制，保留待验收状态，不把结构通过说成完整验收；不交改后缀、图片或PDF冒充Word。

脚本输出“结构检查通过”只代表包结构和公式转换检查，不意味着数学正确、已渲染或适合印刷。最终报告实际完成的检查及仍未完成的事项。
