# Auto Research Agent

[English](README.md) · [简体中文](README.zh-CN.md)

**一个以本地工作区为中心的研究助手：把研究任务变成可检查、可修改、可比较的草稿。**

项目使用本地 Ollama 或 Google Gemini 执行 **起草 → 审查 → 修改 → 评分**，通过本地网页集中查看任务、进度、已保存成果和运行对比。模型评分帮助迭代，不代表研究结论已经得到验证。

**用户入口：**阅读[用户 README](docs/user/README.zh-CN.md)。

**Agent 入口：**先读 [AGENTS.md](AGENTS.md)，再读 [Agent README](docs/agent/README.zh-CN.md)。

## 三步使用

1. **写下任务。**使用公开示例，或在 `projects/` 下建立独立研究项目。
2. **运行并检查。**打开工作台，选择模型来源和模型，查看每一轮保存的结果。
3. **带着上下文继续。**恢复有效检查点、浏览成果、比较运行记录，再决定下一步。

## 本地启动

需要 Python **3.10+**、Git 和 Make。首次克隆后执行：

```bash
git clone https://github.com/ThineLord/auto-research-agent.git
cd auto-research-agent
cp config.example.yaml config.yaml
make install
make ui
```

打开 **[http://127.0.0.1:8501/](http://127.0.0.1:8501/)**，使用期间保持服务运行。已有项目请复用原有配置和环境。打开工作台不会自动开始研究；真实运行需要配置模型来源，`make mock` 可在不调用模型的情况下演示成果保存。运行实际任务前请阅读[用户指南](docs/user/README.zh-CN.md)。

## 文件位置

```text
auto-research-agent/
├── src/                 研究流程与命令行程序
├── ui/                  本地网页工作台
├── prompts/             起草、审查、修改、评分提示词
├── projects/            公开示例与 Git 忽略的本地研究项目
├── docs/                用户、Agent、版本、参考和设计文档
├── scripts/             安装、验证与性能工具
├── tests/               自动检查
├── AGENTS.md            Agent 入口和维护规则
└── CHANGELOG.md         按版本记录的变更
```

本地配置、密钥、运行产物和私人项目默认不进入 Git。成果保存在本机；选择 Gemini 时，模型输入会发送给云端服务。

## 版本与文档

当前版本：**0.2.0**。发布使用 `v主版本.次版本.修订版本` 标签，与 `pyproject.toml` 保持一致，历史里程碑标签保留。应用版本与研究产物的数据兼容边界分别管理。

- [版本发布](https://github.com/ThineLord/auto-research-agent/releases) · [0.2.0 更新说明](docs/releases/0.2.0.zh-CN.md) · [变更记录](CHANGELOG.md)
- [用户 README](docs/user/README.zh-CN.md) · [Agent README](docs/agent/README.zh-CN.md)
- [文档导航](docs/README.md) · [版本与发布规则](docs/agent/releases.zh-CN.md)

网页工作台通过源码仓库运行；可安装的 Python 包提供命令行程序和内置入门资源。
