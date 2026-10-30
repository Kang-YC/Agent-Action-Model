# 固定模型推理服务

服务使用用户指定的 base checkpoint，名称为 `agent-action-base-gs450`。历史 eager 配置保留在 `configs/base_model.json`；A 线的新运行使用 `configs/a_model_compiled.json`，开启编译与单请求 CUDA Graph，保持同一 checkpoint、BF16 和 thinking=false。

## 环境与模型服务

固定服务入口（在主仓库根目录执行）：

```bash
bash scripts/base_service.sh start --wait  # 已运行时复用同一进程
bash scripts/base_service.sh status
bash scripts/base_service.sh logs --lines 20
bash scripts/base_service.sh stop
```

进程登记和历史启动日志位于 `artifacts/base-service/`。管理器核对 PID 启动标识、完整进程参数、模型名及 checkpoint；配置发生变化时要求先结束旧服务。当前已接管原进程，重复 `start` 实测保持同一 PID，没有重载权重。

统一调用入口支持文本和重复的 `--image` 参数：

```bash
bash scripts/base_infer.sh --text 'Reply with exactly: BASE_SERVICE_READY' --max-tokens 32
bash scripts/base_infer.sh --text 'Describe these views.' --image head.png --image left.png --image right.png
```

Python 调用使用 `agent_action.client.BaseModelClient().chat(messages, tools=...)`，支持标准 Chat Completions 消息和函数工具，返回原始响应及 usage。两种入口共同读取 `configs/base_model.json`，无自动模型切换或请求重试。HTTP 地址是 `http://127.0.0.1:19230/v1`，model 为 `agent-action-base-gs450`。

命令均在主仓库根目录执行。使用 Python 3.11，推理环境与 RoboDojo 环境分开。`requirements-inference.lock` 固定本次安装的依赖；推荐把环境放在容器本地盘，避免 NFS 上大量小文件影响安装和导入。

```bash
uv venv /tmp/agent-action-base-venv --python /opt/robodojo-conda/envs/RoboDojo/bin/python
uv pip sync --python /tmp/agent-action-base-venv/bin/python requirements-inference.lock
mkdir -p artifacts/my-base
BASE_MODEL_PYTHON=/tmp/agent-action-base-venv/bin/python \
  bash scripts/start_base_model.sh --output artifacts/my-base/runtime.json \
  > artifacts/my-base/model.log 2>&1
```

服务监听 `127.0.0.1:19230`，单并发，BF16，32K 上下文，eager 执行，关闭 thinking，温度 0。启动器检查全部 26 个分片存在且非空，并保存配置、tokenizer、模板、权重索引哈希，以及分片大小和 mtime；不会宣称已计算全部权重内容哈希。`runtime.json` 必须使用新路径。


依赖清单为 `requirements-inference.lock`。服务与 PID 隔离检查已通过；共享基础与 A 线自动化检查共 19 项通过。调用和服务管理使用同一配置文件。

## A 线编译配置（2026-10-29）

GPU 0 的服务配置切换到 `configs/a_model_compiled.json` 后，管理命令需显式指定该配置及本机登记目录：

```bash
bash scripts/base_service.sh --config configs/a_model_compiled.json --state-dir artifacts/base-service-p02080 status
bash scripts/base_service.sh --config configs/a_model_compiled.json --state-dir artifacts/base-service-p02080 logs --lines 20
```

同一地址 `127.0.0.1:19230` 和模型名继续提供 API。旧客户端的采样参数仍由各请求指定，但共享服务的执行模式已改变，跨切换窗口的 B 线耗时不能视为同一配置。使用旧 base 配置管理新服务会因配置哈希不一致被拒绝，不能忽略校验或伪造原配置。实际服务 PID、配置哈希及日志路径以 `service.json` 为准。

`enforce_eager` 缺省为 true，兼容历史配置；`compilation_config` 只在显式 `enforce_eager=false` 时允许设置。A 线配置使用 `cudagraph_capture_sizes=[1]`，与 `max_num_seqs=1` 对应，前缀缓存继续关闭。新 A 线开发及发布案例入口选择该配置，旧实验快照不改写。

2026-10-29 投瓶短回测前，A 配置 gpu_memory_utilization 从 0.90 调为 0.88，为同卡原生仿真留出显存；KV 容量变为 48576 token，单请求上下文仍为 32768。该变化区别于此前 0.90 的速度对照。两组回测均使用 0.88；08:13 UTC 服务就绪，PID 1202466，日志 artifacts/a-bottle-wording-backtest-20261029/compiled.log。回测结束后继续保留此编译服务，健康状态为 ready。

2026-10-29 抓碗长任务在上下文压缩时积累到 13 张图，被旧 max_images=12 拒绝。A 配置现提高为 32；10:08 UTC 重启后 PID 529962，日志 artifacts/base-service-p02080/20261029T100118-529936/model.log。编码器仍以 2048 token／8 图预算 profiling，KV 仍为 3.73 GiB／48576 token，CUDA Graph 池 0.04 GiB。原 13 图请求原样回放正常完成，证据 artifacts/a-image-cap-fix-20261029/replay-result.json；尚未重跑完整长任务。该变化只涉及 A 配置，旧 base 配置不改写。
