#!/usr/bin/env python3
"""Shared helpers for the BDD/ATDD acceptance workflow scripts.

The helpers intentionally use only the Python standard library. They parse the
strict acceptance.md subset used by this skill and write deterministic artifacts.
They do not infer business expectations from implementation code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


VALID_STATUSES = {"active", "draft", "pending", "uncertain", "deprecated", "manual"}
VALID_PRIORITIES = {"must", "should", "nice"}
VALID_TYPES = {
    "auto",
    "unit_test",
    "integration_test",
    "http_api",
    "command",
    "command_db",
    "command_redis",
    "command_mq",
    "file_output",
    "log_output",
    "worker_job",
    "scheduled_job",
    "manual_review",
}

FIELD_ALIASES = {
    "状态": "status",
    "Status": "status",
    "来源": "source",
    "Source": "source",
    "优先级": "priority",
    "Priority": "priority",
    "类型": "type",
    "Type": "type",
    "标签": "tags",
    "Tags": "tags",
    "Command": "command",
    "命令": "command",
    "Runner": "runner",
    "执行器": "runner",
}

SECTION_NAMES = {"Given", "When", "Then", "Data", "Notes"}


@dataclass
class Scenario:
    id: str
    title: str
    status: str = "active"
    source: str = "manual"
    priority: str = "must"
    type: str = "auto"
    tags: str = ""
    given: list[str] = field(default_factory=list)
    when: list[str] = field(default_factory=list)
    then: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    command: str = ""
    runner: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)

    def text_for_hash(self) -> str:
        payload = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "source": self.source,
            "priority": self.priority,
            "type": self.type,
            "tags": self.tags,
            "given": self.given,
            "when": self.when,
            "then": self.then,
            "data": self.data,
            "notes": self.notes,
            "command": self.command,
            "runner": self.runner,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def source_hash(self) -> str:
        return hashlib.sha256(self.text_for_hash().encode("utf-8")).hexdigest()[:16]

    def all_text(self) -> str:
        parts = [self.title, self.tags, *self.given, *self.when, *self.then, *self.data, *self.notes]
        return "\n".join(parts)


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def now_id() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def default_locale_from_script() -> str:
    path = str(Path(__file__).resolve()).lower()
    if "-en" in path:
        return "en"
    return "zh"


def slugify(value: str, fallback: str = "unit") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def unit_prefix(unit: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9]+", "-", unit).strip("-").upper()
    if not letters:
        letters = "UNIT"
    return letters


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def acceptance_root(project_root: Path) -> Path:
    default_root = project_root / ".acceptance"
    config = default_root / "config.yaml"
    if not config.exists():
        return default_root
    root_value = None
    for line in read_text(config).splitlines():
        if line.strip().startswith("root:"):
            root_value = line.split(":", 1)[1].strip().strip("\"'")
            break
    if not root_value:
        return default_root
    root_path = Path(root_value)
    return root_path if root_path.is_absolute() else project_root / root_path


def read_config_context(project_root: Path) -> dict[str, Any]:
    root = acceptance_root(project_root)
    config = root / "config.yaml"
    result = {"config_path": str(config), "exists": config.exists(), "root": str(root), "context": ""}
    if not config.exists():
        return result

    lines = read_text(config).splitlines()
    context_lines: list[str] = []
    in_context = False
    context_indent = 0
    for line in lines:
        stripped = line.strip()
        if not in_context and stripped.startswith("context:"):
            after = line.split(":", 1)[1].strip()
            if after in {"|", ">"}:
                in_context = True
                context_indent = len(line) - len(line.lstrip()) + 2
                continue
            result["context"] = after.strip("\"'")
            continue
        if in_context:
            if stripped and (len(line) - len(line.lstrip())) < context_indent:
                break
            context_lines.append(line[context_indent:] if len(line) >= context_indent else "")
    if context_lines:
        result["context"] = "\n".join(context_lines).strip()
    return result


def ensure_base_files(project_root: Path, locale: str = "zh") -> Path:
    root = acceptance_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    config = root / "config.yaml"
    if not config.exists():
        write_text(
            config,
            "version: 1\n"
            "root: .acceptance\n\n"
            "context: |\n\n"
            "project:\n"
            "  language: auto\n"
            "  test_framework: auto\n"
            "  package_manager: auto\n\n"
            "defaults:\n"
            "  feature_enabled: true\n"
            "  generated_dir: generated\n"
            "  fixture_dir: fixtures\n"
            "  report_dir: reports\n\n"
            "execution:\n"
            "  env: test\n"
            "  timeout_seconds: 120\n"
            "  polling:\n"
            "    interval_ms: 500\n"
            "    timeout_seconds: 20\n",
        )
    index = root / "index.yaml"
    if not index.exists():
        write_text(index, "version: 1\nunits: []\n")
    (root / "units").mkdir(exist_ok=True)
    return root


def update_index(root: Path, unit_id: str) -> None:
    index = root / "index.yaml"
    existing = read_text(index) if index.exists() else "version: 1\nunits: []\n"
    if f"id: {unit_id}" in existing or f"- {unit_id}" in existing:
        return
    if "units: []" in existing:
        updated = existing.replace("units: []", f"units:\n  - id: {unit_id}\n    path: units/{unit_id}")
    else:
        if not existing.endswith("\n"):
            existing += "\n"
        updated = existing + f"  - id: {unit_id}\n    path: units/{unit_id}\n"
    write_text(index, updated)


def unit_dir(project_root: Path, unit_id: str, locale: str = "zh") -> Path:
    root = ensure_base_files(project_root, locale)
    safe_unit = slugify(unit_id, "unit")
    path = root / "units" / safe_unit
    path.mkdir(parents=True, exist_ok=True)
    for child in ["compiled", "generated", "fixtures", "reports"]:
        (path / child).mkdir(exist_ok=True)
    update_index(root, safe_unit)
    return path


def acceptance_template(unit_id: str, locale: str = "zh") -> str:
    if locale == "en":
        title = f"# {unit_id} Acceptance\n\n"
        return (
            title +
            "## Metadata\n\n"
            f"Module: {unit_id}\n"
            "Specs:\n"
            "- auto\n\n"
            "Code:\n"
            "- auto\n\n"
            "Entry:\n"
            "- auto\n\n"
            "## Acceptance Scenarios\n"
        )
    return (
        f"# {unit_id} 验收文档\n\n"
        "## 元信息\n\n"
        f"模块: {unit_id}\n"
        "关联规范:\n"
        "- auto\n\n"
        "关联代码:\n"
        "- auto\n\n"
        "关联入口:\n"
        "- auto\n\n"
        "## 验收场景\n"
    )


def parse_acceptance_md(path: Path) -> tuple[str, list[Scenario]]:
    if not path.exists():
        return path.stem, []
    text = read_text(path)
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    feature_title = title_match.group(1).strip() if title_match else path.parent.name
    heading_matches = list(re.finditer(r"^###\s+([A-Za-z0-9_-]+)\s+(.+)$", text, re.M))
    scenarios: list[Scenario] = []
    for idx, match in enumerate(heading_matches):
        start = match.end()
        end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(text)
        body = text[start:end]
        scenario = Scenario(id=match.group(1).strip(), title=match.group(2).strip())
        current_section: str | None = None
        for raw_line in body.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            section = stripped[:-1] if stripped.endswith(":") else ""
            if section in SECTION_NAMES:
                current_section = section.lower()
                continue
            field_match = re.match(r"^([^:：]+)[:：]\s*(.*)$", stripped)
            if field_match and current_section is None:
                key = FIELD_ALIASES.get(field_match.group(1).strip())
                value = field_match.group(2).strip()
                if key:
                    setattr(scenario, key, value)
                    continue
                scenario.raw_fields[field_match.group(1).strip()] = value
                continue
            if field_match and field_match.group(1).strip() in FIELD_ALIASES:
                key = FIELD_ALIASES[field_match.group(1).strip()]
                setattr(scenario, key, field_match.group(2).strip())
                current_section = None
                continue
            if current_section:
                item = stripped[2:].strip() if stripped.startswith("- ") else stripped
                getattr(scenario, current_section).append(item)
        scenario.status = normalize_choice(scenario.status, VALID_STATUSES, "active")
        scenario.priority = normalize_choice(scenario.priority, VALID_PRIORITIES, "must")
        scenario.type = normalize_choice(scenario.type, VALID_TYPES, "auto")
        scenarios.append(scenario)
    return feature_title, scenarios


def normalize_choice(value: str, valid: set[str], default: str) -> str:
    normalized = (value or default).strip().lower()
    normalized = normalized.replace("-", "_")
    return normalized if normalized in valid else default


def next_scenario_id(scenarios: list[Scenario], unit_id: str) -> str:
    prefix = f"AC-{unit_prefix(unit_id)}-"
    max_number = 0
    for scenario in scenarios:
        if scenario.id.upper().startswith(prefix):
            tail = scenario.id[len(prefix) :]
            if tail.isdigit():
                max_number = max(max_number, int(tail))
    return f"{prefix}{max_number + 1:03d}"


def render_scenario_md(scenario: Scenario, locale: str = "zh") -> str:
    labels = {
        "zh": {"status": "状态", "source": "来源", "priority": "优先级", "type": "类型", "tags": "标签"},
        "en": {"status": "Status", "source": "Source", "priority": "Priority", "type": "Type", "tags": "Tags"},
    }[locale]
    parts = [
        f"### {scenario.id} {scenario.title}",
        "",
        f"{labels['status']}: {scenario.status}",
        f"{labels['source']}: {scenario.source}",
        f"{labels['priority']}: {scenario.priority}",
        f"{labels['type']}: {scenario.type}",
    ]
    if scenario.tags:
        parts.append(f"{labels['tags']}: {scenario.tags}")
    for name, items in [
        ("Given", scenario.given),
        ("When", scenario.when),
        ("Then", scenario.then),
        ("Data", scenario.data),
        ("Notes", scenario.notes),
    ]:
        if name in {"Data", "Notes"} and not items:
            continue
        parts.extend(["", f"{name}:"])
        parts.extend(f"- {item}" for item in items)
    return "\n".join(parts).rstrip() + "\n"


def append_scenario(path: Path, scenario: Scenario, locale: str = "zh") -> None:
    if not path.exists():
        write_text(path, acceptance_template(path.parent.name, locale) + "\n")
    text = read_text(path)
    if not text.endswith("\n"):
        text += "\n"
    if "## 验收场景" not in text and "## Acceptance Scenarios" not in text:
        text += "\n## 验收场景\n" if locale == "zh" else "\n## Acceptance Scenarios\n"
    text += "\n" + render_scenario_md(scenario, locale)
    write_text(path, text)


def scenario_similar(existing: Scenario, candidate: Scenario) -> bool:
    a = compact_text(existing.title + existing.all_text())
    b = compact_text(candidate.title + candidate.all_text())
    if not a or not b:
        return False
    return a in b or b in a or compact_text(existing.title) == compact_text(candidate.title)


def render_feature(feature_title: str, scenarios: list[Scenario]) -> str:
    lines = [f"Feature: {feature_title}", ""]
    for scenario in scenarios:
        if scenario.status not in {"active", "pending", "uncertain"}:
            continue
        lines.append(f"  Scenario: {scenario.id} {scenario.title}")
        add_gwt_lines(lines, "Given", scenario.given)
        add_gwt_lines(lines, "When", scenario.when)
        add_gwt_lines(lines, "Then", scenario.then)
        if scenario.status in {"pending", "uncertain"}:
            lines.append(f"    And acceptance status is {scenario.status}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def add_gwt_lines(lines: list[str], keyword: str, items: list[str]) -> None:
    if not items:
        lines.append(f"    {keyword} TODO")
        return
    for idx, item in enumerate(items):
        lines.append(f"    {keyword if idx == 0 else 'And'} {item}")


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def write_normalized_yaml(path: Path, unit_id: str, feature_title: str, scenarios: list[Scenario]) -> None:
    lines = ["version: 1", f"unit_id: {scalar(unit_id)}", f"title: {scalar(feature_title)}", "scenarios:"]
    for s in scenarios:
        lines.extend(
            [
                f"  - id: {scalar(s.id)}",
                f"    title: {scalar(s.title)}",
                f"    status: {scalar(s.status)}",
                f"    source: {scalar(s.source)}",
                f"    priority: {scalar(s.priority)}",
                f"    type: {scalar(s.type)}",
                f"    source_hash: {s.source_hash()}",
                "    given:",
            ]
        )
        lines.extend(f"      - {scalar(item)}" for item in s.given)
        lines.append("    when:")
        lines.extend(f"      - {scalar(item)}" for item in s.when)
        lines.append("    then:")
        lines.extend(f"      - {scalar(item)}" for item in s.then)
    write_text(path, "\n".join(lines) + "\n")


def dump_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def run_command(command: str, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    started = datetime.now()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": round((datetime.now() - started).total_seconds(), 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timeout": True,
            "duration_seconds": round((datetime.now() - started).total_seconds(), 3),
        }


def command_is_dangerous(command: str) -> bool:
    lowered = command.lower()
    forbidden = [
        "rm -rf",
        "remove-item -recurse",
        "drop database",
        "truncate table",
        "kubectl delete",
        "docker compose down -v",
        "docker-compose down -v",
        "format ",
        "del /s",
        "rmdir /s",
    ]
    return any(item in lowered for item in forbidden)


def shell_quote(value: str) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)
