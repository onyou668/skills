#!/usr/bin/env python3
"""Run selected acceptance cases across one or more units under one acceptance lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from acceptance_common import (
    acceptance_map_path,
    acceptance_root,
    command_is_broad_test_run,
    command_is_dangerous,
    context_dependency_mode,
    load_yaml,
    read_config_context,
    read_text,
    run_command,
    slugify,
    write_yaml,
)


NO_TEST_PATTERNS = [
    "no tests ran",
    "no tests collected",
    "no test files found",
    "no tests found",
    "0 tests",
    "testing: warning: no tests to run",
]
ACCEPTANCE_ID_RE = re.compile(r"^ACC-[A-Za-z0-9][A-Za-z0-9-]{2,80}$")
IGNORED_STATE_PARTS = {".git", ".acceptance", "__pycache__", "node_modules", "vendor", "target", "dist", "build"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def render_frontmatter(metadata: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
    lines.extend(["---", "", body.rstrip(), ""])
    return "\n".join(lines)


def parse_frontmatter(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    lines = read_text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        try:
            result[key.strip()] = json.loads(raw.strip())
        except json.JSONDecodeError:
            result[key.strip()] = raw.strip().strip("\"'")
    return result


def relative_link(source_file: Path, target_file: Path) -> str:
    return Path(os.path.relpath(target_file, source_file.parent)).as_posix()


def redact_text(value: str) -> str:
    text = value or ""
    patterns = [
        (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"), r"\1[REDACTED]"),
        (re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key|cookie)\s*[=:]\s*)[^\s,;]+"), r"\1[REDACTED]"),
        (re.compile(r'(?i)(\"(?:password|passwd|secret|token|api[_-]?key|cookie)\"\s*:\s*\")[^\"]*(\")'), r"\1[REDACTED]\2"),
        (re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:\s/@]+:)[^@\s/]+(@)"), r"\1[REDACTED]\2"),
    ]
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


def dependency_policy_error(scenario: dict, context: str) -> str:
    for dependency in scenario.get("dependency_resolution", []):
        name = str(dependency.get("name", ""))
        mode = str(dependency.get("mode", "real"))
        if mode in {"mock", "fake", "stub", "no_access_mock"} and context_dependency_mode(context, name) != "mock":
            return f"Mock mode for {name or 'dependency'} is not explicitly authorized by global context."
        if mode == "real" and dependency.get("availability") == "unavailable":
            return f"Configured real dependency is unavailable: {name}. Mock fallback is forbidden."
    return ""


def entrypoint_ready(value: object) -> bool:
    if not value:
        return False
    if isinstance(value, dict):
        text = " ".join(str(item) for item in value.values()).lower()
    else:
        text = str(value).lower()
    return "pending" not in text


def mapping_policy_error(scenario: dict) -> tuple[str, str]:
    if scenario.get("feature_missing"):
        return "uncertain", "Scenario is missing from the canonical Feature and requires review before deprecation."
    if scenario.get("status") != "active":
        return "uncertain", "Only active canonical Feature scenarios can be executed."
    if scenario.get("generated_tests_stale"):
        return "pending", "Generated acceptance tests are stale after a Feature change."
    tests = scenario.get("generated_tests", [])
    if not tests:
        return "pending", "No executable generated test is mapped to this scenario."
    expected_cases = {str(item) for item in scenario.get("case_ids", [])} or {"case-001"}
    mapped_cases = {str(item.get("case_id", "")) for item in tests}
    missing_cases = sorted(expected_cases - mapped_cases)
    if missing_cases:
        return "pending", f"Acceptance cases have no mapped executable test: {', '.join(missing_cases)}."
    assertions = scenario.get("assertion_mapping", [])
    if not assertions or any(item.get("test_assertion") in {None, "", "pending_generation"} for item in assertions):
        return "pending", "Not every Then step is mapped to a concrete test assertion."
    if not scenario.get("style_evidence"):
        return "pending", "No current-project test-style evidence or explicit framework recommendation is recorded."
    if not entrypoint_ready(scenario.get("business_entrypoint")) or not entrypoint_ready(scenario.get("validation_entrypoint")):
        return "pending", "Business and validation entrypoints must be resolved before execution."
    return "", ""


def output_contains_test(discovery: dict, test: dict, scenario_id: str) -> bool:
    output = f"{discovery.get('stdout', '')}\n{discovery.get('stderr', '')}".lower()
    candidates = [test.get("symbol", ""), test.get("case_id", ""), scenario_id]
    return any(str(candidate).lower() in output for candidate in candidates if candidate)


def status_from_command(result: dict) -> tuple[str, str]:
    if result.get("timeout"):
        return "timeout", "Acceptance command exceeded its timeout."
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    if result.get("exit_code") == 0 and any(pattern in output for pattern in NO_TEST_PATTERNS):
        return "pending", "Command exited 0 but no acceptance test was executed."
    if result.get("exit_code") == 0:
        return "pass", ""
    return "fail", "Executable acceptance test failed."


def selected_scenarios(mapping: dict, requested: list[str], run_all: bool) -> list[dict]:
    scenarios = mapping.get("scenarios", [])
    if requested:
        wanted = set(requested)
        return [scenario for scenario in scenarios if scenario.get("id") in wanted]
    if run_all:
        return [scenario for scenario in scenarios if scenario.get("status") == "active"]
    return [scenario for scenario in scenarios if scenario.get("selected") is True]


def status_from_results(results: list[dict]) -> str:
    statuses = {result["status"] for result in results}
    if statuses == {"pass"}:
        return "incremental_pass"
    if statuses & {"fail", "error", "timeout"}:
        return "fail"
    if "uncertain" in statuses:
        return "uncertain"
    return "pending"


def result_counts(results: list[dict]) -> dict[str, int]:
    counts = {name: 0 for name in ["pass", "fail", "pending", "uncertain", "error", "timeout"]}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return counts


def module_body(
    unit_id: str,
    results: list[dict],
    excluded_count: int,
    report_path: Path,
    run_report: Path,
    acceptance_report: Path,
) -> str:
    counts = result_counts(results)
    lines = [
        f"# {unit_id} Acceptance Module Report",
        "",
        f"- run_report: [run report]({relative_link(report_path, run_report)})",
        f"- acceptance_report: [acceptance report]({relative_link(report_path, acceptance_report)})",
    ]
    lines.extend(
        [
            f"- not_selected_scenarios: {excluded_count}",
            f"- pass: {counts['pass']}",
            f"- fail: {counts['fail']}",
            f"- pending: {counts['pending']}",
            f"- uncertain: {counts['uncertain']}",
            f"- error: {counts['error']}",
            f"- timeout: {counts['timeout']}",
            "",
            "## Results",
            "",
        ]
    )
    for result in results:
        lines.extend(
            [
                f"### {result['scenario_id']}/{result['case_id']}",
                "",
                f"- status: `{result['status']}`",
                f"- test_file: `{result.get('file', '')}`",
                f"- test_symbol: `{result.get('symbol', '')}`",
                f"- command: `{result.get('command', '')}`",
                f"- reason: {result.get('reason', '') or 'none'}",
                "- expected:",
            ]
        )
        assertions = result.get("assertion_mapping", [])
        lines.extend(f"  - {item.get('then', '')}" for item in assertions)
        if result["status"] != "pass":
            lines.extend(
                [
                    "- repair_state: `awaiting_diagnosis`",
                    "- required_follow_up: trace the route/symbol call chain, quote the abnormal code, classify the root cause, and propose the correct repair before changing code",
                    "",
                    "```text",
                    redact_text((result.get("stdout", "") or "")[-4000:]),
                    redact_text((result.get("stderr", "") or "")[-4000:]),
                    "```",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_module_report(
    report_path: Path,
    acceptance_id: str,
    run_id: str,
    unit_id: str,
    module_status: str,
    results: list[dict],
    excluded_count: int,
    mapping: dict,
    code_state: dict,
    context_fingerprint: str,
    run_report: Path,
    acceptance_report: Path,
) -> str:
    metadata = {
        "acceptance_id": acceptance_id,
        "run_id": run_id,
        "unit_id": unit_id,
        "status": module_status,
        "code_revision": code_state["commit"],
        "code_state_id": code_state["code_state_id"],
        "feature_hash": mapping.get("feature_hash", ""),
        "contract_revision": int(mapping.get("contract_revision", 1) or 1),
        "map_hash": hashlib.sha256(read_text(acceptance_map_path(report_path.parent.parent)).encode("utf-8")).hexdigest()[:16],
        "context_fingerprint": context_fingerprint,
        "run_report": relative_link(report_path, run_report),
        "acceptance_report": relative_link(report_path, acceptance_report),
    }
    body = module_body(unit_id, results, excluded_count, report_path, run_report, acceptance_report)
    return render_frontmatter(metadata, body)


def execute_unit(
    project_root: Path,
    acceptance_id: str,
    run_id: str,
    unit_id: str,
    requested: list[str],
    args: argparse.Namespace,
    context: str,
    code_state: dict,
    context_fingerprint: str,
    run_report_path: Path,
    acceptance_report_path: Path,
) -> dict:
    root = acceptance_root(project_root)
    unit_path = root / "units" / unit_id
    map_path = acceptance_map_path(unit_path)
    mapping = load_yaml(map_path)
    chosen = selected_scenarios(mapping, requested, args.all)
    results: list[dict] = []
    if not chosen:
        results.append(
            {
                "scenario_id": "none",
                "case_id": "selection-gate",
                "status": "pending",
                "reason": "No affected acceptance scenarios are selected. Full-module fallback is forbidden.",
                "assertion_mapping": [],
            }
        )
    for scenario in chosen:
        gate_status, gate_error = mapping_policy_error(scenario)
        dependency_error = dependency_policy_error(scenario, context)
        if dependency_error:
            gate_status, gate_error = "uncertain", dependency_error
        tests = scenario.get("generated_tests", [])
        if gate_error:
            results.append(
                {
                    "scenario_id": scenario.get("id", ""),
                    "case_id": "mapping-gate",
                    "status": gate_status,
                    "reason": gate_error,
                    "assertion_mapping": scenario.get("assertion_mapping", []),
                }
            )
            continue
        for test in tests:
            result = {
                "scenario_id": scenario.get("id", ""),
                "case_id": test.get("case_id", "case"),
                "file": test.get("file", ""),
                "symbol": test.get("symbol", ""),
                "command": test.get("command", ""),
                "assertion_mapping": scenario.get("assertion_mapping", []),
            }
            if not (project_root / str(test.get("file", ""))).is_file():
                result.update(status="pending", reason="Mapped generated test file does not exist.")
            elif command_is_broad_test_run(str(test.get("command", ""))) and not args.allow_broad:
                result.update(status="uncertain", reason="Repository-wide test command is forbidden for incremental acceptance.")
            elif command_is_dangerous(str(test.get("command", ""))):
                result.update(status="uncertain", reason="Acceptance command matched the dangerous-command blocklist.")
            elif not test.get("discovery_command"):
                result.update(status="pending", reason="No scoped test discovery command is recorded.")
            else:
                discovery = run_command(str(test["discovery_command"]), project_root, args.timeout)
                if discovery.get("exit_code") != 0 or not output_contains_test(discovery, test, result["scenario_id"]):
                    result.update(status="pending", reason="Test discovery did not prove that the exact acceptance case exists.")
                    result["stdout"] = discovery.get("stdout", "")
                    result["stderr"] = discovery.get("stderr", "")
                else:
                    executed = run_command(str(test["command"]), project_root, args.timeout)
                    status, reason = status_from_command(executed)
                    result.update(executed)
                    result.update(status=status, reason=reason)
            results.append(result)

    module_status = status_from_results(results)
    report_path = unit_path / "reports" / f"{acceptance_id}-{run_id}.md"
    excluded_count = max(0, len(mapping.get("scenarios", [])) - len(chosen))
    report = render_module_report(
        report_path,
        acceptance_id,
        run_id,
        unit_id,
        module_status,
        results,
        excluded_count,
        mapping,
        code_state,
        context_fingerprint,
        run_report_path,
        acceptance_report_path,
    )
    if report_path.exists():
        raise ValueError(f"Immutable module report already exists: {report_path}")
    atomic_write(report_path, report)
    return {
        "unit": unit_id,
        "status": module_status,
        "report_path": report_path,
        "report": str(report_path.relative_to(root)).replace("\\", "/"),
        "feature_hash": mapping.get("feature_hash", ""),
        "contract_revision": int(mapping.get("contract_revision", 1) or 1),
        "map_hash": hashlib.sha256(read_text(map_path).encode("utf-8")).hexdigest()[:16],
        "selected_scenarios": len(chosen),
        "results": results,
        "mapping": mapping,
        "map_path": map_path,
    }


def update_module_map(module: dict, acceptance_id: str, run_id: str) -> None:
    mapping = module["mapping"]
    by_scenario: dict[str, list[dict]] = {}
    for result in module["results"]:
        by_scenario.setdefault(result["scenario_id"], []).append(result)
    relative_report = f"reports/{module['report_path'].name}"
    for scenario in mapping.get("scenarios", []):
        scenario_results = by_scenario.get(scenario.get("id", ""), [])
        if not scenario_results:
            continue
        passed = all(item["status"] == "pass" for item in scenario_results)
        scenario["latest_result"] = "pass" if passed else "not_accepted"
        scenario["latest_acceptance_id"] = acceptance_id
        scenario["latest_run_id"] = run_id
        scenario["latest_report"] = relative_report
        if passed:
            scenario["selected"] = False
            scenario["selection_reason"] = "accepted_current_change"
            scenario["repair_state"] = "not_required"
        else:
            scenario["repair_state"] = "awaiting_diagnosis"
    mapping["latest_acceptance_id"] = acceptance_id
    mapping["latest_run_id"] = run_id
    mapping["latest_result"] = module["status"]
    mapping["latest_report"] = relative_report
    write_yaml(module["map_path"], mapping)


def reserve_run(acceptance_dir: Path, acceptance_id: str) -> tuple[str, Path]:
    runs_dir = acceptance_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for number in range(1, 10000):
        run_id = f"RUN-{number:03d}"
        path = runs_dir / f"{run_id}.md"
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    render_frontmatter(
                        {"acceptance_id": acceptance_id, "run_id": run_id, "status": "running", "started_at": now_iso()},
                        f"# {acceptance_id} {run_id}\n\nRun is in progress.",
                    )
                )
            return run_id, path
        except FileExistsError:
            continue
    raise ValueError("Could not allocate a unique run id.")


def new_acceptance_id() -> str:
    return f"ACC-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


def contract_snapshot(project_root: Path, units: list[str]) -> tuple[str, list[dict]]:
    root = acceptance_root(project_root)
    items = []
    for unit in sorted(set(units)):
        path = root / "units" / unit / "acceptance-map.yaml"
        mapping = load_yaml(path) if path.exists() else {}
        items.append(
            {
                "unit": unit,
                "feature_hash": mapping.get("feature_hash", ""),
                "contract_revision": int(mapping.get("contract_revision", 1) or 1),
            }
        )
    fingerprint = hashlib.sha256(json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return fingerprint, items


def git_code_state(project_root: Path) -> dict[str, str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        root = acceptance_root(project_root)
        exclude = ""
        try:
            exclude = root.relative_to(project_root).as_posix()
        except ValueError:
            pass
        diff_args = ["git", "diff", "--binary", "HEAD", "--", "."]
        if exclude:
            diff_args.append(f":(exclude){exclude}/**")
        diff = subprocess.run(diff_args, cwd=str(project_root), capture_output=True, check=True).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        digest = hashlib.sha256(diff)
        for relative in sorted(untracked):
            path = Path(relative)
            if exclude and (relative == exclude or relative.startswith(exclude + "/")):
                continue
            if any(part in IGNORED_STATE_PARTS for part in path.parts) or path.suffix == ".pyc":
                continue
            absolute = project_root / path
            if not absolute.is_file():
                continue
            digest.update(relative.encode("utf-8"))
            with absolute.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        dirty_hash = digest.hexdigest()[:16]
        state_id = hashlib.sha256(f"{commit}:{dirty_hash}".encode("utf-8")).hexdigest()[:16]
        return {"commit": commit, "dirty_diff_hash": dirty_hash, "code_state_id": state_id}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "not-git", "dirty_diff_hash": "unavailable", "code_state_id": "unavailable"}


def run_body(acceptance_id: str, run_id: str, modules: list[dict], run_report_path: Path) -> str:
    lines = [
        f"# {acceptance_id} {run_id}",
        "",
        "## Modules",
        "",
        "| Unit | Status | Selected scenarios | Report |",
        "|---|---|---:|---|",
    ]
    for module in modules:
        link = relative_link(run_report_path, module["report_path"])
        lines.append(f"| {module['unit']} | {module['status']} | {module['selected_scenarios']} | [module report]({link}) |")
    return "\n".join(lines) + "\n"


def run_metadata(
    acceptance_id: str,
    run_id: str,
    run_status: str,
    modules: list[dict],
    code_state: dict,
    contract_revision: int,
    contract_fingerprint: str,
    parent_run: str,
    args: argparse.Namespace,
    started_at: str,
    context_fingerprint: str,
) -> dict[str, Any]:
    return {
        "acceptance_id": acceptance_id,
        "run_id": run_id,
        "parent_run": parent_run,
        "status": run_status,
        "started_at": started_at,
        "finished_at": now_iso(),
        "trigger": "repair_rerun" if args.repair_confirmed else "initial_run",
        "repair_confirmed": bool(args.repair_confirmed),
        "repair_note": args.repair_note or "",
        "approved_files": args.approved_file,
        "code_revision": code_state["commit"],
        "dirty_diff_hash": code_state["dirty_diff_hash"],
        "code_state_id": code_state["code_state_id"],
        "contract_revision": contract_revision,
        "contract_fingerprint": contract_fingerprint,
        "context_fingerprint": context_fingerprint,
        "modules": [
            {
                "unit": module["unit"],
                "status": module["status"],
                "report": module["report"],
                "feature_hash": module["feature_hash"],
                "contract_revision": module["contract_revision"],
                "map_hash": module["map_hash"],
            }
            for module in modules
        ],
    }


def load_run_metadata(acceptance_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted((acceptance_dir / "runs").glob("RUN-*.md")):
        metadata = parse_frontmatter(path)
        if metadata.get("status") == "running":
            metadata["status"] = "interrupted"
        metadata["path"] = path
        runs.append(metadata)
    return runs


def current_module_states(project_root: Path, scope_units: list[str], runs: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for run in runs:
        for module in run.get("modules", []) or []:
            latest[str(module.get("unit", ""))] = dict(module)
    root = acceptance_root(project_root)
    states = []
    for unit in scope_units:
        current = latest.get(unit)
        if current is None:
            states.append({"unit": unit, "status": "pending", "report": ""})
            continue
        mapping_path = root / "units" / unit / "acceptance-map.yaml"
        mapping = load_yaml(mapping_path) if mapping_path.exists() else {}
        status = str(current.get("status", "pending"))
        if status == "incremental_pass":
            status = "pass"
            feature_changed = current.get("feature_hash", "") != mapping.get("feature_hash", "")
            map_stale = any(
                scenario.get("selected") is True or scenario.get("generated_tests_stale") or scenario.get("feature_missing")
                for scenario in mapping.get("scenarios", [])
            )
            if feature_changed or map_stale:
                status = "stale"
        states.append({"unit": unit, "status": status, "report": current.get("report", "")})
    return states


def acceptance_status(states: list[dict]) -> str:
    statuses = {state["status"] for state in states}
    if states and statuses == {"pass"}:
        return "accepted"
    if statuses & {"fail", "error", "timeout"}:
        return "awaiting_diagnosis"
    if "uncertain" in statuses:
        return "uncertain"
    return "pending"


def acceptance_body(
    acceptance_id: str,
    acceptance_report_path: Path,
    runs: list[dict],
    states: list[dict],
) -> str:
    lines = [
        f"# Acceptance {acceptance_id}",
        "",
        "## Runs",
        "",
        "| Run | Status | Trigger | Superseded by | Report |",
        "|---|---|---|---|---|",
    ]
    for index, run in enumerate(runs):
        path = run["path"]
        superseded_by = runs[index + 1].get("run_id", "") if index + 1 < len(runs) else ""
        lines.append(
            f"| {run.get('run_id', path.stem)} | {run.get('status', 'interrupted')} | {run.get('trigger', 'unknown')} | {superseded_by} | [run report]({relative_link(acceptance_report_path, path)}) |"
        )
    lines.extend(["", "## Current Module State", "", "| Unit | Effective status | Latest report |", "|---|---|---|"])
    for state in states:
        report = state.get("report", "")
        link = f"[module report]({relative_link(acceptance_report_path, acceptance_report_path.parents[2] / report)})" if report else ""
        lines.append(f"| {state['unit']} | {state['status']} | {link} |")
    lines.extend(
        [
            "",
            "Old failed runs remain immutable evidence. A pass is reusable only while its Feature and acceptance-map selection remain current.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_latest_pointer(
    module: dict,
    acceptance_id: str,
    run_id: str,
    acceptance_status_value: str,
    run_report_path: Path,
    acceptance_report_path: Path,
    effective_status: str | None = None,
) -> None:
    latest_path = module["report_path"].parent / "latest.md"
    metadata = {
        "acceptance_id": acceptance_id,
        "run_id": run_id,
        "unit_id": module["unit"],
        "status": module["status"],
        "effective_status": effective_status or module["status"],
        "acceptance_status": acceptance_status_value,
        "module_report": relative_link(latest_path, module["report_path"]),
        "run_report": relative_link(latest_path, run_report_path),
        "acceptance_report": relative_link(latest_path, acceptance_report_path),
        "updated_at": now_iso(),
    }
    body = "\n".join(
        [
            f"# {module['unit']} Latest Acceptance Run",
            "",
            f"- module_report: [report]({metadata['module_report']})",
            f"- run_report: [report]({metadata['run_report']})",
            f"- acceptance_report: [report]({metadata['acceptance_report']})",
        ]
    )
    atomic_write(latest_path, render_frontmatter(metadata, body))


def refresh_scope_latest_pointers(
    project_root: Path,
    acceptance_id: str,
    states: list[dict],
    acceptance_status_value: str,
    acceptance_report_path: Path,
) -> None:
    root = acceptance_root(project_root)
    for state in states:
        relative_report = str(state.get("report", ""))
        if not relative_report:
            continue
        report_path = root / relative_report
        metadata = parse_frontmatter(report_path)
        module_run_id = str(metadata.get("run_id", ""))
        if not report_path.exists() or not module_run_id:
            continue
        module = {
            "unit": state["unit"],
            "status": metadata.get("status", state["status"]),
            "report_path": report_path,
        }
        run_report_path = acceptance_report_path.parent / "runs" / f"{module_run_id}.md"
        write_latest_pointer(
            module,
            acceptance_id,
            module_run_id,
            acceptance_status_value,
            run_report_path,
            acceptance_report_path,
            effective_status=state["status"],
        )


def requested_for_unit(requested: list[str], units: list[str], unit_id: str) -> list[str]:
    if not requested:
        return []
    result = []
    for value in requested:
        if ":" in value:
            prefix, scenario_id = value.split(":", 1)
            if slugify(prefix, "unit") == unit_id:
                result.append(scenario_id)
        elif len(units) == 1:
            result.append(value)
        else:
            raise ValueError("With multiple units, --scenario must use <unit>:<scenario-id>.")
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--project-root", default=".")
    result.add_argument("--unit", action="append", required=True, help="Affected unit; repeat for a multi-unit run.")
    result.add_argument("--scenario", action="append", default=[], help="Exact scenario, or <unit>:<scenario> for multiple units.")
    result.add_argument("--acceptance-id", help="Continue an existing acceptance; omit to start a new one.")
    result.add_argument("--repair-confirmed", action="store_true", help="The user approved the diagnosed repair and this rerun.")
    result.add_argument("--repair-note", help="Short record of the approved repair logic.")
    result.add_argument("--approved-file", action="append", default=[], help="Approved repair file; repeat as needed.")
    result.add_argument("--all", action="store_true", help="Run every active scenario in each named unit after explicit authorization.")
    result.add_argument("--allow-broad", action="store_true", help="Allow a repository-wide command only after explicit authorization.")
    result.add_argument("--timeout", type=int, default=120)
    result.add_argument("--keep-history", action="store_true", help=argparse.SUPPRESS)
    return result


def main() -> int:
    args = parser().parse_args()
    project_root = Path(args.project_root).resolve()
    units = list(dict.fromkeys(slugify(value, "unit") for value in args.unit))
    root = acceptance_root(project_root)
    for unit_id in units:
        map_path = root / "units" / unit_id / "acceptance-map.yaml"
        if not map_path.exists():
            print(f"Missing {map_path}. Confirm the Feature and generate test mappings first.")
            return 2

    acceptance_id = args.acceptance_id or new_acceptance_id()
    if not ACCEPTANCE_ID_RE.fullmatch(acceptance_id):
        print("acceptance-id must use ACC- followed by letters, digits, or hyphens.")
        return 2
    acceptance_dir = root / "acceptances" / acceptance_id
    acceptance_report_path = acceptance_dir / "report.md"
    existing_metadata = parse_frontmatter(acceptance_report_path)
    previous_runs = load_run_metadata(acceptance_dir) if acceptance_dir.exists() else []
    if existing_metadata.get("status") == "accepted":
        print("This acceptance is already accepted. Start a new acceptance instead of appending another run.")
        return 2
    if previous_runs and not args.repair_confirmed:
        print("Continuing an existing acceptance after a prior run requires --repair-confirmed.")
        return 2

    acceptance_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    run_id, run_report_path = reserve_run(acceptance_dir, acceptance_id)
    parent_run = str(previous_runs[-1].get("run_id", "")) if previous_runs else ""
    previous_scope = [str(item) for item in existing_metadata.get("scope_units", [])]
    if not previous_scope:
        previous_scope = [
            str(module.get("unit", ""))
            for run in previous_runs
            for module in (run.get("modules", []) or [])
            if module.get("unit")
        ]
    scope_units = list(dict.fromkeys([*previous_scope, *units]))
    contract_fingerprint, contracts = contract_snapshot(project_root, scope_units)
    previous_contract_revision = int(existing_metadata.get("contract_revision", 0) or 0)
    contract_revision = previous_contract_revision or 1
    if previous_contract_revision and existing_metadata.get("contract_fingerprint") != contract_fingerprint:
        contract_revision += 1
    code_state = git_code_state(project_root)
    context = str(read_config_context(project_root).get("context", ""))
    context_fingerprint = hashlib.sha256(context.encode("utf-8")).hexdigest()[:16]

    try:
        modules = []
        for unit_id in units:
            modules.append(
                execute_unit(
                    project_root,
                    acceptance_id,
                    run_id,
                    unit_id,
                    requested_for_unit(args.scenario, units, unit_id),
                    args,
                    context,
                    code_state,
                    context_fingerprint,
                    run_report_path,
                    acceptance_report_path,
                )
            )
        run_status = "incremental_pass" if modules and all(module["status"] == "incremental_pass" for module in modules) else (
            "fail" if any(module["status"] == "fail" for module in modules) else (
                "uncertain" if any(module["status"] == "uncertain" for module in modules) else "pending"
            )
        )
        run_meta = run_metadata(
            acceptance_id,
            run_id,
            run_status,
            modules,
            code_state,
            contract_revision,
            contract_fingerprint,
            parent_run,
            args,
            started_at,
            context_fingerprint,
        )
        atomic_write(run_report_path, render_frontmatter(run_meta, run_body(acceptance_id, run_id, modules, run_report_path)))

        for module in modules:
            update_module_map(module, acceptance_id, run_id)

        runs = load_run_metadata(acceptance_dir)
        states = current_module_states(project_root, scope_units, runs)
        final_status = acceptance_status(states)
        acceptance_meta = {
            "acceptance_id": acceptance_id,
            "status": final_status,
            "latest_run_id": run_id,
            "scope_units": scope_units,
            "contract_revision": contract_revision,
            "contract_fingerprint": contract_fingerprint,
            "contracts": contracts,
            "code_revision": code_state["commit"],
            "code_state_id": code_state["code_state_id"],
            "context_fingerprint": context_fingerprint,
            "updated_at": now_iso(),
        }
        atomic_write(
            acceptance_report_path,
            render_frontmatter(
                acceptance_meta,
                acceptance_body(acceptance_id, acceptance_report_path, runs, states),
            ),
        )
        refresh_scope_latest_pointers(project_root, acceptance_id, states, final_status, acceptance_report_path)

        print(f"Acceptance ID: {acceptance_id}")
        print(f"Run ID: {run_id}")
        print(f"Run report: {run_report_path}")
        print(f"Acceptance report: {acceptance_report_path}")
        print(f"Run status: {run_status}")
        print(f"Acceptance status: {final_status}")
        return 0 if final_status == "accepted" else 1
    except (OSError, ValueError) as exc:
        interrupted = parse_frontmatter(run_report_path)
        interrupted.update({"status": "interrupted", "finished_at": now_iso(), "error": redact_text(str(exc))})
        atomic_write(run_report_path, render_frontmatter(interrupted, f"# {acceptance_id} {run_id}\n\nRun interrupted: {redact_text(str(exc))}"))
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
