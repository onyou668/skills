#!/usr/bin/env python3
"""Run only selected acceptance cases from a module acceptance-map.yaml."""

from __future__ import annotations

import argparse
from pathlib import Path

from acceptance_common import (
    acceptance_map_path,
    command_is_broad_test_run,
    command_is_dangerous,
    context_dependency_mode,
    load_yaml,
    now_id,
    read_config_context,
    read_text,
    run_command,
    slugify,
    unit_dir,
    write_text,
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


def select_scenarios(mapping: dict, requested: list[str], run_all: bool) -> list[dict]:
    scenarios = mapping.get("scenarios", [])
    if requested:
        wanted = set(requested)
        return [scenario for scenario in scenarios if scenario.get("id") in wanted]
    if run_all:
        return [scenario for scenario in scenarios if scenario.get("status") == "active"]
    return [scenario for scenario in scenarios if scenario.get("selected") is True]


def render_report(unit_id: str, run_id: str, overall: str, selected: list[dict], results: list[dict], excluded_count: int) -> str:
    counts = {name: 0 for name in ["pass", "fail", "pending", "uncertain", "error", "timeout"]}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    lines = [
        f"# {unit_id} Incremental Acceptance Report",
        "",
        f"- run_id: `{run_id}`",
        f"- status: `{overall}`",
        f"- selected_scenarios: {len(selected)}",
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
                    "- required_follow_up: trace the current route/symbol call chain, quote the abnormal code logic, classify the root cause, and propose the correct repair logic before changing production code",
                    "",
                    "```text",
                    (result.get("stdout", "") or "")[-4000:],
                    (result.get("stderr", "") or "")[-4000:],
                    "```",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--scenario", action="append", default=[], help="Run an exact affected scenario; repeat as needed.")
    parser.add_argument("--all", action="store_true", help="Run every active scenario in this unit only after explicit user authorization.")
    parser.add_argument("--allow-broad", action="store_true", help="Allow a repository-wide command only after explicit user authorization.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--keep-history", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    unit_id = slugify(args.unit, "unit")
    unit_path = unit_dir(project_root, unit_id)
    map_path = acceptance_map_path(unit_path)
    if not map_path.exists():
        print(f"Missing {map_path}. Confirm the Feature and generate test mappings first.")
        return 2
    mapping = load_yaml(map_path)
    selected = select_scenarios(mapping, args.scenario, args.all)
    if not selected:
        print("No affected acceptance scenarios are selected. Full-module fallback is forbidden.")
        return 2

    context = read_config_context(project_root).get("context", "")
    results = []
    for scenario in selected:
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

    statuses = {result["status"] for result in results}
    if statuses == {"pass"}:
        overall = "incremental_pass"
    elif statuses & {"fail", "error", "timeout"}:
        overall = "fail"
    elif "uncertain" in statuses:
        overall = "uncertain"
    else:
        overall = "pending"

    run_id = now_id()
    excluded_count = max(0, len(mapping.get("scenarios", [])) - len(selected))
    report = render_report(unit_id, run_id, overall, selected, results, excluded_count)
    report_path = unit_path / "reports" / "latest.md"
    write_text(report_path, report)
    if args.keep_history:
        write_text(unit_path / "reports" / "history" / f"{run_id}.md", report)

    by_scenario: dict[str, list[dict]] = {}
    for result in results:
        by_scenario.setdefault(result["scenario_id"], []).append(result)
    for scenario in mapping.get("scenarios", []):
        scenario_results = by_scenario.get(scenario.get("id", ""), [])
        if not scenario_results:
            continue
        scenario["latest_result"] = "pass" if all(item["status"] == "pass" for item in scenario_results) else "not_accepted"
        scenario["latest_report"] = "reports/latest.md"
        if scenario["latest_result"] == "pass":
            scenario["selected"] = False
            scenario["selection_reason"] = "accepted_current_change"
            scenario["repair_state"] = "not_required"
        else:
            scenario["repair_state"] = "awaiting_diagnosis"
    write_yaml(map_path, mapping)

    print(f"Wrote incremental acceptance report: {report_path}")
    print(f"Status: {overall}")
    return 0 if overall == "incremental_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
