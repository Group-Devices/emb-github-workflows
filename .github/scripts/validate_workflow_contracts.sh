#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

require_file() {
  local path="$1"
  test -f "$repo_root/$path"
}

require_pattern() {
  local pattern="$1"
  local path="$2"
  grep -q "$pattern" "$repo_root/$path"
}

build_current_context() {
  jq -n --compact-output '{
    repo: env.GITHUB_REPOSITORY,
    owner: env.GITHUB_REPOSITORY_OWNER,
    run_id: env.GITHUB_RUN_ID,
    run_number: env.GITHUB_RUN_NUMBER,
    run_attempt: env.GITHUB_RUN_ATTEMPT,
    sha: env.GITHUB_SHA,
    ref: env.GITHUB_REF,
    actor: env.GITHUB_ACTOR,
    workflow: env.GITHUB_WORKFLOW
  }'
}

echo "Checking helper actions"
require_file ".github/actions/build-source-build-context/action.yml"
require_file ".github/actions/restore-conan-build-state/action.yml"
require_file ".github/actions/upload-conan-build-state/action.yml"
require_file ".github/actions/gh-auth-owner/action.yml"

echo "Checking workflow wiring"
require_pattern "source-build-context:" ".github/workflows/conan-library.yml"
require_pattern "build-source-build-context@release/v1.0" ".github/workflows/conan-library.yml"
require_pattern "source_build_context" ".github/workflows/conan-context-delivery.yml"
require_pattern "context-key: collector_context" ".github/workflows/conan-context-delivery.yml"
require_pattern "lockfile-partial" ".github/workflows/conan-context-delivery.yml"

echo "Checking source_build_context helper contract"
require_pattern "^  append-key:" ".github/actions/build-source-build-context/action.yml"
require_pattern "^  incoming-context:" ".github/actions/build-source-build-context/action.yml"
require_pattern "^  fallback-context:" ".github/actions/build-source-build-context/action.yml"
require_pattern "^  context:" ".github/actions/build-source-build-context/action.yml"

export GITHUB_REPOSITORY="Group-Devices/secretary.sdk"
export GITHUB_REPOSITORY_OWNER="Group-Devices"
export GITHUB_RUN_ID="1001"
export GITHUB_RUN_NUMBER="42"
export GITHUB_RUN_ATTEMPT="1"
export GITHUB_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
export GITHUB_REF="refs/heads/main"
export GITHUB_ACTOR="package-bot"
export GITHUB_WORKFLOW="CI"

PACKAGE_CONTEXT="$(build_current_context)"
CHAIN="$(printf '%s' '{}' | jq -c --arg key "package_context" --argjson current "$PACKAGE_CONTEXT" '. + {($key): $current}')"
echo "$CHAIN" | jq -e '
  .package_context.repo == "Group-Devices/secretary.sdk" and
  .package_context.run_id == "1001" and
  .package_context.workflow == "CI"
' >/dev/null

export GITHUB_REPOSITORY="Group-Devices/collect-secretary"
export GITHUB_REPOSITORY_OWNER="Group-Devices"
export GITHUB_RUN_ID="2002"
export GITHUB_RUN_NUMBER="314"
export GITHUB_RUN_ATTEMPT="2"
export GITHUB_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
export GITHUB_REF="refs/heads/main"
export GITHUB_ACTOR="collector-bot"
export GITHUB_WORKFLOW="rebuild"

COLLECTOR_CONTEXT="$(build_current_context)"
CHAIN="$(printf '%s' "$CHAIN" | jq -c --arg key "collector_context" --argjson current "$COLLECTOR_CONTEXT" '. + {($key): $current}')"
echo "$CHAIN" | jq -e '
  .package_context.repo == "Group-Devices/secretary.sdk" and
  .collector_context.repo == "Group-Devices/collect-secretary" and
  .collector_context.run_id == "2002" and
  .collector_context.workflow == "rebuild"
' >/dev/null

echo "Workflow contract checks passed"
