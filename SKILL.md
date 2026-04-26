---
name: gitcode-release-note-generator
description: 自动生成GitCode仓库指定版本的Release Note Markdown文件。根据GitCode API获取仓库在指定时间范围内的PR、Issue和roadmap数据，按标准模板输出结构化release note。适用于需要基于真实GitCode仓库数据生成版本发布说明的场景。触发条件：(1) 用户要求生成release note或版本发布说明，(2) 用户提供GitCode仓库链接、roadmap链接、版本时间范围，(3) 用户需要基于GitCode PR/Issue数据自动生成发布文档。
---

# GitCode Release Note Generator

自动生成 GitCode 仓库指定版本的 release note，并尽量自动补齐版本概述、配套关系、特性描述、变更影响与缺陷影响范围。

## 使用流程

### 1. 收集必要信息

向用户确认以下输入：

| 参数 | 必须 | 说明 |
| ---- | ---- | ---- |
| `--output` / `-o` | 是 | 输出文件名，如 `Product-26.0.0-release-note.md` |
| `--repo` / `-r` | 是 | 仓库链接，如 `https://gitcode.com/owner/repo` |
| `--roadmap` / `-m` | 是 | Roadmap issue链接 |
| `--time-range` / `-t` | 是 | 版本时间范围 |
| `--token` / `-k` | 否 | GitCode API Token；未传时尝试读取 `GITCODE_TOKEN` |
| `--version` / `-v` | 否 | 版本号（默认从输出文件名推断） |
| `--release-url` | 否 | Release页面参考链接 |

**时间范围格式支持：**
- `YYYYQ[1-4]`: 季度格式，如 `2026Q1`
- `YYYY-MM`: 月份格式，如 `2026-01`
- `YYYY-MM-DD:YYYY-MM-DD`: 日期范围，如 `2026-01-01:2026-03-31`

### 2. 运行生成脚本

```bash
python3 scripts/generate_release_note.py \
  --output <输出文件名> \
  --repo <仓库链接> \
  --roadmap <roadmap链接> \
  --time-range <时间范围> \
  --token <GitCode API Token> \
  --version <版本号>
```

### 3. 人工审查与补充

脚本生成的是**可交付初稿**。当前版本会额外尝试：

- 从 roadmap、README、安装文档中提取版本亮点与产品定位
- 自动补齐配套关系中的常见字段，如操作系统、CANN、Python、PyTorch、三方依赖
- 为新增特性、变更说明、修复缺陷生成用户视角的描述
- 对同主题的多条 PR/Issue 做聚合归并，尽量输出接近正式版本公告的条目级摘要
- 通过 release/tag 信息补充发布日期与版本标签

仍建议人工重点复核以下内容：

- **版本概述**: 检查场景定位与版本亮点是否贴合产品口径
- **配套关系**: 检查仓库未声明或抽取不完整的软硬件版本要求
- **特性描述**: 检查自动生成的描述是否足够准确、是否需要更产品化表达
- **变更影响**: 检查是否存在需要显式标注的兼容性影响
- **影响范围**: 检查缺陷修复的适用范围是否足够准确
- **已知问题**: 检查是否有遗漏的已知问题
- **分类调整**: 检查PR/Issue是否被正确分类到特性/变更/缺陷

## 分类规则

脚本按以下规则自动分类：

| 分类 | 触发条件 |
| ---- | -------- |
| 新增特性 | 标签含 `feature`/`enhancement`/`新特性`/`需求`，或标题含 `新增`/`支持`/`添加`/`实现` |
| 变更说明 | 标签含 `change`/`变更`/`调整`/`修改`/`refactor`，或其他未分类的 PR/Issue |
| 不兼容变更 | 标签含 `breaking-change`/`不兼容`，或标题含 `不兼容`/`breaking`/`移除`/`废弃` |
| 修复缺陷 | 标签含 `bug`/`bug-report`/`缺陷`，或标题含 `修复`/`fix`/`bug`/`解决` |
| 已知问题 | 标签含 `known-issue`/`已知问题` |
| 文档 | 标签含 `documentation`/`doc`/`文档` |

## 输出模板

生成的release note严格遵循 `assets/release-note-template.md` 的结构，包含：

1. 版本概述
2. 配套关系
3. 新增特性
4. 变更说明
5. 修复缺陷
6. 已知问题
7. 致谢

## API参考

GitCode API详细信息见 `references/gitcode-api.md`。

核心端点：
- Issues: `GET /api/v5/repos/{owner}/{repo}/issues`
- PRs: `GET /api/v5/repos/{owner}/{repo}/pulls`
- Issue详情: `GET /api/v5/repos/{owner}/{repo}/issues/{number}`
- Releases: `GET /api/v5/repos/{owner}/{repo}/releases`
