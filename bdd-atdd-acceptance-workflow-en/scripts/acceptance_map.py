#!/usr/bin/env python3
"""Maintain scenario-to-test mappings and incremental selection for one acceptance unit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acceptance_common import (
    acceptance_map_path,
    command_is_broad_test_run,
    load_yaml,
    slugify,
    unit_dir,
    write_yaml,
)


def find_scenario(mapping: dict, scenario_id: str) -> dict:
    for scenario in mapping.get("scenarios", []):
        if scenario.get("id") == scenario_id:
            return scenario
    raise ValueError(f"Scenario not found in acceptance-map.yaml: {scenario_id}")


def relative_existing_file(project_root: Path, value: str) -> str:
    path = (project_root / value).resolve()
    try:
        relative = path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("Generated test file must stay inside the project root.") from exc
    if not path.is_file():
        raise ValueError(f"Generated test file does not exist: {relative.as_posix()}")
    return relative.as_posix()


def load_map(project_root: Path, unit_id: str) -> tuple[Path, dict]:
    unit_path = unit_dir(project_root, unit_id)
    path = acceptance_map_path(unit_path)
    if not path.exists():
        raise ValueError(f"Missing {path}. Confirm the Feature with acceptance_compile.py first.")
    return path, load_yaml(path)


def record_test(args: argparse.Namespace, project_root: Path, path: Path, mapping: dict) -> None:
    if command_is_broad_test_run(args.command):
        raise ValueError("Repository-wide test commands are forbidden for incremental acceptance.")
    if command_is_broad_test_run(args.discovery_command):
        raise ValueError("Test discovery must be scoped to the generated file or exact scenario.")
    test_file = relative_existing_file(project_root, args.file)
    scenario = find_scenario(mapping, args.scenario)
    expected_cases = {str(item) for item in scenario.get("case_ids", [])} or {"case-001"}
    if args.case_id not in expected_cases:
        raise ValueError(f"Unknown case_id for {args.scenario}: {args.case_id}. Expected: {', '.join(sorted(expected_cases))}")
    generated = scenario.setdefault("generated_tests", [])
    entry = {
        "case_id": args.case_id,
        "file": test_file,
        "symbol": args.symbol,
        "command": args.command,
        "discovery_command": args.discovery_command,
        "language": args.language,
        "framework": args.framework,
        "test_level": args.test_level,
    }
    key = (args.case_id, test_file, args.symbol)
    replaced = False
    for index, current in enumerate(generated):
        current_key = (current.get("case_id"), current.get("file"), current.get("symbol"))
        if current_key == key:
            generated[index] = entry
            replaced = True
            break
    if not replaced:
        generated.append(entry)
    scenario["selected"] = True
    scenario["selection_reason"] = "generated_test_added_or_updated"
    scenario["test_level"] = args.test_level
    if args.business_entrypoint:
        scenario["business_entrypoint"] = args.business_entrypoint
    if args.validation_entrypoint:
        scenario["validation_entrypoint"] = args.validation_entrypoint
    if args.style_evidence:
        scenario["style_evidence"] = [{"file": item, "source": "project_existing_test"} for item in args.style_evidence]
    if args.assertion:
        provided = set(args.assertion)
        assertions = scenario.get("assertion_mapping", [])
        scenario["assertion_mapping"] = [
            {
                "then": item.get("then", ""),
                "test_assertion": "recorded_in_generated_test" if item.get("then", "") in provided else item.get("test_assertion", "pending_generation"),
            }
            for item in assertions
        ]
    mapped_cases = {str(item.get("case_id", "")) for item in generated}
    assertions_complete = bool(scenario.get("assertion_mapping")) and all(
        item.get("test_assertion") not in {None, "", "pending_generation"} for item in scenario.get("assertion_mapping", [])
    )
    scenario["generated_tests_stale"] = not (expected_cases <= mapped_cases and assertions_complete)
    write_yaml(path, mapping)


def select_scenarios(args: argparse.Namespace, path: Path, mapping: dict) -> None:
    selected = set(args.scenario)
    known = {scenario.get("id") for scenario in mapping.get("scenarios", [])}
    missing = sorted(selected - known)
    if missing:
        raise ValueError(f"Unknown scenarios: {', '.join(missing)}")
    for scenario in mapping.get("scenarios", []):
        scenario["selected"] = scenario.get("id") in selected
        scenario["selection_reason"] = args.reason if scenario["selected"] else "not_selected_unaffected"
    write_yaml(path, mapping)


def clear_selection(path: Path, mapping: dict) -> None:
    for scenario in mapping.get("scenarios", []):
        scenario["selected"] = False
        scenario["selection_reason"] = "not_selected_unaffected"
    write_yaml(path, mapping)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--project-root", default=".")
    result.add_argument("--unit", required=True)
    actions = result.add_subparsers(dest="action", required=True)

    record = actions.add_parser("record-test", help="Record one generated executable acceptance test.")
    record.add_argument("--scenario", required=True)
    record.add_argument("--case-id", required=True)
    record.add_argument("--file", required=True)
    record.add_argument("--symbol", required=True)
    record.add_argument("--command", required=True)
    record.add_argument("--discovery-command", required=True)
    record.add_argument("--language", required=True)
    record.add_argument("--framework", required=True)
    record.add_argument("--test-level", choices=["component", "integration", "e2e"], default="integration")
    record.add_argument("--style-evidence", action="append", default=[])
    record.add_argument("--assertion", action="append", default=[])
    record.add_argument("--business-entrypoint")
    record.add_argument("--validation-entrypoint")

    select = actions.add_parser("select", help="Select only the affected scenarios for the next run.")
    select.add_argument("--scenario", action="append", required=True)
    select.add_argument("--reason", default="affected_by_current_change")
    actions.add_parser("clear-selection", help="Mark every scenario as unaffected/not selected.")
    actions.add_parser("show", help="Print the current module map as JSON.")
    return result


def main() -> int:
    args = parser().parse_args()
    project_root = Path(args.project_root).resolve()
    unit_id = slugify(args.unit, "unit")
    try:
        path, mapping = load_map(project_root, unit_id)
        if args.action == "record-test":
            record_test(args, project_root, path, mapping)
            print(f"Recorded generated acceptance test in {path}")
        elif args.action == "select":
            select_scenarios(args, path, mapping)
            print(f"Updated incremental selection in {path}")
        elif args.action == "clear-selection":
            clear_selection(path, mapping)
            print(f"Cleared incremental selection in {path}")
        else:
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
