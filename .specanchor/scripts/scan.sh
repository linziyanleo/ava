#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STALE_DAYS=14
OUTDATED_DAYS=30

cd "$ROOT"

now="$(date +%s)"

status_for_age() {
  local age_days="$1"
  if [ "$age_days" -ge "$OUTDATED_DAYS" ]; then
    printf "OUTDATED"
  elif [ "$age_days" -ge "$STALE_DAYS" ]; then
    printf "STALE"
  else
    printf "FRESH"
  fi
}

last_ts_for_file() {
  local file="$1"
  local ts
  ts="$(git log -1 --format=%ct -- "$file" 2>/dev/null || true)"
  if [ -n "$ts" ]; then
    printf "%s" "$ts"
    return 0
  fi
  stat -f %m "$file"
}

printf "SpecAnchor scan root: %s\n" "$ROOT"

found=0
while IFS= read -r file; do
  found=1
  ts="$(last_ts_for_file "$file")"
  age_days="$(( (now - ts) / 86400 ))"
  state="$(status_for_age "$age_days")"
  printf "%-8s %4sd  %s\n" "$state" "$age_days" "$file"
done < <(find .specanchor/global .specanchor/modules .specanchor/tasks -type f -name "*.md" | sort)

if [ "$found" -eq 0 ]; then
  echo "No spec files found."
fi
