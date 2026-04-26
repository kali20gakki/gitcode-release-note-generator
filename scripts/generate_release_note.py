#!/usr/bin/env python3
"""
GitCode Release Note Generator

根据GitCode仓库的PR、Issue和roadmap数据，按模板自动生成release note。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

API_BASE = "https://api.gitcode.com/api/v5"


def parse_repo_url(url: str) -> tuple[str, str]:
    """从GitCode仓库URL解析owner和repo。"""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"无法从URL解析仓库: {url}")
    return parts[0], parts[1]


def parse_issue_url(url: str) -> tuple[str, str, str]:
    """从GitCode issue URL解析owner、repo和issue number。"""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) < 4:
        raise ValueError(f"无法从URL解析issue: {url}")
    return parts[0], parts[1], parts[3]


def parse_time_range(time_range: str) -> tuple[str, str]:
    """解析版本时间范围。"""
    time_range = time_range.strip()

    # 季度格式: 2026Q1
    m = re.match(r"^(\d{4})Q([1-4])$", time_range, re.I)
    if m:
        year = int(m.group(1))
        quarter = int(m.group(2))
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        start = f"{year}-{start_month:02d}-01"
        if end_month == 12:
            end = f"{year}-{end_month:02d}-31"
        elif end_month in [3, 5, 8, 10]:
            end = f"{year}-{end_month:02d}-30"
        else:
            end = f"{year}-{end_month:02d}-30"
        return start, end

    # 月份格式: 2026-01
    m = re.match(r"^(\d{4})-(\d{2})$", time_range)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        start = f"{year}-{month:02d}-01"
        if month == 12:
            end = f"{year}-{month:02d}-31"
        elif month == 2:
            end = f"{year}-{month:02d}-28"
        elif month in [1, 3, 5, 7, 8, 10]:
            end = f"{year}-{month:02d}-31"
        else:
            end = f"{year}-{month:02d}-30"
        return start, end

    # 日期范围格式: 2026-01-01:2026-03-31
    m = re.match(r"^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$", time_range)
    if m:
        return m.group(1), m.group(2)

    raise ValueError(
        f"无法解析时间范围: {time_range}。"
        f"支持的格式: YYYYQ[1-4]、YYYY-MM、YYYY-MM-DD:YYYY-MM-DD"
    )


def api_get(path: str, token: str, params: dict | None = None) -> dict | list:
    """调用GitCode API。"""
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params or {}, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all_pages(path: str, token: str, params: dict | None = None) -> list[dict]:
    """获取API分页的所有数据。"""
    results = []
    page = 1
    per_page = 100
    params = dict(params or {})
    params["per_page"] = per_page

    while True:
        params["page"] = page
        data = api_get(path, token, params)
        if not isinstance(data, list):
            break
        results.extend(data)
        if len(data) < per_page:
            break
        page += 1
        if page > 100:
            break

    return results


def fetch_issues(owner: str, repo: str, token: str, state: str = "all") -> list[dict]:
    """获取仓库所有Issue。"""
    return fetch_all_pages(f"/repos/{owner}/{repo}/issues", token, {"state": state})


def fetch_pulls(owner: str, repo: str, token: str, state: str = "all") -> list[dict]:
    """获取仓库所有Pull Requests。"""
    return fetch_all_pages(f"/repos/{owner}/{repo}/pulls", token, {"state": state})


def fetch_issue_detail(owner: str, repo: str, issue_number: str, token: str) -> dict:
    """获取单个Issue详情。"""
    return api_get(f"/repos/{owner}/{repo}/issues/{issue_number}", token)


def filter_by_time(
    items: list[dict], start: str, end: str, field: str = "created_at"
) -> list[dict]:
    """按创建/更新时间过滤数据。"""
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

    # 统一转为offset-aware
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    filtered = []
    for item in items:
        ts = item.get(field, "")
        if not ts:
            continue
        try:
            item_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if item_dt.tzinfo is None:
                item_dt = item_dt.replace(tzinfo=timezone.utc)
            if start_dt <= item_dt <= end_dt:
                filtered.append(item)
        except ValueError:
            continue
    return filtered


def is_pull_request(item: dict) -> bool:
    """判断item是否为Pull Request（GitCode API中PR也有issue格式但包含pull_request字段）。"""
    return "pull_request" in item or item.get("html_url", "").endswith(
        "/pulls/" + str(item.get("number", ""))
    )


def classify_item(item: dict) -> str:
    """根据标签和标题内容分类issue/PR。"""
    labels = [l.get("name", "").lower() for l in item.get("labels", [])]
    title = item.get("title", "").lower()

    # 已知问题标签
    if any(k in labels for k in ["known-issue", "已知问题"]):
        return "known_issue"

    # bug相关
    if any(k in labels for k in ["bug", "bug-report", "缺陷"]):
        return "bugfix"
    if any(k in title for k in ["修复", "fix", "bug", "解决", "修复"]):
        return "bugfix"

    # 不兼容变更
    if any(k in labels for k in ["breaking-change", "不兼容"]):
        return "breaking"
    if any(k in title for k in ["不兼容", "breaking", "移除", "废弃", "deprecate"]):
        return "breaking"

    # feature
    if any(k in labels for k in ["feature", "enhancement", "新特性", "需求"]):
        return "feature"
    if any(k in title for k in ["新增", "支持", "添加", "add"]):
        return "feature"

    # 文档
    if any(k in labels for k in ["documentation", "doc", "文档"]):
        return "doc"

    # 变更
    if any(k in labels for k in ["change", "变更", "调整", "修改"]):
        return "change"

    # 默认：如果是PR标题包含fix则bugfix，否则feature或change
    if "fix" in title:
        return "bugfix"
    return "change"


def extract_contributors(pulls: list[dict]) -> list[dict]:
    """从PR中提取贡献者信息。"""
    contributors = []
    seen = set()
    for pr in pulls:
        user = pr.get("user", {})
        login = user.get("login", "")
        name = user.get("name", login)
        if not login or login in seen:
            continue
        seen.add(login)
        contributors.append({
            "name": name,
            "login": login,
            "html_url": user.get("html_url", f"https://gitcode.com/{login}"),
            "pr": pr,
        })
    return contributors


def guess_version(output_file: str, time_range: str) -> str:
    """从输出文件名推断版本号。"""
    # 尝试从文件名提取版本号，如 repo-26.0.0-release-note.md
    base = os.path.basename(output_file)
    m = re.search(r"-(\d+\.\d+\.\d+.*?)-release-note", base)
    if m:
        return m.group(1)
    # 从时间范围推断
    m = re.match(r"^(\d{4})", time_range)
    if m:
        return f"{m.group(1)}.x.x"
    return "x.x.x"


def guess_product_name(repo_url: str, repo_name: str) -> str:
    """推断产品名称。"""
    # 从仓库URL或名称推断
    if repo_name.lower() == "mspti":
        return "MindStudio Profiler Tools Interface"
    if repo_name.lower() == "msprof":
        return "MindStudio Profiler"
    return repo_name


def format_link(item: dict) -> str:
    """格式化issue/PR链接。"""
    number = item.get("number", "")
    url = item.get("html_url", "")
    # 判断是否为PR
    if "/merge_requests/" in url or "/pulls/" in url:
        return f"[!{number}]({url})"
    return f"[#{number}]({url})"


def generate_release_note(
    output_file: str,
    repo_url: str,
    roadmap_url: str,
    time_range: str,
    token: str,
    release_url: str | None = None,
    version: str | None = None,
) -> str:
    """生成release note文件。"""
    owner, repo = parse_repo_url(repo_url)
    product_name = guess_product_name(repo_url, repo)

    # 解析时间范围
    start_date, end_date = parse_time_range(time_range)

    # 推断版本号
    if not version:
        version = guess_version(output_file, time_range)

    # 获取数据
    print(f"正在获取 {owner}/{repo} 的数据...")
    issues = fetch_issues(owner, repo, token)
    pulls = fetch_pulls(owner, repo, token)

    # 过滤时间范围
    filtered_issues = filter_by_time(issues, start_date, end_date)
    filtered_pulls = filter_by_time(pulls, start_date, end_date)

    print(f"  Issues: {len(filtered_issues)} / {len(issues)}")
    print(f"  PRs: {len(filtered_pulls)} / {len(pulls)}")

    # 获取roadmap
    roadmap_body = ""
    roadmap_title = ""
    if roadmap_url:
        try:
            r_owner, r_repo, r_number = parse_issue_url(roadmap_url)
            roadmap_data = fetch_issue_detail(r_owner, r_repo, r_number, token)
            roadmap_body = roadmap_data.get("body", "")
            roadmap_title = roadmap_data.get("title", "")
            print(f"  Roadmap已获取: {roadmap_title}")
        except Exception as e:
            print(f"  获取roadmap失败: {e}")

    # 分类
    features = []
    changes = []
    breaking_changes = []
    bugfixes = []
    known_issues_list = []
    docs = []

    # 处理PR
    for pr in filtered_pulls:
        cat = classify_item(pr)
        if cat == "feature":
            features.append(pr)
        elif cat == "bugfix":
            bugfixes.append(pr)
        elif cat == "breaking":
            breaking_changes.append(pr)
        elif cat == "doc":
            docs.append(pr)
        else:
            changes.append(pr)

    # 处理Issue（排除PR，因为GitCode issues API可能返回PR）
    for issue in filtered_issues:
        url = issue.get("html_url", "")
        if "/merge_requests/" in url or "/pulls/" in url:
            continue
        cat = classify_item(issue)
        if cat == "known_issue":
            known_issues_list.append(issue)
        elif cat == "bugfix":
            bugfixes.append(issue)
        elif cat == "feature":
            features.append(issue)

    # 提取贡献者（从PR）
    contributors = extract_contributors(filtered_pulls)

    # 生成markdown
    lines = []
    lines.append(f"# {product_name} {version} 版本发布说明")
    lines.append("")
    lines.append(f"*发布日期：{datetime.now().strftime('%Y-%m-%d')}*")
    lines.append("")

    # 1. 版本概述
    lines.append("## 1. 版本概述")
    lines.append("")
    roadmap_link_text = f"#{r_number}" if roadmap_url else "roadmap"
    lines.append(
        f"{product_name} {version} 是面向xxx场景的版本。"
        f"本说明按照 roadmap [{roadmap_link_text}]({roadmap_url}) "
        f"与仓库 {time_range}（{start_date} 至 {end_date}）范围内的真实提交整理。"
        f"核心亮点如下："
    )
    lines.append("")

    # 从roadmap提取亮点
    highlights = []
    if roadmap_body:
        for line in roadmap_body.split("\n"):
            line = line.strip()
            if line.startswith("## ") and "roadmap" not in line.lower():
                highlight = line.replace("## ", "").strip()
                if highlight:
                    highlights.append(highlight)
            elif line.startswith("- ") and len(highlights) < 5:
                highlight = line.replace("- ", "").strip()
                if highlight and "goal" not in highlight.lower():
                    highlights.append(highlight)

    if not highlights:
        for f in features[:5]:
            highlights.append(f.get("title", ""))

    for h in highlights[:5]:
        lines.append(f"- {h}。")

    if not highlights:
        lines.append("- 请根据实际内容补充亮点。")
    lines.append("")

    # 2. 配套关系
    lines.append("## 2. 配套关系")
    lines.append("")
    lines.append("| 软件/硬件 | 版本要求 | 说明 |")
    lines.append("| ---- | ---- | ---- |")
    lines.append("| 产品型号 | xxx | |")
    lines.append("| 操作系统 | xxx | |")
    lines.append("| 驱动版本 | xxx | |")
    lines.append("| 固件版本 | xxx | |")
    lines.append("| CANN版本 | xxx | |")
    lines.append("| Python版本 | xxx | |")
    lines.append("| PyTorch版本 | xxx | |")
    lines.append("| 依赖三方库 | xxx | |")
    lines.append("")

    # 3. 新增特性
    lines.append("## 3. 新增特性")
    lines.append("")
    if features:
        lines.append("| 序号 | 特性名称 | 特性描述 | 关联Issue/PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for i, f in enumerate(features, 1):
            title = f.get("title", "").replace("|", "\\|")
            lines.append(f"| {i} | {title} | 请补充描述 | {format_link(f)} |")
    else:
        lines.append("不涉及。")
    lines.append("")

    # 4. 变更说明
    lines.append("## 4. 变更说明")
    lines.append("")
    if changes or breaking_changes:
        lines.append("| 序号 | 变更内容 | 变更影响 | 关联Issue/PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for i, c in enumerate(breaking_changes + changes, 1):
            title = c.get("title", "").replace("|", "\\|")
            impact = "**不兼容变更**：请补充影响" if c in breaking_changes else "请补充影响"
            lines.append(f"| {i} | {title} | {impact} | {format_link(c)} |")
    else:
        lines.append("不涉及。")
    lines.append("")

    # 5. 修复缺陷
    lines.append("## 5. 修复缺陷")
    lines.append("")
    if bugfixes:
        lines.append("| 序号 | Issue链接 | 问题描述 | 影响范围 |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for i, b in enumerate(bugfixes, 1):
            title = b.get("title", "").replace("|", "\\|")
            lines.append(f"| {i} | {format_link(b)} | {title} | 请补充影响范围 |")
    else:
        lines.append("不涉及。")
    lines.append("")

    # 6. 已知问题
    lines.append("## 6. 已知问题")
    lines.append("")
    if known_issues_list:
        lines.append("| 序号 | Issue链接 | 问题描述 | 影响 | 规避措施 | 计划修复版本 |")
        lines.append("| ---- | ---- | ---- | ---- | ---- | ---- |")
        for i, k in enumerate(known_issues_list, 1):
            title = k.get("title", "").replace("|", "\\|")
            lines.append(f"| {i} | {format_link(k)} | {title} | 请补充 | 请补充 | vx.x.x |")
    else:
        lines.append("不涉及。")
    lines.append("")

    # 7. 致谢
    lines.append("## 7. 致谢")
    lines.append("")
    lines.append("感谢以下贡献者对本版本的贡献：")
    lines.append("")
    if contributors:
        lines.append("| 序号 | 贡献者 | 贡献内容 | 关联PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for i, c in enumerate(contributors[:20], 1):
            pr = c.get("pr", {})
            pr_title = pr.get("title", "").replace("|", "\\|")
            pr_url = pr.get("html_url", "")
            pr_number = pr.get("number", "")
            lines.append(
                f"| {i} | @{c['login']} | {pr_title} | "
                f"[!{pr_number}]({pr_url}) |"
            )
    else:
        lines.append("（无数据）")
    lines.append("")

    content = "\n".join(lines)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\nRelease note 已生成: {output_file}")
    return content


def main():
    parser = argparse.ArgumentParser(description="GitCode Release Note Generator")
    parser.add_argument("--output", "-o", required=True, help="输出文件名")
    parser.add_argument(
        "--repo", "-r", required=True,
        help="仓库链接，如 https://gitcode.com/owner/repo"
    )
    parser.add_argument("--roadmap", "-m", required=True, help="Roadmap issue链接")
    parser.add_argument(
        "--time-range", "-t", required=True,
        help="版本时间范围，如 2026Q1、2026-01、2026-01-01:2026-03-31"
    )
    parser.add_argument("--token", "-k", required=True, help="GitCode API Token")
    parser.add_argument("--release-url", help="Release页面参考链接（可选）")
    parser.add_argument("--version", "-v", help="版本号（可选，默认从文件名推断）")

    args = parser.parse_args()

    generate_release_note(
        output_file=args.output,
        repo_url=args.repo,
        roadmap_url=args.roadmap,
        time_range=args.time_range,
        token=args.token,
        release_url=args.release_url,
        version=args.version,
    )


if __name__ == "__main__":
    main()
