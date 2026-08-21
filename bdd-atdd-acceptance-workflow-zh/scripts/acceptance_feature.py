#!/usr/bin/env python3
"""Validate a directly edited canonical Feature and refresh its module map."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from acceptance_common import acceptance_map_path, feature_path, load_yaml, read_text, slugify, unit_dir, write_yaml


SCENARIO_RE = re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+)$", re.I)
STEP_RE = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+)$", re.I)
ID_RE = re.compile(r"AC-[A-Za-z0-9_-]+", re.I)


def scenario_hash(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def parse_feature(text: str) -> tuple[str, list[dict], list[str]]:
    errors: list[str] = []
    feature_match = re.search(r"^\s*Feature:\s*(.+)$", text, re.M | re.I)
    if not feature_match:
        return "", [], ["Feature: heading is required."]
    title = feature_match.group(1).strip()
    lines = text.splitlines()
    scenarios: list[dict] = []
    tags: list[str] = []
    current: dict | None = None
    current_section = ""
    in_examples = False
    example_headers: list[str] = []

    def finish() -> None:
        nonlocal current, example_headers
        if current is None:
            return
        for section in ["given", "when", "then"]:
            if not current[section]:
                errors.append(f"{current.get('id') or current['title']}: missing {section.title()} step.")
        placeholders = sorted(
            set(
                re.findall(
                    r"<([^>]+)>",
                    "\n".join([current["title"], *current["given"], *current["when"], *current["then"]]),
                )
            )
        )
        if current["outline"]:
            if not current["case_ids"]:
                errors.append(f"{current.get('id') or current['title']}: Scenario Outline requires Examples with a case_id column and at least one row.")
            missing_headers = sorted(set(placeholders) - set(current.get("example_headers", [])))
            if missing_headers:
                errors.append(f"{current.get('id') or current['title']}: Examples is missing columns: {', '.join(missing_headers)}.")
            duplicate_cases = sorted({case_id for case_id in current["case_ids"] if current["case_ids"].count(case_id) > 1})
            if duplicate_cases:
                errors.append(f"{current.get('id') or current['title']}: duplicate case_id values: {', '.join(duplicate_cases)}.")
        elif placeholders:
            errors.append(f"{current.get('id') or current['title']}: placeholders require Scenario Outline and Examples.")
        if current.get("id") and any(item.get("id") == current["id"] for item in scenarios):
            errors.append(f"Duplicate Scenario ID: {current['id']}.")
        current["feature_hash"] = scenario_hash(current)
        scenarios.append(current)
        current = None
        example_headers = []

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("@"):
            if current is not None:
                finish()
            tags = stripped.split()
            continue
        scenario_match = SCENARIO_RE.match(raw)
        if scenario_match:
            finish()
            heading = scenario_match.group(1).strip()
            tag_id = next((ID_RE.search(tag).group(0).upper() for tag in tags if ID_RE.search(tag)), "")
            heading_match = ID_RE.search(heading)
            scenario_id = tag_id or (heading_match.group(0).upper() if heading_match else "")
            if not scenario_id:
                errors.append(f"Scenario requires a stable @AC-... tag or AC ID in its title: {heading}")
            current = {
                "id": scenario_id,
                "title": heading,
                "status": "active",
                "outline": "outline" in raw.lower(),
                "tags": tags,
                "given": [],
                "when": [],
                "then": [],
                "case_ids": [],
                "example_headers": [],
            }
            tags = []
            current_section = ""
            in_examples = False
            continue
        if current is None:
            continue
        if re.match(r"^\s*Examples:\s*$", raw, re.I):
            in_examples = True
            example_headers = []
            continue
        if in_examples and stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not example_headers:
                example_headers = cells
                current["example_headers"] = cells
                if "case_id" not in example_headers:
                    errors.append(f"{current.get('id')}: Examples must contain a case_id column.")
            elif "case_id" in example_headers:
                index = example_headers.index("case_id")
                if index < len(cells) and cells[index]:
                    current["case_ids"].append(cells[index])
            continue
        step = STEP_RE.match(raw)
        if step:
            keyword = step.group(1).lower()
            if keyword in {"given", "when", "then"}:
                current_section = keyword
            elif not current_section:
                errors.append(f"{current.get('id')}: {keyword.title()} appears before Given/When/Then.")
                continue
            current[current_section].append(step.group(2).strip())
    finish()
    if not scenarios:
        errors.append("At least one Scenario is required.")
    return title, scenarios, errors


def refresh_mapping(mapping: dict, parsed: list[dict]) -> dict:
    existing = {scenario.get("id", ""): scenario for scenario in mapping.get("scenarios", [])}
    refreshed = []
    seen = set()
    for feature_scenario in parsed:
        scenario_id = feature_scenario["id"]
        previous = existing.get(scenario_id, {})
        changed = previous.get("feature_hash") != feature_scenario["feature_hash"]
        assertions = (
            [{"then": item, "test_assertion": "pending_generation"} for item in feature_scenario["then"]]
            if changed
            else previous.get("assertion_mapping", [{"then": item, "test_assertion": "pending_generation"} for item in feature_scenario["then"]])
        )
        previous.update(
            {
                "id": scenario_id,
                "title": feature_scenario["title"],
                "status": "active",
                "feature_hash": feature_scenario["feature_hash"],
                "case_ids": feature_scenario["case_ids"] or previous.get("case_ids", ["case-001"]),
                "selected": bool(changed),
                "selection_reason": "feature_directly_added_or_changed" if changed else "not_selected_unchanged",
                "assertion_mapping": assertions,
                "generated_tests": previous.get("generated_tests", []),
                "generated_tests_stale": bool(previous.get("generated_tests_stale") or (changed and previous.get("generated_tests"))),
                "feature_missing": False,
            }
        )
        if changed:
            previous["latest_result"] = "stale"
        refreshed.append(previous)
        seen.add(scenario_id)
    for scenario_id, previous in existing.items():
        if scenario_id in seen:
            continue
        previous["feature_missing"] = True
        previous["selected"] = True
        previous["selection_reason"] = "feature_scenario_missing_review_before_deprecation"
        previous["repair_state"] = "awaiting_feature_review"
        refreshed.append(previous)
    mapping["scenarios"] = refreshed
    mapping["canonical_source"] = "feature"
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--mode", choices=["manual", "auto"], default="manual")
    parser.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    unit_id = slugify(args.unit, "unit")
    unit_path = unit_dir(project_root, unit_id)
    target_feature = feature_path(unit_path, unit_id)
    target_map = acceptance_map_path(unit_path)
    if not target_feature.exists() or not target_map.exists():
        print("Feature and acceptance-map.yaml must exist before direct Feature refresh.")
        return 1
    title, scenarios, errors = parse_feature(read_text(target_feature))
    preview = {"unit": unit_id, "feature_title": title, "scenarios": scenarios, "errors": errors}
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if errors:
        return 2
    if args.mode == "manual" and not args.confirmed:
        print("Manual mode requires confirmation before refreshing generated mappings.")
        return 2
    feature_text = read_text(target_feature)
    mapping = load_yaml(target_map)
    previous_feature_hash = str(mapping.get("feature_hash", ""))
    current_feature_hash = hashlib.sha256(feature_text.encode("utf-8")).hexdigest()[:16]
    previous_revision = int(mapping.get("contract_revision", 0) or 0)
    contract_revision = previous_revision or 1
    if previous_revision and previous_feature_hash != current_feature_hash:
        contract_revision += 1
    mapping = refresh_mapping(mapping, scenarios)
    mapping["version"] = 3
    mapping["feature_hash"] = current_feature_hash
    mapping["contract_revision"] = contract_revision
    mapping["mode"] = args.mode
    write_yaml(target_map, mapping)
    print(f"Refreshed affected scenarios in {target_map}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
