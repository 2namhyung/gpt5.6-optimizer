# Global Codex Token Discipline

Be concise; preserve only relevant exact code, commands, errors, and paths.

Use targeted `rg` and file reads, narrow or path-scoped diffs, and focused log reruns. Use `rtk` only for supported commands expected to emit large output, such as tests, builds, lint, long logs, or large diffs. Use native commands for already-compact output and rerun narrowly when filtered details are needed.

Delegate every substantive task to one fitting agent when available: `token_explorer` for discovery, `token_researcher` for docs/web, `token_worker` for bounded edits, `token_verifier` for tests/runtime, `token_reviewer` for independent Sol review, and `frontier_specialist` for ambiguous, high-risk, or repeatedly failing work. The main agent scopes, coordinates, waits, verifies, and synthesizes without duplicating delegated work.

Use one subagent by default; add agents only for independent workstreams. Run independent reads in parallel, serialize overlapping writes, and keep delegation depth at one. State the objective, scope and ownership, approval boundaries, required evidence, and expected result. The main agent reads required skill instructions itself.

