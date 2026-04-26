#!/usr/bin/env python3
"""
GitCode Release Note Generator

根据 GitCode 仓库的 PR、Issue、Roadmap、Release 与仓库文档，自动生成
质量更高的 release note 初稿。
"""

from __future__ import annotations

import argparse
import calendar
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote, urlparse

import requests

API_BASE = "https://api.gitcode.com/api/v5"
RAW_BASE = "https://gitcode.com"
USER_AGENT = "gitcode-release-note-generator/2.0"

FEATURE_LABEL_KEYWORDS = {
    "feature", "enhancement", "新特性", "需求", "feat", "epic",
}
CHANGE_LABEL_KEYWORDS = {
    "change", "变更", "调整", "修改", "refactor", "optimization",
}
BUG_LABEL_KEYWORDS = {
    "bug", "bug-report", "缺陷", "hotfix", "fix",
}
KNOWN_ISSUE_LABEL_KEYWORDS = {"known-issue", "已知问题"}
DOC_LABEL_KEYWORDS = {"documentation", "doc", "文档"}
BREAKING_LABEL_KEYWORDS = {"breaking-change", "不兼容"}

FEATURE_TITLE_KEYWORDS = [
    "新增", "支持", "添加", "接入", "上线", "发布", "能力", "特性",
    "实现", "提供", "enable", "support", "add", "introduce",
]
CHANGE_TITLE_KEYWORDS = [
    "调整", "优化", "更新", "升级", "改造", "重构", "修改",
    "adapt", "update", "refactor", "optimize", "rename",
]
BUG_TITLE_KEYWORDS = [
    "修复", "fix", "bug", "异常", "问题", "卡死", "崩溃", "残留",
]
BREAKING_TITLE_KEYWORDS = [
    "不兼容", "breaking", "移除", "废弃", "deprecate", "rename",
]
DOC_TITLE_KEYWORDS = [
    "doc", "readme", "文档", "说明书", "指导", "资料",
]
NOISY_CHANGE_KEYWORDS = [
    "ci", "流水线", "presmoke", "wip", "临时出包", "lint", "format",
    "clean", "cleancode", "secure compile", "safe",
]


def parse_repo_url(url: str) -> tuple[str, str]:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"无法从 URL 解析仓库: {url}")
    return parts[0], parts[1]


def parse_issue_url(url: str) -> tuple[str, str, str]:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) < 4:
        raise ValueError(f"无法从 URL 解析 issue: {url}")
    return parts[0], parts[1], parts[3]


def parse_time_range(time_range: str) -> tuple[str, str]:
    time_range = time_range.strip()

    quarter_match = re.match(r"^(\d{4})Q([1-4])$", time_range, re.I)
    if quarter_match:
        year = int(quarter_match.group(1))
        quarter = int(quarter_match.group(2))
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        start = f"{year}-{start_month:02d}-01"
        end_day = calendar.monthrange(year, end_month)[1]
        end = f"{year}-{end_month:02d}-{end_day:02d}"
        return start, end

    month_match = re.match(r"^(\d{4})-(\d{2})$", time_range)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        start = f"{year}-{month:02d}-01"
        end_day = calendar.monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{end_day:02d}"
        return start, end

    date_range_match = re.match(r"^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$", time_range)
    if date_range_match:
        return date_range_match.group(1), date_range_match.group(2)

    raise ValueError(
        f"无法解析时间范围: {time_range}。"
        "支持格式: YYYYQ[1-4]、YYYY-MM、YYYY-MM-DD:YYYY-MM-DD"
    )


def parse_iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_end_date(end: str) -> datetime:
    end_dt = parse_iso_datetime(end)
    if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
        end_dt = end_dt + timedelta(days=1) - timedelta(microseconds=1)
    return end_dt


def api_get(path: str, token: str, params: dict | None = None) -> dict | list:
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, params=params or {}, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all_pages(path: str, token: str, params: dict | None = None) -> list[dict]:
    results: list[dict] = []
    page = 1
    per_page = 100
    query = dict(params or {})
    query["per_page"] = per_page

    while True:
        query["page"] = page
        data = api_get(path, token, query)
        if not isinstance(data, list):
            break
        results.extend(data)
        if len(data) < per_page or page >= 100:
            break
        page += 1
    return results


def fetch_issues(owner: str, repo: str, token: str, state: str = "all") -> list[dict]:
    return fetch_all_pages(f"/repos/{owner}/{repo}/issues", token, {"state": state})


def fetch_pulls(owner: str, repo: str, token: str, state: str = "all") -> list[dict]:
    return fetch_all_pages(f"/repos/{owner}/{repo}/pulls", token, {"state": state})


def fetch_issue_detail(owner: str, repo: str, issue_number: str, token: str) -> dict:
    return api_get(f"/repos/{owner}/{repo}/issues/{issue_number}", token)


def fetch_repo(owner: str, repo: str, token: str) -> dict:
    return api_get(f"/repos/{owner}/{repo}", token)


def fetch_releases(owner: str, repo: str, token: str) -> list[dict]:
    data = api_get(f"/repos/{owner}/{repo}/releases", token)
    return data if isinstance(data, list) else []


def fetch_tags(owner: str, repo: str, token: str) -> list[dict]:
    data = api_get(f"/repos/{owner}/{repo}/tags", token)
    return data if isinstance(data, list) else []


def fetch_raw_file(owner: str, repo: str, file_path: str, token: str) -> str:
    encoded = quote(file_path, safe="/")
    url = f"{RAW_BASE}/{owner}/{repo}/raw/master/{encoded}"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 404:
        alt_url = f"{RAW_BASE}/{owner}/{repo}/-/raw/master/{encoded}"
        response = requests.get(alt_url, headers=headers, timeout=30)
    if response.ok:
        return response.text
    return ""


def filter_by_time(items: list[dict], start: str, end: str, field: str = "created_at") -> list[dict]:
    start_dt = parse_iso_datetime(start)
    end_dt = normalize_end_date(end)
    filtered: list[dict] = []
    for item in items:
        ts = item.get(field)
        if not ts:
            continue
        try:
            item_dt = parse_iso_datetime(ts)
        except ValueError:
            continue
        if start_dt <= item_dt <= end_dt:
            filtered.append(item)
    return filtered


def is_pull_request(item: dict) -> bool:
    url = item.get("html_url", "")
    return "pull_request" in item or "/merge_requests/" in url or "/pulls/" in url


def normalize_text(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\r", "\n")
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"!\[(.*?)\]\((.*?)\)", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[#>*_~-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_title(title: str) -> str:
    title = normalize_text(title)
    title = re.sub(r"^\[(feature|bug|bugfix|roadmap|wip|doc|docs)\]\s*[:：-]?\s*", "", title, flags=re.I)
    title = re.sub(r"^【[^】]+】", "", title)
    title = re.sub(r"^\[[^\]]+\]\s*", "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip(" .:-")


def get_labels(item: dict) -> list[str]:
    return [label.get("name", "").lower() for label in item.get("labels", [])]


def contains_any(text: str, keywords: list[str] | set[str]) -> bool:
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in keywords)


def classify_item(item: dict) -> str:
    labels = get_labels(item)
    raw_title = item.get("title", "")
    title = normalize_title(raw_title)
    body = normalize_text(item.get("body", ""))
    combined = f"{raw_title} {title} {body}".lower()

    if contains_any(combined, ["roadmap"]) and item.get("html_url", "").endswith(f"/issues/{item.get('number')}"):
        return "roadmap"
    if any(keyword in labels for keyword in KNOWN_ISSUE_LABEL_KEYWORDS):
        return "known_issue"
    if any(keyword in labels for keyword in BREAKING_LABEL_KEYWORDS) or contains_any(combined, BREAKING_TITLE_KEYWORDS):
        return "breaking"
    if any(keyword in labels for keyword in BUG_LABEL_KEYWORDS) or contains_any(combined, BUG_TITLE_KEYWORDS):
        return "bugfix"
    if any(keyword in labels for keyword in DOC_LABEL_KEYWORDS) or contains_any(combined, DOC_TITLE_KEYWORDS):
        return "doc"
    if any(keyword in labels for keyword in FEATURE_LABEL_KEYWORDS):
        return "feature"
    if any(keyword in labels for keyword in CHANGE_LABEL_KEYWORDS):
        return "change"
    if contains_any(combined, FEATURE_TITLE_KEYWORDS):
        return "feature"
    if contains_any(combined, CHANGE_TITLE_KEYWORDS) or contains_any(combined, NOISY_CHANGE_KEYWORDS):
        return "change"
    if is_pull_request(item):
        return "change"
    return "other"


def extract_contributors(pulls: list[dict]) -> list[dict]:
    contributors: list[dict] = []
    seen: set[str] = set()
    for pr in pulls:
        user = pr.get("user", {})
        login = user.get("login", "")
        if not login or login in seen:
            continue
        seen.add(login)
        contributors.append(
            {
                "login": login,
                "name": user.get("name", login),
                "html_url": user.get("html_url", f"https://gitcode.com/{login}"),
                "pr": pr,
            }
        )
    return contributors


def guess_version(output_file: str, time_range: str) -> str:
    base = os.path.basename(output_file)
    matched = re.search(r"-(\d+\.\d+\.\d+(?:[-._][A-Za-z0-9]+)*)-release-note", base)
    if matched:
        return matched.group(1)
    year_match = re.match(r"^(\d{4})", time_range)
    if year_match:
        return f"{year_match.group(1)}.x.x"
    return "x.x.x"


def guess_product_name(repo_url: str, repo_name: str) -> str:
    repo_key = repo_name.lower()
    special_names = {
        "mspti": "MindStudio Profiler Tools Interface",
        "msprof": "MindStudio Profiler",
        "msmonitor": "MindStudio Monitor",
    }
    return special_names.get(repo_key, repo_name)


def format_link(item: dict) -> str:
    number = item.get("number", "")
    url = item.get("html_url", "")
    if "/merge_requests/" in url or "/pulls/" in url:
        return f"[!{number}]({url})"
    return f"[#{number}]({url})"


def clean_cell(text: str) -> str:
    text = normalize_text(text).replace("|", "\\|")
    return text if text else "不涉及"


def trim_sentence(text: str, max_len: int = 120) -> str:
    text = normalize_text(text)
    if len(text) <= max_len:
        return text
    shortened = text[:max_len].rsplit(" ", 1)[0].strip()
    return f"{shortened}..."


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in split_lines(text):
        if re.match(r"^[-*+]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            cleaned = re.sub(r"^[-*+]\s+|^\d+[.)]\s+", "", line).strip()
            cleaned = normalize_title(cleaned)
            if cleaned:
                bullets.append(cleaned)
    return bullets


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def infer_release_meta(version: str, releases: list[dict], tags: list[dict], release_url: str | None = None) -> dict:
    result = {"tag_name": "", "released_at": "", "source_url": release_url or ""}
    version_lower = version.lower()

    candidates = releases or []
    for release in candidates:
        tag_name = (release.get("tag_name") or release.get("name") or "").strip()
        if version_lower in tag_name.lower():
            result["tag_name"] = tag_name
            result["released_at"] = (release.get("created_at") or release.get("published_at") or "")[:10]
            result["source_url"] = release.get("html_url", result["source_url"])
            return result

    for tag in tags or []:
        tag_name = (tag.get("name") or "").strip()
        if version_lower in tag_name.lower():
            result["tag_name"] = tag_name
            commit = tag.get("commit") or {}
            commit_date = commit.get("created_at") or commit.get("committed_date") or ""
            result["released_at"] = commit_date[:10]
            return result
    return result


def infer_positioning(repo_data: dict, readme_text: str, product_name: str) -> str:
    description = normalize_text(repo_data.get("description", ""))
    if description:
        return f"{product_name} 是面向 {description} 的版本。"

    readme_lines = split_lines(readme_text)
    for line in readme_lines[:20]:
        line_text = normalize_text(line)
        if product_name.lower() in line_text.lower():
            continue
        if 12 <= len(line_text) <= 80:
            return f"{product_name} 是面向 {line_text} 的版本。"

    fallback_map = {
        "MindStudio Profiler": "MindStudio Profiler 是面向 AI 训练与推理场景的性能采集与解析版本。",
        "MindStudio Monitor": "MindStudio Monitor 是面向昇腾 AI 场景的轻量性能采集与监控版本。",
    }
    return fallback_map.get(product_name, f"{product_name} 是当前仓库对应版本。")


def infer_support_matrix(readme_text: str, docs_text: str) -> list[tuple[str, str, str]]:
    corpus = f"{readme_text}\n{docs_text}"
    support_rows: list[tuple[str, str, str]] = []

    def find_values(pattern: str, source_text: str = corpus) -> list[str]:
        values: list[str] = []
        for match in re.finditer(pattern, source_text, re.I):
            value = normalize_text(match.group(1))
            if value:
                values.extend([piece.strip(" ;,.") for piece in re.split(r"[;/]|；|、|,|\u3001", value) if piece.strip()])
        return dedupe_keep_order(values)

    product_models = find_values(r"(Atlas[^。\n]+)")
    operating_systems = find_values(r"(Ubuntu[^。\n]*)|(openEuler[^。\n]*)|(CentOS[^。\n]*)")
    cann_versions = find_values(r"CANN(?:\s*版本)?[:：\s]*([0-9A-Za-z.\-_+]+)")
    python_versions = find_values(r"Python(?:\s*版本)?[:：\s]*([0-9A-Za-z.\- ]+(?:及以上|以上)?)")
    pytorch_versions = find_values(r"PyTorch(?:\s*版本)?[:：\s]*([0-9A-Za-z.\- ]+(?:及以上|以上)?)")

    third_party_libs = []
    if re.search(r"sqlite3", corpus, re.I):
        third_party_libs.append("SQLite3")
    if re.search(r"prometheus", corpus, re.I):
        third_party_libs.append("Prometheus")

    support_rows.append((
        "产品型号",
        "；".join(product_models) if product_models else "未在仓库文档中明确列出",
        "根据仓库文档中的产品支持说明整理" if product_models else "仓库文档未显式声明具体产品型号",
    ))
    support_rows.append((
        "操作系统",
        "；".join(operating_systems) if operating_systems else "未单独声明固定操作系统版本",
        "根据安装或编译文档整理" if operating_systems else "建议结合安装文档确认实际部署环境",
    ))
    support_rows.append(("驱动版本", "随配套 CANN 环境", "仓库未单独声明固定驱动版本"))
    support_rows.append(("固件版本", "随配套 CANN 环境", "仓库未单独声明固定固件版本"))
    support_rows.append((
        "CANN版本",
        "；".join(cann_versions) if cann_versions else "未单独声明固定版本",
        "根据仓库 README 与说明文档整理" if cann_versions else "建议结合配套发布资料确认",
    ))
    support_rows.append((
        "Python版本",
        "；".join(python_versions) if python_versions else "未单独声明固定版本",
        "根据仓库命令说明与安装文档整理" if python_versions else "建议结合运行环境要求确认",
    ))
    support_rows.append((
        "PyTorch版本",
        "；".join(pytorch_versions) if pytorch_versions else "未单独声明固定版本",
        "仓库文档如涉及 PyTorch 场景，请以实际说明为准",
    ))
    support_rows.append((
        "依赖三方库",
        "；".join(third_party_libs) if third_party_libs else "未在仓库文档中明确列出",
        "根据仓库中出现的依赖名称整理" if third_party_libs else "如有额外依赖，建议结合安装脚本补充",
    ))
    return support_rows


def issue_pr_key(title: str) -> str:
    title = normalize_title(title).lower()
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title)
    return title


def build_issue_index(issues: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        index[issue_pr_key(issue.get("title", ""))].append(issue)
    return index


def find_related_issues(item: dict, issue_index: dict[str, list[dict]]) -> list[dict]:
    key = issue_pr_key(item.get("title", ""))
    related = list(issue_index.get(key, []))
    body = normalize_text(item.get("body", ""))
    for match in re.findall(r"(?:#|!)(\d+)", body):
        for issues in issue_index.values():
            for issue in issues:
                if str(issue.get("number")) == match and issue not in related:
                    related.append(issue)
    return related


def combined_links(item: dict, related_issues: list[dict]) -> str:
    links = [format_link(item)]
    for issue in related_issues:
        issue_link = format_link(issue)
        if issue_link not in links:
            links.append(issue_link)
    return "、".join(links)


def choose_primary_sentence(item: dict) -> str:
    body = item.get("body", "")
    bullets = extract_bullets(body)
    if bullets:
        return bullets[0]
    for line in split_lines(body):
        sentence = normalize_text(line)
        if len(sentence) >= 14 and "http" not in sentence.lower():
            return sentence
    return ""


def describe_feature(item: dict, related_issues: list[dict]) -> str:
    title = normalize_title(item.get("title", ""))
    issue_titles = [normalize_title(issue.get("title", "")) for issue in related_issues]
    base = choose_primary_sentence(item)
    if base:
        return trim_sentence(base.replace(title, "").strip(" ：:-"), 120) or trim_sentence(base, 120)

    if contains_any(title, ["支持", "新增", "添加", "实现", "enable", "support", "add"]):
        return f"{title}，提升该版本在对应场景下的使用能力与可观测性。"
    if issue_titles:
        return f"{title}，对应需求包括 {clean_cell(issue_titles[0])}。"
    return f"{title}，用于补齐本版本的功能能力。"


def describe_change(item: dict) -> str:
    title = normalize_title(item.get("title", ""))
    body_sentence = choose_primary_sentence(item)
    if body_sentence:
        return trim_sentence(body_sentence, 120)
    if contains_any(title, ["readme", "文档", "指导", "说明书", "资料"]):
        return f"更新相关文档与使用说明，帮助用户更快完成安装、构建或特性使用。"
    if contains_any(title, ["ci", "流水线", "presmoke"]):
        return "调整 CI 或预检流程，提升版本交付阶段的构建与验证稳定性。"
    if contains_any(title, ["secure", "safe", "clean", "refactor", "优化"]):
        return "优化现有实现与工程质量，对外接口预期不变，但稳定性与可维护性有所提升。"
    return f"{title}，对现有功能或交付流程进行了调整。"


def describe_breaking_change(item: dict) -> str:
    change = describe_change(item)
    return f"**不兼容变更**：{change} 如已有自动化脚本或既有流程依赖旧行为，需同步完成适配。"


def describe_bugfix(item: dict, related_issues: list[dict]) -> tuple[str, str]:
    title = normalize_title(item.get("title", ""))
    body_sentence = choose_primary_sentence(item)
    issue_titles = [normalize_title(issue.get("title", "")) for issue in related_issues]

    if body_sentence:
        description = trim_sentence(body_sentence, 120)
    elif issue_titles:
        description = trim_sentence(issue_titles[0], 120)
    else:
        description = title

    if contains_any(description, ["卡死", "hang", "死锁"]):
        scope = "运行时采集与数据落盘场景"
    elif contains_any(description, ["build", "安装", "编译", "deb", "run 包"]):
        scope = "构建、安装与发包场景"
    elif contains_any(description, ["save", "文件", "路径", "目录"]):
        scope = "结果保存与本地文件输出场景"
    elif contains_any(description, ["trace", "monitor", "marker", "device"]):
        scope = "监控采集与数据解析场景"
    else:
        scope = "相关功能使用场景"
    return description, scope


def extract_highlights(
    roadmap_title: str,
    roadmap_body: str,
    features: list[dict],
    changes: list[dict],
) -> list[str]:
    candidates: list[str] = []
    if roadmap_title and "roadmap" not in roadmap_title.lower():
        candidates.append(normalize_title(roadmap_title))
    candidates.extend(extract_bullets(roadmap_body))

    for item in features[:8]:
        candidates.append(normalize_title(item.get("title", "")))
    for item in changes[:4]:
        title = normalize_title(item.get("title", ""))
        if contains_any(title, ["安装", "卸载", "解析", "适配", "支持", "性能", "trace"]):
            candidates.append(title)

    cleaned: list[str] = []
    for item in dedupe_keep_order(candidates):
        if not item:
            continue
        if contains_any(item, ["roadmap", "q1", "q2", "q3", "q4"]):
            continue
        if len(item) < 4:
            continue
        cleaned.append(item)
    return cleaned[:5]


def render_support_matrix(lines: list[str], rows: list[tuple[str, str, str]]) -> None:
    lines.append("## 2. 配套关系")
    lines.append("")
    lines.append("| 软件/硬件 | 版本要求 | 说明 |")
    lines.append("| ---- | ---- | ---- |")
    for name, version, note in rows:
        lines.append(f"| {name} | {clean_cell(version)} | {clean_cell(note)} |")
    lines.append("")


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: (item.get("created_at", ""), item.get("number", 0)))


def generate_release_note(
    output_file: str,
    repo_url: str,
    roadmap_url: str,
    time_range: str,
    token: str,
    release_url: str | None = None,
    version: str | None = None,
) -> str:
    owner, repo = parse_repo_url(repo_url)
    product_name = guess_product_name(repo_url, repo)
    start_date, end_date = parse_time_range(time_range)
    version = version or guess_version(output_file, time_range)

    print(f"正在获取 {owner}/{repo} 的数据...")
    repo_data = fetch_repo(owner, repo, token)
    issues = fetch_issues(owner, repo, token)
    pulls = fetch_pulls(owner, repo, token)

    filtered_issues = filter_by_time(issues, start_date, end_date)
    filtered_pulls = filter_by_time(pulls, start_date, end_date)

    print(f"  Issues: {len(filtered_issues)} / {len(issues)}")
    print(f"  PRs: {len(filtered_pulls)} / {len(pulls)}")

    roadmap_body = ""
    roadmap_title = ""
    roadmap_number = ""
    if roadmap_url:
        try:
            r_owner, r_repo, roadmap_number = parse_issue_url(roadmap_url)
            roadmap_data = fetch_issue_detail(r_owner, r_repo, roadmap_number, token)
            roadmap_body = roadmap_data.get("body", "")
            roadmap_title = roadmap_data.get("title", "")
            print(f"  Roadmap 已获取: {roadmap_title}")
        except Exception as exc:
            print(f"  获取 roadmap 失败: {exc}")

    readme_text = fetch_raw_file(owner, repo, "README.md", token)
    docs_text = "\n\n".join(
        filter(
            None,
            [
                fetch_raw_file(owner, repo, "docs/README.md", token),
                fetch_raw_file(owner, repo, "docs/install.md", token),
                fetch_raw_file(owner, repo, "docs/quick_start.md", token),
                fetch_raw_file(owner, repo, "docs/msprof_parsing_instruct.md", token),
                fetch_raw_file(owner, repo, "docs/msmonitor_parsing_instruct.md", token),
            ],
        )
    )

    releases: list[dict] = []
    tags: list[dict] = []
    try:
        releases = fetch_releases(owner, repo, token)
    except Exception as exc:
        print(f"  获取 releases 失败: {exc}")
    try:
        tags = fetch_tags(owner, repo, token)
    except Exception as exc:
        print(f"  获取 tags 失败: {exc}")
    release_meta = infer_release_meta(version, releases, tags, release_url)

    features: list[dict] = []
    changes: list[dict] = []
    breaking_changes: list[dict] = []
    bugfixes: list[dict] = []
    known_issues_list: list[dict] = []
    docs: list[dict] = []

    for pr in filtered_pulls:
        category = classify_item(pr)
        if category == "feature":
            features.append(pr)
        elif category == "bugfix":
            bugfixes.append(pr)
        elif category == "breaking":
            breaking_changes.append(pr)
        elif category == "doc":
            docs.append(pr)
            changes.append(pr)
        elif category == "roadmap":
            continue
        else:
            changes.append(pr)

    pure_issues: list[dict] = []
    for issue in filtered_issues:
        if is_pull_request(issue):
            continue
        if roadmap_url and issue.get("html_url") == roadmap_url:
            continue
        pure_issues.append(issue)
        category = classify_item(issue)
        if category == "known_issue":
            known_issues_list.append(issue)
        elif category == "bugfix":
            bugfixes.append(issue)
        elif category == "feature":
            features.append(issue)
        elif category in {"change", "doc"}:
            changes.append(issue)

    issue_index = build_issue_index(pure_issues)
    contributors = extract_contributors(sort_items(filtered_pulls))
    support_rows = infer_support_matrix(readme_text, docs_text)
    highlights = extract_highlights(roadmap_title, roadmap_body, sort_items(features), sort_items(changes))
    positioning = infer_positioning(repo_data, readme_text, product_name)

    lines: list[str] = []
    lines.append(f"# {product_name} {version} 版本发布说明")
    lines.append("")
    release_date = release_meta["released_at"] or datetime.now().strftime("%Y-%m-%d")
    lines.append(f"*发布日期：{release_date}*")
    lines.append("")

    lines.append("## 1. 版本概述")
    lines.append("")
    overview_parts = [
        positioning.rstrip("。"),
        f"本说明按照 roadmap [#{roadmap_number}]({roadmap_url}) 与仓库 {time_range}（{start_date} 至 {end_date}）范围内的真实提交整理。"
        if roadmap_url and roadmap_number
        else f"本说明基于仓库 {time_range}（{start_date} 至 {end_date}）范围内的真实提交整理。",
    ]
    if release_meta["tag_name"]:
        release_sentence = f"对应版本标签 `{release_meta['tag_name']}`"
        if release_meta["released_at"]:
            release_sentence += f" 于 {release_meta['released_at']} 创建"
        overview_parts.append(f"{release_sentence}。")
    lines.append(" ".join(part for part in overview_parts if part).strip())
    lines.append("核心亮点如下：")
    lines.append("")
    if highlights:
        for highlight in highlights:
            lines.append(f"- {highlight}。")
    else:
        lines.append("- 本版本主要聚焦核心功能增强、稳定性修复与交付流程完善。")
    lines.append("")

    render_support_matrix(lines, support_rows)

    lines.append("## 3. 新增特性")
    lines.append("")
    feature_items = sort_items(features)
    if feature_items:
        lines.append("| 序号 | 特性名称 | 特性描述 | 关联Issue/PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, item in enumerate(feature_items, 1):
            title = clean_cell(normalize_title(item.get("title", "")))
            related_issues = find_related_issues(item, issue_index)
            description = clean_cell(describe_feature(item, related_issues))
            lines.append(f"| {index} | {title} | {description} | {combined_links(item, related_issues)} |")
    else:
        lines.append("不涉及。")
    lines.append("")

    lines.append("## 4. 变更说明")
    lines.append("")
    change_items = sort_items(breaking_changes) + sort_items(changes)
    if change_items:
        lines.append("| 序号 | 变更内容 | 变更影响 | 关联Issue/PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, item in enumerate(change_items, 1):
            title = clean_cell(normalize_title(item.get("title", "")))
            impact = describe_breaking_change(item) if item in breaking_changes else describe_change(item)
            related_issues = find_related_issues(item, issue_index)
            lines.append(f"| {index} | {title} | {clean_cell(impact)} | {combined_links(item, related_issues)} |")
    else:
        lines.append("不涉及。")
    lines.append("")

    lines.append("## 5. 修复缺陷")
    lines.append("")
    bugfix_items = sort_items(bugfixes)
    if bugfix_items:
        lines.append("| 序号 | Issue链接 | 问题描述 | 影响范围 |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, item in enumerate(bugfix_items, 1):
            related_issues = find_related_issues(item, issue_index)
            description, scope = describe_bugfix(item, related_issues)
            lines.append(
                f"| {index} | {combined_links(item, related_issues)} | {clean_cell(description)} | {clean_cell(scope)} |"
            )
    else:
        lines.append("不涉及。")
    lines.append("")

    lines.append("## 6. 已知问题")
    lines.append("")
    if known_issues_list:
        lines.append("| 序号 | Issue链接 | 问题描述 | 影响 | 规避措施 | 计划修复版本 |")
        lines.append("| ---- | ---- | ---- | ---- | ---- | ---- |")
        for index, item in enumerate(sort_items(known_issues_list), 1):
            title = clean_cell(normalize_title(item.get("title", "")))
            lines.append(
                f"| {index} | {format_link(item)} | {title} | 相关功能使用场景 | "
                "建议结合 issue 中的临时方案规避 | 后续版本待确认 |"
            )
    else:
        lines.append("不涉及。")
    lines.append("")

    lines.append("## 7. 致谢")
    lines.append("")
    lines.append("感谢以下贡献者对本版本的贡献：")
    lines.append("")
    if contributors:
        lines.append("| 序号 | 贡献者 | 贡献内容 | 关联PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, contributor in enumerate(contributors[:20], 1):
            pr = contributor["pr"]
            title = clean_cell(normalize_title(pr.get("title", "")))
            pr_number = pr.get("number", "")
            pr_url = pr.get("html_url", "")
            lines.append(f"| {index} | @{contributor['login']} | {title} | [!{pr_number}]({pr_url}) |")
    else:
        lines.append("（无数据）")
    lines.append("")

    content = "\n".join(lines)
    with open(output_file, "w", encoding="utf-8") as output_handle:
        output_handle.write(content)

    print(f"\nRelease note 已生成: {output_file}")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="GitCode Release Note Generator")
    parser.add_argument("--output", "-o", required=True, help="输出文件名")
    parser.add_argument("--repo", "-r", required=True, help="仓库链接，如 https://gitcode.com/owner/repo")
    parser.add_argument("--roadmap", "-m", required=True, help="Roadmap issue 链接")
    parser.add_argument("--time-range", "-t", required=True, help="版本时间范围，如 2026Q1、2026-01、2026-01-01:2026-03-31")
    parser.add_argument("--token", "-k", help="GitCode API Token，未传时尝试读取 GITCODE_TOKEN")
    parser.add_argument("--release-url", help="Release 页面参考链接（可选）")
    parser.add_argument("--version", "-v", help="版本号（可选，默认从文件名推断）")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITCODE_TOKEN", "")
    if not token:
        raise SystemExit("缺少 GitCode Token。请通过 --token 传入，或设置环境变量 GITCODE_TOKEN。")

    generate_release_note(
        output_file=args.output,
        repo_url=args.repo,
        roadmap_url=args.roadmap,
        time_range=args.time_range,
        token=token,
        release_url=args.release_url,
        version=args.version,
    )


if __name__ == "__main__":
    main()
