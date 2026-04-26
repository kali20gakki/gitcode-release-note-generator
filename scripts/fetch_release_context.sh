#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
VERBOSE=1

usage() {
  cat <<'EOF'
Usage:
  fetch_release_context.sh \
    --repo https://gitcode.com/owner/repo \
    --roadmap https://gitcode.com/owner/repo/issues/9 \
    --time-range 2026Q1 \
    --output-dir .release-context/msprof-26.0.0 \
    --token <gitcode-token>

Notes:
  - If --token is omitted, reads GITCODE_TOKEN from environment.
  - This script only fetches raw context for LLM summarization.
  - It does NOT generate the final release note markdown.
  - Use --quiet to reduce progress logs.
EOF
}

log() {
  if [[ "${VERBOSE}" -eq 1 ]]; then
    printf '[%s] %s\n' "$SCRIPT_NAME" "$*" >&2
  fi
}

warn() {
  printf '[%s][warn] %s\n' "$SCRIPT_NAME" "$*" >&2
}

fatal() {
  printf '[%s][error] %s\n' "$SCRIPT_NAME" "$*" >&2
  exit 1
}

on_error() {
  local line="$1"
  fatal "Script failed near line ${line}. Check earlier logs for the failing fetch step."
}

trap 'on_error $LINENO' ERR

REPO_URL=""
ROADMAP_URL=""
TIME_RANGE=""
OUTPUT_DIR=""
TOKEN="${GITCODE_TOKEN:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_URL="$2"
      shift 2
      ;;
    --roadmap)
      ROADMAP_URL="$2"
      shift 2
      ;;
    --time-range)
      TIME_RANGE="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --token)
      TOKEN="$2"
      shift 2
      ;;
    --quiet)
      VERBOSE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPO_URL" || -z "$ROADMAP_URL" || -z "$TIME_RANGE" || -z "$OUTPUT_DIR" ]]; then
  echo "Missing required arguments." >&2
  usage >&2
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  fatal "Missing GitCode token. Pass --token or set GITCODE_TOKEN."
fi

command -v curl >/dev/null 2>&1 || fatal "curl is required but was not found in PATH."
command -v sed >/dev/null 2>&1 || fatal "sed is required but was not found in PATH."
command -v awk >/dev/null 2>&1 || fatal "awk is required but was not found in PATH."

parse_repo_url() {
  local url="$1"
  local path
  path="$(printf '%s' "$url" | sed -E 's#https?://[^/]+/##')"
  local owner repo
  owner="$(printf '%s' "$path" | cut -d/ -f1)"
  repo="$(printf '%s' "$path" | cut -d/ -f2)"
  printf '%s %s\n' "$owner" "$repo"
}

parse_issue_url() {
  local url="$1"
  local path
  path="$(printf '%s' "$url" | sed -E 's#https?://[^/]+/##')"
  local owner repo number
  owner="$(printf '%s' "$path" | cut -d/ -f1)"
  repo="$(printf '%s' "$path" | cut -d/ -f2)"
  number="$(printf '%s' "$path" | cut -d/ -f4)"
  printf '%s %s %s\n' "$owner" "$repo" "$number"
}

quarter_range() {
  local year="$1"
  local quarter="$2"
  case "$quarter" in
    1) printf '%s\n%s\n' "$year-01-01" "$year-03-31" ;;
    2) printf '%s\n%s\n' "$year-04-01" "$year-06-30" ;;
    3) printf '%s\n%s\n' "$year-07-01" "$year-09-30" ;;
    4) printf '%s\n%s\n' "$year-10-01" "$year-12-31" ;;
  esac
}

days_in_month() {
  local year="$1"
  local month="$2"
  case "$month" in
    01|03|05|07|08|10|12) printf '31\n' ;;
    04|06|09|11) printf '30\n' ;;
    02)
      if (( (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 )); then
        printf '29\n'
      else
        printf '28\n'
      fi
      ;;
    *)
      echo "Unsupported month: $month" >&2
      exit 1
      ;;
  esac
}

parse_time_range() {
  local value="$1"
  if [[ "$value" =~ ^([0-9]{4})Q([1-4])$ ]]; then
    quarter_range "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi
  if [[ "$value" =~ ^([0-9]{4})-([0-9]{2})$ ]]; then
    local year="${BASH_REMATCH[1]}"
    local month="${BASH_REMATCH[2]}"
    local start="${year}-${month}-01"
    local end
    end="${year}-${month}-$(days_in_month "$year" "$month")"
    printf '%s\n%s\n' "$start" "$end"
    return
  fi
  if [[ "$value" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2}):([0-9]{4}-[0-9]{2}-[0-9]{2})$ ]]; then
    printf '%s\n%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi
  echo "Unsupported time range format: $value" >&2
  exit 1
}

read -r OWNER REPO <<<"$(parse_repo_url "$REPO_URL")"
read -r ROADMAP_OWNER ROADMAP_REPO ROADMAP_NUMBER <<<"$(parse_issue_url "$ROADMAP_URL")"
RANGE_LINES="$(parse_time_range "$TIME_RANGE")"
START_DATE="$(printf '%s\n' "$RANGE_LINES" | sed -n '1p')"
END_DATE="$(printf '%s\n' "$RANGE_LINES" | sed -n '2p')"

mkdir -p "$OUTPUT_DIR/raw" "$OUTPUT_DIR/raw/pr-details" "$OUTPUT_DIR/raw/issue-details" "$OUTPUT_DIR/docs"
RUN_LOG="$OUTPUT_DIR/fetch.log"
: > "$RUN_LOG"

log_and_file() {
  log "$*"
  printf '%s\n' "$*" >> "$RUN_LOG"
}

curl_json() {
  local url="$1"
  local output_file="$2"
  log_and_file "GET $url -> $output_file"
  curl -fsSL \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "User-Agent: gitcode-release-note-generator/llm-workflow" \
    "$url" \
    -o "$output_file"
}

curl_text() {
  local url="$1"
  local output_file="$2"
  log_and_file "GET $url -> $output_file"
  curl -fsSL \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "User-Agent: gitcode-release-note-generator/llm-workflow" \
    "$url" \
    -o "$output_file"
}

fetch_first_text() {
  local output_file="$1"
  shift
  local url
  local tmp_file
  tmp_file="$(mktemp)"
  for url in "$@"; do
    if curl_text "$url" "$tmp_file" 2>/dev/null; then
      mv "$tmp_file" "$output_file"
      log_and_file "Saved text file: $output_file"
      return 0
    fi
  done
  rm -f "$tmp_file"
  warn "Unable to fetch any candidate URL for $output_file"
  return 1
}

fetch_paginated() {
  local base_url="$1"
  local output_file="$2"
  log_and_file "Fetching paginated collection: $base_url"
  : > "$output_file"
  printf '[\n' >> "$output_file"
  local page=1
  local first=1
  while true; do
    local page_file
    page_file="$(mktemp)"
    curl_json "${base_url}&page=${page}&per_page=100" "$page_file"
    local count
    count="$(grep -o '"number"[[:space:]]*:' "$page_file" | wc -l | tr -d ' ')"
    if [[ "$count" == "0" ]]; then
      rm -f "$page_file"
      break
    fi
    local body
    body="$(sed '1d;$d' "$page_file")"
    if [[ -n "$body" ]]; then
      if [[ "$first" -eq 0 ]]; then
        printf ',\n' >> "$output_file"
      fi
      printf '%s' "$body" >> "$output_file"
      first=0
    fi
    rm -f "$page_file"
    if [[ "$count" -lt 100 ]]; then
      break
    fi
    page=$((page + 1))
  done
  printf '\n]\n' >> "$output_file"
  log_and_file "Saved collection: $output_file"
}

extract_numbers() {
  local json_file="$1"
  grep -Eo '"number"[[:space:]]*:[[:space:]]*[0-9]+' "$json_file" \
    | sed -E 's/.*:[[:space:]]*([0-9]+)/\1/' \
    | awk '!seen[$0]++'
}

fetch_detail_set() {
  local kind="$1"
  local numbers_file="$2"
  local detail_dir="$3"
  local api_path="$4"
  local index_file="$5"
  local number
  : > "$index_file"
  log_and_file "Fetching ${kind} detail set from $numbers_file"
  while IFS= read -r number; do
    [[ -z "$number" ]] && continue
    local output_file="${detail_dir}/${kind}-${number}.json"
    if curl_json "${BASE_API}/${api_path}/${number}" "$output_file"; then
      printf '%s\t%s\n' "$number" "$output_file" >> "$index_file"
      log_and_file "Saved ${kind} detail #${number}: $output_file"
    else
      rm -f "$output_file"
      warn "Failed to fetch ${kind} detail #${number}"
    fi
  done < "$numbers_file"
}

require_file() {
  local file_path="$1"
  [[ -f "$file_path" ]] || fatal "Expected file was not created: $file_path"
}

require_nonempty_file() {
  local file_path="$1"
  [[ -s "$file_path" ]] || fatal "Expected non-empty file was not created: $file_path"
}

BASE_API="https://api.gitcode.com/api/v5/repos/${OWNER}/${REPO}"

log_and_file "Starting fetch for ${OWNER}/${REPO} in range ${START_DATE}..${END_DATE}"

fetch_paginated "${BASE_API}/issues?state=all" "$OUTPUT_DIR/raw/issues.json"
fetch_paginated "${BASE_API}/pulls?state=all" "$OUTPUT_DIR/raw/pulls.json"
curl_json "${BASE_API}" "$OUTPUT_DIR/raw/repo.json"
if ! curl_json "${BASE_API}/releases" "$OUTPUT_DIR/raw/releases.json"; then
  warn "Failed to fetch releases; creating empty fallback file."
  printf '[]\n' > "$OUTPUT_DIR/raw/releases.json"
fi
if ! curl_json "${BASE_API}/tags" "$OUTPUT_DIR/raw/tags.json"; then
  warn "Failed to fetch tags; creating empty fallback file."
  printf '[]\n' > "$OUTPUT_DIR/raw/tags.json"
fi
curl_json "https://api.gitcode.com/api/v5/repos/${ROADMAP_OWNER}/${ROADMAP_REPO}/issues/${ROADMAP_NUMBER}" "$OUTPUT_DIR/raw/roadmap.json"

extract_numbers "$OUTPUT_DIR/raw/issues.json" > "$OUTPUT_DIR/raw/issue-numbers.txt"
extract_numbers "$OUTPUT_DIR/raw/pulls.json" > "$OUTPUT_DIR/raw/pr-numbers.txt"

fetch_detail_set "issue" "$OUTPUT_DIR/raw/issue-numbers.txt" "$OUTPUT_DIR/raw/issue-details" "issues" "$OUTPUT_DIR/raw/issue-details/index.txt"
fetch_detail_set "pr" "$OUTPUT_DIR/raw/pr-numbers.txt" "$OUTPUT_DIR/raw/pr-details" "pulls" "$OUTPUT_DIR/raw/pr-details/index.txt"

if [[ "$ROADMAP_OWNER" == "$OWNER" && "$ROADMAP_REPO" == "$REPO" ]]; then
  cp "$OUTPUT_DIR/raw/roadmap.json" "$OUTPUT_DIR/raw/issue-details/issue-${ROADMAP_NUMBER}.json"
fi

RAW_BASE="https://gitcode.com/${OWNER}/${REPO}"
fetch_first_text "$OUTPUT_DIR/docs/README.md" \
  "${RAW_BASE}/raw/master/README.md" \
  "${RAW_BASE}/-/raw/master/README.md" || true
fetch_first_text "$OUTPUT_DIR/docs/install.md" \
  "${RAW_BASE}/raw/master/docs/install.md" \
  "${RAW_BASE}/-/raw/master/docs/install.md" || true
fetch_first_text "$OUTPUT_DIR/docs/quick_start.md" \
  "${RAW_BASE}/raw/master/docs/quick_start.md" \
  "${RAW_BASE}/-/raw/master/docs/quick_start.md" || true
fetch_first_text "$OUTPUT_DIR/docs/msprof_parsing_instruct.md" \
  "${RAW_BASE}/raw/master/docs/msprof_parsing_instruct.md" \
  "${RAW_BASE}/-/raw/master/docs/msprof_parsing_instruct.md" || true
fetch_first_text "$OUTPUT_DIR/docs/msmonitor_parsing_instruct.md" \
  "${RAW_BASE}/raw/master/docs/msmonitor_parsing_instruct.md" \
  "${RAW_BASE}/-/raw/master/docs/msmonitor_parsing_instruct.md" || true

cat > "$OUTPUT_DIR/context-meta.txt" <<EOF
repo_url=$REPO_URL
roadmap_url=$ROADMAP_URL
time_range=$TIME_RANGE
start_date=$START_DATE
end_date=$END_DATE
owner=$OWNER
repo=$REPO
EOF

cat > "$OUTPUT_DIR/raw/detail-index.txt" <<EOF
issues_json=$OUTPUT_DIR/raw/issues.json
pulls_json=$OUTPUT_DIR/raw/pulls.json
roadmap_json=$OUTPUT_DIR/raw/roadmap.json
repo_json=$OUTPUT_DIR/raw/repo.json
releases_json=$OUTPUT_DIR/raw/releases.json
tags_json=$OUTPUT_DIR/raw/tags.json
issue_numbers=$OUTPUT_DIR/raw/issue-numbers.txt
pr_numbers=$OUTPUT_DIR/raw/pr-numbers.txt
issue_details_dir=$OUTPUT_DIR/raw/issue-details
pr_details_dir=$OUTPUT_DIR/raw/pr-details
issue_details_index=$OUTPUT_DIR/raw/issue-details/index.txt
pr_details_index=$OUTPUT_DIR/raw/pr-details/index.txt
EOF

require_nonempty_file "$OUTPUT_DIR/context-meta.txt"
require_nonempty_file "$OUTPUT_DIR/raw/detail-index.txt"
require_file "$OUTPUT_DIR/raw/issues.json"
require_file "$OUTPUT_DIR/raw/pulls.json"
require_file "$OUTPUT_DIR/raw/repo.json"
require_file "$OUTPUT_DIR/raw/roadmap.json"
require_file "$OUTPUT_DIR/raw/issue-numbers.txt"
require_file "$OUTPUT_DIR/raw/pr-numbers.txt"
require_file "$OUTPUT_DIR/raw/issue-details/index.txt"
require_file "$OUTPUT_DIR/raw/pr-details/index.txt"

log_and_file "Fetch completed successfully."
printf 'Fetched release context into: %s\n' "$OUTPUT_DIR"
