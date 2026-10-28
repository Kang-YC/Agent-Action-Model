# B03 完成后的两个论文任务

用户明确要求：本次叠碗结束后，再执行两个网页／论文任务，步数采用官方原生上限。这里执行每个任务的一个固定案例，不当作论文每任务五案例的完整复现，也不据此计算正式成功率。

## 已准备的顺序

| 顺序 | 任务 | 固定案例 | 原生控制上限 | 对应仿真时间 |
|---|---|---|---:|---:|
| 1 | 按语言分类 classify_objects_by_language | standard，eval_seed=0，layout_id=0 | 1100 | 44 秒 |
| 2 | 物品装箱 pack_objects_into_box | standard，eval_seed=0，layout_id=0 | 1300 | 52 秒 |

任务来自[论文 RoboDojo 十任务](https://arxiv.org/html/2609.38537#B1)，预算来自配套[公开逐案例记录](https://github.com/anonymous-report-421/GPT-as-Policy/blob/8f3d362b077d8efb77e2a7274d5b2c20e2243846/public_results/evaluation_cases.json)。25Hz，仿真在模型推理期间暂停；实际墙钟远长于表中时间。原生成功可以提前结束，达到 horizon 未成功则按原生结果记失败；不改为 400 步开发预算。额外模型轮次、累计 token 和 episode 墙钟上限为 0，仍保留单请求／基础设施超时与固定模型 32K 上限。

两任务复用当前 B harness、指定 base 模型、静态标定／14 维状态、澄清后的边界说明，历史仍为最新三图＋最近八轮完整文本＋持久 Python。没有加入更长图像历史。参数选择和任务顺序在看到新任务结果之前确定，开发排除清单已检查，这两个案例均不属于此前分类布局 0 的调试记录。

## 启动入口和原生身份绑定

新增 `agent_action/b_case.py`：从公开 50 案例清单取得该 case 的 horizon 与布局，再与 `configs/a_native_panel60_v1.json` 中同 case_id 的原生身份交叉检查。60 案例文件只用于原生绑定，不改变所选公开案例或将其当作论文 60 案例结果。

准备器核对原生源码 commit／文件哈希、布局顺序、布局／支持资产 SHA256；保存全新的 `.plan.json`、`.case.json` 和 `.native-panel.json`。原生 simulator 通过 `--eval-manifest`、`--case-file`、`--eval-seed` 和 manifest hash 绑定案例，controller 通过 reset seed 绑定同一 layout。正式启动前再次核对身份、命令和预算，拒绝不一致或已有输出目录。历史成功／评分不放入控制器提示词。

CLI 示例只准备，不启动：

```bash
python3 -m agent_action.b_case \
  --case-id classify_objects_by_language__standard__g0__l0 \
  --robodojo /dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo \
  --output artifacts/b-language-fresh \
  --prepare-only
```

这一补充解决了候选准备文档中“B 缺少 native case binding”的启动缺口；原先 49 案例提案仍保持草案，不自动变为已批准的完整评测。

## 已启动的等待队列

配置为 `configs/b_followup_two_tasks.json`，实际不可变计划、源码快照和状态位于 `artifacts/b-followup-two-01/`：

- `sequence.json`：前置运行、两项 plan 路径／哈希、固定源码哈希与仿真 GPU。
- `state.json`：实时 waiting／running_case／complete／halted／error 状态，各任务进度和最终 summary。
- `launch.json`、`watch.log`：本机 worker PID、启动命令、时间与异常。
- `source/`：该队列使用的 B controller／启动器、原生适配器与标定推导器等代码快照。

前置运行明确为 `artifacts/b-stack-bowls-p02080-03`。等待进程已启动，等待期间不发模型请求、不启动额外仿真、不停止 A／B 或模型服务。只有前置 supervisor 确认结束且有完整、有效的原生结果才继续；原生成功和有效原生失败均可继续。若前置运行是基础设施异常、提前停止或缺少最终结果，队列记 halted 并保留原因，不将异常伪装成完成。

之后单 GPU 顺序运行两个案例，每次只做一次：

1. 验证冻结源码、plan、原生身份和指定模型服务；等待 GPU 1 空闲显存至少 7500 MiB，最长等资源六小时，不抢停其他任务。
2. 用全新输出目录启动，同一时刻仅一个 follow-up controller／simulator；wrapper 继续监测 backend 退出。
3. 保存原生结果、轨迹、实际模型请求、观测和视频；只接受对应 case 的完整有效原生 outcome。有效原生失败会保留并进入下一任务；基础设施／上下文异常、无效布局、提前停止或身份不符会停住队列，不自动重跑或换案例。
4. 两项均有有效终局时记 complete；结果不挑最好值。

本次两个输出目录分别预定为 `artifacts/b-published-language-p02080-01` 和 `artifacts/b-published-pack-p02080-01`；当前仅相邻计划文件已生成，任务目录将在真正启动时创建。新增回归覆盖预算与 argv 一致、native case 身份不能篡改、准备阶段不启动、重复目录拒绝以及原生失败／基础设施异常的队列区别。全仓 97 项检查通过。
