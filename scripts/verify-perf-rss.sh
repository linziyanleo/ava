#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DURATION_MIN=30
INTERVAL_SEC=30
PID=""
LOG_DIR="${REPO_ROOT}/docs"

usage() {
  cat <<'TEXT'
Usage:
  scripts/verify-perf-rss.sh [--pid <PID>] [--duration-min N] [--interval-sec N] [--log-dir DIR]

Sample resident memory of an already-running Ava process at fixed intervals.
Closeout step for .specanchor/.../2026-05-15_memory-perf-optimization.spec.md §6.3.

Default: sample every 30s for 30 minutes, writing to
docs/ava-rss-YYYYMMDD-HHMM.log and printing a min/max/delta summary at the end.

Options:
  --pid PID            Target PID. If omitted, auto-detects via `pgrep -f ava-core`.
  --duration-min N     Total monitoring duration in minutes (default 30).
  --interval-sec N     Sampling interval in seconds (default 30).
  --log-dir DIR        Directory to write the sample log (default docs/).

Threshold (per spec §6.3):
  - idle RSS should stay < 500 MB
  - 30 min growth should be < 100 MB
  - if either fails, inspect EvictingSessionCache._data length and confirm
    RetentionManager fired at startup before chasing other unbounded structures.
TEXT
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --pid)
      PID="$2"
      shift 2
      ;;
    --duration-min)
      DURATION_MIN="$2"
      shift 2
      ;;
    --interval-sec)
      INTERVAL_SEC="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${PID}" ]]; then
  PID="$(pgrep -f 'ava-core|ava\.console|python -m ava' | head -1 || true)"
  if [[ -z "${PID}" ]]; then
    echo "error: could not auto-detect Ava PID. Start Ava first or pass --pid." >&2
    exit 1
  fi
fi

if ! ps -p "${PID}" > /dev/null 2>&1; then
  echo "error: PID ${PID} is not running." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/ava-rss-$(date +%Y%m%d-%H%M).log"
SAMPLES=$(( DURATION_MIN * 60 / INTERVAL_SEC ))

{
  echo "# ava perf RSS sampling"
  echo "# pid=${PID}"
  echo "# started=$(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "# duration_min=${DURATION_MIN} interval_sec=${INTERVAL_SEC} samples=${SAMPLES}"
  echo "# columns: epoch_s rss_kb vsz_kb etime"
} > "${LOG_FILE}"

echo "sampling pid=${PID} for ${DURATION_MIN}m at ${INTERVAL_SEC}s -> ${LOG_FILE}"

for ((i = 1; i <= SAMPLES; i++)); do
  if ! ps -p "${PID}" > /dev/null 2>&1; then
    echo "# pid ${PID} disappeared at sample ${i}/${SAMPLES} ($(date '+%H:%M:%S'))" >> "${LOG_FILE}"
    echo "error: target process exited mid-sample at iteration ${i}/${SAMPLES}." >&2
    break
  fi
  read -r RSS VSZ ETIME < <(ps -o rss=,vsz=,etime= -p "${PID}")
  printf '%d %s %s %s\n' "$(date +%s)" "${RSS}" "${VSZ}" "${ETIME}" >> "${LOG_FILE}"
  if (( i < SAMPLES )); then
    sleep "${INTERVAL_SEC}"
  fi
done

# Summary
RSS_MIN=$(awk 'NR>1 && /^[0-9]/ {print $2}' "${LOG_FILE}" | sort -n | head -1)
RSS_MAX=$(awk 'NR>1 && /^[0-9]/ {print $2}' "${LOG_FILE}" | sort -n | tail -1)
RSS_FIRST=$(awk 'NR>1 && /^[0-9]/ {print $2; exit}' "${LOG_FILE}")
RSS_LAST=$(awk 'NR>1 && /^[0-9]/ {last=$2} END{print last}' "${LOG_FILE}")

if [[ -z "${RSS_FIRST:-}" ]]; then
  echo "error: no samples recorded." >&2
  exit 1
fi

DELTA_KB=$(( RSS_LAST - RSS_FIRST ))
DELTA_MB=$(( DELTA_KB / 1024 ))
MAX_MB=$(( RSS_MAX / 1024 ))
MIN_MB=$(( RSS_MIN / 1024 ))

{
  echo
  echo "# summary"
  echo "# rss_min_mb=${MIN_MB} rss_max_mb=${MAX_MB} rss_first_mb=$(( RSS_FIRST / 1024 )) rss_last_mb=$(( RSS_LAST / 1024 ))"
  echo "# delta_first_to_last_mb=${DELTA_MB}"
} >> "${LOG_FILE}"

echo
echo "summary:"
echo "  rss min   = ${MIN_MB} MB"
echo "  rss max   = ${MAX_MB} MB"
echo "  delta     = ${DELTA_MB} MB (last - first)"
echo "  log       = ${LOG_FILE}"
echo

PASS=1
if (( MAX_MB >= 500 )); then
  echo "FAIL: rss_max ${MAX_MB} MB >= 500 MB threshold"
  PASS=0
fi
if (( DELTA_MB >= 100 )); then
  echo "FAIL: delta ${DELTA_MB} MB >= 100 MB growth threshold"
  PASS=0
fi

if (( PASS == 1 )); then
  echo "PASS: rss within thresholds (max < 500 MB, delta < 100 MB)"
  exit 0
else
  echo
  echo "next: inspect EvictingSessionCache._data length + confirm RetentionManager fired at startup"
  exit 1
fi
