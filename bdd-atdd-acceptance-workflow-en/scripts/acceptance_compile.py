#!/usr/bin/env python3
"""Compile confirmed acceptance.md into feature, bindings, lock, and scaffolds."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from acceptance_common import (
    Scenario,
    default_locale_from_script,
    dump_json,
    parse_acceptance_md,
    read_config_context,
    render_feature,
    scalar,
    slugify,
    unit_dir,
    write_normalized_yaml,
    write_text,
)
from acceptance_detect import detect


def scenario_test_name(scenario: Scenario) -> str:
    words = re.findall(r"[A-Za-z0-9]+", scenario.id.title())
    return "TestAcceptance" + "".join(words or ["Scenario"])


def go_module_prefix(detection: dict) -> str:
    module = detection.get("modules", {}).get("go", "")
    return module.replace("\\", "/").strip("./")


def go_package_for_selected(selected: str, detection: dict) -> str:
    module = go_module_prefix(detection)
    style_files: list[str] = []
    for style_name in ["go_gin_handler", "go_httptest", "go_sqlmock"]:
        style_files.extend(item.get("file", "") for item in detection.get("local_test_styles", {}).get(style_name, []))
    route_files = [item.get("file", "") for item in detection.get("route_hints", [])]
    handler_files = [item for item in [*style_files, *route_files] if "handler" in item.lower() or "handlers" in item.lower()]
    chosen = handler_files[0] if handler_files else style_files[0] if style_files else route_files[0] if route_files else ""
    if chosen and "/" in chosen.replace("\\", "/"):
        parent = str(Path(chosen).parent).replace("\\", "/")
        if module and parent.startswith(module + "/"):
            return "./" + parent[len(module) + 1 :]
        return "./" + parent
    return "./..."


def local_command_preview(selected: str, detection: dict, scenario: Scenario) -> str:
    if "go" in detection.get("languages", []):
        module = go_module_prefix(detection)
        package = go_package_for_selected(selected, detection)
        command = f"go test -v {package} -run {scenario_test_name(scenario)} -count=1"
        return f"cd {module} && {command}" if module else command
    if "python" in detection.get("languages", []):
        return f"pytest -k {scenario_test_name(scenario)}"
    if "node" in detection.get("languages", []):
        pm = "pnpm" if "pnpm" in detection.get("package_managers", []) else "yarn" if "yarn" in detection.get("package_managers", []) else "npm"
        return f"{pm} test -- {scenario_test_name(scenario)}"
    if "java" in detection.get("languages", []):
        return f"mvn test -Dtest={scenario_test_name(scenario)}"
    if "rust" in detection.get("languages", []):
        return f"cargo test {scenario_test_name(scenario)}"
    return detection.get("suggested_commands", [""])[0] if detection.get("suggested_commands") else ""


def suggested_runner_path(selected: str, detection: dict, scenario: Scenario) -> str:
    stem = scenario.id.lower().replace("-", "_") + "_acceptance_test"
    module = go_module_prefix(detection)
    if "go" in detection.get("languages", []):
        package = go_package_for_selected(selected, detection).strip("./")
        parts = [part for part in [module, package, f"{stem}.go"] if part]
        return "/".join(parts)
    if "python" in detection.get("languages", []):
        return f"tests/acceptance/test_{stem}.py"
    if "node" in detection.get("languages", []):
        ext = "ts" if any(str(item.get("file", "")).endswith(".ts") for item in detection.get("route_hints", [])) else "js"
        return f"tests/acceptance/{stem}.{ext}"
    if "java" in detection.get("languages", []):
        return f"src/test/java/acceptance/{scenario_test_name(scenario)}.java"
    if "rust" in detection.get("languages", []):
        return f"tests/{stem}.rs"
    return f".acceptance/units/{slugify(scenario.id, 'scenario')}/generated/{stem}.txt"


def select_method(scenario: Scenario, detection: dict) -> tuple[str, str, str]:
    if scenario.type != "auto":
        selected = scenario.type
        reason = f"acceptance.md explicitly sets type={scenario.type}."
    else:
        text = scenario.all_text().lower()
        languages = detection.get("languages", [])
        route_hints = detection.get("route_hints", [])
        styles = detection.get("local_test_styles", {})
        if any(word in text for word in ["cli", "command", "script", "脚本", "命令", "批处理"]):
            selected = "local_script_test"
            reason = "Scenario targets a script/command workflow; acceptance must execute existing local code or script with fixtures."
        elif any(word in text for word in ["worker", "job", "queue", "mq", "消费者", "队列", "异步", "定时"]):
            selected = "async_acceptance"
            reason = "Scenario targets worker/job or asynchronous side effects; acceptance must trigger local worker code and poll observable side effects."
        elif route_hints and any(word in text for word in ["api", "http", "接口", "请求", "响应", "登录", "login"]):
            if "go" in languages and ("go_gin_handler" in styles or "go_httptest" in styles):
                style_names = []
                if "go_httptest" in styles:
                    style_names.append("httptest")
                if "go_gin_handler" in styles:
                    style_names.append("Gin handler")
                if "go_sqlmock" in styles:
                    style_names.append("sqlmock")
                style_text = "/".join(style_names) or "local Go test"
                selected = "go_handler_test"
                reason = f"Project exposes HTTP routes and existing Go {style_text} test style; validate the local handler/router, not a remote HTTP endpoint."
            else:
                selected = "local_handler_test"
                reason = "Scenario targets an HTTP business entrypoint; validate through a local handler/router/test client, not a remote endpoint."
        elif any(word in text for word in ["db", "mysql", "redis", "mq", "数据库", "表", "缓存"]):
            selected = "integration_test"
            reason = "Scenario mentions persistence or infrastructure side effects; use local fixtures, sqlmock, temporary DB, fake Redis/MQ, or test containers."
        elif languages:
            selected = "go_unit_test" if "go" in languages else "unit_test"
            reason = "Scenario appears to target core rule/boundary behavior; use the existing local language test stack."
        else:
            selected = "manual_review"
            reason = "No supported project language or execution entry point was detected."
    command = local_command_preview(selected, detection, scenario)
    return selected, reason, command


def write_bindings_yaml(path: Path, unit_id: str, bindings: list[dict]) -> None:
    lines = ["version: 1", f"unit_id: {unit_id}", "", "scenarios:"]
    for binding in bindings:
        lines.extend(
            [
                f"  {binding['id']}:",
                f"    status: {binding['status']}",
                f"    selected_type: {binding['selected_type']}",
                "    execution_scope: local",
                "    remote: false",
                f"    reason: {binding['reason']!r}",
                f"    command: {binding['command']!r}",
                f"    runner: {binding['runner']!r}",
                f"    plan_doc: {binding['plan_doc']!r}",
                f"    execution_plan: {binding['execution_plan']!r}",
                "    assertions:",
            ]
        )
        for assertion in binding["assertions"]:
            lines.append(f"      - {assertion!r}")
    write_text(path, "\n".join(lines) + "\n")


def yaml_dump(value, indent: int = 0) -> list[str]:
    space = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.extend(yaml_dump(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        if not value:
            return [f"{space}[]"]
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.extend(yaml_dump(item, indent + 2))
            else:
                lines.append(f"{space}- {scalar(item)}")
        return lines
    return [f"{space}{scalar(value)}"]


def write_plan_yaml(path: Path, plan: dict) -> None:
    write_text(path, "\n".join(yaml_dump(plan)) + "\n")


def route_hint_for_scenario(scenario: Scenario, detection: dict) -> dict:
    text = scenario.all_text().lower()
    for hint in detection.get("route_hints", []):
        path = str(hint.get("path", "")).lower()
        method = str(hint.get("method", "")).upper()
        if path and (path in text or any(part and part in text for part in path.strip("/").split("/"))):
            return {"type": "http_api", "method": method, "path": hint.get("path"), "source_file": hint.get("file")}
    if detection.get("route_hints") and any(word in text for word in ["api", "http", "接口", "请求", "响应", "登录", "login"]):
        hint = detection["route_hints"][0]
        return {"type": "http_api", "method": hint.get("method"), "path": hint.get("path"), "source_file": hint.get("file")}
    if any(word in text for word in ["script", "脚本", "命令", "统计", "report", "stats"]):
        scripts = detection.get("local_scripts", [])
        script = scripts[0] if scripts else {}
        return {"type": "script", "path": script.get("file", "pending")}
    return {"type": "local_code", "path": "pending"}


def split_case_groups(scenario: Scenario) -> dict:
    raw = scenario.all_text().lower()
    has_allowed_email = any(word in raw for word in ["gmail", "google", "谷歌", "outlook"])
    has_positive = has_allowed_email or any(word in raw for word in ["valid", "success", "allow", "合法", "成功", "允许", "正确"])
    has_negative = ("只支持" in raw or "only" in raw) or any(word in raw for word in ["invalid", "fail", "reject", "非法", "失败", "拒绝", "错误"])
    return {
        "positive_required": True,
        "negative_required": True,
        "boundary_required": True,
        "positive_evidence_present": has_positive,
        "negative_evidence_present": has_negative,
        "missing_or_uncertain": [
            item
            for item, present in {
                "positive examples": has_positive,
                "negative examples": has_negative,
            }.items()
            if not present
        ],
    }


def parse_data_value(value: str):
    text = value.strip()
    if not text:
        return ""
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
            if isinstance(parsed, (str, int, float, bool, list, dict)):
                return parsed
        except Exception:
            pass
    return text


def parse_data_entries(scenario: Scenario) -> dict:
    entries: dict[str, object] = {}
    loose: list[str] = []
    for item in scenario.data:
        if ":" in item:
            key, value = item.split(":", 1)
            entries[slugify(key, "data").replace("-", "_")] = parse_data_value(value)
        else:
            loose.append(item)
    if loose:
        entries["items"] = loose
    return entries


def list_from_entries(entries: dict, names: list[str]) -> list[str]:
    values: list[str] = []
    for name in names:
        value = entries.get(name)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None and value != "":
            values.append(str(value))
    return values


def derive_email_examples(scenario: Scenario, entries: dict) -> dict:
    text = scenario.all_text().lower()
    valid = list_from_entries(entries, ["valid_emails", "allowed_emails", "valid_email", "allowed_email"])
    invalid = list_from_entries(entries, ["invalid_emails", "rejected_emails", "invalid_email", "rejected_email"])
    allowed_domains = list_from_entries(entries, ["allowed_domains", "valid_domains", "allowed_domain", "valid_domain"])
    rejected_domains = list_from_entries(entries, ["rejected_domains", "invalid_domains", "rejected_domain", "invalid_domain"])

    if "gmail" in text or "google" in text or "谷歌" in text:
        allowed_domains.append("gmail.com")
    if "outlook" in text:
        allowed_domains.append("outlook.com")

    allowed_domains = sorted(set(item.strip().lstrip("@") for item in allowed_domains if item.strip()))
    rejected_domains = sorted(set(item.strip().lstrip("@") for item in rejected_domains if item.strip()))

    for domain in allowed_domains:
        valid.append(f"user@{domain}")
    if ("只支持" in text or "only" in text) and allowed_domains and not rejected_domains:
        rejected_domains.extend(["qq.com", "yahoo.com", "example.com"])
    for domain in rejected_domains:
        invalid.append(f"user@{domain}")
    if any(word in text for word in ["email", "邮箱", "mail", "格式", "format"]):
        invalid.extend(["abc", "user@", "@gmail.com"])

    return {
        "valid": sorted(set(valid)),
        "invalid": sorted(set(invalid)),
        "allowed_domains": allowed_domains,
        "rejected_domains": sorted(set(rejected_domains)),
    }


def derive_generic_examples(scenario: Scenario, entries: dict) -> dict:
    return {
        "valid": list_from_entries(entries, ["valid", "valid_values", "allowed", "valid_codes", "success_cases"]),
        "invalid": list_from_entries(entries, ["invalid", "invalid_values", "rejected", "invalid_codes", "fail_cases"]),
    }


def request_payload_for_case(scenario: Scenario, route: dict, value: str, kind: str) -> dict:
    text = scenario.all_text().lower()
    if route.get("type") == "http_api" or any(word in text for word in ["api", "http", "接口", "请求", "响应", "登录", "login"]):
        payload: dict[str, object] = {}
        if any(word in text for word in ["login", "登录"]):
            payload.update(
                {
                    "loginType": "password",
                    "accountType": "email" if any(word in text for word in ["email", "邮箱"]) else "pending_from_code",
                    "account": value or "pending_from_acceptance",
                    "password": "<valid password fixture>",
                }
            )
        elif value:
            payload["value"] = value
        else:
            payload["body"] = "pending_from_acceptance"
        return {
            "content_type": "application/json",
            "method": route.get("method") or "pending_from_code",
            "path": route.get("path") or "pending_from_code",
            "json": payload,
        }
    if any(word in text for word in ["script", "脚本", "命令", "统计", "report", "stats"]):
        return {"args": scenario.data, "fixtures": "derive from acceptance Data and existing script inputs"}
    return {"value": value or "pending_from_acceptance", "kind": kind}


def assertion_for_case(scenario: Scenario, kind: str) -> dict:
    negative = kind in {"negative", "boundary_invalid"}
    return {
        "expected_behavior": scenario.then,
        "response_or_output": {
            "polarity": "failure" if negative else "success_or_continue",
            "http_status": "derive_from_existing_local_response_shape",
            "business_code": "uncertain_from_acceptance_if_not_specified",
            "json_body": "derive_fields_from_current_code_response_model",
            "stdout": "assert when validating CLI/script behavior",
            "stderr": "assert when validating CLI/script errors",
        },
        "side_effects": {
            "db": "assert required DB changes; for early validation failure assert no unexpected writes",
            "redis": "assert required Redis changes or none",
            "mq": "assert required messages or none",
            "files": "assert required file/log output or none",
            "external_calls": "use fake server/mock transport; never call real external services by default",
        },
    }


def build_execution_cases(scenario: Scenario, binding: dict, detection: dict) -> list[dict]:
    route = route_hint_for_scenario(scenario, detection)
    entries = parse_data_entries(scenario)
    examples = derive_email_examples(scenario, entries) if any(word in scenario.all_text().lower() for word in ["email", "邮箱", "mail"]) else derive_generic_examples(scenario, entries)
    raw_cases: list[tuple[str, str, str]] = []
    for idx, value in enumerate(examples["valid"][:3], 1):
        raw_cases.append((f"positive_{idx}", "positive", value))
    for idx, value in enumerate(examples["invalid"][:5], 1):
        raw_cases.append((f"negative_{idx}", "negative", value))
    if not raw_cases:
        raw_cases.append(("case_001", "uncertain", ""))

    cases = []
    for case_id, kind, value in raw_cases:
        cases.append(
            {
                "id": case_id,
                "title": f"{scenario.title} - {kind}",
                "input": {
                    "source": "acceptance.md",
                    "given": scenario.given,
                    "when": scenario.when,
                    "data": entries,
                    "request_or_args": request_payload_for_case(scenario, route, value, kind),
                },
                "execute": {
                    "scope": "local",
                    "remote": False,
                    "mode": binding["selected_type"],
                    "business_entrypoint": route,
                    "validation_entrypoint": {
                        "must_be_local_code": True,
                        "selected_type": binding["selected_type"],
                        "command_preview": binding["command"],
                    },
                    "fixtures_or_mocks": {
                        "db": "use existing local test helper, sqlmock, temporary DB, or fixture",
                        "redis": "use fake/miniredis/test instance when needed",
                        "mq": "use fake queue or in-process consumer trigger when needed",
                        "external_http": "use local fake server/mock transport when needed",
                    },
                    "timeout_seconds": 120,
                    "continue_batch_on_failure": True,
                },
                "assert": assertion_for_case(scenario, kind),
            }
        )
    return cases


def build_execution_plan(unit_id: str, feature_title: str, scenarios: list[Scenario], bindings: list[dict], detection: dict, context_present: bool) -> dict:
    binding_map = {binding["id"]: binding for binding in bindings}
    plans = []
    for scenario in scenarios:
        binding = binding_map[scenario.id]
        case_groups = split_case_groups(scenario)
        plans.append(
            {
                "scenario_id": scenario.id,
                "title": scenario.title,
                "status": binding["status"],
                "scope": "local",
                "remote": False,
                "validation_method": {
                    "type": binding["selected_type"],
                    "reason": binding["reason"],
                },
                "case_coverage": case_groups,
                "code_evidence": {
                    "codegraph_available": detection.get("codegraph_available", False),
                    "languages": detection.get("languages", []),
                    "modules": detection.get("modules", {}),
                    "route_hints": detection.get("route_hints", [])[:10],
                    "local_test_styles": detection.get("local_test_styles", {}),
                    "local_scripts": detection.get("local_scripts", [])[:20],
                },
                "cases": build_execution_cases(scenario, binding, detection),
                "generated_assets_preview": [
                    binding["runner"],
                    binding["plan_doc"],
                    "feature.feature",
                    "bindings.yaml",
                    "compiled/bindings.json",
                    "compiled/execution_plan.preview.json",
                    "compiled/execution_plan.preview.yaml",
                ],
                "command_preview": [binding["command"]] if binding["command"] else [],
                "execution_policy": {
                    "can_modify_business_code": False,
                    "generate_after_feature_confirm": True,
                    "run_after_second_confirm": True,
                    "batch_continue_on_failure": True,
                    "default_remote_execution": False,
                },
                "uncertain": case_groups["missing_or_uncertain"],
            }
        )
    return {
        "version": 1,
        "unit_id": unit_id,
        "title": feature_title,
        "context_present": context_present,
        "plans": plans,
    }


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
                "      - compiled/execution_plan.preview.json",
                "      - compiled/execution_plan.preview.yaml",
                f"      - {binding.get('plan_doc', '')}",
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
            "Generated after feature and execution-plan confirmation. Generate acceptance code from the structured execution plan only; do not modify production code.\n\n"
            f"- selected_type: {binding['selected_type']}\n"
            f"- reason: {binding['reason']}\n"
            f"- command_preview: `{binding['command']}`\n"
            f"- runner: `{binding['runner']}`\n"
            f"- execution_plan: `{binding['execution_plan']}`\n"
            "- scope: local\n"
            "- remote: false\n"
        )
    else:
        text = (
            f"# {scenario.id} {scenario.title}\n\n"
            "这是 feature 和执行计划确认后生成的验收计划索引。只能根据结构化 execution plan 生成验收代码，禁止修改生产业务代码。\n\n"
            f"- selected_type: {binding['selected_type']}\n"
            f"- reason: {binding['reason']}\n"
            f"- command_preview: `{binding['command']}`\n"
            f"- runner: `{binding['runner']}`\n"
            f"- execution_plan: `{binding['execution_plan']}`\n"
            "- scope: local\n"
            "- remote: false\n"
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

    context = read_config_context(project_root)
    detection = detect(project_root)
    active_scenarios = [s for s in scenarios if s.status == "active"]

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
            "runner": scenario.runner or suggested_runner_path(selected, detection, scenario),
            "plan_doc": f"generated/{scenario.id.lower().replace('-', '_')}_acceptance_plan.md",
            "execution_plan": "compiled/execution_plan.preview.yaml",
            "assertions": scenario.then,
            "source_hash": scenario.source_hash(),
            "context_present": bool(context.get("context")),
            "execution_scope": "local",
            "remote": False,
        }
        bindings.append(binding)

    execution_plan = build_execution_plan(unit_id, feature_title or unit_id, scenarios, bindings, detection, bool(context.get("context")))

    if not args.confirmed:
        print("Feature preview confirmation is required before generating validation assets.")
        print("")
        print("Incremental feature preview:")
        print(render_feature(feature_title or unit_id, scenarios))
        print("Execution plan preview:")
        print("\n".join(yaml_dump(execution_plan)))
        print("")
        print("Confirm the feature and execution plan before running again with --confirmed.")
        return 2

    write_normalized_yaml(unit_path / "compiled" / "acceptance.normalized.yaml", unit_id, feature_title or unit_id, scenarios)
    write_text(unit_path / "feature.feature", render_feature(feature_title or unit_id, scenarios))
    dump_json(unit_path / "compiled" / "execution_plan.preview.json", execution_plan)
    write_plan_yaml(unit_path / "compiled" / "execution_plan.preview.yaml", execution_plan)
    for scenario, binding in zip(scenarios, bindings):
        binding["plan_doc"] = write_plan(unit_path, scenario, binding, locale)

    write_bindings_yaml(unit_path / "bindings.yaml", unit_id, bindings)
    dump_json(unit_path / "compiled" / "bindings.json", {"version": 1, "unit_id": unit_id, "scenarios": bindings})
    write_lock(unit_path / "acceptance.lock.yaml", unit_id, scenarios, bindings)

    print("Generated acceptance assets:")
    for rel in [
        "compiled/acceptance.normalized.yaml",
        "compiled/execution_plan.preview.json",
        "compiled/execution_plan.preview.yaml",
        "feature.feature",
        "bindings.yaml",
        "compiled/bindings.json",
        "acceptance.lock.yaml",
    ]:
        print(f"- {unit_path / rel}")
    print("Generated plan docs:")
    for binding in bindings:
        print(f"- {unit_path / binding['plan_doc']}")
    print("Suggested executable acceptance code paths:")
    for binding in bindings:
        print(f"- {project_root / binding['runner']}")
    if active_scenarios:
        print("Suggested commands:")
        for binding in bindings:
            if binding["command"]:
                print(f"- {binding['id']}: {binding['command']}")
        print("Run acceptance only after explicit execution confirmation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
