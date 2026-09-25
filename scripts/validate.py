"""Static repository validation with no dependency on a user's Codex home."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "token_explorer": ("gpt-6-luna", "high"),
    "token_researcher": ("gpt-6-luna", "high"),
    "token_worker": ("gpt-6-luna", "high"),
    "frontend_builder": ("gpt-6-sol", "medium"),
    "backend_builder": ("gpt-6-sol", "medium"),
    "database_builder": ("gpt-6-sol", "high"),
    "token_verifier": ("gpt-6-luna", "high"),
    "token_reviewer": ("gpt-6-sol", "high"),
    "frontier_specialist": ("gpt-6-astra", "high"),
}
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


def load(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except Exception as exc:
        raise AssertionError(f"{path.relative_to(ROOT)}: invalid TOML: {exc}") from exc


def validate() -> list[str]:
    errors: list[str] = []
    roles = ROOT / "codex" / "agents"
    if len(ROLE_FILES) != len(EXPECTED):
        errors.append("validator role map is incomplete")
    seen = set()
    for filename in ROLE_FILES:
        path = roles / filename
        if not path.is_file():
            errors.append(f"missing role: {path.relative_to(ROOT)}")
            continue
        try:
            data = load(path)
        except AssertionError as exc:
            errors.append(str(exc))
            continue
        name = data.get("name")
        seen.add(name)
        for key in ("name", "description", "model", "model_reasoning_effort", "sandbox_mode", "developer_instructions"):
            if not data.get(key):
                errors.append(f"{path.relative_to(ROOT)} missing {key}")
        if name not in EXPECTED:
            errors.append(f"unexpected role name {name!r} in {filename}")
            continue
        expected_model, expected_effort = EXPECTED[name]
        if (data.get("model"), data.get("model_reasoning_effort")) != (expected_model, expected_effort):
            errors.append(f"{filename}: model/effort does not match expected map")
        if data.get("agents", {}).get("enabled") is not False:
            errors.append(f"{filename}: agents.enabled must be false")
        instructions = str(data.get("developer_instructions", "")).lower()
        if not any(token in instructions for token in ("subagent", "재위임", "reassign")):
            errors.append(f"{filename}: delegation prohibition is missing")
    if seen != set(EXPECTED):
        errors.append(f"role set mismatch: expected {sorted(EXPECTED)}, found {sorted(seen)}")

    fragment = ROOT / "codex" / "config-fragment.toml"
    if fragment.is_file():
        try:
            config = load(fragment)
            expected_root = {
                "model": "gpt-6-sol",
                "model_reasoning_effort": "medium",
                "model_verbosity": "low",
                "model_context_window": 260000,
                "model_auto_compact_token_limit": 220000,
                "model_auto_compact_token_limit_scope": "total",
                "service_tier": "default",
            }
            for key, value in expected_root.items():
                if config.get(key) != value:
                    errors.append(f"config-fragment: {key} is not {value!r}")
            agents = config.get("agents", {})
            for key, value in {
                "enabled": True,
                "max_concurrent_threads_per_session": 3,
                "default_subagent_model": "gpt-6-sol",
                "default_subagent_reasoning_effort": "medium",
                "interrupt_message": True,
            }.items():
                if agents.get(key) != value:
                    errors.append(f"config-fragment agents.{key} is not {value!r}")
            if "max_threads" in agents:
                errors.append("config-fragment retains legacy agents.max_threads")
        except AssertionError as exc:
            errors.append(str(exc))
    else:
        errors.append("missing codex/config-fragment.toml")

    for relative in (
        "README.md",
        "docs/design.md",
        "project/AGENTS.md",
        "templates/task-card.md",
        "templates/api-contract.md",
        "templates/review-report.md",
        "templates/pilot-results.csv",
        "scripts/install.py",
        "requirements.txt",
    ):
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")
    for relative in ("README.md", "docs/design.md", "codex/AGENTS.md"):
        text = (ROOT / relative).read_text(encoding="utf-8") if (ROOT / relative).is_file() else ""
        if "C:\\Users\\" in text or "chatgpt.com/c/" in text:
            errors.append(f"private path or conversation URL found in public file: {relative}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VALIDATION PASSED: {len(EXPECTED)} roles, config fragment, docs, and templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
