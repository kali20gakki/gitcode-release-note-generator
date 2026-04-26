# 贡献指南

感谢你对本项目的关注！以下是参与贡献的说明。

## 如何贡献

### 提交 Issue

如果你发现了 bug 或有功能建议，请通过 GitHub Issue 提交：

- **Bug 报告**：描述问题现象、复现步骤、期望结果和实际结果
- **功能建议**：描述功能场景、预期行为和实现思路
- **使用问题**：提供仓库链接、时间范围、命令行参数和错误日志

### 提交 Pull Request

1. Fork 本仓库
2. 创建你的功能分支：`git checkout -b feature/my-feature`
3. 提交更改：`git commit -am 'Add some feature'`
4. 推送分支：`git push origin feature/my-feature`
5. 提交 Pull Request

## 代码规范

- Python 代码遵循 PEP 8 规范
- 保持脚本简洁，优先使用标准库
- 新增功能需附带使用说明

## 发布流程

如需更新 Skill 包：

```bash
cd gitcode-release-note-generator
zip -r ../gitcode-release-note-generator.skill .
```
