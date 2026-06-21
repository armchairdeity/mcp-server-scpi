#!/usr/bin/env bash
# PreToolUse/Bash hook: enforce "lint before tests" — but FAIL OPEN.
#
# If a Bash command invokes pytest, run ruff first and DENY the run ONLY when
# ruff reports actual lint findings (exit 1). If the linter can't be found, or
# ruff errors out for any other reason, allow the tests through (with a warning
# on stderr) so a missing tool never blocks a run. The gate should catch real
# lint problems, not punish an environment that lacks jq/ruff/uv.
set -uo pipefail

# Without jq we can't parse the hook payload at all — fail open.
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Only gate commands that actually invoke pytest (as a word, not a substring).
printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_])pytest([^[:alnum:]_]|$)' || exit 0

proj="${CLAUDE_PROJECT_DIR:-.}"
cd "$proj" 2>/dev/null || exit 0

# Keep brew / user-local tools reachable regardless of how Claude Code launched.
export PATH="/usr/local/bin:$HOME/.local/bin:$PATH"

# Resolve a ruff command: project venv first (pinned version), then uv. If
# neither exists, skip the gate rather than blocking.
if [ -x "$proj/.venv/bin/ruff" ]; then
  ruff_cmd=("$proj/.venv/bin/ruff")
elif command -v uv >/dev/null 2>&1; then
  ruff_cmd=(uv run ruff)
else
  echo "lint-before-tests: no ruff (.venv) or uv found — skipping lint gate." >&2
  exit 0
fi

out=$("${ruff_cmd[@]}" check . 2>&1)
status=$?

if [ "$status" -eq 0 ]; then
  exit 0  # clean — let the tests run
elif [ "$status" -ne 1 ]; then
  # Exit 1 = real lint findings. Anything else (2 = ruff/config error, 127 =
  # binary vanished, etc.) is not a lint failure — fail open with a warning.
  echo "lint-before-tests: ruff did not run cleanly (exit $status) — allowing tests." >&2
  exit 0
fi

# status == 1: genuine lint findings -> block the pytest run.
jq -n --arg reason "Lint must pass before tests. \`ruff check\` failed:

$out

Fix these, then re-run the tests." \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
exit 0
