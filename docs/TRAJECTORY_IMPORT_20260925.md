# 2026-09-25 轨迹补充批次归纳

本报告记录从服务器移动回来的
`agent_trajectories_mine_20260925.tar.gz` 的盘点、服务器评分结果导入，以及
阈值 0.9 下的表格和图更新。新增批次曾经合并作审计，论文仍明确区分
“fully scored core”与包含部分 benign 覆盖的历史扩展结果。经完整性核对后，
这 7 个补充批次已从正式分析输入和派生图表中排除；当前正式口径恢复为此前
完整的 20 组配置（18,000 条攻击、6,000 条 benign）。

本批次按每个模型 **900 条攻击 + 300 条 benign** 的完整性逐 slot 核对见
[TRAJECTORY_COMPLETENESS_20260925.md](TRAJECTORY_COMPLETENESS_20260925.md)。该报告同时给出缺失
slot、已有 raw 但评分失败的行，以及 raw benign 与 UGS 输入不一致的标记。

当前正式输入位于 `results/figures/threshold_0.9/_inputs/`，只包含完整核心数据。
补充批次的评分文件和原始归档已从本机清理；下面的核对报告与汇总仍保留作审计记录，不参与正式统计。

## 1. 来源和内容

- 本地归档：`agent_trajectories_mine_20260925.tar.gz`（核对完成后已从本机清理）
- SHA-256：`560eb41ff0fb73c83add01cb91c14d91fb23460a892edf228036a1db7d8289f9`
- 归档清单生成时间：`2026-09-25T10:57:46`
- 内容结构：每条攻击轨迹包含 `trajectory.json` 和 `metadata.json`；另有按模型保存的 benign baseline JSON
- 归档本身的攻击轨迹曾标记为 `scoring_status=deferred`；服务器对应的 AGS/UGS score JSON 曾复制到 `results/imported_server_scores/20260924/`，现已随补充轨迹一并清理
- 归档内嵌的历史攻击阈值：`0.8`；本地复核按当前策略显式使用 `score >= 0.9`

清单统计为 6,232 条成功攻击轨迹、2,074 条成功 benign baseline，共 8,306 条。计划中的 7 个模型批次应有 6,300 条攻击轨迹，缺少 68 个攻击 run slot；benign baseline 计划为 2,100 条，实际缺少 26 条。

## 2. 模型和批次范围

| 归档目录 | 实际目标模型 | 攻击轨迹 | benign | 缺少攻击 slot | 运行时间（UTC） | 与当前 15 模型表的关系 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `openclaw_gpt-5.4` | `zju-router/gpt-5.4` | 873 | 300 | 27 | 2026-08-05 19:06 – 2026-08-07 07:16 | 新模型；不同于 GPT-5.4-mini |
| `openclaw_gpt-5.6-sol` | `zju-router/gpt-5.6-sol` | 892 | 300 | 8 | 2026-08-08 17:52 – 2026-08-09 15:08 | 新模型 |
| `openclaw_gpt-5.6-terra` | `zju-router/gpt-5.6-terra` | 896 | 298 | 4 | 2026-08-07 07:27 – 2026-08-08 01:00 | 新模型 |
| `openclaw_gpt-5.6-luna` | `zju-router/gpt-5.6-luna` | 899 | 299 | 1 | 2026-08-07 07:26 – 2026-08-08 01:23 | 新模型 |
| `openclaw_grok-4.3` | `zju-router/grok-4.3` | 898 | 299 | 2 | 2026-08-03 08:13 – 2026-08-04 05:31 | 新模型；不同于 Grok-4.5 |
| `openclaw_minimax-m2.5` | `minimax/MiniMax-M2.5` | 882 | 279 | 18 | 2026-08-03 13:28 – 2026-08-04 12:58 | 新模型；不同于 MiniMax-M2.7/M3 |
| `openclaw_deepseek-v4-flash-0731` | `Deepseek-v4-Flash-0731` | 892 | 299 | 8 | 2026-08-04 10:18 – 2026-08-04 20:24 | 新模型版本；不同于现有 Deepseek-v4-Flash |

因此，时间上这批确实晚于当前表使用的 2026-07-13–07-27 批次；按实际模型版本区分，这批是 7 个新增模型，不应把 `Deepseek-v4-Flash-0731` 合并到现有的 `Deepseek-v4-Flash` 行。

缺失的攻击 slot 主要集中在：GPT-5.4 的 27 个、MiniMax-M2.5 的 18 个、Deepseek-v4-Flash-0731 的 8 个，以及 GPT-5.6-Sol 的 8 个。缺失不应补成失败分数，也不应按 900 条完整批次直接计算 ASR。

## 3. 仅 automated-only 的 0.9 预检（历史记录）

为确认归档是否能被当前评分器读取，我使用归档中内嵌的 `api_audit` 和 grader 做了本地 automated-only 预检，并强制覆盖阈值为 0.9。预检没有调用外部 judge，也没有使用本机可能残留的 `/tmp/claweval` workspace。

| 模型 | 有效攻击数 | 自动 AGS 均值 | 自动 ASR@0.9 | p@1 | p@2 | p@3 | 恶意 Iter. 中位数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT-5.4 | 873 | 0.6131 | 42.84% | 41.95% | 46.44% | 51.79% | 17 |
| GPT-5.6-Luna | 899 | 0.5719 | 37.04% | 38.00% | 41.33% | 43.81% | 17 |
| GPT-5.6-Sol | 892 | 0.5470 | 32.06% | 31.77% | 36.36% | 37.16% | 17 |
| GPT-5.6-Terra | 896 | 0.5067 | 26.67% | 26.00% | 30.10% | 31.31% | 16 |
| Grok-4.3 | 898 | 0.7233 | 60.91% | 61.00% | 64.55% | 67.56% | 21 |
| MiniMax-M2.5 | 882 | 0.6999 | 55.67% | 54.85% | 61.49% | 62.37% | 18 |
| Deepseek-v4-Flash-0731 | 892 | 0.6461 | 49.89% | 50.67% | 55.85% | 58.70% | 17 |

这些数字**不是论文正式表的最终 AGS/UGS**：它们保留为归档刚导入时的自动预检记录。随后发现服务器上已有对应的 combined AGS/UGS score JSON，因此正式扩展表使用服务器 score 文件逐行按 0.9 重算 attack-success/pass 字段，而不是把这张预检表直接拼进去。

## 4. 历史扩展合并结果（现已排除）

以下记录描述补充批次曾经的试合并结果，仅用于追溯；它们已经从正式输入中移除。

服务器 score JSON 已覆盖以下 7 个新增模型；在排除前的历史试合并中，本地脚本
`scripts/merge_server_model_scores.py` 曾将它们合并进
`results/figures/threshold_0.9/_inputs/ags_threshold_0.9.json` 和
`ugs_threshold_0.9.json`。历史版本中的所有攻击行成功判定都按
`attack_success >= 0.9`（等价于 `AGS >= 0.9`）重新计算，评估错误行保留但不计入
有效 ASR；缺失 slot 不补成失败。

| 模型 | AGS 有效数 | AGS 均值 | ASR@0.9 | pass@1 / pass@2 / pass@3 | UGS 有效数 |
| --- | ---: | ---: | ---: | --- | ---: |
| GPT-5.4 | 872 | 0.591 | 46.7% | 44.3% / 54.2% / 61.3% | 165 |
| GPT-5.6-Sol | 891 | 0.434 | 29.2% | 29.4% / 35.7% / 36.9% | 174 |
| GPT-5.6-Terra | 896 | 0.386 | 25.2% | 23.7% / 31.1% / 33.7% | 298 |
| GPT-5.6-Luna | 899 | 0.503 | 37.0% | 39.0% / 43.7% / 47.5% | 299 |
| Grok-4.3 | 898 | 0.862 | 78.1% | 78.3% / 84.6% / 88.6% | 300 |
| MiniMax-M2.5 | 882 | 0.799 | 70.2% | 70.2% / 78.0% / 79.4% | 206 |
| Deepseek-v4-Flash-0731 | 892 | 0.632 | 50.3% | 50.7% / 59.5% / 64.8% | 299 |

这 7 行与原有 15 行组成 22 个 OpenClaw 模型行。新批次 score 文件包含 6,300
个计划行，其中 6,230 条有效、70 条为评估错误；原始归档实际包含 6,232 条
成功攻击轨迹，另有 68 个计划 slot 缺失。与原有输入合并后共有 24,230 条有效攻击
score 行。扩展池的描述性 pooled ASR@0.9 为 52.40%。核心 20 配置的正式
aggregate 仍为 18,000 条有效攻击行、53.90%；扩展池不替换这个核心数字，因为
后续批次的 benign UGS 覆盖不完全。

`Deepseek-v4-Flash` 与 `Deepseek-v4-Flash-0731` 保持为两个不同模型版本。新批次
的 GPT-5.4、GPT-5.6-Sol/Terra/Luna、Grok-4.3、MiniMax-M2.5 和
Deepseek-v4-Flash-0731 的 AGS、ASR、pass@k、迭代图已重画；资源图覆盖 22 个
模型的迭代/执行时间，token 图覆盖 21 个有 populated token fields 的模型。
MiniMax-M2.5 的 token 字段是全零占位值，因此按缺失显示，不作数值统计。

## 5. 历史扩展图和输入位置

- Overleaf `main.tex` 的 RQ1 表曾从 15 行扩展到 22 行，并标注后续批次的有效样本数；这部分扩展现已撤回。
- 正文曾补充 52.40% 的扩展池描述性 ASR；当前正式统计只保留核心 20 配置的 53.90% aggregate。
- `figures/iteration_boxplot_combined_openclaw_models.pdf`、`figures/apdix_execution_cost.pdf`
  以及 `figures/score_weight_sensitivity/` 下的 AGS/UGS、ASR、pass@k 图已替换为新版本。
- 历史 Appendix 资源表曾补入 7 个模型；该历史表和 MiniMax-M2.5 的 unavailable 标记不再属于当前正式论文口径。
- 正式生成输入保留在 `results/figures/threshold_0.9/_inputs/`；补充批次的评分文件和
  `raw_by_task` 轨迹目录已清理，仅保留 `results/imported_server_scores/20260924/completeness_audit_20260929/`
  中的核对汇总，便于复核排除依据。

当前正式结果目录中的输入和派生图表均按完整核心口径重建；运行合并脚本时默认不再加入这 7 个补充批次，只有显式指定
`--include-incomplete-supplemental` 才会生成历史扩展口径。
