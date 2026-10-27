# 本地 base 推理链路

模型固定为用户指定的 `global_step_450/actor/huggingface`，完整路径与解码参数见 `configs/base_model.json`。服务名称为 `agent-action-base-gs450`，不自动切换模型。配置中的 Qwen3.5 MoE 架构来自 checkpoint 自身，保留原始 BF16 权重。

链路：checkpoint → vLLM Chat Completions → 本机 Responses 适配器 → Codex app-server → 参考 Direct 工具 → RoboDojo。

服务启动、复用、停止和统一调用见 [固定模型推理服务](model-service.md)；当前执行顺序和网页对照见 [A 线](a-line.md)。

## 真实 Codex 多图与工具探针

模型服务就绪后，在另一终端启动适配器：

```bash
export PYTHONPATH="$(pwd):$(pwd)/../GPT-as-Policy"
/opt/robodojo-conda/envs/RoboDojo/bin/python -m agent_action.bridge \
  --output artifacts/my-base/probe-bridge
```

再运行探针，`--codex` 指向实际 Codex 二进制：

```bash
export PYTHONPATH="$(pwd):$(pwd)/../GPT-as-Policy"
/opt/robodojo-conda/envs/RoboDojo/bin/python -m agent_action.probe \
  --codex /root/.codex/packages/app-server-daemon/releases/0.164.0-x86_64-unknown-linux-musl/bin/codex \
  --output artifacts/my-base/probe
```

探针由模型连续调用两次动态工具，每次返回三张颜色图片和随机回执。第二轮改变图片顺序，最终逐项核对两轮颜色与回执。预期颜色只保存在评测端，不出现在提示词或工具文本里。该测试验证多图、工具回传和连续反馈，不代表机器人任务能力。

适配器复用相邻 `GPT-as-Policy/hybrid_rollout/luban_direct/bridge.py` 的协议转换；实际请求仅发到本机 vLLM，不使用 Luban 服务或密钥。兼容处理包括合并 Qwen 模板要求的初始 system 消息、通过 `chat_template_kwargs` 设置 thinking、限制输出长度。Codex SSE 在完整模型响应后发出，不是逐 token 透传；不自动重试上游请求。

`probe-bridge/*.input.json.gz` 保存实际 Codex 请求和模型输入，包含完整图片；`requests.jsonl` 记录图片哈希、工具名、耗时和 token；`*.output.json` 保存原始模型响应。每个探针使用独立 Codex home，禁用外部应用、子 agent 和 shell。生成目录必须全新。

## 短 Direct 开发闭环

先结束上述探针适配器。模型服务保持运行，以下入口自行管理适配器、仿真与控制器：

```bash
export PYTHONPATH="$(pwd):$(pwd)/../GPT-as-Policy"
/opt/robodojo-conda/envs/RoboDojo/bin/python -m agent_action.direct \
  --robodojo /dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo \
  --codex /root/.codex/packages/app-server-daemon/releases/0.164.0-x86_64-unknown-linux-musl/bin/codex \
  --output artifacts/my-base/direct \
  --max-decisions 2 --max-control-steps 10 --max-total-tokens 200000
```

沿用参考 Direct 的提示词、工具、校验器与动作执行方式。入口保存实际执行的参考源码快照、文件哈希、dirty diff、checkpoint 清单和预算。唯一 Codex 启动兼容处理是用包装脚本将参考 worker 的 128K 上下文配置覆盖为服务实际支持的 32K；包装脚本和启动参数同样保留。仿真期间推理会暂停物理执行。

本地主进程复用参考 policy 与工具循环，单独处理收尾分类：token 上限记为 `token_budget`，外层汇总为 `budget_censored`，不混入基础设施故障。原生或动作预算结束后，发送最后一份工具结果即关闭 Codex，不依赖模型主动停止；模型动作不做裁剪、代写或重试。token 限制按完成请求后的累计 usage 检查，包含重复输入，因此可能由最后一次请求跨过阈值，不是服务端的严格逐 token 上限。墙钟上限由启动器管理，未完成的运行保留异常和已有证据。

该运行是开发验证，预算截断不计作原生任务失败或成功。检查 `summary.json`、`controller/result.json`、`controller/history.json`、`sim/evaluation_outcome.json` 和 `sim/sensors.mp4`。只有原生环境给出成功判定，才能报告任务成功；模型自述不作为判分。

上面的两次决策命令显式使用短验证预算。通用 Direct 入口现在默认关闭额外预算，使用原生终止；正式 A 线请使用 [A 线入口](a-line.md) 从任务或冻结案例读取控制步上限。

后续先扩大开发闭环与预算，验证正常终止和成本，再冻结正式案例。当前图片上限与上下文预算面向短运行，长 episode 的历史与压缩策略仍需单独验证。

## 本次验证证据（2026-10-27）

完整汇总为 `artifacts/base-inference-01/validation.json`，所有尝试均保留：

| 运行 | 结果 |
|---|---|
| `probe-01` | 两轮三图和随机回执通过；有一次额外的无效文件看图调用 |
| `probe-02` | 关闭文件看图、随机化图片顺序后通过，约 25 秒 |
| `direct-01` | 执行 3 步后达到原 10 万 token 上限；参考 worker 误记为控制器错误，原记录保留 |
| `direct-02` | 两次有效决策、6 个控制步、7 帧原生视频，按决策预算结束；4 次非法动作参数被拒绝后由模型自行修正 |
| `token-budget-check` | 强制小 token 预算，0 个控制步，以 `token_budget / budget_censored` 收尾 |
| `terminal-guard-check` | 最终代码真实执行 1 步后按控制预算结束，终止原因 `native_runner_finished`；没有再次启动 episode 的调用 |

`direct-02` 在终止守卫修复前仍有结束后继续推理和试图重开 episode 的行为，原生守卫拒绝了重开，未发生第二次 reset；最终版本通过 `terminal-guard-check` 验证。该开发记录共 12 个已完成模型响应、206095 token，其中输入 201630、输出 4465；不能把这个成本当作完整任务成本。

18 项自动化检查通过。模型能正确使用多图和反馈，但四元数与 5 cm 目标限制仍会反复出错；当前未取得原生完整任务成绩。token 与延迟统计仅包含收到完成回执的模型请求，终止时已发出但未取得回执的请求在汇总中单列，不按零成本处理。

模型服务保留在 `http://127.0.0.1:19230/v1`，进程信息见 `active_service.json`；探针和 Direct 子进程均已结束。服务若已退出，可按前面的命令重启，使用新的 runtime 清单路径。
