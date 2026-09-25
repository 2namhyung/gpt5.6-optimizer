"""Install and safely roll back the GPT-6 Codex configuration.

The installer deliberately knows only the files this repository owns. Existing
configuration tables and project content outside the marked block are preserved.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import tempfile
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from tomlkit import dumps, loads, table


ROOT = Path(__file__).resolve().parents[1]
ROLE_FILES = (
    "token-explorer.toml",
    "token-researcher.toml",
    "token-worker.toml",
    "frontend-builder.toml",
    "backend-builder.toml",
    "database-builder.toml",
    "token-verifier.toml",
    "token-reviewer.toml",
    "frontier-specialist.toml",
)
PROFILE_FILES = ("economy", "deep", "legacy55")
PROJECT_MARKER = "GPT6-AGENTS-POLICY"


class InstallError(RuntimeError):
    """A safe, user-actionable installation or rollback error."""


@dataclass(frozen=True)
class Operation:
    root_name: str
    relative_path: str
    content: bytes


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write(path: Path, content: bytes) -> None:
    """Write a file atomically, creating only its parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def recovery_write(path: Path, content: bytes) -> None:
    """Separate recovery writer so a simulated install failure can be tested."""
    atomic_write(path, content)


def safe_relative(value: str, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise InstallError(f"invalid {field} path")
    path = Path(value)
    if path.is_absolute() or path.drive:
        raise InstallError(f"absolute {field} path is not allowed: {value!r}")
    if any(part in ("", ".", "..") for part in path.parts):
        raise InstallError(f"path traversal in {field}: {value!r}")
    return path


def under(root: Path, relative: Path, field: str) -> Path:
    root = root.resolve()
    target = Path(os.path.abspath(str(root / relative)))
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise InstallError(f"{field} escapes its root: {relative}") from exc
    cursor = root_resolved
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and _is_reparse_point(cursor):
            raise InstallError(f"refusing symlink or reparse point in {field}: {cursor}")
    return target


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            import ctypes

            attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            return attributes != 0xFFFFFFFF and bool(attributes & 0x400)
        except Exception:
            return False
    try:
        return bool(path.stat().st_mode & stat.S_ISVTX) and path.is_symlink()
    except OSError:
        return False


def parse_document(content: bytes, source: str):
    try:
        text = content.decode("utf-8-sig")
        # tomllib is the standard-library syntax check; tomlkit then keeps
        # comments and formatting while the document is edited.
        tomllib.loads(text)
        return loads(text)
    except Exception as exc:
        raise InstallError(f"invalid TOML in {source}: {exc}") from exc


def clone_document(value):
    return loads(dumps(value))


def clone_value(value):
    return copy.deepcopy(value)


def resolve_codex_home(explicit: str | None) -> Path:
    value = explicit or os.environ.get("CODEX_HOME")
    return Path(value).expanduser().resolve() if value else (Path.home() / ".codex").resolve()


class Installer:
    def __init__(self, repo_root: Path | None = None):
        self.repo_root = (repo_root or ROOT).resolve()
        self.skipped: list[str] = []

    def source(self, relative: str) -> bytes:
        path = under(self.repo_root, safe_relative(relative, "source"), "source")
        if not path.is_file():
            raise InstallError(f"repository source is missing: {relative}")
        return path.read_bytes()

    def _roots(self, codex_home: Path, project: Path | None) -> dict[str, Path]:
        roots = {"codex_home": codex_home.resolve()}
        if project is not None:
            project = project.expanduser().resolve()
            if not project.is_dir():
                raise InstallError(f"project directory does not exist: {project}")
            roots["project"] = project
        return roots

    def _operation(self, root_name: str, relative: str, content: bytes) -> Operation:
        safe_relative(relative, "target")
        return Operation(root_name, relative.replace("\\", "/"), content)

    def _merge_profile(self, home: Path, name: str, old_table=None) -> bytes:
        profile_path = home / f"{name}.config.toml"
        if profile_path.exists():
            if not profile_path.is_file():
                raise InstallError(f"profile target is not a file: {profile_path}")
            document = parse_document(profile_path.read_bytes(), str(profile_path))
        else:
            document = loads("")
        if old_table is not None:
            for key, value in old_table.items():
                # Legacy profile values are only migration fallbacks. The
                # standalone file wins, and the old nested notify key is an
                # ignored legacy path rather than an enabled setting.
                if key not in document and key != "notify":
                    document[key] = clone_value(value)
        fresh = parse_document(self.source(f"codex/profiles/{name}.config.toml"), f"profile {name}")
        for key, value in fresh.items():
            document[key] = clone_value(value)
        return dumps(document).encode("utf-8")

    def _merge_config(self, home: Path) -> bytes:
        config_path = home / "config.toml"
        current = parse_document(config_path.read_bytes(), str(config_path)) if config_path.exists() else loads("")
        fragment = parse_document(self.source("codex/config-fragment.toml"), "codex/config-fragment.toml")

        for key, value in fragment.items():
            if key != "agents":
                current[key] = clone_value(value)
        if "agents" not in current:
            current["agents"] = table()
        agents = current["agents"]
        for key, value in fragment["agents"].items():
            agents[key] = clone_value(value)
        if "max_threads" in agents:
            del agents["max_threads"]

        profiles = current.get("profiles")
        if profiles is not None:
            for name in PROFILE_FILES:
                if name in profiles:
                    del profiles[name]
            if not profiles:
                del current["profiles"]
        return dumps(current).encode("utf-8")

    def _profile_operations(self, home: Path, current_config: bytes) -> list[Operation]:
        document = parse_document(current_config, "merged config")
        # The merged document no longer contains the legacy tables. Read the
        # original once to migrate their extra keys without moving other tables.
        original_path = home / "config.toml"
        original = parse_document(original_path.read_bytes(), str(original_path)) if original_path.exists() else loads("")
        old_profiles = original.get("profiles")
        operations: list[Operation] = []
        for name in PROFILE_FILES:
            old_table = old_profiles.get(name) if old_profiles is not None and name in old_profiles else None
            content = self._merge_profile(home, name, old_table)
            relative = f"{name}.config.toml"
            target = home / relative
            if not target.exists() or target.read_bytes() != content:
                operations.append(self._operation("codex_home", relative, content))
        return operations

    def _project_operations(self, project: Path) -> list[Operation]:
        self.skipped = []
        operations: list[Operation] = []
        source = self.source("project/AGENTS.md").decode("utf-8")
        target = under(project, Path("AGENTS.md"), "project target")
        if target.exists():
            if not target.is_file():
                raise InstallError(f"project AGENTS.md is not a file: {target}")
            current = target.read_text(encoding="utf-8")
            pattern = re.compile(
                rf"(?ms)^<!-- BEGIN {re.escape(PROJECT_MARKER)} -->.*?^<!-- END {re.escape(PROJECT_MARKER)} -->\s*"
            )
            block = source.rstrip() + "\n"
            if pattern.search(current):
                merged = pattern.sub(block, current)
            else:
                merged = current.rstrip() + "\n\n" + block
        else:
            merged = source.rstrip() + "\n"
        operations.append(self._operation("project", "AGENTS.md", merged.encode("utf-8")))

        for name in ("task-card.md", "api-contract.md", "review-report.md", "pilot-results.csv"):
            relative = f"docs/agent-workflow/{name}"
            content = self.source(f"templates/{name}")
            target = under(project, safe_relative(relative, "project target"), "project target")
            if target.exists():
                if not target.is_file() or target.read_bytes() != content:
                    self.skipped.append(f"project:{relative}")
                continue
            operations.append(self._operation("project", relative, content))
        return operations

    def planned_operations(self, codex_home: Path, project: Path | None) -> list[Operation]:
        self.skipped = []
        config_content = self._merge_config(codex_home)
        operations = [self._operation("codex_home", "config.toml", config_content)]
        operations.append(self._operation("codex_home", "AGENTS.md", self.source("codex/AGENTS.md")))
        operations.extend(self._profile_operations(codex_home, config_content))
        for name in ROLE_FILES:
            operations.append(self._operation("codex_home", f"agents/{name}", self.source(f"codex/agents/{name}")))
        if project is not None:
            operations.extend(self._project_operations(project))
        return operations

    def _changed(self, operations: Iterable[Operation], roots: dict[str, Path]) -> list[tuple[Operation, Path, bool, bytes | None]]:
        result = []
        for operation in operations:
            relative = safe_relative(operation.relative_path, "target")
            if operation.root_name not in roots:
                raise InstallError(f"operation requires missing root: {operation.root_name}")
            target = under(roots[operation.root_name], relative, "target")
            if target.exists() and not target.is_file():
                raise InstallError(f"target is not a file: {target}")
            before = target.read_bytes() if target.exists() else None
            if before != operation.content:
                result.append((operation, target, before is not None, before))
        return result

    def _backup(self, home: Path, changed: list[tuple[Operation, Path, bool, bytes | None]], roots: dict[str, Path]) -> Path:
        backup_parent = home / "backups"
        if backup_parent.exists() and _is_reparse_point(backup_parent):
            raise InstallError(f"refusing symlink or reparse point as backup directory: {backup_parent}")
        backup_parent.mkdir(parents=True, exist_ok=True)
        backup_dir = backup_parent / (
            "gpt6-agents-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:8]
        )
        backup_dir.mkdir()
        entries = []
        for index, (operation, target, existed, before) in enumerate(changed):
            backup_name = None
            original_hash = sha256_bytes(before) if existed and before is not None else None
            if existed:
                backup_name = f"files/{index:04d}.bin"
                backup_path = under(backup_dir, safe_relative(backup_name, "backup"), "backup")
                atomic_write(backup_path, before or b"")
            entries.append(
                {
                    "root": operation.root_name,
                    "path": operation.relative_path,
                    "existed": existed,
                    "original_sha256": original_hash,
                    "installed_sha256": sha256_bytes(operation.content),
                    "backup": backup_name,
                }
            )
        manifest = {
            "version": 1,
            "schema": "gpt6-optimizer-v1",
            "root_ids": sorted({operation.root_name for operation, *_ in changed}),
            "roots": {name: str(roots[name].resolve()) for name in sorted({operation.root_name for operation, *_ in changed})},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
        }
        atomic_write(backup_dir / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
        return backup_dir

    def _restore_snapshot(self, changed: list[tuple[Operation, Path, bool, bytes | None]]) -> None:
        for _, target, existed, before in reversed(changed):
            try:
                if existed:
                    recovery_write(target, before or b"")
                elif target.exists():
                    if target.is_file() or target.is_symlink():
                        target.unlink()
                    else:
                        raise InstallError(f"cannot recover non-file target: {target}")
            except Exception:
                # Preserve the original installation exception and expose a
                # concise message to the caller; no recursive deletion occurs.
                raise InstallError(f"automatic recovery failed at {target}")

    def install(
        self,
        codex_home: Path,
        project: Path | None = None,
        dry_run: bool = False,
        replace_global_agents: bool = False,
    ) -> dict:
        codex_home = codex_home.expanduser().resolve()
        project = project.expanduser().resolve() if project is not None else None
        roots = self._roots(codex_home, project)
        operations = self.planned_operations(codex_home, project)
        changed = self._changed(operations, roots)
        planned = [f"{item.root_name}:{item.relative_path}" for item in operations if any(item is row[0] for row in changed)]
        global_agents = next((row for row in changed if row[0].root_name == "codex_home" and row[0].relative_path == "AGENTS.md"), None)
        if global_agents is not None and global_agents[2] and not replace_global_agents and not dry_run:
            raise InstallError("existing CODEX_HOME/AGENTS.md differs; rerun with --replace-global-agents")
        if dry_run:
            return {"changed": planned, "skipped": self.skipped, "backup": None, "dry_run": True}
        if not changed:
            return {"changed": [], "skipped": self.skipped, "backup": None, "dry_run": False}
        backup_dir = self._backup(codex_home, changed, roots)
        written: list[tuple[Operation, Path, bool, bytes | None]] = []
        try:
            for item in changed:
                operation, target, existed, before = item
                atomic_write(target, operation.content)
                written.append(item)
        except Exception as exc:
            if written:
                self._restore_snapshot(written)
            raise InstallError(f"installation failed; previous files were restored: {exc}") from exc
        return {"changed": planned, "skipped": self.skipped, "backup": str(backup_dir), "dry_run": False}

    def rollback(self, backup_dir: Path, codex_home: Path, project: Path | None = None) -> dict:
        codex_home = codex_home.expanduser().resolve()
        backup_dir = backup_dir.expanduser().resolve()
        backup_anchor = codex_home / "backups"
        if backup_anchor.exists() and _is_reparse_point(backup_anchor):
            raise InstallError(f"refusing symlink or reparse point as backup directory: {backup_anchor}")
        backup_parent = backup_anchor.resolve()
        if backup_dir.parent != backup_parent or not backup_dir.name.startswith("gpt6-agents-"):
            raise InstallError("rollback backup must be a direct gpt6-agents-* child of CODEX_HOME/backups")
        manifest_path = under(backup_dir, Path("manifest.json"), "manifest")
        if not manifest_path.is_file():
            raise InstallError(f"rollback manifest is missing: {manifest_path}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise InstallError(f"invalid rollback manifest: {exc}") from exc
        if (
            manifest.get("version") != 1
            or manifest.get("schema") != "gpt6-optimizer-v1"
            or not isinstance(manifest.get("root_ids"), list)
            or not isinstance(manifest.get("roots"), dict)
            or not isinstance(manifest.get("entries"), list)
            or not manifest.get("entries")
        ):
            raise InstallError("unsupported rollback manifest")
        roots = self._roots(codex_home, project)
        manifest_root_ids = manifest["root_ids"]
        manifest_roots = manifest["roots"]
        if (
            not all(isinstance(root, str) for root in manifest_root_ids)
            or set(manifest_roots) != set(manifest_root_ids)
            or not all(root in roots and isinstance(manifest_roots[root], str) for root in manifest_root_ids)
        ):
            raise InstallError("rollback manifest root IDs do not match available roots")
        for root_name in manifest_root_ids:
            if os.path.normcase(manifest_roots[root_name]) != os.path.normcase(str(roots[root_name].resolve())):
                raise InstallError(f"rollback root does not match the installation root: {root_name}")
        checked = []
        seen_targets: set[tuple[str, str]] = set()
        allowed_home = {"AGENTS.md", "config.toml", *(f"{name}.config.toml" for name in PROFILE_FILES), *(f"agents/{name}" for name in ROLE_FILES)}
        allowed_project = {"AGENTS.md", *(f"docs/agent-workflow/{name}" for name in ("task-card.md", "api-contract.md", "review-report.md", "pilot-results.csv"))}
        allowed = {"codex_home": allowed_home, "project": allowed_project}
        entry_roots = set()
        for entry in manifest["entries"]:
            if not isinstance(entry, dict) or entry.get("root") not in roots:
                raise InstallError("rollback manifest contains an invalid root")
            root_name = entry["root"]
            relative = safe_relative(entry.get("path"), "manifest target")
            key = (root_name, relative.as_posix())
            if key in seen_targets:
                raise InstallError("rollback manifest contains duplicate targets")
            seen_targets.add(key)
            entry_roots.add(root_name)
            if relative.as_posix() not in allowed[root_name]:
                raise InstallError(f"rollback target is outside managed destinations: {root_name}:{relative}")
            target = under(roots[root_name], relative, "manifest target")
            existed = entry.get("existed")
            if not isinstance(existed, bool) or not isinstance(entry.get("installed_sha256"), str):
                raise InstallError("rollback manifest entry is incomplete")
            current_hash = sha256_file(target) if target.is_file() else None
            if current_hash != entry["installed_sha256"]:
                raise InstallError(f"refusing rollback because target changed after install: {target}")
            backup_name = entry.get("backup")
            backup_bytes = None
            if existed:
                backup_rel = safe_relative(backup_name, "manifest backup")
                backup_path = under(backup_dir, backup_rel, "manifest backup")
                if not backup_path.is_file():
                    raise InstallError(f"rollback bytes are missing: {backup_path}")
                backup_bytes = backup_path.read_bytes()
                if sha256_bytes(backup_bytes) != entry.get("original_sha256"):
                    raise InstallError(f"rollback bytes hash mismatch: {backup_path}")
            elif backup_name is not None:
                raise InstallError("new target cannot have rollback bytes")
            checked.append((target, existed, backup_bytes))
        if set(manifest_root_ids) != entry_roots:
            raise InstallError("rollback manifest root IDs do not match its entries")
        for target, existed, backup_bytes in checked:
            if existed:
                recovery_write(target, backup_bytes or b"")
            elif target.exists():
                if not target.is_file() and not target.is_symlink():
                    raise InstallError(f"cannot remove non-file generated target: {target}")
                target.unlink()
        return {"restored": [str(target) for target, _, _ in checked], "backup": str(backup_dir)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", help="Codex home; defaults to CODEX_HOME or ~/.codex")
    parser.add_argument("--project", type=Path, help="optional project to receive AGENTS policy and templates")
    parser.add_argument("--dry-run", action="store_true", help="show changes without creating files")
    parser.add_argument("--replace-global-agents", action="store_true", help="allow replacing a differing global AGENTS.md")
    parser.add_argument("--rollback", type=Path, help="restore a backup manifest created by this installer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rollback and args.dry_run:
        print("error: --dry-run cannot be used with --rollback")
        return 2
    installer = Installer()
    home = resolve_codex_home(args.codex_home)
    try:
        if args.rollback:
            result = installer.rollback(args.rollback, home, args.project)
            print(f"restored {len(result['restored'])} file(s) from {result['backup']}")
        else:
            result = installer.install(home, args.project, args.dry_run, args.replace_global_agents)
            if result["dry_run"]:
                suffix = f"; skipped: {', '.join(result['skipped'])}" if result.get("skipped") else ""
                print("dry-run: " + (", ".join(result["changed"]) if result["changed"] else "no changes") + suffix)
            elif result["backup"]:
                suffix = f"; skipped: {', '.join(result['skipped'])}" if result.get("skipped") else ""
                print(f"installed {len(result['changed'])} file(s); backup: {result['backup']}{suffix}")
            else:
                suffix = f"; skipped: {', '.join(result['skipped'])}" if result.get("skipped") else ""
                print("already up to date; no backup created" + suffix)
    except InstallError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
