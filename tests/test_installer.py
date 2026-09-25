from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gpt6_install", ROOT / "scripts" / "install.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "codex-home"
        self.project = Path(self.temp.name) / "project"
        self.project.mkdir()
        self.installer = MODULE.Installer(ROOT)

    def tearDown(self):
        self.temp.cleanup()

    def config(self, text: str) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "config.toml").write_text(text, encoding="utf-8")

    def test_config_merge_preserves_unrelated_tables_and_converts_profiles(self):
        original = """# keep this comment
model = \"old\"
approval_policy = \"never\"

[agents]
max_threads = 8
job_max_runtime_seconds = 77

[plugins.custom]
enabled = true

[profiles.economy]
model = \"old-luna\"
notify = \"keep-extra\"

[profiles.custom]
model = \"custom-model\"
        """
        self.config(original)
        (self.home / "economy.config.toml").write_text('notify = "standalone-extra"\n', encoding="utf-8")
        result = self.installer.install(self.home)
        self.assertTrue(result["backup"])
        merged = (self.home / "config.toml").read_text(encoding="utf-8")
        self.assertIn("# keep this comment", merged)
        self.assertIn('approval_policy = "never"', merged)
        self.assertIn("job_max_runtime_seconds = 77", merged)
        self.assertIn("[plugins.custom]", merged)
        self.assertIn("[profiles.custom]", merged)
        self.assertNotIn("max_threads", merged)
        self.assertNotIn("[profiles.economy]", merged)
        economy = (self.home / "economy.config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "gpt-6-luna"', economy)
        self.assertNotIn('notify = "keep-extra"', economy)
        self.assertIn('notify = "standalone-extra"', economy)
        self.assertEqual(len(list((self.home / "agents").glob("*.toml"))), 9)
        self.assertTrue((self.home / "AGENTS.md").is_file())

    def test_dry_run_does_not_create_home_or_project_files(self):
        result = self.installer.install(self.home, self.project, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.home.exists())
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse((self.project / "docs").exists())

    def test_differing_global_agents_requires_explicit_replace_flag(self):
        self.home.mkdir(parents=True)
        agents = self.home / "AGENTS.md"
        agents.write_text("# user policy\n", encoding="utf-8")
        with self.assertRaises(MODULE.InstallError):
            self.installer.install(self.home)
        self.assertEqual(agents.read_text(encoding="utf-8"), "# user policy\n")
        self.assertFalse((self.home / "config.toml").exists())
        result = self.installer.install(self.home, replace_global_agents=True)
        self.assertIn("codex_home:AGENTS.md", result["changed"])
        self.assertNotEqual(agents.read_text(encoding="utf-8"), "# user policy\n")

    def test_install_is_idempotent_without_new_backup(self):
        first = self.installer.install(self.home)
        backups = list((self.home / "backups").iterdir())
        second = self.installer.install(self.home)
        self.assertTrue(first["backup"])
        self.assertEqual(second["changed"], [])
        self.assertEqual(backups, list((self.home / "backups").iterdir()))

    def test_project_block_is_replaced_once_and_unrelated_text_survives(self):
        path = self.project / "AGENTS.md"
        path.write_text("# Existing\n\nkeep this project rule\n", encoding="utf-8")
        custom_template = self.project / "docs" / "agent-workflow" / "task-card.md"
        custom_template.parent.mkdir(parents=True)
        custom_template.write_text("user template\n", encoding="utf-8")
        self.installer.install(self.home, self.project)
        self.installer.install(self.home, self.project)
        text = path.read_text(encoding="utf-8")
        self.assertIn("keep this project rule", text)
        self.assertEqual(custom_template.read_text(encoding="utf-8"), "user template\n")
        self.assertIn("project:docs/agent-workflow/task-card.md", self.installer.skipped)
        self.assertEqual(text.count("BEGIN GPT6-AGENTS-POLICY"), 1)
        self.assertEqual(text.count("END GPT6-AGENTS-POLICY"), 1)

    def test_backup_rollback_restores_original_bytes_and_removes_created_files(self):
        original = "# original\nmodel = \"before\"\n"
        self.config(original)
        result = self.installer.install(self.home)
        self.installer.rollback(Path(result["backup"]), self.home)
        self.assertEqual((self.home / "config.toml").read_text(encoding="utf-8"), original)
        self.assertFalse((self.home / "AGENTS.md").exists())
        self.assertFalse((self.home / "agents" / "token-worker.toml").exists())
        self.assertFalse((self.home / "economy.config.toml").exists())

    def test_rollback_refuses_user_modified_target(self):
        self.config("model = \"before\"\n")
        result = self.installer.install(self.home)
        (self.home / "config.toml").write_text("model = \"user edit\"\n", encoding="utf-8")
        with self.assertRaises(MODULE.InstallError):
            self.installer.rollback(Path(result["backup"]), self.home)

    def test_rollback_rejects_manifest_traversal(self):
        backup = Path(self.temp.name) / "backup"
        (backup / "files").mkdir(parents=True)
        manifest = {
            "version": 1,
            "entries": [{
                "root": "codex_home",
                "path": "../outside",
                "existed": False,
                "original_sha256": None,
                "installed_sha256": "0" * 64,
                "backup": None,
            }],
        }
        (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(MODULE.InstallError):
            self.installer.rollback(backup, self.home)

    def test_mid_write_failure_restores_previous_files(self):
        original = "# before failure\nmodel = \"old\"\n"
        self.config(original)
        original_atomic = MODULE.atomic_write
        calls = {"count": 0}
        original_backup_dir = self.installer._backup

        def backup_then_flake(home, changed, roots):
            result = original_backup_dir(home, changed, roots)

            def flaky(path, content):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("simulated write failure")
                return original_atomic(path, content)

            MODULE.atomic_write = flaky
            return result

        try:
            with mock.patch.object(self.installer, "_backup", side_effect=backup_then_flake):
                with self.assertRaises(MODULE.InstallError):
                    self.installer.install(self.home)
        finally:
            MODULE.atomic_write = original_atomic
        self.assertEqual((self.home / "config.toml").read_text(encoding="utf-8"), original)
        self.assertFalse((self.home / "agents" / "token-explorer.toml").exists())

    def test_rollback_rejects_a_different_project_root(self):
        first_project = Path(self.temp.name) / "first-project"
        second_project = Path(self.temp.name) / "second-project"
        first_project.mkdir()
        second_project.mkdir()
        result = self.installer.install(self.home, first_project)
        with self.assertRaises(MODULE.InstallError):
            self.installer.rollback(Path(result["backup"]), self.home, second_project)

    def test_project_rollback_restores_project_bytes(self):
        agents = self.project / "AGENTS.md"
        agents.write_text("# project original\n", encoding="utf-8")
        result = self.installer.install(self.home, self.project)
        self.installer.rollback(Path(result["backup"]), self.home, self.project)
        self.assertEqual(agents.read_text(encoding="utf-8"), "# project original\n")
        self.assertFalse((self.project / "docs" / "agent-workflow" / "task-card.md").exists())


if __name__ == "__main__":
    unittest.main()
