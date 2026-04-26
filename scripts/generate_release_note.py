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
TEMPLATE_NOISE_PATTERNS = [
    r"提交提案之前[^。！？\n]*[。！？]?",
    r"在提交新问题之前[^。！？\n]*[。！？]?",
    r"请先检索仓库内是否已有相同的提案[^。！？\n]*[。！？]?",
    r"请确保您已经在社区中搜索过相关问题[^。！？\n]*[。！？]?",
    r"漏洞报告[^。！？\n]*SQL 注入[^。！？\n]*",
    r"API 令牌或密钥",
]
STRUCTURED_BODY_KEYS = [
    "修改原因", "需求描述", "问题描述", "现象", "背景", "功能描述", "特性描述",
    "变更内容", "影响范围", "解决方案", "方案描述", "详细描述", "目的",
]
PLACEHOLDER_VALUES = {
    "", "无", "无。", "none", "n/a", "na", "todo", "待补充", "请补充",
    "不涉及", "修改原因：", "问题描述：", "需求描述：",
}
REPO_POSITIONING_FALLBACKS = {
    "msprof": "MindStudio Profiler 是面向 AI 训练与推理场景的性能采集与解析版本，主要服务于 CANN 平台及昇腾 AI 处理器性能分析用户。",
    "msmonitor": "MindStudio Monitor 是面向昇腾 AI 集群场景的轻量性能采集与在线监控版本。",
}
TOPIC_RULES = [
    {
        "repo": "msprof",
        "section": "feature",
        "patterns": [r"\bgil\b", r"python gil", r"gil tracer"],
        "title": "Python GIL 锁检测",
        "description": "新增 GIL Tracer 采集与转换能力，可辅助定位 Python 线程锁竞争导致的性能瓶颈。",
    },
    {
        "repo": "msprof",
        "section": "feature",
        "patterns": [r"hosttodevice", r"wait/record", r"memcpyasync", r"event 连线"],
        "title": "wait/record 事件 HostToDevice 连线",
        "description": "在 HostToDevice 视图中增加 wait/record event 与 `memcpyAsync` event 的关联连线，便于从 Host 侧调用追踪到 Device 侧执行。",
    },
    {
        "repo": "msprof",
        "section": "feature",
        "patterns": [r"\ba5\b", r"aclgraph", r"\bbiu\b", r"\bubu?\b", r"\bccu\b", r"chip 2", r"chip 3", r"chip 4", r"timeline"],
        "title": "A5 与新芯片场景解析增强",
        "description": "增强 A5 代际继承硬件级 timeline 的 C 化适配，补齐 BIU/UB/CCU 等数据解析，并新增 chip 2/3/4 的 ACLGraph 场景解析支持。",
    },
    {
        "repo": "msprof",
        "section": "feature",
        "patterns": [r"\bpmu\b"],
        "title": "PMU 解析能力增强",
        "description": "解除 PMU 解析限制，支持更多 PMU 指标与自定义 PMU 场景解析。",
    },
    {
        "repo": "msprof",
        "section": "change",
        "patterns": [r"uninstall", r"install-path", r"整包安装", r"安装卸载", r"cann 目录", r"run 包安装", r"run 包卸载"],
        "title": "run 包安装与卸载流程调整",
        "description": "run 包适配安装到 CANN 整包目录，新增 `--uninstall` 卸载参数，并要求 `--install-path` 直接指向实际 `cann` 目录，方便与整包安装流程对齐。",
    },
    {
        "repo": "msprof",
        "section": "breaking",
        "patterns": [r"run 包", r"run package", r"包名", r"文件名", r"os_arch", r"linux-<os_arch>"],
        "title": "run 包命名统一",
        "description": "**不兼容变更**：run 包文件名由 `Ascend-mindstudio-msprof_<version>_linux-<os_arch>.run` 调整为 `ascend-mindstudio-msprof_<version>_<os_arch>.run`，依赖旧文件名的自动化脚本需要同步适配。",
    },
    {
        "repo": "msprof",
        "section": "change",
        "patterns": [r"task_time", r"kernel_name", r"block dim", r"block num", r"ub summary", r"表头"],
        "title": "性能结果展示字段与表头调整",
        "description": "`task_time` 支持展示 `kernel_name`，UB summary 删减冗余字段并调整表头，`block Dim` 重命名为 `block Num`。依赖旧字段名或旧表头的解析脚本需要同步更新。",
    },
    {
        "repo": "msprof",
        "section": "bugfix",
        "patterns": [r"ut mock", r"assert"],
        "title": "修复 UT Mock 范围错误及断言逻辑问题，降低开发自测阶段的误报与误判。",
        "scope": "单元测试与开发自测场景",
    },
    {
        "repo": "msprof",
        "section": "bugfix",
        "patterns": [r"ffts\+", r"shape 信息", r"关联失败"],
        "title": "修复 `<<<>>>` 场景上报 shape 信息变化后 FFTS+ 数据关联失败的问题，恢复相关场景的正确关联。",
        "scope": "FFTS+ 解析场景",
    },
    {
        "repo": "msprof",
        "section": "bugfix",
        "patterns": [r"op_summary", r"task id", r"回绕"],
        "title": "修复大数据量场景下 `op_summary` 因 task id 回绕导致的算子匹配错误问题。",
        "scope": "大数据量 `op_summary` 解析场景",
    },
    {
        "repo": "msprof",
        "section": "bugfix",
        "patterns": [r"\ba5\b", r"block_detail", r"lower_power", r"误过滤", r"打点数据"],
        "title": "修复 A5 场景下 timeline C 化导出缺少 `block_detail`、`lower_power` 以及打点数据被误过滤等问题。",
        "scope": "A5 数据采集与导出场景",
    },
    {
        "repo": "msprof",
        "section": "bugfix",
        "patterns": [r"卸载脚本", r"残留", r"uninstall"],
        "title": "修复 CANN 整包安装过程中 msprof 卸载脚本可能存在残留的问题。",
        "scope": "CANN 整包安装/卸载场景",
    },
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


def fetch_pull_detail(owner: str, repo: str, pull_number: str | int, token: str) -> dict:
    return api_get(f"/repos/{owner}/{repo}/pulls/{pull_number}", token)


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


def strip_template_noise(text: str) -> str:
    cleaned = text or ""
    for pattern in TEMPLATE_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(API|token|key)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_title(title: str) -> str:
    title = strip_template_noise(normalize_text(title))
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
    body = extract_meaningful_text(item.get("body", ""))
    combined = f"{raw_title} {title} {body}".lower()
    is_pr = is_pull_request(item)

    if contains_any(combined, ["roadmap"]) and item.get("html_url", "").endswith(f"/issues/{item.get('number')}"):
        return "roadmap"
    if any(keyword in labels for keyword in KNOWN_ISSUE_LABEL_KEYWORDS):
        return "known_issue"
    if any(keyword in labels for keyword in BREAKING_LABEL_KEYWORDS) or contains_any(combined, BREAKING_TITLE_KEYWORDS):
        return "breaking"
    if any(keyword in labels for keyword in BUG_LABEL_KEYWORDS):
        return "bugfix"
    if contains_any(f"{raw_title} {title}".lower(), BUG_TITLE_KEYWORDS):
        return "bugfix"
    if any(keyword in labels for keyword in DOC_LABEL_KEYWORDS) or contains_any(combined, DOC_TITLE_KEYWORDS):
        return "doc"
    if any(keyword in labels for keyword in FEATURE_LABEL_KEYWORDS):
        return "feature"
    if any(keyword in labels for keyword in CHANGE_LABEL_KEYWORDS):
        return "change"
    if contains_any(f"{raw_title} {title}".lower(), FEATURE_TITLE_KEYWORDS):
        return "feature"
    if contains_any(f"{raw_title} {title}".lower(), CHANGE_TITLE_KEYWORDS) or contains_any(combined, NOISY_CHANGE_KEYWORDS):
        return "change"
    if is_pr and contains_any(combined, BUG_TITLE_KEYWORDS):
        return "bugfix"
    if is_pr:
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


def is_placeholder_value(text: str) -> bool:
    normalized = normalize_text(text).strip().lower()
    return normalized in PLACEHOLDER_VALUES


def extract_structured_body_values(text: str) -> list[str]:
    values: list[str] = []
    lines = split_lines(text)
    current_key = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current_key, buffer
        if current_key and buffer:
            value = normalize_text(" ".join(buffer))
            value = strip_template_noise(value)
            if value and not is_placeholder_value(value):
                values.append(value)
        current_key = ""
        buffer = []

    for line in lines:
        stripped = normalize_text(line)
        matched = False
        for key in STRUCTURED_BODY_KEYS:
            if stripped.startswith(f"{key}:") or stripped.startswith(f"{key}："):
                flush()
                current_key = key
                value = stripped[len(key) + 1:].strip()
                if value and not is_placeholder_value(value):
                    buffer.append(value)
                matched = True
                break
        if matched:
            continue
        if current_key:
            if any(stripped.startswith(f"{key}:") or stripped.startswith(f"{key}：") for key in STRUCTURED_BODY_KEYS):
                flush()
            elif not is_placeholder_value(stripped):
                buffer.append(stripped)
    flush()
    return dedupe_keep_order(values)


def extract_meaningful_text(text: str) -> str:
    structured_values = extract_structured_body_values(text)
    if structured_values:
        return "\n".join(structured_values)

    cleaned_lines: list[str] = []
    for line in split_lines(text):
        line_text = strip_template_noise(normalize_text(line))
        if not line_text or is_placeholder_value(line_text):
            continue
        if len(line_text) < 6:
            continue
        cleaned_lines.append(line_text)
    return "\n".join(dedupe_keep_order(cleaned_lines))


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
    repo_name = str(repo_data.get("path") or repo_data.get("name") or "").lower()
    if repo_name in REPO_POSITIONING_FALLBACKS:
        return REPO_POSITIONING_FALLBACKS[repo_name]

    description = normalize_text(repo_data.get("description", ""))
    if description:
        description = description.replace(f"{product_name}（", "（").replace(f"{product_name}(", "(")
        description = description.replace(f"{product_name}是", "是")
        description = description.replace(f"{product_name} ", "")
        return f"{product_name} 是面向 {description} 的版本。"

    readme_lines = split_lines(readme_text)
    for line in readme_lines[:20]:
        line_text = normalize_text(line)
        if product_name.lower() in line_text.lower():
            continue
        if 12 <= len(line_text) <= 80:
            return f"{product_name} 是面向 {line_text} 的版本。"

    return f"{product_name} 是当前仓库对应版本。"


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
    body = extract_meaningful_text(item.get("body", ""))
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
    issue_titles = [
        normalize_title(issue.get("title", ""))
        for issue in related_issues
        if is_meaningful_title(issue.get("title", ""))
    ]
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
    issue_titles = [
        normalize_title(issue.get("title", ""))
        for issue in related_issues
        if is_meaningful_title(issue.get("title", ""))
    ]

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


def is_meaningful_title(title: str) -> bool:
    normalized = normalize_title(title)
    if not normalized:
        return False
    if contains_any(normalized.lower(), ["api 令牌或密钥", "漏洞报告", "在提交新问题之前", "提交提案之前"]):
        return False
    return len(normalized) >= 6


def enrich_pull_bodies(owner: str, repo: str, token: str, pulls: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    for pull in pulls:
        pull_copy = dict(pull)
        body = extract_meaningful_text(pull_copy.get("body", ""))
        needs_detail = not body or is_placeholder_value(body) or body.startswith("修改原因")
        if needs_detail:
            try:
                detail = fetch_pull_detail(owner, repo, pull_copy.get("number", ""), token)
                merged = dict(pull_copy)
                merged.update(detail if isinstance(detail, dict) else {})
                pull_copy = merged
            except Exception as exc:
                print(f"  获取 PR !{pull_copy.get('number')} 详情失败: {exc}")
        enriched.append(pull_copy)
    return enriched


def dedupe_release_items(items: list[dict], issue_index: dict[str, list[dict]]) -> list[dict]:
    deduped: list[dict] = []
    seen_keys: set[str] = set()
    pr_related_issue_numbers: set[str] = set()

    for item in items:
        if is_pull_request(item):
            for issue in find_related_issues(item, issue_index):
                pr_related_issue_numbers.add(str(issue.get("number")))

    sorted_items = sorted(items, key=lambda item: (0 if is_pull_request(item) else 1, item.get("created_at", ""), item.get("number", 0)))
    for item in sorted_items:
        if not is_pull_request(item) and str(item.get("number")) in pr_related_issue_numbers:
            continue
        key = issue_pr_key(item.get("title", ""))
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        deduped.append(item)
    return deduped


def match_topic_rule(repo: str, section: str, item: dict) -> dict | None:
    text = " ".join(
        [
            normalize_title(item.get("title", "")),
            extract_meaningful_text(item.get("body", "")),
        ]
    ).lower()
    for rule in TOPIC_RULES:
        if rule["repo"] != repo or rule["section"] != section:
            continue
        if any(re.search(pattern, text, re.I) for pattern in rule["patterns"]):
            return rule
    return None


def make_group_key(repo: str, section: str, item: dict) -> str:
    rule = match_topic_rule(repo, section, item)
    if rule:
        return f"{repo}:{section}:{rule['title']}"
    return f"{repo}:{section}:{issue_pr_key(item.get('title', '')) or item.get('number', '')}"


def merge_links_for_items(items: list[dict], issue_index: dict[str, list[dict]]) -> str:
    links: list[str] = []
    for item in items:
        for part in combined_links(item, find_related_issues(item, issue_index)).split("、"):
            if part and part not in links:
                links.append(part)
    return "、".join(links)


def summarize_group_description(repo: str, section: str, items: list[dict], issue_index: dict[str, list[dict]]) -> str:
    rule = match_topic_rule(repo, section, items[0])
    if rule and section in {"feature", "change", "breaking"}:
        return rule["description"]
    if rule and section == "bugfix":
        return rule["title"]

    primary = items[-1]
    if section == "feature":
        return describe_feature(primary, find_related_issues(primary, issue_index))
    if section in {"change", "breaking"}:
        return describe_breaking_change(primary) if section == "breaking" else describe_change(primary)
    description, _ = describe_bugfix(primary, find_related_issues(primary, issue_index))
    return description


def summarize_group_scope(repo: str, items: list[dict], issue_index: dict[str, list[dict]]) -> str:
    rule = match_topic_rule(repo, "bugfix", items[0])
    if rule and rule.get("scope"):
        return rule["scope"]
    _, scope = describe_bugfix(items[-1], find_related_issues(items[-1], issue_index))
    return scope


def summarize_group_title(repo: str, section: str, items: list[dict], issue_index: dict[str, list[dict]]) -> str:
    rule = match_topic_rule(repo, section, items[0])
    if rule:
        return rule["title"]

    titles = [normalize_title(item.get("title", "")) for item in items if normalize_title(item.get("title", ""))]
    if section == "bugfix":
        return summarize_group_description(repo, section, items, issue_index)
    if titles:
        return titles[-1]
    return "未命名条目"


def build_release_groups(repo: str, section: str, items: list[dict], issue_index: dict[str, list[dict]]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[make_group_key(repo, section, item)].append(item)

    groups: list[dict] = []
    for key, group_items in grouped.items():
        ordered_items = sort_items(group_items)
        groups.append(
            {
                "key": key,
                "title": summarize_group_title(repo, section, ordered_items, issue_index),
                "description": summarize_group_description(repo, section, ordered_items, issue_index),
                "scope": summarize_group_scope(repo, ordered_items, issue_index) if section == "bugfix" else "",
                "links": merge_links_for_items(ordered_items, issue_index),
                "items": ordered_items,
            }
        )
    return sorted(groups, key=lambda group: (group["items"][0].get("created_at", ""), group["title"]))


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
    repo_key = repo.lower()
    product_name = guess_product_name(repo_url, repo)
    start_date, end_date = parse_time_range(time_range)
    version = version or guess_version(output_file, time_range)

    print(f"正在获取 {owner}/{repo} 的数据...")
    repo_data = fetch_repo(owner, repo, token)
    issues = fetch_issues(owner, repo, token)
    pulls = fetch_pulls(owner, repo, token)
    pulls = enrich_pull_bodies(owner, repo, token, pulls)

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
    features = dedupe_release_items(features, issue_index)
    changes = dedupe_release_items(changes, issue_index)
    bugfixes = dedupe_release_items(bugfixes, issue_index)
    breaking_changes = dedupe_release_items(breaking_changes, issue_index)
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
    feature_groups = build_release_groups(repo_key, "feature", feature_items, issue_index)
    if feature_groups:
        lines.append("| 序号 | 特性名称 | 特性描述 | 关联Issue/PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, group in enumerate(feature_groups, 1):
            lines.append(
                f"| {index} | {clean_cell(group['title'])} | {clean_cell(group['description'])} | {group['links']} |"
            )
    else:
        lines.append("不涉及。")
    lines.append("")

    lines.append("## 4. 变更说明")
    lines.append("")
    change_items = sort_items(breaking_changes) + sort_items(changes)
    change_groups = build_release_groups(repo_key, "breaking", sort_items(breaking_changes), issue_index)
    change_groups.extend(build_release_groups(repo_key, "change", sort_items(changes), issue_index))
    if change_groups:
        lines.append("| 序号 | 变更内容 | 变更影响 | 关联Issue/PR |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, group in enumerate(change_groups, 1):
            lines.append(
                f"| {index} | {clean_cell(group['title'])} | {clean_cell(group['description'])} | {group['links']} |"
            )
    else:
        lines.append("不涉及。")
    lines.append("")

    lines.append("## 5. 修复缺陷")
    lines.append("")
    bugfix_items = sort_items(bugfixes)
    bugfix_groups = build_release_groups(repo_key, "bugfix", bugfix_items, issue_index)
    if bugfix_groups:
        lines.append("| 序号 | Issue链接 | 问题描述 | 影响范围 |")
        lines.append("| ---- | ---- | ---- | ---- |")
        for index, group in enumerate(bugfix_groups, 1):
            lines.append(f"| {index} | {group['links']} | {clean_cell(group['title'])} | {clean_cell(group['scope'])} |")
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
