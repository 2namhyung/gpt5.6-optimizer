#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME_ARG="${CODEX_HOME:-$HOME/.codex}"
PROJECT_ARG="${1:-}"
INSTALL_ARGS=(--codex-home "$CODEX_HOME_ARG")
if [[ "${REPLACE_GLOBAL_AGENTS:-0}" == "1" ]]; then
  INSTALL_ARGS+=(--replace-global-agents)
fi

if [[ -n "$PROJECT_ARG" ]]; then
  python scripts/install.py "${INSTALL_ARGS[@]}" --project "$PROJECT_ARG"
else
  python scripts/install.py "${INSTALL_ARGS[@]}"
fi
