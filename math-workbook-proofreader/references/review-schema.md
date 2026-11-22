# review.json 格式

使用 UTF-8 JSON，顶层包含文档信息和问题数组：

```json
{
  "document": {
    "title": "六年级数学第一单元",
    "notes": "AI 辅助校对，数学公式及结论请人工复核"
  },
  "issues": [
    {
      "id": 1,
      "kind": "suspected",
      "category": "题答不一致",
      "questionId": "第3章-练习2-第4题",
      "title": "正文与解析使用的数据不一致",
      "detail": "正文为360米，答案解析中使用了3600米。",
      "suggestion": "核对答案解析数据并重新计算。",
      "targets": [
        {
          "document": "body",
          "page": 8,
          "bbox": {"x": 0.12, "y": 0.20, "width": 0.72, "height": 0.08}
        },
        {
          "document": "answer",
          "page": 36,
          "bbox": {"x": 0.10, "y": 0.42, "width": 0.76, "height": 0.12}
        }
      ]
    }
  ]
}
```

## 字段约束

- `id`：从 1 开始的唯一整数，按页码和页面内阅读顺序递增。
- `kind`：只能是 `confirmed`、`suspected` 或 `suggestion`。
  分别显示为红色确定错误、黄色待人工复核、蓝色优化建议。新流程 confirmed 必须经过 recheck；不能把 AI 与原稿不同直接标红。
- `category`：简短分类，例如错别字、语病、数学逻辑、公式符号、图文对应、答案一致性、格式规范。
- `questionId`：尽可能稳定的题目标识，由章节、题型和题号组成；无法确定时使用空字符串。
- `title`：右侧清单中首先显示的一句话结论。
- `detail`：说明原文、冲突或判断依据，不要只写“有误”。
  保留原文与必要的一句依据，避免长篇说明。
- `suggestion`：可执行的修改或人工复核建议；没有可靠改法时说明应核对什么。
- `targets`：至少一个位置。单文档问题只有一个；题答不一致通常同时包含正文和答案位置。
- `targets[].document`：必须对应 `manifest.json` 中的文档 `id`，通常为 `body` 或 `answer`。
- `targets[].page`：该文档内从 1 开始的 PDF 页码，正文页码与答案页码互不对应。
- `targets[].bbox`：页面左上角为原点的归一化矩形，`x/y/width/height` 均为 0-1；无法可靠定位时使用 `null`。

若未找到可靠对应答案，只保留正文 target，并将 `kind` 设为 `suspected`，在 `detail` 中说明配对不确定。不要创建虚假的答案 target。

不要写入 Markdown、注释、尾随逗号或未经转义的换行。

新流程由 audit_run.py export 生成 review.json，包含 audit_version 和 draft；build 从收据核对，不能手写覆盖状态绕过门槛。未完成只能导出阶段稿。旧格式仍兼容但显示覆盖未知。单页多个不同 bbox 可以作为多个 targets；完全重复位置不允许。
