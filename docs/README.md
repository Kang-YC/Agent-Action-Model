# 项目文档

| 文档 | 内容 |
|---|---|
| [研究与评测计划](robodojo-harness-evaluation-plan.md) | 范围、评测约定、阶段与当前证据 |
| [固定模型推理服务](model-service.md) | 服务启停、复用、状态、文本/多图调用、依赖 |
| [本地 base 推理链路](base-inference.md) | Codex 多图探针、Direct 入口与已完成验证记录 |
| [A 线](a-line.md) | 叠碗开发运行、网页十任务配对清单、后续验收 |
| [B 线](b-line.md) | mini-swe-agent、持久 Python、历史窗口与叠碗开发运行 |
| [A/B 叠碗对照协议](ab-stack-bowls-protocol.md) | 固定条件、已知差异、判分口径与自动报告入口 |
| [B 线评测候选准备](b-panel-readiness.md) | 开发案例排除、布局校验、候选参数与正式启动缺口 |
| [叠碗首次运行复盘](experiments/a-stack-bowls-01.md) | 147 步显存异常、证据与失败分类 |
| [参考评测限制](reference-evaluation-limits.md) | 五案例规模、原生步数、仿真时间与墙钟预算的区别 |
| [共享机器人契约](robot-contract.md) | 双臂目标、逐步 ACK、图像反馈、固定命令检查 |

本会话负责 A 线。新 A 线入口使用 `configs/a_model_compiled.json`，与历史 `configs/base_model.json` 使用同一 checkpoint，执行配置的差异见服务文档。任务与预算放在 `configs/`，实现放在 `agent_action/`，可执行入口放在 `scripts/`。大型图片、视频、原始模型请求和进程状态保存在忽略版本跟踪的 `artifacts/`；文档记录路径与验证结论。A 线文档顶部给出当前状态，下方保留按日期记录的历史证据。

完成一个子任务后先检查，再单独 commit。正式成绩、开发验证和运行中状态分别记录，不以模型自述代替原生判分。
