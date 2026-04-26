# GitCode Release Note Generator

面向 OpenCode、Codex、Claude Code 等 Agent 的 GitCode 仓库 Release Note 生成 Skill。

提供 GitCode 仓库链接、roadmap、版本时间范围和 token，Agent 会自动拉取该时间范围内的 PR、Issue、roadmap、release/tag 与仓库文档数据，按标准模板生成结构化的 Release Note Markdown 文件。

适合需要基于真实 GitCode 仓库数据快速输出版本发布说明的开发者。

## 快速上手

### 1. 安装 Skill

#### OpenCode

```bash
npx skills add kali20gakki/gitcode-release-note-generator --skill gitcode-release-note-generator -a opencode -g -y
```

或手动克隆到 skills 目录：

```bash
git clone https://github.com/kali20gakki/gitcode-release-note-generator.git
mkdir -p ~/.config/opencode/skills
ln -s "$(pwd)/gitcode-release-note-generator" ~/.config/opencode/skills/gitcode-release-note-generator
```

#### Codex

```bash
npx skills add kali20gakki/gitcode-release-note-generator --skill gitcode-release-note-generator -a codex -g -y
```

#### Claude Code

```bash
npx skills add kali20gakki/gitcode-release-note-generator --skill gitcode-release-note-generator -a claude-code -g -y
```

### 2. 配置 GitCode Token

在 Agent 对话中直接提供，或配置到环境变量：

```bash
export GITCODE_TOKEN=<your-gitcode-token>
```

Token 需要至少拥有 `pull_requests` 和 `issues` 读取权限。未显式传 `--token` 时，脚本会尝试读取环境变量 `GITCODE_TOKEN`。

### 3. 直接使用

在 Agent 中输入提示词即可触发，见下方「提示词模板」。

## 提示词模板

### 基础用法

```
帮我生成 MindStudio Profiler Tools Interface 26.0.0 版本的 release note：

1. 输出文件名：MindStudio-Profiler-Tools-Interface-26.0.0-release-note.md
2. roadmap：https://gitcode.com/Ascend/mspti/issues/3
3. 仓库链接：https://gitcode.com/Ascend/mspti
4. 版本时间范围：2026Q1
5. gitcode token：xxxx
```

### 指定版本号

```
生成 release note：
- 输出文件：Ascend-Toolkit-8.0.0-release-note.md
- 仓库：https://gitcode.com/Ascend/ascend-toolkit
- roadmap：https://gitcode.com/Ascend/ascend-toolkit/issues/100
- 时间范围：2025Q4
- 版本号：8.0.0
- gitcode token：xxx
```

### 自定义日期范围

```
请基于以下信息生成 release note：

- 仓库：https://gitcode.com/owner/repo
- roadmap issue：https://gitcode.com/owner/repo/issues/5
- 时间范围：2026-01-01:2026-03-31
- 版本：v2.1.0
- token：xxx
```

### 生成后要求人工审查

```
帮我生成 release note 初稿，生成后帮我检查：
1. 亮点概述是否准确反映了本版本核心价值
2. 新增特性、变更说明、修复缺陷的分类是否合理
3. 配套关系是否需要补充实际的软硬件版本
4. 有没有遗漏的重要 PR 或 Issue

仓库：https://gitcode.com/owner/repo
roadmap：https://gitcode.com/owner/repo/issues/1
时间范围：2026Q1
token：xxx
```

## 这个 Skill 能做什么

- 自动拉取 GitCode 仓库指定时间范围内的 **Issues** 和 **Pull Requests**
- 读取 **Roadmap Issue**、**README**、安装说明等内容，提取版本亮点、产品定位与部分配套关系
- 读取 **Release/Tag** 信息，尽量补齐发布日期与版本标签
- 按标签、标题与正文关键词自动分类：新增特性、变更说明、修复缺陷、已知问题
- 严格遵循 `assets/release-note-template.md` 结构输出 Markdown
- 提取贡献者信息并生成致谢表格

## 输出模板结构

生成的 release note 包含以下章节：

1. **版本概述** — 版本定位、面向场景、核心亮点（从 roadmap 与仓库文档综合提取）
2. **配套关系** — 软硬件版本要求（优先从仓库文档自动抽取，缺失项再人工补充）
3. **新增特性** — 时间范围内的新功能 PR/Issue
4. **变更说明** — 接口调整、行为变化等（含不兼容变更标注）
5. **修复缺陷** — Bug 修复列表（自动补齐影响范围）
6. **已知问题** — 未修复的遗留问题
7. **致谢** — 贡献者列表

## 时间范围格式

| 格式 | 示例 | 含义 |
|------|------|------|
| 季度 | `2026Q1` | 2026年1月1日 ~ 3月31日 |
| 月份 | `2026-01` | 2026年1月1日 ~ 1月31日 |
| 日期范围 | `2026-01-01:2026-03-31` | 自定义起止日期 |

## 自动分类规则

| 分类 | 触发条件 |
|------|----------|
| 新增特性 | 标签含 `feature`/`enhancement`/`需求`，或标题含 `新增`/`支持`/`添加`/`实现` |
| 变更说明 | 标签含 `change`/`变更`/`调整`/`修改`/`refactor`，或其他未分类 PR/Issue |
| 不兼容变更 | 标签含 `breaking-change`/`不兼容`，或标题含 `不兼容`/`breaking`/`移除`/`废弃` |
| 修复缺陷 | 标签含 `bug`/`bug-report`/`缺陷`，或标题含 `修复`/`fix`/`bug`/`解决` |
| 已知问题 | 标签含 `known-issue`/`已知问题` |
| 文档 | 标签含 `documentation`/`doc`/`文档` |

## ⚠️ 重要提醒

Skill 生成的是 **可交付初稿**，但仍建议做一次人工审查：

- **版本概述**：检查场景描述、版本标签与亮点是否符合正式发布口径
- **配套关系**：补齐仓库文档中未声明的软硬件版本要求
- **特性描述**：检查自动生成的描述是否准确反映用户价值
- **变更影响**：确认是否存在需要额外强调的不兼容调整
- **影响范围**：确认缺陷修复的适用场景是否准确
- **已知问题**：检查是否有遗漏的已知问题
- **分类调整**：检查 PR/Issue 是否被正确分类

## 获取 GitCode API Token

1. 登录 [GitCode](https://gitcode.com)
2. 进入「个人设置」→「访问令牌」
3. 生成新的 Personal Access Token（需要 `pull_requests` 和 `issues` 权限）
4. 在提示词中直接提供，或配置为环境变量 `GITCODE_TOKEN`

## License

[MIT](LICENSE)
