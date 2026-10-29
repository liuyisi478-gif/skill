---
name: math-workbook-proofreader
description: 校对小学和初中数学教辅 PDF，并生成适合编辑照着纸质稿誊红的带定位批注 HTML。用于用户要求检查题干、解析、答案、公式、图文对应或教辅文字规范时；不用于改写原 PDF、稿件管理或调用外部 AI API。
---

# 数学教辅 PDF 校对

生成一次性的本地 HTML 校对稿：左侧保留原页视觉，叠加定位框；右侧列出问题。Codex 负责校对判断，本地脚本只负责 PDF 预处理和网页生成。不得调用 OpenAI API 或其他外部模型 API。

## 工作流程

1. 确认用户指定的 PDF。若目录中只有一个 PDF，直接使用；若有多个且无法可靠判断正文文件，询问一次。
2. 保留源 PDF，不覆盖、不改写。运行：

   ```powershell
   python scripts/prepare_pdf.py "<输入.pdf>" --work-dir "<工作目录>"
   ```

3. 阅读 `references/proofreading-rules.md`。结合工作目录中的 `manifest.json`、每页文字块和页面 PNG 逐页校对。提取文字只是辅助，页面图像才是版面、公式和图形的依据。
4. 按 `references/review-schema.md` 创建 UTF-8 `review.json`。长稿按 4-8 页一批检查，最终合并并连续编号。
5. 对能够明确定位的问题填写归一化 `bbox`；只能确定页码时将 `bbox` 设为 `null`，不得猜测坐标。
6. 运行：

   ```powershell
   python scripts/build_review.py --work-dir "<工作目录>" --review "<review.json>" --output "<输出目录>"
   ```

7. 检查脚本输出的计数，并打开 `index.html` 验证：页面清晰、问题列表可点击、定位框与原文对齐、适宽和缩放按钮有效。至少抽查首页、中间页和末页。

## 判断边界

- 将有明确依据的错误标为 `confirmed`；合理但不能确定的问题标为 `suspected`；纯表达改进标为 `suggestion`。
- 公式、上下标、分式、根式、图形标注和扫描文字容易误识别。信息不足时降低确定性，并明确写出复核点。
- 同时核对题干、解析、图形和答案之间的一致性，但不要仅凭答案不同就断言原稿错误。
- 不为了增加数量而生成批注。若未发现问题，可输出空问题列表。
- HTML 仅用于本次纸质誊红，不添加编辑、登录、数据库、稿件历史或“打开原稿 PDF”按钮。

## 输出

输出目录包含 `index.html`、`review-data.js`、页面图片和静态资源。它可以复制到其他电脑直接查看；生成新的 AI 校对结果仍需在 Codex 中调用本 Skill。
