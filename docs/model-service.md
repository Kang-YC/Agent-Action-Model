# 固定模型推理服务

服务使用用户指定的 base checkpoint，完整路径与参数固定在 `configs/base_model.json`；名称为 `agent-action-base-gs450`。

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
