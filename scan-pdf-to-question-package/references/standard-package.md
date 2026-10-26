# 标准题库包 1.0

## ZIP 结构

ZIP 根目录必须包含 UTF-8 编码的 `manifest.json`。推荐结构：

```text
manifest.json
sources/s001/original.pdf
images/s001/q0005_figure_01.png
images/s001/q0010_figure_01.png
```

`images/` 只存必要插图，不存每道题的完整截图。原始正文 PDF 可选。路径必须使用 ZIP 内相对路径和 `/`，禁止绝对路径、反斜杠和 `..`。

## 顶层字段

- `schema_version`：必须为字符串 `1.0`。
- `sources`：非空题源数组。
- `questions`：非空题目数组。

## 题源字段

- `source_id`：包内唯一，只能含英文字母、数字、下划线和连字符。
- `name`：题目出处或试卷名称，例如 `2026年工大附中001`。
- school_name：学校名称。从文件名去掉开头年份（如 2026年 或 2026）和末尾卷号（如 001）后提取；无法可靠判断时填写空字符串，并在交付说明列待核对。
- `original_file`：可选，原始正文 PDF 在 ZIP 内的路径。

## 题目字段

- `question_id`：包内唯一，格式同 `source_id`。
- source_name：上传 PDF 文件名（不含扩展名），必须与对应 sources[].name 完全相同。
- school_name：学校名称，必须与对应 sources[].school_name 完全相同；无法确认时填写空字符串。
- `source_id`：必须对应 `sources` 中的题源。
- `original_number`：原卷题号，字符串，必填。
- `question_type`：题型字符串。
- `stem`、`answer`、`analysis`：Markdown 字符串，数学公式使用 LaTeX。
- `knowledge_points`：知识点数组，每项完整包含 `level_1`、`level_2`、`level_3`。
- `difficulty`：`基础`、`进阶`、`高阶` 或空字符串。
- `source_pages`：从 1 开始的原卷页码数组。
- `images`：必要插图路径数组，支持 PNG、JPG、JPEG、WEBP；纯文字题填写 `[]`。

每题必须有非空 `stem`。不要依赖整题截图代替可识别的题干文字。

## 图片判断示例

- 分数计算题：公式写入 `stem`，`images: []`。
- 纯文字行程题：题干写入 `stem`，`images: []`。
- 几何题：题干和已知条件写入 `stem`，只把几何图保存到 `images`。
- 统计题：能用 Markdown 准确表达的简单表格不截图；统计图、扇形图等保存为插图。
- 图形规律题：题干文字写入 `stem`，图形序列保存为插图。

## 示例

```json
{
  "schema_version": "1.0",
  "sources": [
    {
      "source_id": "s001",
      "name": "2026年工大附中001",
      "school_name": "工大附中",
      "original_file": "sources/s001/original.pdf"
    }
  ],
  "questions": [
    {
      "question_id": "q0001",
      "source_id": "s001",
      "source_name": "2026年工大附中001",
      "school_name": "工大附中",
      "original_number": "1",
      "question_type": "计算题",
      "stem": "计算 $\\frac{2}{3}+\\frac{1}{4}$。",
      "answer": "$\\frac{11}{12}$",
      "analysis": "通分后相加。",
      "knowledge_points": [
        {"level_1": "计算", "level_2": "分数巧算", "level_3": "分数加减巧算"}
      ],
      "difficulty": "基础",
      "source_pages": [1],
      "images": []
    },
    {
      "question_id": "q0005",
      "source_id": "s001",
      "original_number": "5",
      "question_type": "几何题",
      "stem": "如图，已知梯形 $ABCD$ 的面积和两底长度，求指定三角形面积。",
      "answer": "8 平方厘米",
      "analysis": "利用同高三角形面积比等于底边比。",
      "knowledge_points": [
        {"level_1": "几何", "level_2": "三角形面积", "level_3": "同高面积比"}
      ],
      "difficulty": "基础",
      "source_pages": [1],
      "images": ["images/s001/q0005_figure_01.png"]
    }
  ]
}
```

## 知识点

不要直接把完整 `knowledge_points.json` 载入模型上下文。每批题目使用 `scripts/find_knowledge.py` 以多个关键词一次检索候选路径，再从候选中选择。最终路径仍必须与目录逐字一致；一道题允许多个路径，也允许暂时为空数组。

## 校验和打包

```powershell
python scripts/package_folder.py C:\path\to\package C:\path\to\result.zip
```

脚本检查字段、题源引用、知识点、资源文件和 ZIP 路径安全。退出码为 0 才表示格式通过；格式通过不代表模型生成答案已经人工确认。
