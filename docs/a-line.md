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

## 继续核查（2026-10-28）

第二次运行的共享产物已停在 330/800 步：仿真 `server_close`、原生评分无效，总汇总缺失。控制器在仿真关闭后仍重复读取观测；成本累计约 2276 万 token。视频已验证为 331 帧。详细证据与限制见 [第二次运行核查](experiments/a-stack-bowls-p02152-02.md)。当前主机为 `cnwlb-a100-p02080`，不能将原主机进程登记视为本机正在运行的服务。

已补上 launcher 的必需进程退出监测，避免无墙钟上限时仿真退出后控制器继续消耗推理。当前主机 GPU 0 已启动固定模型服务，登记独立保存在 `artifacts/base-service-p02080/`，未修改其他主机的服务登记。一次性续跑进程等待该服务健康检查（包括 checkpoint 一致性）通过后，在 GPU 1 启动 `artifacts/a-stack-bowls-p02080-03/`，保持 800 原生控制步、关闭额外预算；不恢复或覆盖旧 episode。等待最长一小时，服务退出或超时即失败，不自动重试。

续跑实时状态见 `artifacts/a-line-followup-20261028/state.json`，启动器和日志也保存在该目录；只有状态变为 running 且新目录产出实际轨迹后才算 episode 已启动。开发链路尚未通过完整验收，50 案例正式评测仍未启动。

### 第三轮实时核验（2026-10-28 06:54 UTC）

`a-stack-bowls-p02080-03` 已在 05:47:26 UTC 启动，固定模型 GPU 0、仿真 GPU 1。06:53 UTC 快照确认原生控制步 89/800，19 次有效决策；history 从 0 到 89 连续，`executed_steps` 合计 89，存在 19 个 execution 数组，与 progress 一致。launcher 和等待进程存活，模型持续返回 HTTP 200，未发现显存分配失败或场景损坏签名。尚无原生终止成绩。

累计约 202 万 token（快照之后仍在增长）。最近五个模型请求中四个含图像，图像数量分别为 5、2、2、2；另一个请求不含图像，不能据单个文本请求判断图像链路失效。RPC 日志已记录 11 个完成的 `contextCompaction` 事件，且此后继续产生动作；工作区 `agent/NOTES.md` 仍为初始模板，故压缩事件存在和执行可继续已证实，长期记忆保真尚未验收。16 次 recoverable input 拒绝包含位移越界、四元数/布尔校验和过期 observation，均为 `no_execution=true`，未计入控制步。

机器可读核验快照保存于 `artifacts/a-line-followup-20261028/live-audit.json`。保持本轮原配置继续运行，不在运行中改写提示或补写模型工作笔记。完成后再检查原生结果、完整视频、记忆保真与成本；50 案例正式评测仍待开发验收。

## 链路验收口径与并行准备（2026-10-28）

按用户确认，开发验收目标是完整链路与工具闭环，不要求叠碗成功。模型收到图像和状态、调用工具、仿真实际执行、返回回执与新观测、继续调用，并正常结束保存结果、轨迹和成本，即可通过相应链路验收。原生任务失败或耗尽 800 步不阻碍链路验收；排除工具、适配器与仿真问题后，将其作为模型能力结果。基础设施中断仍单列，不直接归因模型。

叠碗继续运行期间，并行完成网页 50 案例离线准备。入口如下，不启动仿真或请求模型；输出文件必须全新：

```bash
python3 -m agent_action.a_panel \
  --robodojo /dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo \
  --runs artifacts/a-published-runs \
  --output artifacts/a-panel-readiness-new.json
```

入口核对冻结 panel、原生预算、布局与支持轨迹哈希，生成每例 `next_command` 和历史尝试汇总。已有 `.plan.json` 必须与冻结案例一致；原生结果完整且顶层正常结束的案例标为 completed，任务失败也不重跑。未结束或异常尝试标为 needs_review，保留原生分数缺失，不会自动执行重试命令；多个完整结果直接要求复核，避免择优选择。新命令使用未占用的 attempt 目录，不覆盖旧证据。该入口提供继续执行清单，不是后台批量执行器，也不自动启动正式评测。

本次准备结果为 `artifacts/a-line-followup-20261028/panel-readiness.json`：50 计划、0 尝试、50 待运行，全部布局和支持轨迹通过哈希检查。原生任务源码的历史差异仍沿用既有审计，不因资产哈希通过就宣称环境完全相同。新增准备入口与预算相关检查共 13 项通过。

## 自动验收与第三轮结束核查（2026-10-28 07:40 UTC）

新增只读验收入口，独立检查工具闭环、正常终止、模型任务结果。任务失败不影响链路通过；基础设施中断不能算作正常完成。运行中报告为快照，不推断进程存活，也不提前扫描尚未封装的视频：

```bash
/opt/robodojo-conda/envs/RoboDojo/bin/python -m agent_action.a_acceptance \
  --run artifacts/a-stack-bowls-p02080-03 \
  --output artifacts/a-acceptance-new.json
```

报告检查连续 history、逐决策 execution 数组形状与有限数值、步数一致性、初始和最终反馈观测图像、模型请求中的实际图像、完成的压缩事件、`no_execution` 拒绝、正常终止结果、最终视频帧数及 token 成本。只记录压缩事件，不自动宣称记忆保真。输出必须使用新路径。验收入口及 A 线预算/评测准备相关测试共 19 项通过，其中覆盖原生失败仍通过、执行数组缺失拒绝通过、仿真异常和视频不完整拒绝通过。

第三轮已于 07:33 UTC 异常结束，不再运行。自动报告 `artifacts/a-line-followup-20261028/acceptance-live-01.json` 核实：25 次有效决策、117 个控制步，25 份执行数组完整且连续；26 份反馈观测有图片；135 个模型请求含图像，共 480 个 image parts；25 次输入拒绝未执行动作；18 次压缩事件。视频 118 帧可读取；总成本 3,140,324 token。工具闭环已验证，正常终止未通过，原生 success/score 保持 null。

launcher 本次及时检测到 `Simulator exited 0 while controller was running` 并清理控制器，输出完整顶层 summary，证明上一轮进程监测修复生效。仿真最后动作在 07:18:00，07:33:03 关闭，间隔约 900 秒；本轮冻结 RPC 源码设有 `connection.settimeout(900)`，捕获 timeout 后退出，server finally 又将原因写成 `server_close`。这与 RPC 空闲超时高度一致，但现有日志未保存捕获异常类型，仍标为待直接复现确认的基础设施原因，不归为模型原生任务失败。下一步应隔离复现 idle 超时并修复推理等待期间的服务生命周期，而非重复长跑叠碗。

### RPC 空闲退出隔离复现

使用本轮冻结 `reference_source` 的真实 RPC serve/protocol，在本机回环 TCP 上连接后不发包，仅将测试连接的 900 秒 timeout 缩短为 0.1 秒；不启动仿真、不加载模型、不修改参考源码。测试成功复现 serve 正常返回并记录 `controller_disconnect`。结合 server finally 无条件 `_write_summary('server_close')`，确认空闲超时可被现有日志掩盖成 server_close。脚本与结果位于 `artifacts/a-line-followup-20261028/reproduce-idle.py` 和 `idle-reproduction.log`。该复现确认机制存在；第三轮具体关闭异常没有独立异常日志，仍不能声称已捕获其原始 timeout 异常。

旧第二轮离线验收报告也已生成：`artifacts/a-line-followup-20261028/acceptance-previous-02.json`。顶层汇总缺失时仅标 incomplete，不据此推断其原主机当前仍在运行。

## 修复推理期间 RPC 空闲退出（2026-10-28）

A 线新运行仅在自己的 reference_source 快照中，为 RPC 每次读请求前加入 `select.select` 等待可读数据。模型思考期间不触发空闲截止；一旦开始传包，仍保留原 900 秒 socket 超时。连接 EOF 仍正常退出，launcher 继续监测必需服务并清理所属进程。原参考仓库、B 线和旧运行快照不变；manifest 登记补丁类型、原始/修改后哈希，reference_sources 记录实际使用源码。动作协议与原生控制步预算不变。

真实回环 socket 测试将传输超时缩短到 0.05 秒，验证空闲 0.15 秒后仍可收发合法请求；只发送部分包则仍会超时退出。与自动验收、案例准备及预算检查合计 22 项通过。

续跑使用新的 episode，不具备从旧仿真 117 步恢复的条件。07:52 UTC 两张卡核查：GPU 0 剩 7487 MiB，GPU 1 剩 9283 MiB；B 线固定占用 GPU 1 模型与仿真，单仿真约 7189 MiB。按用户要求选择剩余更多的 GPU 1 承载新的 A 线仿真，模型复用 GPU 0 的 19230 服务；不停止其他运行。新目录预定为 `artifacts/a-stack-bowls-p02080-04/`，独立仿真端口 19124、桥接端口 19231；启动记录与日志使用同名 `.launch.json` / `.launch.log`。GPU 共享情况作为本轮基础设施差异记录；未生成实际轨迹前不称为已跑通。

第四轮已于 2026-10-28 07:52:40 UTC 启动，launcher PID 2661831。07:53 UTC 仿真 RPC 19124 已报告 ready；模型服务复用 GPU 0，仿真在 GPU 1，与 B 线共享资源。尚无动作轨迹时只标记初始化，不标记闭环通过。补丁与推理、原生工具、服务管理相关检查共 30 项通过。新运行 manifest 已登记 rpc_idle_patch 及实际源码哈希。

### 第四轮首动作与自动跟踪（2026-10-28 08:02 UTC）

已确认本轮首动作实际执行到 3/800 步，保存 `execution_000.npz` 与新观测；模型此后继续推理。RPC 快照实际哈希与 manifest 的 `rpc_idle_patch.patched_sha256` 及 reference_sources 一致，确认本轮已加载空闲等待修复；真实长空闲验证仍须依靠后续运行证据，不能用单次动作替代。

GPU 1 在仿真加载后尚余 3404 MiB，未见显存分配或场景损坏错误。当前验收快照 `artifacts/a-line-followup-20261028/run04-monitor/initial-acceptance.json` 标记 incomplete：仅一次有效动作，尚不足以验证两轮连续反馈闭环；不表示实验失败。

独立只读跟踪进程 PID 2942395 已启动，登记 launcher 的 PID、启动标识和完整命令以防 PID 复用。每 30 秒将进度和成本写入 `artifacts/a-line-followup-20261028/run04-monitor/state.json`。launcher 退出后自动运行验收，输出该目录下 `final-acceptance.json` 并记录最终状态；不发送仿真 RPC、不请求模型、不停止进程。脚本、启动登记和错误日志也保存在该目录。正常结束、任务结果与链路验收继续分别记录。
