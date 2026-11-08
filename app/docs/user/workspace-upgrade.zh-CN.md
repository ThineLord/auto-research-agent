# 工作区安全升级与回滚（0.3.0）

[English](workspace-upgrade.md) · [简体中文](workspace-upgrade.zh-CN.md)

## 升级前

先用旧版停止研究和网页服务，完整备份私人工作区（包括 `config.yaml`、`projects/`、新研究目录及另行配置的外部运行存储），并确认备份可读。不要替换正在运行的程序文件。本版本不会自动移动、改写或删除旧研究。

干净的源码仓库可获取新版本、检查 `git status`，切换到 `v0.3.0` 后运行 `./start`。如果 Git 提示会覆盖本地已跟踪文件的修改，请保留修改，不要用强制切换、`reset --hard` 或 `clean` 解决。不确定时先在独立目录检出新版本，保留原工作区不动。需要 Python 3.10+；新版环境位于 `app/.venv/`，旧 `.venv/` 可保留用于回滚。

## 旧研究原位兼容

网页和 CLI 均可读取原来的 `projects/<name>/`，包括 Task、Memory、Runs、Scores、Checkpoints。扫描只读。同名时优先旧 `projects/` 项目（包括 `example`）；实际路径可在工作台「设置 → 高级」中查看。旧项目无效时明确报错，不会静默换成同名新目录。新建时两处任一位置已有同名文件或目录都拒绝覆盖。

本次**不提供研究目录搬迁命令，也不需要迁移才能使用新版**。不要拖动已有运行目录：检查点和恢复日志可能绑定绝对路径及文件身份。将来需要搬迁时，必须先验证备份、检查冲突并明确确认；简单复制不能视作已验证的迁移。现有 legacy-history 修复命令与搬迁不同，继续要求原有明确批准和证据。

## 新用户与 CLI

运行 `./start`，在浏览器打开输出的本地网址，点击研究选择器旁的 **+**。输入非隐藏文件夹名和任务，新建 `<工作区>/<名称>/task.md` 与 `memory.md`，不会覆盖原文件夹。上次选择保存在被忽略的 `.ara-workspace.json` 中，各项目数据单独保存。切换不会重启服务，也不会移动或停止正在运行的项目；切回原项目即可安全停止或恢复。

```bash
make install-dev
app/.venv/bin/auto-research-agent --create-project topic-a --task "描述研究实验"
app/.venv/bin/auto-research-agent --project topic-a --mock --max-rounds 1
make check
make browser-test
```

CLI 与网页服务均支持 `--workspace /工作区路径`。源码安装默认使用 `app/` 的父目录，wheel CLI 默认使用当前目录。全新 wheel 工作区的 `--mock` 可安全创建缺失的 `example/`；源码工作台首次启动只创建缺失的配置／示例。真实运行仍需配置原有模型来源。wheel 不包含网页工作台，统一网页入口请使用源码 `./start`。内部 Streamlit 仍可通过 `cd app && .venv/bin/python -m streamlit run ui/app.py` 运行，主入口为 `./start`。

## 回滚

先停止全部运行和服务，备份当前数据，再从干净工作区切回旧标签并恢复匹配的环境。未搬动的 `projects/<name>/` 保持原路径和产物格式。**0.2.x 无法发现新建的同级研究目录**：请原样保留，回到 0.3.0 再使用，不要搬进 `projects/` 或手改检查点强行兼容。如果升级后的产物无法由旧程序恢复，应在检查冲突、明确选择恢复内容后，将已验证的升级前备份恢复到原工作区路径。本程序不自动回滚研究数据。

根目录 Git 规则仅允许应用与公开文件；私人研究、配置和选择状态默认忽略。wheel 构建仅使用应用白名单及内置模板，不读取可修改的工作区示例或私人研究。忽略规则不是加密，私人备份仍需妥善保管。
