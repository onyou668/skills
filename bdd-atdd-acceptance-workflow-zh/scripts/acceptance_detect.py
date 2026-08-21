#!/usr/bin/env python3
"""Detect project language, test tools, BDD tools, and acceptance context."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from acceptance_common import acceptance_root, read_config_context, read_text


TEXT_SUFFIXES = {".go", ".py", ".js", ".ts", ".tsx", ".java", ".rs", ".kt", ".dart", ".cs", ".php", ".yml", ".yaml", ".toml", ".json", ".xml"}
IGNORED_DIRS = {".git", "node_modules", "vendor", "target", "dist", "build", ".acceptance", "temp", "tmp"}


def file_exists(root: Path, *names: str) -> bool:
    return any((root / name).exists() for name in names)


def find_first(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.exists():
        return direct
    for path in root.rglob(name):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        return path
    return None


def read_if_exists(path: Path) -> str:
    return read_text(path) if path.exists() and path.is_file() else ""


def module_dir(root: Path, path: Path | None) -> str:
    return path.parent.relative_to(root).as_posix() if path else ""


def package_json(path: Path | None) -> dict:
    if path is None or not path.exists():
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
    seen: set[tuple[str, str, str]] = set()
    scanned = 0
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
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
                key = (str(path.relative_to(root)), match.group(1).upper(), match.group(2))
                if key in seen:
                    continue
                seen.add(key)
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


def scan_local_test_styles(root: Path, max_files: int = 800) -> dict:
    styles: dict[str, list[dict]] = {}
    scanned = 0
    patterns = {
        "go_httptest": ["httptest.NewRecorder", "httptest.NewRequest", "httptest.NewServer"],
        "go_gin_handler": ["gin.CreateTestContext"],
        "go_sqlmock": ["sqlmock.New", "github.com/DATA-DOG/go-sqlmock"],
        "python_test_client": ["TestClient(", ".test_client()", "APIClient("],
        "node_supertest": ["supertest", "request(app)", "request(server)"],
        "java_mockmvc": ["MockMvc", "WebTestClient"],
        "rust_http_test": ["axum::Router", "actix_web::test", "rocket::local"],
        "fake_http": ["httptest.NewServer", "MockTransport", "responses.activate", "nock(", "wiremock"],
    }
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        scanned += 1
        if scanned > max_files:
            break
        try:
            text = read_text(path)
        except Exception:
            continue
        for style, needles in patterns.items():
            if any(needle in text for needle in needles):
                styles.setdefault(style, []).append({"file": str(path.relative_to(root))})
    return {key: value[:20] for key, value in sorted(styles.items())}


def scan_local_scripts(root: Path, limit: int = 200) -> list[dict]:
    results: list[dict] = []
    script_dirs = {"scripts", "script", "cmd", "tools", "bin", "jobs", "tasks"}
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
            continue
        if not (set(path.parts) & script_dirs or path.suffix in {".ps1", ".sh", ".bat", ".cmd"}):
            continue
        if path.suffix not in TEXT_SUFFIXES and path.suffix not in {".ps1", ".sh", ".bat", ".cmd"}:
            continue
        results.append({"file": str(path.relative_to(root)), "suffix": path.suffix})
    return results


def scan_middleware_config_hints(root: Path, limit: int = 100) -> list[dict]:
    """Return config file paths and dependency kinds without exposing secrets."""
    results: list[dict] = []
    needles = {
        "mysql": ["mysql", "mariadb"],
        "postgres": ["postgres", "postgresql"],
        "redis": ["redis"],
        "kafka": ["kafka"],
        "mq": ["rabbitmq", "amqp"],
        "object_storage": ["minio", "s3"],
    }
    candidate_names = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", ".env.test", ".env.local"}
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
            continue
        lowered_name = path.name.lower()
        if lowered_name not in candidate_names and not any(token in lowered_name for token in ["test", "local", "sandbox", "docker"]):
            continue
        try:
            lowered = read_text(path).lower()
        except Exception:
            continue
        kinds = sorted(name for name, values in needles.items() if any(value in lowered for value in values))
        if kinds:
            results.append({"file": str(path.relative_to(root)), "dependencies": kinds})
    return results


def detect(root: Path) -> dict:
    package_path = find_first(root, "package.json")
    pyproject_path = find_first(root, "pyproject.toml")
    requirements_path = find_first(root, "requirements.txt") or find_first(root, "requirements-dev.txt")
    gradle_path = find_first(root, "build.gradle") or find_first(root, "build.gradle.kts")
    pubspec_path = find_first(root, "pubspec.yaml")
    composer_path = find_first(root, "composer.json")
    csproj_path = next((path for path in root.rglob("*.csproj") if not any(part in IGNORED_DIRS for part in path.parts)), None)
    kotlin_path = next((path for path in root.rglob("*.kt") if not any(part in IGNORED_DIRS for part in path.parts)), None)
    pkg = package_json(package_path)
    pyproject = read_if_exists(pyproject_path) if pyproject_path else ""
    requirements = read_if_exists(requirements_path) if requirements_path else ""
    go_mod = find_first(root, "go.mod")
    cargo_path = find_first(root, "Cargo.toml")
    pom_path = find_first(root, "pom.xml")
    cargo = read_if_exists(cargo_path) if cargo_path else ""
    pom = read_if_exists(pom_path) if pom_path else ""
    gradle = read_if_exists(gradle_path) if gradle_path else ""

    languages = []
    if go_mod:
        languages.append("go")
    if pyproject_path or requirements_path or find_first(root, "setup.py") or find_first(root, "pytest.ini"):
        languages.append("python")
    if package_path:
        languages.append("node")
    if pom_path or gradle_path:
        languages.append("java")
    if kotlin_path:
        languages.append("kotlin")
    if cargo_path:
        languages.append("rust")
    if pubspec_path:
        languages.append("flutter")
    if csproj_path:
        languages.append("dotnet")
    if composer_path:
        languages.append("php")

    package_managers = []
    if go_mod:
        package_managers.append("go")
    if find_first(root, "pnpm-lock.yaml"):
        package_managers.append("pnpm")
    elif find_first(root, "yarn.lock"):
        package_managers.append("yarn")
    elif find_first(root, "package-lock.json") or package_path:
        package_managers.append("npm")
    if find_first(root, "poetry.lock"):
        package_managers.append("poetry")
    elif pyproject_path or requirements_path:
        package_managers.append("pip")
    if pom_path:
        package_managers.append("maven")
    if gradle_path or find_first(root, "gradlew") or find_first(root, "gradlew.bat"):
        package_managers.append("gradle")
    if cargo_path:
        package_managers.append("cargo")

    test_frameworks = []
    bdd_tools = []
    if "go" in languages:
        test_frameworks.append("go test")
        if go_mod and "godog" in read_if_exists(go_mod):
            bdd_tools.append("godog")
    if "python" in languages:
        if "pytest" in pyproject or "pytest" in requirements or find_first(root, "pytest.ini") or find_first(root, "conftest.py"):
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

    candidate_adapters = [language for language in ["go", "python", "node", "java", "kotlin", "rust", "flutter", "dotnet", "php"] if language in languages]

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
        "modules": {
            "go": module_dir(root, go_mod),
            "python": module_dir(root, pyproject_path or requirements_path),
            "node": module_dir(root, package_path),
            "rust": module_dir(root, cargo_path),
            "java": module_dir(root, pom_path or gradle_path),
            "kotlin": module_dir(root, gradle_path or kotlin_path),
            "flutter": module_dir(root, pubspec_path),
            "dotnet": module_dir(root, csproj_path),
            "php": module_dir(root, composer_path),
        },
        "test_frameworks": sorted(set(test_frameworks)),
        "bdd_tools": sorted(set(bdd_tools)),
        "suggested_commands": [],
        "candidate_adapters": candidate_adapters,
        "command_policy": {
            "broad_repository_runs_forbidden": True,
            "exact_scenario_or_file_selector_required": True,
        },
        "codegraph_available": (root / ".codegraph").exists(),
        "route_hints": scan_route_hints(root),
        "local_test_styles": scan_local_test_styles(root),
        "local_scripts": scan_local_scripts(root),
        "middleware_config_hints": scan_middleware_config_hints(root),
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
