param(
  [string]$CodexHome = "$HOME\.codex",
  [string]$Project = "",
  [switch]$ReplaceGlobalAgents
)

$arguments = @("scripts/install.py", "--codex-home", $CodexHome)
if ($Project) { $arguments += @("--project", $Project) }
if ($ReplaceGlobalAgents) { $arguments += "--replace-global-agents" }
python @arguments
exit $LASTEXITCODE
