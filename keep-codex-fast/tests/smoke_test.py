#!/usr/bin/env python3
"""Smoke tests for keep-codex-fast using a fake Codex home."""

from __future__ import annotations

import argparse
import contextlib
import io
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "keep_codex_fast.py"


def load_module():
    spec = importlib.util.spec_from_file_location("keep_codex_fast", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["keep_codex_fast"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.codex_processes_running = lambda: []
    module.top_node_processes = lambda details=False: module.report("top_node_processes skipped_in_smoke")
    return module


def make_fake_home(root: Path) -> dict[str, Path]:
    codex_home = root / ".codex"
    sessions = codex_home / "sessions" / "2026" / "01" / "01"
    sessions.mkdir(parents=True)
    rollout = sessions / "rollout-2026-01-01T00-00-00-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.jsonl"
    rollout.write_text('{"type":"test"}\n', encoding="utf-8")
    old_time = time.time() - 30 * 86400
    os.utime(rollout, (old_time, old_time))

    sidebar_state = {
        "pinned-thread-ids": [],
        "projectless-thread-ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
        "thread-workspace-root-hints": {
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": str(root),
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": str(root),
        },
        "heartbeat-thread-permissions-by-id": {
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {"approvalPolicy": "on-request"},
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": {"approvalPolicy": "on-request"},
        },
        "electron-persisted-atom-state": {
            "prompt-history": {
                "global": [],
                "new-conversation": [],
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": ["old prompt"],
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": ["active prompt"],
            }
        },
    }
    (codex_home / ".codex-global-state.json").write_text(json.dumps(sidebar_state), encoding="utf-8")
    (codex_home / "config.toml").write_text(
        '[projects."C:\\\\DefinitelyMissingKeepCodexFast"]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )

    worktree = codex_home / "worktrees" / "oldtree"
    worktree.mkdir(parents=True)
    (worktree / "file.txt").write_text("x", encoding="utf-8")
    os.utime(worktree, (old_time, old_time))

    log_file = codex_home / "logs_2.sqlite"
    log_file.write_text("log", encoding="utf-8")

    state_db = codex_home / "state_5.sqlite"
    conn = sqlite3.connect(state_db)
    conn.execute(
        "create table threads (id text primary key, title text, first_user_message text, rollout_path text, cwd text, updated_at integer, archived_at integer, archived integer)"
    )
    long_title = "Title " + ("x" * 300)
    long_preview = "Preview " + ("y" * 600)
    conn.execute(
        "insert into threads values (?,?,?,?,?,?,?,?)",
        (
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            long_title,
            long_preview,
            str(rollout),
            r"\\?\C:\DefinitelyMissingKeepCodexFast",
            int(old_time),
            None,
            0,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "codex_home": codex_home,
        "rollout": rollout,
        "worktree": worktree,
        "log_file": log_file,
        "state_db": state_db,
    }


def assert_report_mode(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-report"
        args = argparse.Namespace(
            apply=False,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=7,
            rotate_logs_above_mb=0,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert module.run(args) == 0
        text = output.getvalue()
        assert paths["rollout"].exists(), "report mode must not move sessions"
        assert paths["worktree"].exists(), "report mode must not move worktrees"
        assert paths["log_file"].exists(), "report mode must not rotate logs"
        assert not backup.exists(), "report mode must not create backup artifacts"
        assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in text
        assert str(paths["codex_home"]) not in text
        conn = sqlite3.connect(paths["state_db"])
        title, preview = conn.execute(
            "select title, first_user_message from threads where id=?",
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",),
        ).fetchone()
        conn.close()
        assert len(title) > 120, "report mode must not trim titles"
        assert len(preview) > 240, "report mode must not trim previews"


def assert_backup_only_mode(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-only"
        args = argparse.Namespace(
            apply=False,
            backup_only=True,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=7,
            rotate_logs_above_mb=0,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(args) == 0
        assert paths["rollout"].exists(), "backup-only mode must not move sessions"
        assert paths["worktree"].exists(), "backup-only mode must not move worktrees"
        assert paths["log_file"].exists(), "backup-only mode must not rotate logs"
        assert (backup / "state_5.sqlite").exists()
        assert (backup / "config.toml").exists()
        assert not (backup / "moved-sessions.jsonl").exists()
        conn = sqlite3.connect(paths["state_db"])
        title, preview = conn.execute(
            "select title, first_user_message from threads where id=?",
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",),
        ).fetchone()
        conn.close()
        assert len(title) > 120, "backup-only mode must not trim titles"
        assert len(preview) > 240, "backup-only mode must not trim previews"


def assert_session_alias_detection(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        real_root = root / "real"
        alias_root = root / "alias"
        real_root.mkdir()
        try:
            alias_root.symlink_to(real_root, target_is_directory=True)
        except OSError:
            return

        paths = make_fake_home(real_root)
        alias_home = alias_root / ".codex"
        conn = module.sqlite_connect(alias_home / "state_5.sqlite", readonly=True)
        try:
            candidates = module.active_session_candidates(conn, alias_home, 10)
        finally:
            conn.close()
        assert len(candidates) == 1


def assert_apply_mode(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-apply"
        args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=7,
            rotate_logs_above_mb=0,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=True,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(args) == 0

        conn = sqlite3.connect(paths["state_db"])
        archived, archived_at, rollout_path, cwd, title, preview = conn.execute(
            "select archived, archived_at, rollout_path, cwd, title, first_user_message from threads where id=?",
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",),
        ).fetchone()
        conn.close()

        assert archived == 1
        assert archived_at is not None
        assert "archived_sessions" in rollout_path
        archived_path = Path(rollout_path)
        assert archived_path.parent == paths["codex_home"] / "archived_sessions"
        assert archived_path.name == paths["rollout"].name
        assert archived_path.exists()
        assert cwd == r"C:\DefinitelyMissingKeepCodexFast"
        assert len(title) <= 120
        assert len(preview) <= 240
        assert not paths["rollout"].exists()
        assert not paths["worktree"].exists()
        assert not paths["log_file"].exists()
        assert "DefinitelyMissingKeepCodexFast" not in (paths["codex_home"] / "config.toml").read_text(
            encoding="utf-8"
        )
        assert (backup / "restore-sessions.py").exists()
        assert (backup / "restore-thread-metadata.py").exists()
        assert (backup / "moved-sessions.jsonl").exists()
        assert (backup / "thread-metadata-repairs.jsonl").exists()
        assert (backup / "moved-worktrees.jsonl").exists()
        state = json.loads((paths["codex_home"] / "keep-codex-fast-state.json").read_text(encoding="utf-8"))
        assert state["archives"]["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]["archived_by"] == "keep-codex-fast"
        assert state["archives"]["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]["restored_at"] is None
        session_index = paths["codex_home"] / "session_index.jsonl"
        assert session_index.exists()
        assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in session_index.read_text(encoding="utf-8")
        sidebar_state = json.loads((paths["codex_home"] / ".codex-global-state.json").read_text(encoding="utf-8"))
        archived_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        active_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        assert archived_id not in sidebar_state["projectless-thread-ids"]
        assert active_id in sidebar_state["projectless-thread-ids"]
        assert archived_id not in sidebar_state["thread-workspace-root-hints"]
        assert active_id in sidebar_state["thread-workspace-root-hints"]
        assert archived_id not in sidebar_state["heartbeat-thread-permissions-by-id"]
        assert active_id in sidebar_state["heartbeat-thread-permissions-by-id"]
        prompt_history = sidebar_state["electron-persisted-atom-state"]["prompt-history"]
        assert archived_id not in prompt_history
        assert active_id in prompt_history


def assert_archived_layout_normalization(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-layout"
        archive_root = paths["codex_home"] / "archived_sessions"
        nested = (
            archive_root
            / "keep-codex-fast-old"
            / "2026"
            / "01"
            / "01"
            / "rollout-2026-01-01T00-00-00-cccccccc-cccc-cccc-cccc-cccccccccccc.jsonl"
        )
        nested.parent.mkdir(parents=True)
        nested.write_text('{"type":"archived"}\n', encoding="utf-8")

        conn = sqlite3.connect(paths["state_db"])
        conn.execute(
            "insert into threads values (?,?,?,?,?,?,?,?)",
            (
                "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "Archived",
                "Archived preview",
                str(nested),
                str(Path(td)),
                int(time.time()) - 20 * 86400,
                int(time.time()) - 20 * 86400,
                1,
            ),
        )
        conn.commit()
        conn.close()

        args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=9999,
            rotate_logs_above_mb=9999,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=True,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(args) == 0

        conn = sqlite3.connect(paths["state_db"])
        rollout_path = conn.execute(
            "select rollout_path from threads where id=?",
            ("cccccccc-cccc-cccc-cccc-cccccccccccc",),
        ).fetchone()[0]
        conn.close()

        flat = archive_root / nested.name
        assert Path(rollout_path) == flat
        assert flat.exists()
        assert not nested.exists()
        assert (backup / "archived-layout-moves.jsonl").exists()
        assert (backup / "restore-archived-layout.py").exists()


def assert_unarchive_sessions_defaults_to_owned_recent(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        archive_backup = Path(td) / "backup-archive"
        archive_args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(archive_backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=9999,
            rotate_logs_above_mb=9999,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(archive_args) == 0
        archived_path = paths["codex_home"] / "archived_sessions" / paths["rollout"].name
        assert archived_path.exists()

        unarchive_backup = Path(td) / "backup-unarchive"
        unarchive_args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(unarchive_backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=9999,
            rotate_logs_above_mb=9999,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=True,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(unarchive_args) == 0

        assert paths["rollout"].exists()
        assert not archived_path.exists()
        conn = sqlite3.connect(paths["state_db"])
        archived, archived_at, rollout_path = conn.execute(
            "select archived, archived_at, rollout_path from threads where id=?",
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",),
        ).fetchone()
        conn.close()
        assert archived == 0
        assert archived_at is None
        assert Path(rollout_path) == paths["rollout"]
        state = json.loads((paths["codex_home"] / "keep-codex-fast-state.json").read_text(encoding="utf-8"))
        assert state["archives"]["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]["restored_at"] is not None
        assert (unarchive_backup / "unarchived-sessions.jsonl").exists()
        assert (unarchive_backup / "restore-unarchive-sessions.py").exists()


def assert_unarchive_sessions_all_scope_restores_manual_archives(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        manual_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        archive_root = paths["codex_home"] / "archived_sessions"
        archived = archive_root / f"rollout-2026-01-02T00-00-00-{manual_id}.jsonl"
        archived.parent.mkdir(parents=True)
        archived.write_text('{"type":"manual"}\n', encoding="utf-8")
        archived_at = int(time.time())
        conn = sqlite3.connect(paths["state_db"])
        conn.execute(
            "insert into threads values (?,?,?,?,?,?,?,?)",
            (
                manual_id,
                "Manual archived",
                "Manual archived preview",
                str(archived),
                str(Path(td)),
                archived_at,
                archived_at,
                1,
            ),
        )
        conn.commit()
        conn.close()

        default_args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(Path(td) / "backup-default-unarchive"),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=9999,
            rotate_logs_above_mb=9999,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=True,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(default_args) == 0
        assert archived.exists(), "default unarchive must not restore manual archives"

        all_args = argparse.Namespace(**{**default_args.__dict__})
        all_args.backup_root = str(Path(td) / "backup-all-unarchive")
        all_args.unarchive_scope = "all"
        assert module.run(all_args) == 0
        restored = paths["codex_home"] / "sessions" / "2026" / "01" / "02" / archived.name
        assert restored.exists()
        assert not archived.exists()
        conn = sqlite3.connect(paths["state_db"])
        archived_flag, archived_at_value, rollout_path = conn.execute(
            "select archived, archived_at, rollout_path from threads where id=?",
            (manual_id,),
        ).fetchone()
        conn.close()
        assert archived_flag == 0
        assert archived_at_value is None
        assert Path(rollout_path) == restored


def assert_apply_no_backup_skips_backup_artifacts(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-no-backup"
        args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=True,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=9999,
            rotate_logs_above_mb=9999,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(args) == 0
        archived_path = paths["codex_home"] / "archived_sessions" / paths["rollout"].name
        assert archived_path.exists()
        assert not paths["rollout"].exists()
        assert not backup.exists(), "--no-backup must not create backup artifacts"
        assert (paths["codex_home"] / "keep-codex-fast-state.json").exists()


def assert_normal_apply_does_not_repair_thread_metadata(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-normal-apply"
        args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=7,
            rotate_logs_above_mb=64,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        assert module.run(args) == 0

        conn = sqlite3.connect(paths["state_db"])
        title, preview = conn.execute(
            "select title, first_user_message from threads where id=?",
            ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",),
        ).fetchone()
        conn.close()

        assert len(title) > 120, "normal apply must not trim titles without explicit repair flag"
        assert len(preview) > 240, "normal apply must not trim previews without explicit repair flag"
        assert not (backup / "thread-metadata-repairs.jsonl").exists()
        assert not (backup / "restore-thread-metadata.py").exists()


def assert_running_codex_prints_log_cleanup_hint(module) -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = make_fake_home(Path(td))
        backup = Path(td) / "backup-running"
        args = argparse.Namespace(
            apply=True,
            backup_only=False,
            no_backup=False,
            details=False,
            wait_for_codex_exit=False,
            codex_home=str(paths["codex_home"]),
            backup_root=str(backup),
            archive_older_than_days=10,
            archive_date=None,
            archive_sessions_only=False,
            worktree_older_than_days=7,
            rotate_logs_above_mb=0,
            thread_title_limit=120,
            thread_preview_limit=240,
            repair_thread_metadata_bloat=False,
            prune_sidebar_archived_refs=False,
            rotate_logs_only=False,
            normalize_archived_layout_only=False,
            unarchive_sessions=False,
            unarchive_scope="keep-codex-fast",
            unarchive_archived_within_days=7,
        )
        original = module.codex_processes_running
        module.codex_processes_running = lambda: ["123 Codex.exe"]
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                assert module.run(args) == 0
        finally:
            module.codex_processes_running = original
        text = output.getvalue()
        assert paths["rollout"].exists(), "running Codex must prevent archive mutations"
        assert paths["log_file"].exists(), "running Codex must prevent log rotation"
        assert "apply_skipped_codex_running" in text
        assert "log_cleanup_deferred reason=codex_running" in text
        assert "--rotate-logs-only" in text


def main() -> int:
    module = load_module()
    assert_report_mode(module)
    assert_backup_only_mode(module)
    assert_session_alias_detection(module)
    assert_normal_apply_does_not_repair_thread_metadata(module)
    assert_running_codex_prints_log_cleanup_hint(module)
    assert_apply_mode(module)
    assert_archived_layout_normalization(module)
    assert_unarchive_sessions_defaults_to_owned_recent(module)
    assert_unarchive_sessions_all_scope_restores_manual_archives(module)
    assert_apply_no_backup_skips_backup_artifacts(module)
    print("smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
