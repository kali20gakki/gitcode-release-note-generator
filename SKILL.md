---
name: gitcode-release-note-generator
description: 自动生成GitCode仓库指定版本的Release Note Markdown文件。根据GitCode API获取仓库在指定时间范围内的PR、Issue和roadmap数据，按标准模板输出结构化release note。适用于需要基于真实GitCode仓库数据生成版本发布说明的场景。触发条件：(1) 用户要求生成release note或版本发布说明，(2) 用户提供GitCode仓库链接、roadmap链接、版本时间范围，(3) 用户需要基于GitCode PR/Issue数据自动生成发布文档。
---

# GitCode Release Note Generator

自动生成GitCode仓库指定版本的release note。

## 使用流程

### 1. 收集必要信息

向用户确认以下输入：

| 参数 | 必须 | 说明 |
| ---- | ---- | ---- |
| `--output` / `-o` | 是 | 输出文件名，如 `Product-26.0.0-release-note.md` |
| `--repo` / `-r` | 是 | 仓库链接，如 `https://gitcode.com/owner/repo` |
| `--roadmap` / `-m` | 是 | Roadmap issue链接 |
| `--time-range` / `-t` | 是 | 版本时间范围 |
| `--token` / `-k` | 是 | GitCode API Token |
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

脚本生成的是**初稿**，必须人工审查并补充以下内容：

- **版本概述**: 补充准确的场景描述和亮点总结
- **配套关系**: 填写实际的软硬件版本要求
- **特性描述**: 为每条特性补充用户视角的描述
- **变更影响**: 为变更说明补充具体影响，标注不兼容变更
- **影响范围**: 为缺陷修复补充影响范围
- **已知问题**: 检查是否有遗漏的已知问题
- **分类调整**: 检查PR/Issue是否被正确分类到特性/变更/缺陷

## 分类规则

脚本按以下规则自动分类：

| 分类 | 触发条件 |
| ---- | -------- |
| 新增特性 | 标签含 `feature`/`enhancement`/`新特性`/`需求`，或标题含 `新增`/`支持`/`添加` |
| 变更说明 | 标签含 `change`/`变更`/`调整`/`修改`，或其他未分类的PR |
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
