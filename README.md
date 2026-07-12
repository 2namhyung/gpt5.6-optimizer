# GPT-5.6 Optimizer

A compact Codex configuration for routing work across GPT-5.6 Sol and Luna agents while limiting context growth and plugin overhead.

## Defaults

- Main orchestrator: GPT-5.6 Sol, medium reasoning
- Research: GPT-5.6 Luna, xhigh reasoning
- Routine implementation: GPT-5.6 Luna, high reasoning
- Review and difficult work: GPT-5.6 Sol, high reasoning
- Context window: 260,000 tokens
- Automatic compaction: 220,000 total active-context tokens
- Plugins: keep only GitHub and browser/computer-control plugins globally enabled
- RTK: optional, only for noisy tests, builds, lint, logs, and large diffs

The context cap stays below the 272K-input long-context pricing boundary documented for GPT-5.6 Sol. It is a conservative active-context limit, not a substitute for splitting a single oversized file or tool result.

## Install

1. Back up your existing Codex configuration.
2. Copy `config.example.toml` to your Codex home as `config.toml`, then merge any authentication, MCP, notification, marketplace, and project-trust settings you need.
3. Copy `AGENTS.md` to your Codex home.
4. Copy the `agents` directory to your Codex home.
5. Restart Codex.

On Windows, the default Codex home is `%USERPROFILE%\.codex`. On macOS and Linux, it is usually `~/.codex`.

The example deliberately uses `approval_policy = "on-request"` and `sandbox_mode = "workspace-write"`. Do not copy machine-specific paths, hook hashes, runtime environment values, or project trust entries into a public repository.

## Plugin policy

The example globally enables only:

- GitHub
- Computer Use
- Chrome
- In-app Browser

Document, spreadsheet, presentation, Vercel, Supabase, Netlify, PDF, Sites, and other specialist plugins are disabled to avoid injecting large skill catalogs into every task. Enable them only when the current work needs them.

## RTK policy

RTK is useful when a command would otherwise emit a large amount of text. Native `rg`, targeted reads, `git status --short`, and `git diff --stat` are already compact and should normally remain native. If RTK filters out a needed detail, rerun a narrower native command.

## Files

- `AGENTS.md`: compact global routing and token-discipline instructions
- `config.example.toml`: sanitized Codex configuration template
- `agents/*.toml`: role-specific subagent definitions

## License

MIT

