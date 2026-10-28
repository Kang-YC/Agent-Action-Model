# Eval Atlas · 实时评测记录页

页面直接读取本机实验产物，支持 A/B 线以及后续登记的运行，不调用模型或机器人 RPC，不干预现有实验。

当前内网地址：**http://10.1.60.249:19340/**（主机 `cnwlb-a100-p02080`）。需要客户端能访问这台实验机的内网；未将产物上传到公共网站。云端 Sites 无法直接读取训练机目录，因此本轮采用训练机上的实时 HTTP 服务。

## 使用

- 总览每 15 秒自动读取进度、预算、tokens、原生成绩和最新观测；支持路线、状态和关键词筛选。
- 点击运行进入详情：查看相机图像、实验录像、机器人动作与输入拒绝；Agent 活动单列展示消息、命令和图像查看。
- 每个机器人工具调用都有 `#run=…&call=…` 独立链接，可展开原始参数；录像可播放时，点击“回放”按控制步 × control_dt 跳转。视频保持单实例，刷新数据不重置正在播放的录像。
- 运行中 MP4 常尚未封装完成。接口使用 ffprobe 判断可播放性；未通过时显示“仍在写入”，不生成失效播放链接。最新相机观测仍可查看。
- 备注保存到服务器的 `artifacts/evaluation-dashboard/notes.json`，不是浏览器临时存储。运行元数据登记在同目录的 registry.json。
- artifacts 顶层包含 controller/ 和 sim/ 的运行会自动发现；a-published-runs/ 和 b-published-runs/ 下的案例同样自动发现。其他嵌套目录可以在“登记评测”中填写 artifacts 下相对路径。
- 可导出当前筛选后的记录或包含工具轨迹的单次运行 JSON。页面只读已有评测，新增登记不会启动评测。

原生成绩只在 complete 与 valid_for_success_rate 均为 true 时展示；不完整结果保持缺失，不补零。开发预算、启动快照预算与原生 horizon 分别记录。当前第四轮的有效预算来自外部 400 步守护，原始启动快照仍为 800。界面的连续闭环信息是轨迹证据，不替代完整终止、视频和成本的最终验收。Agent 自述不视为成功证明。

## 启动与代码

```bash
bash scripts/serve_evaluations.sh --host 0.0.0.0 --port 19340
```

默认不传 host 时只监听 127.0.0.1。可通过 --artifacts 指定另一份实验目录。当前后台进程的 PID、主机和端口记录在 artifacts/evaluation-dashboard/launch.json，日志为同目录 server.log；主机或进程重启后需重新启动服务。

- agent_action/evaluation_web.py：发现运行、读取 A/B 产物、持久化备注、提供媒体 Range 请求。
- evaluation_web/：无构建依赖的 HTML/CSS/JS，前端通过同源 API 自动刷新。
- tests/test_evaluation_web.py：真实 HTTP 测试覆盖缺失分数、工具执行、视频分段/尾部 Range/416、目录和符号链接越界、备注持久化、跨源写入拒绝与嵌套目录登记。

媒体路由只允许已发现运行中的 PNG/JPEG/MP4，不提供任意工作区文件、模型请求原始 gzip、API 凭据或 checkpoint 文件下载。命令与工具参数来自既有 Agent 记录，按文本转义显示。

## 本次验证

四项 HTTP/数据测试通过，前端 node --check 与 Python 编译检查通过。服务已在内网地址响应，5 条真实记录均成功读取，所有详情接口返回；真实 MP4 返回有效 206 Content-Range，可用于拖动播放。验证时第四轮仍为 running、预算400，未封装的视频标 writing，已结束实验的录像标 ready。

当前环境没有可用的浏览器预览/自动化工具，因此未执行浏览器截图或视觉验收；已完成服务器、API、媒体流与 JavaScript 语法检查。
