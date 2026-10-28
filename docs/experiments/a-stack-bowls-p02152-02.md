# 叠碗第二次开发运行核查

核查时间：2026-10-28 UTC。目录：`artifacts/a-stack-bowls-p02152-02/`。启动主机为 `cnwlb-a100-p02152`；本次检查主机为 `cnwlb-a100-p02080`，仅能核验共享产物，不能以本机进程表推断原主机进程已退出。

本轮未完成原生评测。`sim/summary.json` 与 `sim/evaluation_outcome.json` 记录 330/800 控制步、`server_close`、`complete=false`、`valid_for_success_rate=false`；原生 success/score 均为 null，不填零。顶层 `summary.json` 与 `controller/result.json` 缺失。仿真日志在 2026-10-27 17:59:47 UTC 显示 Simulation App Shutting Down，未发现可据此确认的关闭原因。

控制器最后确认动作是 `response_109.json` / `execution_109.npz`，对应 327→330 步；`progress.json` 同样为 330 步。随后一直读取观测 110 和图片，日志与 token usage 更新到 19:29，未产生下一条动作回执。最后累计 22,755,624 token（输入 22,322,282，输出 433,342）。日志中的模型自述不能证明任务成功，也不能证明历史压缩已正确完成，后者仍待验收。

视频 `sim/sensors.mp4` 经 ffprobe 完整计帧可读取，1920×360，共 331 帧，与初始帧加 330 控制步一致。模型图像读取事件与工具输入拒绝均有保留；拒绝不作为物理执行计数。

本次发现 launcher 在关闭墙钟上限时仅阻塞等待控制器，仿真退出后仍可能持续推理。现已改为同时监测 simulator 与 model bridge：任一必需进程退出即报基础设施错误并清理所属子进程；保留原生 800 步和关闭额外预算的协议。该修复不能追溯补写旧运行总汇总，也不解释原仿真为何关闭。
