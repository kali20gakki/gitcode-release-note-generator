# MindStudio Profiler 26.0.0 版本发布说明

*发布日期：2026-04-xxx*

## 1. 版本概述

MindStudio Profiler 26.0.0 是面向 AI 训练与推理场景的性能采集与解析版本，主要服务于 CANN 平台及昇腾 AI 处理器性能分析用户。本说明按照 roadmap [#9](https://gitcode.com/Ascend/msprof/issues/9) 与仓库 2026Q1（2026-01-01 至 2026-03-31）范围内的真实提交整理，对应版本标签 `tag_MindStudio_26.0.0.B100_001` 于 2026-04-01 创建。核心亮点如下：

- 新增 Python GIL 锁检测能力，帮助定位 Python 侧锁竞争导致的性能问题。
- 增强 HostToDevice 关联分析，支持 wait/record 事件连线，便于查看主机与设备侧执行关系。
- 扩展 A5 及新芯片场景解析能力，补齐硬件级 timeline、ACLGraph 与多类 C 化导出数据支持。
- 优化 run 包安装与卸载流程，适配 CANN 整包安装场景，并提供 `--uninstall` 卸载能力。
- 修复大数据量 `op_summary` 算子匹配、FFTS+ 数据关联、A5 数据过滤等问题，提升解析结果稳定性和准确性。

## 2. 配套关系

| 软件/硬件 | 版本要求 | 说明 |
| ---- | ---- | ---- |
| 产品型号 | Atlas 350 加速卡；Atlas A3 训练系列产品/Atlas A3 推理系列产品；Atlas A2 训练系列产品/Atlas A2 推理系列产品；Atlas 200I/500 A2 推理产品；Atlas 推理系列产品；Atlas 训练系列产品 | 根据仓库文档中的产品支持情况整理 |
| 操作系统 | Ubuntu；openEuler/CentOS | 源码编译安装指南提供了对应依赖安装方式 |
| 驱动版本 | 随配套 CANN 环境 | 仓库未单独声明固定驱动版本 |
| 固件版本 | 随配套 CANN 环境 | 仓库未单独声明固定固件版本 |
| CANN版本 | ？ | 根据 `README.md` 与 `msprof_parsing_instruct.md` 整理 |
| Python版本 | 3.7.5 及以上 | 解析命令 `--python-path` 的版本要求 |
| PyTorch版本 | 未单独声明固定版本 | 仓库文档提及支持 Ascend PyTorch Profiler 场景 |
| 依赖三方库 | SQLite3 | 源码编译安装依赖 |

## 3. 新增特性

| 序号 | 特性名称 | 特性描述 | 关联Issue/PR |
| ---- | ---- | ---- | ---- |
| 1 | Python GIL 锁检测 | 新增 GIL Tracer 采集与转换能力，可辅助定位 Python 线程锁竞争导致的性能瓶颈。 | [!83](https://gitcode.com/Ascend/msprof/merge_requests/83) |
| 2 | wait/record 事件 HostToDevice 连线 | 在 HostToDevice 视图中增加 wait/record event 与 `memcpyAsync` event 的关联连线，便于从 Host 侧调用追踪到 Device 侧执行。 | [!55](https://gitcode.com/Ascend/msprof/merge_requests/55) |
| 3 | A5 与新芯片场景解析增强 | 增强 A5 代际继承硬件级 timeline 的 C 化适配，补齐 BIU/UB/CCU 等数据解析，并新增 chip 2/3/4 的 ACLGraph 场景解析支持。 | [!96](https://gitcode.com/Ascend/msprof/merge_requests/96)、[!98](https://gitcode.com/Ascend/msprof/merge_requests/98)、[!101](https://gitcode.com/Ascend/msprof/merge_requests/101)、[!105](https://gitcode.com/Ascend/msprof/merge_requests/105)、[!106](https://gitcode.com/Ascend/msprof/merge_requests/106) |
| 4 | PMU 解析能力增强 | 解除 PMU 解析限制，支持更多 PMU 指标与自定义 PMU 场景解析。 | [!54](https://gitcode.com/Ascend/msprof/merge_requests/54) |

## 4. 变更说明

| 序号 | 变更内容 | 变更影响 | 关联Issue/PR |
| ---- | ---- | ---- | ---- |
| 1 | run 包安装与卸载流程调整 | run 包适配安装到 CANN 整包目录，新增 `--uninstall` 卸载参数，并要求 `--install-path` 直接指向实际 `cann` 目录，方便与整包安装流程对齐。 | [!62](https://gitcode.com/Ascend/msprof/merge_requests/62)、[!64](https://gitcode.com/Ascend/msprof/merge_requests/64)、[!84](https://gitcode.com/Ascend/msprof/merge_requests/84) |
| 2 | run 包命名统一 | **不兼容变更**：run 包文件名由 `Ascend-mindstudio-msprof_<version>_linux-<os_arch>.run` 调整为 `ascend-mindstudio-msprof_<version>_<os_arch>.run`，依赖旧文件名的自动化脚本需要同步适配。 | [!56](https://gitcode.com/Ascend/msprof/merge_requests/56) |
| 3 | 性能结果展示字段与表头调整 | `task_time` 支持展示 `kernel_name`，UB summary 删减冗余字段并调整表头，`block Dim` 重命名为 `block Num`。依赖旧字段名或旧表头的解析脚本需要同步更新。 | [!40](https://gitcode.com/Ascend/msprof/merge_requests/40)、[!47](https://gitcode.com/Ascend/msprof/merge_requests/47)、[!134](https://gitcode.com/Ascend/msprof/merge_requests/134) |

## 5. 修复缺陷

| 序号 | Issue链接 | 问题描述 | 影响范围 |
| ---- | ---- | ---- | ---- |
| 1 | [#5](https://gitcode.com/Ascend/msprof/issues/5) | 修复 UT Mock 范围错误及断言逻辑问题，降低开发自测阶段的误报与误判。 | 单元测试与开发自测场景 |
| 2 | [!89](https://gitcode.com/Ascend/msprof/merge_requests/89) | 修复 `<<<>>>` 场景上报 shape 信息变化后 FFTS+ 数据关联失败的问题，恢复相关场景的正确关联。 | FFTS+ 解析场景 |
| 3 | [!139](https://gitcode.com/Ascend/msprof/merge_requests/139) | 修复大数据量场景下 `op_summary` 因 task id 回绕导致的算子匹配错误问题。 | 大数据量 `op_summary` 解析场景 |
| 4 | [!114](https://gitcode.com/Ascend/msprof/merge_requests/114)、[!124](https://gitcode.com/Ascend/msprof/merge_requests/124)、[!155](https://gitcode.com/Ascend/msprof/merge_requests/155) | 修复 A5 场景下 timeline C 化导出缺少 `block_detail`、`lower_power` 以及打点数据被误过滤等问题。 | A5 数据采集与导出场景 |
| 5 | [!158](https://gitcode.com/Ascend/msprof/merge_requests/158) | 修复 CANN 整包安装过程中 msprof 卸载脚本可能存在残留的问题。 | CANN 整包安装/卸载场景 |

## 8. 已知问题

不涉及。

## 11. 致谢

感谢以下贡献者对本版本的贡献：

| 序号 | 贡献者 | 贡献内容 | 关联PR |
| ---- | ---- | ---- | ---- |
| 1 | @eejiechu | 新增 Python GIL 锁检测能力 | [!83](https://gitcode.com/Ascend/msprof/merge_requests/83) |
| 2 | @panzhaohu | 增加 wait/record 事件 HostToDevice 连线 | [!55](https://gitcode.com/Ascend/msprof/merge_requests/55) |
| 3 | @yu_liangbin | 完成 run 包安装/卸载流程适配与 CANN 整包集成支持 | [!84](https://gitcode.com/Ascend/msprof/merge_requests/84) |
| 4 | @Seanesmhxocism | 增强新芯片 ACLGraph 解析能力 | [!106](https://gitcode.com/Ascend/msprof/merge_requests/106) |
| 5 | @fanhong | 修复大数据量 `op_summary` 算子匹配错误 | [!139](https://gitcode.com/Ascend/msprof/merge_requests/139) |
| 6 | @SoraAzzz | 增强 PMU 解析能力 | [!54](https://gitcode.com/Ascend/msprof/merge_requests/54) |
