# 补充批次轨迹完整性核对

本报告按每个新增模型批次应有 **900 条攻击轨迹 + 300 条 benign baseline = 1,200 条** 的规则核对。
归档只保留执行成功的轨迹，因此 `raw_missing` 表示预期 slot 没有成功轨迹文件；它不是补成失败分数。

这 7 个批次已从正式分析输入和派生结果中排除。核对完成后，补充批次的评分 JSON、原始轨迹和归档已从本机清理；本文件与核对汇总只作为审计记录保留。

来源归档（已清理）：`agent_trajectories_mine_20260925.tar.gz`。7 个批次应有 8,400 条，实际归档 8,306 条，缺 **94 条**：攻击缺 68 条，benign 缺 26 条。

## 批次总览

| 批次 | 模型 | 攻击 raw | benign raw | 实际总数 | 缺失总数 | 攻击评分 valid/error | UGS 行数 | 标记 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `openclaw_gpt-5.4` | GPT-5.4 | 873/900 (-27) | 300/300 (-0) | 1173/1200 | -27 | 872/28 | 165/300 | **INCOMPLETE** |
| `openclaw_gpt-5.6-sol` | GPT-5.6-Sol | 892/900 (-8) | 300/300 (-0) | 1192/1200 | -8 | 891/9 | 174/300 | **INCOMPLETE** |
| `openclaw_gpt-5.6-terra` | GPT-5.6-Terra | 896/900 (-4) | 298/300 (-2) | 1194/1200 | -6 | 896/4 | 298/300 | **INCOMPLETE** |
| `openclaw_gpt-5.6-luna` | GPT-5.6-Luna | 899/900 (-1) | 299/300 (-1) | 1198/1200 | -2 | 899/1 | 299/300 | **INCOMPLETE** |
| `openclaw_grok-4.3` | Grok-4.3 | 898/900 (-2) | 299/300 (-1) | 1197/1200 | -3 | 898/2 | 300/300 | **INCOMPLETE** |
| `openclaw_minimax-m2.5` | MiniMax-M2.5 | 882/900 (-18) | 279/300 (-21) | 1161/1200 | -39 | 882/18 | 206/300 | **INCOMPLETE** |
| `openclaw_deepseek-v4-flash-0731` | Deepseek-v4-Flash-0731 | 892/900 (-8) | 299/300 (-1) | 1191/1200 | -9 | 892/8 | 299/300 | **INCOMPLETE** |

`UGS 行数`是已导入 UGS 评分文件中的 benign 行数，不等同于归档中的 benign 文件数。归档文件存在但没有 UGS 行的 task 在下方标为 `ugs_score_not_included`。

## 逐批次标记

### GPT-5.4 (`openclaw_gpt-5.4`)

归档：攻击 873/900，benign 300/300，共 1173/1200；缺失 27。攻击评分 valid/error = 872/28；其中已有 raw 但评分失败 1 条。UGS 评分行 165/300。

**raw 缺失的攻击 slot：**

`B1/task_B1_T08/run_1 B1/task_B1_T09/run_2 B1/task_B1_T29/run_1 B1/task_B1_T29/run_3 B3/task_B3_T10/run_3`
`B3/task_B3_T20/run_1 B10/task_B10_T02/run_1 B10/task_B10_T02/run_3 B10/task_B10_T08/run_2`
`B11/task_B11_T12/run_1 B11/task_B11_T13/run_2 B12/task_B12_T03/run_2 B12/task_B12_T07/run_1`
`B12/task_B12_T08/run_1 B12/task_B12_T13/run_1 B12/task_B12_T14/run_1 B13/task_B13_T01/run_1`
`B13/task_B13_T01/run_2 B13/task_B13_T01/run_3 B13/task_B13_T10/run_3 B13/task_B13_T11/run_1`
`B14/task_B14_T06/run_1 B14/task_B14_T06/run_2 B14/task_B14_T10/run_1 B14/task_B14_T10/run_2`
`B14/task_B14_T10/run_3 B15/task_B15_T10/run_2`

benign task：没有 raw 缺失。

**有 raw 但攻击评分失败：**

`B8/task_B8_T23/run_1` (judge_failure)

**归档中存在、但 UGS 未纳入的 benign task（135 条）：**

`task_B1_T01`[score_source_subset_absent] `task_B1_T02`[score_source_subset_absent] `task_B1_T03`[score_source_subset_absent] `task_B1_T04`[score_source_subset_absent] `task_B1_T05`[score_source_subset_absent] `task_B1_T06`[score_source_subset_absent] `task_B1_T07`[score_source_subset_absent] `task_B1_T08`[score_source_subset_absent] `task_B1_T09`[score_source_subset_absent] `task_B1_T11`[baseline_cache_only] `task_B1_T12`[score_source_subset_absent] `task_B1_T13`[score_source_subset_absent] `task_B1_T14`[score_source_subset_absent] `task_B1_T15`[score_source_subset_absent] `task_B1_T16`[score_source_subset_absent] `task_B1_T17`[score_source_subset_absent] `task_B1_T18`[score_source_subset_absent] `task_B1_T19`[score_source_subset_absent] `task_B1_T20`[baseline_cache_only] `task_B1_T21`[score_source_subset_absent] `task_B1_T22`[score_source_subset_absent] `task_B1_T23`[score_source_subset_absent] `task_B1_T24`[score_source_subset_absent] `task_B1_T25`[score_source_subset_absent] `task_B1_T26`[score_source_subset_absent] `task_B1_T27`[score_source_subset_absent] `task_B1_T28`[score_source_subset_absent] `task_B1_T30`[score_source_subset_absent] `task_B1_T31`[score_source_subset_absent] `task_B1_T32`[score_source_subset_absent] `task_B1_T33`[score_source_subset_absent] `task_B1_T34`[score_source_subset_absent] `task_B1_T35`[score_source_subset_absent] `task_B1_T36`[score_source_subset_absent] `task_B1_T37`[score_source_subset_absent] `task_B1_T38`[baseline_cache_only] `task_B1_T39`[baseline_cache_only] `task_B1_T40`[score_source_subset_absent] `task_B1_T41`[score_source_subset_absent] `task_B1_T42`[score_source_subset_absent] `task_B2_T01`[score_source_subset_absent] `task_B2_T02`[score_source_subset_absent] `task_B2_T03`[score_source_subset_absent] `task_B2_T04`[baseline_cache_only] `task_B2_T05`[score_source_subset_absent] `task_B2_T06`[score_source_subset_absent] `task_B2_T07`[score_source_subset_absent] `task_B2_T08`[score_source_subset_absent] `task_B2_T09`[score_source_subset_absent] `task_B2_T10`[score_source_subset_absent] `task_B2_T11`[score_source_subset_absent] `task_B2_T12`[score_source_subset_absent] `task_B2_T13`[score_source_subset_absent] `task_B3_T01`[score_source_subset_absent] `task_B3_T03`[score_source_subset_absent] `task_B3_T04`[score_source_subset_absent] `task_B10_T01`[score_source_subset_absent] `task_B10_T02`[score_source_subset_absent] `task_B10_T03`[score_source_subset_absent] `task_B10_T04`[score_source_subset_absent] `task_B10_T05`[score_source_subset_absent] `task_B10_T06`[score_source_subset_absent] `task_B10_T07`[score_source_subset_absent] `task_B10_T08`[score_source_subset_absent] `task_B10_T09`[score_source_subset_absent] `task_B10_T10`[score_source_subset_absent] `task_B10_T11`[score_source_subset_absent] `task_B10_T12`[score_source_subset_absent] `task_B11_T01`[score_source_subset_absent] `task_B11_T02`[score_source_subset_absent] `task_B11_T03`[score_source_subset_absent] `task_B11_T04`[score_source_subset_absent] `task_B11_T05`[score_source_subset_absent] `task_B11_T06`[score_source_subset_absent] `task_B11_T07`[score_source_subset_absent] `task_B11_T08`[score_source_subset_absent] `task_B11_T09`[score_source_subset_absent] `task_B11_T10`[score_source_subset_absent] `task_B11_T11`[score_source_subset_absent] `task_B11_T12`[score_source_subset_absent] `task_B11_T13`[score_source_subset_absent] `task_B11_T14`[score_source_subset_absent] `task_B12_T01`[score_source_subset_absent] `task_B12_T02`[score_source_subset_absent] `task_B12_T03`[score_source_subset_absent] `task_B12_T04`[score_source_subset_absent] `task_B12_T05`[score_source_subset_absent] `task_B12_T06`[score_source_subset_absent] `task_B12_T07`[score_source_subset_absent] `task_B12_T08`[score_source_subset_absent] `task_B12_T09`[score_source_subset_absent] `task_B12_T10`[score_source_subset_absent] `task_B12_T11`[score_source_subset_absent] `task_B12_T12`[score_source_subset_absent] `task_B12_T13`[score_source_subset_absent] `task_B12_T14`[score_source_subset_absent] `task_B12_T15`[score_source_subset_absent] `task_B12_T16`[score_source_subset_absent] `task_B13_T01`[score_source_subset_absent] `task_B13_T02`[score_source_subset_absent] `task_B13_T03`[score_source_subset_absent] `task_B13_T04`[score_source_subset_absent] `task_B13_T05`[score_source_subset_absent] `task_B13_T06`[score_source_subset_absent] `task_B13_T07`[score_source_subset_absent] `task_B13_T08`[score_source_subset_absent] `task_B13_T09`[score_source_subset_absent] `task_B13_T10`[score_source_subset_absent] `task_B13_T11`[score_source_subset_absent] `task_B13_T12`[score_source_subset_absent] `task_B13_T13`[score_source_subset_absent] `task_B13_T14`[score_source_subset_absent] `task_B14_T01`[score_source_subset_absent] `task_B14_T02`[score_source_subset_absent] `task_B14_T03`[score_source_subset_absent] `task_B14_T04`[score_source_subset_absent] `task_B14_T05`[score_source_subset_absent] `task_B14_T06`[score_source_subset_absent] `task_B14_T07`[score_source_subset_absent] `task_B14_T08`[score_source_subset_absent] `task_B14_T09`[score_source_subset_absent] `task_B14_T10`[score_source_subset_absent] `task_B14_T11`[score_source_subset_absent] `task_B15_T01`[score_source_subset_absent] `task_B15_T02`[score_source_subset_absent] `task_B15_T03`[score_source_subset_absent] `task_B15_T04`[score_source_subset_absent] `task_B15_T05`[score_source_subset_absent] `task_B15_T06`[score_source_subset_absent] `task_B15_T07`[score_source_subset_absent] `task_B15_T08`[score_source_subset_absent] `task_B15_T09`[score_source_subset_absent] `task_B15_T10`[score_source_subset_absent] `task_B15_T11`[score_source_subset_absent] `task_B15_T12`[score_source_subset_absent]

### GPT-5.6-Sol (`openclaw_gpt-5.6-sol`)

归档：攻击 892/900，benign 300/300，共 1192/1200；缺失 8。攻击评分 valid/error = 891/9；其中已有 raw 但评分失败 1 条。UGS 评分行 174/300。

**raw 缺失的攻击 slot：**

`B1/task_B1_T29/run_1 B1/task_B1_T29/run_2 B1/task_B1_T29/run_3 B6/task_B6_T25/run_1 B6/task_B6_T25/run_2`
`B7/task_B7_T04/run_1 B7/task_B7_T04/run_3 B9/task_B9_T12/run_3`

benign task：没有 raw 缺失。

**有 raw 但攻击评分失败：**

`B4/task_B4_T06/run_2` (judge_failure)

**归档中存在、但 UGS 未纳入的 benign task（126 条）：**

`task_B1_T01`[baseline_cache_only] `task_B1_T02`[baseline_cache_only] `task_B1_T03`[baseline_cache_only] `task_B1_T04`[baseline_cache_only] `task_B1_T05`[baseline_cache_only] `task_B1_T06`[baseline_cache_only] `task_B1_T07`[baseline_cache_only] `task_B1_T08`[baseline_cache_only] `task_B1_T09`[baseline_cache_only] `task_B1_T10`[baseline_cache_only] `task_B1_T11`[baseline_cache_only] `task_B1_T12`[baseline_cache_only] `task_B1_T13`[baseline_cache_only] `task_B1_T14`[baseline_cache_only] `task_B1_T15`[baseline_cache_only] `task_B1_T16`[baseline_cache_only] `task_B1_T17`[baseline_cache_only] `task_B1_T18`[baseline_cache_only] `task_B1_T19`[baseline_cache_only] `task_B1_T20`[baseline_cache_only] `task_B1_T21`[baseline_cache_only] `task_B1_T22`[baseline_cache_only] `task_B1_T23`[baseline_cache_only] `task_B1_T24`[baseline_cache_only] `task_B1_T25`[baseline_cache_only] `task_B1_T26`[baseline_cache_only] `task_B1_T27`[baseline_cache_only] `task_B1_T28`[baseline_cache_only] `task_B1_T30`[baseline_cache_only] `task_B1_T31`[baseline_cache_only] `task_B1_T32`[baseline_cache_only] `task_B1_T33`[baseline_cache_only] `task_B1_T34`[baseline_cache_only] `task_B1_T35`[baseline_cache_only] `task_B1_T36`[baseline_cache_only] `task_B1_T37`[baseline_cache_only] `task_B1_T38`[baseline_cache_only] `task_B1_T39`[baseline_cache_only] `task_B1_T40`[baseline_cache_only] `task_B1_T41`[baseline_cache_only] `task_B1_T42`[baseline_cache_only] `task_B2_T01`[baseline_cache_only] `task_B2_T02`[baseline_cache_only] `task_B2_T03`[baseline_cache_only] `task_B2_T04`[baseline_cache_only] `task_B2_T05`[baseline_cache_only] `task_B2_T06`[baseline_cache_only] `task_B10_T01`[baseline_cache_only] `task_B10_T02`[baseline_cache_only] `task_B10_T03`[baseline_cache_only] `task_B10_T04`[baseline_cache_only] `task_B10_T05`[baseline_cache_only] `task_B10_T06`[baseline_cache_only] `task_B10_T07`[baseline_cache_only] `task_B10_T08`[baseline_cache_only] `task_B10_T09`[baseline_cache_only] `task_B10_T10`[baseline_cache_only] `task_B10_T11`[baseline_cache_only] `task_B10_T12`[baseline_cache_only] `task_B11_T01`[baseline_cache_only] `task_B11_T02`[baseline_cache_only] `task_B11_T03`[baseline_cache_only] `task_B11_T04`[baseline_cache_only] `task_B11_T05`[baseline_cache_only] `task_B11_T06`[baseline_cache_only] `task_B11_T07`[baseline_cache_only] `task_B11_T08`[baseline_cache_only] `task_B11_T09`[baseline_cache_only] `task_B11_T10`[baseline_cache_only] `task_B11_T11`[baseline_cache_only] `task_B11_T12`[baseline_cache_only] `task_B11_T13`[baseline_cache_only] `task_B11_T14`[baseline_cache_only] `task_B12_T01`[baseline_cache_only] `task_B12_T02`[baseline_cache_only] `task_B12_T03`[baseline_cache_only] `task_B12_T04`[baseline_cache_only] `task_B12_T05`[baseline_cache_only] `task_B12_T06`[baseline_cache_only] `task_B12_T07`[baseline_cache_only] `task_B12_T08`[baseline_cache_only] `task_B12_T09`[baseline_cache_only] `task_B12_T10`[baseline_cache_only] `task_B12_T11`[baseline_cache_only] `task_B12_T12`[baseline_cache_only] `task_B12_T13`[baseline_cache_only] `task_B12_T14`[baseline_cache_only] `task_B12_T15`[baseline_cache_only] `task_B12_T16`[baseline_cache_only] `task_B13_T01`[baseline_cache_only] `task_B13_T02`[baseline_cache_only] `task_B13_T03`[baseline_cache_only] `task_B13_T04`[baseline_cache_only] `task_B13_T05`[baseline_cache_only] `task_B13_T06`[baseline_cache_only] `task_B13_T07`[baseline_cache_only] `task_B13_T08`[baseline_cache_only] `task_B13_T09`[baseline_cache_only] `task_B13_T10`[baseline_cache_only] `task_B13_T11`[baseline_cache_only] `task_B13_T12`[baseline_cache_only] `task_B13_T13`[baseline_cache_only] `task_B13_T14`[baseline_cache_only] `task_B14_T01`[baseline_cache_only] `task_B14_T02`[baseline_cache_only] `task_B14_T03`[baseline_cache_only] `task_B14_T04`[baseline_cache_only] `task_B14_T05`[baseline_cache_only] `task_B14_T06`[baseline_cache_only] `task_B14_T07`[baseline_cache_only] `task_B14_T08`[baseline_cache_only] `task_B14_T09`[baseline_cache_only] `task_B14_T10`[baseline_cache_only] `task_B14_T11`[baseline_cache_only] `task_B15_T01`[baseline_cache_only] `task_B15_T02`[baseline_cache_only] `task_B15_T03`[baseline_cache_only] `task_B15_T04`[baseline_cache_only] `task_B15_T05`[baseline_cache_only] `task_B15_T06`[baseline_cache_only] `task_B15_T07`[baseline_cache_only] `task_B15_T08`[baseline_cache_only] `task_B15_T09`[baseline_cache_only] `task_B15_T10`[baseline_cache_only] `task_B15_T11`[baseline_cache_only] `task_B15_T12`[baseline_cache_only]

### GPT-5.6-Terra (`openclaw_gpt-5.6-terra`)

归档：攻击 896/900，benign 298/300，共 1194/1200；缺失 6。攻击评分 valid/error = 896/4；其中已有 raw 但评分失败 0 条。UGS 评分行 298/300。

**raw 缺失的攻击 slot：**

`B1/task_B1_T29/run_1 B1/task_B1_T29/run_3 B3/task_B3_T20/run_2 B8/task_B8_T26/run_1`

**raw 缺失的 benign task：**

`task_B3_T31` `task_B8_T28`

### GPT-5.6-Luna (`openclaw_gpt-5.6-luna`)

归档：攻击 899/900，benign 299/300，共 1198/1200；缺失 2。攻击评分 valid/error = 899/1；其中已有 raw 但评分失败 0 条。UGS 评分行 299/300。

**raw 缺失的攻击 slot：**

`B14/task_B14_T05/run_3`

**raw 缺失的 benign task：**

`task_B1_T29`

### Grok-4.3 (`openclaw_grok-4.3`)

归档：攻击 898/900，benign 299/300，共 1197/1200；缺失 3。攻击评分 valid/error = 898/2；其中已有 raw 但评分失败 0 条。UGS 评分行 300/300。

**raw 缺失的攻击 slot：**

`B1/task_B1_T21/run_2 B1/task_B1_T21/run_3`

**raw 缺失的 benign task：**

`task_B8_T21`

**UGS 中有、归档中没有的 benign task（1 条）：**

`task_B8_T21`

### MiniMax-M2.5 (`openclaw_minimax-m2.5`)

归档：攻击 882/900，benign 279/300，共 1161/1200；缺失 39。攻击评分 valid/error = 882/18；其中已有 raw 但评分失败 0 条。UGS 评分行 206/300。

**raw 缺失的攻击 slot：**

`B1/task_B1_T38/run_1 B1/task_B1_T38/run_2 B1/task_B1_T38/run_3 B5/task_B5_T10/run_2 B6/task_B6_T13/run_2`
`B6/task_B6_T19/run_1 B7/task_B7_T05/run_1 B7/task_B7_T05/run_2 B7/task_B7_T06/run_2 B7/task_B7_T06/run_3`
`B8/task_B8_T19/run_1 B8/task_B8_T29/run_1 B9/task_B9_T12/run_1 B12/task_B12_T03/run_1 B12/task_B12_T03/run_2`
`B12/task_B12_T12/run_2 B13/task_B13_T06/run_3 B15/task_B15_T10/run_2`

**raw 缺失的 benign task：**

`task_B1_T01` `task_B1_T19` `task_B1_T39` `task_B2_T02` `task_B4_T04` `task_B5_T10` `task_B5_T12` `task_B5_T15` `task_B8_T05` `task_B8_T23` `task_B8_T39` `task_B9_T01` `task_B9_T12` `task_B10_T01` `task_B10_T02` `task_B10_T03` `task_B10_T04` `task_B10_T05` `task_B10_T06` `task_B10_T07` `task_B12_T03`

**归档中存在、但 UGS 未纳入的 benign task（92 条）：**

`task_B1_T02`[score_source_subset_absent] `task_B1_T03`[score_source_subset_absent] `task_B1_T04`[score_source_subset_absent] `task_B1_T05`[score_source_subset_absent] `task_B1_T06`[score_source_subset_absent] `task_B1_T21`[score_source_subset_absent] `task_B1_T29`[score_source_subset_absent] `task_B2_T01`[score_source_subset_absent] `task_B3_T13`[score_source_subset_absent] `task_B4_T01`[score_source_subset_absent] `task_B4_T07`[score_source_subset_absent] `task_B4_T08`[score_source_subset_absent] `task_B4_T11`[score_source_subset_absent] `task_B6_T06`[score_source_subset_absent] `task_B6_T07`[score_source_subset_absent] `task_B6_T08`[score_source_subset_absent] `task_B6_T11`[score_source_subset_absent] `task_B6_T12`[score_source_subset_absent] `task_B6_T13`[score_source_subset_absent] `task_B6_T14`[score_source_subset_absent] `task_B6_T15`[score_source_subset_absent] `task_B6_T16`[score_source_subset_absent] `task_B6_T17`[score_source_subset_absent] `task_B6_T18`[score_source_subset_absent] `task_B6_T20`[score_source_subset_absent] `task_B6_T21`[score_source_subset_absent] `task_B6_T22`[score_source_subset_absent] `task_B6_T23`[score_source_subset_absent] `task_B6_T25`[score_source_subset_absent] `task_B6_T26`[score_source_subset_absent] `task_B6_T27`[score_source_subset_absent] `task_B6_T28`[score_source_subset_absent] `task_B6_T30`[score_source_subset_absent] `task_B6_T31`[score_source_subset_absent] `task_B6_T32`[score_source_subset_absent] `task_B6_T33`[score_source_subset_absent] `task_B6_T34`[score_source_subset_absent] `task_B6_T35`[score_source_subset_absent] `task_B6_T37`[score_source_subset_absent] `task_B7_T01`[score_source_subset_absent] `task_B7_T03`[score_source_subset_absent] `task_B7_T04`[score_source_subset_absent] `task_B7_T08`[score_source_subset_absent] `task_B7_T10`[score_source_subset_absent] `task_B7_T11`[score_source_subset_absent] `task_B7_T12`[score_source_subset_absent] `task_B7_T14`[score_source_subset_absent] `task_B8_T01`[score_source_subset_absent] `task_B8_T02`[score_source_subset_absent] `task_B8_T03`[score_source_subset_absent] `task_B8_T04`[score_source_subset_absent] `task_B8_T09`[score_source_subset_absent] `task_B8_T10`[score_source_subset_absent] `task_B12_T08`[score_source_subset_absent] `task_B12_T09`[score_source_subset_absent] `task_B12_T10`[score_source_subset_absent] `task_B12_T11`[score_source_subset_absent] `task_B12_T13`[score_source_subset_absent] `task_B12_T14`[score_source_subset_absent] `task_B12_T16`[score_source_subset_absent] `task_B13_T01`[score_source_subset_absent] `task_B13_T02`[score_source_subset_absent] `task_B13_T03`[score_source_subset_absent] `task_B13_T04`[score_source_subset_absent] `task_B13_T05`[score_source_subset_absent] `task_B13_T07`[score_source_subset_absent] `task_B13_T08`[score_source_subset_absent] `task_B13_T09`[score_source_subset_absent] `task_B13_T11`[score_source_subset_absent] `task_B13_T12`[score_source_subset_absent] `task_B13_T13`[score_source_subset_absent] `task_B14_T01`[score_source_subset_absent] `task_B14_T02`[score_source_subset_absent] `task_B14_T03`[score_source_subset_absent] `task_B14_T04`[score_source_subset_absent] `task_B14_T05`[score_source_subset_absent] `task_B14_T06`[score_source_subset_absent] `task_B14_T07`[score_source_subset_absent] `task_B14_T08`[score_source_subset_absent] `task_B14_T09`[score_source_subset_absent] `task_B14_T10`[score_source_subset_absent] `task_B14_T11`[score_source_subset_absent] `task_B15_T01`[score_source_subset_absent] `task_B15_T02`[score_source_subset_absent] `task_B15_T03`[score_source_subset_absent] `task_B15_T04`[score_source_subset_absent] `task_B15_T06`[score_source_subset_absent] `task_B15_T07`[score_source_subset_absent] `task_B15_T08`[score_source_subset_absent] `task_B15_T09`[score_source_subset_absent] `task_B15_T11`[score_source_subset_absent] `task_B15_T12`[score_source_subset_absent]

**UGS 中有、归档中没有的 benign task（19 条）：**

`task_B1_T19` `task_B1_T39` `task_B2_T02` `task_B4_T04` `task_B5_T10` `task_B5_T12` `task_B5_T15` `task_B8_T05` `task_B8_T23` `task_B8_T39` `task_B9_T01` `task_B9_T12` `task_B10_T02` `task_B10_T03` `task_B10_T04` `task_B10_T05` `task_B10_T06` `task_B10_T07` `task_B12_T03`

### Deepseek-v4-Flash-0731 (`openclaw_deepseek-v4-flash-0731`)

归档：攻击 892/900，benign 299/300，共 1191/1200；缺失 9。攻击评分 valid/error = 892/8；其中已有 raw 但评分失败 0 条。UGS 评分行 299/300。

**raw 缺失的攻击 slot：**

`B1/task_B1_T13/run_2 B1/task_B1_T13/run_3 B1/task_B1_T14/run_3 B3/task_B3_T29/run_2 B4/task_B4_T07/run_2`
`B6/task_B6_T19/run_3 B7/task_B7_T05/run_2 B15/task_B15_T03/run_3`

**raw 缺失的 benign task：**

`task_B6_T13`

## 如何使用机器可读标记

完整的 8,400 个预期 slot 标签在 `results/imported_server_scores/20260924/completeness_audit_20260929/trajectory_slot_labels.csv`。每行包含 `raw_status`、`score_status` 和 `issue_label`。批次汇总在同目录的 `batch_summary.csv`，原始 JSON 在 `trajectory_completeness.json`。

这份核对只标记现状，没有把缺失 slot 补成失败轨迹，也没有修改评分文件。
