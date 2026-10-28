# B 线启动提示词：本体状态与静态标定

这次改动用于后续新启动的 B 线运行；不热更新旧进程，不改写已失败的叠碗记录，也不自动发起新 episode。

## 论文与实际输入核查

参考[论文 3.1 和附录 A.1](https://arxiv.org/html/2609.38537#A1)，RoboDojo Direct 使用三视角、14 维本体状态、实测 EEF、指令、历史、进度／预算和完成规则；动作是受限的双臂位置、朝向与夹爪命令。只对照 RoboDojo Direct，不把 RoboLab 的 Franka 或其他域的特权物体状态搬进来。论文正文没有发布完整逐字 RoboDojo 启动 prompt；具体 link6／硬件和相机细节还要核对参考实现与真实模型请求，不能声称论文逐字要求某个 URDF 文件。

旧 B 首次请求已具备机器人型号、environment-origin、link6、米、wxyz、5cm／0.35rad、1–5 步／25Hz、三图及 EEF；但没有给模型原生 14 维 states，也没有等价的静态硬件／相机上下文。核查证据为 `artifacts/paper-2609-38537-audit/checklist.json` 和 `b_actual_start_prompt.txt`。原始 NPZ 的 states.shape=(14,) 证明这是模型观测投影遗漏，不是仿真没有提供数据。

## 两类状态与 ACK

- `current_state`：左 joint1..6（弧度）、左 opening、右 joint1..6（弧度）、右 opening，共 14 个原生本体状态。opening 约定 0 闭合、1 张开；不是触觉或抓取成功证据。
- `current_eef`：左右 link6 的三维位置与 wxyz 朝向。位置／朝向来自实测；动作后的 gripper_closed 表示最后被确认的夹爪命令。
- 关节状态通过机器人运动学得到末端位姿；相同末端位姿可能对应不同关节构型。EEF 信息不能替代整条机械臂的状态。
- ACK 是控制执行回执，表明原生控制步已被确认，不等于目标到位、接触、抓住物体或任务成功。

## 新版本如何让模型已知标定

`agent_action/b_embodiment.py` 从指定 RoboDojo 根目录读取静态资源，复用已审查的参考 geometry 推导器。它不会读取布局、物体真值、reward、先前 episode 或学习策略。B runner 默认构建此包，直接内联到 system prompt，而非只提供模型不可读取的文件路径。`--robodojo`／`ROBODOJO_ROOT` 与 `--reference`／`GPT_AS_POLICY_ROOT` 可指定相应源码根目录。

内联内容包括：

| 信息 | 内容和边界 |
|---|---|
| 硬件 | dual ARX X5，完整 robot_config，包括关节名、夹爪配置和相机安装 link |
| 双臂安装 | dual_x5 中左右安装位移／四元数；明确是配置值，不冒充运行时测量 |
| 运动学 | URDF 十个 joint 的 parent／child、origin、axis、limit／mimic；明确米、弧度和 Rz(yaw)Ry(pitch)Rx(roll) 约定 |
| 指爪几何 | 指爪相对 link6 的安装、边界和开合轴；手指伸出方向为 link6 局部 +X |
| 接触参考 | 局部 [0.145,0,0] 的近似配置参考；用实际 link6 姿态旋转到环境坐标，不能当成世界 Z 偏移或物体专属抓取点 |
| 三相机 | 分辨率、配置推导 K、固定／相对安装位置和 Euler 角、pose parent、USD/OpenGL 光学坐标约定 |
| 信息解释 | 两臂共享环境坐标；link6 不等于指尖；腕相机不是固定世界外参；像素不能直接当环境坐标或唯一深度 |

保存到每次新 run 的 `controller/embodiment_context.json`、`embodiment_source/` 和 `system_prompt.txt`。源文件和推导器代码均保存快照和 SHA256，manifest 保存 context 文件哈希。历史窗口保留初始 system，因此静态信息不会随最近八轮文本窗口一起移出。原始 14 维状态加入每次初始／动作后 observation，并自动进入模型工具反馈。

## 尚不能宣称已实测的部分

相机内参是配置推导值，不是 runtime Camera.get_intrinsics_matrix 的测量。当前 Isaac 相机源码和旧 B 日志显示 square-pixel aperture 自动调整，因此系统提示词明确标注 nominal，禁止将其视为精确运行时深度标定。腕相机外参还依赖其父 link 运动学，不能给固定世界变换。本次未启动仿真做运行时标定读回，不宣称这一项已验证。

通用 task_context／完成规则通道、历史图像裁剪工具和结构化停滞反馈不因加入标定就自动实现，仍是后续需独立对齐的接口。论文规定的信息边界与当前 harness 的剩余差异应继续列出，不能称完全等价。

## 验证

静态包只读取 7 个已记录静态源资源，并保存推导器快照。单元检查覆盖源快照、内联内容、坐标／状态解释、14 维观测字段和窗口切换后 system context 保留；全仓 77 项测试通过。

真实模型传输验证使用旧 episode 的记录初始观测，不连接机器人，也不执行返回 Python。实际请求、响应和统计保存于 `artifacts/b-embodiment-validation-v2/`。这只验证新增信息能进入模型，不是新 episode 或任务成功验证。用户最新决定恢复原生上限；下一轮采用 800 步叠碗上限，以新配置单独记录，保留此前 400 步标准下的失败记录。
