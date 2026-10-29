# A 线：Codex Direct

本会话只推进指定 base＋Codex Direct；B 线由独立工作维护。

本会话 A 线指“指定 base＋Codex Direct”。当前先跑 `stack_bowls` 开发 episode，入口为：

```bash
bash scripts/run_a_stack_bowls.sh --output artifacts/a-stack-bowls-new
```

当前叠碗开发预算为 **400 控制步**，原生 horizon 仍为 800，`budget_protocol=development_control_step_cap`。`max_decisions`、`max_total_tokens`、`wall_seconds` 保持 0，关闭额外上限。此设置用于链路验收，不要求任务成功；到 400 步未成功记为 `budget_censored`，不填原生零分。实际预算和命令存入 `<run>.plan.json`。网页 50 案例仍各自使用冻结的原生 horizon，不因开发预算缩短而改变。

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

## 网页案例原生身份与成绩归属（2026-10-28）

并行核查发现，原 `--case-id` 入口虽检查网页布局和预算，但未将身份传入原生 server，汇总也未要求结果身份一致。现已接入参考 server 既有 `--eval-manifest` / `--case-file` 路径，不改 native 判分代码。

`configs/a_native_panel60_v1.json` 冻结当前原生源码、布局与支持资产，并使用原生 60 案例 schema 提供身份校验。它是身份校验载体，实际待运行的评测范围仍是网页清单的 50 例；没有增加评测案例，也没有更换原网页布局。50 例均匹配载体中的 case_id、variant、eval_seed、layout_id、布局哈希和支持轨迹。当前源码与历史源码的差异仍按既有审计单列，不能据新载体宣称它们相同。

网页入口生成独立 `.case.json`，将原生 identity 写入 `.plan.json`；Direct 在启动仿真前调用原生 verify_assets 校验提交、源码与案例资产，复制 panel/case 到运行目录，再交由 server 校验和记录实际 reset 布局。manifest 同步保存 identity。叠碗开发入口不启用评测身份，已启动的第四轮使用其既有源码快照继续运行。

离线汇总现在要求 plan、manifest 和 `evaluation_outcome.json.evaluation_case` 与固定原生身份完全一致，才接受完整的原生成绩。旧记录缺失身份时标 needs_review，原始文件保留，不自动补身份或补分数；原生失败且身份与结果完整仍算有效完成，不因失败重跑。非默认身份载体可通过 `--native-panel` 指定，生成的命令同时携带该参数。

检查共 35 项通过，包含 50 例逐一身份匹配、启动参数传递，以及 outcome / manifest / plan 任一身份错配都不得计分。离线准备新报告为 `artifacts/a-line-followup-20261028/panel-readiness-with-identity.json`，仍为 50 待运行、0 已尝试。该验证未启动新的仿真，也尚未完成任一网页案例的真实原生判分验收。

08:14 UTC 第四轮进度为 9/800 步，自动跟踪状态 running；新入口修改未热更新或干预当前运行。


## 开发预算缩减为 400 步（2026-10-28 09:05 UTC）

按用户要求，后续叠碗启动配置从 800 缩减为 400 控制步，保留 native_control_horizon=800。开发入口允许正数且不超过原生 horizon 的预算；网页案例入口仍严格要求等于冻结原生 horizon。Direct 将提前预算结束单列为 budget_censored；自动链路验收接受规范的 control_step_budget 终止，不要求 native_score 或任务成功。预算与验收相关检查共 37 项通过。

网页冻结结果的上限范围是 500–1600 步：折衣 500、麻将 600、丢瓶 700，其余 1000–1600。叠碗不在网页十任务内。400 步适合本阶段工具闭环与退出流程验证，但不能保证任务完成，也不作为网页同协议成绩。

第四轮启动时仍为 800，原始 plan 和运行参数保持不变，不伪称配置已热更新。另启动预算守护 PID 696625，检查 launcher/controller 的 PID、启动标识与完整命令，每 0.2 秒观察日志与步数。它在首次完成动作且步数至少 395 时，只对登记的 controller 发 SIGTERM，使用其既有 finish/close 清理路径，尽量在 400 以内完整动作边界收尾；这是外部守护，不是进程内精确硬上限。当前动作每次 3 步，预期在约 396 步收尾；以实际记录为准。

守护状态、代码与日志位于 `artifacts/a-line-followup-20261028/run04-budget400/`，状态已确认为 watching，登记时进度45。触发后另写本轮 `budget_adjustment.json`，记录用户调整预算与实际停步；原始 termination 可能仍为 operator_interrupt、顶层为 controller_error，必须结合此证据解释为开发预算人工截断，不能归为模型原生失败或伪称完整原生终止。守护不停止 B 线、模型服务或其他实例。后续新运行在进程内逐控制步执行精确的 400 上限。

## 论文协议对齐与50案例执行器（2026-10-28）

用户要求完成网页联动后，整体运行网页十任务尚未运行的案例。随后补充论文 https://arxiv.org/pdf/2609.38537 并要求核对工具、提示词和夹爪坐标系。详细审计见 [协议对齐](a-protocol-alignment.md)。动作schema、坐标、位姿限制与FK/IK相同；开发期新增的静态标定、640预览和续接提示不混入正式对照。

网页案例入口现固定选择 published_reference 协议：恢复发布提示文本组合、480预览和原始事件循环，保留本地模型/API适配并单列不可消除的模型、32K上下文和xhigh差异。叠碗第四轮仍按自身已启动快照执行，不热改。

新增 agent_action.a_batch 串行执行器：只选从未尝试的冻结案例；每任务先覆盖一例，再按原案例顺序轮转补齐50例。已有成功、原生失败和异常尝试均不自动重跑。基础设施故障或缺失总汇总使队列停止并保留证据；完整原生失败正常继续。每例使用冻结原生horizon，不继承叠碗400步开发限制。执行器可等待指定开发运行退出，再检查模型checkpoint健康、GPU空闲显存与端口，整个过程不停止其他模型或B线。

批量运行将使用独立冻结harness和reference工作树，包含当前本地适配改动与未跟踪的Luban适配目录，不随后续主工作区修改漂移。每例仍保存实际源码和协议哈希。具体批次状态、来源和启动信息在准备完成后另记。

### 当前执行范围更新：先做两个任务

用户最新要求为“完成后再做2个网页要求任务，限制以官方原文为准”。因此首批缩为物体分类 classify_objects 与瓶子入桶 put_bottles_into_dustbin，各5个冻结案例，共10例；不直接启动完整50例。两任务的原生horizon分别为1100和700；开发叠碗400步不带入正式案例。按两任务逐轮交替顺序执行，所有布局/种子来自既有网页清单，不按新base得分挑选。

执行器通过--tasks固定子集，同时保留全50例身份载体与只针对本批10例的进度/成绩汇总。结果仅代表这两个任务，不能拿该子集的整体均值直接与论文十任务总分比较。后续是否扩到其余八任务另行执行。

批次目录为 artifacts/a-published-batch-20261028-two-task，运行目录为 artifacts/a-published-runs。批次会等待第四轮退出，冻结harness、reference及Codex可执行文件后再启动案例；网页可显示队列等待/运行状态和实际案例记录。案例之间没有自动重试，完整原生失败正常进入下一例；基础设施异常会停队列并保留可审查状态。

### 首批案例数最终确认

用户进一步明确“每个任务先1个案例即可”。首批最终为2任务×1例，共2例，固定选择各任务冻结清单中的首个案例：classify_objects__standard__g0__l0 与 put_bottles_into_dustbin__standard__g0__l0。分别使用1100和700原生控制步。并不执行此前计划的10例；也不将每任务单例结果冒充论文5例成绩。执行器--cases-per-task默认1，批次启动时也显式指定1，选例在运行前冻结，不根据新模型结果更换。

### 两案例队列已启动等待

2026-10-28 11:20 UTC，批次PID613946已启动，状态为 waiting_development_run：2任务、2案例、0已尝试，等待第四轮（当时185步）受控收尾。不是已开始执行官方案例。网页首页已通过API核验显示该队列及2例范围。

harness工作树冻结在 bf7edbab9fb09e3f7ca3ccfc41eaec629a94bd42；reference工作树固定公开提交8f3d362并保留必要本地适配补丁和Luban目录，逐例再恢复正式原提示/原循环。Codex 0.164.0及code-mode host二进制已独立复制并记录哈希。来源见批次source-manifest.json，精确的两个case_id见execution-plan.json；状态与汇总分别为state.json、results.json，日志batch.log。启动参数显式指定 --cases-per-task 1，不会在这批中自动补齐另外8例或网页剩余任务。

## 第四轮收尾与两案例实际执行（2026-10-29）

第四轮最后一次控制步更新为 2026-10-28 18:00 UTC，停在372步。之后仍反复读取观测114、查看同一组三图并进行上下文压缩，模型请求继续消耗 token。2026-10-29 02:21 UTC 核对控制器身份及无活动动作后，通过 SIGTERM 走既有 finish/close 路径结束；`budget_adjustment.json` 明确记录 `model_no_action_loop`、实际372步和原请求400步。此次没有达到预算守护的395步触发点，也不记为原生任务失败。

控制器原始 termination 为 operator_interrupt；启动器因仿真先于控制器退出而写 infrastructure_error。两份原始记录均保留，不能据该顶层标签推断此次是自发仿真故障。只读最终验收位于 `artifacts/a-line-followup-20261028/run04-monitor/final-acceptance.json`：114份执行数组、372控制步、115份图像观测一致；视频373帧可读取，累计51,597,280 token。工具闭环通过，正常终止未通过，原生success/score为空；396次压缩事件不代表记忆保真。

旧批次在0/2时因上述顶层异常标签停止。续跑批次为 `artifacts/a-published-batch-20261029-two-case-resume/`，02:22 UTC启动，复用旧批次冻结的harness/reference/Codex与原定两个case_id，未更换案例或自动重试。身份、预算和发布协议已核对。

分类 `classify_objects__standard__g0__l0--attempt-001` 于约02:31 UTC异常结束，仅执行1/1100步，累计149,467 token；控制器错误为 `Codex ended repeatedly before completing the episode`。日志显示模型在动作拒绝后多次结束文本回合，发布事件循环触发保护退出。结果为needs_review，原生成绩保持空值。瓶子入桶 `put_bottles_into_dustbin__standard__g0__l0--attempt-001` 随后启动，原生预算700步，已收到初始观测并发出工具调用；运行中不记录最终成绩。续跑状态、两例汇总和原始日志均在新批次目录，后续按实际终局核查。

### 两例提前退出的适配核对（2026-10-29）

逐份核对实际模型输入、上游回包、桥接输出及Codex turn完成记录，机器报告为 `artifacts/a-published-batch-20261029-two-case-resume/adapter-audit.json`。分类10份模型回包含7次工具调用，瓶子15份回包含11次工具调用；调用数量、call_id与原始arguments转换一致，没有发现桥接丢工具调用。两例各有3次普通请求返回 `finish_reason=stop`、仅文字且无tool_calls；对应输入均提供6个工具且tool_choice=auto。Codex均记录3个completed回合、error为空。瓶子另有一次无工具的压缩摘要回包，它不计入这3次普通回合。

两例实际运行的 `skill/run.py` 字节均与固定公开提交8f3d362一致。`continuations` 在episode开始设0，每次任务未完成的turn/completed后加1，允许2次续接，第3次触发 `Codex ended repeatedly before completing the episode`；中间实际执行动作不会清零。退出因此源于上游文本结束行为与发布控制器累计续接上限的组合，未发现本地桥接将已有工具调用误变为结束回合的证据。该核查不解释模型为何选择文本结束，也不能单独验证vLLM生成前的原始token解析；不据此扩大到全面适配正确性结论。旧结果保留，不自动重跑或修改冻结协议。

### 生命周期修复与耗时归因（2026-10-29）

后续开发运行快照增加900秒无物理控制步进展上限，独立于图片查看、shell和模型活动；沿用开发循环的连续无控制进展回合计数（成功执行后重置，12轮上限）。发布协议的原始两次累计续接限制仍作为冻结对照保留。桥接将同一助手文字及紧随的工具调用合并回单条Chat消息，保留调用ID与参数。启动器仅在仿真退出码0且控制器已写termination时允许最多30秒收尾；无终止记录或非零仿真退出仍立即报错。队列遇controller_error或未完成状态停止。网页依据实际停止原因区分预算与无进展中断，已重新加载网页服务。旧实验快照不改写。

修复相关30项测试通过，覆盖服务先退出的收尾窗口、无进展停止分类、消息合并和图片活动不能无限刷新物理进展期限；JavaScript语法及diff检查通过。

性能快照 `artifacts/a-published-batch-20261029-two-case-resume/latency-audit.json`：分类总559秒，10次模型请求合计457秒，1次有效动作处理约1.60秒，5次拒绝；瓶子总809秒，15次模型请求合计717秒，2次有效动作处理约5.18秒，5次拒绝；叠碗第四轮总66527秒，2473次模型请求合计64809秒，114次有效动作处理约307秒，145次拒绝。动作处理由调用前后文件mtime估计，包含RPC、图像反馈和保存；不是纯物理仿真内核时间。模型耗时包含共享服务排队、prefill和decode，现有记录不能可靠拆分三者。结论是模型侧等待与过多调用占主导，仿真动作处理占比很小。

### 轻量 thinking 对照准备（2026-10-29）

推理适配器现在支持显式top_k、repetition_penalty、parallel_tool_calls；未配置时保持既有行为。Direct支持显式auto_compact_token_limit，并在manifest记录最终压缩阈值，启动前检查其小于上下文窗口。full-access等运行权限保留，共享base配置未修改。相关16项测试通过。

轻量实验目录 `artifacts/a-thinking-probe-20261029/`：选取分类案例的四元数拒绝后和位移拒绝后两个真实请求，各测试thinking关闭／开启；共4次串行请求，每次最多1024输出token，温度0，其余消息和图像固定，使用当前消息合并后的适配器。返回动作只做离线参数校验，不执行任何机器人动作。原始输入、输出、计划和逐请求状态分别保存；1024上限下的截断仅说明该预算未完成输出，不能当作完整能力失败。共享服务排队计入墙钟，不能据此推断纯GPU生成速度。最终结果以该目录state.json/results.json为准。

本轮轻量对照未取得能力结论：首个thinking=false请求等待600.1秒后超时；脚本随即发出的thinking=true请求被主动取消，剩余两次未发送，共2次尝试、0份成功回包，token成本未知。状态记stopped_inconclusive，未执行机器人动作。已补充探针脚本的请求异常即停止逻辑，防止服务异常时继续发送后续样本。现有证据不能把该超时归因于thinking或模型能力，需先核查服务调度／请求处理。
