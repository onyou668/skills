#!/usr/bin/env python3
"""Collect document, spoken, or manual criteria in the acceptance.md intake."""

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


def split_spoken_parts(text: str, locale: str) -> tuple[list[str], list[str], list[str], list[str]]:
    explicit: dict[str, list[str]] = {"given": [], "when": [], "then": []}
    current: str | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip().lstrip("-*0123456789.）) ")
        match = re.match(r"^(Given|When|Then|假设|当|那么)[:：]\s*(.*)$", stripped, re.I)
        if match:
            key = match.group(1).lower()
            current = {"假设": "given", "当": "when", "那么": "then"}.get(key, key)
            if match.group(2).strip():
                explicit[current].append(match.group(2).strip())
            continue
        if current and stripped:
            explicit[current].append(stripped)
    if any(explicit.values()):
        return explicit["given"], explicit["when"], explicit["then"], []

    chunks = [re.sub(r"^(并且|并|且|and)\s*", "", item.strip(), flags=re.I) for item in re.split(r"[，,；;。.\n]+", text) if item.strip()]
    when_words = ["when", "if", "输入", "提交", "请求", "点击", "执行", "触发", "消费", "调用", "时", "当", "如果"]
    then_words = [
        "should",
        "must",
        "return",
        "fail",
        "generated",
        "generate",
        "not generate",
        "success",
        "reject",
        "allow",
        "失败",
        "成功",
        "返回",
        "提示",
        "生成",
        "不生成",
        "拒绝",
        "允许",
        "锁定",
        "写入",
        "发送",
        "更新",
        "删除",
        "创建",
    ]
    when = [re.sub(r"^(when|if|当|如果)\s*", "", chunk, flags=re.I) for chunk in chunks if any(word in chunk.lower() for word in when_words)]
    then = [chunk for chunk in chunks if any(word in chunk.lower() for word in then_words) and chunk not in when]
    if not then:
        then = [chunk for chunk in chunks if any(word in chunk.lower() for word in then_words)]

    if locale == "en":
        given = ["the relevant business context exists"]
        default_then = "the expected behavior is explicit enough to verify"
        missing = "Then is missing a concrete observable business result."
    else:
        given = ["相关业务上下文已存在"]
        default_then = "系统行为必须满足该验收条件"
        missing = "Then 缺少可观察的业务结果。"
    notes = [] if then else [missing]
    return given, when or [text.strip()], then or [default_then], notes


def missing_expectation_notes(text: str, given: list[str], when: list[str], then: list[str], locale: str) -> list[str]:
    lowered = text.lower()
    notes: list[str] = []
    if not given:
        notes.append("Given is missing." if locale == "en" else "Given 缺少前置业务状态。")
    if not when:
        notes.append("When is missing." if locale == "en" else "When 缺少业务动作或事件。")
    if not then:
        notes.append("Then is missing." if locale == "en" else "Then 缺少可观察业务结果。")
    unclear_markers = ["待确认", "不确定", "tbd", "todo", "unclear", "unknown"]
    if any(marker in lowered for marker in unclear_markers):
        notes.append("Expected behavior contains unclear placeholders." if locale == "en" else "验收期望包含待确认占位。")
    if ("多次" in text or "several" in lowered or "multiple" in lowered) and not re.search(r"\d+", text):
        notes.append("Count threshold is missing." if locale == "en" else "次数阈值缺失。")
    if ("锁定" in text or "lock" in lowered) and not re.search(r"\d+\s*(分钟|小时|秒|minute|hour|second|min|h|s)", text, re.I):
        notes.append("Lock duration is missing." if locale == "en" else "锁定时长缺失。")
    if ("错误码" in text or "error code" in lowered or "business code" in lowered) and not re.search(r"[A-Z0-9_.-]{3,}|\d{3,}", text):
        notes.append("Error/business code value is missing." if locale == "en" else "错误码或业务 code 的具体值缺失。")
    return notes


def scenario_from_text(text: str, scenario_id: str, source: str, locale: str, status: str, priority: str, scenario_type: str) -> Scenario:
    title = text.strip().splitlines()[0]
    title = re.sub(r"^[-*]\s+|\d+[.)]\s+", "", title).strip()
    title = title[:80].rstrip() if len(title) > 80 else title
    if not title:
        title = "待确认验收条件" if locale == "zh" else "Acceptance criterion pending confirmation"
    given, when, then, notes = split_spoken_parts(text, locale)
    notes.extend(missing_expectation_notes(text, given, when, then, locale))
    if notes and status == "active":
        status = "uncertain"
    if locale == "en":
        notes.append("Review the scenario and confirm exact expected values before generating validation logic.")
    else:
        notes.append("请确认该场景的精确期望值后，再生成验证逻辑。")
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
        print("Proposed incremental Feature preview:")
        print(render_feature(feature_title or unit_id, added))
        print("acceptance.md is an intake, not the canonical acceptance contract.")
        print("Run acceptance_compile.py to inspect the generation preview. In manual mode, wait for confirmation before updating the canonical Feature.")
    if skipped:
        print("Similar scenarios already exist; skipped:")
        for scenario in skipped:
            print(f"- {scenario.title}")
    print(f"acceptance_root: {root}")
    print(f"acceptance_file: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
