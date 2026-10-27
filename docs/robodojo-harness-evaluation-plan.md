# Agent-Action：RoboDojo Harness 与评测计划

V1.3 · 2026-10-27 · A 线：固定模型服务 → 叠碗开发 episode → 网页十任务配对评测，尚未完成正式评测


> B 线执行补充（2026-10-27）：当前会话按用户要求推进原 B 线，复用同一 `agent-action-base-gs450` 服务；已有 A 线叠碗运行保留。B 线按模型接入、多图探针、机器人开发闭环、冻结评测顺序执行，入口和状态见 [B 线运行说明](b-line.md)。A 线结束释放显存前不启动 B 线仿真。本页原 A 线计划保留为对应工作的记录。

## 1. 目标与范围

在已跑通的 RoboDojo 环境中，首先将本地部署的模型接入 Codex harness，在代表性任务上取得 Direct 评测结果。该模型是后续训练的 base；本轮建立可复现的训练前能力、失败类型与推理成本基线。

本会话明确只推进 **A 线：指定 base＋Codex Direct**。模型服务作为共享基础固定；mini-swe-agent/B 线由独立工作维护，不作为 A 线前置。Hybrid 与训练不在本轮范围。先运行 `stack_bowls`（叠碗）开发 episode，之后按网页原有十任务案例做逐例对照。

本阶段只做模型接入、harness 验证与评测。保留原始观测、模型调用和执行轨迹；数据集加工、训练及新动作表示后续展开。模型失败也属于有效研究结果，成功完成任务不是链路验收的前提。

## 2. 主线与后续研究

| 优先级 | 工作 | 目的 |
|---|---|---|
| 当前主线 | 本地 base 模型＋Codex harness＋参考 Direct 机器人工具 | 获得后续训练的起点成绩 |
| 后续训练对照 | 训练后模型＋同一冻结 harness 和评测协议 | 评估相对 base 的变化 |
| 可选参考 | 原参考模型＋同一 Codex harness 和案例 | 提供参考能力水平，登记实际模型与配置差异 |
| 后续 harness 研究 | 同一 base 或训练后模型接入 mini-swe-agent | 单独评估 harness 与工具接口变化 |
| 后续策略研究 | 历史图像、VLA-only、Hybrid | 在稳定基线上分析各项收益 |

不再以“原参考模型＋Codex”与“自有模型＋mini-swe-agent”两条路线同时推进作为近期交付。首轮沿用参考 Direct 的工具、提示词、历史与执行机制，只做本地模型协议适配和必要的兼容修复；逐项记录修改。`move_to` 和 mini-swe-agent 接入不阻塞本轮结果。

本地部署不要求模型与仿真同一进程或机器，可通过已有模型服务调用。开跑前固定模型名称、checkpoint/revision 或权重标识、服务版本、推理参数及协议适配器版本；不得用临时 Qwen 开发轨迹替代选定 base 的正式成绩。本轮 base 已指定为用户提供的 `qwen3_6_35B_A3B_ties_merge_mopd_5_experts_k1_teacher_ratio_sampler_video_affordance_spatial_pointing_v2_0724_01/global_step_450/actor/huggingface`，完整路径和服务参数登记在 `configs/base_model.json`，服务名称为 `agent-action-base-gs450`。

训练后对照应固定案例、harness、工具语义、图像处理、提示词、历史与压缩规则、解码参数和预算。必须变化的项目另列实验，避免将模型训练收益与 harness 改动混在一起。评测案例与后续训练数据隔离，开发案例可用于调试；冻结评测集不用于提示词、checkpoint 或参数选择。

## 3. 共用评测约定

本地 base 正式开跑前冻结：

- **案例：**task、variant、layout、reset seed、模拟器初始 seed；能获取时记录初始状态校验信息。
- **环境：**RoboDojo、资产、机器人与控制器版本；核对观测来源、动作约束和执行语义。
- **预算：**物理步数、模型调用、token 和端到端超时；记录推理期间仿真是否暂停。
- **判分：**同一原生成功判定、部分完成分数和阶段指标。
- **差异：**登记模型、提示词、图像处理、历史策略、动作粒度和控制器差异。

先在 `stack_bowls` 独立开发案例验证完整运行、连续反馈、历史压缩与正常终止，并估计成本。随后直接沿用网页的 **10 个任务 × 5 个案例，共 50 案例**，保持原 case_id、seed、standard/random 配比和原生 horizon；不按新 base 的得分挑选。清单固定在 `configs/a_published_ten_task_panel.json`，来源为参考仓库 `public_results/evaluation_cases.json` 的 `gpt` 案例。它是网页子集对照，不代表整个 RoboDojo。

正式运行采用事先确定的预算与停止规则，不在中途调整。开发案例应至少验证一次正常原生终止或规范的预算终止，并保存最终结果；不要求成功。若预算不足以覆盖原生 horizon，明确报告预算受限的表现。基础设施中断保留在尝试记录中，不能把未判分直接填成原生零分；同时报告计划数、尝试数、原生完整数、预算截断数、异常数与成功数，避免只对完成案例汇总。

新 base 与网页旧 Direct 按案例逐例配对，报告原生成功率、可获取的原生分数、阶段进展及成本；旧记录中未完整判分的案例保留缺失状态，不补零。后续训练对比继续使用同一冻结案例。模型、上下文、推理参数与必要的 harness 修复分别登记。

## 4. 后续 harness 研究：move_to 与观测闭环

### 4.1 复用基础

本节记录可独立开展的 mini-swe-agent 接入，不作为 A 线首轮评测前置条件，本会话不推进其实现。下文“首轮”指 mini-swe-agent 接入的首轮。

mini-swe-agent 固定分支 `feat/python-tool-agent-service`，当前提交 `a9d2d82`。复用模型请求、持久 Python 会话、工具注册和图像消息能力。

首轮在主仓库写轻量 CLI runner，加载外部机器人工具集合。当前 HTTP AgentRunner 写死了内置工具集合，服务化按需后置。

```text
自有模型 API → run_python → move_to → RoboDojo 执行
      ↑                                  ↓
      └──── 当前图像、机器人状态、执行反馈 ──┘
```

机器人业务工具只有 `move_to`；初始观测与动作后观测由 harness 自动提供。

### 4.2 机器人与动作契约

机器人配置统一供工具说明、参数校验和执行器使用，参考 GPT-as-Policy 并核对现有环境。

| 项目 | 首轮约定 |
|---|---|
| 机器人与末端 | 双臂 ARX X5，各臂 `link6`；核对夹爪几何，不能套用其他机器人偏移 |
| 坐标与姿态 | 环境原点坐标系、米制、单位四元数 `wxyz` |
| 双臂与夹爪 | 显式左右臂目标；`gripper_closed=True` 对应原生 opening=0 |
| 动作限制 | 参考平移 0.05 m、旋转 0.35 rad 限幅，以及逐步 IK 和关节约束 |
| 动作片段 | 参考 25 Hz、每次 1–5 控制步；不保证一次调用到达目标 |
| 观测 | 头部与双腕图像、实测位姿、夹爪命令状态、执行反馈和剩余预算 |

```python
move_to(left: dict, right: dict, steps: int = 5)
# 每侧：position、quaternion_wxyz、gripper_closed
```

固定命令先验证保持姿态、平移、旋转、夹爪和非法目标，再接模型。首轮每个 Python cell 最多一次 `move_to`，运行时落实限制；动作超时先查回执，不盲目重发。

统一观测消息构造：将同一步的图像和状态实际送入模型，并保存输入清单。仅保存图片文件或返回字典，不算图像回传验收通过。模型声明完成不等于任务成功，终止由 runner 与原生环境状态统一处理。

短动作片段可能需要大量模型调用。先测真实 API 延迟和单 episode 调用量，再安排批量规模；更长片段只作为后续独立实验。

## 5. 历史图像与 Hybrid

### 历史图像：在选定且固定的 harness 内做 Direct 消融

| 配置 | 每轮直接呈现的图像 |
|---|---|
| H0 | 当前一组多视角图像 |
| H1 | 当前＋上一组观测 |
| H2 | 当前＋固定更长窗口，例如过去三组 |

固定文本历史处理规则、图像清晰度、控制器及主要预算，标记相机、时间和对应动作。明确旧图像能否通过 Python 变量、路径或裁剪图再次访问；未限制重访时，只称“默认图像上下文策略比较”。每个 episode 独立上下文。

比较成功率、阶段进展、恢复表现、token 和耗时。在开发集选择配置后冻结评测；关键帧策略按结果决定，不使用隐藏标签或未来信息选帧。

### Hybrid：Direct 基线完成后开展

流程为：VLA 提案 → Agent 接受前缀或通过 `move_to` 修正 → 新观测。保持 `move_to` 语义不变，另设接受策略提案的通路。

在同一 harness 内比较 Direct、VLA-only、Hybrid；另在小子集增加与 Hybrid 匹配提案刷新和执行步长的 VLA-only，排除调度变化的影响。固定 VLA checkpoint 和案例，记录动作来源。

重点分析：Hybrid 救回了哪些 VLA 失败、破坏了哪些原有成功、在哪个阶段介入，以及额外推理成本。如复现原版 Hybrid，单独登记模型、调度和工具差异。

## 6. 中间状态与日志

首个任务即接入少数可靠事件：**到位、抓起并保持、放置并稳定、原生任务完成**。优先复用任务谓词；暂缺可靠判定时，用视频人工标注少量开发案例，不先建设通用评分系统。

每个阶段记录是否曾达成、首次达成时间/步数、终局是否保持及是否退步。夹爪闭合不是抓取成功，短暂进入目标区不是稳定放置。评分隐藏真值不反馈给 Agent。

后续再增加顺序、恢复等指标。中间状态重置启动另建诊断集，验证状态和历史可重复性，与完整任务成绩分开。

每次运行保存：案例及配置版本、模型实际输入与工具调用、请求目标与实际执行、时间戳及回执、原生与阶段结果、终止原因和视频。凭据不进入日志。

协议错误、动作失败、预算耗尽和基础设施异常分别统计；列出计划/完成/有效判分数。重跑保留原记录，不选择最好结果。仿真时长与端到端耗时分开报告。

## 7. 实施顺序与验收

| 阶段 | 当前工作 | 验收 |
|---|---|---|
| S0 | 登记本地 base 与 Codex/适配器版本，验证多图、工具和连续反馈 | 实际 API 输入与模型响应可查，模型身份明确 |
| S1 | 在独立开发案例跑通 Direct，修复提前结束和收尾问题 | 动作与观测对应；原生或预算终止均有最终结果；异常如实记录 |
| S2 | 根据开发成本冻结代表性案例、预算和协议，运行 base 评测 | 每个计划案例有结果或明确异常状态，配套轨迹、视频和成本汇总 |
| S3 | 保存 base 基线，准备后续训练对照 | 冻结配置、模型标识和运行源码可复现，评测案例与训练数据隔离 |
| S4 | 按需接入 mini-swe-agent，开展历史图像实验 | 同模型对照，harness 或历史变化单独解释 |
| S5 | 按需开展 VLA-only、匹配调度 VLA、Hybrid 与任务扩展 | 协同收益、失败变化及额外成本可解释 |

**近期交付：**选定训练 base 的模型身份与配置清单；Codex Direct 开发闭环验收；冻结代表性评测清单；base 的逐案例结果、汇总报告及可追溯轨迹。原参考模型复现、mini-swe-agent 接入和 Hybrid 均不阻塞这批交付。

### 当前实现证据与缺口（2026-10-27 核查）

- 相邻 `GPT-as-Policy` 仓库已有 Codex＋Luban 适配的 Direct 开发轨迹；`qwen3.8-max` 的 `classify_objects` 开发运行执行了 400 个控制步后按当时用户要求停止，没有最终原生分数。
- `qwen3.6-flash` 的 `general_pickup` 开发运行存在模型反复提前结束导致的控制器异常。现有结果证明部分闭环可用，不等于正式 base 评测完成，也不能据此认定当前源码修复已验收。
- 参考仓库有未提交修改与未跟踪的本地适配代码。正式运行需保存实际执行源码、提交与 diff/内容哈希，不能仅记录上游提交。
- 本轮 base 身份已确定。尚需使用该模型验证完整 episode 闭环，冻结正式案例与预算，并生成正式汇总。旧开发案例与轨迹保留为调试证据。
- 本仓库新增 `agent_action` 辅助实现：双臂契约校验、逐步 ACK 的 `move_to` 执行器、外部工具集合及持久 Python 环境。15 项自动化检查通过，覆盖非法输入、单 cell 单次调用、图像 artifact 与丢失回执不重发；不代表真实模型多图输入已验收。
- `artifacts/fixed-command-04/` 保存 `classify_objects` 的真实固定命令检查：保持、平移、旋转、夹爪、非法目标拒绝、重复调用拒绝六项通过，共五个原生控制步。同步渲染设置已启用；实测夹爪反馈与最后命令分开记录。该运行主动结束于 smoke 预算，没有任务成功成绩；早期启动失败和修正前轨迹保留在 `fixed-command-01` 至 `03`。
- 固定命令开发检查入口为 `python -m agent_action.smoke --task classify_objects --port 19123 --output <新的绝对输出目录>`，需用 RoboDojo Python，并将主仓库及相邻 `GPT-as-Policy` 加入 `PYTHONPATH`。服务通过 `scripts/start_native.sh --task classify_objects --port 19123 --output <预先创建的服务输出目录>` 启动；`ROBODOJO_ROOT` 必须指向包含完整 Assets 的 checkout。该工具属于后续 harness 基础工作，不替代当前 Codex base 主线。
- 本地 base 已以原始 BF16 权重加载到 vLLM。真实 Codex 两轮三图与随机回执探针通过，随机颜色顺序复验耗时约 25 秒；证据为 `artifacts/base-inference-01/probe-02/result.json`，每轮实际模型输入和图片哈希保存在 `probe-bridge/`。启动、探针和短 Direct 开发入口见 [本地 base 推理链路](base-inference.md)。这仍不等于正式任务评测通过。
- `artifacts/base-inference-01/direct-02/` 已验证选定 base 经 Codex 完成两次有效决策和 6 个原生控制步，按 `decision_budget` 收尾，三路拼接视频 7 帧。原生任务未完成、不纳入成功率。运行暴露了动作参数反复越界、token 预算误分类及结束后继续调用的问题；本地 worker 已修复后两项，分别通过 `token-budget-check` 和 `terminal-guard-check` 真实运行验证。18 项自动化检查通过，汇总保存在 `artifacts/base-inference-01/validation.json`。下一阶段仍需完整开发 episode、成本预算与长历史验证，再冻结正式评测。

## 8. 参考

- [GPT-as-Policy 论文](https://arxiv.org/abs/2609.38537) · [配套实现](https://github.com/anonymous-report-421/GPT-as-Policy)
- [Direct 机器人契约](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/hybrid_rollout/robodojo/robodojo-gpt-only-rollout/context/eef_control.md) · [评测案例](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/public_results/evaluation_cases.json)
- [mini-swe-agent 指定分支](https://gitlab.x-peng.com/capek-harness/mini-swe-agent/-/tree/feat/python-tool-agent-service)
- [RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) · [内部研究规划](https://xiaopeng.feishu.cn/wiki/BiVhw63vgi8xvjkuxU3cTg1Bndg)
