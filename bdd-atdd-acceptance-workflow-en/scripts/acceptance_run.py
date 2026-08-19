#!/usr/bin/env python3
"""Run acceptance commands from compiled/bindings.json and write reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from acceptance_common import (
    command_is_dangerous,
    dump_json,
    load_json,
    now_id,
    read_config_context,
    run_command,
    slugify,
    unit_dir,
    write_text,
)


def write_report_yaml(path: Path, report: dict) -> None:
    lines = [
        f"unit_id: {report['unit_id']}",
        f"run_id: {report['run_id']}",
        f"status: {report['status']}",
        "summary:",
    ]
    for key, value in report["summary"].items():
        lines.append(f"  {key}: {value}")
    lines.append("scenarios:")
    for scenario in report["scenarios"]:
        lines.extend(
            [
                f"  - id: {scenario['id']}",
                f"    status: {scenario['status']}",
                f"    command: {scenario.get('command', '')!r}",
                f"    reason: {scenario.get('reason', '')!r}",
            ]
        )
        if "exit_code" in scenario:
            lines.append(f"    exit_code: {scenario['exit_code']}")
    write_text(path, "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--scenario", help="Run only one scenario id.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--include-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes-dangerous", action="store_true", help="Allow commands that match the dangerous-command blocklist.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    unit_id = slugify(args.unit, "unit")
    unit_path = unit_dir(project_root, unit_id)
    bindings_path = unit_path / "compiled" / "bindings.json"
    if not bindings_path.exists():
        print(f"Missing {bindings_path}. Run acceptance_compile.py --confirmed first.")
        return 1

    context = read_config_context(project_root)
    bindings = load_json(bindings_path)
    scenarios = bindings.get("scenarios", [])
    if args.scenario:
        scenarios = [s for s in scenarios if s.get("id") == args.scenario]
    if not scenarios:
        print("No matching scenarios.")
        return 1

    summary = {"pass": 0, "fail": 0, "skip": 0, "pending": 0, "uncertain": 0}
    results = []
    for scenario in scenarios:
        command = scenario.get("command", "")
        status = scenario.get("status", "pending")
        result = {
            "id": scenario.get("id"),
            "title": scenario.get("title", ""),
            "command": command,
            "reason": scenario.get("reason", ""),
            "selected_type": scenario.get("selected_type", ""),
        }
        if status in {"pending", "uncertain", "manual", "draft", "deprecated"} and not args.include_pending:
            mapped = "pending" if status in {"manual", "draft", "deprecated"} else status
            result["status"] = mapped
            result["reason"] = f"Scenario binding status is {status}; use --include-pending to run pending commands."
            summary[mapped] += 1
        elif not command:
            result["status"] = "pending"
            result["reason"] = "No command is bound to this scenario."
            summary["pending"] += 1
        elif command_is_dangerous(command) and not args.yes_dangerous:
            result["status"] = "uncertain"
            result["reason"] = "Command matched dangerous-command blocklist."
            summary["uncertain"] += 1
        elif args.dry_run:
            result["status"] = "skip"
            result["reason"] = "dry-run"
            summary["skip"] += 1
        else:
            command_result = run_command(command, project_root, args.timeout)
            result.update(command_result)
            if command_result.get("exit_code") == 0:
                result["status"] = "pass"
                summary["pass"] += 1
            else:
                result["status"] = "fail"
                summary["fail"] += 1
        results.append(result)

    overall = "fail" if summary["fail"] else "uncertain" if summary["uncertain"] else "pending" if summary["pending"] else "pass"
    report = {
        "unit_id": unit_id,
        "run_id": now_id(),
        "status": overall,
        "context_present": bool(context.get("context")),
        "summary": summary,
        "scenarios": results,
    }
    report_dir = unit_path / "reports"
    report_json = report_dir / f"{report['run_id']}.json"
    report_yaml = report_dir / f"{report['run_id']}.yaml"
    latest_json = report_dir / "latest.json"
    latest_yaml = report_dir / "latest.yaml"
    dump_json(report_json, report)
    dump_json(latest_json, report)
    write_report_yaml(report_yaml, report)
    write_report_yaml(latest_yaml, report)

    print(f"Report: {report_yaml}")
    print(f"Status: {overall}")
    print(f"Summary: {summary}")
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
