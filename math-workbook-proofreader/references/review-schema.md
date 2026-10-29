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
      "page": 3,
      "kind": "suspected",
      "category": "图文对应",
      "title": "图示长度与题意不一致",
      "detail": "图中两端标注的 8 米比例明显大于全长的八分之一。",
      "suggestion": "核对图示比例或改为示意图标注。",
      "bbox": {
        "x": 0.13,
        "y": 0.18,
        "width": 0.73,
        "height": 0.22
      }
    }
  ]
}
```

## 字段约束

- `id`：从 1 开始的唯一整数，按页码和页面内阅读顺序递增。
- `page`：从 1 开始的 PDF 页码。
- `kind`：只能是 `confirmed`、`suspected` 或 `suggestion`。
- `category`：简短分类，例如错别字、语病、数学逻辑、公式符号、图文对应、答案一致性、格式规范。
- `title`：右侧清单中首先显示的一句话结论。
- `detail`：说明原文、冲突或判断依据，不要只写“有误”。
- `suggestion`：可执行的修改或人工复核建议；没有可靠改法时说明应核对什么。
- `bbox`：页面左上角为原点的归一化矩形，`x/y/width/height` 均为 0-1；无法可靠定位时使用 `null`。

不要写入 Markdown、注释、尾随逗号或未经转义的换行。
