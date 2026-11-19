#!/usr/bin/env bash
# Run one headless Copilot CLI session of the Adhoc QA agent.
#   bash qa/ci/run_agent.sh <learn|start|continue|report> [timeout, default 45m]
# Prompt = agent rules (.github/agents/adhoc-qa.agent.md without front matter) + CI rules + task.
set -uo pipefail
step="$1"; limit="${2:-45m}"
cd "$(dirname "$0")/../.."
TMPD="${RUNNER_TEMP:-/tmp}"
prompt="$TMPD/qa-prompt-$step.md"
logdir="qa/runs/_ci-logs"; mkdir -p "$logdir"

{
  awk 'NR==1 && /^---$/ {fm=1; next} fm && /^---$/ {fm=0; next} !fm' .github/agents/adhoc-qa.agent.md
  cat qa/ci/ci_rules.md
  printf '\n## Run context\n- commit: %s\n- trigger: %s by %s\n- session: %s\n' \
    "${GITHUB_SHA:0:8}" "${GITHUB_EVENT_NAME:-manual}" "${GITHUB_ACTOR:-?}" "$step"
  cat "qa/ci/prompts/$step.md"
} > "$prompt"

args=(
  -p "$(cat "$prompt")"
  --allow-all-tools
  --disable-builtin-mcps
  --additional-mcp-config "@$TMPD/mcp.json"
  --deny-tool 'shell(git:*)' --deny-tool 'shell(npm:*)' --deny-tool 'shell(npx:*)'
  --deny-tool 'shell(curl:*)' --deny-tool 'shell(wget:*)' --deny-tool 'shell(gh:*)'
  --share="$logdir/$(date +%H%M%S)-$step.md"
)
[ -n "${COPILOT_MODEL:-}" ] && args+=(--model "$COPILOT_MODEL")

echo "::group::Copilot session: $step"
timeout "$limit" copilot "${args[@]}"
rc=$?
echo "::endgroup::"
echo "copilot session '$step' exit code $rc"
[ "$rc" -eq 124 ] && echo "::warning::Session '$step' hit the $limit limit; the next session resumes from the ledger."
exit 0
