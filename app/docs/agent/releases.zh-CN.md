# 版本与发布规则

[English](releases.md) · [简体中文](releases.zh-CN.md)

`app/pyproject.toml` 是应用版本的唯一来源。从 **0.2.0** 开始，每次正式更新统一包版本、两个首页 README、`app/CHANGELOG.md`、中英文版本说明、`v主版本.次版本.修订版本` Git 标签和 GitHub Release。开发提交合并不等于正式发布。

## 选择版本号

- **修订版本：**兼容性修复、文档更正和维护更新。
- **次版本：**兼容的新能力或重要版本基线，例如 0.2.0 汇总的工作台与仓库整理。
- **主版本：**1.0 之后的不兼容变更。1.0 之前，不兼容变更使用新次版本，并显著说明影响与迁移步骤。

不得复用或移动已发布标签。保留历史 `v0.1.0-stable`、`v0.1.1-hardening`；当时包版本仍是 0.1.0。0.2.0 统一今后的命名，不改写历史。产物结构和检查点具有独立兼容约束，应用版本升级不自动授权数据迁移。

## 准备发布 PR

1. 从最新 `origin/master` 建立分支，检查未发布改动、已有标签和 Release。
2. 更新 `app/pyproject.toml`、两个首页 README、相关中英文指南、`app/CHANGELOG.md`，以及 `app/docs/releases/<版本>.md` 和 `<版本>.zh-CN.md`，保留 `Unreleased` 区域记录后续工作。
3. 说明变更、升级步骤、数据兼容性、验证和限制，不虚构模型验证结果。
4. 执行 `make check` 和隔离 wheel 检查。`make release-check` 检查本地版本标记、中英文说明、变更条目及历史归档外 Markdown 的相对文件链接；它不证明远端标签、CI 或 GitHub 审批已完成。
5. 建立 draft PR，完成独立 subagent review 和最终提交的 CI，再由已获授权的 merge subagent 合并准确的已审查提交。

## 发布合并后的版本

合并提交的 CI 成功后，获取 `origin`，确认目标提交位于 `master`，且该版本标签和 Release 尚不存在。下列占位符需替换为真实版本和已审查的合并提交：

```bash
git tag -a v<VERSION> <MERGE_SHA> -m "Auto Research Agent <VERSION>"
git push origin refs/tags/v<VERSION>
gh release create v<VERSION> --verify-tag --title "Auto Research Agent <VERSION>" --notes-file <RELEASE_BODY_FILE> --latest
```

发布前在该提交执行 `app/.venv/bin/python app/scripts/check_release.py --tag v<VERSION>`。从已提交的中英文说明准备发布正文，使用绝对 GitHub 链接，因为 Release 正文的相对链接不会按仓库文件链接解析。说明验证结果与所测 SHA。源码发布使用 GitHub 自动生成的源码归档即可；不要上传包含忽略文件的本地目录压缩包。PyPI 发布属于单独操作，不在此流程内。

发布后读取 Release、标签目标和版本进行核对。如果打标签后发布失败，先核查已有标签再重试，不要强制改写。已发布版本的问题通过新的修订版本修复。保留无关分支和本地研究数据。
