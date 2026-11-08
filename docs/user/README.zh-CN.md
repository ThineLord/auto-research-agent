# 用户 README

[English](README.md) · [简体中文](README.zh-CN.md) · [项目首页](../../README.zh-CN.md)

Auto Research Agent 帮助你迭代研究任务、检查保存的过程和成果。程序负责起草、审查、修改和评分；来源、方法和结论仍需由你判断。

## 安装与打开

需要 Python 3.10+、Git 和 Make。首次克隆后，在仓库根目录执行：

```bash
cp config.example.yaml config.yaml
make install
make ui
```

打开[本地工作台](http://127.0.0.1:8501/)。再次使用时复用已有 `config.yaml` 和 `.venv`。端口被占用时，可用 `scripts/start_ui.sh --port 8502`。在服务所在终端按 Ctrl+C 关闭。

| 页面 | 用途 |
| --- | --- |
| 工作台 | 编辑任务和研究记忆、控制运行、查看进度 |
| 研究成果 | 阅读保存的 Markdown、JSON 和日志 |
| 运行分析 | 查看评分、耗时、元数据与运行对比 |
| 设置 | 配置模型与外观，访问工作区工具 |

语言和外观偏好保存在浏览器。打开页面不会自动开始研究；正常运行前会保存编辑后的输入。

## 不调用模型的演示

`make mock` 生成确定性演示产物，无需 Ollama、Gemini 或 API key。它会更新所选项目的运行状态。为保留已有研究，使用独立项目：

```bash
mkdir projects/demo
cp projects/example/task.md projects/demo/task.md
make mock ARGS="--project demo --max-rounds 1"
```

如果 `demo` 已存在，改用新目录名，不要覆盖原文件。在工作台选择该项目查看成果。Mock 结果仅用于检查程序，不是研究发现。

## 运行自己的任务

1. 新建 `projects/<name>/task.md`，或选择已有项目。私人研究使用独立目录，保留公开示例。
2. 在本地 `config.yaml` 中设置 `project_name` 和 `topic`，或在工作台选择项目。
3. 选择实际可用的模型。Ollama 需要服务运行且已安装模型；Gemini 需要有效密钥，并可能产生服务费用。程序的免费运行策略不等于计费保证。
4. 准备好实际调用模型后，先运行诊断，再开始有界运行。检查成果后，决定恢复旧运行还是新建运行。

| 命令 | 作用 |
| --- | --- |
| `make ui` | 打开本地工作台 |
| `make mock` | 保存确定性演示产物，不调用模型 |
| `make diagnostic` | 调用真实模型完成一轮诊断 |
| `make run` | 新建有界研究运行 |
| `make resume` | 从所选项目的有效检查点继续 |
| `make survey` | 确定性整理已保存的本地资料，不调用模型 |

`make bootstrap` 会安装依赖、检查 Ollama 并调用真实模型诊断。如果只想打开页面，使用上面的安装步骤即可。

## 保存与隐私

任务、记忆、检查点和运行记录位于所选 `projects/<name>/`。运行目录保留中间文本、元数据和指标。恢复会保留原历史，并拒绝不安全或不一致的状态；新建运行生成独立记录。不要通过移动或手改活动运行目录来绕过恢复错误。

本地配置和研究产物默认被 Git 忽略，但忽略规则不等于加密或访问控制。Gemini 会接收提供给它的任务和上下文。密钥只放在本地环境或配置中，不要提交。备份前停止运行，私下保存整个项目目录和本地配置；若配置了外部运行存储，也要一起备份。

## 按版本升级

从 [GitHub Releases](https://github.com/ThineLord/auto-research-agent/releases) 选择版本并先阅读说明。切换版本标签前停止活动运行、备份私人数据并保持工作区干净。升级后重新执行 `make install`，不要为了升级丢弃本地修改或覆盖配置。

**0.2.0** 保持原有运行路径和产物结构。高级命令与边界见[版本说明](../releases/0.2.0.zh-CN.md)和[文档导航](../README.md)。网页工作台需要源码仓库；wheel 安装提供命令行程序。
