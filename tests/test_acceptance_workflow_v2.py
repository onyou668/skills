import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ZH_SCRIPTS = ROOT / "bdd-atdd-acceptance-workflow-zh" / "scripts"
sys.path.insert(0, str(ZH_SCRIPTS))

from acceptance_common import (  # noqa: E402
    command_is_broad_test_run,
    context_dependency_mode,
    load_yaml,
    unit_dir,
    write_text,
    write_yaml,
)
from acceptance_detect import detect  # noqa: E402
from acceptance_feature import parse_feature  # noqa: E402
from acceptance_run import parse_frontmatter  # noqa: E402


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ZH_SCRIPTS / name), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def detailed_report_from_latest(unit: Path) -> tuple[dict, Path]:
    latest = unit / "reports" / "latest.md"
    metadata = parse_frontmatter(latest)
    return metadata, (latest.parent / metadata["module_report"]).resolve()


class AcceptanceWorkflowV2Tests(unittest.TestCase):
    def test_context_mock_authorization_and_broad_command_policy(self):
        self.assertEqual(context_dependency_mode("Redis 使用本地测试实例。", "redis"), "real")
        self.assertEqual(context_dependency_mode("验收统一使用 mock 模式。", "redis"), "mock")
        self.assertEqual(context_dependency_mode("只有 Kafka 允许使用 fake。", "kafka"), "mock")
        self.assertEqual(context_dependency_mode("只有 Kafka 允许使用 fake。", "redis"), "real")
        self.assertEqual(context_dependency_mode("Redis 不允许使用 mock。", "redis"), "real")
        for command in [
            "go test -count=1 ./...",
            "go test ./internal/auth",
            "pytest",
            "python -m pytest -q",
            "npm test -- --runInBand",
            "mvn -q test",
            "cargo test --release",
            "./gradlew test --info",
            "dotnet test -c Release",
        ]:
            self.assertTrue(command_is_broad_test_run(command), command)
        self.assertFalse(command_is_broad_test_run("pytest tests/test_login.py -k wrong_password"))
        self.assertFalse(command_is_broad_test_run("go test ./internal/auth -run TestLogin/wrong_password"))
        self.assertFalse(command_is_broad_test_run("go test ./internal/auth -list TestLogin"))
        self.assertFalse(command_is_broad_test_run("npm test -- tests/login.test.ts -t wrong-password"))
        self.assertFalse(command_is_broad_test_run("mvn test -Dtest=LoginAcceptanceTest"))
        self.assertFalse(command_is_broad_test_run("cargo test login_wrong_password"))
        self.assertFalse(command_is_broad_test_run("./gradlew test --tests LoginAcceptanceTest"))

    def test_detection_handles_nested_language_modules_without_broad_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_text(
                project / "apps" / "api" / "package.json",
                '{"scripts":{"test":"vitest"},"devDependencies":{"vitest":"1.0.0"}}\n',
            )
            profile = detect(project)
            self.assertIn("node", profile["languages"])
            self.assertEqual(profile["modules"]["node"], "apps/api")
            self.assertIn("vitest", profile["test_frameworks"])
            self.assertEqual(profile["suggested_commands"], [])
            self.assertTrue(profile["command_policy"]["broad_repository_runs_forbidden"])

    def test_feature_parser_keeps_stable_ids_and_case_ids(self):
        _, scenarios, errors = parse_feature(
            "Feature: login\n\n"
            "  @AC-LOGIN-001\n"
            "  Scenario Outline: first\n"
            "    Given one\n"
            "    When two\n"
            "    Then three\n"
            "    Examples:\n"
            "      | case_id | value |\n"
            "      | qq      | one   |\n"
            "      | 163     | two   |\n\n"
            "  @AC-LOGIN-002\n"
            "  Scenario: second\n"
            "    Given four\n"
            "    When five\n"
            "    Then six\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual([item["id"] for item in scenarios], ["AC-LOGIN-001", "AC-LOGIN-002"])
        self.assertEqual(scenarios[0]["case_ids"], ["qq", "163"])

        _, _, errors = parse_feature(
            "Feature: invalid\n\n"
            "  @AC-LOGIN-001\n"
            "  Scenario Outline: duplicate\n"
            "    Given <account>\n"
            "    When login\n"
            "    Then accepted\n"
            "    Examples:\n"
            "      | case_id |\n"
            "      | same    |\n"
            "      | same    |\n\n"
            "  @AC-LOGIN-001\n"
            "  Scenario: duplicate id\n"
            "    Given one\n"
            "    When two\n"
            "    Then three\n"
        )
        self.assertTrue(any("missing columns: account" in error for error in errors), errors)
        self.assertTrue(any("duplicate case_id" in error for error in errors), errors)
        self.assertTrue(any("Duplicate Scenario ID" in error for error in errors), errors)

    def test_confirmed_compile_creates_minimal_module_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            unit = unit_dir(project, "login")
            write_text(
                unit / "acceptance.md",
                "# login\n\n## 验收场景\n\n"
                "### AC-LOGIN-001 错误密码不能登录\n\n"
                "状态: active\n来源: spoken\n优先级: must\n类型: auto\n\n"
                "Given:\n- 用户账号存在\n\nWhen:\n- 用户输入错误密码\n\nThen:\n- 登录失败\n- 不生成 token\n",
            )
            result = run_script(
                "acceptance_compile.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "--confirmed",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((unit / "login.feature").is_file())
            self.assertTrue((unit / "acceptance-map.yaml").is_file())
            self.assertFalse((unit / "compiled").exists())
            self.assertFalse((unit / "bindings.yaml").exists())
            mapping = load_yaml(unit / "acceptance-map.yaml")
            self.assertEqual(mapping["version"], 3)
            self.assertEqual(mapping["contract_revision"], 1)
            self.assertEqual(mapping["canonical_source"], "feature")
            self.assertTrue(mapping["scenarios"][0]["selected"])
            self.assertTrue(mapping["scenarios"][0]["intake_hash"])

    def test_compile_preserves_direct_feature_and_requires_conflict_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            unit = unit_dir(project, "login")
            acceptance = unit / "acceptance.md"
            write_text(
                acceptance,
                "# login\n\n## 验收场景\n\n"
                "### AC-LOGIN-001 原始条件\n\n状态: active\n来源: spoken\n优先级: must\n类型: auto\n\n"
                "Given:\n- 账号存在\n\nWhen:\n- 用户登录\n\nThen:\n- 登录成功\n",
            )
            result = run_script("acceptance_compile.py", "--project-root", str(project), "--unit", "login", "--confirmed")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            feature = unit / "login.feature"
            direct = (
                feature.read_text(encoding="utf-8").rstrip()
                + "\n\n  @AC-LOGIN-002\n"
                "  Scenario: 直接维护的条件\n"
                "    Given 管理员已登录\n"
                "    When 管理员查看审计日志\n"
                "    Then 审计日志可见\n"
            )
            write_text(feature, direct)
            result = run_script("acceptance_feature.py", "--project-root", str(project), "--unit", "login", "--confirmed")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(load_yaml(unit / "acceptance-map.yaml")["contract_revision"], 2)

            with acceptance.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "\n### AC-LOGIN-003 新增口述条件\n\n状态: active\n来源: spoken\n优先级: must\n类型: auto\n\n"
                    "Given:\n- 账号存在\n\nWhen:\n- 用户退出\n\nThen:\n- 会话失效\n"
                )
            result = run_script("acceptance_compile.py", "--project-root", str(project), "--unit", "login", "--confirmed")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            canonical = feature.read_text(encoding="utf-8")
            self.assertIn("AC-LOGIN-001", canonical)
            self.assertIn("AC-LOGIN-002", canonical)
            self.assertIn("AC-LOGIN-003", canonical)
            self.assertEqual(load_yaml(unit / "acceptance-map.yaml")["contract_revision"], 3)

            changed_intake = acceptance.read_text(encoding="utf-8").replace("- 登录成功", "- 登录成功并记录时间")
            write_text(acceptance, changed_intake)
            before = feature.read_text(encoding="utf-8")
            result = run_script("acceptance_compile.py", "--project-root", str(project), "--unit", "login", "--confirmed")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("conflict", result.stdout.lower())
            self.assertEqual(feature.read_text(encoding="utf-8"), before)

    def test_runner_rejects_partial_case_and_pending_assertion_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            unit = unit_dir(project, "login")
            test_file = project / "tests" / "test_login_acceptance.py"
            write_text(test_file, 'print("case_qq case_163")\n')
            exact = subprocess.list2cmdline([sys.executable, str(test_file)])
            mapping = {
                "version": 2,
                "unit": "login",
                "scenarios": [
                    {
                        "id": "AC-LOGIN-001",
                        "status": "active",
                        "selected": True,
                        "case_ids": ["qq", "163"],
                        "business_entrypoint": "POST /login",
                        "validation_entrypoint": "LoginHandler",
                        "style_evidence": [{"file": "tests/test_login_acceptance.py"}],
                        "assertion_mapping": [{"then": "登录成功", "test_assertion": "pending_generation"}],
                        "generated_tests_stale": False,
                        "generated_tests": [
                            {
                                "case_id": "qq",
                                "file": "tests/test_login_acceptance.py",
                                "symbol": "case_qq",
                                "command": exact,
                                "discovery_command": exact,
                            }
                        ],
                    }
                ],
            }
            map_path = unit / "acceptance-map.yaml"
            write_yaml(map_path, mapping)
            result = run_script("acceptance_run.py", "--project-root", str(project), "--unit", "login")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            _, report_path = detailed_report_from_latest(unit)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("163", report)

            mapping["scenarios"][0]["generated_tests"].append(
                {
                    "case_id": "163",
                    "file": "tests/test_login_acceptance.py",
                    "symbol": "case_163",
                    "command": exact,
                    "discovery_command": exact,
                }
            )
            mapping["scenarios"][0]["selected"] = True
            write_yaml(map_path, mapping)
            result = run_script("acceptance_run.py", "--project-root", str(project), "--unit", "login")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            _, report_path = detailed_report_from_latest(unit)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Not every Then", report)

            mapping["scenarios"][0]["assertion_mapping"][0]["test_assertion"] = "assert response success"
            mapping["scenarios"][0]["selected"] = True
            write_yaml(map_path, mapping)
            result = run_script("acceptance_run.py", "--project-root", str(project), "--unit", "login")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_spoken_intake_to_selected_incremental_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            result = run_script(
                "acceptance_sync.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "--source",
                "spoken",
                "--criteria",
                "Given: 用户账号存在\nWhen: 用户输入错误密码\nThen: 登录失败\n不生成 token",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run_script(
                "acceptance_compile.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "--confirmed",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            test_file = project / "tests" / "test_login_acceptance.py"
            write_text(test_file, 'print("test_ac_login_001")\n')
            exact = subprocess.list2cmdline([sys.executable, str(test_file)])
            result = run_script(
                "acceptance_map.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "record-test",
                "--scenario",
                "AC-LOGIN-001",
                "--case-id",
                "case-001",
                "--file",
                "tests/test_login_acceptance.py",
                "--symbol",
                "test_ac_login_001",
                "--command",
                exact,
                "--discovery-command",
                exact,
                "--language",
                "python",
                "--framework",
                "pytest",
                "--style-evidence",
                "tests/test_login_acceptance.py",
                "--assertion",
                "登录失败",
                "--assertion",
                "不生成 token",
                "--business-entrypoint",
                "login behavior",
                "--validation-entrypoint",
                "test_ac_login_001",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run_script(
                "acceptance_run.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            latest, report_path = detailed_report_from_latest(project / ".acceptance" / "units" / "login")
            report = report_path.read_text(encoding="utf-8")
            self.assertEqual(latest["status"], "incremental_pass")
            self.assertEqual(latest["acceptance_status"], "accepted")
            self.assertIn("AC-LOGIN-001/case-001", report)

    def test_multi_unit_acceptance_keeps_failed_runs_and_requires_stale_units_to_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            tests_dir = project / "tests"
            discovery = tests_dir / "discover.py"
            login_test = tests_dir / "login_acceptance.py"
            account_test = tests_dir / "account_acceptance.py"
            account_pass = project / "account-pass"
            write_text(discovery, 'print("case_login case_account")\n')
            write_text(login_test, 'print("case_login token=login-secret")\n')
            write_text(
                account_test,
                "from pathlib import Path\nimport sys\n"
                'print("case_account token=account-secret postgres://tester:db-secret@localhost/test")\n'
                f"sys.exit(0 if Path({str(account_pass)!r}).exists() else 1)\n",
            )
            discovery_command = subprocess.list2cmdline([sys.executable, str(discovery)])

            def create_unit(unit_id: str, scenario_id: str, case_id: str, test_file: Path, feature_hash: str) -> Path:
                unit = unit_dir(project, unit_id)
                mapping = {
                    "version": 3,
                    "unit": unit_id,
                    "feature_hash": feature_hash,
                    "contract_revision": 1,
                    "scenarios": [
                        {
                            "id": scenario_id,
                            "status": "active",
                            "selected": True,
                            "selection_reason": "affected_by_current_change",
                            "case_ids": [case_id],
                            "business_entrypoint": f"{unit_id} behavior",
                            "validation_entrypoint": test_file.stem,
                            "style_evidence": [{"file": str(test_file.relative_to(project)).replace('\\', '/')}],
                            "assertion_mapping": [{"then": f"{unit_id} accepted", "test_assertion": "assert process exit"}],
                            "generated_tests_stale": False,
                            "generated_tests": [
                                {
                                    "case_id": case_id,
                                    "file": str(test_file.relative_to(project)).replace('\\', '/'),
                                    "symbol": case_id,
                                    "command": subprocess.list2cmdline([sys.executable, str(test_file)]),
                                    "discovery_command": discovery_command,
                                }
                            ],
                        }
                    ],
                }
                write_yaml(unit / "acceptance-map.yaml", mapping)
                return unit

            login = create_unit("login", "AC-LOGIN-001", "case_login", login_test, "feature-login-v1")
            account = create_unit("account", "AC-ACCOUNT-001", "case_account", account_test, "feature-account-v1")
            acceptance_id = "ACC-TEST-MULTI-001"
            result = run_script(
                "acceptance_run.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "--unit",
                "account",
                "--acceptance-id",
                acceptance_id,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            acceptance_report = project / ".acceptance" / "acceptances" / acceptance_id / "report.md"
            first_acceptance = parse_frontmatter(acceptance_report)
            self.assertEqual(first_acceptance["status"], "awaiting_diagnosis")
            self.assertEqual(first_acceptance["scope_units"], ["login", "account"])
            run_one = acceptance_report.parent / "runs" / "RUN-001.md"
            self.assertTrue(run_one.is_file())
            run_one_metadata = parse_frontmatter(run_one)
            self.assertEqual(len(run_one_metadata["modules"]), 2)
            self.assertTrue(run_one_metadata["context_fingerprint"])
            self.assertTrue(all(item["map_hash"] for item in run_one_metadata["modules"]))
            _, failed_account_report = detailed_report_from_latest(account)
            self.assertIn("[REDACTED]", failed_account_report.read_text(encoding="utf-8"))
            self.assertNotIn("account-secret", failed_account_report.read_text(encoding="utf-8"))
            self.assertNotIn("db-secret", failed_account_report.read_text(encoding="utf-8"))

            login_map = load_yaml(login / "acceptance-map.yaml")
            login_map["scenarios"][0]["selected"] = True
            login_map["scenarios"][0]["selection_reason"] = "shared_code_changed_after_repair"
            write_yaml(login / "acceptance-map.yaml", login_map)
            write_text(account_pass, "ok\n")
            result = run_script(
                "acceptance_run.py",
                "--project-root",
                str(project),
                "--unit",
                "account",
                "--acceptance-id",
                acceptance_id,
                "--repair-confirmed",
                "--repair-note",
                "fix account and re-evaluate shared authentication impact",
                "--approved-file",
                "src/account.py",
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            second_acceptance = parse_frontmatter(acceptance_report)
            self.assertEqual(second_acceptance["status"], "pending")
            run_two = parse_frontmatter(acceptance_report.parent / "runs" / "RUN-002.md")
            self.assertEqual(run_two["parent_run"], "RUN-001")
            self.assertTrue(run_two["repair_confirmed"])
            self.assertEqual([item["unit"] for item in run_two["modules"]], ["account"])
            self.assertIn("login | stale", acceptance_report.read_text(encoding="utf-8"))

            result = run_script(
                "acceptance_run.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "--acceptance-id",
                acceptance_id,
                "--repair-confirmed",
                "--repair-note",
                "rerun shared authentication impact",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            final_acceptance = parse_frontmatter(acceptance_report)
            self.assertEqual(final_acceptance["status"], "accepted")
            self.assertEqual(final_acceptance["latest_run_id"], "RUN-003")
            acceptance_text = acceptance_report.read_text(encoding="utf-8")
            self.assertIn("| RUN-001 | fail | initial_run | RUN-002 |", acceptance_text)
            self.assertIn("| RUN-002 | incremental_pass | repair_rerun | RUN-003 |", acceptance_text)
            self.assertIn("| RUN-003 | incremental_pass | repair_rerun |  |", acceptance_text)
            self.assertTrue((account / "reports" / f"{acceptance_id}-RUN-001.md").is_file())
            self.assertTrue((account / "reports" / f"{acceptance_id}-RUN-002.md").is_file())
            account_latest = parse_frontmatter(account / "reports" / "latest.md")
            login_latest = parse_frontmatter(login / "reports" / "latest.md")
            self.assertEqual(account_latest["run_id"], "RUN-002")
            self.assertEqual(login_latest["run_id"], "RUN-003")
            self.assertEqual(account_latest["acceptance_status"], "accepted")
            self.assertEqual(login_latest["acceptance_status"], "accepted")

            result = run_script(
                "acceptance_run.py",
                "--project-root",
                str(project),
                "--unit",
                "login",
                "--acceptance-id",
                acceptance_id,
                "--repair-confirmed",
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("already accepted", result.stdout)

    def test_language_script_sets_remain_identical(self):
        en_scripts = ROOT / "bdd-atdd-acceptance-workflow-en" / "scripts"
        for path in ZH_SCRIPTS.glob("acceptance_*.py"):
            self.assertEqual(path.read_bytes(), (en_scripts / path.name).read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
