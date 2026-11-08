# Agent README

[English](README.md) · [简体中文](README.zh-CN.md) · [仓库规则](../../AGENTS.md)

Codex 负责实现、组织和仓库管理。Subagents 负责独立 review 和已获授权的合并。不调用外部 bots 或 bot bridge。

## 读取上下文与确定范围

1. 阅读 `AGENTS.md`、当前用户要求和 `git status --short --branch`。
2. 获取最新 `origin`，确认默认分支 `master`，建立分支前检查本地改动，保留未提交文件和被忽略的研究数据。
3. 阅读[用户 README](../user/README.zh-CN.md)、[开发参考](../reference/development.md)和相关源码。`.codex/` 仅提供历史上下文，旧任务队列不代表新的执行要求。
4. 建立 `codex/` 分支，围绕用户要求完成实现。

## 文件归属

| 位置 | 内容 |
| --- | --- |
| `src/`、`ui/`、`prompts/` | 程序、工作台、正式提示词 |
| `src/_bundled/` | wheel 的明确资源清单，与正式资源同步 |
| `projects/example/` | 可公开的入门输入 |
| 其他 `projects/` 目录 | Git 忽略的私人研究，原地保留 |
| `docs/user/`、`docs/agent/` | 当前中英文使用与维护文档 |
| `docs/reference/`、`docs/design/` | 命令、架构和设计细节 |
| `docs/releases/` | 各版本中英文发布说明 |
| `docs/archive/`、`.codex/` | 历史证据，不代表当前版本验收 |
| `output/`、`outputs/`、本地配置 | 被忽略的本地数据，不作为发布附件 |

## 实现与验证

除非任务明确要求，否则保留运行路径、模型调用行为、产物结构和恢复约束。用户可见的改动同步更新中英文入口。开发中使用最小有效检查，合并前完成仓库检查：

```bash
make install-dev
make check
.venv/bin/python scripts/check_wheel_install.py
```

`make check` 包含格式、静态检查、导入、仓库安全、版本与文档检查及测试。打包或版本改动必须验证隔离 wheel 安装，CI 也会运行该检查。这些检查不调用模型。不要为了文档验收执行 `make bootstrap`、`make diagnostic` 或真实研究。

## Review 与合并

建立 draft PR，说明最终行为、版本边界和实际验证。向 review subagent 提供 base/head SHA 和 diff，修复问题后重新审查受影响部分，审查结论对应最终提交。

合并已获授权时，由独立 merge subagent 检查 PR、准确的已审查提交、可合并状态、问题解决情况和 CI 成功结果。随后将 PR 标为 ready，并限定在已审查 SHA 上合并。遵守分支保护；同账户的 subagent 分析不等于其他账户的 GitHub APPROVED 审查。合并 agent 返回真实结果和 merge SHA。

## 发布与交接

遵循[版本规则](releases.zh-CN.md)（[English](releases.md)）。合并提交的 CI 通过后再打标签、发布。不要上传私人研究、移动已有标签，或把合并成功等同于发布成功。交接提供 PR、版本、发布链接、检查结果和未解决限制；达到用户要求后结束。
