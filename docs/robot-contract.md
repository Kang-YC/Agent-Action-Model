# 共享机器人执行基础

`agent_action/robot.py` 固定双臂 ARX X5 的机器人契约：环境原点坐标系、`link6`、米制、单位四元数 wxyz、显式左右臂、每次 1–5 个 25 Hz 控制步；每只手臂的目标点到本次观测末端位置的三维欧氏距离最多 0.05 m，姿态变化最多 0.35 rad。`gripper_closed=True` 映射为原生 opening=0。

`agent_action/native.py` 复用参考 RPC，每个真实控制 ACK 后重新计算受限 IK；模型目标不保证一次到达。保存目标、实际控制、逐步回执、原始观测和三视角图片。夹爪最后命令与原生反馈分开保存，不能把夹爪闭合当作抓取成功。RPC 不提供独立回执查询；不确定执行记录后停止，不重发动作。

`agent_action/toolset.py` 是可复用的外部 Python 工具集合，`RobotEnvironment` 在运行时限制每 cell 一次 `move_to`，并将图片接到图像 artifact 通道。A 线当前使用参考 Direct 工具，未将该工具集合替换进去。

固定命令开发检查：

```bash
export ROBODOJO_ROOT=/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo
mkdir -p artifacts/fixed-new/sim
bash scripts/start_native.sh --task classify_objects --port 19123 \
  --output "$(pwd)/artifacts/fixed-new/sim"
```

另一终端在主仓库根目录执行：

```bash
export PYTHONPATH="$(pwd):$(pwd)/../GPT-as-Policy:$(pwd)/third_party/mini-swe-agent/src"
/opt/robodojo-conda/envs/RoboDojo/bin/python -m agent_action.smoke \
  --task classify_objects --port 19123 --output "$(pwd)/artifacts/fixed-new/client"
```

`artifacts/fixed-command-04/` 已验证保持、平移、旋转、夹爪、非法目标拒绝、重复调用拒绝六项，共 5 个原生控制步；同步渲染已启用。15 项基础自动化检查通过。该运行是接口检查，没有任务成功成绩。

## A 线统一的 5 cm 定义

对左、右臂分别计算，坐标单位为米：

```text
dx, dy, dz = target.position - current_eef.position
sqrt(dx*dx + dy*dy + dz*dz) <= 0.05
```

这是目标点与当前测量点之间的直线距离，不是每个轴各允许 5 cm，也不是两只手臂距离相加或实际运动路径长度。steps=1 和 steps=5 使用同一目标距离上限。

- 位移 (3, 4, 0) cm：距离 5 cm，允许。
- 位移 (5, 5, 5) cm：距离约 8.66 cm，拒绝。
- 位移 (−4, 2, −3) cm：距离约 5.39 cm，拒绝。
- 左右臂各移动 5 cm：分别检查合格，不合并成 10 cm。

`RobotContract.translation_rule()` 是 A 线模型可见说明的统一来源。新运行在自有快照中将同一说明写入 SKILL、EEF 说明、robodojo_act 工具描述以及拒绝回执的 translation_constraint 字段。原生 `np.linalg.norm` 与本地 `math.dist` 校验均保持原有欧氏距离规则，不放宽阈值、不自动裁剪目标。

发布对照的 manifest 明确记录这项文字澄清及变更前后哈希；既有历史快照不改写，不能宣称澄清后的提示词仍与原发布版逐字相同。
