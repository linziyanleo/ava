#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HAPPY_LOG="${1:-docs/desktop-acceptance-happy.log}"
PORT_CONFLICT_LOG="${2:-docs/desktop-acceptance-port-conflict.log}"
ACCEPTANCE_DOC="${3:-docs/desktop-launch-acceptance.md}"
TASK_SPEC="${4:-.specanchor/tasks/_cross-module/2026-05-12_electron-headless-launch.spec.md}"

cd "${REPO_ROOT}"

python3 - "${HAPPY_LOG}" "${PORT_CONFLICT_LOG}" "${ACCEPTANCE_DOC}" "${TASK_SPEC}" <<'PY'
import sys
from pathlib import Path

happy_log, port_conflict_log, acceptance_doc, task_spec = sys.argv[1:5]

HUMAN_FIELDS = (
    "Finder double-click, no Terminal",
    "Setup surface visible before Console",
    "Cancel stops uv sync, Retry starts again",
    "Help -> Open Logs opens ~/Library/Logs/Ava",
)


def fail(message: str) -> None:
    print(f"verify-desktop-closeout-records: {message}", file=sys.stderr)
    sys.exit(1)


def read_required(path: str, label: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        fail(f"{label} is missing: {path}")
    return file_path.read_text(encoding="utf-8")


def require_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        fail(f"{label} is missing required text: {needle}")


def require_not_contains(text: str, needle: str, label: str) -> None:
    if needle in text:
        fail(f"{label} contains forbidden text: {needle}")


def require_success_log(path: str, text: str, *, with_port_conflict: bool) -> str:
    label = path
    command = expected_command(path, with_port_conflict=with_port_conflict)
    require_contains(text, "Automated desktop acceptance checks passed.", label)
    require_contains(text, "Paste-ready result record:", label)
    require_contains(text, f"Command: {command}", label)
    require_contains(text, f"Evidence log: {path}", label)
    app_path = require_log_field(text, "App path", label)
    require_not_contains(text, "Automated desktop acceptance checks failed", label)
    require_not_contains(text, "Do not paste this evidence log into Result Records", label)
    if with_port_conflict:
        require_contains(text, "Skip build: 1", label)
        require_contains(text, "With port conflict: 1", label)
        require_contains(text, "Conflict port: 6688", label)
        require_contains(text, "127.0.0.1:6688 is occupied by temporary non-Ava server", label)
        require_contains(
            text,
            "Dynamic-port path: automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6688",
            label,
        )
    else:
        require_contains(text, "Skip build: 0", label)
        require_contains(text, "With port conflict: 0", label)
        require_contains(text, "Conflict port: not run by this command", label)
        require_contains(text, "Dynamic-port path: not run by this command", label)
    return app_path


def expected_command(evidence_log: str, *, with_port_conflict: bool) -> str:
    if with_port_conflict:
        return f"scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log {evidence_log}"
    return f"scripts/verify-desktop-acceptance.sh --evidence-log {evidence_log}"


def field_value(line: str, field: str) -> str | None:
    prefix = f"{field}:"
    if not line.startswith(prefix):
        return None
    return line[len(prefix):].strip()


def require_log_field(text: str, field: str, label: str) -> str:
    for line in text.splitlines():
        value = field_value(line.strip(), field)
        if value is None:
            continue
        if not value:
            fail(f"{label} has an unfilled log field: {field}")
        return value
    fail(f"{label} is missing log field: {field}")


def extract_record(text: str, evidence_log: str, label: str) -> list[str]:
    lines = text.splitlines()
    evidence_line = f"Evidence log: {evidence_log}"
    for index, line in enumerate(lines):
        if line.strip() == evidence_line:
            return lines[max(0, index - 6): index + 14]
    fail(f"{label} does not contain a result record for {evidence_log}")


def section_after(text: str, marker: str, label: str) -> str:
    marker_index = text.find(marker)
    if marker_index < 0:
        fail(f"{label} is missing section marker: {marker}")
    return text[marker_index:]


def require_filled_field(record: list[str], field: str, label: str) -> str:
    for line in record:
        value = field_value(line.strip(), field)
        if value is None:
            continue
        if not value:
            fail(f"{label} has an unfilled field: {field}")
        return value
    fail(f"{label} is missing field: {field}")


def require_record_value(record: list[str], field: str, expected: str, label: str) -> None:
    for line in record:
        value = field_value(line.strip(), field)
        if value is None:
            continue
        if value != expected:
            fail(f"{label} field {field!r} expected {expected!r}, got {value!r}")
        return
    fail(f"{label} is missing field: {field}")


def require_closeout_record(text: str, evidence_log: str, label: str, *, with_port_conflict: bool, app_path: str) -> list[str]:
    record = extract_record(text, evidence_log, label)
    require_filled_field(record, "Date", label)
    require_record_value(record, "Command", expected_command(evidence_log, with_port_conflict=with_port_conflict), label)
    require_record_value(record, "App path", app_path, label)
    require_record_value(record, "Evidence log", evidence_log, label)
    require_record_value(record, "Console happy path", "automated LaunchServices verifier passed", label)
    if with_port_conflict:
        require_record_value(record, "Conflict port", "6688", label)
        require_record_value(
            record,
            "Dynamic-port path",
            "automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6688",
            label,
        )
    else:
        require_record_value(record, "Conflict port", "not run by this command", label)
        require_record_value(record, "Dynamic-port path", "not run by this command", label)

    for field in HUMAN_FIELDS:
        require_filled_field(record, field, label)
    return record


def require_matching_human_fields(doc_record: list[str], task_record: list[str], evidence_log: str) -> None:
    for field in HUMAN_FIELDS:
        doc_value = require_filled_field(doc_record, field, acceptance_doc)
        task_value = require_filled_field(task_record, field, task_spec)
        if doc_value != task_value:
            fail(
                f"human field {field!r} for {evidence_log} differs between acceptance doc and task spec: "
                f"{acceptance_doc}={doc_value!r}, {task_spec}={task_value!r}"
            )


happy_text = read_required(happy_log, "happy-path evidence log")
port_conflict_text = read_required(port_conflict_log, "port-conflict evidence log")
doc_text = read_required(acceptance_doc, "desktop acceptance doc")
task_text = read_required(task_spec, "desktop task spec")

happy_app_path = require_success_log(happy_log, happy_text, with_port_conflict=False)
port_conflict_app_path = require_success_log(port_conflict_log, port_conflict_text, with_port_conflict=True)

doc_records_text = section_after(doc_text, "## Result Records", acceptance_doc)
task_records_text = section_after(task_text, "## 8. Objective Completion Audit", task_spec)

for text, label in ((doc_records_text, acceptance_doc), (task_records_text, task_spec)):
    require_not_contains(text, "No non-sandbox desktop acceptance result has been recorded yet.", label)

doc_happy_record = require_closeout_record(
    doc_records_text,
    happy_log,
    acceptance_doc,
    with_port_conflict=False,
    app_path=happy_app_path,
)
doc_port_conflict_record = require_closeout_record(
    doc_records_text,
    port_conflict_log,
    acceptance_doc,
    with_port_conflict=True,
    app_path=port_conflict_app_path,
)
task_happy_record = require_closeout_record(
    task_records_text,
    happy_log,
    task_spec,
    with_port_conflict=False,
    app_path=happy_app_path,
)
task_port_conflict_record = require_closeout_record(
    task_records_text,
    port_conflict_log,
    task_spec,
    with_port_conflict=True,
    app_path=port_conflict_app_path,
)

require_matching_human_fields(doc_happy_record, task_happy_record, happy_log)
require_matching_human_fields(doc_port_conflict_record, task_port_conflict_record, port_conflict_log)

require_not_contains(task_text, "Partially verified:", task_spec)
require_not_contains(task_text, "### 8.2 Unclosed Acceptance", task_spec)
require_not_contains(task_text, "Do not mark this goal complete yet", task_spec)

print("Desktop closeout records verified")
PY
