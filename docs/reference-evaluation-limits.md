# 参考 RoboDojo 网页的运行规模与预算

核查日期：2026-10-27。范围是当前 A 线对照的 RoboDojo 十任务，参考源码提交为 `8f3d362b077d8efb77e2a7274d5b2c20e2243846`；不是网页另列的 RoboLab 补充实验。

## 案例数

每个方法为 10 个任务、每任务 5 个对齐案例，共 50 个案例；Direct 与 Hybrid 对齐 case_id、布局和 seed。数字摆放、装箱、折衣采用 2 个 standard＋3 个 random，其余任务为 5 个 standard。这里的“五次”是案例规模，不是每个相同案例重试五次取最好值。

来源：[项目说明](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/README.md)、[逐案例公开结果](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/public_results/evaluation_cases.json)。

## 原生步数与仿真时间

案例数据的 `limit` 是原生控制步上限，`dt=0.04`，即 25 Hz。原生成功可提前结束；达到原生 horizon 而未成功属于原生失败。

| 任务 | 控制步上限 | 对应仿真控制时间 |
|---|---:|---:|
| fold_clothes | 500 | 20 秒 |
| make_kong | 600 | 24 秒 |
| put_bottles_into_dustbin | 700 | 28 秒 |
| organize_table | 1000 | 40 秒 |
| arrange_largest_number | 1050 | 42 秒 |
| build_tower | 1050 | 42 秒 |
| classify_objects | 1100 | 44 秒 |
| classify_objects_by_language | 1100 | 44 秒 |
| pack_objects_into_box | 1300 | 52 秒 |
| imitate_sorting_sequence | 1600 | 64 秒 |

这些时间由 `limit × dt` 换算，不是端到端墙钟上限，也不包括模型推理等待。公开视频还可能包含初始帧，因此视频时长不必恰好等于控制步数乘 dt。

## 正式配置的额外预算

参考 `hybrid_rollout/robodojo/cluster.env.example` 明确说明正式 panel 采用原生步数限制，并配置：

```text
MAX_DECISIONS=0
CODEX_MAX_TOTAL_TOKENS=0
ROLLOUT_MAX_SECONDS=0
```

此处 0 表示关闭相应额外上限。因此公开正式配置没有统一限制模型决策次数、累计 token 或整条 episode 的墙钟时间。单次模型/RPC 请求仍可能有连接和执行超时，这属于基础设施机制，不等于任务的整体评测时间预算。该配置不能证明历史每次尝试都完全一致，但足以区分正式 panel 配置与开发脚本的保护默认值。

来源：[正式配置示例](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/hybrid_rollout/robodojo/cluster.env.example)。

## 与当前 A 线的区别

当前 `stack_bowls` 是网页十任务之外的开发案例。原生 horizon 为 800 步；我们预先设置的 4 小时墙钟、4000 万累计 token 和 800 次有效决策是开发保护预算，见 `configs/a_stack_bowls_development.json`，不是参考网页规定。

当前运行保持启动时预算。若先触发额外预算，应记为预算截断，不能冒充原生完成或直接填成网页同协议的零分。正式对照须明确原生步数一致，并单列任何额外预算差异、截断数和基础设施异常；开发保护预算与正式协议应分别登记。
