#!/usr/bin/env python3
"""Detect project language, test tools, BDD tools, and acceptance context."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from acceptance_common import acceptance_root, read_config_context, read_text


TEXT_SUFFIXES = {".go", ".py", ".js", ".ts", ".tsx", ".java", ".rs", ".kt", ".yml", ".yaml", ".toml", ".json", ".xml"}


def file_exists(root: Path, *names: str) -> bool:
    return any((root / name).exists() for name in names)


def read_if_exists(path: Path) -> str:
    return read_text(path) if path.exists() and path.is_file() else ""


def package_json(root: Path) -> dict:
    path = root / "package.json"
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def package_has(pkg: dict, name: str) -> bool:
    for field in ["dependencies", "devDependencies", "peerDependencies"]:
        if name in pkg.get(field, {}):
            return True
    return False


def scan_route_hints(root: Path, limit: int = 300, max_files: int = 800) -> list[dict]:
    patterns = [
        re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s*\(\s*[\"']([^\"']+)[\"']", re.I),
        re.compile(r"\.(GET|POST|PUT|PATCH|DELETE)\s*\(\s*[\"']([^\"']+)[\"']", re.I),
        re.compile(r"@(Get|Post|Put|Patch|Delete)Mapping\s*\(\s*[\"']?([^\"')]+)", re.I),
    ]
    results: list[dict] = []
    scanned = 0
    ignored = {".git", "node_modules", "vendor", "target", "dist", "build", ".acceptance"}
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in ignored for part in path.parts):
            continue
        scanned += 1
        if scanned > max_files:
            break
        try:
            text = read_text(path)
        except Exception:
            continue
        for pattern in patterns:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "file": str(path.relative_to(root)),
                        "method": match.group(1).upper(),
                        "path": match.group(2),
                    }
                )
                if len(results) >= limit:
                    break
    return results


def detect(root: Path) -> dict:
    pkg = package_json(root)
    pyproject = read_if_exists(root / "pyproject.toml")
    requirements = "\n".join(read_if_exists(root / name) for name in ["requirements.txt", "requirements-dev.txt"])
    cargo = read_if_exists(root / "Cargo.toml")
    pom = read_if_exists(root / "pom.xml")
    gradle = "\n".join(read_if_exists(root / name) for name in ["build.gradle", "build.gradle.kts"])

    languages = []
    if file_exists(root, "go.mod"):
        languages.append("go")
    if file_exists(root, "pyproject.toml", "requirements.txt", "setup.py", "pytest.ini"):
        languages.append("python")
    if file_exists(root, "package.json"):
        languages.append("node")
    if file_exists(root, "pom.xml", "build.gradle", "build.gradle.kts"):
        languages.append("java")
    if file_exists(root, "Cargo.toml"):
        languages.append("rust")

    package_managers = []
    if file_exists(root, "go.mod"):
        package_managers.append("go")
    if file_exists(root, "pnpm-lock.yaml"):
        package_managers.append("pnpm")
    elif file_exists(root, "yarn.lock"):
        package_managers.append("yarn")
    elif file_exists(root, "package-lock.json", "package.json"):
        package_managers.append("npm")
    if file_exists(root, "poetry.lock"):
        package_managers.append("poetry")
    elif file_exists(root, "pyproject.toml", "requirements.txt"):
        package_managers.append("pip")
    if file_exists(root, "pom.xml"):
        package_managers.append("maven")
    if file_exists(root, "build.gradle", "build.gradle.kts", "gradlew", "gradlew.bat"):
        package_managers.append("gradle")
    if file_exists(root, "Cargo.toml"):
        package_managers.append("cargo")

    test_frameworks = []
    bdd_tools = []
    if "go" in languages:
        test_frameworks.append("go test")
        if "godog" in read_if_exists(root / "go.mod"):
            bdd_tools.append("godog")
    if "python" in languages:
        if "pytest" in pyproject or "pytest" in requirements or file_exists(root, "pytest.ini", "conftest.py"):
            test_frameworks.append("pytest")
        if "pytest-bdd" in pyproject or "pytest-bdd" in requirements:
            bdd_tools.append("pytest-bdd")
        if "behave" in pyproject or "behave" in requirements or file_exists(root, "behave.ini"):
            bdd_tools.append("behave")
    if "node" in languages:
        for tool in ["jest", "vitest", "playwright", "cucumber-js", "@cucumber/cucumber", "supertest"]:
            if package_has(pkg, tool):
                (bdd_tools if "cucumber" in tool else test_frameworks).append(tool)
    if "java" in languages:
        java_text = pom + "\n" + gradle
        if "junit" in java_text.lower():
            test_frameworks.append("JUnit")
        if "cucumber" in java_text.lower():
            bdd_tools.append("Cucumber JVM")
        if "rest-assured" in java_text.lower():
            test_frameworks.append("RestAssured")
    if "rust" in languages:
        test_frameworks.append("cargo test")
        if "cucumber" in cargo:
            bdd_tools.append("cucumber-rs")
        if "assert_cmd" in cargo:
            test_frameworks.append("assert_cmd")

    commands = []
    if "go" in languages:
        commands.append("go test ./...")
    if "python" in languages:
        commands.append("pytest")
    if "node" in languages:
        pm = "pnpm" if "pnpm" in package_managers else "yarn" if "yarn" in package_managers else "npm"
        commands.append(f"{pm} test")
    if "java" in languages:
        commands.append("mvn test" if "maven" in package_managers else "./gradlew test")
    if "rust" in languages:
        commands.append("cargo test")

    context = read_config_context(root)
    return {
        "project_root": str(root),
        "acceptance_root": str(acceptance_root(root)),
        "config": {
            "exists": context["exists"],
            "path": context["config_path"],
            "context_present": bool(context["context"]),
            "context": context["context"],
        },
        "languages": languages,
        "package_managers": package_managers,
        "test_frameworks": sorted(set(test_frameworks)),
        "bdd_tools": sorted(set(bdd_tools)),
        "suggested_commands": commands,
        "codegraph_available": (root / ".codegraph").exists(),
        "route_hints": scan_route_hints(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root to inspect.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    print(json.dumps(detect(root), ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
