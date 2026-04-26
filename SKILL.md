---
name: gitcode-release-note-generator
description: 基于 GitCode 仓库真实数据生成高质量 Release Note。优先使用 curl 拉取 roadmap、PR、Issue、release/tag 和仓库文档原始信息，再由 Agent 结合上下文总结输出正式风格的 Markdown 发布说明，而不是直接依赖脚本模板填空。适用于需要基于真实 GitCode 仓库数据生成版本发布说明的场景。
---

# GitCode Release Note Generator

基于 GitCode 仓库原始数据生成正式风格的 release note。默认工作流是“`curl` 抓取上下文 + Agent 总结成文”，而不是直接调用 Python 脚本输出成品。

## 使用流程

### 1. 收集必要信息

向用户确认以下输入：

| 参数 | 必须 | 说明 |
| ---- | ---- | ---- |
| 输出文件名 | 是 | 如 `Product-26.0.0-release-note.md` |
| 仓库链接 | 是 | 如 `https://gitcode.com/owner/repo` |
| roadmap 链接 | 是 | Roadmap issue 链接 |
| 版本时间范围 | 是 | 如 `2026Q1` |
| GitCode Token | 否 | 未显式提供时尝试读取 `GITCODE_TOKEN` |
| 版本号 | 否 | 建议显式提供，避免只从文件名推断 |
| Release 链接 | 否 | 如有现成 release 页面可一并提供 |

**时间范围格式支持：**
- `YYYYQ[1-4]`: 季度格式，如 `2026Q1`
- `YYYY-MM`: 月份格式，如 `2026-01`
- `YYYY-MM-DD:YYYY-MM-DD`: 日期范围，如 `2026-01-01:2026-03-31`

### 2. 抓取原始上下文

```bash
./scripts/fetch_release_context.sh \
  --repo <仓库链接> \
  --roadmap <roadmap链接> \
  --time-range <时间范围> \
  --output-dir .release-context/<版本目录> \
  --token <GitCode API Token>
```

兼容性说明：

- 脚本使用 `#!/usr/bin/env bash`
- 已避免依赖 `mapfile`、GNU `date` 等兼容性较差的能力
- 在 macOS 自带 Bash 3.2 环境中也应可运行
- 如果用户手动以 `zsh scripts/fetch_release_context.sh` 方式执行，建议改为 `bash scripts/fetch_release_context.sh` 或直接 `./scripts/fetch_release_context.sh`

抓取结果会落在指定目录下，包含：

- `raw/issues.json`
- `raw/pulls.json`
- `raw/roadmap.json`
- `raw/repo.json`
- `raw/releases.json`
- `raw/tags.json`
- `raw/issue-numbers.txt`
- `raw/pr-numbers.txt`
- `raw/issue-details/issue-<number>.json`
- `raw/pr-details/pr-<number>.json`
- `raw/issue-details/index.txt`
- `raw/pr-details/index.txt`
- `raw/detail-index.txt`
- `docs/README.md`
- `docs/install.md`
- `docs/quick_start.md`
- `docs/msprof_parsing_instruct.md`
- `docs/msmonitor_parsing_instruct.md`
- `context-meta.txt`

### 3. 由 Agent 总结生成 Markdown

拿到原始数据后，Agent 应直接基于这些材料总结输出 release note Markdown 文件。重点不是逐条转抄 PR，而是聚合成正式发布说明的主题条目，例如：

- 版本概述要体现产品定位、适用场景、版本标签、发布时间和 3-5 条核心亮点
- 新增特性要合并同主题的多条 PR，写成用户视角的能力摘要
- 变更说明要体现兼容性影响，必要时显式标注“不兼容变更”
- 修复缺陷要概括问题现象和修复效果，并标出影响范围
- 致谢要挑选真正代表性贡献，而不是简单按 PR 时间罗列

Agent 在执行这一步时，应优先阅读：

- `.release-context/<version>/raw/detail-index.txt`
- `assets/MindStudio-Profiler-26.0.0-release-note.md`
- `assets/release-note-agent-prompt.md`
- `assets/release-note-template.md`

其中：

- `detail-index.txt` 用来快速定位聚合 JSON、编号清单和拆分后的 issue/PR 详情文件
- `MindStudio-Profiler-26.0.0-release-note.md` 是成品风格参考
- `release-note-agent-prompt.md` 是建议 Agent 采用的总结提示模板
- `release-note-template.md` 是章节结构约束

如果 `curl` 获取的信息不足以支撑正式摘要，不应停留在原始 PR/Issue 文案层，而应继续结合代码理解补充：

- 优先读仓库 README、安装文档、解析说明
- 如果仓库就在当前工作区，直接搜索相关模块、接口、测试和注释
- 根据代码行为总结“新增了什么能力 / 修复了什么问题 / 对用户有什么影响”
- 只有在代码和文档都无法支撑时，才保守表述为“仓库未单独声明”

### 4. 人工审查与补充

Agent 生成的是**可交付初稿**。当前版本的推荐工作流会额外帮助：

- 从 roadmap、README、安装文档中提取版本亮点与产品定位
- 自动整理配套关系中的常见字段，如操作系统、CANN、Python、PyTorch、三方依赖
- 对同主题的多条 PR/Issue 做聚合归并，输出接近正式版本公告的条目级摘要
- 结合 release/tag 信息补充发布日期与版本标签

仍建议人工重点复核以下内容：

- **版本概述**: 检查场景定位与版本亮点是否贴合产品口径
- **配套关系**: 检查仓库未声明或抽取不完整的软硬件版本要求
- **特性描述**: 检查自动生成的描述是否足够准确、是否需要更产品化表达
- **变更影响**: 检查是否存在需要显式标注的兼容性影响
- **影响范围**: 检查缺陷修复的适用范围是否足够准确
- **已知问题**: 检查是否有遗漏的已知问题
- **分类调整**: 检查PR/Issue是否被正确分类到特性/变更/缺陷

## 输出要求

生成结果应尽量对齐正式版本公告风格，而不是“原始 issue/PR 列表 + 模板字段拼接”。尤其要避免：

- 把 issue/PR 模板文案直接写进正文
- 用“修改原因：”“需求背景：”这类字段名充当发布说明
- 把同一主题的多条 PR 拆成多行重复描述
- 把文档整改、CI、模板修正等噪音项塞进“核心亮点”

## 输出模板

生成的release note严格遵循 `assets/release-note-template.md` 的结构，包含：

1. 版本概述
2. 配套关系
3. 新增特性
4. 变更说明
5. 修复缺陷
6. 已知问题
7. 致谢

## 推荐执行方式

推荐让 Agent 按下面的顺序执行：

1. 用 `fetch_release_context.sh` 或直接 `curl` 拉取原始上下文
2. 读 `assets/MindStudio-Profiler-26.0.0-release-note.md`、`assets/release-note-agent-prompt.md`，建立目标输出风格
3. 读 roadmap、README、关键 docs，先建立版本主题
4. 从 PR/Issue 中挑出真正影响用户感知的能力增强、变更和缺陷修复
5. 当 PR 描述不足时，继续读代码理解真实变更
6. 合并同主题条目，输出 Markdown
7. 最后再回头补齐配套关系和致谢

`python3 scripts/generate_release_note.py` 仍可保留作旧的规则化参考工具，但**不应再作为默认主流程**。

## API参考

GitCode API详细信息见 `references/gitcode-api.md`。

核心端点：
- Issues: `GET /api/v5/repos/{owner}/{repo}/issues`
- PRs: `GET /api/v5/repos/{owner}/{repo}/pulls`
- Issue详情: `GET /api/v5/repos/{owner}/{repo}/issues/{number}`
- Releases: `GET /api/v5/repos/{owner}/{repo}/releases`
