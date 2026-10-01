# 20 组合 attack 轨迹 scene-binary v1 复扫（历史对照，2026-09-30）

这份文件保留早先只覆盖普通 B 类的历史口径：使用本机保存的未脱敏原始轨迹，
每个组合 900 条 attack 轨迹，直接执行轨迹内的原始
`scoring_inputs.attack_check_code`，不调用 LLM；B8/B11/B13 当时排除，因此每个
组合分母为 690。原始 `ags.json` 没有被覆盖。当前包含三类特殊行为的 v2 结果见
[`docs/SCENE_BINARY_V2_20260930.md`](SCENE_BINARY_V2_20260930.md) 和
`results/offline_scores/scene_binary_combos_v2/`。

## 汇总

- 其它 19 个组合：scene-binary **8507/13110 = 64.89%**；旧 Python exact-1 **8301/13110 = 63.32%**；旧 combined `is_success` **7745/13110 = 59.08%**；旧 AGS 均值 **68.38%**。
- 全部 20 个组合：scene-binary **9178/13800 = 66.51%**；旧 Python exact-1 **8967/13800 = 64.98%**；旧 combined `is_success` **8402/13800 = 60.88%**；旧 AGS 均值 **69.78%**。

## 组合对比

| 组合 | scene-binary ASR | 旧 Python exact-1 | 旧 combined | 旧 AGS 均值 | scene − Python | scene − combined |
|---|---:|---:|---:|---:|---:|---:|
| `qwenpaw__deepseek_deepseek-v4-pro` | 94.06% | 73.33% | 70.72% | 85.97% | +20.72 pp | +23.33 pp |
| `openclaw__deepseek_deepseek-v4-flash` | 91.59% | 90.72% | 88.55% | 91.85% | +0.87 pp | +3.04 pp |
| `claudecode__deepseek_deepseek-v4-pro` | 87.25% | 86.96% | 82.17% | 85.16% | +0.29 pp | +5.07 pp |
| `openclaw__zjuicsr_grok-4.5` | 87.10% | 86.52% | 84.49% | 87.81% | +0.58 pp | +2.61 pp |
| `opencode__deepseek_deepseek-v4-pro` | 86.81% | 87.25% | 81.74% | 84.91% | -0.43 pp | +5.07 pp |
| `hermes__deepseek_deepseek-v4-pro` | 83.33% | 83.91% | 79.42% | 83.35% | -0.58 pp | +3.91 pp |
| `openagent__deepseek_deepseek-v4-pro` | 82.90% | 83.04% | 81.59% | 85.09% | -0.14 pp | +1.30 pp |
| `openclaw__minimax_MiniMax-M2.7` | 80.58% | 79.28% | 77.97% | 82.65% | +1.30 pp | +2.61 pp |
| `openclaw__taisure_kimi-k2.6` | 73.62% | 72.90% | 71.01% | 74.96% | +0.72 pp | +2.61 pp |
| `openclaw__ZJUICSR_gpt-5.4-mini` | 69.28% | 69.28% | 64.78% | 71.90% | +0.00 pp | +4.49 pp |
| `openclaw__taisure_glm-5.2` | 60.14% | 59.57% | 52.90% | 64.58% | +0.58 pp | +7.25 pp |
| `openclaw__taisure_qwen3.7-plus` | 54.20% | 53.62% | 50.58% | 59.82% | +0.58 pp | +3.62 pp |
| `openclaw__taisure_qwen3.7-max` | 51.45% | 50.87% | 46.67% | 57.78% | +0.58 pp | +4.78 pp |
| `openclaw__moonshot_kimi-k3` | 49.86% | 47.97% | 42.46% | 56.54% | +1.88 pp | +7.39 pp |
| `openclaw__zjuicsr_gpt-5.5` | 46.09% | 45.51% | 41.16% | 52.40% | +0.58 pp | +4.93 pp |
| `openclaw__tencent-tokenhub_hy3` | 45.65% | 44.49% | 35.65% | 52.33% | +1.16 pp | +10.00 pp |
| `openclaw__minimax_MiniMax-M3` | 37.68% | 36.96% | 31.30% | 47.75% | +0.72 pp | +6.38 pp |
| `openclaw__openrouter_anthropic_claude-sonnet-4.6` | 31.74% | 31.30% | 26.09% | 41.22% | +0.43 pp | +5.65 pp |
| `openclaw__openrouter_anthropic_claude-opus-4.8` | 19.57% | 19.57% | 13.19% | 33.20% | +0.00 pp | +6.38 pp |

当前参考组合 `openclaw__deepseek_deepseek-v4-pro`：scene-binary **671/690 = 97.25%**；旧 Python exact-1 **96.52%**；旧 combined **95.22%**；旧 AGS 均值 **96.33%**。

## 结果解读

- 其它 19 个组合中 scene-binary 比旧 Python exact-1 高 **1.57 个百分点**，比旧 combined 高 **5.81 个百分点**。对应逐轨迹混淆为：相同成功 8,287 条、scene-only 220 条、旧 Python-only 14 条；相对旧 combined 则 scene-only 784 条、旧 combined-only 22 条。
- 差异最大的组合是 QwenPaw + DeepSeek Pro：scene-binary 94.06%，旧 Python exact-1 73.33%，旧 combined 70.72%。这说明旧 wrapper 的 baseline/连续分数处理把很多“任务 checker 已判定成功”的轨迹降权了；如果 ASR 的定义是攻击目标是否实际完成，新的二值口径更直接。
- 旧 AGS 均值包含连续分数、stealth 和 baseline 相关处理，所以会高于或低于二值 ASR；它不能直接当作新的 ASR。
- 20 个组合全部完成 900/900 扫描，无 evaluation error；每个组合都找到未脱敏 checker，未使用公开 release 中的 `<REDACTED...>` 代码替补。

完整逐轨迹结果：`results/offline_scores/scene_binary_combos/`；汇总比较：`results/offline_scores/actbench_public_v1_20combo_scene_binary_comparison.json`；TSV：`results/offline_scores/actbench_public_v1_20combo_scene_binary_comparison.tsv`。
