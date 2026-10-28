# B 线后续评测候选清单

本项在叠碗开发 episode 运行期间离线准备，不发模型请求、不连接机器人 RPC、不启动仿真。候选清单尚未冻结，不改变当前运行的预算、上下文或提示词。

## 候选范围

复用 A 线已保存的 `configs/a_published_ten_task_panel.json` 作为案例身份／布局／预算来源，逐案验证该文件的 panel hash，并重新核验全部布局及原生支持轨迹 SHA256。输出剔除 prior_direct、历史成功和评分字段，避免把历史标签传入后续控制器计划。

本次真实核验覆盖 50 案例、59 个唯一布局／支持资产，全部匹配源清单。根据 `configs/b_development_exclusions.json`，分类任务 `classify_objects` 的 eval seed 0、layout ID 0 已用于 B 线 smoke 和历史窗口开发，应从后续未调试候选中排除。叠碗 eval seed／layout 0 同样登记为开发案例，但不属于公开十任务清单，因此不会额外减少案例数。

结果为 **49 个候选＋1 个开发排除案例**。这只是排除已知 B 线调试布局，不保证对模型训练、公开历史或其他会话也属于 held-out 数据。若后续 A/B 正式配对采用这 49 案例，两线必须采用相同子集；不能把 B 的 49 案例均值直接与 A／网页的 50 案例均值比较。原始 50 案例和排除记录均保留，不改写 A 线清单。

## 目前可检查的结果

准备入口为 `agent_action/b_panel.py`。每个候选包含：原 case_id、task 和 runtime_task（保留 random variant）、eval seed／layout ID、该任务原生 horizon、布局及支持资产哈希、控制器参数建议，以及启动时应绑定的原生身份。模型轮次、累计 token 和 episode 墙钟保护上限保持 0；历史窗口取自当前 B 开发运行实际 manifest 中的 8 轮设置，记录 manifest 和模型配置哈希。

输出为 `draft_not_frozen`，每案 executable_command 为 null，launchable_cases 为 0。它是可复核的参数计划，不是原生 eval manifest，也不是可直接执行的正式评测命令。proposal_sha256 标识该次草案快照，不能冒充已冻结协议或模型权重内容哈希。生成时只读输入，输出路径必须在开发运行之外，且不能覆盖已有提案。

```bash
python3 -m agent_action.b_panel \
  --robodojo /dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo \
  --development-run artifacts/b-stack-bowls-p02080-01 \
  --output artifacts/b-panel-candidate-new/proposal.json
```

本次产物为 `artifacts/b-panel-candidate-02/proposal.json`。运行此命令只准备草案，不申请或占用 GPU。

## 正式开跑前的缺口

1. 当前叠碗开发运行结束后，验收原生终局／异常、视频、目标拒绝率和 token／耗时，再判断当前 B harness 是否适合正式评测。
2. 分别冻结 B 的提示词、静态信息、8 轮历史策略和执行源码；显式记录与 A 的差异。若调整反馈或信息条件，应另开开发配置验证。
3. B 启动器目前只显式传 task 和布局 seed，尚未连通原生 `--eval-manifest`／`--case-file` 的身份绑定与启动校验。必须实现并验证 case_id、runtime_task、eval_seed、layout_id 与布局哈希一致，不能用当前开发入口冒充完整的冻结评测入口。
4. 冻结原生 evaluator／adapter 源码和运行时版本。B 当前 controller/source 快照覆盖 agent_action 与 mini-swe，不能声称它也完整覆盖相邻原生参考仓库和 RoboDojo。
5. 每次启动前重新核对布局／支持轨迹哈希，分配全新的 attempt 目录，保留中断和失败，不做 best-of 选择或自动挑重跑结果。
6. 审核开发排除记录和 A/B 共同案例分母，然后才冻结正式案例清单、生成可执行评测命令。

这些缺口保存在机器提案的 activation_gates 中。开发 summary 是否存在、状态是什么也会如实记录，但即使出现成功 summary，准备器仍不会自动解锁或启动评测。

后续更新：用户已授权 B03 完成后先做两个论文任务。[两任务队列](b-followup-two.md)已实现并验证 native manifest/case-file 绑定，只准备并排队这两个明确案例；本页原 49 案例提案仍不是已启动的完整评测。
