# B 线：本地 base 与 mini-swe-agent

当前主线固定为：`agent-action-base-gs450` → mini-swe-agent 的 `run_python` → 持久 Python → `move_to` → RoboDojo。模型路径和解码参数读取 `configs/base_model.json`，复用现有 `agent_action.client.BaseModelClient`，不经过 Codex 或 Responses 适配器。连接时验证模型服务返回的 checkpoint 身份，不自动替换模型或重试请求。

## 环境与探针

使用独立 Python 环境，避免修改正在运行的模型与仿真环境。本次环境为 `/tmp/agent-action-b-venv`，依赖清单为 `requirements-b.lock`；mini-swe-agent 使用仓库固定子模块的源码。

```bash
uv venv /tmp/agent-action-b-venv --python /opt/robodojo-conda/envs/RoboDojo/bin/python --system-site-packages
uv pip install --python /tmp/agent-action-b-venv/bin/python -r requirements-b.lock
export PYTHONPATH="$(pwd):$(pwd)/../GPT-as-Policy"
export LITELLM_LOCAL_MODEL_COST_MAP=True
export MSWEA_GLOBAL_CONFIG_DIR="$(pwd)/artifacts/b-mini-config"
/tmp/agent-action-b-venv/bin/python -m agent_action.b_probe --output artifacts/b-probe-new
```

探针由真实模型调用两轮 Python，读取每轮三张随机排序的颜色图片与随机回执，再提交两轮结果。输出保留预期答案、实际请求（压缩 JSON，含图片）、原始响应、usage、延迟、Python 图像 artifact 和完整轨迹。预期颜色不放入提示词或工具文本。

## 机器人开发闭环

等现有 A 线运行结束、释放仿真显存后执行。已启动一次性等待流程，届时只运行下面的短闭环预算，不启动批量评测。不要为释放显存停止其他运行。手动运行时，以下输出目录必须全新：

```bash
ROBODOJO_ROOT=/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo \
  bash scripts/run_b_line.sh artifacts/b-robot-new \
  --max-turns 10 --max-control-steps 10 --max-total-tokens 200000
```

入口启动独立原生后端，通过日志等待 ready，再连接唯一控制器；结束时清理自己启动的仿真进程。可用 `B_LINE_TASK`、`B_LINE_PORT`、`B_LINE_PYTHON` 配置任务、端口和控制器 Python。布局由 `--seed` 选择。原生服务默认评测组为 0。

初始三视角观测在第一次模型请求前送入；每个动作完成逐步 ACK 后，工具自动回传新三视角图像和同一步状态。H0 仅发送最近一组图像，保留文本历史；历史图片仍保存在轨迹文件。Python 变量跨 cell 保留，每 cell 最多调用一次 `move_to`。动作超出剩余控制预算直接拒绝，不裁剪模型动作。终止、控制步预算、模型轮数、token 与墙钟预算均独立记录；token 和墙钟预算在模型请求之间检查，最后一个请求可能越过阈值。32K 上下文耗尽会记录错误，不静默压缩或丢弃文本。

控制器保存执行源码副本与哈希、模型配置、轨迹、实际模型请求、动作回执、观测和收尾报告。`ReturnAnswer` 仅代表模型停止，不能判为任务成功；开发预算截断不纳入原生成功率。正式评测仍需原生完整 episode 和独立冻结的任务清单。

## 本次状态（2026-10-27）

- 已确认模型服务就绪，checkpoint 与指定路径一致。
- `artifacts/b-line-01/probe-01` 在依赖导入阶段退出，未发模型请求；随后关闭 LiteLLM 在线价格表下载，模型调用仍走本地客户端。
- `probe-02`：模型嵌套调用 `run_python`，并且未保存和展示图片，最终耗尽 5 轮预算；失败记录保留。
- `probe-03`：两轮图片和回执均送入模型，但最终把第二轮颜色复用于第一轮，未通过。
- `probe-04`：明确要求在 H0 切换图片前，把上一轮读图结果写入持久 Python 状态并打印。3 次模型请求后，两轮颜色和回执全部正确，探针通过。该记忆提示已同步到机器人 runner。
- `smoke-01`：仿真在 RPC ready 前因 CUDA 显存不足退出，未执行机器人动作。当时 base 服务和已有 A 线仿真共占满唯一可见 GPU。该次失败后按用户要求等待 A 线，未停止它；后续一次性排队状态见下节。
- 机器人短闭环、完整开发 episode、正式案例冻结及评分尚未完成。探针通过仅证明本次多图和工具反馈链路，不代表机器人任务能力。

19 项动作契约、ACK、Python 持久状态、H0 图像过滤与终止预算检查通过；正确加入相邻参考仓库的 `PYTHONPATH` 后，全仓 23 项检查通过。成功探针共 2558 token，模型请求耗时合计约 38 秒，仅代表协议验证成本。

所有尝试汇总在 `artifacts/b-line-01/validation.json`。原始失败记录与当前成功记录均保留。运行产物位于被 Git 忽略的 `artifacts/`，本次提交只包含代码、依赖清单、测试及文档。


## 顺序执行状态（2026-10-27 补充）

一次性等待进程已启动，状态写入 `artifacts/b-line-02/queue/state.json`，启动信息为 `artifacts/b-line-02/launch.json`。它登记当前 A 线 launcher 和 simulator 的 PID、启动时刻与命令，等待原进程退出且唯一可见 GPU 空闲显存达到 7500 MiB，再校验指定 base 服务并启动 `artifacts/b-line-02/smoke-01`。不会停止 A 线，不会因 PID 复用误把新进程当作原进程。等待最长 6 小时；资源不足、服务不符或运行错误均写入状态，不自动重跑。

本次短闭环预算固定为 10 个模型轮次、10 个控制步、20 万累计 token、1800 秒 agent 墙钟。外层另有 1 小时看护上限。短闭环结果需要检查动作 ACK、实际模型输入的动作后图片、终止分类和视频，再进入完整开发 episode；该等待流程不会直接启动完整 episode 或正式评测。

新增 evaluator 汇总保留原生 outcome 和有效判分标记；未完整判分的任务成功与分数保持 null，未收到 usage 的模型请求单列。控制预算和轮次预算按原生协议对应原因收尾。原生回执身份错误会留下不确定执行标记；Python kernel 超时、崩溃或状态丢失后停止，不重建机器人会话。此轮全仓 29 项检查通过，另验证了模型服务不可用时零模型请求、零动作且保留结构化错误汇总。后者证据为 `artifacts/b-line-02/unavailable-model-check/summary.json`。
