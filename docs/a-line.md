# A 线：Codex Direct

本会话只推进指定 base＋Codex Direct；B 线由独立工作维护。

本会话 A 线指“指定 base＋Codex Direct”。当前先跑 `stack_bowls` 开发 episode，入口为：

```bash
bash scripts/run_a_stack_bowls.sh --output artifacts/a-stack-bowls-new
```

新运行按参考协议，仅使用原生控制步数限制。`configs/a_stack_bowls_development.json` 中叠碗固定为 800 步，`max_decisions`、`max_total_tokens`、`wall_seconds` 均为 0，表示关闭额外上限。实际预算和命令另存到 `<run>.plan.json`；原生成功可提前结束，达到 horizon 时仍未成功，汇总标为 `failure_control_step_limit`，停止继续发控制动作；成功可提前结束。仿真故障另记为 `aborted_simulator_error`，不伪造原生分数。

`artifacts/a-stack-bowls-01/` 在预算变更前启动，仍使用自身快照中的旧开发保护预算（800 步、800 次有效决策、4000 万 token、4 小时）。修改配置不会热更新已有 Python 进程，既有运行以其 `.plan.json` 为准，不能追溯标成新协议。详见 [参考评测限制](reference-evaluation-limits.md)。

网页案例从冻结清单提取各自的原生 horizon，单案例入口示例：

```bash
bash scripts/run_a_stack_bowls.sh \
  --case-id imitate_sorting_sequence__standard__g0__l0 \
  --output artifacts/a-published-sequence-new
```

此入口会按 case_id 切换任务、variant、eval seed 和布局，检查清单及布局哈希，并设置该任务的 1600 步上限；其余案例同样使用自身的 500–1600 步预算，额外决策、token、墙钟上限保持关闭。单次模型/RPC 超时和 300 秒服务启动超时仍保留，属于基础设施保护。

叠碗是独立开发任务。后续网页对照清单为 `configs/a_published_ten_task_panel.json`，逐例复用网页原 Direct 的十任务、每任务五案例（含原 standard/random 配比），共 50 案例。所有布局及原生支持轨迹的哈希与历史冻结清单一致；169 个历史原生源码文件中 165 个一致，4 处差异已保存到 `artifacts/a-published-comparison-audit/`，主要涉及图像同步和日志路径，另一个任务文件不属于这十任务。十任务评分代码保持相同；模型、上下文和适配器差异仍需在结果中单列。清单已准备，尚未批量运行。

## 运行跟进（2026-10-27）

工作区位于 NFS，共享文件更新与本机进程可见性应分别核查。旧运行 `a-stack-bowls-01` 已在 11:14 UTC 输出 `summary.json`，状态为 `controller_error`：最后确认执行到 147/800 控制步、累计约 591 万 token。仿真日志先报告 PhysX scene corrupted / simulation stopped，随后 controller 的动作 RPC 超时，清理 RPC 也失败。该次属于基础设施异常，未得到原生终止结果；运行中曾检测到 `sensors.mp4` 缺少 moov atom；退出清理后复验已可读取，共 148 帧（1920×360），视频保留用于复盘。另有 35 次 recoverable tool input 拒绝，回执标记 `no_execution`，不计作物理动作。

本机 `cnwlb-a100-p02152` 已加载固定 base（服务 PID 2486868，GPU 0），健康接口核对 checkpoint 成功，文本与三个相机视角的实际推理回包通过。验证证据位于 `artifacts/a-line-followup-20261027/`；冷启动因 NFS 依赖导入和预热超过十分钟，等待命令超时后原进程继续初始化并最终 ready，未重复加载。

新的叠碗开发运行目录为 `artifacts/a-stack-bowls-p02152-02/`，launcher 信息保存于同名 `.launch.json`（含主机、PID、GPU 和启动时间），仿真使用 GPU 1，模型复用本机 GPU 0 服务。新 episode 按启动时 plan 使用原生 800 步、关闭额外决策/token/墙钟上限；运行中的实验不标为完成。旧运行、原始预算及证据完整保留。验收继续检查历史压缩、图像输入、工具回执、失败分类和成本。

## 下一步验收

叠碗运行结束后，检查原生终止或预算终止、轨迹与视频、模型输入和工具回执、历史压缩、失败分类和成本，再记录开发报告。网页 50 案例在开发链路稳定、预算明确后按冻结清单推进；旧记录缺失的原生分数保持缺失，不填零。每个完成的子任务先检查、再单独 commit，运行中的实验不标成完成。

服务入口见 [固定模型推理服务](model-service.md)，基础闭环证据见 [本地 base 推理链路](base-inference.md)。

旧 episode 的错误时间线、成本和证据见 [叠碗首次运行复盘](experiments/a-stack-bowls-01.md)。
