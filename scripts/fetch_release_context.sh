#!/usr/bin/env bash
set -euo pipefail

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
EOF
}

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
  echo "Missing GitCode token. Pass --token or set GITCODE_TOKEN." >&2
  exit 1
fi

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

parse_time_range() {
  local value="$1"
  if [[ "$value" =~ ^([0-9]{4})Q([1-4])$ ]]; then
    quarter_range "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi
  if [[ "$value" =~ ^([0-9]{4})-([0-9]{2})$ ]]; then
    local year="${BASH_REMATCH[1]}"
    local month="${BASH_REMATCH[2]}"
    local next_month next_year
    next_month=$((10#$month + 1))
    next_year="$year"
    if [[ "$next_month" -eq 13 ]]; then
      next_month=1
      next_year=$((year + 1))
    fi
    local start="${year}-${month}-01"
    local end
    end="$(date -j -v+1m -f "%Y-%m-%d" "${year}-${month}-01" "+%Y-%m-01" 2>/dev/null | xargs -I{} date -j -v-1d -f "%Y-%m-%d" "{}" "+%Y-%m-%d" 2>/dev/null || true)"
    if [[ -z "$end" ]]; then
      case "$month" in
        01|03|05|07|08|10|12) end="${year}-${month}-31" ;;
        04|06|09|11) end="${year}-${month}-30" ;;
        02)
          if (( (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 )); then
            end="${year}-${month}-29"
          else
            end="${year}-${month}-28"
          fi
          ;;
      esac
    fi
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
mapfile -t RANGE_LINES < <(parse_time_range "$TIME_RANGE")
START_DATE="${RANGE_LINES[0]}"
END_DATE="${RANGE_LINES[1]}"

mkdir -p "$OUTPUT_DIR/raw" "$OUTPUT_DIR/docs"

curl_json() {
  local url="$1"
  local output_file="$2"
  curl -fsSL \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "User-Agent: gitcode-release-note-generator/llm-workflow" \
    "$url" \
    -o "$output_file"
}

curl_text() {
  local url="$1"
  local output_file="$2"
  if ! curl -fsSL \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "User-Agent: gitcode-release-note-generator/llm-workflow" \
    "$url" \
    -o "$output_file"; then
    rm -f "$output_file"
  fi
}

fetch_paginated() {
  local base_url="$1"
  local output_file="$2"
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
}

BASE_API="https://api.gitcode.com/api/v5/repos/${OWNER}/${REPO}"

fetch_paginated "${BASE_API}/issues?state=all" "$OUTPUT_DIR/raw/issues.json"
fetch_paginated "${BASE_API}/pulls?state=all" "$OUTPUT_DIR/raw/pulls.json"
curl_json "${BASE_API}" "$OUTPUT_DIR/raw/repo.json"
curl_json "${BASE_API}/releases" "$OUTPUT_DIR/raw/releases.json" || true
curl_json "${BASE_API}/tags" "$OUTPUT_DIR/raw/tags.json" || true
curl_json "https://api.gitcode.com/api/v5/repos/${ROADMAP_OWNER}/${ROADMAP_REPO}/issues/${ROADMAP_NUMBER}" "$OUTPUT_DIR/raw/roadmap.json"

RAW_BASE="https://gitcode.com/${OWNER}/${REPO}"
curl_text "${RAW_BASE}/raw/master/README.md" "$OUTPUT_DIR/docs/README.md"
curl_text "${RAW_BASE}/-/raw/master/README.md" "$OUTPUT_DIR/docs/README.md"
curl_text "${RAW_BASE}/raw/master/docs/install.md" "$OUTPUT_DIR/docs/install.md"
curl_text "${RAW_BASE}/-/raw/master/docs/install.md" "$OUTPUT_DIR/docs/install.md"
curl_text "${RAW_BASE}/raw/master/docs/quick_start.md" "$OUTPUT_DIR/docs/quick_start.md"
curl_text "${RAW_BASE}/-/raw/master/docs/quick_start.md" "$OUTPUT_DIR/docs/quick_start.md"
curl_text "${RAW_BASE}/raw/master/docs/msprof_parsing_instruct.md" "$OUTPUT_DIR/docs/msprof_parsing_instruct.md"
curl_text "${RAW_BASE}/-/raw/master/docs/msprof_parsing_instruct.md" "$OUTPUT_DIR/docs/msprof_parsing_instruct.md"
curl_text "${RAW_BASE}/raw/master/docs/msmonitor_parsing_instruct.md" "$OUTPUT_DIR/docs/msmonitor_parsing_instruct.md"
curl_text "${RAW_BASE}/-/raw/master/docs/msmonitor_parsing_instruct.md" "$OUTPUT_DIR/docs/msmonitor_parsing_instruct.md"

cat > "$OUTPUT_DIR/context-meta.txt" <<EOF
repo_url=$REPO_URL
roadmap_url=$ROADMAP_URL
time_range=$TIME_RANGE
start_date=$START_DATE
end_date=$END_DATE
owner=$OWNER
repo=$REPO
EOF

echo "Fetched release context into: $OUTPUT_DIR"
