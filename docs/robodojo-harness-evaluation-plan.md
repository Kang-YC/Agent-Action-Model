# Agent-Action：RoboDojo Harness 与评测计划

版本：V1.0

日期：2026-10-23

状态：实施计划；本文不代表已经完成模型评测。

## 1. 目标与当前结论

以 mini-swe-agent 为主 harness，在已有 RoboDojo 环境中接入自有 base 模型，通过一个 `move_to` 机器人工具完成 Direct 控制评测。同期建立 GPT-as-Policy 适配基线，随后研究历史图像影响，再扩展到 Hybrid，并利用任务中间状态解释能力差异。

本阶段交付四类结果：

1. 可重复运行的机器人 harness 与 `move_to` 工具。
2. 同一自有模型在两套 harness 上的 Direct 对照结果。
3. 历史图像实验、VLA-only / Hybrid 对照结果。
4. 包含完整任务、子目标和执行诊断的评测报告。

数据集加工、SFT、RL、Action Token 和 Action Expert 不在本阶段展开。本阶段保留后续研究所需的原始执行记录。

## 2. 已确定条件与待核对项

| 项目 | 当前状态或决定 |
|---|---|
| 研究主仓库 | `/Users/xpeng/dev/Agent-Action-Model/` |
| 主 harness | `third_party/mini-swe-agent`，以 Git submodule 管理 |
| harness 分支 | `feat/python-tool-agent-service` |
| 当前固定提交 | `a9d2d8202a3553484f17d669c57d9ab7aa45968a` |
| 评测环境 | RoboDojo 已配置并可运行，无需重新搭建 |
| 自有模型 | 已有远程 API；模型标识、协议兼容性和推理配置在实施时登记 |
| Direct 工具 | 仅一个机器人业务工具 `move_to` |
| 参考系统 | GPT-as-Policy 的 RoboDojo Direct 路径；后续再参考 Hybrid |
| 正式评测原则 | 冻结模型、提示词、工具、控制器、案例和预算后运行 |

实施前核对：现有 RoboDojo 与控制器版本、资产版本、机器人末端定义、API 多图与工具调用支持、模型上下文长度。核对工作不重复环境部署。

## 3. 系统组织与代码边界

### 3.1 主调用路径

```text
评测 Runner：选择任务、初始化场景、设置预算、收集结果
    ↓
mini-swe-agent ←→ 自有 base 模型 API
    ↓ run_python(code)
move_to：参数校验、观测版本绑定、动作提交
    ↓
RoboDojo：控制器执行、仿真推进、原生终止与判分
    ↓
最新图像、机器人状态、执行反馈 → harness → 模型
```

Agent 是动作决策循环。RoboDojo 服务执行动作并返回观测，首轮不在仿真服务内部再嵌套模型调用。

### 3.2 复用与新增

| 组件 | 实施方式 |
|---|---|
| 模型请求与工具协议 | 复用 `LitellmPythonModel`，先验证远程 API 兼容性 |
| 持久 Python 会话 | 复用 `PythonToolEnvironment` 与现有会话实现 |
| 工具说明与注册 | 复用 `ToolSpec / ToolPrompt / ToolRegistry` |
| 图像回传 | 复用现有图像产物与消息转换能力 |
| 机器人工具、观测与动作适配 | 在主仓库新增 |
| 评测案例、预算、指标与分析 | 在主仓库新增 |

当前分支的 HTTP `AgentRunner` 写死了内置工具集合，但底层 `PythonToolEnvironment` 支持外部工具集合。首轮采用主仓库中的轻量 CLI runner，直接加载机器人工具。需要 HTTP 调度时，再将服务的 `toolset/context_factory` 配置化。

建议目录：

```text
Agent-Action-Model/
├── third_party/mini-swe-agent/
├── src/agent_action/
│   ├── tools/                 # move_to、参数契约、工具注册
│   ├── robodojo/              # session、观测、执行桥接
│   ├── runner.py              # 单 episode 生命周期
│   └── evaluation/            # 案例、批量运行、指标与汇总
├── configs/
│   ├── robot.yaml
│   ├── models/
│   ├── harness/
│   └── evaluation/
├── scripts/
└── tests/
```

以上是拟议结构，不表示模块已实现。模型权重、原始图像和大体积轨迹存放在实验存储中，Git 保存代码、配置和数据清单。

## 4. 机器人配置与 move_to 契约

### 4.1 配置原则

以 GPT-as-Policy 的双臂 ARX X5 控制契约为参考，与现有 RoboDojo 版本逐项核对。工具说明、参数校验与执行器读取同一份配置，避免三者不一致。

| 配置项 | 参考约定与实施要求 |
|---|---|
| 机器人与末端 | 双臂 ARX X5；末端定义为各臂 `link6` |
| 坐标系 | 环境原点坐标系；两臂使用共同坐标轴 |
| 位置与姿态 | 位置单位为米；单位四元数顺序为 `wxyz` |
| 夹爪 | `gripper_closed=True` 对应原生 opening=0；False 对应 opening=1 |
| 目标限幅 | 相对当前实测位姿，平移不超过 0.05 m、旋转不超过 0.35 rad |
| 执行粒度 | 一次执行 1–5 个控制步；参考控制频率 25 Hz |
| IK 与关节限制 | 核对逐控制步 IK 更新、局部增量与关节限幅实现 |
| 相机 | 核对 `cam_high`、`cam_left_wrist`、`cam_right_wrist`，以及图像方向和尺寸 |
| 任务完成条件 | 沿用原生判定，包括任务要求的机器人归位条件 |

末端位姿、夹爪几何和目标位置必须一致。不能把其他机器人的夹爪偏移直接套到 X5，也不能仅根据偏移标量猜测偏移轴。

### 4.2 工具接口

模型的外层执行工具沿用 `run_python(code)`，机器人业务工具仅注册 `move_to`。

建议接口：

```python
move_to(left: dict, right: dict, steps: int = 5)
```

每侧目标结构：

```python
{
    "position": [x, y, z],
    "quaternion_wxyz": [qw, qx, qy, qz],
    "gripper_closed": False,
}
```

左右臂目标显式填写；保持某侧不动时使用当前实测位姿。夹爪开合包含在 `move_to` 中，不另设业务工具。

`move_to` 表示执行一段有界运动，不保证目标已经到达。返回实际位姿、执行步数、错误信息和终止状态。

### 4.3 自动观测与执行约束

- episode 启动时自动注入初始图像和机器人状态。
- 每次动作后自动向模型呈现新图像、状态、执行反馈和剩余预算。
- `episode_id / observation_id / action_id` 由适配层维护，拒绝过期观测对应的动作。
- 首轮每个 Python cell 最多执行一次 `move_to`；限制在运行时落实，避免代码循环绕过动作预算。
- 执行动作超时后先查询回执，不盲目重发，防止重复运动。
- Agent 只能访问允许的观测；环境隐藏状态与评分内部变量保留在服务端。工具白名单不能替代进程与数据隔离。
- 模型提交结束不等于任务成功。环境原生判定、模型主动结束和预算耗尽分别记录。

## 5. 实施阶段与验收

### P0：接口与参考实现核对

工作：

1. 登记 RoboDojo、控制器、资产、mini-swe-agent 和参考代码版本。
2. 验证模型 API 的多图输入、原生工具调用、tool result 图像、连续多轮和上下文限制。
3. 用约 10–20 条协议检查样例确认调用可用性，记录服务延迟与错误行为。
4. 检查 GPT-as-Policy 原路径接入自有 API 的改动范围。

验收：明确工具协议、机器人配置和版本差异；能连续完成模型请求、工具调用和图像反馈。若需文本代码输出适配，配置单独命名并记录，与原生工具调用结果区分。

### P1：move_to 与单 episode 闭环

工作：

1. 接入现有 RoboDojo 执行接口。
2. 用固定命令验证保持姿态、双臂分别平移、旋转、夹爪开合和非法目标处理。
3. 接入自有模型 API，修改静态问答提示词为机器人执行提示词。
4. 完成一个已有任务的全过程运行，并验证 episode 间状态隔离。

验收：目标动作、实际运动、返回观测一致；任务可以正常终止并生成完整记录。模型成功率不作为环境桥接正确性的唯一判据。

### P2：两套 harness 的 Direct 对照

工作：建立 GPT-as-Policy 适配基线与 mini-swe-agent 主线基线，使用同一自有 base 和相同案例。先在开发场景调试，再冻结约 3 个任务 × 5 个案例。

验收：逐案例结果可配对，差异可以追溯到模型消息、观测、动作或运行配置；完成首轮失败归因和成本估计。

### P3：历史图像实验

工作：在 mini-swe-agent Direct 中单独改变图像历史，固定文本历史、控制器、图像清晰度和主要预算，选择后续默认历史配置。

验收：报告能力收益、输入成本与耗时变化。配置选择在开发集完成；冻结配置后评测，不反复针对测试案例调整。

### P4：VLA-only 与 Hybrid

工作：接入固定 VLA，比较 Direct、VLA-only 与 Hybrid，分析救回、破坏和介入阶段。

验收：模式与动作来源可追踪，明确协同收益及额外成本。必要时补 GPT-as-Policy Hybrid 参考对照。

### P5：扩展任务与阶段诊断

工作：完善已有任务的中间状态指标，按成本与覆盖需要扩展到论文十任务子集。

验收：报告完整任务、子目标、动作执行和恢复表现；原生 benchmark 成绩与新增诊断指标分开呈现。

阶段指标不等到 P5 才开始：P0 定义日志字段，P2 接入首批判定，P5 完善任务覆盖。

## 6. GPT-as-Policy 对照与复现范围

### 6.1 必做对照与可选复现

| 实验 | 模型 | Harness | 用途 |
|---|---|---|---|
| A | 自有 base | GPT-as-Policy 适配版 | 建立参考实现基线 |
| B | 同一自有 base | mini-swe-agent | 检查迁移后的系统表现 |
| C，可选 | 论文模型 | GPT-as-Policy | 检查参考系统复现程度 |

A/B 优先，C 根据模型可用性、适配结果和成本决定。只比较“论文模型＋原 harness”与“自有模型＋mini”，会同时改变模型和 harness，无法拆分差异来源。

公开 GPT-as-Policy 路径依赖 Codex CLI。自有 API 接入应尽量保留机器人控制、观测、任务提示和历史组织，只替换必要的模型调用部分。若无法保留原有执行机制，应明确标为“参考协议实现”，不能称为严格原 harness 复现。

### 6.2 配对与变量控制

- 两套 harness 尽量共用已验证的机器人执行后端；若共用后端本身偏离参考实现，需要登记差异。
- 配对 task、variant、layout、reset seed、模拟器初始 seed；能获取时记录初始状态校验信息。
- 固定模型版本、采样设置、控制器、动作约束和主要预算。
- 原始系统对比允许各自保留历史与工具组织方式，结论是系统整体差异。
- 历史图像等单因素实验在同一 harness 内完成。
- 3×5 用于发现大问题和估算成本，不能用于证明小幅优势。正式报告提供样本量及适当的不确定性说明。

首轮三任务建议为 `classify_objects`、`classify_objects_by_language`、`build_tower`，分别覆盖基础操作、语义约束与精确放置。该子集不代表整个 RoboDojo。

## 7. 历史图像实验

| 配置 | 输入图像 | 主要问题 |
|---|---|---|
| H0 | 当前一组多视角图像 | 当前观测的能力基线 |
| H1 | 当前图像＋上一组观测 | 是否改善运动、抓取和滑落判断 |
| H2 | 当前图像＋固定更长窗口，例如过去三组 | 是否改善阶段记忆，或引入冗余干扰 |
| H3，可选 | 当前图像＋固定规则选择的历史关键帧 | 能否降低历史成本并保留有效信息 |

所有历史图像标记时间、相机和对应动作。保持最新观测清晰度一致，固定文本历史；不使用隐藏成功标签、未来帧或测试结果选帧。记忆类任务单独报告。

比较指标：任务与子目标成功率、重复无效动作、恢复表现、输入 token、模型请求耗时和端到端耗时。

先做 H0/H1/H2，根据结果决定是否需要 H3。不同模型上下文容量不足时，应单独记录实际输入配置，不宣称输入条件完全一致。

## 8. Hybrid 实验

流程：当前观测 → VLA 生成提案 → Agent 接受提案前缀或使用 `move_to` 修正 → 新观测。

保持 `move_to` 的 Direct 语义不变。Hybrid 另设接受策略提案的执行通路，不把 VLA 隐藏在 `move_to` 内部。

| 模式 | 作用 |
|---|---|
| Direct | 模型直接构造动作 |
| VLA-only | 测策略本身的能力 |
| Hybrid | 测 Agent 审查与修正的增益 |

对齐 VLA checkpoint、任务案例与物理预算。提案长度、前缀执行范围和修正方式参考原实现并固定。不同执行频率或动作空间在报告中明确，不将其影响全部归因于 Agent。

重点报告：

- VLA-only 失败而 Hybrid 成功的案例。
- VLA-only 成功而 Hybrid 失败的案例。
- 接受提案与自主修正的比例、执行步数和发生阶段。
- 达成相同结果所需的模型调用、控制步数和端到端耗时。

## 9. 已有任务上的细粒度评测

### 9.1 指标层级

| 层级 | 示例 | 判定原则 |
|---|---|---|
| 动作执行 | 实测位姿接近目标、姿态误差 | 不能用下发命令代替执行结果 |
| 基础操作 | 抓起、保持、搬运、释放 | 夹爪闭合不代表抓取成功 |
| 子目标 | 正确分类、物体放入目标区域、积木正确摆放 | 明确位置、类别、姿态和稳定条件 |
| 阶段推进 | 首件完成、完成一层、完成顺序前缀 | 区分局部与累计进展 |
| 失败恢复 | 抓取失败后重抓、滑落后继续 | 定义触发条件、恢复窗口和分母 |
| 完整任务 | 全部要求完成及必要归位 | 使用 RoboDojo 原生判定 |

优先复用已有任务谓词。新增判定需明确阈值和稳定持续时间，并用成功、失败及临界案例检查。阶段得分不能取代原生 benchmark 成绩。

每个阶段记录：是否曾达成、首次达成的时间和动作数、终局是否保持、是否退步、是否重复完成。物体短暂进入容器后掉出，应区分“曾达成”与“终局保持”。

阶段判分默认只用于评测，不反馈隐藏真值给模型。观察到某阶段后的条件成功率可能受此前轨迹选择影响，需要与整体成功率一起解释。

### 9.2 中间状态专项评测

先分析完整 episode 的中间状态。后续确需隔离某一技能时，再建立单独的阶段诊断集，例如固定“已经抓起物体”的起点评测搬运与放置。

诊断集使用可重复的状态快照或经验证的初始化方式，明确是否提供此前历史。同一状态供各方法使用；不能只选某一方法有利的轨迹。诊断集结果与完整任务成绩分开报告。

## 10. 预算、日志与结果口径

### 10.1 独立预算

分别限制和记录：模型调用次数、物理控制步数、token、上下文长度、端到端超时。先通过开发运行估计调用密度与延迟，再冻结配置，不沿用静态问答默认轮数。

推理时仿真是否暂停也需固定并登记。仿真时长不能代替真实端到端耗时。

### 10.2 必留记录

| 类型 | 内容 |
|---|---|
| 运行身份 | run/case/episode ID，任务、场景、seed，代码与配置版本 |
| 模型输入输出 | 实际发送的图像与上下文、可见输出、工具调用、错误与 usage |
| 物理执行 | 请求目标、实际执行动作、控制步数、实测状态、时间戳、执行回执 |
| 结果 | 原生成功、原生分数、阶段事件、终止原因、视频 |
| 来源 | 模型版本、harness 类型、历史配置、VLA checkpoint 与动作来源 |

不要求模型提供私有思维链；只记录服务可用的标准输出、工具调用与必要的简短动作说明。凭据不进入实验产物。

### 10.3 失败与重跑

失败主要归因为：协议/代码执行、视觉与空间理解、动作参数、物理接触、任务组织与记忆、恢复失败、基础设施异常。

API 超时和仿真异常单列。报告计划案例数、实际运行数、有效判分数及失败分布；缺失分数不静默填零或剔除。基础设施异常按预先规定重跑，保留所有尝试，不选择最佳结果。模型主动停止、动作错误和预算耗尽按冻结协议统计。

## 11. 本阶段完成标准

1. 自有模型可经 `move_to` 完成真实环境交互，执行和反馈可核验。
2. 两套 harness 完成有限范围的 Direct 配对评测，差异记录完整。
3. 历史图像实验形成可解释的能力与成本结论。
4. Hybrid 与 VLA-only、Direct 在相同案例上形成对照。
5. 每个案例可追溯到模型输入、动作命令、实际执行、中间状态与最终判分。

不预设模型必须达到某一成功率。阶段价值是建立可信基线，识别感知、动作、历史与策略协同的主要瓶颈，为后续数据和训练决策提供依据。

## 12. 参考资料

- [Agent Action Model 内部规划](https://xiaopeng.feishu.cn/wiki/BiVhw63vgi8xvjkuxU3cTg1Bndg)
- [mini-swe-agent 指定分支](https://gitlab.x-peng.com/capek-harness/mini-swe-agent/-/tree/feat/python-tool-agent-service)
- [Systematically Exploring the Capabilities of GPT-6 Astra as Embodied Policies](https://arxiv.org/abs/2609.38537)
- [GPT-as-Policy 配套仓库](https://github.com/anonymous-report-421/GPT-as-Policy)
- [Direct EEF 控制契约](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/hybrid_rollout/robodojo/robodojo-gpt-only-rollout/context/eef_control.md)
- [Direct 动作 Schema](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/hybrid_rollout/robodojo/skill/schema.py)
- [公开评测案例清单](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/public_results/evaluation_cases.json)
- [参考系统源码与模型版本记录](https://github.com/anonymous-report-421/GPT-as-Policy/blob/main/hybrid_rollout/robodojo/SOURCE.json)
- [RoboDojo 官方仓库](https://github.com/RoboDojo-Benchmark/RoboDojo)

引用的实现细节以已检查源码为依据；本计划新增的模块名称、实验规模和执行顺序属于建议，实施时通过配置和版本记录冻结。
