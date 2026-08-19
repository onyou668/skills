#!/usr/bin/env python3
"""Initialize acceptance units and sync criteria into acceptance.md.

This script stops at the feature-preview gate. It never generates bindings,
test code, or execution commands.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from acceptance_common import (
    Scenario,
    acceptance_template,
    append_scenario,
    default_locale_from_script,
    ensure_base_files,
    next_scenario_id,
    parse_acceptance_md,
    read_text,
    render_feature,
    scenario_similar,
    slugify,
    unit_dir,
    write_text,
)


def extract_criteria(text: str) -> list[str]:
    lines = text.splitlines()
    active = False
    candidates: list[str] = []
    heading_pattern = re.compile(r"^#{1,4}\s+(.+)$")
    trigger_pattern = re.compile(r"(验收|边界|场景|acceptance|criteria|scenario|boundary)", re.I)
    for line in lines:
        stripped = line.strip()
        heading = heading_pattern.match(stripped)
        if heading:
            active = bool(trigger_pattern.search(heading.group(1)))
            continue
        if not active:
            continue
        item = re.sub(r"^[-*]\s+|\d+[.)]\s+|\[[ xX]\]\s+", "", stripped).strip()
        if item:
            candidates.append(item)
    if candidates:
        return candidates
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paragraphs[:1]


def scenario_from_text(text: str, scenario_id: str, source: str, locale: str, status: str, priority: str, scenario_type: str) -> Scenario:
    title = text.strip().splitlines()[0]
    title = re.sub(r"^[-*]\s+|\d+[.)]\s+", "", title).strip()
    title = title[:80] if len(title) > 80 else title
    if not title:
        title = "待确认验收条件" if locale == "zh" else "Acceptance criterion pending confirmation"
    if locale == "en":
        given = ["the feature context exists"]
        when = [text.strip()]
        then = ["the expected behavior must match this acceptance criterion"]
        notes = ["Review the scenario and confirm the exact expected values before generating validation logic."]
    else:
        given = ["相关业务上下文已存在"]
        when = [text.strip()]
        then = ["系统行为必须满足该验收条件"]
        notes = ["请确认该场景的精确期望值后，再生成验证逻辑。"]
    return Scenario(
        id=scenario_id,
        title=title,
        status=status,
        source=source,
        priority=priority,
        type=scenario_type,
        tags="",
        given=given,
        when=when,
        then=then,
        notes=notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root.")
    parser.add_argument("--unit", required=True, help="Acceptance unit id, such as login.")
    parser.add_argument("--spec", help="Spec markdown file to scan for acceptance criteria.")
    parser.add_argument("--criteria", help="One spoken/manual acceptance criterion.")
    parser.add_argument("--criteria-file", help="File containing one or more criteria.")
    parser.add_argument("--source", default="manual", choices=["spec", "manual", "spoken", "generated"])
    parser.add_argument("--status", default="active")
    parser.add_argument("--priority", default="must")
    parser.add_argument("--type", default="auto")
    parser.add_argument("--locale", choices=["auto", "zh", "en"], default="auto")
    parser.add_argument("--dry-run", action="store_true", help="Print preview without writing acceptance.md.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    locale = default_locale_from_script() if args.locale == "auto" else args.locale
    root = ensure_base_files(project_root, locale)
    unit_id = slugify(args.unit, "unit")
    path = unit_dir(project_root, unit_id, locale) / "acceptance.md"
    if not path.exists() and not args.dry_run:
        write_text(path, acceptance_template(unit_id, locale))

    criteria: list[str] = []
    if args.spec:
        criteria.extend(extract_criteria(read_text((project_root / args.spec).resolve())))
    if args.criteria_file:
        criteria.extend(extract_criteria(read_text((project_root / args.criteria_file).resolve())))
    if args.criteria:
        criteria.append(args.criteria)
    if not criteria:
        print("No acceptance criteria found.")
        return 1

    feature_title, existing = parse_acceptance_md(path)
    added: list[Scenario] = []
    skipped: list[Scenario] = []
    scenarios = list(existing)
    for item in criteria:
        candidate = scenario_from_text(
            item,
            next_scenario_id(scenarios + added, unit_id),
            args.source,
            locale,
            args.status,
            args.priority,
            args.type,
        )
        if any(scenario_similar(s, candidate) for s in scenarios):
            skipped.append(candidate)
            continue
        added.append(candidate)
        scenarios.append(candidate)
        if not args.dry_run:
            append_scenario(path, candidate, locale)

    if added:
        print("Incremental feature preview:")
        print(render_feature(feature_title or unit_id, added))
        print("Waiting for user confirmation before generating bindings or validation code.")
    if skipped:
        print("Similar scenarios already exist; skipped:")
        for scenario in skipped:
            print(f"- {scenario.title}")
    print(f"acceptance_root: {root}")
    print(f"acceptance_file: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
