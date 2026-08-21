#!/usr/bin/env python3
"""Confirm an acceptance intake as the canonical Feature and initialize its module map."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from acceptance_common import (
    Scenario,
    acceptance_map_path,
    context_dependency_mode,
    default_locale_from_script,
    feature_path,
    load_yaml,
    parse_acceptance_md,
    read_config_context,
    render_feature,
    slugify,
    unit_dir,
    write_text,
    write_yaml,
)
from acceptance_detect import detect
from acceptance_feature import parse_feature


DEPENDENCY_TERMS = {
    "mysql": ["mysql"],
    "postgres": ["postgres", "postgresql"],
    "database": ["database", "db", "数据库", "表", "事务"],
    "redis": ["redis", "缓存"],
    "kafka": ["kafka"],
    "mq": ["rabbitmq", " mq", "消息队列", "队列"],
    "object_storage": ["s3", "object storage", "对象存储"],
    "external_http": ["external http", "third-party", "第三方", "外部接口"],
}


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def active_for_feature(scenario: Scenario) -> bool:
    return scenario.status == "active"


def scenario_complete(scenario: Scenario) -> bool:
    items = [*scenario.given, *scenario.when, *scenario.then]
    return bool(scenario.given and scenario.when and scenario.then and not any("todo" in item.lower() for item in items))


def infer_test_level(scenario: Scenario) -> str:
    text = scenario.all_text().lower()
    if any(term in text for term in ["browser", "playwright", "浏览器", "页面", "完整用户流程"]):
        return "e2e"
    if scenario.status == "manual":
        return "manual"
    return "integration"


def detect_dependencies(scenario: Scenario, context: str) -> list[dict]:
    text = scenario.all_text().lower()
    dependencies = []
    for name, terms in DEPENDENCY_TERMS.items():
        if not any(term in text for term in terms):
            continue
        mode = context_dependency_mode(context, name)
        dependencies.append(
            {
                "name": name,
                "mode": mode,
                "reason": "context_explicitly_authorizes_mock" if mode == "mock" else "real_test_required_unless_context_explicitly_authorizes_mock",
            }
        )
    return dependencies


def style_evidence(detection: dict) -> list[dict]:
    evidence = []
    for style, items in detection.get("local_test_styles", {}).items():
        for item in items:
            evidence.append({"style": style, "file": item.get("file", "")})
    return evidence[:20]


def route_for(scenario: Scenario, detection: dict) -> dict:
    text = scenario.all_text().lower()
    tokens = [token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text) if len(token) >= 3]
    for route in detection.get("route_hints", []):
        route_text = f"{route.get('method', '')} {route.get('path', '')}".lower()
        if any(token in route_text for token in tokens):
            return {"type": "http", **route}
    return {"type": "pending_agent_code_scan", "path": "pending"}


def case_ids(scenario: Scenario) -> list[str]:
    found = []
    for item in scenario.data:
        match = re.search(r"(?:case[_ -]?id)\s*[:=]\s*([A-Za-z0-9_-]+)", item, re.I)
        if match:
            found.append(match.group(1))
    return found or ["case-001"]


def existing_scenarios(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = load_yaml(path)
    return {item.get("id", ""): item for item in payload.get("scenarios", []) if item.get("id")}


def feature_scenario(payload: dict) -> Scenario:
    return Scenario(
        id=payload["id"],
        title=payload["title"],
        status="active",
        source="feature",
        given=list(payload.get("given", [])),
        when=list(payload.get("when", [])),
        then=list(payload.get("then", [])),
        data=[f"case_id={case_id}" for case_id in payload.get("case_ids", [])],
        tags=" ".join(payload.get("tags", [])),
    )


def append_feature_scenarios(current: str, unit_id: str, scenarios: list[Scenario]) -> str:
    if not current.strip():
        return render_feature(unit_id, scenarios)
    if not scenarios:
        return current
    rendered = render_feature(unit_id, scenarios).splitlines()
    scenario_block = "\n".join(rendered[2:]).strip()
    return current.rstrip() + "\n\n" + scenario_block + "\n"


def merged_dependencies(previous: list[dict], detected: list[dict]) -> list[dict]:
    merged = {str(item.get("name", "")): dict(item) for item in previous if item.get("name")}
    for item in detected:
        name = str(item.get("name", ""))
        current = merged.get(name, {})
        current.update(item)
        merged[name] = current
    return list(merged.values())


def build_map(unit_id: str, feature_file: Path, feature_text: str, scenarios: list[Scenario], feature_scenarios: dict[str, dict], detection: dict, context: str, mode: str, existing: dict[str, dict], intake_hashes: dict[str, str]) -> dict:
    project_style = style_evidence(detection)
    mapped = []
    for scenario in scenarios:
        previous = existing.get(scenario.id, {})
        parsed_feature = feature_scenarios.get(scenario.id, {})
        canonical_hash = parsed_feature.get("feature_hash", scenario.source_hash())
        changed = previous.get("feature_hash") != canonical_hash
        generated_tests = previous.get("generated_tests", [])
        pending_assertions = [{"then": item, "test_assertion": "pending_generation"} for item in scenario.then]
        assertions = pending_assertions if changed else previous.get("assertion_mapping", pending_assertions)
        dependencies = merged_dependencies(previous.get("dependency_resolution", []), detect_dependencies(scenario, context))
        mapped.append(
            {
                "id": scenario.id,
                "title": scenario.title,
                "status": scenario.status,
                "feature_hash": canonical_hash,
                "intake_hash": intake_hashes.get(scenario.id, previous.get("intake_hash", "")),
                "selected": bool(changed),
                "selection_reason": "feature_added_or_changed" if changed else "not_selected_unchanged",
                "test_level": previous.get("test_level", infer_test_level(scenario)),
                "case_ids": parsed_feature.get("case_ids") or previous.get("case_ids", case_ids(scenario)),
                "business_entrypoint": previous.get("business_entrypoint", route_for(scenario, detection)),
                "validation_entrypoint": previous.get("validation_entrypoint", "pending_agent_code_scan"),
                "style_evidence": previous.get("style_evidence", project_style),
                "dependency_resolution": dependencies,
                "assertion_mapping": assertions,
                "generated_tests": generated_tests,
                "generated_tests_stale": bool(previous.get("generated_tests_stale") or (changed and generated_tests)),
                "repair_state": previous.get("repair_state", "not_required"),
            }
        )
    return {
        "version": 2,
        "unit": unit_id,
        "feature": feature_file.name,
        "feature_hash": hash_text(feature_text),
        "canonical_source": "feature",
        "intake_source": "acceptance.md",
        "mode": mode,
        "project": {
            "languages": detection.get("languages", []),
            "test_frameworks": detection.get("test_frameworks", []),
            "bdd_tools": detection.get("bdd_tools", []),
            "modules": detection.get("modules", {}),
        },
        "context_present": bool(context),
        "execution_policy": {
            "incremental_only": True,
            "full_repository_run_forbidden_by_default": True,
            "real_middleware_required_unless_context_allows_mock": True,
            "production_code_fix_requires_confirmation": True,
        },
        "scenarios": mapped,
    }


def preview_payload(unit_id: str, scenarios: list[Scenario], detection: dict, context: str, mode: str) -> dict:
    return {
        "unit": unit_id,
        "mode": mode,
        "canonical_source_after_confirmation": "feature",
        "languages": detection.get("languages", []),
        "test_frameworks": detection.get("test_frameworks", []),
        "style_evidence": style_evidence(detection),
        "scenarios": [
            {
                "id": scenario.id,
                "status": scenario.status,
                "complete": scenario_complete(scenario),
                "test_level": infer_test_level(scenario),
                "business_entrypoint": route_for(scenario, detection),
                "dependencies": detect_dependencies(scenario, context),
                "assertions": scenario.then,
            }
            for scenario in scenarios
        ],
        "next_step": "generate executable acceptance tests in the current project's existing style, then record their paths and exact selectors in acceptance-map.yaml",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--scenario", help="Compile only one scenario ID.")
    parser.add_argument("--locale", choices=["auto", "zh", "en"], default="auto")
    parser.add_argument("--mode", choices=["manual", "auto"], default="manual")
    parser.add_argument("--confirmed", action="store_true", help="The user confirmed the Feature and generation preview.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    locale = default_locale_from_script() if args.locale == "auto" else args.locale
    unit_id = slugify(args.unit, "unit")
    unit_path = unit_dir(project_root, unit_id, locale)
    _, scenarios = parse_acceptance_md(unit_path / "acceptance.md")
    if args.scenario:
        scenarios = [scenario for scenario in scenarios if scenario.id == args.scenario]
    if not scenarios:
        print("No acceptance scenarios found.")
        return 1

    active = [scenario for scenario in scenarios if active_for_feature(scenario)]
    target_feature = feature_path(unit_path, unit_id)
    target_map = acceptance_map_path(unit_path)
    existing = existing_scenarios(target_map)
    existing_text = target_feature.read_text(encoding="utf-8") if target_feature.exists() else ""
    existing_feature_scenarios: list[dict] = []
    if existing_text:
        _, existing_feature_scenarios, feature_errors = parse_feature(existing_text)
        if feature_errors:
            print("Existing canonical Feature is invalid. Fix it before compiling intake changes:")
            for error in feature_errors:
                print(f"- {error}")
            return 2

    existing_ids = {item["id"] for item in existing_feature_scenarios}
    changed_intake = [scenario for scenario in active if existing.get(scenario.id, {}).get("intake_hash") != scenario.source_hash()]
    conflicts = [scenario for scenario in changed_intake if scenario.id in existing_ids]
    additions = [scenario for scenario in changed_intake if scenario.id not in existing_ids]
    merged_feature = append_feature_scenarios(existing_text, unit_id, additions if existing_text else active)
    _, parsed_feature_scenarios, feature_errors = parse_feature(merged_feature)
    if feature_errors:
        print("Proposed canonical Feature is invalid:")
        for error in feature_errors:
            print(f"- {error}")
        return 2
    context = read_config_context(project_root).get("context", "")
    detection = detect(project_root)
    preview = preview_payload(unit_id, scenarios, detection, context, args.mode)

    print("Feature change preview:")
    if additions or not existing_text:
        print(render_feature(unit_id, additions if existing_text else active))
    else:
        print("(no additive Feature change)")
    print("Generation preview:")
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    if conflicts:
        print("Intake changes conflict with existing canonical Feature scenarios:")
        for scenario in conflicts:
            print(f"- {scenario.id}: edit and confirm the canonical Feature directly, then run acceptance_feature.py")
        return 2

    incomplete = [scenario.id for scenario in active if not scenario_complete(scenario)]
    if incomplete:
        print(f"Cannot confirm incomplete scenarios: {', '.join(incomplete)}")
        return 2
    if args.mode == "manual" and not args.confirmed:
        print("Manual mode requires user confirmation before updating the canonical Feature.")
        return 2

    parsed_by_id = {scenario["id"]: scenario for scenario in parsed_feature_scenarios}
    canonical_scenarios = [feature_scenario(item) for item in parsed_feature_scenarios]
    intake_hashes = {scenario.id: scenario.source_hash() for scenario in active}
    mapping = build_map(unit_id, target_feature, merged_feature, canonical_scenarios, parsed_by_id, detection, context, args.mode, existing, intake_hashes)
    write_text(target_feature, merged_feature)
    write_yaml(target_map, mapping)
    print("Updated canonical acceptance assets:")
    print(f"- {target_feature}")
    print(f"- {target_map}")
    print("No executable acceptance test code has been claimed yet. Generate it in the project's existing test style and record it in acceptance-map.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
