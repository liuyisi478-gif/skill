# 六阶段产物协议

脚本不识题、不调用模型。Codex 打开图像并生成判断；脚本验证逐题/逐页/逐步覆盖、引用、顺序和产物完整性。证据可追溯不等于机器证明数学判断正确。

## 存储与提交

manifest.json 固定输入。packets/<token>.json 是最小任务包，receipts/<token>.json 是原始结果，audit-state.json 保存阶段、结果 SHA256、包引用、墙钟耗时和可得 usage。阶段快照：

| 阶段 | 文件 |
| --- | --- |
| inventory | questions.json |
| independent | independent_answers.json |
| answer_inventory | answer_questions.json |
| answer_audit | answer_audit.json |
| comparison | comparisons.json |
| recheck | rechecks.json |

coverage.json 由收据推导，不能直接写 checked 代替执行产物。review.json 由 export 汇总，build 重新校验。同一目录不要并发写；提交其他包后旧包失效。每批只含1–5题，通常3–5题，结构清点阶段例外。封存数据不覆盖；输入变更开新目录。临时文件替换保证单文件写入；断电造成快照不一致时用 repair 从已提交收据恢复快照，不修改收据。

失败题仅在下游尚未使用该结果前可原阶段重试，原失败收据保留，快照采用最后一次尝试；成功题不重做。尤其独立解题一旦已进入答案识别，即使失败也不能在看过答案后重写，只能保留失败状态和复核说明。清单识别修订/重新分题用新运行。

所有结果顶层为 `{"records":[...],"usage":null}`。每条都有稳定 id（章节/栏目/题号/小题，不能只用全书重复的“1”）、status:ok|uncertain|failed、uncertainties:[]；不确定和失败须说明原因。

原稿位置沿用 targets:[{document:"body",page:1,bbox:{x:0.1,y:0.2,width:0.8,height:0.1}}]。页码为1起始 PDF 真页码；印刷页码另存。跨页同 id 保留所有页和区域，不强制每题截图。同页不同 bbox 可同时标注。

views:[{document,page,bbox:null,image_sha256,tool_ref}] 保存图像查看证据。指纹取 manifest，tool_ref 记录实际图像查看调用。先看完整页，再对疑点局部查看；必要局部图记录原页区域。程序仅验证文件指纹，不能验证任意工具引用真实性，须保留调用日志。不允许把生成图片当作查看图片。

## 1. inventory / answer_inventory

正文记录示例（views 填实际证据）：

```json
{"id":"第一章-练习1-Q1","status":"ok","uncertainties":[],
 "section":"第一章/练习1","number":"1","stem":"计算1/2+1/4。",
 "type":"计算","options":[],"figures":[],"complex_figure":false,
 "targets":[{"document":"body","page":1,"bbox":null}],
 "views":[{"document":"body","page":1,"bbox":null,"image_sha256":"原图指纹","tool_ref":"实际调用引用"}]}
```

figures 保存可见标注、节点、连线、方向和全部约束。不要按视觉比例推断长度。按章节清点题号/小题/空格/选项，跨页续题依上下文合并；不确定断题用 uncertain，不能造题。

识别结果顶层还需 pages，每个 PDF 页一条：{document,page,printed_page,role,question_ids,anomalies,views,reason}。role 为 body/answer/mixed/front/blank；question_ids 包括本页出现或续接的稳定 id；无题页必须有 reason。anomalies 是跳号、重复号、印刷页码断裂、未闭合跨页等列表。脚本核对所有文件页、题目区域与页清单双向一致。源文件本身缺页只能靠印刷页码/目录/题号线索提示，不能保证发现所有物理缺页。

先做正文 inventory；合订本答案页仅标角色和原因，先不读具体答案。

全部独立解题记录提交后做 answer_inventory，每个正文 id 一条：

- match:matched|unpaired|ambiguous|not_supplied；match_reason 写章节/题号/关键数据证据。
- matched 时有唯一 answer_id、原 answer_number、source_answer、source_steps、answer，以及答案 targets/views。共用解析拆为对应子项，不能重复使用同一 answer_id。
- source_steps 按可核查步骤保存原文字符串列表，连等式拆到每个等号；仅最终答案时为空数组。
- answer 采用值/单位数组；未配对不可编答案，status=uncertain，targets 暂留正文位置。
  整份输入确实未提供答案（也无合订答案页）时可用 not_supplied、status=ok，后续答案阶段只记“不适用”，不重复解题。该情况不自动触发冲突复核，覆盖仍显示原稿答案/步骤未检查。已提供答案但缺某题不能用 not_supplied。
- pages 含所有文档页，可复用正文已核实的页清点和看图证据。这次 question_ids 表示该页答案对应的正文 id，纯正文页可空并说明。未匹配原稿答案放在页记录 unmatched_answers 列表，记录原题号、原文、位置、原因。第4阶段按倒序逐项核对，不能漏掉孤立答案。

## 2. independent

每题 answer:[{value:"3/4",unit:""}]、reasoning（短而足以重算）、body_checks:{language,conditions,figure,ambiguity,units}。检查值必须是简短依据/不适用原因，不能仅 true。正文问题写 uncertainties，比较阶段汇入批注。多空按正文顺序记录，单位单存。失败 answer=[]，说明缺少的条件。

只打开本批正文包和所指图像。提交后不改写；发现 AI 错误，在 recheck 中记 corrected_independent_answer（同样为 value/unit 数组）。HTML 侧栏精简答案优先显示成功复核后的更正值并注明“已更正”，详细记录中仍保留封存的原独立答案。待人工或失败复核不能作为已确定的更正答案。

## 3. answer_audit

包中没有 independent。每题 reasoning、steps:[{source:"原稿步骤",verdict:"valid|invalid|uncertain",reason:"验算/推理依据"}]、final_check、grade_check。steps 与 source_steps 一一相等；不能漏中间错误。重要计算引用 calculations.jsonl 或保留独立 Python 脚本和真实输出。只有最终数值的答案 steps=[]，标 final_only，不声称检查了不存在的推导。

脚本自动对纯数值等式及连等式的每个环节进行精确验算，program_checks 随阶段结果封存。即使模型把错误等式写为 valid，程序发现 invalid 仍强制触发复核；不自动判原稿错，以免把转写错误当原稿错误。带文字、变量、约等于的步骤返回 unknown，需要数学核查，不冒充程序已验证。

逐空反代正文，检查数量/对象/单位/答句。图形验证每条边、共享节点、连线、给定数和全部约束。未匹配答案 status=uncertain/failed，不能为 ok。

## 4. comparison

每题 reasoning、answer_vs_solution（原稿答案与解析结论）、derivation（过程能否推出结果）、conditions_vs_figure、review_reasons:[]、issues:[]。numeric_comparison 的 equal/different/unknown 只作线索。different 不直接标红；unknown 要数学核验或重点复核。数组保留顺序，不交换空格、不猜单位换算。带分数、变量、集合、多解、舍入、近似值、不同单位保留原文和判断依据，不能字符串不同报错。

issues 沿用 review-schema，不需 id，questionId 等于当前稳定 id。本阶段只能 suspected/suggestion，confirmed 必须第5阶段复核。孤立答案也须逐条核查并在 structure_review 中记录结果，必要批注到答案原位置。

## 5. recheck

status 的 doubts 从识别/解题/配对/步骤/比较状态、数值冲突或未知、复杂图形和发现自动触发。其他疑点主动写 review_reasons。一次复核应增加新证据；必要多次验算可放同条 verification，不进行无意义重复。

每题 reasoning、views（双方对应原图重新打开）、verification（工具验算/另一思路/全图约束，或不能确认的具体原因）、outcome:confirmed|cleared|manual、issues（该题最终全部批注，包括保留蓝色建议；空数组表示撤销）。明确原稿证据才 confirmed；仍有疑问用 manual+黄色；AI 错原稿对用 cleared，不能报原稿错误。转写修正在 corrected_transcription，不能抹掉历史。

## 6. 输出门槛

export 拒绝缺阶段、失败题、缺必要复核；--draft 可输出阶段稿并自动增加未完成黄色批注。已经复核但仍需人工可出最终稿，状态 manual。明确失败的独立求解仍显示未完成，不能用批注替代解题。

覆盖推导字段：recognized、answer_matched、independent_solved、answer_checked、steps_checked（steps_mode 区分 final_only）、doubts、annotated、manual_review、missing、complete。完成不等于无错；无批注不等于完成。遗留 review 无审计数据时仅显示覆盖未知。

## 测试与评测边界

运行 `python -m unittest discover -s tests -v`。测试使用明确标注的模拟数据，验证算术、隔离/门禁、封存、漏页/漏题/跨页、步骤覆盖、AI错误撤销、批注和旧版兼容。模拟阶段记录只能证明流程行为，不能证明模型真实检出率。真实效果须用独立标准稿盲测，记录 TP/FN/FP、逐题覆盖、人工核准位置、耗时及可得 usage。无真实运行/日志写未知，不能报告虚构提升。
