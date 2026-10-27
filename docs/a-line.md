# A 线：Codex Direct

本会话只推进指定 base＋Codex Direct；B 线由独立工作维护。

本会话 A 线指“指定 base＋Codex Direct”。当前先跑 `stack_bowls` 开发 episode，入口为：

```bash
bash scripts/run_a_stack_bowls.sh --output artifacts/a-stack-bowls-new
```

预算固定在 `configs/a_stack_bowls_development.json`：原生 800 控制步、最多 800 次有效决策、4000 万累计 token、4 小时墙钟。实际预算和命令另存到 `<run>.plan.json`，执行中不调整；预算结束与原生任务完成分别报告。当前运行目录为 `artifacts/a-stack-bowls-01/`。

这些额外预算是本次开发保护设置。参考正式 panel 关闭额外决策次数、token 和墙钟上限，只使用原生控制步数约束；详见 [参考评测限制](reference-evaluation-limits.md)。后续正式对照须单独登记任何预算差异。

叠碗是独立开发任务。后续网页对照清单为 `configs/a_published_ten_task_panel.json`，逐例复用网页原 Direct 的十任务、每任务五案例（含原 standard/random 配比），共 50 案例。所有布局及原生支持轨迹的哈希与历史冻结清单一致；169 个历史原生源码文件中 165 个一致，4 处差异已保存到 `artifacts/a-published-comparison-audit/`，主要涉及图像同步和日志路径，另一个任务文件不属于这十任务。十任务评分代码保持相同；模型、上下文和适配器差异仍需在结果中单列。清单已准备，尚未批量运行。

## 运行跟进（2026-10-27）

工作区位于 NFS，共享文件更新与本机进程可见性应分别核查。11:04 UTC 检查时，`a-stack-bowls-01` 的 controller 日志及 token 计数仍在更新，本机却看不到原 launcher / simulator；因此不能根据本机 PID 缺失判定该运行中断，也不启动重复 episode。最近已确认执行到 147/800 控制步，累计 token 约 591 万；尚无最终 summary，未完成验收。

当前可见主机为 `cnwlb-a100-p02152`。本机正在按固定配置加载 base；本机模型就绪不代表旧运行已迁移到本机。旧运行继续保留原预算、目录与模型接入。验收时另行检查日志中的过期 observation 路径拒绝及历史压缩，区分被拒绝的调用与实际执行动作，不将模型自述当作执行证据。

## 下一步验收

叠碗运行结束后，检查原生终止或预算终止、轨迹与视频、模型输入和工具回执、历史压缩、失败分类和成本，再记录开发报告。网页 50 案例在开发链路稳定、预算明确后按冻结清单推进；旧记录缺失的原生分数保持缺失，不填零。每个完成的子任务先检查、再单独 commit，运行中的实验不标成完成。

服务入口见 [固定模型推理服务](model-service.md)，基础闭环证据见 [本地 base 推理链路](base-inference.md)。
