# B 线：本地 base 与 mini-swe-agent

当前开发任务已按用户要求改为 **stack_bowls（叠碗）**，与 A 线做同任务对照；分类任务的历史尝试均保留，最新叠碗入口和状态见文末。

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

## 恢复执行（2026-10-28，cnwlb-a100-p02080）

重新核查旧排队产物：`artifacts/b-line-02/queue/state.json` 最终为 `smoke_failed`，`smoke-01/sim.log` 明确显示默认 `/workspace/RoboDojo` 缺少 X5 资源。该次在原生 ready 前退出，没有 controller 目录，也没有模型请求或机器人动作；不是机器人任务失败。当前 `b_wait` 源码已包含共享资源路径，但旧进程执行的启动命令没有该修复，不能用当前源码推断旧进程的行为。

本次主机为 `cnwlb-a100-p02080`，与 A 线文档中 `cnwlb-a100-p02152` 的进程命名空间不同；不据本机 PID 判断另一主机运行状态。启动时本机两张可见 GPU 各有 81153 MiB 空闲，本机没有固定模型服务。已按锁定依赖恢复 `/tmp/agent-action-b-venv`；全仓 `pytest tests -q` 为 **38 passed**。`run_b_line.sh` 现在默认使用共享 RoboDojo 资源路径，仍支持显式 `ROBODOJO_ROOT` 与 `ROBODOJO_SHARED_ROOT`；shell 语法与 diff 空白检查通过。

固定 base 在本机 GPU 0 启动，服务登记独立保存到 `artifacts/base-service-p02080/`，避免改写其他主机服务记录。续跑进程及状态为 `artifacts/b-line-p02080-20261028/resume.py`、`state.json`、`resume.log`：等待服务身份校验通过后，在 GPU 1 运行全新 `smoke-01`，预算仍为 10 轮、10 控制步、20 万 token、1800 秒 agent 墙钟。模型冷启动等待上限 1800 秒；错误写入状态，不自动重试或切换模型。当前处于模型冷启动等待阶段，尚无本次机器人结果。短闭环结束后需检查 controller 汇总、动作 ACK、动作后模型图像输入及视频，再进入完整开发 episode。

## 短闭环验收与完整开发启动（2026-10-28）

本机固定模型已 ready，身份与 `configs/base_model.json` 一致。GPU 0 承载模型，GPU 1 承载仿真；同机 A 线另有运行，未停止或改动它。A/B 同时请求时观察到一个等待请求，尚未启第二个模型：现有模型权重加载即占 65.53 GiB，另需 KV cache 和运行显存，而两路仿真运行时 GPU 1 只剩约 67.7 GB（67658 MiB），不足以再启动同配置实例。

本轮 `smoke-01` 在初次 reset 时被人工过早中止，不能记作仿真死锁：第一次采样位于 PhysX UJITSO 碰撞预处理，第二次已推进至 render。更正后的干预说明和两份采样均在 `artifacts/b-line-p02080-20261028/`；该尝试 summary 为 infrastructure_error，零模型请求、零控制动作。随后新建 `smoke-02`，没有修改碰撞处理或仿真设置，也没有重发任何动作。

`smoke-02` 已完成并验收：

- 10 次模型请求全部返回 usage，共 58470 token，模型请求耗时合计 438.15 秒（含服务排队），controller 墙钟 492.58 秒。
- 两组真实动作分别执行 1 和 5 个原生控制步；6 个逐步 ACK 连续、身份与有效标记正确，没有不确定执行或自动重发。
- 另外 8 轮中，2 次四元数校验失败、4 次平移越界、1 次 Python 语法错误、1 次仅输出文字；均无额外控制动作。夹爪尚未完成抓取，不能据协议通过声称任务能力通过。
- 每次实际请求恰好携带当前三视角 PNG；图像内容哈希与最新观测匹配。第 5 次及后续请求已读取动作后观测，H0 保留文本而只呈现最新一组图像。
- 最终状态为 `LimitsExceeded`／`budget_censored`，原生 reason 为 `decision_budget`，控制步为 6/1100；成功与分数均为 null。
- `sensors.mp4` 可解码，1920×360，共 7 帧，等于初始帧加 6 个控制步。初始与终局相机画面已检查。17 项产物验收全部通过，证据为 `smoke-02.audit.json`，检查脚本为同目录 `audit_smoke.py`。

完整开发配置新增为 `configs/b_classify_objects_development.json`：任务 `classify_objects`，eval seed 0、布局 0，原生控制上限 1100，模型轮数、累计 token 和 agent 墙钟上限均为 0（关闭）。CLI 已支持这两个新增的零值预算，保留正控制步约束；新增检查验证大量历史调用/token/耗时不会触发已关闭上限，但仍在控制 horizon 前阻止后续请求。全仓 **39 passed**。32K 上下文上限和单次模型/RPC/kernel 超时仍保留，不自动压缩历史或重启会话。

完整开发运行 `artifacts/b-line-p02080-20261028/development-01` 已启动，监督器为 `development.py`，实时状态为 `development.state.json`，包含主机、PID、GPU、实际命令、冻结 plan 及其哈希、最新观测和模型请求数。运行仍在进行，不标为完成；结束后监督器会登记返回码和 controller summary。该布局已用于调试，后续不得当作独立 held-out 案例。下一步检查完整 episode 原生终止／上下文或基础设施错误、动作拒绝率、视频和成本，再冻结 B 线正式评测方案；当前没有启动批量评测。

## 全历史开发结果与显式窗口策略（2026-10-28 续）

`development-01` 已结束，不能再标为运行中。最终确认 **80/1100 控制步、16 组动作、26 次成功模型请求、365062 token**；controller 墙钟 1103.00 秒，模型请求耗时合计 1028.49 秒。第 27 次请求被 HTTP 400 拒绝：输入至少 28673 token，另预留 4096 输出 token，合计至少 32769，超过固定 32768 上下文。原 summary 的分类为 `infrastructure_error`，本次不改写历史产物；复盘明确归因为上下文耗尽，原生任务未结束，成功／分数仍为 null。监督器最后一次轮询的 75 步是滞后值，应以 controller 最终 summary 的 80 步为准。

复验 80 个原生 ACK 连续有效，16 组动作均 acknowledged，没有不确定执行。视频可解码，1920×360、81 帧。另有 2 次四元数拒绝、8 次平移越界；终局高位相机画面中物品仍在桌面，未完成分类。复盘证据为 `artifacts/b-line-p02080-20261028/development-01.audit.json`。本轮没有把完整开发失败记为原生任务零分，也没有重置旧 episode 或重发动作。

新增 **显式选择** 的 `--history-turns 8`，作为新的开发配置，不追溯修改旧 H0 全文本基线：

- 默认 0 仍保留全部文本。开启后保留初始指令、最近 8 组完整 assistant/tool 交互；若最新带图观测在窗口外，额外保留产生它的完整交互，避免错误重试期间丢失当前图像和状态。
- 图像仍按 H0 仅提供最新三视角。模型请求内明确提示有历史被移出、Python 变量仍然保留；原完整轨迹不删改，不生成带隐藏标签的摘要。
- 每次请求新增 `request_NNNN.history.json`，保存策略、保留消息索引及移出消息的索引／SHA256。固定 32K 上限、模型解码参数与动作契约不变；仍不自动重试请求、恢复丢失 kernel 或继续失败 episode。
- 新运行若遇相同上下文拒绝，会记为 `context_limit`／`context_exhausted`，并以相同原因收尾，不混入通用仿真故障。其他 HTTP 400 继续按原错误处理。

以原第 27 次溢出位置的完整消息进行真实 transport 验证：54 条消息保留 18 条，明确移出 36 条；输入 **13336 token**，输出 320 token，请求成功。验证未连接机器人、未执行返回代码，不是旧 episode 的续接。证据位于 `history-window-validation/validation.json` 及实际请求、响应、history audit。全仓 **44 passed**，覆盖完整工具配对、窗口边界、最新观测在窗口外时的保留、原消息不变、上下文错误独立分类及不重试。

窗口版完整开发配置为 `configs/b_classify_objects_window8_development.json`。新运行 `artifacts/b-line-p02080-20261028/development-02-window8` 已启动，仍是 `classify_objects`、eval seed／布局 0、原生 1100 步、关闭额外轮次／token／墙钟限制；GPU 0 模型复用、GPU 1 仿真。实时状态为 `development-window8.state.json`，监督器为 `development-window8.py`，包含实际命令、plan 哈希和最终汇总；最终状态会同步最终观测，避免旧监督器的滞后值。当前仍在运行，不宣称已解决完整 episode 或任务成功；后续需检查超过原 27 次请求边界后的历史窗口、原生终局／异常、拒绝率、视频和成本，再决定正式评测协议。

### 窗口版持续验收（2026-10-28 07:08 UTC）

继续保持当前 episode，不重启。最新核查为 13 次完成模型请求、35/1100 控制步，最近输入 11250 token；已启用历史窗口，但还未跨过旧运行第 27 次调用的失败边界。此前 6 次工具拒绝为 1 次四元数校验、5 次平移越界，不计控制动作。

新增独立只读验收进程 `artifacts/b-line-p02080-20261028/watch_window8.py`，每 30 秒更新 `development-window8.audit.json`，只读取产物，不连接机器人 RPC、不修改运行或自动重跑。它检查已确认动作的连续 step／episode／有效 ACK、每个已返回请求的完整工具调用配对、实际发送的三视角内容与最新观测、历史保留／移出计数，另记录是否已成功跨过第 27 次请求。当前检查通过。controller summary 出现后，继续验证视频解码和帧数是否等于最终控制步＋初始帧，并保存最终 summary；验收日志为 `watch-window8.log`。协议检查通过与任务成功分别记录，批量评测仍未启动。

## 按用户要求改为叠碗对照（2026-10-28 07:21 UTC）

B 线主开发任务改为 `stack_bowls`，对照 A 线正在运行的 `artifacts/a-stack-bowls-p02080-03`。新增配置 `configs/b_stack_bowls_development.json`，启动前核对 A 的实际 `.plan.json` 与 `base_model.json`：同 checkpoint 和解码参数、eval seed 0、布局 0、原生 800 控制步，均关闭额外模型轮次／token／episode 墙钟上限。B 仍使用 mini-swe-agent、持久 Python、`move_to` 与显式 8 轮文本窗口；A 使用 Codex 的提示词和上下文管理。这是匹配任务条件的 harness 开发对照，不是仅改变单一因素的消融实验，也不是正式成功率结论。

分类窗口运行已按换任务要求停止，最后确认 **100 个控制步、26 个有 usage 的模型请求、277593 token**。共有 28 份请求输入，其中 2 次没有 usage，包含中断请求；不将它们当成零成本。首次 SIGINT 暴露旧版 `abort_exceptions=[Exception]` 未覆盖 KeyboardInterrupt，mini-swe 的重试包装器继续请求。现改为 `[BaseException]`，新增真实 query 路径的回归检查，确保中断只调用一次；全仓 **45 passed**。旧运行随后按明确进程身份停止 B controller/kernel，并清理本次 B 仿真，A 线未停止。分类视频已复验可读取，101 帧；原 controller 未生成终止 summary，因此独立保存 `classification-task-switch.json` 和 `classification-task-switch.summary.json`，标记 `operator_interrupted`，成功／分数保持 null，不伪造原生失败或改写旧产物。

新叠碗运行目录为 `artifacts/b-stack-bowls-p02080-01/`，模型复用 GPU 0 服务，仿真使用 GPU 1、端口 19134。监督器与实时状态分别为同名前缀 `.supervisor.py`、`.state.json`，包含实际启动命令、配置哈希、A 线对照路径、最新观测和最终汇总。仿真已 ready；reset 后监督器会记录两线的实际 metadata、resolved config 各分组和初始观测 fingerprint 比较。初始机器人 proprio 哈希或图像相同也不宣称完整物理状态逐比特一致。

独立只读验收进程为同名前缀 `.audit.py`，结果为 `.audit.json`；持续检查动作 ACK、图像、工具配对、历史窗口，结束后检查视频和终止结果。新任务运行中不标为完成；先看叠碗原生结果、任务进展、成本和失败原因，再与 A 线相同布局的最终结果并列比较。可复用命令：

```bash
CUDA_VISIBLE_DEVICES=1 B_LINE_TASK=stack_bowls B_LINE_PORT=19134 \
  bash scripts/run_b_line.sh artifacts/b-stack-bowls-new \
  --seed 0 --max-control-steps 800 --max-turns 0 \
  --max-total-tokens 0 --wall-seconds 0 --history-turns 8
```

叠碗 reset 后已核对：task／layout_id／eval_seed／800 步 horizon／control_dt／frame／相机列表一致；实际 resolved config 的 sim、scene、camera、robot、eval_cfg、deploy_cfg、task_env 七组全部一致。初始机器人 states、EEF 位置／姿态、指令和 remaining_steps fingerprint 一致；三路 RGB 内容哈希不同，初始高位画面人工检查为相同三碗布局，仍如实保留渲染差异，不宣称输入图像逐像素相同。

## 叠碗持续跟进（2026-10-28 07:42 UTC）

当前 `b-stack-bowls-p02080-01` 继续原配置运行，已确认至少 42 次成功模型请求、80/800 原生控制步。实际 episode 已跨过旧全历史版第 27 次请求的溢出位置；窗口开启后的近期 prompt 约 6–9K token，未观察到上下文溢出。独立验收的 ACK、完整工具配对、三视角最新观测内容检查持续通过。这证明当前长度下窗口有效，不宣称已验收完整 800 步。

新增只读离线诊断 `artifacts/b-stack-bowls-p02080-01.diagnose.py` 与 `.diagnostics.json`：只解析已捕获请求、响应和轨迹，使用 AST literal 识别直接给出的目标，不执行模型 Python，不求值动态表达式，不回传纠正或隐藏标签。最新快照含 1 次四元数错误、16 次平移越界和 1 次语法错误。第 41／42 次请求右臂目标距实测 pose 分别约 0.163／0.113 m，超过 0.05 m；左臂目标为当前 pose。请求仍正确收到 observation_0016，而不是回传错步图像。

人工检查 observation_0016 高位图，三个碗仍分开位于桌面；模型声称已抓起／准备叠放不作为阶段达成或成功依据。当前瓶颈为无效目标与模型对真实执行／抓取的判断，不是已证实的 transport 或上下文故障。暂不改变该 paired run 的提示词、动作限制或反馈格式；结束后依据原生结果和视频决定是否另开具备结构化距离反馈的新配置。全仓当前 **61 passed**（包含并行 A 线新增检查）；本轮未修改 A 线实现或运行。
