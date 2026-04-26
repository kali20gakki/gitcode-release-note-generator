#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import calendar
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


API_BASE = "https://api.gitcode.com/api/v5"
RAW_BASE = "https://gitcode.com"
USER_AGENT = "gitcode-release-note-generator/fetcher"
TEXT_DOC_SUFFIXES = (".md", ".rst", ".txt")
EXCLUDED_DOC_PREFIXES = (
    ".git/",
    ".github/",
    ".gitlab/",
    "third_party/",
    "vendor/",
    "node_modules/",
    "build/",
    "dist/",
)


class FetchError(RuntimeError):
    pass


def log(message: str, *, quiet: bool, log_file: Path | None = None) -> None:
    if not quiet:
        print(f"[fetch_release_context] {message}", file=sys.stderr)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def warn(message: str, *, log_file: Path | None = None) -> None:
    print(f"[fetch_release_context][warn] {message}", file=sys.stderr)
    if log_file is not None:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[warn] {message}\n")


def http_get(url: str, token: str, *, expect_json: bool, quiet: bool, log_file: Path | None = None) -> Any:
    log(f"GET {url}", quiet=quiet, log_file=log_file)
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            body = response.read()
    except HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise FetchError(f"Network error for {url}: {exc}") from exc

    if expect_json:
        return json.loads(body.decode("utf-8"))
    return body.decode("utf-8", errors="replace")


def parse_repo_url(url: str) -> tuple[str, str]:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        raise FetchError(f"Cannot parse repo URL: {url}")
    return parts[0], parts[1]


def parse_issue_url(url: str) -> tuple[str, str, str]:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 4:
        raise FetchError(f"Cannot parse issue URL: {url}")
    return parts[0], parts[1], parts[3]


def parse_time_range(value: str) -> tuple[str, str]:
    quarter_match = re.match(r"^(\d{4})Q([1-4])$", value, re.I)
    if quarter_match:
        year = int(quarter_match.group(1))
        quarter = int(quarter_match.group(2))
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        return (
            f"{year}-{start_month:02d}-01",
            f"{year}-{end_month:02d}-{calendar.monthrange(year, end_month)[1]:02d}",
        )

    month_match = re.match(r"^(\d{4})-(\d{2})$", value)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        return (
            f"{year}-{month:02d}-01",
            f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}",
        )

    range_match = re.match(r"^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$", value)
    if range_match:
        return range_match.group(1), range_match.group(2)

    raise FetchError(f"Unsupported time range format: {value}")


def parse_iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_end_date(value: str) -> datetime:
    dt = parse_iso_datetime(value)
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def in_time_range(item: dict[str, Any], start: str, end: str, field: str = "created_at") -> bool:
    timestamp = item.get(field)
    if not timestamp:
        return False
    try:
        item_dt = parse_iso_datetime(str(timestamp))
    except ValueError:
        return False
    return parse_iso_datetime(start) <= item_dt <= normalize_end_date(end)


def fetch_paginated(path: str, token: str, *, quiet: bool, log_file: Path | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API_BASE}{path}&page={page}&per_page=100"
        data = http_get(url, token, expect_json=True, quiet=quiet, log_file=log_file)
        if not isinstance(data, list):
            raise FetchError(f"Expected list payload from {url}")
        items.extend(data)
        if len(data) < 100:
            break
        page += 1
        if page > 100:
            break
    return items


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)


def fetch_optional_json(url: str, token: str, *, quiet: bool, log_file: Path | None = None) -> Any:
    try:
        return http_get(url, token, expect_json=True, quiet=quiet, log_file=log_file)
    except FetchError as exc:
        warn(str(exc), log_file=log_file)
        return []


def fetch_repo_tree(owner: str, repo: str, ref: str, token: str, *, quiet: bool, log_file: Path | None = None) -> dict[str, Any]:
    url = f"{API_BASE}/repos/{owner}/{repo}/git/trees/{quote(ref)}?recursive=1&per_page=100"
    payload = http_get(url, token, expect_json=True, quiet=quiet, log_file=log_file)
    if not isinstance(payload, dict):
        raise FetchError(f"Unexpected tree payload for {owner}/{repo}@{ref}")
    return payload


def score_doc_path(path: str) -> int:
    score = 0
    lowered = path.lower()
    if lowered.startswith("docs/") or lowered.startswith("doc/"):
        score += 5
    if lowered.count("/") <= 1:
        score += 3
    if any(keyword in lowered for keyword in ["readme", "install", "quick", "guide", "getting", "start", "release", "change", "note", "parse", "profil", "monitor"]):
        score += 4
    if lowered.endswith(".md"):
        score += 2
    return score


def select_doc_paths(tree_payload: dict[str, Any], *, max_docs: int = 40) -> list[str]:
    tree_items = tree_payload.get("tree", [])
    if not isinstance(tree_items, list):
        return []

    candidates: list[str] = []
    for item in tree_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        lowered = path.lower()
        if not path or not lowered.endswith(TEXT_DOC_SUFFIXES):
            continue
        if any(lowered.startswith(prefix) for prefix in EXCLUDED_DOC_PREFIXES):
            continue
        if lowered.startswith("docs/") or lowered.startswith("doc/") or path.count("/") <= 1:
            candidates.append(path)

    ranked = sorted(set(candidates), key=lambda value: (-score_doc_path(value), value.lower()))
    return ranked[:max_docs]


def fetch_content_file(
    owner: str,
    repo: str,
    path: str,
    ref: str,
    token: str,
    *,
    quiet: bool,
    log_file: Path | None = None,
) -> str:
    encoded_path = "/".join(quote(part) for part in path.split("/"))
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{encoded_path}?ref={quote(ref)}"
    payload = http_get(url, token, expect_json=True, quiet=quiet, log_file=log_file)
    if not isinstance(payload, dict):
        raise FetchError(f"Unexpected contents payload for {path}")
    if payload.get("type") != "file":
        raise FetchError(f"Path is not a file: {path}")
    content = payload.get("content", "")
    encoding = str(payload.get("encoding") or "").lower()
    if not isinstance(content, str) or encoding != "base64":
        raise FetchError(f"Unsupported content encoding for {path}: {encoding}")
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Failed to decode content for {path}: {exc}") from exc


def extract_numbers(items: list[dict[str, Any]]) -> list[int]:
    seen: set[int] = set()
    numbers: list[int] = []
    for item in items:
        number = item.get("number")
        if isinstance(number, int) and number not in seen:
            seen.add(number)
            numbers.append(number)
    return numbers


def extract_linked_issue_numbers(roadmap_payload: dict[str, Any]) -> list[int]:
    text = json.dumps(roadmap_payload, ensure_ascii=False)
    numbers = {int(match) for match in re.findall(r"/issues/(\d+)", text)}
    roadmap_number = roadmap_payload.get("number")
    if isinstance(roadmap_number, int) and roadmap_number in numbers:
        numbers.remove(roadmap_number)
    return sorted(numbers)


def extract_linked_pull_numbers(roadmap_payload: dict[str, Any]) -> list[int]:
    text = json.dumps(roadmap_payload, ensure_ascii=False)
    numbers = {int(match) for match in re.findall(r"/(?:merge_requests|pulls)/(\d+)", text)}
    return sorted(numbers)


def fetch_detail_set(
    numbers: list[int],
    *,
    owner: str,
    repo: str,
    api_segment: str,
    kind: str,
    token: str,
    detail_dir: Path,
    quiet: bool,
    log_file: Path | None = None,
) -> list[dict[str, Any]]:
    detail_dir.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    for number in numbers:
        url = f"{API_BASE}/repos/{owner}/{repo}/{api_segment}/{number}"
        try:
            payload = http_get(url, token, expect_json=True, quiet=quiet, log_file=log_file)
        except FetchError as exc:
            warn(f"Failed to fetch {kind} #{number}: {exc}", log_file=log_file)
            continue
        output_path = detail_dir / f"{kind}-{number}.json"
        write_json(output_path, payload)
        index_rows.append({"number": number, "path": str(output_path)})
    write_json(detail_dir / "index.json", index_rows)
    write_text(
        detail_dir / "index.txt",
        "".join(f"{row['number']}\t{row['path']}\n" for row in index_rows),
    )
    return index_rows


def ensure_nonempty(path: Path) -> None:
    if not path.exists():
        raise FetchError(f"Expected file was not created: {path}")
    if path.is_file() and path.stat().st_size == 0:
        raise FetchError(f"Expected non-empty file was not created: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GitCode release context for LLM summarization.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--roadmap", required=True)
    parser.add_argument("--time-range", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--token", default=os.environ.get("GITCODE_TOKEN", ""))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("[fetch_release_context.py][error] Missing GitCode token. Pass --token or set GITCODE_TOKEN.")

    owner, repo = parse_repo_url(args.repo)
    roadmap_owner, roadmap_repo, roadmap_number = parse_issue_url(args.roadmap)
    start_date, end_date = parse_time_range(args.time_range)

    output_dir = Path(args.output_dir)
    raw_dir = output_dir / "raw"
    docs_dir = output_dir / "docs"
    pr_detail_dir = raw_dir / "pr-details"
    issue_detail_dir = raw_dir / "issue-details"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "fetch.log"
    write_text(log_file, "")

    log(f"Starting fetch for {owner}/{repo} in range {start_date}..{end_date}", quiet=args.quiet, log_file=log_file)

    issues_all = fetch_paginated(f"/repos/{owner}/{repo}/issues?state=all", args.token, quiet=args.quiet, log_file=log_file)
    pulls_all = fetch_paginated(f"/repos/{owner}/{repo}/pulls?state=all", args.token, quiet=args.quiet, log_file=log_file)
    issues_in_range = [item for item in issues_all if in_time_range(item, start_date, end_date)]
    pulls_in_range = [item for item in pulls_all if in_time_range(item, start_date, end_date)]

    repo_payload = http_get(f"{API_BASE}/repos/{owner}/{repo}", args.token, expect_json=True, quiet=args.quiet, log_file=log_file)
    roadmap_payload = http_get(
        f"{API_BASE}/repos/{roadmap_owner}/{roadmap_repo}/issues/{roadmap_number}",
        args.token,
        expect_json=True,
        quiet=args.quiet,
        log_file=log_file,
    )
    releases_payload = fetch_optional_json(f"{API_BASE}/repos/{owner}/{repo}/releases", args.token, quiet=args.quiet, log_file=log_file)
    tags_payload = fetch_optional_json(f"{API_BASE}/repos/{owner}/{repo}/tags", args.token, quiet=args.quiet, log_file=log_file)

    write_json(raw_dir / "issues.all.json", issues_all)
    write_json(raw_dir / "pulls.all.json", pulls_all)
    write_json(raw_dir / "issues.json", issues_in_range)
    write_json(raw_dir / "pulls.json", pulls_in_range)
    write_json(raw_dir / "repo.json", repo_payload)
    write_json(raw_dir / "roadmap.json", roadmap_payload)
    write_json(raw_dir / "releases.json", releases_payload)
    write_json(raw_dir / "tags.json", tags_payload)

    issue_numbers = extract_numbers(issues_in_range)
    pull_numbers = extract_numbers(pulls_in_range)
    roadmap_issue_numbers = extract_linked_issue_numbers(roadmap_payload)
    roadmap_pull_numbers = extract_linked_pull_numbers(roadmap_payload)

    issue_detail_numbers = sorted({*issue_numbers, *roadmap_issue_numbers, int(roadmap_number)})
    pull_detail_numbers = sorted({*pull_numbers, *roadmap_pull_numbers})

    write_text(raw_dir / "issue-numbers.txt", "".join(f"{number}\n" for number in issue_numbers))
    write_text(raw_dir / "pr-numbers.txt", "".join(f"{number}\n" for number in pull_numbers))
    write_text(raw_dir / "roadmap-linked-issue-numbers.txt", "".join(f"{number}\n" for number in roadmap_issue_numbers))
    write_text(raw_dir / "roadmap-linked-pr-numbers.txt", "".join(f"{number}\n" for number in roadmap_pull_numbers))

    issue_index_rows = fetch_detail_set(
        issue_detail_numbers,
        owner=owner,
        repo=repo,
        api_segment="issues",
        kind="issue",
        token=args.token,
        detail_dir=issue_detail_dir,
        quiet=args.quiet,
        log_file=log_file,
    )
    pull_index_rows = fetch_detail_set(
        pull_detail_numbers,
        owner=owner,
        repo=repo,
        api_segment="pulls",
        kind="pr",
        token=args.token,
        detail_dir=pr_detail_dir,
        quiet=args.quiet,
        log_file=log_file,
    )

    default_branch = str(repo_payload.get("default_branch") or "master")
    docs_index_rows: list[dict[str, str | int]] = []
    try:
        tree_payload = fetch_repo_tree(owner, repo, default_branch, args.token, quiet=args.quiet, log_file=log_file)
        write_json(raw_dir / "tree.json", tree_payload)
        doc_paths = select_doc_paths(tree_payload)
        write_text(raw_dir / "doc-paths.txt", "".join(f"{path}\n" for path in doc_paths))
        for doc_path in doc_paths:
            try:
                content = fetch_content_file(owner, repo, doc_path, default_branch, args.token, quiet=args.quiet, log_file=log_file)
            except FetchError as exc:
                warn(str(exc), log_file=log_file)
                continue
            output_name = doc_path.replace("/", "__")
            output_path = docs_dir / output_name
            write_text(output_path, content)
            docs_index_rows.append(
                {
                    "repo_path": doc_path,
                    "local_path": str(output_path),
                    "score": score_doc_path(doc_path),
                }
            )
    except FetchError as exc:
        warn(f"Unable to inspect repository tree for docs: {exc}", log_file=log_file)

    write_json(docs_dir / "index.json", docs_index_rows)
    write_text(
        docs_dir / "index.txt",
        "".join(f"{row['repo_path']}\t{row['local_path']}\t{row['score']}\n" for row in docs_index_rows),
    )

    write_text(
        output_dir / "context-meta.txt",
        "\n".join(
            [
                f"repo_url={args.repo}",
                f"roadmap_url={args.roadmap}",
                f"time_range={args.time_range}",
                f"start_date={start_date}",
                f"end_date={end_date}",
                f"owner={owner}",
                f"repo={repo}",
                f"default_branch={default_branch}",
            ]
        )
        + "\n",
    )

    detail_index = {
        "issues_all_json": str(raw_dir / "issues.all.json"),
        "pulls_all_json": str(raw_dir / "pulls.all.json"),
        "issues_in_range_json": str(raw_dir / "issues.json"),
        "pulls_in_range_json": str(raw_dir / "pulls.json"),
        "roadmap_json": str(raw_dir / "roadmap.json"),
        "repo_json": str(raw_dir / "repo.json"),
        "releases_json": str(raw_dir / "releases.json"),
        "tags_json": str(raw_dir / "tags.json"),
        "issue_numbers": str(raw_dir / "issue-numbers.txt"),
        "pr_numbers": str(raw_dir / "pr-numbers.txt"),
        "roadmap_linked_issue_numbers": str(raw_dir / "roadmap-linked-issue-numbers.txt"),
        "roadmap_linked_pr_numbers": str(raw_dir / "roadmap-linked-pr-numbers.txt"),
        "issue_details_dir": str(issue_detail_dir),
        "pr_details_dir": str(pr_detail_dir),
        "issue_details_index": str(issue_detail_dir / "index.txt"),
        "pr_details_index": str(pr_detail_dir / "index.txt"),
        "docs_dir": str(docs_dir),
        "docs_index": str(docs_dir / "index.txt"),
        "tree_json": str(raw_dir / "tree.json"),
        "doc_paths": str(raw_dir / "doc-paths.txt"),
        "fetch_log": str(log_file),
    }
    write_json(raw_dir / "detail-index.json", detail_index)
    write_text(
        raw_dir / "detail-index.txt",
        "".join(f"{key}={value}\n" for key, value in detail_index.items()),
    )

    summary = {
        "issue_total": len(issues_all),
        "issue_in_range": len(issues_in_range),
        "pull_total": len(pulls_all),
        "pull_in_range": len(pulls_in_range),
        "issue_detail_count": len(issue_index_rows),
        "pull_detail_count": len(pull_index_rows),
        "roadmap_linked_issue_count": len(roadmap_issue_numbers),
        "roadmap_linked_pull_count": len(roadmap_pull_numbers),
    }
    write_json(output_dir / "summary.json", summary)

    for required in [
        output_dir / "context-meta.txt",
        raw_dir / "issues.all.json",
        raw_dir / "pulls.all.json",
        raw_dir / "issues.json",
        raw_dir / "pulls.json",
        raw_dir / "repo.json",
        raw_dir / "roadmap.json",
        raw_dir / "detail-index.txt",
        raw_dir / "issue-numbers.txt",
        raw_dir / "pr-numbers.txt",
        issue_detail_dir / "index.txt",
        pr_detail_dir / "index.txt",
    ]:
        ensure_nonempty(required)

    log("Fetch completed successfully.", quiet=args.quiet, log_file=log_file)
    print(f"Fetched release context into: {output_dir}")


if __name__ == "__main__":
    main()
