# A 线与论文、网页 Direct 的协议核对

核对日期：2026-10-28。论文：[Systematically Exploring the Capabilities of GPT-6 Astra as Embodied Policies](https://arxiv.org/html/2609.38537v1)，重点为第3.1/3.2节和附录A.1、B.1；代码依据为本地 `../GPT-as-Policy` 的公开快照 `8f3d362b077d8efb77e2a7274d5b2c20e2243846`。论文没有逐项公开所有底层坐标细节，因此坐标与工具字段以发布源码为准，不将源码细节冒充论文原句。

## 已确认相同的动作协议

| 项目 | 网页/发布源码与当前A线 |
|---|---|
| 机器人 | dual ARX X5 |
| 服务工具 | `robodojo_start`、`robodojo_act`；A线不使用B线的 `move_to` |
| 动作空间 | 明确给出左右臂 EEF 目标，无pi05提案、直接关节命令或物体真值 |
| 位置坐标 | 两臂共用 environment_origin，单位米；目标是各自link6，不是指尖接触点 |
| 姿态 | 单位四元数wxyz；不是xyzw或直接欧拉角指令 |
| 夹爪 | gripper_closed布尔值；true→opening=0闭合，false→opening=1张开；夹爪指令不是抓取证明 |
| 位姿边界 | 相对当前测量EEF，欧氏距离不超过0.05m，旋转不超过0.35rad |
| 动作片段 | 1–5个25Hz控制步，每次真实ACK后重算有界DLS IK |
| 观测 | 顶部/双腕RGB、14维状态、测量EEF、原始指令和当前episode历史 |
| 案例 | 网页10任务×5例，保留case_id、layout/seed、standard/random比例与原生horizon |

对 skill/schema.py、server/validation.py、server/kinematics.py、server/client.py、Direct SKILL、eef_control、teacher_context 共7个文件逐字节比对，均与发布提交相同；tool_specs函数AST也相同。证据为 `artifacts/a-protocol-audit-20261028/contract.json`。发布README明确缺少原始模型会话，因此不能声称恢复了历史模型的完整上下文。

特别注意：link6坐标不等于指尖接触点。当前开发适配版额外解释了机器人局部+X方向及约0.145m名义接触参考；这不是服务层自动增加的位移，也不能宣称是网页原提示中已显式提供的同等信息。

## 开发运行与正式对照分开

第四轮叠碗继续使用启动时的开发适配版本：额外静态URDF/相机标定、内联几何说明、640长边预览、progress_aware_continuation_v2续接。它已验证工具闭环，但不能称为“只替换模型”的论文复现。旧提示词和快照不追溯修改。

正式网页案例使用 `prompt_protocol=published_reference`：

1. 在每次运行拥有的reference_source快照里，按原CodexPolicy的拼接方式组成Direct SKILL、teacher context和工作目录说明；仅替换模型身份陈述与运行路径。
2. 不复制额外robot_geometry，不增加内联静态标定、额外操作建议或续接提示。EEF契约仍通过原始context文件提供。
3. 将图像预览恢复为长边480，原始PNG仍保留原分辨率。该设置与论文附录A.1一致。
4. 将skill/run.py恢复为发布提交的原始recoverable_tool_input_v1事件循环，而非开发期新增的progress-aware续接。
5. 保留本地API接入、明确的原生控制步上限、案例身份和基础设施生命周期修复；动作验证、FK/IK、native评分逻辑不改。
6. 保存tools.json、PROMPT.md与协议元数据，manifest记录原始/适配后worker哈希和原始事件循环哈希，便于逐次审核。

测试通过执行实际源码的提示词表达式，确认其组合与发布版本一致；另验证额外标定块已移除、预览为480、原始事件循环逐字节一致，并对未知适配器版本拒绝静默改写。

## 不能抹去的差异

- 2026-10-29 起，新快照默认使用统一欧氏位移说明；2026-10-30 起，拒绝回执区分 response 类型错误与 ID 不匹配并保留原始错误。两者均不改变原生校验、动作或评分，manifest 记录适配版本与哈希；不能再将新快照的工具描述／回执称为与发布版本逐字一致。可选数值诊断默认关闭。上文逐字节一致结论仅适用于 2026-10-28 的原审计快照。
- 当前使用用户指定base checkpoint；论文使用GPT-6 Astra/xhigh。base的推理方式不等同于xhigh，不能伪称相同。
- 本地模型上下文为32768 token，压缩阈值约24576；发布源码不能提供历史所有会话的完整上下文。
- 本地Codex/Responses协议桥接、工具隔离配置、请求超时以及RPC空闲等待修复仍须作为系统差异记录。
- 原生源码与历史冻结资产存在的4处既有差异，继续沿用原审计，不因提示词对齐而消失。
- 400步仅用于叠碗开发验证；网页正式案例使用各自500–1600原生horizon，提前截断不伪称完整原生失败。

因此正式结果的准确表述是“指定base在与发布Direct动作协议及提示文本对齐的本地Codex适配链路上的配对评测”，而不是对原论文模型和全部历史运行环境的完全复现。
