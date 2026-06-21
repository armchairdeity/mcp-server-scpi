#!/usr/bin/env bash
# PreToolUse/Bash hook: enforce "lint before tests".
# If a Bash command invokes pytest, run ruff first and DENY the pytest run
# (with the ruff output as the reason) when lint fails.
set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Only gate commands that actually invoke pytest (as a word, not a substring).
if ! printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_])pytest([^[:alnum:]_]|$)'; then
  exit 0
fi

proj="${CLAUDE_PROJECT_DIR:-.}"
cd "$proj" 2>/dev/null || exit 0

# Prefer the project venv's ruff; fall back to uv. Keep brew paths on PATH.
export PATH="/usr/local/bin:$HOME/.local/bin:$PATH"
if [ -x "$proj/.venv/bin/ruff" ]; then
  out=$("$proj/.venv/bin/ruff" check . 2>&1)
  status=$?
else
  out=$(uv run ruff check . 2>&1)
  status=$?
fi

if [ "$status" -eq 0 ]; then
  exit 0
fi

# Lint failed -> block the pytest run.
jq -n --arg reason "Lint must pass before tests. \`ruff check\` failed:

$out

Fix these, then re-run the tests." \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
exit 0
