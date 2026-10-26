# Agent-Action：RoboDojo Harness 与评测计划

V1.1 · 2026-10-26 · 实施计划，尚未完成模型评测

## 1. 目标与范围

在已跑通的 RoboDojo 环境中，并行推进银河 GPT-as-Policy 参考基线和自有模型主线。先做 Direct，再研究历史图像与 Hybrid，用完整任务和中间状态指标解释差异。

本阶段只做 harness 与评测。保留原始观测、模型调用和执行轨迹；数据集加工、训练及新动作表示后续再展开。

## 2. 两条并行路线

| | A：银河参考基线 | B：自有模型主线 |
|---|---|---|
| 实现 | GPT-as-Policy 原有实现 | Agent-Action-Model |
| Harness | Codex harness | mini-swe-agent |
| 模型 | 原实现支持的参考模型，登记实际版本 | 自有 base，使用已有远程 API |
| 首轮 | Direct 小规模复现 | 单个 `move_to`，跑通 Direct |
| 后续 | 原版 Hybrid | 历史图像实验 → 自有 Hybrid |
| 目的 | 验证参考系统在当前环境下的表现 | 建立可持续迭代的研究入口 |

A 线尽量保留原有工具、提示词、历史和执行机制；B 线参考其机器人动作契约。两条线不互相等待，不要求先统一代码后端。

首轮结果属于**系统基线对比**：模型和 harness 同时不同，不能把分数差距单独归因于其中一项。自有 API 适配 GPT-as-Policy、同模型跨 harness 对照均为后续可选实验。

## 3. 共用评测约定

开跑前共同冻结：

- **案例：**task、variant、layout、reset seed、模拟器初始 seed；能获取时记录初始状态校验信息。
- **环境：**RoboDojo、资产、机器人与控制器版本；核对观测来源、动作约束和执行语义。
- **预算：**物理步数、模型调用、token 和端到端超时；记录推理期间仿真是否暂停。
- **判分：**同一原生成功判定、部分完成分数和阶段指标。
- **差异：**登记模型、提示词、图像处理、历史策略、动作粒度和控制器差异。

先各跑少量开发案例，再冻结约 **3 个任务 × 5 个案例**。建议覆盖 `classify_objects`、`classify_objects_by_language`、`build_tower`；该规模用于摸底与成本估计，不代表整个 RoboDojo，也不足以证明小幅优势。链路稳定后再决定是否扩展到论文十任务子集。

## 4. 自有主线：move_to 与观测闭环

### 4.1 复用基础

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

### 历史图像：在 B 线 Direct 内做消融

| 配置 | 每轮直接呈现的图像 |
|---|---|
| H0 | 当前一组多视角图像 |
| H1 | 当前＋上一组观测 |
| H2 | 当前＋固定更长窗口，例如过去三组 |

固定文本历史处理规则、图像清晰度、控制器及主要预算，标记相机、时间和对应动作。明确旧图像能否通过 Python 变量、路径或裁剪图再次访问；未限制重访时，只称“默认图像上下文策略比较”。每个 episode 独立上下文。

比较成功率、阶段进展、恢复表现、token 和耗时。在开发集选择配置后冻结评测；关键帧策略按结果决定，不使用隐藏标签或未来信息选帧。

### Hybrid：两条线分别接入，再汇总对照

流程为：VLA 提案 → Agent 接受前缀或通过 `move_to` 修正 → 新观测。保持 `move_to` 语义不变，另设接受策略提案的通路。

B 线比较 Direct、VLA-only、Hybrid；另在小子集增加与 Hybrid 匹配提案刷新和执行步长的 VLA-only，排除调度变化的影响。固定 VLA checkpoint 和案例，记录动作来源。

重点分析：Hybrid 救回了哪些 VLA 失败、破坏了哪些原有成功、在哪个阶段介入，以及额外推理成本。A 线保持原版 Hybrid 运行方式，差异如实登记。

## 6. 中间状态与日志

首个任务即接入少数可靠事件：**到位、抓起并保持、放置并稳定、原生任务完成**。优先复用任务谓词；暂缺可靠判定时，用视频人工标注少量开发案例，不先建设通用评分系统。

每个阶段记录是否曾达成、首次达成时间/步数、终局是否保持及是否退步。夹爪闭合不是抓取成功，短暂进入目标区不是稳定放置。评分隐藏真值不反馈给 Agent。

后续再增加顺序、恢复等指标。中间状态重置启动另建诊断集，验证状态和历史可重复性，与完整任务成绩分开。

每次运行保存：案例及配置版本、模型实际输入与工具调用、请求目标与实际执行、时间戳及回执、原生与阶段结果、终止原因和视频。凭据不进入日志。

协议错误、动作失败、预算耗尽和基础设施异常分别统计；列出计划/完成/有效判分数。重跑保留原记录，不选择最好结果。仿真时长与端到端耗时分开报告。

## 7. 实施顺序与验收

| 阶段 | A：银河参考线 | B：自有主线 | 验收 |
|---|---|---|---|
| S0 | 核对原版启动配置与模型可用性 | 验证 API 多图、工具调用和连续反馈 | 冻结共同案例与机器人契约 |
| S1 | 跑通原版 Direct 少量案例 | 固定命令验证 move_to，接通单任务 | 动作、实际执行、模型观测对应正确 |
| S2 | 获取参考小规模基线 | 获取自有小规模基线 | 配对结果、阶段事件、失败原因与成本可查 |
| S3 | 继续原版 Hybrid | 历史图像实验，选定冻结配置 | 两条线独立推进，配置差异明确 |
| S4 | 提供原版 Hybrid 参考结果 | VLA-only、匹配调度 VLA、Hybrid | 协同收益及额外成本可解释 |
| S5 | 按需扩展案例 | 扩展任务与阶段诊断 | 汇总系统对比和自有单因素实验 |

**近期交付：**A 线跑出原版 Direct 参考轨迹；B 线完成“一个已有任务＋自有模型＋一个 move_to＋可靠图像反馈＋基本阶段事件”。先取得可解释轨迹，再扩大评测。

## 8. 参考

- [GPT-as-Policy 论文](https://arxiv.org/abs/2609.38537) · [配套实现](https://github.com/anonymous-report-421/GPT-as-Policy)
- [Direct 机器人契约](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/hybrid_rollout/robodojo/robodojo-gpt-only-rollout/context/eef_control.md) · [评测案例](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/public_results/evaluation_cases.json)
- [mini-swe-agent 指定分支](https://gitlab.x-peng.com/capek-harness/mini-swe-agent/-/tree/feat/python-tool-agent-service)
- [RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) · [内部研究规划](https://xiaopeng.feishu.cn/wiki/BiVhw63vgi8xvjkuxU3cTg1Bndg)
