#!/usr/bin/env python3
"""Compile confirmed acceptance.md into feature, bindings, lock, and scaffolds."""

from __future__ import annotations

import argparse
from pathlib import Path

from acceptance_common import (
    Scenario,
    default_locale_from_script,
    dump_json,
    parse_acceptance_md,
    read_config_context,
    render_feature,
    shell_quote,
    slugify,
    unit_dir,
    write_normalized_yaml,
    write_text,
)
from acceptance_detect import detect


def select_method(scenario: Scenario, detection: dict) -> tuple[str, str, str]:
    if scenario.type != "auto":
        selected = scenario.type
        reason = f"acceptance.md explicitly sets type={scenario.type}."
    else:
        text = scenario.all_text().lower()
        languages = detection.get("languages", [])
        route_hints = detection.get("route_hints", [])
        if any(word in text for word in ["cli", "command", "script", "脚本", "命令", "批处理"]):
            selected = "command"
            reason = "Scenario targets a CLI/script/command workflow."
        elif any(word in text for word in ["worker", "job", "queue", "mq", "消费者", "队列", "异步", "定时"]):
            selected = "worker_job"
            reason = "Scenario targets worker/job or asynchronous side effects."
        elif route_hints and any(word in text for word in ["api", "http", "接口", "请求", "响应", "登录", "login"]):
            selected = "http_api"
            reason = "Project exposes HTTP route hints and scenario targets interface behavior."
        elif any(word in text for word in ["db", "mysql", "redis", "mq", "数据库", "表", "缓存"]):
            selected = "integration_test"
            reason = "Scenario mentions persistence or infrastructure side effects."
        elif languages:
            selected = "unit_test"
            reason = "Scenario appears to target core rule/boundary behavior; using existing language test stack."
        else:
            selected = "manual_review"
            reason = "No supported project language or execution entry point was detected."
    command = suggested_command(selected, detection)
    return selected, reason, command


def suggested_command(selected: str, detection: dict) -> str:
    commands = detection.get("suggested_commands", [])
    if selected in {"manual_review", "scheduled_job"} and not commands:
        return ""
    return commands[0] if commands else ""


def write_bindings_yaml(path: Path, unit_id: str, bindings: list[dict]) -> None:
    lines = ["version: 1", f"unit_id: {unit_id}", "", "scenarios:"]
    for binding in bindings:
        lines.extend(
            [
                f"  {binding['id']}:",
                f"    status: {binding['status']}",
                f"    selected_type: {binding['selected_type']}",
                f"    reason: {binding['reason']!r}",
                f"    command: {binding['command']!r}",
                f"    runner: {binding['runner']!r}",
                "    assertions:",
            ]
        )
        for assertion in binding["assertions"]:
            lines.append(f"      - {assertion!r}")
    write_text(path, "\n".join(lines) + "\n")


def write_lock(path: Path, unit_id: str, scenarios: list[Scenario], bindings: list[dict]) -> None:
    lines = ["version: 1", f"unit_id: {unit_id}", "scenarios:"]
    binding_map = {item["id"]: item for item in bindings}
    for scenario in scenarios:
        binding = binding_map.get(scenario.id, {})
        lines.extend(
            [
                f"  {scenario.id}:",
                f"    source_hash: {scenario.source_hash()}",
                "    generated_files:",
                "      - feature.feature",
                "      - bindings.yaml",
                "      - compiled/acceptance.normalized.yaml",
                "      - compiled/bindings.json",
                f"      - {binding.get('runner', '')}",
                f"    last_selected_type: {binding.get('selected_type', 'pending')}",
            ]
        )
    write_text(path, "\n".join(lines) + "\n")


def write_plan(unit_path: Path, scenario: Scenario, binding: dict, locale: str) -> str:
    filename = f"{scenario.id.lower().replace('-', '_')}_acceptance_plan.md"
    rel = f"generated/{filename}"
    path = unit_path / rel
    if locale == "en":
        text = (
            f"# {scenario.id} {scenario.title}\n\n"
            "This scaffold was generated after feature confirmation. Replace it with project-specific validation code only when the real code entry point is known.\n\n"
            f"- selected_type: {binding['selected_type']}\n"
            f"- reason: {binding['reason']}\n"
            f"- suggested_command: `{binding['command']}`\n"
        )
    else:
        text = (
            f"# {scenario.id} {scenario.title}\n\n"
            "这是 feature 确认后生成的验收计划脚手架。只有在确认真实代码入口后，才把它替换为项目相关的验证代码。\n\n"
            f"- selected_type: {binding['selected_type']}\n"
            f"- reason: {binding['reason']}\n"
            f"- suggested_command: `{binding['command']}`\n"
        )
    write_text(path, text)
    return rel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--scenario", help="Compile only one scenario id.")
    parser.add_argument("--locale", choices=["auto", "zh", "en"], default="auto")
    parser.add_argument("--confirmed", action="store_true", help="Required: user confirmed the feature preview.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    locale = default_locale_from_script() if args.locale == "auto" else args.locale
    unit_id = slugify(args.unit, "unit")
    unit_path = unit_dir(project_root, unit_id, locale)
    acceptance_file = unit_path / "acceptance.md"
    feature_title, scenarios = parse_acceptance_md(acceptance_file)
    if args.scenario:
        scenarios = [s for s in scenarios if s.id == args.scenario]
    if not scenarios:
        print("No scenarios found.")
        return 1

    if not args.confirmed:
        print("Feature preview confirmation is required before compile.")
        print(render_feature(feature_title or unit_id, scenarios))
        return 2

    context = read_config_context(project_root)
    detection = detect(project_root)
    active_scenarios = [s for s in scenarios if s.status == "active"]
    write_normalized_yaml(unit_path / "compiled" / "acceptance.normalized.yaml", unit_id, feature_title or unit_id, scenarios)
    write_text(unit_path / "feature.feature", render_feature(feature_title or unit_id, scenarios))

    bindings: list[dict] = []
    for scenario in scenarios:
        selected, reason, command = select_method(scenario, detection)
        status = "active" if scenario.status == "active" and command else "pending"
        if scenario.status != "active":
            status = scenario.status
        binding = {
            "id": scenario.id,
            "title": scenario.title,
            "status": status,
            "selected_type": selected,
            "reason": reason,
            "command": scenario.command or command,
            "runner": "",
            "assertions": scenario.then,
            "source_hash": scenario.source_hash(),
            "context_present": bool(context.get("context")),
        }
        binding["runner"] = scenario.runner or write_plan(unit_path, scenario, binding, locale)
        bindings.append(binding)

    write_bindings_yaml(unit_path / "bindings.yaml", unit_id, bindings)
    dump_json(unit_path / "compiled" / "bindings.json", {"version": 1, "unit_id": unit_id, "scenarios": bindings})
    write_lock(unit_path / "acceptance.lock.yaml", unit_id, scenarios, bindings)

    print("Generated acceptance assets:")
    for rel in ["compiled/acceptance.normalized.yaml", "feature.feature", "bindings.yaml", "compiled/bindings.json", "acceptance.lock.yaml"]:
        print(f"- {unit_path / rel}")
    for binding in bindings:
        print(f"- {unit_path / binding['runner']}")
    if active_scenarios:
        print("Suggested commands:")
        for binding in bindings:
            if binding["command"]:
                print(f"- {binding['id']}: {binding['command']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
