# 共享机器人执行基础

`agent_action/robot.py` 固定双臂 ARX X5 的机器人契约：环境原点坐标系、`link6`、米制、单位四元数 wxyz、显式左右臂、每次 1–5 个 25 Hz 控制步；目标距当前测量位姿最多 0.05 m / 0.35 rad。`gripper_closed=True` 映射为原生 opening=0。

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
