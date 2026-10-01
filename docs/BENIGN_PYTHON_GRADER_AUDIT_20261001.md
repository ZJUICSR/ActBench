# Benign Python grader audit

本报告对 OpenClaw + DeepSeek v4-pro 数据集中的 300 个 benign baseline 轨迹运行当前 task-specific Python checker，并按新的 UGS task-completion 规则重新划分检查项。此次检查只读取已有轨迹和 workspace，不重跑 agent。

## 覆盖情况

- 轨迹数：300；checker 运行错误：0。
- checker 状态：`passed=147`，`partial=153`，其他状态 `0`。
- 每个任务都有正向 task-completion 证据；没有出现空的 UGS completion contract。
- 旧 checker 输出中的诊断检查共 702 项，已从 UGS contract、Python 分母、LLM 输入和 UGS 结果行移除。

正向完成证据数量分布如下；它表示底层审计证据数量，不表示评分等级：

| 正向证据项数 | 任务数 |
|---:|---:|
| 1 | 63 |
| 2 | 38 |
| 3 | 58 |
| 4 | 86 |
| 5 | 32 |
| 6 | 19 |
| 7 | 3 |
| 8 | 1 |

诊断项数量分布如下；这些项不参与 UGS：

| 被移除诊断项数 | 任务数 |
|---:|---:|
| 1 | 74 |
| 2 | 83 |
| 3 | 120 |
| 4 | 16 |
| 5 | 4 |
| 6 | 3 |

## 新 Python task-completion 分数

- 原始正向证据平均分：`0.8021`；范围 `0.0000–1.0000`。
- 五档公开分平均值：`0.8075`。
- 五档分布：

| Python task-completion grade | 任务数 |
|---:|---:|
| 0 | 16 |
| 0.25 | 8 |
| 0.5 | 34 |
| 0.75 | 75 |
| 1 | 167 |

## 检查结论

- 诊断项主要是 `no extra`、`remains empty`、`excludes`、`avoided`、`forbidden` 等旧的安全或额外副作用约束；当前 300 个任务中没有被归入诊断区、但名称仍表现为 `created/updated/expected/includes` 的正向交付检查。
- 正向项主要验证目标记录、目标字段、目标文章内容、目标 workspace 文件，以及用户明确要求的检索步骤。它们都描述了原任务的完成证据。
- Python grader 当前仍保留底层原始分数，正式 UGS 使用统一的 `0 / 0.25 / 0.5 / 0.75 / 1` task-completion grade；因此底层证据数量可以变化，公开评分语义不会随 2–12 的旧检查项数量变化。
- 检查项权重目前仍然等权。此次审计没有发现必须立即手工改写某个 benign checker 的错误；后续若要进一步提高精度，优先验证核心交付物与辅助字段是否需要不同权重。
